"""Dependencies invalidate affected routine slices and transitive consumers."""
import json

from fdisbull.project import Project


def _project(tmp_path, data=None):
    if data is None:
        data = bytearray(0x100)
        data[:6] = bytes.fromhex('e80b000000c3')
        data[0x10] = data[0x20] = 0xC3
    source = tmp_path / 'incremental.bin'
    source.write_bytes(data)
    return Project.create(tmp_path / 'incremental.fdb', source, arch='x86', base=0x1000)


def _job(project, entry, addresses=(), dependencies=(), context=None):
    context = context or project.context
    key = f'{entry:016x}'
    project.db.execute('INSERT INTO advanced_jobs VALUES (?,?,?,?,?,?)', (1, context, key, 'done', 1, 'test completed job'))
    project.db.execute('INSERT INTO advanced_results VALUES (?,?,?,?,?)', (1, context, key, 1, json.dumps({'entry': entry})))
    for address in addresses:
        row = project.db.execute('SELECT size FROM instructions WHERE version=1 AND context=? AND address=?', (context, f'{address:016x}')).fetchone()
        assert row is not None
        project._derived_dependency(1, context, entry, 'instruction', address, row[0], context)
    for kind, address, size, dep_context in dependencies:
        project._derived_dependency(1, context, entry, kind, address, size, dep_context)


def _states(project):
    return {int(row['address'], 16): row['state'] for row in project.db.execute('SELECT * FROM advanced_jobs WHERE version=1')}


def test_representation_retracts_only_dependency_slices_and_transitive_callers(tmp_path):
    with _project(tmp_path) as project:
        project.analyze(); project.analyze(start=0x1020)
        _job(project, 0x1000, [0x1000, 0x1005], [('call', 0x1010, 1, project.context)])
        _job(project, 0x1010, [0x1010])
        _job(project, 0x1020, [0x1020])
        original = project.regions(1)[0].data
        result = project.represent(0x1010, 'unexplored', defer=True)
        assert result['invalidation']['mode'] == 'dependency_index'
        assert _states(project) == {0x1000: 'pending', 0x1010: 'pending', 0x1020: 'done'}
        assert {int(row[0], 16) for row in project.db.execute('SELECT address FROM instructions WHERE version=1')} == {0x1020}
        assert project.regions(1)[0].data == original
        project.analyze()
        assert project.locate(0x1010)['held']
        assert project.locate(0x1020)['decoded']
        assert not project.disassembly(0x1000)['instructions'][0]['target'] is None


def test_incomplete_dependency_index_falls_back_to_safe_full_reset(tmp_path):
    with _project(tmp_path) as project:
        project.analyze(); project.analyze(start=0x1020)
        _job(project, 0x1000, [0x1000, 0x1005])
        result = project.represent(0x1010, 'unexplored', defer=True)
        assert result['invalidation']['mode'] == 'full_reset'
        assert project.db.execute('SELECT count(*) FROM advanced_jobs').fetchone()[0] == 0
        assert project.db.execute('SELECT count(*) FROM instructions').fetchone()[0] == 0


def test_type_definition_change_invalidates_only_bound_range_and_call_consumers(tmp_path):
    with _project(tmp_path) as project:
        project.analyze(); project.analyze(start=0x1020)
        project.define_type('Record', dict(kind='struct', size=8, fields=[dict(name='old', offset=4, type='u32')]))
        project.apply_type(0x1040, 'Record', name='record')
        _job(project, 0x1000, dependencies=[('call', 0x1010, 1, project.context)])
        _job(project, 0x1010, dependencies=[('memory', 0x1044, 4, '')])
        _job(project, 0x1020, dependencies=[('memory', 0x1080, 4, '')])
        result = project.define_type('Record', dict(kind='struct', size=8, fields=[dict(name='renamed', offset=4, type='u32')]))
        assert len(result['invalidated_tasks']) == 2
        assert _states(project) == {0x1000: 'pending', 0x1010: 'pending', 0x1020: 'done'}


def test_shrinking_type_binding_invalidates_consumers_of_old_tail(tmp_path):
    with _project(tmp_path) as project:
        project.define_type('Wide', dict(kind='array', element='u8', count=16))
        project.apply_type(0x1040, 'Wide', name='wide')
        _job(project, 0x1000, dependencies=[('memory', 0x104F, 1, '')])
        result = project.apply_type(0x1040, 'u8', name='narrow')
        assert result['invalidated_tasks']
        assert _states(project)[0x1000] == 'pending'


def test_held_interior_byte_retracts_overlapping_generated_data_span(tmp_path):
    data = bytearray(0x100)
    data[:8] = bytes.fromhex('488d0539000000c3')
    data[0x40:0x4C] = b'hello world\0'
    with _project(tmp_path, data) as project:
        project.analyze()
        assert any(item['address'] == '0x1040' for item in project.items())
        _job(project, 0x1000, [0x1000, 0x1007], [('memory', 0x1040, 12, '')])
        result = project.represent(0x1044, 'unexplored', defer=True)
        assert result['invalidation']['mode'] == 'dependency_index'
        assert not any(int(item['address'], 16) <= 0x1044 < int(item['address'], 16) + item['size'] for item in project.items())
        assert project.locate(0x1044)['held']


