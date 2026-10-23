"""Read-only project adapter for bounded native function-membership facts."""
from __future__ import annotations

from .cfg import _following, _id, _segmented
from .function_analysis import function_membership as _membership


_MAX_EDGES = 500000
_MAX_ENTRIES = 10000
_CONTROL = "('branch','resolved_branch','call','resolved_call','fallthrough')"
_SELECTED = "WITH selected AS (SELECT context,address FROM instructions WHERE version=? AND context NOT LIKE 'cil:%' ORDER BY context,address LIMIT ?) "


class MembershipMixin:
    def function_membership(self, version=None, max_work=1000000, max_instructions=100000):
        """Describe overlapping candidates over stored native instruction facts.

        This query never decodes bytes or changes analysis queues. Call targets
        remain external to each candidate's intraprocedural membership. Missing
        ordinary fallthroughs are reconstructed from stored sizes and flows.
        Instruction, entry and edge truncation always prevents completeness.
        """
        from .project import integer

        max_instructions = integer(max_instructions, 'max_instructions', 1, 100000)
        max_work = integer(max_work, 'max_work', 1, 20000000)
        with self.transaction():
            v = self.version(version)['id']
            dos = self.meta['format'] == 'MZ'
            total = self.db.execute("SELECT COUNT(*) FROM instructions WHERE version=? AND context NOT LIKE 'cil:%'", (v,)).fetchone()[0]
            rows = list(self.db.execute("SELECT * FROM instructions WHERE version=? AND context NOT LIKE 'cil:%' ORDER BY context,address LIMIT ?", (v, max_instructions)))
            nodes = []
            for row in rows:
                address = int(row['address'], 16)
                nodes.append(dict(id=_id(row['context'], address), address=hex(address), context=row['context'],
                                  segmented_address=_segmented(address, row['context']), size=row['size'],
                                  bytes=row['bytes'], mnemonic=row['mnemonic'], operands=row['operands'],
                                  flow=row['flow'], next_address=_following(row, address)))
            entry_total = self.db.execute("SELECT COUNT(*) FROM functions f JOIN instructions i ON i.version=f.version AND i.context=f.context AND i.address=f.address WHERE f.version=? AND i.context NOT LIKE 'cil:%'", (v,)).fetchone()[0]
            entry_rows = list(self.db.execute(_SELECTED + "SELECT f.* FROM functions f JOIN selected s ON s.context=f.context AND s.address=f.address WHERE f.version=? ORDER BY f.context,f.address LIMIT ?",
                                              (v, max_instructions, v, _MAX_ENTRIES + 1)))
            entries = []
            for row in entry_rows[:_MAX_ENTRIES]:
                address = int(row['address'], 16)
                if dos:
                    name = self._dos_label(v, address, row['context'])
                else:
                    annotation = self.db.execute("SELECT text FROM annotations WHERE version=? AND context=? AND address=? AND kind='name'", (v, row['context'], row['address'])).fetchone()
                    name = annotation[0] if annotation else row['name']
                entries.append(dict(id=_id(row['context'], address), address=hex(address), context=row['context'],
                                    name=name, source=row['source']))
            table, source_context, target_context = ('dos_edges', 'source_context', 'target_context') if dos else ('xrefs', 'context', 'context')
            join = f'FROM {table} e JOIN selected s ON s.context=e.{source_context} AND s.address=e.source WHERE e.version=?'
            parameters = (v, max_instructions, v)
            stored_edge_total = self.db.execute(_SELECTED + f'SELECT COUNT(*) {join} AND e.kind IN {_CONTROL}', parameters).fetchone()[0]
            edge_rows = self.db.execute(_SELECTED + f'SELECT e.* {join} AND e.kind IN {_CONTROL} ORDER BY e.{source_context},e.source,e.target,e.{target_context},e.kind LIMIT ?',
                                        parameters + (_MAX_EDGES,))
            by_id = {node['id']: node for node in nodes}
            edges = []
            for row in edge_rows:
                source_address, target_address = int(row['source'], 16), int(row['target'], 16)
                context, target_cs = row[source_context], row[target_context] or None
                source, target = _id(context, source_address), _id(target_cs, target_address)
                edges.append(dict(id=f'e{len(edges)}', source=source, target=target, kind=row['kind'], evidence=row['evidence'],
                                  source_address=hex(source_address), source_context=context,
                                  target_address=hex(target_address), target_context=target_cs,
                                  provenance='stored', assumed_return=row['kind'] == 'fallthrough' and by_id[source]['flow'] in ('call', 'indirect_call')))
            # Query existence independently from the output edge cap, so an
            # omitted stored edge is never replaced with invented provenance.
            stored_fallthrough = {(row[0], row[1]) for row in self.db.execute(_SELECTED + f'SELECT DISTINCT e.{source_context},e.source {join} AND e.kind=\'fallthrough\'', parameters)}
            reconstructed_total, omitted_reconstructed = 0, 0
            for row, node in zip(rows, nodes):
                if row['flow'] not in ('next', 'call', 'indirect_call', 'conditional') or (row['context'], row['address']) in stored_fallthrough:
                    continue
                following = node['next_address']
                if not 0 <= following < (0x100000 if dos else 1 << 64):
                    continue
                reconstructed_total += 1
                if len(edges) >= _MAX_EDGES:
                    omitted_reconstructed += 1
                    continue
                edges.append(dict(id=f'e{len(edges)}', source=node['id'], target=_id(node['context'], following),
                                  source_address=node['address'], source_context=node['context'],
                                  target_address=hex(following), target_context=node['context'], kind='fallthrough',
                                  evidence='reconstructed from stored instruction size and permitted flow' + ('; assumes call returns' if row['flow'] in ('call', 'indirect_call') else ''),
                                  provenance='reconstructed', assumed_return=row['flow'] in ('call', 'indirect_call')))
            result = _membership(nodes, edges, entries, max_work=max_work)
            instruction_omissions = total - len(nodes)
            entry_omissions = entry_total - len(entries)
            edge_omissions = max(0, stored_edge_total - _MAX_EDGES) + omitted_reconstructed
            truncation = dict(instructions=instruction_omissions, candidate_entries=entry_omissions, edges=edge_omissions)
            truncated = any(truncation.values())
            if truncated:
                for kind, omitted in truncation.items():
                    if omitted:
                        result['frontier'].append(dict(entry=None, source=None, target=None, reason=f'input_{kind}_limit', omitted_count=omitted))
                        result['frontier_count'] += 1
                result['complete'] = False
                result['traversal_exhausted'] = False
                for function in result['functions']:
                    function['complete'] = False
                    function['input_truncated'] = True
            result.update(version=v, arch=self.arch, bits=self.bits, scope='candidate membership over stored native CFG facts',
                          input_truncated=truncated, truncation=truncation,
                          instruction_count=len(nodes), stored_instruction_count=total, max_instructions=max_instructions,
                          candidate_entry_count=len(entries), stored_candidate_entry_count=entry_total, candidate_entry_limit=_MAX_ENTRIES,
                          edge_count=len(edges), stored_edge_count=stored_edge_total, reconstructed_fallthrough_count=reconstructed_total,
                          edge_limit=_MAX_EDGES, analysis=self.analysis_status(v),
                          complete_scope='All supplied stored native facts and candidate entries were covered; not all binary code or runtime behavior.',
                          note='Many-to-many candidate membership; labels do not prove boundaries. Calls are excluded and continuations assume return. Missing facts, unknown transfers, input caps and work budgets remain explicit.')
            return result
