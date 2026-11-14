"""Authored provider readbacks exercise publication, not native qualification."""
from copy import deepcopy
import hashlib
import json

import pytest

from fdisbull.memory_search_runtime import _artifact, _snapshot
from fdisbull.project import Project
from test_runtime_mapping_snapshots import capture
from test_runtime_tracking import provider_tracker, setup


def _sha(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, sort_keys=True, separators=(',', ':'),
                           allow_nan=False).encode()
    return hashlib.sha256(value).hexdigest()


def _certificate(project, snapshot, native):
    """Author the provider boundary response from a real sealed snapshot."""
    from fdisbull.runtime_desqview_physical import FORMAT, SCOPE

    row, data, metadata = _snapshot(project, snapshot)
    context = metadata['snapshot']['context']
    pages = metadata['capture']['pages']
    start = cursor = context['region']['start']
    end = start + len(data)
    ranges = []
    while cursor < end:
        page = next(page for page in pages
                    if int(page['linear'], 16) == cursor & ~4095)
        count = min(end - cursor, 4096 - (cursor & 4095))
        ranges.append(dict(linear_start=cursor,
            physical_start=int(page['physical'], 16) + (cursor & 4095),
            length=count, sha256=_sha(data[cursor - start:cursor - start + count])))
        cursor += count
    return dict(format=FORMAT, qualified=True, snapshot=snapshot,
        snapshot_sha256=row['sha256'], mapping_id=context['mapping_id'],
        context_sha256=_sha(context), native_identity_sha256=_sha(native),
        ranges=ranges, passes=2, verification_scope=SCOPE)


def _recorded(project, evidence):
    reference = evidence['reference']
    prefix = 'local-runtime-tracking:'
    assert evidence['kind'] == 'recorded' and reference.startswith(prefix)
    row, raw, metadata = _artifact(project, reference[len(prefix):], 'runtime-tracking')
    assert row['sha256'] == evidence['sha256'] == _sha(raw)
    return json.loads(raw), metadata


def _two_spans(project, session, match, monkeypatch):
    """Two real captures let the second readback fail after a first publication."""
    match['source_spans'] = [
        dict(name='tail', address=0x123ff0, length=16,
             object_id='region:0', object_offset=0),
        dict(name='head', address=0x124000, length=16,
             object_id='region:0', object_offset=16),
    ]

    def snapshot(address, *, length, task_id, name):
        span = next(span for span in match['source_spans'] if span['address'] == address)
        assert length == span['length']
        offset = span['object_offset']
        raw = project.regions(1)[0].data[offset:offset + length]
        pages = [dict(linear='0x123000', physical=hex(session.physical), entries=[]),
                 dict(linear='0x124000', physical=hex(session.physical + 0x3000), entries=[])]
        pages = [page for page in pages if int(page['linear'], 16) == address & ~4095]
        identifier = capture(project, raw, start=address, task=task_id, pages=pages,
                             epoch=session._runtime_epoch)
        session.snapshots.append(identifier)
        return dict(artifact=identifier)

    monkeypatch.setattr(session, 'memory_snapshot', snapshot)