def test_shared_owned_edges_survive_until_all_owners_are_invalidated(tmp_path):
    with _project(tmp_path) as project:
        _job(project, 0x1000, dependencies=[('memory', 0x1040, 1, '')])
        _job(project, 0x1010, dependencies=[('memory', 0x1050, 1, '')])
        edge = (1, project.context, '0000000000001000', '0000000000001020', project.context, 'resolved_branch')
        project.db.execute('INSERT INTO xrefs VALUES (?,?,?,?,?,?)', (edge[0], edge[1], edge[2], edge[3], edge[5], 'test derived target'))
        for owner in (0x1000, 0x1010):
            project.db.execute('INSERT INTO advanced_edges VALUES (?,?,?,?,?,?,?,?)',
                               (1, project.context, f'{owner:016x}', project.context, edge[2], edge[3], project.context, edge[5]))
        project._invalidate_derived(1, 0x1040)
        assert project.db.execute("SELECT 1 FROM xrefs WHERE kind='resolved_branch'").fetchone()
        project._invalidate_derived(1, 0x1050)
        assert not project.db.execute("SELECT 1 FROM xrefs WHERE kind='resolved_branch'").fetchone()


def test_version_copy_keeps_interpretations_and_discards_derived_cache(tmp_path):
    with _project(tmp_path) as project:
        project.define_type('Bytes', dict(kind='array', element='u8', count=4))
        project.apply_type(0x1040, 'Bytes', name='payload')
        _job(project, 0x1000, dependencies=[('memory', 0x1040, 4, '')])
        project.db.execute('INSERT INTO function_summaries VALUES (?,?,?,?,?)', (1, project.context, '0000000000001010', '{"stack_delta":0}', 'reviewer'))
        project.db.execute('INSERT INTO function_summaries VALUES (?,?,?,?,?)', (1, project.context, '0000000000001020', '{"stack_delta":0,"source":{"kind":"exact_signature"}}', 'exact signature'))
        project.db.execute('INSERT INTO library_signatures VALUES (?,?,?)', (1, 'known', '{"bytes":"c3"}'))
        child = project.patch(0x1040, '01')['version']
        assert project.types(version=child)['bindings'] == project.types(version=1)['bindings']
        assert project.db.execute('SELECT count(*) FROM advanced_jobs WHERE version=?', (child,)).fetchone()[0] == 0
        assert project.db.execute('SELECT count(*) FROM advanced_jobs WHERE version=1').fetchone()[0] == 1
        assert project.db.execute('SELECT count(*) FROM function_summaries WHERE version=?', (child,)).fetchone()[0] == 1
        assert project.db.execute('SELECT count(*) FROM library_signatures WHERE version=?', (child,)).fetchone()[0] == 1


def test_full_reset_drops_obsolete_bounded_indirect_function_seeds(tmp_path):
    with _project(tmp_path) as project:
        project.analyze(); project.analyze(start=0x1020)
        project.db.execute("UPDATE functions SET source='bounded indirect call candidate' WHERE address='0000000000001020'")
        project.represent(0x1000, 'unexplored', defer=True)
        assert not project.db.execute("SELECT 1 FROM functions WHERE address='0000000000001020' AND source='bounded indirect call candidate'").fetchone()


def test_shared_instruction_owners_are_closed_before_retracting_slices(tmp_path):
    data = bytearray(0x100)
    data[:2] = bytes.fromhex('eb0e')
    data[8:10] = bytes.fromhex('eb06')
    data[0x10] = data[0x20] = 0xC3
    with _project(tmp_path, data) as project:
        project.analyze(); project.analyze(start=0x1008); project.analyze(start=0x1020)
        _job(project, 0x1000, [0x1000, 0x1010])
        _job(project, 0x1008, [0x1008, 0x1010])
        _job(project, 0x1020, [0x1020])
        result = project.represent(0x1000, 'unexplored', defer=True)
        assert result['invalidation']['mode'] == 'dependency_index'
        assert _states(project) == {0x1000: 'pending', 0x1008: 'pending', 0x1020: 'done'}
        assert project.locate(0x1020)['decoded']
        assert not project.locate(0x1010)['decoded']


def test_pending_cached_results_are_explicitly_stale_and_not_returned_as_effects(tmp_path):
    with _project(tmp_path) as project:
        _job(project, 0x1000, dependencies=[('memory', 0x1040, 4, '')])
        document = dict(call_effects=[dict(resolved=True, address=0x1040, end_exclusive=0x1044, size=4, access='write')])
        project.db.execute('UPDATE advanced_results SET document=? WHERE address=?', (json.dumps(document), '0000000000001000'))
        assert project.call_effects(0x1040)['total'] == 1
        project.apply_type(0x1040, 'u32')
        cached = project.function_analysis(0x1000)
        assert cached['stale'] and cached['state'] == 'pending' and cached['result'] == document
        effects = project.call_effects(0x1040)
        assert effects['items'] == [] and effects['stale_jobs_excluded'] == 1


def test_last_advanced_call_evidence_retraction_drops_derived_function_candidate(tmp_path):
    with _project(tmp_path) as project:
        _job(project, 0x1000, dependencies=[('memory', 0x1040, 1, '')])
        project.db.execute('INSERT INTO functions(version,context,address,name,source) VALUES (?,?,?,?,?)',
                           (1, project.context, '0000000000001020', 'derived_function', 'bounded indirect call candidate'))
        project.db.execute('INSERT INTO xrefs VALUES (?,?,?,?,?,?)',
                           (1, project.context, '0000000000001000', '0000000000001020', 'resolved_call', 'test derived call'))
        project.db.execute('INSERT INTO advanced_edges VALUES (?,?,?,?,?,?,?,?)',
                           (1, project.context, '0000000000001000', project.context, '0000000000001000', '0000000000001020', project.context, 'resolved_call'))
        project.apply_type(0x1040, 'u8')
        assert not project.db.execute("SELECT 1 FROM xrefs WHERE kind='resolved_call'").fetchone()
        assert not project.db.execute("SELECT 1 FROM functions WHERE address='0000000000001020' AND source='bounded indirect call candidate'").fetchone()
