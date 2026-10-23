"""Bounded, deterministic SVG views of stored intraprocedural CFG facts.

No decoder, Graphviz process, browser, or runtime is involved. Block membership
comes from the CFG query; names never create or terminate a block here.
"""
from __future__ import annotations

from collections import defaultdict, deque
from html import escape
import heapq
import json
from pathlib import Path
import unicodedata


_MAX_NODES = 10000
_MAX_BLOCKS = 2000
_MAX_EDGES = 20000
_MAX_DIMENSION = 200000
_MAX_TEXT = 4096
_MAX_SVG_BYTES = 32 * 1024 * 1024
_BLOCK_WIDTH = 952
_COLUMN_GAP = 64
_LINE = 26
_PAD = 36


def _clean(value, limit=_MAX_TEXT):
    text = '' if value is None else str(value)
    if len(text) > limit:
        raise ValueError(f'CFG render text exceeds {limit} characters')
    return ''.join(' ' if ch.isspace() else ch for ch in text
                   if ch.isspace() or not unicodedata.category(ch).startswith('C'))


def _wrap(value, columns=80):
    text = _clean(value)
    result, line, cells = [], '', 0
    for ch in text:
        size = 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 0 if unicodedata.combining(ch) else 1
        if line and cells + size > columns:
            result.append(line)
            line, cells = '', 0
        line += ch
        cells += size
    return result + [line] if line or not result else result


def _list(snapshot, key, limit):
    value = snapshot.get(key, [])
    if not isinstance(value, list) or len(value) > limit or any(not isinstance(item, dict) for item in value):
        raise ValueError(f'CFG {key} must contain at most {limit} objects')
    return value


def _ranks(blocks, edges):
    """SCC-aware layers, with breadth-first levels inside each loop component."""
    order = {block['id']: index for index, block in enumerate(blocks)}
    outgoing, incoming = defaultdict(set), defaultdict(set)
    for edge in edges:
        if edge.get('target_block') is not None:
            source, target = edge['source_block'], edge['target_block']
            outgoing[source].add(target)
            incoming[target].add(source)
    # Iterative Kosaraju keeps even a long 2,000-block chain off Python's stack.
    visited, finished = set(), []
    for block in order:
        if block in visited:
            continue
        stack = [(block, False)]
        while stack:
            current, done = stack.pop()
            if done:
                finished.append(current)
            elif current not in visited:
                visited.add(current)
                stack.append((current, True))
                stack.extend((target, False) for target in sorted(outgoing[current], key=order.get, reverse=True)
                             if target not in visited)
    component, members = {}, []
    for block in reversed(finished):
        if block in component:
            continue
        index = len(members)
        members.append([])
        stack = [block]
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component[current] = index
            members[index].append(current)
            stack.extend(sorted(incoming[current], key=order.get, reverse=True))
    levels, spans, successors, indegree = {}, {}, defaultdict(set), defaultdict(int)
    for index, group in enumerate(members):
        root = min(group, key=order.get)
        levels[root] = 0
        queue = deque([root])
        while queue:
            current = queue.popleft()
            for target in sorted(outgoing[current], key=order.get):
                if component[target] == index and target not in levels:
                    levels[target] = levels[current] + 1
                    queue.append(target)
        spans[index] = max(levels[node] for node in group) + 1
        for node in group:
            for target in outgoing[node]:
                other = component[target]
                if other != index and other not in successors[index]:
                    successors[index].add(other)
                    indegree[other] += 1
    priorities = {index: min(order[node] for node in group) for index, group in enumerate(members)}
    ready = [(priorities[index], index) for index in range(len(members)) if not indegree[index]]
    heapq.heapify(ready)
    offsets = defaultdict(int)
    while ready:
        _, current = heapq.heappop(ready)
        for target in sorted(successors[current], key=priorities.get):
            offsets[target] = max(offsets[target], offsets[current] + spans[current])
            indegree[target] -= 1
            if not indegree[target]:
                heapq.heappush(ready, (priorities[target], target))
    return {node: offsets[component[node]] + levels[node] for node in order}


