"""Artifact-backed event searches over authored native-shaped observations."""
from copy import deepcopy
import hashlib
import json

import pytest

from fdisbull import event_search
from fdisbull.debug_semantics import contract, normalize_trace
from fdisbull.event_search import EventSearchProjectMixin
from fdisbull.project import Project


SearchProject = Project if issubclass(Project, EventSearchProjectMixin) else type(
    'SearchProject', (EventSearchProjectMixin, Project), {})


@pytest.fixture
def project(tmp_path):
    binary = tmp_path / 'events.com'
    binary.write_bytes(bytes.fromhex('90' * 32 + 'ebfe'))
    with SearchProject.create(tmp_path / 'events.fdb', binary, image='com') as result:
        yield result


def document(project, observations, *, run='run-a', runtime=0x800, version=None,
             complete=True, window=None, backend='dosbox'):
    version = project.version(version)
    mapping = dict(source_sha256=project.meta['source_sha256'], version_sha256=version['sha256'],
                   runtime_profile='real-normal-com-v1', static_load_segment=0x1000,
                   runtime_load_segment=runtime)
    if backend != 'dosbox':
        mapping['backend'] = backend
    events = []
    for index, observation in enumerate(observations):
        offset, value = observation[:2]
        code = observation[2] if len(observation) > 2 else '90'
        updates = dict(eax=hex(value), instruction_pointer=hex(offset))
        if index == 0:
            updates.update(ebx='0x00000037', ecx='0x00000000', edx='0x00000000',
                esi='0x00000100', edi='0x00000000', ebp='0x00000000', esp='0x0000fffe',
                flags='0x00000202', cs=hex(runtime), ds=hex(runtime), es=hex(runtime),
                ss=hex(runtime), fs='0x0000', gs='0x0000')
        events.append(dict(sequence=index + 1,
            address=dict(space='segmented', segment=hex(runtime), offset=hex(offset)),
            cpu_mode='real', code_bits=16, stack_bits=16, execution_bytes=code, ram_bytes=code,
            instruction='authored observation', project_address=hex(0x10000 + offset),
            project_segmented_address=f'1000:{offset:04x}', register_changes=updates))
    normalize_trace(backend, events, version=version['id'], delta=(runtime - 0x1000) * 16,
                    budget_reached=complete)
    result = dict(version=version['id'], mapping=mapping, observation_contract=contract(backend),
        run=dict(run=run, outcome='pause', timed_out=False, hook_hits=[],
                 session=dict(state='stopped', stop_reason=dict(kind='pause'))),
        events=events, requested_count=len(events), complete=complete)
    if window is not None:
        result['window'] = deepcopy(window)
    return result


def save_trace(project, value, *, kind='trace'):
    run = value['run']['run'] if isinstance(value['run'], dict) else value['run']
    with project.transaction(True):
        if project.db.execute('SELECT 1 FROM debug_runs WHERE id=?', (run,)).fetchone() is None:
            project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                (run, value['version'], 'authored', None, 'stopped', json.dumps(value['mapping'])))
        return project._debug_artifact(run, 'authored-trace.json', kind,
            json.dumps(value).encode(), dict(event_count=len(value['events']), complete=value['complete']))['artifact']


def trace(project, observations, **options):
    return save_trace(project, document(project, observations, **options))


def contents(project, artifact):
    return json.loads(bytes(project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',
                                             (artifact,)).fetchone()[0]))


def replace(project, artifact, value, *, rehash=True):
    data = value if isinstance(value, bytes) else json.dumps(value).encode()
    with project.transaction(True):
        if rehash:
            project.db.execute('UPDATE debug_artifacts SET data=?,sha256=? WHERE id=?',
                               (data, hashlib.sha256(data).hexdigest(), artifact))
        else:
            project.db.execute('UPDATE debug_artifacts SET data=? WHERE id=?', (data, artifact))


def search_count(project):
    return project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='event-search'").fetchone()[0]


