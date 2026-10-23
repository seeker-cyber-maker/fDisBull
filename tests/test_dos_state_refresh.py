"""Explicit, version-local repair of legacy DOS pointer-state assumptions."""
import hashlib
import json
import struct

import pytest

from fdisbull.project import Project
from test_advanced_formats import _elf64
from test_dos_loader import mz_file


def _project(tmp_path):
    module = bytearray(256)
    # MOV AX,DATA; MOV DS,AX; LES BX,[0]; MOV AX,[ES:BX+12h]; RET.
    module[:14] = bytes.fromhex('b804008ed8c41e0000268b4712c3')
    struct.pack_into('<HH', module, 0x40, 0x10, 8)
    module[0x70:0x74] = bytes.fromhex('a10000cb')  # Separate explicit root.
    struct.pack_into('<H', module, 0xA2, 20)
    struct.pack_into('<HH', module, 0xC0, 1, 2)
    binary = tmp_path / 'legacy.exe'
    binary.write_bytes(mz_file(module, relocations=[(1, 0), (0x42, 0)], ss=15, sp=16))
    project = Project.create(tmp_path / 'legacy.fdb', binary)
    project.define_type('NeutralRecord', dict(kind='struct', size=4, fields=[
        dict(name='field_00', offset=0, type='u16'), dict(name='field_02', offset=2, type='u16')]))
    project.apply_type('100c:0000', 'NeutralRecord', name='native_record')
    project.represent('100c:0004', 'word', defer=True)
    project.analyze(start='1007:0000', ds=0x1004, es=0x1008, ss=0x100F)
    project.annotate('1007:0000', 'retained_root', kind='name', author='analyst')
    project.annotate('1000:0009', 'retained explanation', author='analyst')
    resource = tmp_path / 'resource.dat'
    resource.write_bytes(struct.pack('<HH', 20, 35))
    project.attach_file(resource, author='analyst')
    project.apply_file_type('resource.dat', 'NeutralRecord', name='raw_records')
    project.file_reference('1000:0009', 'resource.dat', width=2,
                           evidence='Authored offset hypothesis; runtime buffer is unproven.', author='analyst')
    return project


def _legacy(project, version=1):
    """Retain the former wrong exact EA as an actual stored legacy fact."""
    context, source, target = 'x86:16:little:cs=1000', 0x10009, 0x100A2
    registers = dict(ds=0x1004, es=0x1008, bx=0x10, ss=0x100F)
    with project.transaction(True):
        project.db.execute('DELETE FROM metadata WHERE key=?', (f'dos_pointer_revision_{version}',))
        project.db.execute('UPDATE dos_states SET registers=? WHERE version=? AND context=? AND address=?',
                           (json.dumps(registers), version, context, f'{source:016x}'))
        project.db.execute('DELETE FROM memory_refs WHERE version=? AND context=? AND source=?',
                           (version, context, f'{source:016x}'))
        project._memory_facts(version, context, source, bytes.fromhex('268b4712'), 0x1000, registers)
        project.db.execute('INSERT OR IGNORE INTO operand_refs VALUES (?,?,?,?,?,?,?)',
                           (version, context, f'{source:016x}', 1, 'memory', f'{target:016x}', 2))
        project._dos_edge(version, context, source, target, None, 'data', 'legacy snapshot pointer assumption')


_GUARDED = [
    lambda p: p.analyze(),
    lambda p: p.cfg('1000:0000'),
    lambda p: p.memory_accesses('100a:0002'),
    lambda p: p.function_analysis('1000:0000'),
    lambda p: p.calls(),
    lambda p: p.refresh_facts(),
    lambda p: p.xrefs('1000:0009'),
    lambda p: p.call_effects(),
    lambda p: p.function_membership(),
    lambda p: p.represent('100c:0004', 'word', defer=True),
    lambda p: p.auto_analyze(),
]


