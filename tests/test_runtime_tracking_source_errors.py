"""Source availability is independent from a validated native task lifetime.

These authored provider/session fixtures are not native DESQview evidence.
"""
from copy import deepcopy
import json
import hashlib
import sqlite3

import pytest

from fdisbull.project import Project
from fdisbull.runtime_source_matching import SourceMatchError
from fdisbull.runtime_tracking import RuntimeContainmentError
from test_runtime_tracking import setup, provider_tracker


AMBIGUITY = 'ambiguous source placement within one object'


def test_source_ambiguity_with_valid_native_coverage_withdraws_bindings_and_preserves_episode(
        setup, monkeypatch, tmp_path):
    p, session, match, provider, tracker = provider_tracker(setup, monkeypatch)
    original = tracker.status()['sources'][0]
    task = original['task']
    old_bindings = [row['id'] for row in p.runtime_mappings(task)['bindings']]
    before = dict(generations=deepcopy(tracker.generations), processes=deepcopy(tracker.processes),
                  creations=set(tracker.observed_creations), owners=deepcopy(tracker.task_owners),
                  breakpoints=set(tracker.internal_breakpoints))
    tracker.before_execution('machine-gdb-run')
    captures = len(session.snapshots)

    def ambiguous(_):
        raise SourceMatchError(AMBIGUITY)

    monkeypatch.setattr('fdisbull.runtime_source_matching.discover', ambiguous)
    tracker.after_stop('source evidence ambiguous at completed native stop')
    status = tracker.status()
    assert tracker.provider is provider
    assert tracker.internal_breakpoints == before['breakpoints']
    assert tracker.generations == before['generations']
    assert set(tracker.processes) == set(before['processes'])
    for key, prior in before['processes'].items():
        assert {field: tracker.processes[key][field] for field in
                ('incarnation', 'generation', 'creation_observed', 'native')} == {
            field: prior[field] for field in ('incarnation', 'generation', 'creation_observed', 'native')}
    assert tracker.observed_creations == before['creations']
    assert tracker.task_owners == before['owners']
    assert p._mapping_task(task)['ended'] is None
    assert status['sources'] == [] and status['current_bindings'] == 0
    assert not p.runtime_mappings(task)['bindings']
    assert len(session.snapshots) == captures  # Failed enrichment never replays the native action.
    error = status['errors']['last']
    assert status['errors']['count'] == 1 and status['errors']['recent'] == [error]
    assert error['phase'] == 'source-discovery' and error['type'] == 'SourceMatchError'
    assert error['lifetime_action'] == 'preserved-native-provider'

    monkeypatch.setattr('fdisbull.runtime_source_matching.discover', lambda _: [deepcopy(match)])
    session.physical = 0x970000
    tracker.after_stop('later unambiguous original source stop')
    recovered = tracker.status()
    assert recovered['sources'][0]['task'] == task
    assert recovered['sources'][0]['identity']['process_episode']['incarnation'] == original['identity']['process_episode']['incarnation']
    assert recovered['sources'][0]['identity']['generation'] == original['identity']['generation']
    assert recovered['errors'] == status['errors']
    assert 'error' not in recovered and 'error_type' not in recovered
    current = p.runtime_mappings(task)['bindings']
    assert current and not set(old_bindings).intersection(row['id'] for row in current)
    assert not p.runtime_resolve(task, 0x870ff0, space='physical')['matches']
    assert p.runtime_resolve(task, 0x970ff0, space='physical')['matches']
    tracker.close('authored normal close')

    with Project(p.path) as reopened:
        listed = reopened.debug_artifacts(run=session.run_id)['artifacts']
        errors = [row for row in listed if row['metadata'].get('kind') == 'observation-error']
        assert len(errors) == 1
        artifact = errors[0]
        assert error['reference'] == 'local-runtime-tracking:' + artifact['id']
        assert error['sha256'] == artifact['sha256']
        exported = tmp_path / 'persisted-source-error.json'
        reopened.debug_export(artifact['id'], str(exported))
        record = json.loads(exported.read_text())
        assert record['kind'] == 'observation-error'
        detail = record['document']
        assert detail['phase'] == 'source-discovery'
        assert detail['reason'] == 'source evidence ambiguous at completed native stop'
        assert detail['run'] == session.run_id
        assert detail['error'] == dict(type='SourceMatchError', module='fdisbull.runtime_source_matching',
                                       message=AMBIGUITY, causes=[])
        assert detail['lifetime_action'] == 'preserved-native-provider'
        assert task in detail['task_incarnations']
        assert detail['process_episodes']