def test_click_idle_other_action_narrowing_survives_reopening_without_changing_ancestors(project):
    clicked = trace(project, [(0x100, 1), (0x101, 1), (0x102, 1)], run='click-A')
    idle = trace(project, [(0x100, 0), (0x100, 0)], run='idle', runtime=0x900)
    repeated = trace(project, [(0x101, 1), (0x101, 1), (0x103, 1)], run='click-A-again', runtime=0xa00)
    start = project.event_search_start(clicked, label='click A')['artifact']
    removed_idle = project.event_search_refine(start, idle, mode='exclude', label='idle')['artifact']
    narrowed = project.event_search_refine(removed_idle, repeated, label='repeat click A')['artifact']
    assert {row['site']['address'] for row in project.event_search_results(start)['rows']} == {0x10100, 0x10101, 0x10102}
    with SearchProject(project.path) as reopened:
        result = reopened.event_search_results(narrowed)
        assert [row['site']['address'] for row in result['rows']] == [0x10101]
        assert result['rows'][0]['support_trials'] == 2
        assert [item['artifact'] for item in result['trace_references']] == [clicked, idle, repeated]
        assert result['owner']['run'] == 'click-A'
        assert [item['label'] for item in result['history']] == ['click A', 'idle', 'repeat click A']
    assert search_count(project) == 3


def test_register_value_features_preserve_a_shared_handler_with_a_different_argument(project):
    a = trace(project, [(0x100, 1)], run='action-a')
    b = trace(project, [(0x100, 2)], run='action-b')
    site = project.event_search_start(a)['artifact']
    empty = project.event_search_refine(site, b, mode='exclude')['artifact']
    assert project.event_search_results(empty)['rows'] == []
    values = project.event_search_start(a, feature='register-value', registers=['EAX'])['artifact']
    different_action = project.event_search_refine(values, b, mode='exclude')['artifact']
    rows = project.event_search_results(different_action)['rows']
    assert len(rows) == 1 and rows[0]['register'] == 'eax' and rows[0]['value'] == 1
    assert rows[0]['site']['address'] == 0x10100
    assert contents(project, values)['operation']['registers'] == ['eax']


def test_source_feature_comparison_is_not_event_ordinal_alignment_or_candidate_resurrection(project):
    a = trace(project, [(0x100, 1), (0x101, 1), (0x102, 1)])
    b = trace(project, [(0x102, 1), (0x100, 1), (0x102, 1)], run='b')
    state = project.event_search_start(a)['artifact']
    state = project.event_search_refine(state, b)['artifact']
    state = project.event_search_refine(state, a)['artifact']
    assert {r['site']['address'] for r in project.event_search_results(state)['rows']} == {0x10100, 0x10102}


def test_pagination_retains_original_indices_and_returns_only_relevant_witnesses(project):
    identifier = trace(project, [(0x100 + index, index) for index in range(8)])
    search = project.event_search_start(identifier)['artifact']
    whole = project.event_search_results(search, limit=8)
    pages = [project.event_search_results(search, offset=index, limit=3) for index in (0, 3, 6)]
    assert [row for page in pages for row in page['rows']] == whole['rows']
    assert project.event_search_results(search, offset=100, limit=3)['rows'] == []
    for page in pages:
        referenced = {i for row in page['rows'] for i in row['samples']}
        assert {sample['sample_index'] for sample in page['samples']} == referenced
        assert all(sample['artifact']['id'] == identifier for sample in page['samples'])


def test_default_project_regions_have_stable_bound_identity_and_half_open_membership(project):
    identifier = trace(project, [(0x100, 1), (0x121, 1)])
    search = project.event_search_start(identifier)['artifact']
    envelope = contents(project, search)
    assert envelope['regions'] == [dict(id='project:0:10100:10122', name='loaded_image',
                                       space='project', start=0x10100, end=0x10122)]
    result = project.event_trace_query(identifier,
        predicate=dict(kind='pc-range', space='project', start='0x10100', end='0x10121'))
    assert result['matched_count'] == 1 and result['rows'][0]['index'] == 0


def test_retrospective_query_reconstructs_sparse_registers_and_pages_matches(project):
    value = document(project, [(0x100, 1), (0x101, 2), (0x102, 3), (0x103, 4)])
    identifier = save_trace(project, value)
    result = project.event_trace_query(identifier, predicate=dict(kind='register', register='BX', equals=0x37),
                                      offset=1, limit=2)
    assert result['matched_count'] == 4 and [row['index'] for row in result['rows']] == [1, 2]
    assert result['next_offset'] == 3 and result['unknown_count'] == 0
    assert result['predicate']['register'] == 'bx'
    assert search_count(project) == 0  # Querying never creates a search or executes a target.


def test_retrospective_transition_predicates_receive_initial_and_previous_events(project):
    identifier = trace(project, [(0x100, 1), (0x101, 1), (0x110, 1)])
    regions = [dict(id='first', space='project', start=0x10100, end=0x10102),
               dict(id='second', space='project', start=0x10110, end=0x10120)]
    changed = project.event_trace_query(identifier, predicate={'kind': 'region-change'}, regions=regions)
    jump = project.event_trace_query(identifier, predicate={'kind': 'nonsequential'})
    assert [row['index'] for row in changed['rows']] == [2]
    assert [row['index'] for row in jump['rows']] == [2]
    assert jump['unknown_count'] == 1