@pytest.mark.parametrize('query', _GUARDED)
def test_legacy_dos_queries_require_explicit_refresh_without_mutation(tmp_path, query):
    with _project(tmp_path) as project:
        assert project.analysis_status()['facts_stale'] is False
        _legacy(project)
        before = project.db.total_changes
        status = project.analysis_status()
        assert status['facts_stale'] and not status['stable'] and not status['overall_stable']
        assert status['pending_dos_state_refresh'] == 1 and status['pending'] >= 1
        with pytest.raises(ValueError, match='run refresh-dos-state'):
            query(project)
        # Rolled-back auto-analysis may increment SQLite's cumulative counter;
        # actual content must remain obsolete and intact in every case.
        assert project.analysis_status()['facts_stale']
        assert project.db.execute("SELECT count(*) FROM operand_refs WHERE target='00000000000100a2'").fetchone()[0]
        if query is not _GUARDED[-1]:
            assert project.db.total_changes == before


def test_legacy_raw_disassembly_hides_bad_facts_but_keeps_authored_file_labels(tmp_path):
    with _project(tmp_path) as project:
        _legacy(project)
        # An obsolete inferred indirect target must not survive the raw view.
        with project.transaction(True):
            project.db.execute("INSERT INTO instructions VALUES (1,?,'0000000000010020',2,'ffe3','jmp','bx','indirect_jump','00000000000100a2')",
                               ('x86:16:little:cs=1000',))
        snapshot = project.disassembly('1000:0009', lines=1)
        row, = snapshot['instructions']
        assert snapshot['stored_facts_stale'] and snapshot['analysis']['facts_stale']
        assert row['stored_facts_stale'] and row['references'] == [] and row['xrefs'] == []
        assert row['assumptions'] is None and row['operands'] == row['raw_operands']
        assert row['display_operands'].startswith(row['raw_operands'])
        assert 'raw_records.field_00' in row['display_operands']
        assert row['file_references'][0]['active'] and any('refresh-dos-state' in w for w in snapshot['warnings'])
        assert project.disassembly('1000:0020', lines=1)['instructions'][0]['target'] is None


def test_refresh_is_bounded_preserves_interpretations_and_drops_old_user_seed_state(tmp_path):
    database = tmp_path / 'legacy.fdb'
    with _project(tmp_path) as project:
        _legacy(project)
        versions = project.versions()
        region = project.regions(1)[0].data
        source = bytes(project.db.execute('SELECT source_bytes FROM binary_info WHERE version=1').fetchone()[0])
        tables = ('annotations', 'definitions', 'type_definitions', 'type_bindings',
                  'external_files', 'file_type_bindings', 'file_references')
        authored = {t: [tuple(r) for r in project.db.execute(f'SELECT * FROM {t} WHERE version=1')] for t in tables}
        result = project.refresh_dos_state(max_instructions=1)
        assert result['previous_dos_pointer_revision'] is None and result['dos_pointer_revision'] == 2
        assert not result['stable'] and result['pending_native'] > 0
        assert result['analysis']['attempted'] == 1
        assert result['restored_user_roots'][0]['address'] == '0x10070'
        seed = project.db.execute("SELECT state,evidence FROM dos_seeds WHERE version=1 AND reason='user seed'").fetchone()
        assert seed['state'] == 'deferred' and 'discarded' in seed['evidence']
        assert not project.analysis_status()['facts_stale']
        assert project.analyze()['stable']
        row = project.disassembly('1000:0009', lines=1)['instructions'][0]
        assert 'es' not in row['assumptions']['registers'] and 'bx' not in row['assumptions']['registers']
        assert not any(ref['target'] == '0x100a2' for ref in row['references'])
        exact = project.memory_accesses('100a:0002', include_unresolved=False)['items']
        assert not any(item['source'] == '0x10009' for item in exact)
        manual = project.disassembly('1007:0000', lines=1)['instructions'][0]
        assert manual['name'] == 'retained_root' and manual['assumptions']['registers'] == {}
        assert project.versions() == versions and project.regions(1)[0].data == region
        assert bytes(project.db.execute('SELECT source_bytes FROM binary_info WHERE version=1').fetchone()[0]) == source
        assert result['sha256'] == versions[0]['sha256']
        assert result['source_sha256'] == hashlib.sha256(source).hexdigest()
        for table in tables:
            assert [tuple(r) for r in project.db.execute(f'SELECT * FROM {table} WHERE version=1')] == authored[table]
        assert project.advanced_status()['pending'] > 0
        assert 'raw_records.field_00' in row['display_operands']
    with Project(database) as project:
        assert not project.analysis_status()['facts_stale']
        assert project.disassembly('1007:0000', lines=1)['instructions'][0]['name'] == 'retained_root'
        assert project.file_bytes('resource.dat')['bytes'] == '14002300'


