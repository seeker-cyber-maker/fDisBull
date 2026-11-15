"""Adversarial pure witnesses for source-clock joins and retained searches."""
from copy import deepcopy
import hashlib
import json

import pytest

from fdisbull.execution_clock import (
    DOMAIN, FORMAT, MAX_COUNTER, MAX_NS, clock_predicates, validate_clock,
    validate_clock_order, validate_clock_predicate,
)
from fdisbull.execution_events import (
    evaluate_predicate, normalize_trace, refine_search, search_results,
    start_search, validate_predicate, validate_search,
)
from fdisbull.qemu_clock import machine_clock_configuration


def clock(*, ns=128, icount=1, sequence=1, run='run-a', epoch='a' * 32,
          native_epoch=1):
    sample = dict(virtual_ns=ns, icount=icount, native_epoch=native_epoch)
    return dict(format=FORMAT, domain=DOMAIN, run=run, epoch=epoch,
                native_epoch=native_epoch, virtual_ns=ns, icount=icount,
                before=dict(sample, sequence=sequence),
                after=dict(sample, sequence=sequence + 1))


def predicate(*, run='run-a', epoch='a' * 32, native_epoch=1,
              start_ns=128, end_ns=256):
    return dict(kind='virtual-time-range', run=run, epoch=epoch,
                native_epoch=native_epoch, start_ns=start_ns, end_ns=end_ns)


def trace(clocks=None, *, timed=True, backend='qemu-dos', run='run-a'):
    clocks = clocks if clocks is not None else [clock(run=run)]
    source_hash = hashlib.sha256(b'\x90').hexdigest()
    events = []
    for index, observation in enumerate(clocks):
        project_pc = 0x10100 + index
        raw = dict(sequence=index + 1,
            address=dict(space='segmented', segment=0x800, offset=0x100 + index),
            project_address=project_pc, cpu_mode='real', code_bits=16,
            execution_bytes='90', registers=dict(eax=1),
            observation=dict(registers_stage='before-instruction',
                             instruction_completed=False, flags_materialized=True),
            identity=dict(source_version=1, project_address=project_pc,
                          context='real:1000', source_instruction_sha256=source_hash))
        if timed:
            raw['clock'] = deepcopy(observation)
        events.append(raw)
    configuration = dict(cpus=1, clock_profile=machine_clock_configuration('virtual', 1),
                         native_clock_admission={'epoch': 1})
    return dict(version=1, run=dict(run=run), events=events,
        mapping=dict(source_sha256='b' * 64, version_sha256='c' * 64,
                     machine_configuration=configuration,
                     process=dict(source_mapping=dict(static_base=0x10000, runtime_base=0x8000))),
        observation_contract=dict(backend=backend), capture_epoch=run + ':process:1',
        native_process_capture=dict(format='fdisbull-qemu-dos-capture-1',
                                    capture_epoch=run + ':process:1',
                                    source_scope='initial verified DOS module'),
        requested_count=len(events), complete=True)


def compiled(*args, **kwargs):
    result = normalize_trace(trace(*args, **kwargs))
    result['artifact'] = dict(id='artifact-' + result['run'], sha256='d' * 64)
    return result


def replace(value, path, replacement):
    parent = value
    for component in path[:-1]:
        parent = parent[component]
    parent[path[-1]] = replacement