def test_missing_historical_register_stays_unknown_and_is_never_treated_as_zero(project):
    identifier = trace(project, [(0x100, 1), (0x101, 1)])
    result = project.event_trace_query(identifier, predicate=dict(kind='register', register='cr3', equals=0))
    assert result['rows'] == [] and result['matched_count'] == 0 and result['unknown_count'] == 2
    assert result['unknown_examples'][0]['unknown']


def test_partial_window_is_queryable_but_cannot_remove_search_candidates(project):
    complete = trace(project, [(0x100, 1), (0x101, 1)])
    incomplete = trace(project, [(0x100, 1)], run='partial', complete=False)
    start = project.event_search_start(complete)['artifact']
    query = project.event_trace_query(incomplete, predicate=dict(kind='mnemonic', equals='nop'))
    assert query['matched_count'] == 1 and not query['complete']
    with pytest.raises(ValueError, match='closed'):
        project.event_search_start(incomplete)
    with pytest.raises(ValueError, match='closed'):
        project.event_search_refine(start, incomplete, mode='exclude')
    assert len(project.event_search_results(start)['rows']) == 2 and search_count(project) == 1


def test_explicit_finite_predicate_capture_can_be_a_closed_window(project):
    identifier = trace(project, [(0x100, 7)], complete=False,
                       window=dict(closed=True, reason='predicate'))
    search = project.event_search_start(identifier)['artifact']
    result = project.event_search_results(search)
    assert len(result['rows']) == 1
    assert result['history'][0]['window']['reason'] == 'predicate'


def test_runtime_only_protected_sites_are_not_compared_across_runs(project):
    a = document(project, [(0x100, 7)])
    for event in a['events']:
        event.update(cpu_mode='protected', code_bits=32, project_address=None, project_segmented_address=None)
        event['identity'].update(context=None, project_address=None)
    identifier = save_trace(project, a)
    search = project.event_search_start(identifier)['artifact']
    assert project.event_search_results(search)['rows'] == []
    query = project.event_trace_query(identifier, predicate=dict(kind='register', register='eax', equals=7))
    assert query['matched_count'] == 1 and query['rows'][0]['site'] is None


def test_caller_region_labels_cannot_turn_runtime_bytes_into_source_candidates(project):
    identifier = trace(project, [(0x200, 7)])
    regions = [dict(id='claimed-code', name='Caller label', space='project', start=0x10200, end=0x10300)]
    search = project.event_search_start(identifier, regions=regions)['artifact']
    result = project.event_search_results(search)
    assert result['rows'] == [] and result['history'][0]['unqualified_events'] == 1
    query = project.event_trace_query(identifier, regions=regions,
        predicate=dict(kind='register', register='eax', equals=7))
    assert query['matched_count'] == 1
    assert query['rows'][0]['site'] is None and query['rows'][0]['pc']['project'] is None
    assert query['rows'][0]['region'] is None


def test_instruction_crossing_image_end_is_not_a_source_site_but_its_pc_is_known(project):
    identifier = trace(project, [(0x121, 7, 'b83412')])
    search = project.event_search_start(identifier)['artifact']
    assert project.event_search_results(search)['rows'] == []
    query = project.event_trace_query(identifier,
        predicate=dict(kind='pc-range', space='project', start=0x10121, end=0x10122))
    assert query['matched_count'] == 1 and query['rows'][0]['pc']['project'] == 0x10121
    assert query['rows'][0]['site'] is None


def test_observed_modified_instruction_keeps_its_own_byte_identity(project):
    nop = trace(project, [(0x100, 7, '90')])
    modified = trace(project, [(0x100, 7, '91')], run='modified')
    original = project.event_search_start(nop)['artifact']
    refined = project.event_search_refine(original, modified, mode='exclude')['artifact']
    assert len(project.event_search_results(refined)['rows']) == 1
    query = project.event_trace_query(modified, predicate=dict(kind='mnemonic', equals='xchg'))
    assert query['matched_count'] == 1 and query['rows'][0]['site'] is not None


