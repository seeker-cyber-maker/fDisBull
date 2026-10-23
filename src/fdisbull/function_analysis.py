"""Candidate function membership over architecture-neutral stored CFG facts.

Reachability is many-to-many: another entry or a label never confers exclusive
ownership. Calls are excluded, and no missing instruction is decoded here.
"""
from __future__ import annotations

from collections import defaultdict, deque


_MAX_NODES = 100000
_MAX_EDGES = 500000
_MAX_ENTRIES = 10000
_MAX_FRONTIER = 10000
_CALL_KINDS = {'call', 'resolved_call', 'indirect_call', 'callee', 'tail_call'}
_FLOW_KINDS = {'branch', 'resolved_branch', 'jump', 'conditional', 'fallthrough', 'next', 'taken', 'not_taken', ''}
_TERMINALS = {'return', 'stop'}


def _number(value):
    if isinstance(value, bool):
        raise ValueError('instruction addresses must be integers or hexadecimal strings')
    if isinstance(value, int):
        result = value
    elif isinstance(value, str):
        try:
            result = int(value, 0)
        except ValueError:
            result = int(value, 16)
    else:
        raise ValueError('instruction addresses must be integers or hexadecimal strings')
    if not 0 <= result < 1 << 64:
        raise ValueError('instruction addresses must fit unsigned 64-bit values')
    return result


def _records(value, name, limit):
    if not isinstance(value, (list, tuple)) or len(value) > limit or any(not isinstance(item, dict) for item in value):
        raise ValueError(f'{name} must be a list of at most {limit} objects')
    return value


def _runs(ids, by_id, addresses, order):
    result = []
    ordered = sorted(ids, key=lambda identity: (str(by_id[identity].get('context') or ''), addresses[identity], order[identity]))
    for identity in ordered:
        node, address = by_id[identity], addresses[identity]
        end = address + node['size']
        if result and result[-1]['context'] == node.get('context') and int(result[-1]['end'], 16) == address:
            result[-1]['end'] = hex(end)
            result[-1]['size'] += node['size']
            result[-1]['instruction_ids'].append(identity)
        else:
            result.append(dict(context=node.get('context'), start=hex(address), end=hex(end),
                               size=node['size'], instruction_ids=[identity]))
    return result


def _blocks(nodes, outgoing, incoming, entry_ids, addresses):
    """Collapse only exact straight lines; all candidate entries are leaders."""
    by_id = {node['id']: node for node in nodes}
    leaders = set(entry_ids)
    for node in nodes:
        identity = node['id']
        if len(incoming[identity]) != 1:
            leaders.add(identity)
        if node.get('flow', 'next') != 'next' or len(outgoing[identity]) != 1:
            leaders.update(edge['target'] for edge in outgoing[identity] if edge['target'] in by_id)
    assigned, result = {}, []

    def consume(start):
        members, current = [], start
        block_id = f'b{len(result)}'
        while current not in assigned:
            assigned[current] = block_id
            members.append(current)
            node, following = by_id[current], outgoing[current]
            if node.get('flow', 'next') != 'next' or len(following) != 1:
                break
            target = following[0]['target']
            if target not in by_id or target in leaders or target in assigned:
                break
            next_node = by_id[target]
            expected = node.get('next_address')
            if expected is None:
                expected = addresses[current] + node['size']
            if next_node.get('context') != node.get('context') or _number(expected) != addresses[target]:
                break
            current = target
        first, last = by_id[members[0]], by_id[members[-1]]
        result.append(dict(id=block_id, entry=members[0], address=hex(addresses[members[0]]),
                           context=first.get('context'), instruction_ids=members,
                           instruction_count=len(members), terminal_flow=last.get('flow', 'next'),
                           candidate_entry_instructions=[identity for identity in members if identity in entry_ids]))

    for node in nodes:
        if node['id'] in leaders and node['id'] not in assigned:
            consume(node['id'])
    for node in nodes:
        if node['id'] not in assigned:
            consume(node['id'])
    return result, assigned


