"""Read-only, context-sensitive control flow over stored instruction facts.

This is a reachable candidate routine slice, not proof of function ownership.
Calls are recorded but not entered; their continuation assumes the call returns.
"""
from __future__ import annotations

from collections import defaultdict, deque


def _key(address):
    return f'{address:016x}'


def _hex(address):
    return f'0x{address:x}'


def _id(context, address):
    return f'{context}@{_hex(address)}'


def _selector(context):
    return int(context.rsplit('=', 1)[1], 16) if context and ':cs=' in context else None


def _segmented(address, context):
    selector = _selector(context)
    offset = address - selector * 16 if selector is not None else None
    return f'{selector:04x}:{offset:04x}' if offset is not None and 0 <= offset <= 65535 else None


def _following(row, address):
    selector = _selector(row['context'])
    if selector is not None:
        return selector * 16 + ((address - selector * 16 + row['size']) & 65535)
    return address + row['size']


def _blocks(nodes, edges, entry):
    """Collapse straight lines without losing joins, loop edges or call sites."""
    by_id = {node['id']: node for node in nodes}
    outgoing, incoming = defaultdict(list), defaultdict(list)
    for edge in edges:
        if edge['target'] in by_id:
            outgoing[edge['source']].append(edge)
            incoming[edge['target']].append(edge)
    assigned, blocks = {}, []
    leaders = {entry}
    for node in nodes:
        if len(incoming[node['id']]) != 1:
            leaders.add(node['id'])
        if node['flow'] != 'next' or len(outgoing[node['id']]) != 1:
            leaders.update(edge['target'] for edge in outgoing[node['id']])

    def consume(start):
        block_id = f'b{len(blocks)}'
        members, current = [], start
        while current not in assigned:
            assigned[current] = block_id
            node = by_id[current]
            members.append(node)
            following = outgoing[current]
            if node['flow'] != 'next' or len(following) != 1:
                break
            target = following[0]['target']
            if target in leaders or target in assigned:
                break
            next_node = by_id[target]
            if next_node['context'] != node['context'] or int(next_node['address'], 16) != node['next_address']:
                break
            current = target
        blocks.append(dict(id=block_id, entry=members[0]['id'], address=members[0]['address'],
                           segmented_address=members[0]['segmented_address'], context=members[0]['context'],
                           name=members[0]['name'], instruction_count=len(members),
                           instruction_ids=[node['id'] for node in members],
                           highlights=sorted({label for node in members for label in node['highlights']}),
                           terminal_flow=members[-1]['flow']))

    if entry in by_id:
        consume(entry)
    # Start joins before their predecessors' remaining chains; no block can
    # accidentally absorb an entry point in the middle of a straight line.
    for node in nodes:
        if node['id'] in leaders and node['id'] not in assigned:
            consume(node['id'])
    for node in nodes:
        if node['id'] not in assigned:
            consume(node['id'])
    block_edges = []
    for edge in edges:
        source, target = assigned[edge['source']], assigned.get(edge['target'])
        if source != target or by_id[edge['source']]['flow'] != 'next':
            block_edges.append(dict(edge, source_block=source, target_block=target))
    return blocks, block_edges