def test_pe_relocated_full_register_observations_share_only_qualified_source_sites(tmp_path):
    from fixtures_formats import pe64
    binary = tmp_path / 'authored.exe'; binary.write_bytes(pe64())
    with SearchProject.create(tmp_path / 'pe.fdb', binary) as project:
        identifiers = []
        for run, base in (('pe-a', 0x180000000), ('pe-b', 0x190000000)):
            value = dict(run=run, version=1, complete=True, requested_count=1,
                mapping=dict(backend='wine-qemu', source_sha256=project.meta['source_sha256'],
                    version_sha256=project.version(1)['sha256'], runtime_profile='pe64-win32-debug-2', bits=64,
                    static_image_base='0x140000000', runtime_image_base=hex(base)),
                observation_contract=contract('wine-qemu'), events=[dict(address=hex(base + 0x1010),
                    project_address='0x140001010', bytes='c3',
                    registers=dict(bits=64, rip=hex(base + 0x1010), rflags='0x202', thread=7,
                                   general=dict(rax='0x100000037', rbx='0x1')))])
            normalize_trace('wine-qemu', value['events'], version=1)
            identifiers.append(save_trace(project, value))
        search = project.event_search_start(identifiers[0], feature='register-value', registers=['eax'])['artifact']
        refined = project.event_search_refine(search, identifiers[1])['artifact']
        result = project.event_search_results(refined)
        assert len(result['rows']) == 1 and result['rows'][0]['value'] == 0x37
        assert result['rows'][0]['site']['address'] == 0x140001010
        query = project.event_trace_query(identifiers[1], predicate=dict(kind='mnemonic', equals='ret'))
        assert query['rows'][0]['region']['name'] == '.text'


@pytest.fixture
def pe_project(tmp_path):
    from fixtures_formats import pe64
    binary = tmp_path / 'restore.exe'; binary.write_bytes(pe64())
    with SearchProject.create(tmp_path / 'restore.fdb', binary) as project:
        yield project


def pe_document(project, *, run='pe-run', base=0x180000000):
    mapping = dict(backend='wine-qemu', source_sha256=project.meta['source_sha256'],
        version_sha256=project.version(1)['sha256'], runtime_profile='pe64-win32-debug-2', bits=64,
        static_image_base='0x140000000', runtime_image_base=hex(base), target_pid=42, qemu_pid=100,
        runtime_inputs={name: dict(path='/authored/' + name, sha256=digit * 64)
                        for name, digit in (('qemu', 'a'), ('kernel', 'b'), ('initramfs', 'c'))},
        capabilities=dict(architecture='x86-64', bits=64), window_requested=False)
    value = dict(run=run, version=1, mapping=mapping, complete=True, requested_count=1,
        observation_contract=contract('wine-qemu'), events=[dict(address=hex(base + 0x1010),
            project_address='0x140001010', bytes='c3', registers=dict(bits=64,
                rip=hex(base + 0x1010), rflags='0x202', thread=7, general=dict(rax='0x37')))])
    normalize_trace('wine-qemu', value['events'], version=1)
    return value


def update_run(project, run, metadata):
    with project.transaction(True):
        project.db.execute('UPDATE debug_runs SET metadata=? WHERE id=?', (json.dumps(metadata), run))


def record_pe_restore(project, old, *, fault=None):
    """Authored manifest/receipt ordering, never a claimed native VM restore."""
    current = deepcopy(old['mapping'])
    current.update(runtime_image_base='0x190000000', target_pid=43, qemu_pid=200)
    current['capabilities']['restored-advertisement'] = True
    current['runtime_inputs']['qemu']['path'] = '/new-owned-path/qemu'
    if fault == 'different-profile':
        current['runtime_profile'] = 'another-runtime-profile'
    elif fault == 'different-static-base':
        current['static_image_base'] = '0x150000000'
    elif fault == 'different-input-hash':
        current['runtime_inputs']['qemu']['sha256'] = 'd' * 64
    state_mapping = deepcopy(current)
    if fault == 'state-source':
        state_mapping['source_sha256'] = 'f' * 64
    manifest = dict(format='fdisbull-qemu-native-1', metadata=state_mapping,
                    machine_sha256='e' * 64, machine_size=1)
    with project.transaction(True):
        # A checkpoint can belong to another run of the same source/version.
        project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
            ('checkpoint-owner', 1, 'authored', None, 'stopped', json.dumps(state_mapping)))
        state = project._debug_artifact('checkpoint-owner', 'authored-state.json', 'state',
            json.dumps(manifest).encode(), dict(format=manifest['format']))
        receipt = dict(artifact=state['artifact'], sha256=state['sha256'], state='stopped')
        if fault == 'failed':
            receipt['state'] = 'interrupted'
        elif fault == 'wrong-hash':
            receipt['sha256'] = 'f' * 64
        if fault != 'missing':
            inserted = project.db.execute('INSERT INTO debug_events(run,created,operation,evidence) VALUES (?,?,?,?)',
                ('checkpoint-owner' if fault == 'wrong-run' else old['run'], 'authored', 'load-state', json.dumps(receipt)))
            if fault == 'before-capture':
                project.db.execute('UPDATE debug_events SET sequence=0 WHERE sequence=?', (inserted.lastrowid,))
        if fault == 'unrelated-newer-load':
            project.db.execute('INSERT INTO debug_events(run,created,operation,evidence) VALUES (?,?,?,?)',
                (old['run'], 'authored', 'load-state', json.dumps(dict(receipt, artifact='another-checkpoint'))))
    current['restored_from'] = state['artifact']
    update_run(project, old['run'], current)
    return current