@pytest.mark.parametrize('failure', ['fingerprint', 'missing-hook', 'changed-hook', 'changed-cpu'])
def test_source_ambiguity_cannot_preserve_unverified_native_coverage(setup, monkeypatch, failure):
    p, session, _, provider, tracker = provider_tracker(setup, monkeypatch)
    task = tracker.status()['sources'][0]['task']
    tracker.before_execution('machine-gdb-run')
    owned = next(iter(tracker.internal_breakpoints))
    if failure == 'fingerprint':
        provider.fingerprint_failure = True
    elif failure == 'missing-hook':
        session.breakpoints.pop(owned)
    elif failure == 'changed-hook':
        session.breakpoints[owned]['address'] += 1

    def ambiguous(_):
        if failure == 'changed-cpu':
            session.registers = lambda: dict(authored_stopped_cpu=True, changed_context=True)
        raise SourceMatchError(AMBIGUITY)

    monkeypatch.setattr('fdisbull.runtime_source_matching.discover', ambiguous)
    tracker.after_stop('ambiguity without complete stopped coverage')
    assert tracker.provider is None and not tracker.internal_breakpoints
    assert p._mapping_task(task)['ended'] is not None
    assert not p.runtime_mappings(task)['bindings']
    assert tracker.status()['sources'] == [] and tracker.status()['current_bindings'] == 0
    assert tracker.status()['errors']['count'] >= 1


def test_source_only_ambiguity_never_joins_a_later_execution_episode(setup, monkeypatch):
    p, session, match = setup
    session.metadata['capabilities']['lifecycle']['dos_guest_exit'] = False
    from fdisbull.runtime_tracking import AutomaticRuntimeTracker
    tracker = AutomaticRuntimeTracker(session)
    tracker.after_stop('one stopped source observation')
    task = tracker.status()['sources'][0]['task']
    tracker.before_execution('machine-gdb-run')

    def ambiguous(_):
        raise SourceMatchError(AMBIGUITY)

    monkeypatch.setattr('fdisbull.runtime_source_matching.discover', ambiguous)
    tracker.after_stop('source-only ambiguous stop')
    assert tracker.provider is None
    assert p._mapping_task(task)['ended'] is not None
    assert not tracker.status()['task_incarnations']
    assert tracker.status()['sources'] == [] and tracker.status()['current_bindings'] == 0
    monkeypatch.setattr('fdisbull.runtime_source_matching.discover', lambda _: [deepcopy(match)])
    tracker.after_stop('later source-only observation')
    assert tracker.status()['sources'][0]['task'] != task
    assert tracker.status()['lifetime_qualification'] == 'one-stop-only'
    assert tracker.status()['errors']['count'] == 1


def test_unexpected_discovery_io_still_retires_native_episode(setup, monkeypatch):
    p, _, _, _, tracker = provider_tracker(setup, monkeypatch)
    task = tracker.status()['sources'][0]['task']
    tracker.before_execution('machine-gdb-run')

    def failed_read(_):
        raise OSError('authored native read transport unavailable')

    monkeypatch.setattr('fdisbull.runtime_source_matching.discover', failed_read)
    tracker.after_stop('failed native read')
    assert tracker.provider is None and p._mapping_task(task)['ended'] is not None
    assert not p.runtime_mappings(task)['bindings']
    assert tracker.status()['sources'] == [] and tracker.status()['current_bindings'] == 0
    assert tracker.status()['errors']['last']['type'] == 'OSError'


def test_partial_mapping_publication_is_withdrawn_and_not_replayed(setup, monkeypatch):
    p, session, _, _, tracker = provider_tracker(setup, monkeypatch)
    task = tracker.status()['sources'][0]['task']
    tracker.before_execution('machine-gdb-run')
    original = p.runtime_map_snapshot
    calls = []
    captures = len(session.snapshots)

    def fail_second_fragment(*args, **kwargs):
        calls.append((args, kwargs))
        if len(calls) == 2:
            raise OSError('authored second mapping journal failure')
        return original(*args, **kwargs)

    monkeypatch.setattr(p, 'runtime_map_snapshot', fail_second_fragment)
    tracker.after_stop('partly published observation')
    assert len(calls) == 2 and len(session.snapshots) == captures + 1
    assert not p.runtime_mappings(task)['bindings']
    assert p._mapping_task(task)['ended'] is not None and tracker.provider is None
    assert tracker.status()['sources'] == [] and tracker.status()['current_bindings'] == 0
    assert tracker.status()['errors']['last']['type'] == 'OSError'


