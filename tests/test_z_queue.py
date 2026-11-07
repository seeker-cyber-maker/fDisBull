import json

import pytest

from fdisbull.z_queue import DependencyQueue


def test_facts_release_only_dependents_and_false_values_are_available(tmp_path):
    queue = DependencyQueue.load(tmp_path / 'work.json')
    queue.add_task('native-load', requires=['reader', 'scene'], produces=['loaded'])
    queue.add_task('record-census', requires=['file'], produces=['rows'],
                   operation={'verb': 'record-rows', 'params': {'stride': 68}}, priority=3)
    queue.publish('file', False, 'save-inventory.json')
    assert [task['id'] for task in queue.ready()] == ['record-census']
    queue.claim('record-census')
    queue.complete('record-census', {'rows': {'value': {'complete': True}, 'evidence': 'rows.json'}})
    summary = DependencyQueue.load(tmp_path / 'work.json').summary()
    assert summary['task_counts'] == {'completed': 1, 'pending': 1}
    assert summary['tasks'][0]['missing'] == ['reader', 'scene']
    assert not summary['ready']


def test_failed_branch_never_retries_implicitly_and_partial_facts_remain_useful():
    queue = DependencyQueue()
    queue.add_task('observe', produces=['filename', 'boundary'])
    queue.add_task('parse', requires=['filename'])
    queue.claim('observe')
    queue.publish('filename', 'actors.dat', 'observation-1')
    queue.fail('observe', 'UI route unavailable')
    assert [task['id'] for task in queue.ready()] == ['parse']
    queue.claim('parse')
    queue.complete('parse')
    assert queue.summary()['task_counts'] == {'failed': 1, 'completed': 1}
    queue.retry('observe')
    assert [task['id'] for task in queue.ready()] == ['observe']


def test_completion_requires_every_output_and_invalid_batch_is_atomic(tmp_path):
    path = tmp_path / 'work.json'
    queue = DependencyQueue(path)
    queue.add_task('capture', produces=['entry', 'return'])
    queue.claim('capture')
    before = path.read_bytes()
    with pytest.raises(ValueError, match='output facts'):
        queue.complete('capture', {'entry': {'value': 123, 'evidence': 'hit-1'}})
    assert path.read_bytes() == before and 'entry' not in queue.snapshot()['facts']
    queue.publish('entry', 123, 'hit-1')
    with pytest.raises(ValueError, match='output facts'):
        queue.complete('capture')
    queue.complete('capture', {'return': {'value': 128, 'evidence': 'hit-2'}})
    assert queue.summary()['task_counts'] == {'completed': 1}


def test_changed_input_invalidates_transitive_outputs_and_running_claim():
    queue = DependencyQueue()
    queue.add_task('reader', requires=['code'], produces=['buffer'])
    queue.add_task('rows', requires=['buffer'], produces=['census'])
    queue.add_task('hud', requires=['census'], produces=['label'])
    queue.add_task('unrelated', produces=['independent'])
    queue.publish('code', {'version': 1}, 'source-1')
    queue.claim('reader')
    queue.complete('reader', {'buffer': {'value': 123, 'evidence': 'reader-1'}})
    queue.claim('rows')
    queue.complete('rows', {'census': {'value': 250, 'evidence': 'rows-1'}})
    queue.claim('hud')
    queue.publish('code', {'version': 2}, 'source-2')
    state = queue.snapshot()
    assert set(state['facts']) == {'code'}
    assert {ident: task['status'] for ident, task in state['tasks'].items()} == {
        'reader': 'pending', 'rows': 'pending', 'hud': 'failed', 'unrelated': 'pending'}
    assert state['tasks']['hud']['reason'] == 'inputs_changed_during_operation'
    assert [task['id'] for task in queue.ready()] == ['reader', 'unrelated']
    with pytest.raises(ValueError, match='running'):
        queue.complete('hud', {'label': {'value': 'Health', 'evidence': 'stale-frame'}})


def test_changed_input_removes_failed_task_outputs_without_retrying_it():
    queue = DependencyQueue()
    queue.add_task('partial', requires=['input'], produces=['part'])
    queue.publish('input', 1, 'input-1')
    queue.claim('partial')
    queue.publish('part', 8, 'partial-1')
    queue.fail('partial', 'missing continuation')
    queue.publish('input', 2, 'input-2')
    assert set(queue.snapshot()['facts']) == {'input'}
    assert queue.snapshot()['tasks']['partial']['status'] == 'failed'
    assert queue.ready() == []


def test_same_value_new_evidence_preserves_claim_but_false_to_zero_invalidates():
    queue = DependencyQueue()
    queue.add_task('probe', requires=['state'])
    queue.publish('state', {'b': False, 'a': 1}, 'frame-1')
    queue.claim('probe')
    revision = queue.snapshot()['facts']['state']['revision']
    queue.publish('state', {'a': 1, 'b': False}, 'frame-2')
    assert queue.snapshot()['facts']['state']['revision'] == revision
    queue.complete('probe')
    queue.publish('state', {'a': 1, 'b': 0}, 'frame-3')
    assert queue.snapshot()['tasks']['probe']['status'] == 'pending'