def test_pe_checkpoint_operational_metadata_does_not_invalidate_prior_trace_or_search(pe_project):
    project = pe_project
    value = pe_document(project)
    identifier = save_trace(project, value)
    search = project.event_search_start(identifier)['artifact']
    current = deepcopy(value['mapping'])
    current.update(qemu_pid=200, restored_from='owned-checkpoint-reference', window_requested=True,
                   dot_mode=dict(enabled=True, window_id=3))
    current['capabilities'].update(restored=True)
    current['runtime_inputs']['qemu']['path'] = '/same-content/new-path/qemu'
    update_run(project, value['run'], current)
    assert len(project.event_search_results(search)['rows']) == 1
    assert project.event_trace_query(identifier, predicate=dict(kind='register', register='eax', equals=0x37))['matched_count'] == 1


def test_equivalent_pe_mapping_base_representations_preserve_trace_identity(pe_project):
    old = pe_document(pe_project)
    identifier = save_trace(pe_project, old)
    current = deepcopy(old['mapping'])
    current.update(static_image_base=0x140000000, runtime_image_base=0x180000000)
    update_run(pe_project, old['run'], current)
    assert pe_project.event_trace_query(identifier, predicate=dict(kind='mnemonic', equals='ret'))['matched_count'] == 1


def test_equivalent_dos_mapping_base_representations_preserve_trace_identity(project):
    old = document(project, [(0x100, 1)])
    identifier = save_trace(project, old)
    current = deepcopy(old['mapping'])
    current.update(static_load_segment='0X1000', runtime_load_segment='0x0800')
    update_run(project, old['run']['run'], current)
    assert project.event_search_start(identifier)['results']['candidate_count'] == 1


def test_ordered_owned_pe_restore_preserves_pre_restore_mapping_and_supports_new_trace_refinement(pe_project):
    project = pe_project
    old = pe_document(project)
    identifier = save_trace(project, old)
    search = project.event_search_start(identifier)['artifact']
    current = record_pe_restore(project, old)
    before = project.event_trace_query(identifier, predicate=dict(kind='mnemonic', equals='ret'))
    assert before['rows'][0]['pc']['linear'] == 0x180001010
    assert before['rows'][0]['pc']['project'] == 0x140001010
    new = pe_document(project, base=0x190000000)
    new['mapping'] = current
    after = save_trace(project, new)
    refined = project.event_search_refine(search, after)['artifact']
    with SearchProject(project.path) as reopened:
        result = reopened.event_search_results(refined)
        assert len(result['rows']) == 1 and result['rows'][0]['support_trials'] == 2
        assert [entry['artifact'] for entry in result['trace_references']] == [identifier, after]


@pytest.mark.parametrize('fault', ['missing', 'wrong-run', 'before-capture', 'failed', 'wrong-hash',
    'different-profile', 'different-static-base', 'different-input-hash', 'state-source', 'unrelated-newer-load'])
def test_pe_runtime_base_change_requires_ordered_qualified_restore_evidence(pe_project, fault):
    project = pe_project
    old = pe_document(project)
    identifier = save_trace(project, old)
    search = project.event_search_start(identifier)['artifact']
    record_pe_restore(project, old, fault=fault)
    with pytest.raises(ValueError, match='mapping differs'):
        project.event_search_results(search)
    assert search_count(project) == 1