@pytest.mark.parametrize('reason', ['resume', 'state.load', 'memory.write', 'parent execution'])
def test_preserved_source_error_does_not_override_explicit_coverage_gap(setup, monkeypatch, reason):
    p, _, _, _, tracker = provider_tracker(setup, monkeypatch)
    task = tracker.status()['sources'][0]['task']
    tracker.before_execution('machine-gdb-run')

    def ambiguous(_):
        raise SourceMatchError(AMBIGUITY)

    monkeypatch.setattr('fdisbull.runtime_source_matching.discover', ambiguous)
    tracker.after_stop('ambiguous source; native monitor remains qualified')
    assert p._mapping_task(task)['ended'] is None
    tracker.before_execution(reason)
    assert p._mapping_task(task)['ended'] is not None
    assert tracker.provider is None and not tracker.internal_breakpoints
    assert tracker.status()['errors']['count'] == 1


def test_error_history_recent_window_is_bounded_but_artifacts_are_append_only(setup, monkeypatch, tmp_path):
    p, session, match, _, tracker = provider_tracker(setup, monkeypatch)
    task = tracker.status()['sources'][0]['task']
    tracker.before_execution('machine-gdb-run')

    def ambiguous(_):
        try:
            raise ValueError('authored candidate multiplicity')
        except ValueError as cause:
            raise SourceMatchError(AMBIGUITY) from cause

    monkeypatch.setattr('fdisbull.runtime_source_matching.discover', ambiguous)
    for i in range(20):
        tracker.after_stop('ambiguous stopped observation ' + str(i))
    history = tracker.status()['errors']
    assert history['count'] == 20 and len(history['recent']) == 16
    assert history['last'] == history['recent'][-1]
    assert len({row['reference'] for row in history['recent']}) == 16
    assert p._mapping_task(task)['ended'] is None
    monkeypatch.setattr('fdisbull.runtime_source_matching.discover', lambda _: [deepcopy(match)])
    tracker.after_stop('later successful source observation')
    assert tracker.status()['sources'][0]['task'] == task
    assert tracker.status()['errors'] == history
    tracker.close('ordinary authored close')
    with Project(p.path) as reopened:
        errors = [row for row in reopened.debug_artifacts(run=session.run_id)['artifacts']
                  if row['metadata'].get('kind') == 'observation-error']
        assert len(errors) == 20
        expected_recent = [dict(reference='local-runtime-tracking:' + row['id'], sha256=row['sha256'],
            phase='source-discovery', type='SourceMatchError', lifetime_action='preserved-native-provider')
            for row in errors[-16:]]
        assert history['recent'] == expected_recent
        assert history['last'] == expected_recent[-1]
        for i, row in enumerate(errors):
            target = tmp_path / ('error-' + str(i) + '.json')
            reopened.debug_export(row['id'], str(target))
            detail = json.loads(target.read_text())['document']
            assert detail['reason'] == 'ambiguous stopped observation ' + str(i)
            assert detail['error']['message'] == AMBIGUITY
            assert detail['error']['causes'] == [dict(type='ValueError', module='builtins',
                message='authored candidate multiplicity')]
            assert detail['lifetime_action'] == 'preserved-native-provider'