def test_cycle_duplicate_producer_and_existing_fact_adoption_rejected_atomically():
    queue = DependencyQueue()
    queue.add_task('first', requires=['second-value'], produces=['first-value'])
    before = queue.snapshot()
    with pytest.raises(ValueError, match='cycle'):
        queue.add_task('second', requires=['first-value'], produces=['second-value'])
    assert queue.snapshot() == before
    with pytest.raises(ValueError, match='one producer'):
        queue.add_task('duplicate', produces=['first-value'])
    with pytest.raises(ValueError, match='already exists'):
        queue.add_task('first')
    queue.publish('known', 1, 'known-artifact')
    with pytest.raises(ValueError, match='already published'):
        queue.add_task('adopt', produces=['known'])


def test_restart_never_replays_operation_and_claim_requires_explicit_recovery(tmp_path):
    path = tmp_path / 'queue.json'
    queue = DependencyQueue(path)
    queue.add_task('save', operation={'verb': 'native-save', 'params': {'slot': 1}})
    queue.claim('save')
    restarted = DependencyQueue.load(path)
    assert restarted.ready() == []
    assert restarted.summary()['task_counts'] == {'running': 1}
    restarted.retry('save')
    assert restarted.ready()[0]['operation'] == {'verb': 'native-save', 'params': {'slot': 1}}
    restarted.claim('save')
    restarted.complete('save')


def test_failed_save_preserves_previous_file_and_in_memory_state(tmp_path, monkeypatch):
    path = tmp_path / 'queue.json'
    queue = DependencyQueue(path)
    queue.publish('first', 1, 'one')
    before = path.read_bytes()
    state = queue.snapshot()
    from pathlib import Path
    original = Path.replace
    def fail(source, destination):
        if destination == path:
            raise OSError('write interrupted')
        return original(source, destination)
    monkeypatch.setattr(Path, 'replace', fail)
    with pytest.raises(OSError, match='interrupted'):
        queue.publish('second', 2, 'two')
    assert path.read_bytes() == before and queue.snapshot() == state
    assert sorted(p.name for p in tmp_path.iterdir()) == ['queue.json']


def test_invalid_nonfinite_or_wrong_producer_never_mutates_queue():
    queue = DependencyQueue()
    queue.add_task('capture', produces=['entry'])
    before = queue.snapshot()
    for value in (float('nan'), {'amount': float('inf')}):
        with pytest.raises(ValueError):
            queue.publish('entry', value, 'artifact')
    with pytest.raises(ValueError, match='producer'):
        queue.publish('entry', 8, 'artifact', producer='some-other-task')
    with pytest.raises(ValueError, match='evidence'):
        queue.publish('entry', 8, '')
    assert queue.snapshot() == before


def test_load_rejects_malformed_completed_state(tmp_path):
    path = tmp_path / 'queue.json'
    queue = DependencyQueue(path)
    queue.add_task('parse', produces=['rows'])
    state = queue.snapshot()
    state['tasks']['parse'].update(status='completed', claimed_inputs={})
    path.write_text(json.dumps(state))
    with pytest.raises(ValueError, match='missing its declared output'):
        DependencyQueue.load(path)


def test_load_rejects_completed_task_with_stale_input_revision(tmp_path):
    path = tmp_path / 'queue.json'
    queue = DependencyQueue(path)
    queue.add_task('parse', requires=['file'])
    queue.publish('file', 'records-1.json', 'records-1.json')
    queue.claim('parse')
    queue.complete('parse')
    state = queue.snapshot()
    state['facts']['file']['revision'] += 1
    state['revision'] += 1
    path.write_text(json.dumps(state))
    with pytest.raises(ValueError, match='claimed input revisions'):
        DependencyQueue.load(path)


def test_ready_priority_order_and_snapshot_are_detached():
    queue = DependencyQueue()
    queue.add_task('later', priority=0)
    queue.add_task('first', priority=4)
    queue.add_task('second', priority=4)
    assert [task['id'] for task in queue.ready()] == ['first', 'second', 'later']
    view = queue.ready()
    view[0]['status'] = 'completed'
    raw = queue.snapshot()
    raw['tasks']['first']['status'] = 'failed'
    assert queue.summary()['task_counts'] == {'pending': 3}


def test_history_is_bounded_and_full_results_should_be_artifact_references():
    queue = DependencyQueue()
    for value in range(80):
        queue.publish('capture', {'path': f'capture-{value}.json'}, f'capture-{value}.json')
    assert len(queue.snapshot()['history']) == 64
    before = queue.snapshot()
    with pytest.raises(ValueError, match='exceeds 2 MiB'):
        queue.publish('raw-game-world', 'x' * (2 * 1024 * 1024), 'unnecessarily-large')
    assert queue.snapshot() == before