class CFGMixin:
    def cfg(self, address, version=None, cs=None, max_instructions=10000, highlights=None):
        """Follow stored intraprocedural edges from an exact instruction start.

        Highlights are addresses or {address, cs?, label?} objects. A physical
        address matches all reachable CS interpretations; CS:IP selects one.
        Missing ordinary fallthroughs are reconstructed from stored size/flow
        with explicit provenance. This query never decodes or queues bytes.
        """
        from .project import integer, number
        budget = integer(max_instructions, 'max_instructions', 1, 1_000_000)
        if highlights is None:
            highlights = []
        if not isinstance(highlights, (list, tuple)) or len(highlights) > 100:
            raise ValueError('highlights must be a list of at most 100 addresses or address objects')
        dos = self.meta['format'] == 'MZ'

        def parse(value, selector=None):
            if dos:
                a, segment = self._dos_parse_address(value, selector)
                return a, f'x86:16:little:cs={segment:04x}' if segment is not None else None
            if selector is not None:
                raise ValueError('CS selection applies only to DOS MZ projects')
            return number(value), self.context

        start, context = parse(address, cs)
        requested = []
        for index, item in enumerate(highlights):
            if isinstance(item, dict):
                if 'address' not in item:
                    raise ValueError('highlight objects require an address')
                a, c = parse(item['address'], item.get('cs'))
                label = item.get('label', str(item['address']))
                if not isinstance(label, str) or not label or len(label) > 256:
                    raise ValueError('highlight label must contain 1..256 characters')
            else:
                a, c = parse(item)
                label = str(item)
            requested.append(dict(index=index, label=label, address=_hex(a), context=c, _address=a))

        with self.transaction():
            v = self.version(version)['id']
            if dos and context is None:
                alternatives = [row[0] for row in self.db.execute('SELECT context FROM instructions WHERE version=? AND address=? ORDER BY context', (v, _key(start)))]
                if len(alternatives) > 1:
                    raise ValueError('CFG entry has multiple stored CS interpretations; supply cs or CS:IP')
                context = alternatives[0] if alternatives else None
            entry = _id(context, start)
            nodes, edges, calls, gaps, unresolved = [], [], [], [], []
            by_id, parents, scheduled = {}, {}, {(context, start)}
            queue = deque([(context, start)])
            presentations = {}

            def presentation(a, c=None):
                identity = (a, c if dos else None)
                if identity not in presentations:
                    presentations[identity] = self._dos_presentation(v, a, c) if dos else self._presentation(v, a)
                return presentations[identity]

            def destination(a, c):
                return dict(target=_id(c, a), target_address=_hex(a), target_context=c,
                            target_segmented_address=_segmented(a, c), target_name=presentation(a, c)['name'])

            def add_edge(row, a, target, target_context, kind, evidence, provenance):
                source_id = _id(row['context'], a)
                edge = dict(id=f'e{len(edges)}', source=source_id, source_address=_hex(a), source_context=row['context'],
                            source_segmented_address=_segmented(a, row['context']), **destination(target, target_context),
                            kind=kind, evidence=evidence, provenance=provenance,
                            assumed_return=row['flow'] in ('call', 'indirect_call'), predicate=None)
                if row['flow'] == 'conditional':
                    edge['predicate'] = dict(mnemonic=row['mnemonic'], operands=row['operands'],
                                             outcome='not_taken' if kind == 'fallthrough' else 'taken', truth_evaluated=False)
                edges.append(edge)
                identity = (target_context, target)
                if identity not in scheduled:
                    scheduled.add(identity)
                    parents[edge['target']] = edge
                    queue.append(identity)

            while queue and len(nodes) < budget:
                current_context, a = queue.popleft()
                row = self.db.execute('SELECT * FROM instructions WHERE version=? AND context=? AND address=?', (v, current_context, _key(a))).fetchone()
                if row is None:
                    gaps.append(dict(id=_id(current_context, a), address=_hex(a), context=current_context,
                                     segmented_address=_segmented(a, current_context), reason='no_stored_instruction_at_target'))
                    continue
                node_id = _id(current_context, a)
                references = [dict(operand_index=ref['operand_index'], role=ref['role'], target=_hex(int(ref['target'], 16)),
                                   width=ref['width'], **presentation(int(ref['target'], 16)))
                              for ref in self.db.execute('SELECT * FROM operand_refs WHERE version=? AND context=? AND source=? ORDER BY operand_index,role,target', (v, current_context, _key(a)))]
                display = row['operands'] + (' ; ' + ', '.join(ref['name'] for ref in references) if references else '')
                shown = presentation(a, current_context)
                node = dict(id=node_id, address=_hex(a), context=current_context, segmented_address=_segmented(a, current_context),
                            size=row['size'], bytes=row['bytes'], mnemonic=row['mnemonic'], operands=row['operands'],
                            raw_operands=row['operands'], display_operands=display, flow=row['flow'], references=references,
                            next_address=_following(row, a), name=shown['name'], representation=shown['representation'],
                            presentation=shown, highlights=[])
                nodes.append(node)
                by_id[node_id] = node
                if dos:
                    stored = [dict(item, context=item['target_context'] or None) for item in self.db.execute(
                        "SELECT * FROM dos_edges WHERE version=? AND source_context=? AND source=? AND kind IN ('branch','resolved_branch','call','resolved_call','fallthrough') ORDER BY target,target_context,kind", (v, current_context, _key(a)))]
                else:
                    stored = [dict(item) for item in self.db.execute(
                        "SELECT * FROM xrefs WHERE version=? AND context=? AND source=? AND kind IN ('branch','resolved_branch','call','resolved_call','fallthrough') ORDER BY target,kind", (v, current_context, _key(a)))]
                flow = row['flow']
                if flow in ('call', 'indirect_call'):
                    callee_edges = [edge for edge in stored if edge['kind'] in ('call', 'resolved_call')]
                    for callee in callee_edges or [None]:
                        calls.append(dict(source=node_id, address=_hex(a), context=current_context,
                                          segmented_address=_segmented(a, current_context), mnemonic=row['mnemonic'],
                                          raw_operands=row['operands'], resolved=callee is not None,
                                          kind=callee['kind'] if callee else 'unresolved_call',
                                          evidence=callee['evidence'] if callee else 'no stored call target',
                                          **destination(int(callee['target'], 16), callee['context']) if callee else dict(target=None, target_address=None, target_context=None, target_segmented_address=None, target_name=None)))
                    if not callee_edges:
                        unresolved.append(dict(source=node_id, address=_hex(a), context=current_context, kind='call', reason='no_stored_call_target'))
                branch_edges = [edge for edge in stored if edge['kind'] in ('branch', 'resolved_branch')] if flow in ('jump', 'indirect_jump', 'conditional') else []
                for branch in branch_edges:
                    add_edge(row, a, int(branch['target'], 16), branch['context'], branch['kind'], branch['evidence'], 'stored')
                if flow in ('jump', 'indirect_jump', 'conditional') and not branch_edges:
                    unresolved.append(dict(source=node_id, address=_hex(a), context=current_context, kind='branch', reason='no_stored_branch_target'))
                if flow in ('next', 'call', 'indirect_call', 'conditional'):
                    fallthroughs = [edge for edge in stored if edge['kind'] == 'fallthrough']
                    if fallthroughs:
                        for following in fallthroughs:
                            add_edge(row, a, int(following['target'], 16), following['context'], 'fallthrough', following['evidence'], 'stored')
                    else:
                        following = _following(row, a)
                        if following < (0x100000 if dos else 1 << 64):
                            add_edge(row, a, following, current_context, 'fallthrough',
                                     'reconstructed from stored instruction size and permitted flow' + ('; assumes call returns' if flow in ('call', 'indirect_call') else ''), 'reconstructed')
                        else:
                            gaps.append(dict(id=node_id, address=_hex(a), context=current_context, reason='fallthrough_outside_supported_address_space'))

            frontier = [dict(id=_id(c, a), address=_hex(a), context=c, segmented_address=_segmented(a, c)) for c, a in queue]
            for edge in edges:
                edge['target_stored_in_graph'] = edge['target'] in by_id
            for item in requested:
                matches = [node for node in nodes if (item['context'] is None or item['context'] == node['context']) and
                           int(node['address'], 16) <= item['_address'] < int(node['address'], 16) + node['size']]
                item.update(reachable=bool(matches), status='reachable' if matches else 'not_reached', matches=[])
                for node in matches:
                    node['highlights'].append(item['label'])
                    path_edges, current = [], node['id']
                    while current != entry and current in parents:
                        edge = parents[current]
                        path_edges.append(edge)
                        current = edge['source']
                    path_edges.reverse()
                    path_ids = [entry] + [edge['target'] for edge in path_edges]
                    item['matches'].append(dict(instruction=node['id'], instruction_address=node['address'],
                                                context=node['context'], byte_offset=item['_address'] - int(node['address'], 16),
                                                path=[dict(id=identity, address=by_id[identity]['address'], context=by_id[identity]['context'],
                                                           segmented_address=by_id[identity]['segmented_address']) for identity in path_ids],
                                                path_edges=path_edges, path_kind='one shortest stored-graph path',
                                                assumed_call_returns=sum(edge['assumed_return'] for edge in path_edges)))
                del item['_address']
            blocks, block_edges = _blocks(nodes, edges, entry)
            exits = [dict(id=node['id'], address=node['address'], context=node['context'], segmented_address=node['segmented_address'], flow=node['flow'])
                     for node in nodes if node['flow'] in ('return', 'stop')]
            return dict(version=v, entry=entry, address=_hex(start), context=context, segmented_address=_segmented(start, context),
                        status='candidate', function_boundary_proven=False, scope='intraprocedural stored-graph reachability',
                        nodes=nodes, edges=edges, basic_blocks=blocks, block_edges=block_edges, calls=calls, exits=exits,
                        highlights=requested, gaps=gaps, unresolved=unresolved, frontier=frontier,
                        instruction_count=len(nodes), block_count=len(blocks), edge_count=len(edges),
                        budget=budget, budget_exhausted=bool(queue), traversal_exhausted=not queue,
                        graph_closed=not queue and not gaps and not any(item['kind'] == 'branch' for item in unresolved),
                        analysis=self.analysis_status(v),
                        assumptions=['Calls are not entered; each call continuation assumes the call returns.',
                                     'Branch outcomes are not evaluated. Stored state alternatives can introduce infeasible paths.'],
                        note='Labels and candidate function entries never stop traversal. Returns/stop instructions do. Not-reached highlights are not proof of runtime unreachability; unknown transfers, missing facts or budget limits may hide paths.')