@pytest.mark.parametrize('value', [True, -1, 1 << 64])
def test_matching_owned_restore_manifest_cannot_justify_an_impossible_current_base(pe_project, value):
    project = pe_project
    old = pe_document(project)
    identifier = save_trace(project, old)
    current = record_pe_restore(project, old)
    current['runtime_image_base'] = value
    state = contents(project, current['restored_from'])
    state['metadata']['runtime_image_base'] = value
    replace(project, current['restored_from'], state)
    digest = project.db.execute('SELECT sha256 FROM debug_artifacts WHERE id=?',
                                (current['restored_from'],)).fetchone()[0]
    with project.transaction(True):
        project.db.execute("UPDATE debug_events SET evidence=? WHERE run=? AND operation='load-state'",
            (json.dumps(dict(artifact=current['restored_from'], sha256=digest, state='stopped')), old['run']))
    update_run(project, old['run'], current)
    with pytest.raises(ValueError, match='runtime_image_base mapping base'):
        project.event_search_start(identifier)


def test_changed_historical_capture_cannot_borrow_a_later_pe_restore_receipt(pe_project):
    project = pe_project
    old = pe_document(project)
    identifier = save_trace(project, old)
    record_pe_restore(project, old)
    changed = contents(project, identifier)
    changed['mapping']['runtime_image_base'] = '0x170000000'
    changed['events'][0]['address'] = '0x170001010'
    changed['events'][0]['registers']['rip'] = '0x170001010'
    changed['events'][0]['identity']['runtime_address'] = '0x170001010'
    replace(project, identifier, changed)
    with pytest.raises(ValueError, match='creation receipt'):
        project.event_search_start(identifier)


@pytest.mark.parametrize('change', ['missing', 'duplicate'])
def test_historical_pe_capture_requires_exactly_one_retained_creation_receipt(pe_project, change):
    project = pe_project
    old = pe_document(project)
    identifier = save_trace(project, old)
    receipt = project.db.execute("SELECT sequence,evidence FROM debug_events WHERE run=? AND operation='artifact'",
                                 (old['run'],)).fetchone()
    with project.transaction(True):
        if change == 'missing':
            project.db.execute('DELETE FROM debug_events WHERE sequence=?', (receipt['sequence'],))
        else:
            project.db.execute('INSERT INTO debug_events(run,created,operation,evidence) VALUES (?,?,?,?)',
                (old['run'], 'authored', 'artifact', project._external_text(receipt['evidence'])))
    record_pe_restore(project, old)
    with pytest.raises(ValueError, match='unique artifact creation receipt'):
        project.event_search_start(identifier)
    assert search_count(project) == 0


def test_historical_creation_receipt_count_is_bounded_without_partial_qualification(pe_project, monkeypatch):
    project = pe_project
    old = pe_document(project)
    identifier = save_trace(project, old)
    save_trace(project, old)
    record_pe_restore(project, old)
    monkeypatch.setattr(event_search, 'MAX_CAPTURE_RECEIPTS', 1)
    with pytest.raises(ValueError, match='receipts exceed the count or size budget'):
        project.event_search_start(identifier)
    assert search_count(project) == 0


@pytest.mark.parametrize('operation', ['artifact', 'load-state'])
def test_historical_receipt_size_is_checked_before_decoding(pe_project, monkeypatch, operation):
    project = pe_project
    old = pe_document(project)
    identifier = save_trace(project, old)
    record_pe_restore(project, old)
    monkeypatch.setattr(event_search, 'MAX_BYTES', 4096)
    # External decoding must be bounded even when the receipt is malformed.
    with project.transaction(True):
        project.db.execute('UPDATE debug_events SET evidence=? WHERE run=? AND operation=?',
            (project._external_text('invalid ' + 'x' * 4096), old['run'], operation))
    with pytest.raises(ValueError, match='receipt.*size budget'):
        project.event_search_start(identifier)
    assert search_count(project) == 0


@pytest.mark.parametrize('field', ['static_load_segment', 'runtime_load_segment'])
def test_missing_dos_mapping_base_is_not_inferred_from_event_addresses(project, field):
    value = document(project, [(0x100, 1)])
    value['mapping'].pop(field)
    identifier = save_trace(project, value)
    with pytest.raises(ValueError, match='mapping bases'):
        project.event_search_start(identifier)


@pytest.mark.parametrize('field,value', [('static_load_segment', True), ('runtime_load_segment', 0x10000)])
def test_dos_mapping_bases_are_unsigned_segment_values(project, field, value):
    old = document(project, [(0x100, 1)])
    old['mapping'][field] = value
    identifier = save_trace(project, old)
    with pytest.raises(ValueError, match='mapping base'):
        project.event_search_start(identifier)