def test_physical_readback_precedes_mapping_and_remap_keeps_episode(setup, monkeypatch):
    project, session, _, provider, tracker = provider_tracker(setup, monkeypatch)
    initial = tracker.status()['sources'][0]
    task = initial['task']
    episode = deepcopy(initial['identity']['process_episode'])
    calls = []
    proofs = {}
    original_snapshot = session.memory_snapshot
    original_map = project.runtime_map_snapshot

    def snapshot(*args, **kwargs):
        result = original_snapshot(*args, **kwargs)
        calls.append(('snapshot', result['artifact']))
        return result

    def qualify(identifier, native):
        assert calls[-1] == ('snapshot', identifier)
        assert native == provider.current_identity()
        calls.append(('qualify', identifier))
        proof = proofs[identifier] = _certificate(project, identifier, native)
        return proof

    def map_snapshot(*args, **kwargs):
        identifier = args[1]
        calls.append(('map', identifier))
        # The independent registry must receive a durably recorded proof,
        # rather than a flag copied from the provider's return value.
        receipt = kwargs.get('physical_readback')
        assert receipt is not None
        document, metadata = _recorded(project, receipt['evidence'])
        assert document['kind'] == metadata['kind'] == 'physical-qualification'
        assert document['document'] == receipt['certificate'] == proofs[identifier]
        return original_map(*args, **kwargs)

    monkeypatch.setattr(session, 'memory_snapshot', snapshot)
    monkeypatch.setattr(provider, 'qualify_physical', qualify, raising=False)
    monkeypatch.setattr(project, 'runtime_map_snapshot', map_snapshot)
    tracker.after_stop('authored physical observation')
    assert [kind for kind, _ in calls] == ['snapshot', 'qualify', 'map', 'map']
    source = tracker.status()['sources'][0]
    assert source['task'] == task and source['identity']['process_episode'] == episode
    snapshot_id = calls[0][1]
    assert source['physical_qualification']['qualified'] is True
    assert source['physical_qualification']['snapshots'] == [snapshot_id]
    first = project.runtime_mappings(task)['bindings']
    assert [binding['physical_start'] for binding in first] == [0x870ff0, 0x873000]
    assert [binding['length'] for binding in first] == [16, 16]
    for binding in first:
        proof = binding['physical_qualification']
        assert proof['qualified'] is True and proof['snapshot'] == snapshot_id
        assert proof['passes'] == 2 and proof['certificate_sha256'] == _sha(proofs[snapshot_id])
        assert (proof['linear_start'], proof['physical_start'], proof['length']) == (
            binding['linear_start'], binding['physical_start'], binding['length'])
        assert _recorded(project, proof['evidence'])[0]['document'] == proofs[snapshot_id]
    at = project.runtime_mapping_events(task)['events'][-1]['sequence']

    calls.clear()
    tracker.before_execution('machine-gdb-run')
    assert not project.runtime_mappings(task)['bindings']
    session.physical = 0x970000
    tracker.after_stop('same task, new physical pages')
    assert [kind for kind, _ in calls] == ['snapshot', 'qualify', 'map', 'map']
    source = tracker.status()['sources'][0]
    assert source['task'] == task and source['identity']['process_episode'] == episode
    assert source['identity']['generation'] == initial['identity']['generation']
    second = project.runtime_mappings(task)['bindings']
    assert [binding['physical_start'] for binding in second] == [0x970ff0, 0x973000]
    assert all(binding['physical_qualification']['snapshot'] != snapshot_id for binding in second)
    assert not project.runtime_resolve(task, 0x870ff0, space='physical')['matches']
    assert project.runtime_resolve(task, 0x870ff0, space='physical', at=at)['matches']
    with Project(project.path) as reopened:
        assert reopened.runtime_mappings(task)['bindings'] == second
        historical = reopened.runtime_mappings(task, at=at)['bindings']
        assert all(binding['closed'] is not None for binding in historical)
        assert [dict(binding, closed=None) for binding in historical] == first


def test_provider_without_physical_method_never_upgrades_snapshot_mappings(setup, monkeypatch):
    project, _, _, provider, tracker = provider_tracker(setup, monkeypatch)
    assert not hasattr(provider, 'qualify_physical')
    source = tracker.status()['sources'][0]
    assert source['physical_qualification']['qualified'] is False
    assert source['physical_qualification']['snapshots'] == []
    bindings = project.runtime_mappings(source['task'])['bindings']
    assert bindings and all('physical_qualification' not in binding for binding in bindings)


def test_physical_certificate_record_failure_retires_without_replaying(setup, monkeypatch):
    project, session, _, provider, tracker = provider_tracker(setup, monkeypatch)
    task = tracker.status()['sources'][0]['task']
    captured = len(session.snapshots)
    qualified = []
    failed_records = []
    original_artifact = session._artifact

    def qualify(identifier, native):
        qualified.append(identifier)
        return _certificate(project, identifier, native)

    def artifact(name, kind, raw, metadata):
        if metadata.get('kind') == 'physical-qualification' and not failed_records:
            failed_records.append(metadata['kind'])
            raise OSError('authored physical-certificate journal write failed')
        return original_artifact(name, kind, raw, metadata)

    monkeypatch.setattr(provider, 'qualify_physical', qualify, raising=False)
    monkeypatch.setattr(session, '_artifact', artifact)
    tracker.after_stop('completed action; physical evidence could not be recorded')
    status = tracker.status()
    assert status['state'] == 'unqualified' and not status['fenced']
    assert status['current_bindings'] == 0 and status['sources'] == []
    assert not project.runtime_mappings(task)['bindings']
    assert project._mapping_task(task)['ended'] is not None
    assert tracker.provider is None and not session.breakpoints
    assert failed_records == ['physical-qualification']
    assert len(session.snapshots) - captured == len(qualified) == 1
    # Error publication succeeds after the single failed certificate write;
    # it durably retires continuity instead of replaying or recapturing input.
    error = status['errors']['last']
    assert error['type'] == 'OSError' and error['lifetime_action'] == 'retire-continuity'
    document, _ = _recorded(project, dict(kind='recorded',
        reference=error['reference'], sha256=error['sha256']))
    assert document['document']['error']['message'] == 'authored physical-certificate journal write failed'