def _address(item):
    return _clean(item.get('segmented_address') or item.get('address') or '?', 128)


def _edge_label(edge, index):
    predicate = edge.get('predicate') or {}
    outcome = predicate.get('outcome')
    kind = outcome.replace('_', ' ') if outcome else _clean(edge.get('kind', 'edge'), 128)
    if edge.get('assumed_return'):
        kind += '; assumes return'
    target = _clean(edge.get('target_block') or ('outside ' + str(edge.get('target_segmented_address') or edge.get('target_address') or edge.get('target') or '?')))
    return f'e{index} -> {target}  [{kind}]'


def render_cfg(snapshot: dict, path: str | Path) -> dict:
    """Export a full CFG query as selectable SVG text, or fail before writing.

    At most 10,000 instructions, 2,000 blocks and 20,000 block edges are
    accepted. Oversized text/layouts fail explicitly; no block is truncated.
    The supplied basic-block membership must cover every instruction exactly.
    """
    if not isinstance(snapshot, dict):
        raise ValueError('CFG snapshot must be an object')
    output = Path(path).expanduser().resolve()
    if output.suffix.lower() != '.svg':
        raise ValueError('CFG render format must be svg')
    nodes = _list(snapshot, 'nodes', _MAX_NODES)
    blocks = _list(snapshot, 'basic_blocks', _MAX_BLOCKS)
    edges = _list(snapshot, 'block_edges', _MAX_EDGES)
    calls = _list(snapshot, 'calls', _MAX_EDGES)
    highlights = _list(snapshot, 'highlights', 100)
    by_node, by_block, membership = {}, {}, {}
    for node in nodes:
        identity = node.get('id')
        if not isinstance(identity, str) or not identity or identity in by_node:
            raise ValueError('CFG instruction IDs must be unique nonempty strings')
        if _clean(identity) != identity:
            raise ValueError('CFG instruction IDs must not contain control characters')
        by_node[identity] = node
    for block in blocks:
        identity, ids = block.get('id'), block.get('instruction_ids')
        if not isinstance(identity, str) or not identity or identity in by_block:
            raise ValueError('CFG block IDs must be unique nonempty strings')
        if _clean(identity) != identity:
            raise ValueError('CFG block IDs must not contain control characters')
        if not isinstance(ids, list) or not ids:
            raise ValueError('CFG blocks require nonempty instruction_ids')
        for node_id in ids:
            if not isinstance(node_id, str) or node_id not in by_node or node_id in membership:
                raise ValueError('CFG blocks must contain each stored instruction exactly once')
            membership[node_id] = identity
        by_block[identity] = block
    if set(membership) != set(by_node):
        raise ValueError('CFG blocks must contain each stored instruction exactly once')
    outgoing = defaultdict(list)
    for index, edge in enumerate(edges):
        source, target = edge.get('source_block'), edge.get('target_block')
        if source not in by_block or target is not None and target not in by_block:
            raise ValueError('CFG edge refers to an unknown block')
        if membership.get(edge.get('source')) != source or (target is not None and membership.get(edge.get('target')) != target):
            raise ValueError('CFG edge instruction endpoints disagree with block membership')
        outgoing[source].append((index, edge))
    call_sources = defaultdict(list)
    for call in calls:
        call_sources[call.get('source')].append(call)
    labels, selected_nodes = defaultdict(list), set()
    for highlight in highlights:
        label = _clean(highlight.get('label', highlight.get('address', '?')))
        for match in highlight.get('matches', []):
            if isinstance(match, dict) and match.get('instruction') in membership:
                labels[membership[match['instruction']]].append(label)
                selected_nodes.add(match['instruction'])
    selected_nodes.update(node['id'] for node in nodes if node.get('highlights'))
    for block in blocks:
        for label in block.get('highlights', []):
            cleaned = _clean(label)
            if cleaned not in labels[block['id']]:
                labels[block['id']].append(cleaned)

    header = [('fDisBull / CONTROL FLOW', 'title')]
    header += [(f'ENTRY {_address(snapshot)}  |  VERSION {_clean(snapshot.get("version", "?"), 128)}  |  CONTEXT {_clean(snapshot.get("context", "?"), 128)}', 'muted'),
               (f'STATUS {_clean(snapshot.get("status", "candidate"), 128)} / function boundary not proven / static stored-graph slice', 'warning'),
               (f'{len(nodes)} instructions / {len(blocks)} blocks / {len(edges)} block edges / {len(calls)} calls (not entered)', 'text'),
               (f'Graph closed: {bool(snapshot.get("graph_closed"))}  |  budget exhausted: {bool(snapshot.get("budget_exhausted"))}  |  unresolved: {len(snapshot.get("unresolved", []))}  |  gaps: {len(snapshot.get("gaps", []))}  |  frontier: {len(snapshot.get("frontier", []))}', 'text')]
    assumptions = snapshot.get('assumptions', [])
    if not isinstance(assumptions, list) or len(assumptions) > 100:
        raise ValueError('CFG assumptions must be a list of at most 100 strings')
    for assumption in assumptions:
        header.extend((line, 'muted') for line in _wrap('ASSUMPTION: ' + _clean(assumption), 135))
    header.extend((line, 'muted') for line in _wrap('No branch outcomes are evaluated; this view is not runtime execution evidence.', 135))
    for item in highlights:
        state = 'REACHED' if item.get('reachable') else 'NOT REACHED (not proof of runtime unreachability)'
        header.extend((line, 'highlight') for line in _wrap(f'SELECTED: {_clean(item.get("label", item.get("address", "?")))} / {state}', 135))
    header.extend((line, 'muted') for line in _wrap('Read top to bottom. Dashed edges assume a call returns. Hover an edge for exact endpoints/evidence; click an edge label to jump to its target block.', 135))
    header = [(line, kind) for value, kind in header for line in _wrap(value, 135)]
    top = _PAD + 38 + (len(header) - 1) * _LINE + 50

    content = {}
    for block in blocks:
        identity = block['id']
        lines = []
        for label in labels[identity]:
            lines.extend(('highlight', line, None) for line in _wrap('SELECTED: ' + label))
        for node_id in block['instruction_ids']:
            node = by_node[node_id]
            instruction = f'{_address(node)}  {_clean(node.get("mnemonic", "?"), 80)} {_clean(node.get("display_operands", node.get("operands", "")))}'.rstrip()
            for number, line in enumerate(_wrap(instruction)):
                lines.append(('selected-instruction' if node_id in selected_nodes else 'instruction', line, node_id if number == 0 else None))
            for call in call_sources[node_id]:
                target = call.get('target_segmented_address') or call.get('target_address') or 'unresolved'
                lines.extend(('muted', line, None) for line in _wrap(f'  call target: {_clean(target)} (not entered)'))
        for index, edge in outgoing[identity]:
            lines.extend(('edge-label', line, index) for line in _wrap(_edge_label(edge, index)))
        name = _clean(block.get('name', ''), 512)
        title = f'{identity}  {_address(block)}' + (f'  {name}' if name else '')
        title_lines = _wrap(title)
        context_lines = _wrap(_clean(block.get('context', '?'), 256))
        height = 32 + (len(title_lines) + len(context_lines) + len(lines)) * _LINE + 20
        content[identity] = dict(lines=lines, title=title_lines, context=context_lines, height=height)

    ranks = _ranks(blocks, edges)
    layers = defaultdict(list)
    for block in blocks:
        layers[ranks[block['id']]].append(block['id'])
    rows = [group[start:start + 3] for _, group in sorted(layers.items()) for start in range(0, len(group), 3)]
    columns = max((len(row) for row in rows), default=1)
    graph_right = _PAD + columns * _BLOCK_WIDTH + (columns - 1) * _COLUMN_GAP
    boxes, row_info = {}, []
    y = top
    for row_index, group in enumerate(rows):
        height = max(content[identity]['height'] for identity in group)
        row_info.append((y, height))
        for column, identity in enumerate(group):
            boxes[identity] = dict(x=_PAD + column * (_BLOCK_WIDTH + _COLUMN_GAP), y=y,
                                   width=_BLOCK_WIDTH, height=content[identity]['height'], row=row_index)
        y += height + 112
    width = max(1560, graph_right + (len(edges) * 8 + 76 if edges else _PAD))
    height = max(top + 120, y + 50)
    if width > _MAX_DIMENSION or height > _MAX_DIMENSION:
        raise ValueError('CFG render exceeds maximum layout dimensions; request a smaller CFG')
    block_dom = {block['id']: f'cfg-block-{index}' for index, block in enumerate(blocks)}
    colors = {'text': '#f1f5fb', 'muted': '#b8c6d9', 'warning': '#ffdc91', 'highlight': '#ffe08a',
              'instruction': '#edf5ff', 'selected-instruction': '#ffe08a', 'edge-label': '#accbff', 'title': '#f1f5fb'}
    def text(x, y, value, kind='text', size=18, extra=''):
        return f'<text x="{x}" y="{y}" font-size="{size}" fill="{colors[kind]}" xml:space="preserve" {extra}>{escape(_clean(value))}</text>'
    summary = dict(version=snapshot.get('version'), entry=snapshot.get('entry'), status=snapshot.get('status', 'candidate'),
                   instruction_count=len(nodes), block_count=len(blocks), edge_count=len(edges),
                   unresolved_count=len(snapshot.get('unresolved', [])), gap_count=len(snapshot.get('gaps', [])),
                   frontier_count=len(snapshot.get('frontier', [])), budget_exhausted=bool(snapshot.get('budget_exhausted')))
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="cfg-title cfg-desc">',
             '<title id="cfg-title">fDisBull static candidate control-flow graph</title>',
             '<desc id="cfg-desc">Selectable instruction text. Highlighted blocks contain selected addresses. Calls are not entered; continuation assumes return. Edge labels link to their target blocks.</desc>',
             f'<metadata>{escape(json.dumps(summary, ensure_ascii=True, sort_keys=True))}</metadata>',
             '<style>.edge path{fill:none;stroke-width:2;pointer-events:stroke}.edge:hover path{stroke:#fff;stroke-width:5}.block:target rect,.block:hover rect{stroke:#fff;stroke-width:3}a:hover text{fill:#fff;text-decoration:underline}text{user-select:text}</style>',
             '<defs><marker id="cfg-arrow" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto" markerUnits="userSpaceOnUse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#c7d6eb"/></marker></defs>',
             '<rect width="100%" height="100%" fill="#101722"/>',
             '<g font-family="DejaVu Sans Mono, Menlo, Consolas, monospace">']
    header_y = _PAD + 26
    for index, (value, kind) in enumerate(header):
        parts.append(text(_PAD, header_y, value, kind, 26 if index == 0 else 18))
        header_y += 38 if index == 0 else _LINE
    for index, edge in enumerate(edges):
        source = boxes[edge['source_block']]
        source_row_y, source_row_height = row_info[source['row']]
        sx, sy = source['x'] + source['width'] - 28, source['y'] + source['height']
        exit_y = source_row_y + source_row_height + 30
        lane = graph_right + 32 + index * 8
        target_id = edge.get('target_block')
        if target_id is not None:
            target = boxes[target_id]
            tx, ty = target['x'] + 28, target['y']
            entry_y = row_info[target['row']][0] - 30
            route = f'M {sx} {sy} V {exit_y} H {lane} V {entry_y} H {tx} V {ty}'
        else:
            route = f'M {sx} {sy} V {exit_y} H {lane}'
        title = (f'e{index}: {edge["source_block"]} ({_clean(edge.get("source"))}) -> '
                 f'{_clean(target_id or "outside rendered graph")} ({_clean(edge.get("target"))}); '
                 f'{_clean(edge.get("kind"))}; provenance: {_clean(edge.get("provenance"))}; '
                 f'{_clean(edge.get("evidence"))}')
        if edge.get('predicate'):
            title += f'; outcome: {_clean(edge["predicate"].get("outcome"))}; truth not evaluated'
        if edge.get('assumed_return'):
            title += '; assumes call returns'
        color = '#a9c8ff' if edge.get('kind') != 'fallthrough' else '#758ba9'
        dash = ' stroke-dasharray="8 5"' if edge.get('assumed_return') or target_id is None else ''
        parts.append(f'<g class="edge" id="cfg-edge-{index}" data-source-block="{escape(edge["source_block"], quote=True)}" data-target-block="{escape(target_id or "", quote=True)}"><title>{escape(title)}</title><path d="{route}" stroke="{color}"{dash} marker-end="url(#cfg-arrow)"/></g>')
    for block in blocks:
        identity, box = block['id'], boxes[block['id']]
        selected = bool(labels[identity])
        parts.append(f'<g class="block{" selected" if selected else ""}" id="{block_dom[identity]}" data-block-id="{escape(identity, quote=True)}" data-instruction-count="{len(block["instruction_ids"])}">')
        parts.append(f'<title>{escape(_clean(identity))}: {len(block["instruction_ids"])} exact stored instructions; context {escape(_clean(block.get("context")))}</title>')
        parts.append(f'<rect class="block-box" x="{box["x"]}" y="{box["y"]}" width="{box["width"]}" height="{box["height"]}" rx="8" fill="{"#302a28" if selected else "#182334"}" stroke="{"#ffe08a" if selected else "#60738d"}" stroke-width="2"/>')
        current_y = box['y'] + 30
        for line in content[identity]['title']:
            parts.append(text(box['x'] + 18, current_y, line, 'highlight' if selected else 'text', extra='font-weight="700"'))
            current_y += _LINE
        for line in content[identity]['context']:
            parts.append(text(box['x'] + 18, current_y, line, 'muted'))
            current_y += _LINE
        for kind, line, item in content[identity]['lines']:
            if kind in ('instruction', 'selected-instruction') and item is not None:
                node = by_node[item]
                tooltip = f'{item}; bytes: {_clean(node.get("bytes"))}; raw: {_clean(node.get("mnemonic"))} {_clean(node.get("raw_operands", node.get("operands", "")))}'
                parts.append(f'<g class="instruction" data-instruction-id="{escape(item, quote=True)}"><title>{escape(tooltip)}</title>{text(box["x"] + 18, current_y, line, kind)}</g>')
            elif kind == 'edge-label' and edges[item].get('target_block') is not None:
                parts.append(f'<a href="#{block_dom[edges[item]["target_block"]]}">{text(box["x"] + 18, current_y, line, kind)}</a>')
            else:
                parts.append(text(box['x'] + 18, current_y, line, kind))
            current_y += _LINE
        parts.append('</g>')
    if not blocks:
        parts.append(text(_PAD, top + 26, 'No stored instruction blocks at this exact entry.', 'warning'))
    parts.append(text(_PAD, height - 25, 'STATIC DATABASE FACTS / Candidate reachability, not execution or proven function ownership.', 'muted'))
    parts.append('</g></svg>\n')
    document = '\n'.join(parts)
    if len(document.encode('utf-8')) > _MAX_SVG_BYTES:
        raise ValueError('CFG render exceeds maximum SVG size; request a smaller CFG')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding='utf-8')
    return dict(path=str(output), format='svg', width=width, height=height, block_count=len(blocks),
                instruction_count=len(nodes), edge_count=len(edges), highlighted_block_count=sum(bool(labels[b['id']]) for b in blocks),
                highlighted_instruction_count=len(selected_nodes),
                external_edge_count=sum(edge.get('target_block') is None for edge in edges))