@pytest.mark.parametrize('change', ['run', 'version', 'boolean-version', 'source', 'version-hash',
                                   'load-segment', 'backend', 'unsupported-backend'])
def test_trace_must_match_joined_run_version_and_mapping_before_search_creation(project, change):
    value = document(project, [(0x100, 1)])
    identifier = save_trace(project, value)
    if change == 'run':
        value['run']['run'] = 'foreign-run'
    elif change == 'version':
        value['version'] += 1
    elif change == 'boolean-version':
        value['version'] = True
    elif change == 'source':
        value['mapping']['source_sha256'] = 'd' * 64
    elif change == 'version-hash':
        value['mapping']['version_sha256'] = 'e' * 64
    elif change == 'load-segment':
        value['mapping']['runtime_load_segment'] += 1
    elif change == 'backend':
        value['observation_contract']['backend'] = 'wine-qemu'
    else:
        value['mapping']['backend'] = value['observation_contract']['backend'] = 'unknown-engine'
    replace(project, identifier, value)
    with pytest.raises(ValueError):
        project.event_search_start(identifier)
    assert search_count(project) == 0


def test_changed_run_metadata_is_rechecked_on_search_results(project):
    identifier = trace(project, [(0x100, 1)])
    search = project.event_search_start(identifier)['artifact']
    row = project.db.execute('SELECT metadata FROM debug_runs WHERE id=?', ('run-a',)).fetchone()
    metadata = json.loads(row[0]); metadata['version_sha256'] = 'f' * 64
    with project.transaction(True):
        project.db.execute('UPDATE debug_runs SET metadata=? WHERE id=?', (json.dumps(metadata), 'run-a'))
    with pytest.raises(ValueError, match='source or version'):
        project.event_search_results(search)


def test_known_restore_annotations_do_not_change_the_launch_binding(project):
    value = document(project, [(0x100, 1)])
    identifier = save_trace(project, value)
    value['mapping'].update(execution_origin='restored-full-native-checkpoint',
                            checkpoint_intervention=None, delta_experiment='explicit-trial')
    replace(project, identifier, value)
    assert project.event_search_start(identifier)['artifact']


def test_refinement_across_versions_or_backend_identities_is_rejected_atomically(project):
    identifier = trace(project, [(0x100, 1)])
    search = project.event_search_start(identifier)['artifact']
    child = project.patch('1000:0100', '91')
    version = child.get('id', child.get('version'))
    changed = trace(project, [(0x100, 1, '91')], version=version, run='child')
    backend = trace(project, [(0x100, 1)], version=1, run='other-backend', backend='dosbox-qemu')
    for other in (changed, backend):
        with pytest.raises(ValueError, match='identit'):
            project.event_search_refine(search, other)
    assert search_count(project) == 1


@pytest.mark.parametrize('rehash', [False, True])
def test_changed_original_trace_invalidates_every_descendant_even_with_a_new_checksum(project, rehash):
    first = trace(project, [(0x100, 1), (0x101, 1)])
    second = trace(project, [(0x101, 1)], run='second')
    ancestor = project.event_search_start(first)['artifact']
    descendant = project.event_search_refine(ancestor, second)['artifact']
    changed = contents(project, first)
    changed['events'][0]['register_changes']['eax'] = '0x42'
    replace(project, first, changed, rehash=rehash)
    with pytest.raises(ValueError, match='hash|changed'):
        project.event_search_results(descendant)
    with pytest.raises(ValueError):
        project.event_search_refine(descendant, second)
    assert search_count(project) == 2


@pytest.mark.parametrize('change', ['state', 'operation', 'owner', 'generation', 'parent-hash', 'cycle', 'regions'])
def test_rehashed_search_edits_cannot_substitute_candidates_or_parent_lineage(project, change):
    first = trace(project, [(0x100, 1), (0x101, 1)])
    second = trace(project, [(0x101, 1)], run='second')
    ancestor = project.event_search_start(first)['artifact']
    descendant = project.event_search_refine(ancestor, second)['artifact']
    value = contents(project, descendant)
    if change == 'state':
        value['state']['candidate_count'] += 1
    elif change == 'operation':
        value['operation']['mode'] = 'exclude'
    elif change == 'owner':
        value['owner']['run'] = 'second'
    elif change == 'generation':
        value['generation'] = 0
    elif change == 'parent-hash':
        value['parent']['sha256'] = 'f' * 64
    elif change == 'cycle':
        value['parent']['artifact'] = descendant
    else:
        value['regions'][0]['end'] -= 1
    replace(project, descendant, value)
    with pytest.raises(ValueError):
        project.event_search_results(descendant)