@pytest.mark.parametrize('failure', ['session-artifact', 'sqlite-write'])
def test_error_recording_failure_permanently_fences_without_claiming_durable_closure(
        setup, monkeypatch, failure):
    p, session, _, _, tracker = provider_tracker(setup, monkeypatch)
    task = tracker.status()['sources'][0]['task']
    tracker.before_execution('machine-gdb-run')
    captures = len(session.snapshots)

    def ambiguous(_):
        raise SourceMatchError(AMBIGUITY)

    monkeypatch.setattr('fdisbull.runtime_source_matching.discover', ambiguous)
    original_artifact = session._artifact
    attempts = []
    if failure == 'session-artifact':
        def fail_record(name, kind, data, metadata):
            attempts.append(metadata['kind'])
            raise OSError('authored error-artifact storage unavailable')
        monkeypatch.setattr(session, '_artifact', fail_record)
        expected_error = OSError
    else:
        def deny_artifact_insert(operation, table, column, database, trigger):
            if operation == sqlite3.SQLITE_INSERT and table == 'debug_artifacts':
                attempts.append('denied-sqlite-insert')
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        p.db.set_authorizer(deny_artifact_insert)
        expected_error = sqlite3.DatabaseError
    try:
        with pytest.raises(expected_error):
            tracker.after_stop('completed native action; error history write failed')
        status = tracker.status()
        assert status['fenced'] is True and status['state'] == 'fenced'
        assert status['current_bindings'] is None and status['sources'] == []
        assert status['errors']['count'] == 0 and status['errors']['last'] is None
        assert status['errors']['recent'] == []
        unrecorded = status['errors']['unrecorded']
        assert unrecorded['phase'] == 'source-discovery'
        assert unrecorded['error']['type'] == 'SourceMatchError'
        assert unrecorded['error']['message'] == AMBIGUITY
        assert unrecorded['recording_error']['type'] in ('OSError', 'DatabaseError')
        assert p._mapping_task(task)['ended'] is None  # No invented durable END event.
        assert len(session.snapshots) == captures and len(attempts) == 1
        with pytest.raises(RuntimeContainmentError, match='fenced'):
            tracker.before_execution('machine-gdb-run')
        assert len(attempts) == 1  # A rejected dispatch does not retry a write or guest action.
    finally:
        p.db.set_authorizer(None)
        monkeypatch.setattr(session, '_artifact', original_artifact)
    errors = [row for row in p.debug_artifacts(run=session.run_id)['artifacts']
              if row['metadata'].get('kind') == 'observation-error']
    assert not errors
    tracker.close('recovered journal permits final retirement')
    assert p._mapping_task(task)['ended'] is not None
    assert tracker.status()['closed'] and tracker.status()['fenced']
    with pytest.raises(RuntimeContainmentError, match='fenced'):
        tracker.before_execution('even a closed fenced tracker cannot dispatch')


def test_before_execution_coverage_error_is_retained_after_later_source_success(setup, monkeypatch):
    p, _, _, provider, tracker = provider_tracker(setup, monkeypatch)
    old = tracker.status()['sources'][0]['task']
    provider.fingerprint_failure = True
    tracker.before_execution('machine-gdb-run')
    history = tracker.status()['errors']
    assert history['count'] == 1
    assert history['last']['phase'] == 'native-coverage-before-execution'
    assert history['last']['type'] == 'ValueError'
    assert history['last']['lifetime_action'] == 'retire-continuity'
    assert p._mapping_task(old)['ended'] is not None and tracker.provider is None
    provider.fingerprint_failure = False
    tracker.after_stop('later independently qualified source stop')
    assert tracker.status()['sources'][0]['task'] != old
    assert tracker.status()['errors'] == history
    assert 'error' not in tracker.status()


def test_long_error_message_and_cause_chain_have_explicit_finite_storage_bounds(setup, monkeypatch, tmp_path):
    p, session, _, _, tracker = provider_tracker(setup, monkeypatch)
    tracker.before_execution('machine-gdb-run')
    message = 'authored ambiguity ' + 'x' * 9000
    error = SourceMatchError(message)
    causes = [ValueError('authored cause ' + str(i)) for i in range(6)]
    error.__cause__ = causes[0]
    for left, right in zip(causes, causes[1:]):
        left.__cause__ = right
    def ambiguous(_):
        raise error
    monkeypatch.setattr('fdisbull.runtime_source_matching.discover', ambiguous)
    tracker.after_stop('bounded diagnostic content')
    artifact = tracker.status()['errors']['last']['reference'].split(':', 1)[1]
    target = tmp_path / 'bounded-error.json'
    p.debug_export(artifact, str(target))
    detail = json.loads(target.read_text())['document']['error']
    assert detail['message'] == message[:8192] and detail['message_truncated'] is True
    assert detail['complete_message_sha256'] == hashlib.sha256(message.encode()).hexdigest()
    assert detail['causes'] == [dict(type='ValueError', module='builtins', message='authored cause ' + str(i))
                                for i in range(4)]