def reseal(state):
    state.pop('state_sha256')
    raw = json.dumps(state, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    state['state_sha256'] = hashlib.sha256(raw).hexdigest()
    return state


def test_clock_bracket_is_copied_and_keeps_distinct_time_and_counter_domains():
    original = clock(ns=9_000_000, icount=7, sequence=4)
    retained = validate_clock(original, run='run-a')
    assert retained == original and retained is not original
    assert retained['virtual_ns'] != retained['icount'] * 128
    retained['before']['icount'] = 99
    assert original['before']['icount'] == 7
    maximum = clock(ns=MAX_NS, icount=MAX_COUNTER, sequence=MAX_NS - 1,
                    native_epoch=MAX_COUNTER)
    assert validate_clock(maximum) == maximum


@pytest.mark.parametrize('path,value', [
    (('extra',), 1), (('format',), 'fdisbull-source-clock-2'),
    (('domain',), 'host-monotonic'), (('run',), ''), (('run',), 'x' * 129),
    (('run',), 'run\nother'), (('epoch',), 'A' * 32), (('epoch',), 'a' * 31),
    (('native_epoch',), 0), (('native_epoch',), True),
    (('native_epoch',), MAX_COUNTER + 1), (('virtual_ns',), -1),
    (('virtual_ns',), MAX_NS + 1), (('virtual_ns',), 128.0),
    (('icount',), True), (('icount',), MAX_COUNTER + 1),
    (('before', 'sequence'), 0), (('before', 'sequence'), True),
    (('after', 'sequence'), 1), (('after', 'sequence'), MAX_NS + 1),
    (('after', 'virtual_ns'), 129), (('before', 'icount'), 2),
    (('after', 'native_epoch'), 2), (('before', 'extra'), 1),
])
def test_malformed_or_unstable_brackets_fail_closed(path, value):
    bad = clock()
    replace(bad, path, value)
    with pytest.raises(ValueError):
        validate_clock(bad)


def test_clock_run_binding_and_observation_sequence_order():
    first = clock()
    with pytest.raises(ValueError, match='owning'):
        validate_clock(first, run='another-run')
    # Time and counters may be equal: a stopped observation is not retirement.
    following = clock(sequence=3)
    assert validate_clock_order(first, following) == following
    assert validate_clock_order(first, first, allow_same=True) == first
    with pytest.raises(ValueError, match='overlap'):
        validate_clock_order(first, first)
    with pytest.raises(ValueError, match='identity'):
        validate_clock_order(first, clock(sequence=3, epoch='f' * 32))
    with pytest.raises(ValueError, match='regressed'):
        validate_clock_order(first, clock(sequence=3, ns=0, icount=2))
    with pytest.raises(ValueError, match='regressed'):
        validate_clock_order(first, clock(sequence=3, ns=256, icount=0))


@pytest.mark.parametrize('updates', [
    {'run': ''}, {'epoch': 'A' * 32}, {'native_epoch': 0},
    {'native_epoch': True}, {'start_ns': True}, {'start_ns': '0x80'},
    {'start_ns': -1}, {'start_ns': 256}, {'end_ns': 128},
    {'end_ns': MAX_NS + 2}, {'start': 128}, {'extra': 1},
])
def test_time_range_has_exact_identity_and_integer_half_open_bounds(updates):
    with pytest.raises(ValueError):
        validate_predicate(dict(predicate(), **updates))


def test_time_range_boundaries_and_missing_or_foreign_clock_are_three_valued():
    event = compiled()['events'][0]
    assert evaluate_predicate(predicate(), event) == {'matched': True, 'unknown': []}
    assert evaluate_predicate(predicate(start_ns=0, end_ns=128), event)['matched'] is False
    assert validate_clock_predicate(predicate(start_ns=MAX_NS, end_ns=MAX_NS + 1))['end_ns'] == 1 << 63
    for foreign in (predicate(run='run-b'), predicate(epoch='b' * 32), predicate(native_epoch=2)):
        assert evaluate_predicate(foreign, event)['matched'] is None
    untimed = compiled(timed=False)['events'][0]
    assert evaluate_predicate(predicate(), untimed)['matched'] is None
    yes = {'kind': 'register', 'register': 'eax', 'equals': 1}
    no = {'kind': 'register', 'register': 'eax', 'equals': 2}
    assert evaluate_predicate({'all': [predicate(), no]}, untimed)['matched'] is False
    assert evaluate_predicate({'any': [predicate(), yes]}, untimed)['matched'] is True
    assert evaluate_predicate({'all': [predicate(), yes]}, untimed)['matched'] is None


def test_clock_predicate_traversal_validates_all_boolean_branches_without_aliasing():
    value = {'any': [dict(kind='mnemonic', equals='nop'),
                     {'all': [predicate(), predicate(run='run-b')]}]}
    found = clock_predicates(value)
    assert found == [predicate(), predicate(run='run-b')]
    found[0]['run'] = 'mutated'
    assert value['any'][1]['all'][0]['run'] == 'run-a'
    assert clock_predicates(None) == []
    with pytest.raises(ValueError):
        clock_predicates({'any': [predicate(), {'kind': 'invented'}]})
    too_deep = predicate()
    for _ in range(9):
        too_deep = {'all': [too_deep]}
    with pytest.raises(ValueError, match='depth'):
        clock_predicates(too_deep)


def test_normalization_retains_clock_and_final_endpoint_without_extra_event():
    values = [clock(), clock(ns=256, icount=2, sequence=3)]
    document = trace(values)
    endpoint = clock(ns=384, icount=3, sequence=5)
    document['collector'] = dict(current_stop=dict(clock=endpoint, registers={'ax': 1}),
                                 outcome='count')
    result = normalize_trace(document)
    assert [event['clock'] for event in result['events']] == values
    assert len(result['events']) == result['window']['requested_count'] == 2
    assert result['collector'] == {'current_stop': {'clock': endpoint}}
    assert result['events'][0]['site']['address'] == 0x10100
    result['events'][0]['clock']['before']['icount'] = 99
    assert document['events'][0]['clock']['before']['icount'] == 1
    document['collector']['current_stop']['clock'] = deepcopy(values[-1])
    assert normalize_trace(document)['collector']['current_stop']['clock'] == values[-1]


@pytest.mark.parametrize('following', [
    clock(sequence=3, ns=127, icount=2), clock(sequence=3, ns=256, icount=0),
    clock(sequence=3, epoch='b' * 32), clock(sequence=3, native_epoch=2),
    clock(sequence=3, run='run-b'), clock(sequence=2),
])
def test_normalization_rejects_clock_discontinuity_independently_of_predicate(following):
    with pytest.raises(ValueError):
        normalize_trace(trace([clock(), following]))


def test_mixed_or_null_clocks_are_rejected_but_older_virtual_and_legacy_rows_survive():
    document = trace([clock(), clock(sequence=3)])
    del document['events'][1]['clock']
    with pytest.raises(ValueError, match='mix'):
        normalize_trace(document)
    document = trace()
    document['events'][0]['clock'] = None
    with pytest.raises(ValueError):
        normalize_trace(document)
    for backend in ('qemu-dos', 'dosbox'):
        result = normalize_trace(trace(timed=False, backend=backend))
        assert 'clock' not in result['events'][0] and 'collector' not in result
        state = start_search(result)
        assert set(search_results(state)['samples'][0]) == {
            'artifact', 'run', 'index', 'sequence', 'sample_index'}
        assert validate_search(json.loads(json.dumps(state))) == state


@pytest.mark.parametrize('change', ['backend', 'cpus', 'cpus-bool', 'profile',
                                  'descriptor-extra', 'descriptor-type', 'admission', 'native-epoch'])
def test_timed_rows_require_exact_native_single_cpu_virtual_admission(change):
    document = trace()
    config = document['mapping']['machine_configuration']
    if change == 'backend':
        document['observation_contract']['backend'] = 'dosbox'
    elif change == 'cpus':
        config['cpus'] = 2
    elif change == 'cpus-bool':
        config['cpus'] = True
    elif change == 'profile':
        config['clock_profile'] = machine_clock_configuration('instruction', 1)
    elif change == 'descriptor-extra':
        config['clock_profile']['extra'] = True
    elif change == 'descriptor-type':
        config['clock_profile']['sleep'] = 0
    elif change == 'admission':
        del config['native_clock_admission']
    else:
        config['native_clock_admission']['epoch'] = 2
    with pytest.raises(ValueError):
        normalize_trace(document)


def test_endpoint_is_validated_even_for_empty_or_incomplete_captures():
    document = trace([clock(), clock(ns=256, icount=2, sequence=3)])
    document['complete'] = False
    for endpoint in (clock(ns=384, icount=3, sequence=2),
                     clock(ns=255, icount=3, sequence=5),
                     clock(ns=384, icount=3, sequence=5, epoch='b' * 32)):
        document['collector'] = dict(current_stop=dict(clock=endpoint))
        with pytest.raises(ValueError):
            normalize_trace(document)
    empty = trace([])
    empty['complete'] = False
    empty['collector'] = dict(current_stop=dict(clock=clock()))
    result = normalize_trace(empty)
    assert not result['events'] and result['collector']['current_stop']['clock'] == clock()
    untimed = trace(timed=False)
    untimed['collector'] = dict(current_stop=dict(clock=clock()))
    with pytest.raises(ValueError, match='clockless'):
        normalize_trace(untimed)


def test_search_candidate_identity_is_time_independent_and_witnesses_keep_each_clock():
    first = compiled()
    second = compiled([clock(run='run-b', epoch='b' * 32, ns=99_999, icount=77)], run='run-b')
    a = start_search(first, predicate=predicate())
    b = start_search(second)
    assert a['candidates'][0]['key'] == b['candidates'][0]['key']
    retained = refine_search(a, second)
    result = search_results(json.loads(json.dumps(retained)))
    assert result['candidate_count'] == 1
    assert result['rows'][0]['support_trials'] == 2
    assert [sample['clock'] for sample in result['samples']] == [
        first['events'][0]['clock'], second['events'][0]['clock']]
    assert [sample['run'] for sample in result['samples']] == ['run-a', 'run-b']
    missing = start_search(first, predicate=predicate(run='run-b'))
    assert missing['candidate_count'] == 0
    assert missing['history'][0]['unknown_observations'] == 1


@pytest.mark.parametrize('change', ['run', 'bracket', 'extra', 'sample-extra'])
def test_resealed_malformed_clock_witness_cannot_be_accepted(change):
    state = start_search(compiled())
    sample = state['samples'][0]
    if change == 'run':
        sample['clock']['run'] = 'foreign-run'
    elif change == 'bracket':
        sample['clock']['after']['icount'] += 1
    elif change == 'extra':
        sample['clock']['claimed_cause'] = 'input'
    else:
        sample['extra'] = True
    with pytest.raises(ValueError):
        validate_search(reseal(state))


def test_search_checks_timed_compiled_rows_even_without_clock_predicate():
    value = compiled([clock(), clock(sequence=3)])
    value['events'][1]['clock']['epoch'] = 'b' * 32
    with pytest.raises(ValueError, match='identity'):
        start_search(value)


def stored_document(project):
    # This existing offline fixture reconstructs COM relocation, source bytes,
    # process ownership and the ordered entry/capture receipts. No live target
    # or patched storage validator is involved.
    from test_qemu_trace_identity import document

    value = document(project)
    value['mapping']['machine_configuration'] = trace()['mapping']['machine_configuration']
    for index, event in enumerate(value['events']):
        event['clock'] = clock(ns=128 * (index + 1), icount=index + 1, sequence=2 * index + 1)
    value['collector'] = dict(current_stop=dict(clock=clock(ns=384, icount=3, sequence=5),
                                               unrelated='not projected'))
    return value


def test_owned_query_returns_count_endpoint_and_search_clocks_after_reopening(tmp_path):
    from fdisbull.project import Project
    from test_qemu_trace_identity import save

    binary = tmp_path / 'SOURCE.COM'
    binary.write_bytes(bytes.fromhex('b801009090ebfe'))
    database = tmp_path / 'source-clock.fdb'
    with Project.create(database, binary, image='com') as project:
        value = stored_document(project)
        artifact = save(project, value)
        selected = predicate(start_ns=128, end_ns=257)
        result = project.event_trace_query(artifact, predicate=selected, limit=1)
        assert result['scanned_events'] == result['matched_count'] == 2
        assert len(result['rows']) == 1 and result['next_offset'] == 1
        assert result['endpoint_clock'] == value['collector']['current_stop']['clock']
        assert 'collector' not in result
        endpoint_only = project.event_trace_query(artifact, predicate=predicate(start_ns=384, end_ns=385))
        assert endpoint_only['matched_count'] == 0
        assert endpoint_only['endpoint_clock'] == result['endpoint_clock']
        search = project.event_search_start(artifact, predicate=selected)['artifact']
        witnesses = project.event_search_results(search)
        assert [sample['clock'] for sample in witnesses['samples']] == [event['clock'] for event in value['events']]
    with Project(database) as project:
        assert project.event_trace_query(artifact, predicate=selected, limit=1) == result
        assert project.event_search_results(search) == witnesses


@pytest.mark.parametrize('change', ['profile', 'cpus', 'epoch', 'receipt'])
def test_owned_trace_clock_requires_retained_run_admission_not_only_artifact_claim(tmp_path, change):
    from fdisbull.project import Project
    from test_qemu_trace_identity import save, update_run

    binary = tmp_path / 'SOURCE.COM'
    binary.write_bytes(bytes.fromhex('b801009090ebfe'))
    with Project.create(tmp_path / 'admission.fdb', binary, image='com') as project:
        value = stored_document(project)
        artifact = save(project, value)
        retained = deepcopy(value['mapping'])
        config = retained['machine_configuration']
        if change == 'profile':
            config['clock_profile'] = machine_clock_configuration('instruction', 1)
        elif change == 'cpus':
            config['cpus'] = 2
        elif change == 'epoch':
            config['native_clock_admission']['epoch'] = 2
        else:
            config['native_clock_admission']['virtual-ns'] = 1
        update_run(project, 'run-a', retained)
        with pytest.raises(ValueError):
            project.event_trace_query(artifact, predicate={'kind': 'mnemonic', 'equals': 'nop'})
