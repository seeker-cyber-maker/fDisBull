"""Explicit repair of DOS facts made under an obsolete pointer-state policy.

Opening a project never discards its analysis. Unsafe legacy facts are blocked
until the caller explicitly rebuilds them from the retained image and roots.
"""
import hashlib
import json

from .dos_analysis import DOS_POINTER_REVISION


_REPAIR = 'run refresh-dos-state to rebuild DOS facts from retained bytes'


class DOSStateRefreshMixin:
    def _dos_pointer_revision(self, version):
        row = self.db.execute('SELECT value FROM metadata WHERE key=?',
                              (f'dos_pointer_revision_{version}',)).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0])
        except (ValueError, TypeError):
            return row[0]

    def _dos_pointer_facts_stale(self, version):
        if self.meta['format'] != 'MZ':
            return False
        revision = self._dos_pointer_revision(version)
        if type(revision) is int and revision == DOS_POINTER_REVISION:
            return False
        return self.db.execute('SELECT 1 FROM instructions WHERE version=? LIMIT 1',
                               (version,)).fetchone() is not None

    def _require_dos_pointer_facts_current(self, version=None):
        v = self.version(version)['id']
        if self._dos_pointer_facts_stale(v):
            raise ValueError('stored DOS pointer/register facts use an obsolete policy; ' + _REPAIR)
        return v

    def analysis_status(self, version=None):
        result = self._stored_analysis_status(version)
        if self.meta['format'] == 'MZ':
            stale = self._dos_pointer_facts_stale(result['version'])
            result.update(facts_stale=stale,
                          dos_pointer_revision=self._dos_pointer_revision(result['version']),
                          required_dos_pointer_revision=DOS_POINTER_REVISION)
            if stale:
                result.update(stable=False, overall_stable=False,
                              pending=result['pending'] + 1, pending_dos_state_refresh=1)
                result['note'] += ' Stored DOS pointer/register facts are obsolete; ' + _REPAIR + '.'
        return result

    def advanced_status(self, version=None):
        result = super().advanced_status(version)
        if self.meta['format'] == 'MZ':
            stale = self._dos_pointer_facts_stale(result['version'])
            result['facts_stale'] = stale
            if stale:
                result.update(stable=False, pending=result['pending']+1, pending_dos_state_refresh=1)
                result['note'] += ' Stored DOS pointer/register facts are obsolete; ' + _REPAIR + '.'
        return result

    def analyze(self, version=None, start=None, max_instructions=10000,
                cs=None, ds=None, es=None, ss=None):
        v = self._require_dos_pointer_facts_current(version)
        return super().analyze(v, start, max_instructions, cs, ds, es, ss)

    def cfg(self, address, version=None, cs=None, max_instructions=10000, highlights=None):
        v = self._require_dos_pointer_facts_current(version)
        return super().cfg(address, v, cs, max_instructions, highlights)

    def memory_accesses(self, address, size=1, version=None, access='all', limit=200,
                        offset=0, include_unresolved=True):
        v = self._require_dos_pointer_facts_current(version)
        return super().memory_accesses(address, size, v, access, limit, offset, include_unresolved)

    def function_analysis(self, address, version=None, cs=None):
        v = self._require_dos_pointer_facts_current(version)
        return super().function_analysis(address, v, cs)

    def calls(self, version=None, limit=200, offset=0, kind='all'):
        v = self._require_dos_pointer_facts_current(version)
        return super().calls(v, limit, offset, kind)

    def refresh_facts(self, version=None):
        v = self._require_dos_pointer_facts_current(version)
        return super().refresh_facts(v)

    def xrefs(self, address, direction='to', version=None, limit=200, cs=None):
        v = self._require_dos_pointer_facts_current(version)
        return self._stored_xrefs(address, direction, v, limit, cs)

    def call_effects(self, address=None, size=1, access='all', version=None,
                     include_unresolved=True, limit=200, offset=0):
        v = self._require_dos_pointer_facts_current(version)
        return super().call_effects(address, size, access, v, include_unresolved, limit, offset)

    def function_membership(self, version=None, max_work=1000000, max_instructions=100000):
        v = self._require_dos_pointer_facts_current(version)
        return super().function_membership(v, max_work, max_instructions)

    def represent(self, address, representation, size=None, author='agent', version=None,
                  max_instructions=10000, defer=False):
        v = self._require_dos_pointer_facts_current(version)
        return super().represent(address, representation, size, author, v, max_instructions, defer)

    def disassembly(self, address=None, lines=50, version=None, cs=None):
        result = self._stored_disassembly(address, lines, version, cs)
        if self.meta['format'] != 'MZ':
            return result
        stale = self._dos_pointer_facts_stale(result['version'])
        result['stored_facts_stale'] = stale
        if not stale:
            return result
        for row in result['instructions']:
            raw = row.get('raw_operands', row['operands'])
            display, references, summary = self._file_reference_display(
                result['version'], row['context'], int(row['address'], 16), raw)
            row.update(references=[], xrefs=[], assumptions=None, stored_facts_stale=True,
                       display_operands=display, file_references=references,
                       file_reference_summary=summary)
            if row['flow'] in ('indirect_call', 'indirect_jump', 'indirect_branch'):
                row['target'] = None
        result.setdefault('warnings', []).append(
            'Stored DOS pointer/register facts are obsolete. Native operand references, '
            'xref lists and register assumptions are hidden; ' + _REPAIR + '.')
        result['view'] = 'Raw stored DOS instructions with authored annotations; obsolete native facts are hidden.'
        return result

    def refresh_dos_state(self, version=None, max_instructions=10000):
        from .project import integer
        if self.meta['format'] != 'MZ':
            raise ValueError('refresh-dos-state requires a DOS MZ project')
        budget = integer(max_instructions, 'max_instructions', 1, 1000000)
        with self.transaction(True):
            v = self.version(version)['id']
            previous = self._dos_pointer_revision(v)
            roots = self.db.execute("SELECT context,address,name FROM functions WHERE version=? AND source='user seed' ORDER BY context,address",
                                    (v,)).fetchall()
            version_hash = self.version(v)['sha256']
            source = self.db.execute('SELECT source_bytes FROM binary_info WHERE version=?', (v,)).fetchone()
            source_hash = hashlib.sha256(bytes(source[0])).hexdigest() if source and source[0] is not None else None
            self._reset_analysis(v)
            restored = []
            for root in roots:
                context = root['context']
                if not context.startswith('x86:16:little:cs='):
                    continue
                selector = int(context.rsplit('=', 1)[1], 16)
                address = int(root['address'], 16)
                if not self._mapping(v, address) or not 0 <= address - selector * 16 <= 65535:
                    continue
                self._dos_function(v, selector, address, root['name'], 'user seed')
                self._dos_add_seed(v, selector, address, 'user seed',
                                   dict(kind='retained explicit analysis root', source='refresh-dos-state',
                                        previous_register_assumptions='discarded'))
                restored.append(dict(context=context, address=hex(address), name=root['name'],
                                     register_assumptions='discarded', scheduling='deferred after entry sweep'))
            analysis = self.analyze(v, max_instructions=budget)
            self._sync_advanced_jobs(v)
            status, advanced = self.analysis_status(v), self.advanced_status(v)
            return dict(version=v, previous_dos_pointer_revision=previous,
                        dos_pointer_revision=DOS_POINTER_REVISION, restored_user_roots=restored,
                        sha256=version_hash, source_sha256=source_hash,
                        analysis=analysis, status=status, advanced=advanced,
                        pending_native=status['pending'], pending_derived=advanced['pending'],
                        stable=bool(status['stable'] and advanced['stable']),
                        note='Native facts rebuilt under a bounded budget; derived analysis is reset and pending. '
                             'Bytes and authored interpretations are retained; previous register assumptions are discarded.')