def test_stored_trace_reference_run_and_hash_are_checked_independently(project):
    identifier = trace(project, [(0x100, 1)])
    search = project.event_search_start(identifier)['artifact']
    value = contents(project, search)
    value['trace']['run'] = 'unrelated'
    replace(project, search, value)
    with pytest.raises(ValueError, match='Referenced trace'):
        project.event_search_results(search)


def test_resealed_candidate_with_a_valid_shape_still_requires_original_trace_evidence(project):
    identifier = trace(project, [(0x100, 7)])
    search = project.event_search_start(identifier, feature='register-value', registers=['eax'])['artifact']
    envelope = contents(project, search)
    state = envelope['state']
    row = state['candidates'][0]
    row['value'] = 99
    feature = {key: row[key] for key in ('feature', 'site', 'register', 'value')}
    row['key'] = hashlib.sha256(event_search._json(feature)).hexdigest()
    state.pop('state_sha256')
    state['state_sha256'] = hashlib.sha256(event_search._json(state)).hexdigest()
    # Both the pure state seal and the outer artifact digest now pass. Only
    # reconstruction from the original trace establishes the actual value 7.
    event_search.kernel.validate_search(state)
    replace(project, search, envelope)
    with pytest.raises(ValueError, match='verified trace lineage'):
        project.event_search_results(search)


def test_ancestor_search_changes_cannot_be_hidden_by_a_valid_descendant_hash(project):
    a = trace(project, [(0x100, 1)])
    b = trace(project, [(0x100, 1)], run='b')
    parent = project.event_search_start(a)['artifact']
    child = project.event_search_refine(parent, b)['artifact']
    changed = contents(project, parent)
    changed['operation']['label'] = 'different trial'
    replace(project, parent, changed)
    with pytest.raises(ValueError, match='parent artifact changed'):
        project.event_search_results(child)


def test_foreign_artifact_ids_and_other_kinds_are_refused(project, tmp_path):
    identifier = trace(project, [(0x100, 1)])
    search = project.event_search_start(identifier)['artifact']
    target = tmp_path / 'other.com'; target.write_bytes(b'\x90\xeb\xfd')
    with SearchProject.create(tmp_path / 'other.fdb', target, image='com') as other:
        with pytest.raises(ValueError, match='Unknown owned'):
            other.event_search_results(search)
        with pytest.raises(ValueError, match='Unknown owned'):
            other.event_search_start(identifier)
    with pytest.raises(ValueError, match='Unknown owned'):
        project.event_search_start(search)
    with pytest.raises(ValueError, match='Unknown owned'):
        project.event_search_results(identifier)


@pytest.mark.parametrize('identifier', [None, True, [], {}, '', 'bad\nidentifier'])
def test_non_identifier_search_inputs_are_rejected_before_lineage_access(project, identifier):
    with pytest.raises(ValueError, match='artifact identifier'):
        project.event_search_results(identifier)


def test_lineage_budget_refuses_additional_trial_before_writing(project, monkeypatch):
    monkeypatch.setattr(event_search, 'MAX_HISTORY', 2)
    a = trace(project, [(0x100, 1)])
    b = trace(project, [(0x100, 1)], run='b')
    start = project.event_search_start(a)['artifact']
    second = project.event_search_refine(start, b)['artifact']
    with pytest.raises(ValueError, match='128 trials'):
        project.event_search_refine(second, a)
    assert search_count(project) == 2 and len(project.event_search_results(second)['rows']) == 1


@pytest.mark.parametrize('value', [b'{"run":1,"run":2}', b'{"nan":NaN}', b'[]', b'invalid'])
def test_malformed_duplicate_and_nonfinite_json_never_becomes_search_evidence(project, value):
    identifier = trace(project, [(0x100, 1)])
    replace(project, identifier, value)
    with pytest.raises(ValueError):
        project.event_search_start(identifier)
    assert search_count(project) == 0


def test_oversize_trace_is_refused_before_json_decoding(project):
    identifier = trace(project, [(0x100, 1)])
    replace(project, identifier, b' ' * (16 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match='16 MiB'):
        project.event_search_start(identifier)


@pytest.mark.parametrize('options', [dict(offset=-1), dict(offset=True), dict(limit=0), dict(limit=True), dict(limit=257)])
def test_query_pagination_validation_is_independent_of_trace_data(project, options):
    with pytest.raises(ValueError):
        project.event_trace_query('missing', predicate={'kind': 'mnemonic', 'equals': 'nop'}, **options)
