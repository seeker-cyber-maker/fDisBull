"""Persist derived flow/access facts without changing bytes or discovery queues."""
import hashlib
import json

FACTS_DDL = """
CREATE TABLE IF NOT EXISTS memory_refs(version INTEGER NOT NULL, context TEXT NOT NULL,
    source TEXT NOT NULL, fact_key TEXT NOT NULL, detail TEXT NOT NULL,
    PRIMARY KEY(version,context,source,fact_key));
CREATE TABLE IF NOT EXISTS analysis_facts_revision(version INTEGER PRIMARY KEY, revision INTEGER NOT NULL);
"""


class FactsMixin:
    def _memory_facts(self, version, context, address, raw, cs=None, registers=None):
        from .memory import instruction_memory_accesses
        source = f'{address:016x}'
        for fact in instruction_memory_accesses(raw,address,self.arch,self.bits,cs=cs,registers=registers):
            detail = json.dumps(fact,sort_keys=True,separators=(',',':'))
            fact_key = hashlib.sha256(detail.encode()).hexdigest()
            self.db.execute('INSERT OR IGNORE INTO memory_refs VALUES (?,?,?,?,?)',
                            (version,context,source,fact_key,detail))

    def _clear_memory_facts(self, version, context, address):
        self.db.execute('DELETE FROM memory_refs WHERE version=? AND context=? AND source=?',
                        (version,context,f'{address:016x}'))

    def _fresh_facts(self, version):
        from .memory import MEMORY_FACTS_REVISION
        self.db.execute('INSERT OR REPLACE INTO analysis_facts_revision VALUES (?,?)',
                        (version,MEMORY_FACTS_REVISION))

    def refresh_facts(self, version=None):
        """Backfill all stored instructions; never discover code or infer labels.

        Old projects acquire missing fallthrough edges and access facts explicitly.
        A successful refresh is atomic and repeatable. Unknown register states stay
        unknown; this index describes the stored static assumptions, not runtime.
        """
        from .project import key
        dos = self.meta['format'] == 'MZ'
        with self.transaction(True):
            v = self.version(version)['id']
            rows = self.db.execute('SELECT * FROM instructions WHERE version=? ORDER BY context,address',(v,)).fetchall()
            regions = self.regions(v)
            self.db.execute('DELETE FROM memory_refs WHERE version=?',(v,))
            self.db.execute('DELETE FROM analysis_facts_revision WHERE version=?',(v,))
            edge_count = 0
            for row in rows:
                address = int(row['address'],16)
                cs = int(row['context'].rsplit('=',1)[1],16) if dos and ':cs=' in row['context'] else None
                state_row = self.db.execute('SELECT registers FROM dos_states WHERE version=? AND context=? AND address=?',
                                            (v,row['context'],row['address'])).fetchone() if dos else None
                states = self._dos_variants(json.loads(state_row[0])) if state_row else [{}]
                raw = bytes.fromhex(row['bytes'])
                for state in states:
                    self._memory_facts(v,row['context'],address,raw,cs,state)
                if row['flow'] not in ('next','conditional','call','indirect_call'):
                    continue
                following = cs*16+((address-cs*16+row['size'])&65535) if cs is not None else address+row['size']
                # Preserve real decoded continuations, including holes the graph
                # must report; do not invent destinations outside mapped memory.
                if not any(r.start<=following<r.start+len(r.data) for r in regions):
                    continue
                evidence = ('permitted call-return fallthrough; return is assumed' if row['flow'] in ('call','indirect_call')
                            else 'decoded conditional fallthrough' if row['flow']=='conditional'
                            else 'decoded straight-line fallthrough')
                before = self.db.total_changes
                if cs is not None:
                    self._dos_edge(v,row['context'],address,following,cs,'fallthrough',evidence)
                else:
                    self.db.execute('INSERT OR IGNORE INTO xrefs VALUES (?,?,?,?,?,?)',
                                    (v,row['context'],key(address),key(following),'fallthrough',evidence))
                edge_count += int(self.db.total_changes>before)
            self._fresh_facts(v)
            count = self.db.execute('SELECT count(*) FROM memory_refs WHERE version=?',(v,)).fetchone()[0]
            return dict(version=v,instructions_indexed=len(rows),memory_access_facts=count,
                        fallthrough_sources_added=edge_count,analysis=self.analysis_status(v),
                        assumptions=['Stored instruction bytes and static register-state alternatives only.',
                                     'Calls may return; graph reachability does not prove a runtime path is feasible.',
                                     'Unresolved indirect and bulk writes remain candidates, not absence of writers.'])