@pytest.mark.parametrize('failed_snapshot', [1, 2])
def test_physical_miss_rolls_back_partial_maps_but_recovers_same_episode(
        setup, monkeypatch, failed_snapshot):
    from fdisbull.runtime_desqview_physical import DesqviewPhysicalError

    project, session, match, provider, tracker = provider_tracker(setup, monkeypatch)
    original = tracker.status()['sources'][0]
    task = original['task']
    hooks = deepcopy(session.breakpoints)
    _two_spans(project, session, match, monkeypatch)
    attempted = []
    miss = True

    def qualify(identifier, native):
        attempted.append(identifier)
        if miss and len(attempted) == failed_snapshot:
            raise DesqviewPhysicalError('authored physical readback differs on pass two')
        return _certificate(project, identifier, native)

    monkeypatch.setattr(provider, 'qualify_physical', qualify, raising=False)
    captured = len(session.snapshots)
    tracker.after_stop('performed action; physical enrichment failed')
    status = tracker.status()
    assert status['state'] == 'physical-unavailable'
    assert status['current_bindings'] == 0 and status['sources'] == []
    assert not project.runtime_mappings(task)['bindings']
    assert project._mapping_task(task)['ended'] is None
    assert tracker.provider is provider and session.breakpoints == hooks
    assert len(session.snapshots) - captured == len(attempted) == failed_snapshot
    error = status['errors']['last']
    assert error['phase'] == 'physical-qualification'
    assert error['type'] == 'DesqviewPhysicalError'
    assert error['lifetime_action'] == 'preserved-native-provider'
    document, _ = _recorded(project, dict(kind='recorded',
        reference=error['reference'], sha256=error['sha256']))
    assert document['document']['error']['message'] == 'authored physical readback differs on pass two'
    # A successful first span is historical only after a second-span miss.
    if failed_snapshot == 2:
        rows = project.db.execute('SELECT closed FROM runtime_mapping_bindings WHERE task=?', (task,)).fetchall()
        assert len(rows) == 3 and all(row['closed'] is not None for row in rows)

    miss = False
    attempted.clear()
    session.physical = 0xa70000
    tracker.after_stop('independent physical recovery, no action replay')
    current = tracker.status()['sources'][0]
    assert current['task'] == task
    assert current['identity'] == original['identity']
    assert len(attempted) == 2
    assert current['physical_qualification']['qualified'] is True
    assert current['physical_qualification']['snapshots'] == attempted
    assert [binding['physical_start'] for binding in project.runtime_mappings(task)['bindings']] == [
        0xa70ff0, 0xa73000]
    assert 'error' not in tracker.status()


@pytest.mark.parametrize('lost_authority', ['coverage', 'registers'])
def test_physical_miss_with_lost_native_authority_retires_episode(
        setup, monkeypatch, lost_authority):
    from fdisbull.runtime_desqview_physical import DesqviewPhysicalError

    project, session, _, provider, tracker = provider_tracker(setup, monkeypatch)
    old = tracker.status()['sources'][0]['task']
    changed_cpu = False
    monkeypatch.setattr(session, 'registers', lambda: dict(authored_stopped_cpu=not changed_cpu))

    def qualify(identifier, native):
        nonlocal changed_cpu
        if lost_authority == 'coverage':
            provider.fingerprint_failure = True
        else:
            changed_cpu = True
        raise DesqviewPhysicalError('authored physical readback unavailable')

    monkeypatch.setattr(provider, 'qualify_physical', qualify, raising=False)
    tracker.after_stop('physical failure also lost independent native authority')
    assert tracker.status()['state'] == 'unqualified'
    assert tracker.status()['current_bindings'] == 0
    assert tracker.status()['errors']['last']['lifetime_action'] == 'retire-continuity'
    assert project._mapping_task(old)['ended'] is not None
    assert not project.runtime_mappings(old)['bindings']
    assert tracker.provider is None and not session.breakpoints

    changed_cpu = False
    provider.fingerprint_failure = False
    monkeypatch.setattr(provider, 'qualify_physical',
                        lambda identifier, native: _certificate(project, identifier, native))
    tracker.after_stop('fresh independent provider qualification')
    fresh = tracker.status()['sources'][0]
    assert fresh['task'] != old and fresh['physical_qualification']['qualified'] is True


def test_checkpoint_invalidation_never_reuses_physically_qualified_episode(setup, monkeypatch):
    project, session, match, provider, tracker = provider_tracker(setup, monkeypatch)
    _two_spans(project, session, match, monkeypatch)
    monkeypatch.setattr(provider, 'qualify_physical',
                        lambda identifier, native: _certificate(project, identifier, native), raising=False)
    tracker.after_stop('physically qualified checkpoint source')
    original = tracker.status()['sources'][0]
    old = original['task']
    old_snapshots = original['physical_qualification']['snapshots']
    old_process = original['identity']['process_episode']['incarnation']
    tracker.before_execution('restore checkpoint')
    assert project._mapping_task(old)['ended'] is not None
    assert not project.runtime_mappings(old)['bindings']
    assert tracker.provider is None and not session.breakpoints
    session._runtime_epoch = 'incarnation-after-restore'
    tracker.after_stop('fresh stopped source after restore')
    fresh = tracker.status()['sources'][0]
    assert fresh['task'] != old
    assert fresh['identity']['process_episode']['incarnation'] != old_process
    assert fresh['physical_qualification']['qualified'] is True
    assert not set(fresh['physical_qualification']['snapshots']).intersection(old_snapshots)
    bindings = project.runtime_mappings(fresh['task'])['bindings']
    assert all(binding['physical_qualification']['snapshot'] in
               fresh['physical_qualification']['snapshots'] for binding in bindings)