def test_before_execution_invalidation_failure_records_original_error_and_fences_before_dispatch(
        setup, monkeypatch, tmp_path):
    p, session, _, _, tracker = provider_tracker(setup, monkeypatch)
    task = tracker.status()['sources'][0]['task']
    before = p.runtime_mappings(task)['bindings']
    captures = len(session.snapshots)
    original_unmap = p.runtime_unmap
    calls = []
    failure = OSError('authored binding invalidation journal unavailable')

    def unavailable(*args, **kwargs):
        calls.append((args, kwargs))
        raise failure

    monkeypatch.setattr(p, 'runtime_unmap', unavailable)
    with pytest.raises(OSError) as caught:
        tracker.before_execution('machine-gdb-run')
    assert caught.value is failure
    status = tracker.status()
    assert status['fenced'] is True and status['current_bindings'] is None
    assert status['sources'] == []
    assert len(calls) == 1 and len(session.snapshots) == captures
    # SQLite rolled back the failed unmap. Neither status nor the error record
    # may pretend that these current journal intervals were durably closed.
    assert p.runtime_mappings(task)['bindings'] == before
    assert p._mapping_task(task)['ended'] is None
    history = status['errors']
    assert history['count'] == 1
    assert history['last']['phase'] == 'binding-invalidation-before-execution'
    assert history['last']['type'] == 'OSError'
    assert history['last']['lifetime_action'] == 'fence-before-dispatch'
    artifact = history['last']['reference'].split(':', 1)[1]
    target = tmp_path / 'pre-dispatch-invalidation-error.json'
    p.debug_export(artifact, str(target))
    detail = json.loads(target.read_text())['document']
    assert detail['phase'] == 'binding-invalidation-before-execution'
    assert detail['error'] == dict(type='OSError', module='builtins',
        message='authored binding invalidation journal unavailable', causes=[])
    assert detail['lifetime_action'] == 'fence-before-dispatch'
    assert task in detail['task_incarnations']
    with pytest.raises(RuntimeContainmentError, match='fenced'):
        tracker.before_execution('machine-gdb-run')
    assert len(calls) == 1  # No second journal attempt or native dispatch.
    monkeypatch.setattr(p, 'runtime_unmap', original_unmap)
    tracker.close('journal recovered; owner closes without another dispatch')
    assert tracker.status()['fenced'] and p._mapping_task(task)['ended'] is not None
    assert not p.runtime_mappings(task)['bindings']


def test_coverage_failure_followed_by_failed_retirement_cannot_resurrect_old_episode(
        setup, monkeypatch):
    p, session, _, provider, tracker = provider_tracker(setup, monkeypatch)
    task = tracker.status()['sources'][0]['task']
    original_end = p.runtime_task_end
    calls = []
    captures = len(session.snapshots)
    failure = OSError('authored task-retirement journal unavailable')
    def fail_retirement(*args, **kwargs):
        calls.append((args, kwargs))
        raise failure
    monkeypatch.setattr(p, 'runtime_task_end', fail_retirement)
    provider.fingerprint_failure = True
    with pytest.raises(OSError) as caught:
        tracker.before_execution('machine-gdb-run')
    assert caught.value is failure and len(calls) == 1
    status = tracker.status()
    assert status['fenced'] is True and status['current_bindings'] is None
    assert status['sources'] == [] and p._mapping_task(task)['ended'] is None
    assert status['errors']['count'] == 1
    assert status['errors']['last']['phase'] == 'native-coverage-before-execution'
    pending = status['errors']['unrecorded']
    assert pending['phase'] == 'lifetime-retirement-before-execution'
    assert pending['error']['type'] == 'ValueError'
    assert pending['retirement_error']['type'] == 'OSError'
    assert pending['retirement_error']['message'] == str(failure)
    # A subsequently matching fingerprint cannot erase a previously observed
    # coverage failure whose lifetime retirement was not durably committed.
    provider.fingerprint_failure = False
    monkeypatch.setattr(p, 'runtime_task_end', original_end)
    with pytest.raises(RuntimeContainmentError, match='fenced'):
        tracker.before_execution('machine-gdb-run')
    tracker.after_stop('later bytes cannot revive a fenced episode')
    assert len(calls) == 1 and len(session.snapshots) == captures
    assert tracker.status()['sources'] == []
    tracker.close('recovered journal permits owner retirement only')
    assert tracker.status()['closed'] and tracker.status()['fenced']
    assert p._mapping_task(task)['ended'] is not None