def function_membership(nodes, edges, entries, max_work=1_000_000):
    """Return bounded candidate membership, overlaps and shared-tail evidence.

    Nodes have ``id,address,context,size,flow``; edges have ``source,target,kind``.
    Entries are exact node IDs, numeric addresses, or ``{id?,address?,context?,
    name?,source?}`` objects. A physical address with several contexts is an
    unresolved request, never a silent choice. Supplied fallthrough edges are
    required; this module neither decodes nor invents missing fallthroughs.

    ``work`` counts visited (entry,instruction) pairs. A stopped budget returns
    an explicit frontier. A shared tail is a candidate shared reachable block,
    not a proof of ownership or a recovered source-language function boundary.
    """
    nodes = _records(nodes, 'nodes', _MAX_NODES)
    edges = _records(edges, 'edges', _MAX_EDGES)
    if not isinstance(entries, (list, tuple)) or len(entries) > _MAX_ENTRIES:
        raise ValueError(f'entries must be a list of at most {_MAX_ENTRIES} entries')
    if isinstance(max_work, bool) or not isinstance(max_work, int) or not 1 <= max_work <= 20_000_000:
        raise ValueError('max_work must be an integer in 1..20000000')
    by_id, addresses, order, by_address = {}, {}, {}, defaultdict(list)
    for index, node in enumerate(nodes):
        identity = node.get('id')
        if not isinstance(identity, str) or not identity or identity in by_id:
            raise ValueError('instruction IDs must be unique nonempty strings')
        size = node.get('size')
        if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= 1_000_000:
            raise ValueError('instruction sizes must be positive integers')
        address = _number(node.get('address'))
        if address + size > 1 << 64:
            raise ValueError('instruction extent exceeds unsigned 64-bit address space')
        by_id[identity], addresses[identity], order[identity] = node, address, index
        by_address[address].append(identity)
    outgoing, incoming = defaultdict(list), defaultdict(list)
    unresolved, excluded_calls, excluded_other = [], [], 0
    seen_edges = set()
    for index, edge in enumerate(edges):
        source, target, kind = edge.get('source'), edge.get('target'), edge.get('kind', '')
        if not isinstance(source, str) or not isinstance(target, str):
            raise ValueError('edge source and target must be instruction ID strings')
        if kind in _CALL_KINDS or edge.get('intraprocedural') is False:
            excluded_calls.append(dict(edge))
            continue
        if kind not in _FLOW_KINDS:
            excluded_other += 1
            continue
        if source not in by_id:
            unresolved.append(dict(kind='edge', reason='source_not_stored', source=source, target=target, edge_index=index))
            continue
        key = (source, target, kind)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        outgoing[source].append(edge)
        if target in by_id:
            incoming[target].append(edge)

    selected, selected_meta = [], {}
    for index, requested in enumerate(entries):
        item = requested if isinstance(requested, dict) else {'id': requested} if isinstance(requested, str) and requested in by_id else {'address': requested}
        identity = item.get('id', item.get('instruction', item.get('entry')))
        if not isinstance(identity, str) or identity not in by_id:
            try:
                address = _number(item.get('address'))
            except (ValueError, TypeError):
                unresolved.append(dict(kind='entry', reason='entry_not_stored', request_index=index, requested=requested))
                continue
            matches = by_address[address]
            if item.get('context') is not None:
                matches = [candidate for candidate in matches if by_id[candidate].get('context') == item['context']]
            if len(matches) != 1:
                unresolved.append(dict(kind='entry', reason='ambiguous_entry_context' if len(matches) > 1 else 'entry_not_stored',
                                       request_index=index, address=hex(address), context=item.get('context'), candidates=list(matches)))
                continue
            identity = matches[0]
        elif item.get('context') is not None and item['context'] != by_id[identity].get('context'):
            unresolved.append(dict(kind='entry', reason='entry_context_mismatch', request_index=index, entry=identity, context=item['context']))
            continue
        if identity not in selected_meta:
            selected.append(identity)
            selected_meta[identity] = dict(item)
    entry_order = {identity: index for index, identity in enumerate(selected)}
    entry_set = set(selected)

    def ordered_entries(values):
        return sorted(values, key=entry_order.get)

    memberships, reached = defaultdict(set), defaultdict(set)
    scheduled = {(entry, entry) for entry in selected}
    queue = deque((entry, entry) for entry in selected)
    frontier, frontier_seen, frontier_count, incomplete = [], set(), 0, set()
    work, expansion_limited = 0, False

    def add_frontier(entry, source, target, reason):
        nonlocal frontier_count
        incomplete.add(entry)
        key = (entry, source, target, reason)
        if key in frontier_seen:
            return
        # Beyond the bounded unique examples, count frontier events rather
        # than retaining an unbounded set of missing target pairs.
        frontier_count += 1
        if len(frontier) < _MAX_FRONTIER:
            frontier_seen.add(key)
            frontier.append(dict(entry=entry, source=source, target=target, reason=reason))

    while queue and work < max_work:
        entry, current = queue.popleft()
        memberships[current].add(entry)
        reached[entry].add(current)
        work += 1
        if by_id[current].get('flow') in _TERMINALS:
            continue
        for edge in outgoing[current]:
            target = edge['target']
            if target not in by_id:
                add_frontier(entry, current, target, 'no_stored_instruction_at_target')
                continue
            pair = (entry, target)
            if pair not in scheduled:
                if len(scheduled) >= max_work + len(selected) + _MAX_FRONTIER:
                    expansion_limited = True
                    add_frontier(entry, current, None, 'work_budget_expansion_limit')
                    break
                scheduled.add(pair)
                queue.append(pair)
    budget_exhausted = bool(queue) or expansion_limited
    for entry, target in queue:
        add_frontier(entry, None, target, 'work_budget')
    for node in nodes:
        identity, flow = node['id'], node.get('flow', 'next')
        if not memberships[identity] or flow in _TERMINALS:
            continue
        kinds = {edge.get('kind', '') for edge in outgoing[identity]}
        if flow in ('jump', 'indirect_jump', 'conditional') and not kinds.intersection({'branch', 'resolved_branch', 'jump', 'conditional', 'taken', ''}):
            unresolved.append(dict(kind='branch', reason='no_stored_branch_target', instruction=identity,
                                   candidate_entries=ordered_entries(memberships[identity])))
        if flow in ('next', 'call', 'indirect_call', 'conditional') and not kinds.intersection({'fallthrough', 'next', 'not_taken', ''}):
            unresolved.append(dict(kind='fallthrough', reason='no_stored_fallthrough', instruction=identity,
                                   candidate_entries=ordered_entries(memberships[identity])))

    blocks, block_for = _blocks(nodes, outgoing, incoming, entry_set, addresses)
    block_order = {block['id']: index for index, block in enumerate(blocks)}
    unresolved_entries = {entry for item in unresolved for entry in item.get('candidate_entries', [])}
    functions = []
    for entry in selected:
        ids = sorted(reached[entry], key=order.get)
        metadata = selected_meta[entry]
        overlaps = ordered_entries((entry_set & reached[entry]) - {entry})
        function_unresolved = entry in unresolved_entries
        functions.append(dict(id=entry, entry=entry, address=hex(addresses[entry]), context=by_id[entry].get('context'),
                              name=metadata.get('name', by_id[entry].get('name')), source=metadata.get('source'),
                              instruction_ids=ids, instruction_count=len(ids),
                              block_ids=sorted({block_for[identity] for identity in ids}, key=block_order.get),
                              runs=_runs(ids, by_id, addresses, order), overlapping_entries=overlaps,
                              traversal_exhausted=entry not in incomplete,
                              complete=entry not in incomplete and not function_unresolved))
    instruction_membership = [dict(id=node['id'], instruction=node['id'], address=hex(addresses[node['id']]),
                                   context=node.get('context'), candidate_entries=ordered_entries(memberships[node['id']])) for node in nodes]
    block_membership, shared_tails = [], []
    for block in blocks:
        candidates = ordered_entries(set().union(*(memberships[identity] for identity in block['instruction_ids'])))
        per_instruction = [memberships[identity] for identity in block['instruction_ids']]
        record = dict(id=block['id'], block=block['id'], candidate_entries=candidates, shared=len(candidates) > 1,
                      partial_membership=any(member != per_instruction[0] for member in per_instruction[1:]))
        block_membership.append(record)
        shared_ids = [identity for identity in block['instruction_ids'] if len(memberships[identity]) > 1]
        if shared_ids:
            shared_candidates = ordered_entries(set().union(*(memberships[identity] for identity in shared_ids)))
            shared_tails.append(dict(block=block['id'], instruction_ids=shared_ids, candidate_entries=shared_candidates,
                                     partial_membership=record['partial_membership'],
                                     instruction_membership=[dict(instruction=identity, candidate_entries=ordered_entries(memberships[identity]))
                                                             for identity in shared_ids],
                                     status='candidate', evidence='recorded intraprocedural reachability from multiple candidate entries; partial budgets can cover only part of a block'))
    overlaps = [dict(entry=entry, reachable_from=ordered_entries(memberships[entry] - {entry}),
                     block=block_for[entry]) for entry in selected if any(other != entry for other in memberships[entry])]
    tail_calls = []
    for source in by_id:
        if by_id[source].get('flow') not in ('jump', 'indirect_jump'):
            continue
        for edge in outgoing[source]:
            target = edge['target']
            if target in selected_meta and source != target:
                owners = ordered_entries(memberships[source] - {target})
                if owners:
                    tail_calls.append(dict(source=source, target=target, source_entries=owners, target_entry=target,
                                           evidence=edge.get('evidence', 'unconditional transfer to another candidate entry'),
                                           status='candidate', ownership_traversal_continues=True))
    return dict(status='candidate', function_boundary_proven=False,
                functions=functions, instruction_membership=instruction_membership, basic_blocks=blocks,
                block_membership=block_membership, shared_tails=shared_tails,
                tail_call_candidates=tail_calls, overlapping_entries=overlaps,
                unresolved=unresolved, frontier=frontier, frontier_count=frontier_count,
                frontier_count_kind='frontier events; examples deduplicated while retained',
                frontier_truncated=frontier_count > len(frontier), work=work, max_work=max_work,
                budget_exhausted=budget_exhausted, traversal_exhausted=not budget_exhausted,
                complete=not budget_exhausted and not frontier_count and not unresolved,
                requested_entry_count=len(entries), resolved_entry_count=len(selected),
                excluded_call_edges=excluded_calls, excluded_non_flow_edge_count=excluded_other,
                assumptions=['Only supplied intraprocedural edges are followed; call targets are excluded.',
                             'Entries and labels do not stop traversal. Membership can overlap.',
                             'Shared tails and tail calls are candidates, not proven function boundaries.'])