def test_refresh_is_version_local_and_rejects_invalid_budget_atomically(tmp_path):
    with _project(tmp_path) as project:
        child = project.patch('100d:0000', '01')['version']
        project.analyze(child)
        _legacy(project)
        assert not project.analysis_status(child)['facts_stale']
        assert project.cfg('1000:0000', child)['instruction_count'] > 0
        child_rows = [tuple(r) for r in project.db.execute('SELECT * FROM instructions WHERE version=?', (child,))]
        for budget in (0, True, 1000001):
            with pytest.raises(ValueError, match='max_instructions'):
                project.refresh_dos_state(1, budget)
            assert project.analysis_status(1)['facts_stale']
        project.refresh_dos_state(1)
        assert [tuple(r) for r in project.db.execute('SELECT * FROM instructions WHERE version=?', (child,))] == child_rows


def test_refresh_rolls_back_all_retractions_when_analysis_fails(tmp_path, monkeypatch):
    with _project(tmp_path) as project:
        _legacy(project)
        tables = ('metadata', 'instructions', 'functions', 'dos_states', 'dos_seeds',
                  'xrefs', 'operand_refs', 'memory_refs', 'binary_info')
        before = {t: [tuple(row) for row in project.db.execute(f'SELECT * FROM {t} ORDER BY rowid')] for t in tables}
        original_analyze = project.analyze

        def fail(*args, **kwargs):
            raise RuntimeError('injected analysis failure')

        monkeypatch.setattr(project, 'analyze', fail)
        with pytest.raises(RuntimeError, match='injected analysis failure'):
            project.refresh_dos_state()
        for table in tables:
            assert [tuple(row) for row in project.db.execute(f'SELECT * FROM {table} ORDER BY rowid')] == before[table]
        assert project.analysis_status()['facts_stale']
        monkeypatch.setattr(project, 'analyze', original_analyze)
        assert not project.refresh_dos_state()['status']['facts_stale']


def test_elf_queries_do_not_require_dos_revision_and_cannot_run_dos_repair(tmp_path):
    binary = tmp_path / 'native.elf'
    binary.write_bytes(_elf64(b'\xc3'))
    with Project.create(tmp_path / 'native.fdb', binary) as project:
        assert project.analyze()['stable']
        assert project.cfg(0x400100)['instruction_count'] == 1
        assert project.calls()['items'] == []
        assert project.memory_accesses(0x400100, include_unresolved=False)['items'] == []
        assert project.refresh_facts()['instructions_indexed'] == 1
        assert 'facts_stale' not in project.analysis_status()
        with pytest.raises(ValueError, match='requires a DOS MZ'):
            project.refresh_dos_state()


def test_legacy_done_derived_jobs_do_not_report_a_current_fixed_point(tmp_path):
    with _project(tmp_path) as project:
        project.auto_analyze(max_functions=100)
        with project.transaction(True):
            project.db.execute("UPDATE advanced_jobs SET state='done' WHERE version=1")
        _legacy(project)
        status=project.advanced_status()
        assert status['facts_stale'] and not status['stable'] and status['pending_dos_state_refresh']==1
        assert status['pending']>=1 and 'refresh-dos-state' in status['note']
