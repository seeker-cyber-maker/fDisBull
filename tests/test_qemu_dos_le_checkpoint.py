"""LE companion proofs with real source admission and durable Project joins.

Only the owned native snapshot serializer/loader collaborator is substituted;
the LE matcher, instruction qualifier, binding artifacts and SQLite are real.
"""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from fdisbull import qemu_dos_le_checkpoint as checkpoint
from fdisbull import qemu_owned_checkpoint as owned_checkpoint
from fdisbull.qemu_cpu_undo_guard import attest_machine_restore
from test_qemu_dos_source_admission import owned
from test_qemu_owned_checkpoint import runtime as native_runtime


@pytest.fixture
def source(owned, monkeypatch):
    o, s = owned, owned.session
    s.metadata['process'] = deepcopy(s._process)
    s._checkpoint_epoch = 0
    o.captures = []; o.loads = []; o.attestations = []; o.thawed = []
    s._cpu_delta_full_restore_complete = lambda: o.thawed.append(True)
    monkeypatch.setattr(owned_checkpoint, '_preflight', lambda _: None)
    snapshot = {}

    def capture(session, name, max_bytes):
        assert session is s
        o.captures.append(max_bytes)
        snapshot.update(cpu=deepcopy(o.peer.cpu), table=o.peer.table,
                        memory=deepcopy(o.peer.memory_regions))
        bundle = dict(format=owned_checkpoint.FORMAT, registers=s.registers(),
            process_provenance=deepcopy(s._process), source_binding_restored=False)
        native_bytes = b'authored-native-machine' + checkpoint._json([
            dict(address=start, sha256=checkpoint._sha(data)) for start, data in o.peer.memory_regions])
        data = owned_checkpoint._archive(native_bytes, bundle)
        metadata = dict(format=owned_checkpoint.FORMAT, source_sha256=s.metadata['source_sha256'],
            version_sha256=s.metadata['version_sha256'], source_binding_restored=False,
            host_files_restored=False, sidecar_sha256=owned_checkpoint._sha(owned_checkpoint._json(bundle)))
        return dict(name=name, kind=owned_checkpoint.KIND, data=data, metadata=metadata,
                    sha256=owned_checkpoint._sha(data), size=len(data))

    def read_native(project, artifact, version=None):
        row = project.db.execute('SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',
                                  (artifact,)).fetchone()
        metadata = json.loads(row['metadata'])
        machine, bundle = owned_checkpoint._unarchive(bytes(row['data']))
        return row, metadata, machine, bundle

    def restore(session, artifact, timeout_ms=60000, rebind_protected_source=False, *, _le_checkpoint=None):
        assert session is s and rebind_protected_source is True
        assert artifact == _le_checkpoint['machine']['artifact']
        o.loads.append(artifact)
        old = s.vm
        try:
            o.peer.cpu = deepcopy(snapshot['cpu']); o.peer.table = snapshot['table']
            o.peer.memory_regions = deepcopy(snapshot['memory'])
            new = SimpleNamespace(**vars(old)); new.process = SimpleNamespace(poll=lambda: None)
            s.vm = new
            s._advance_epoch(); s._checkpoint_epoch += 1
            s._process['source_mapping'].update(live=False, live_ranges=[])
            s._owned_machine_restored = True
            rebound = s.dos_source_bind(timeout_ms=timeout_ms)
            result = dict(artifact=artifact, sha256=_le_checkpoint['machine']['sha256'],
                machine_state_restored=True, source_binding_restored=False,
                protected_source_rebound=True, protected_source_binding=rebound,
                capture_epoch=s._runtime_epoch, checkpoint_epoch=s._checkpoint_epoch)
            result.update(checkpoint.complete_le_restore(s, _le_checkpoint, rebound))
            s._event('load-machine-state', result)
            attest_machine_restore(s, result); o.attestations.append(True)
            return result
        except BaseException as error:
            owned_checkpoint._close_uncertain(s, error)
            raise

    monkeypatch.setattr(owned_checkpoint, 'capture_owned_machine_state', capture)
    monkeypatch.setattr(owned_checkpoint, '_read_artifact', read_native)
    monkeypatch.setattr(owned_checkpoint, '_load_owned_machine_state', restore)
    o.binding = s.dos_source_bind()
    return o


def test_save_freshens_binding_and_publishes_hash_joined_companion(source):
    o, s = source, source.session
    before = s.dos_source_binding()['binding_id']
    saved = checkpoint.save_le_source_state(s)
    assert s.dos_source_binding()['binding_id'] != before
    assert saved['kind'] == 'le-source-state'
    assert saved['charged_size'] == saved['size'] + saved['machine']['size']
    assert o.captures == [checkpoint.MAX_STATE-checkpoint.MAX_DESCRIPTOR]
    prepared = checkpoint.read_le_source_state(s, saved['artifact'])
    assert prepared['machine'] == saved['machine']
    assert prepared['charged_size'] == saved['charged_size']
    assert prepared['document']['boundary']['source_qualification']['qualified'] is True
    assert prepared['document']['lifetime_qualified'] is False
    assert prepared['document']['source_binding_restored'] is False
    assert not o.loads and not o.attestations


def test_real_mode_static_index_read_needs_no_handle_or_native_decoder(source, monkeypatch):
    o, s = source, source.session
    saved = checkpoint.save_le_source_state(s)
    s.dos_source_unbind(); o.peer.mode = 'real'
    def forbidden(*args, **kwargs):
        pytest.fail('Index validation decoded native machine bytes')
    monkeypatch.setattr(owned_checkpoint, '_read_artifact', forbidden)
    before = list(o.peer.reads)
    prepared = checkpoint.read_le_source_state(s, saved['artifact'], full_machine=False)
    assert prepared['artifact'] == saved['artifact'] and prepared['machine'] == saved['machine']
    assert o.peer.reads == before


def test_companion_restore_qualifies_new_handle_before_recovery_attestation(source):
    o, s = source, source.session
    saved = checkpoint.save_le_source_state(s)
    old = s.dos_source_binding(); old_epoch = s._runtime_epoch
    o.peer.cpu['ip'] += 2
    result = checkpoint.load_le_source_state(s, saved['artifact'])
    assert result['artifact'] == saved['machine']['artifact']
    assert result['le_source_checkpoint_restored'] is True
    assert result['source_binding_restored'] is False
    assert result['protected_source_binding']['binding_id'] != old['binding_id']
    assert result['capture_epoch'] != old_epoch
    assert s._process['source_mapping']['live'] is False
    assert s._process['source_mapping']['live_ranges'] == []
    assert o.attestations == o.thawed == [True]


def rewrite(o, saved, change):
    row = o.project.db.execute('SELECT data,metadata FROM debug_artifacts WHERE id=?', (saved['artifact'],)).fetchone()
    document = json.loads(bytes(row['data'])); change(document)
    data = checkpoint._json(document); metadata = json.loads(row['metadata'])
    metadata['charged_size'] = len(data)+document['machine']['size']
    with o.project.transaction(True):
        o.project.db.execute('UPDATE debug_artifacts SET data=?,sha256=?,metadata=? WHERE id=?',
            (data, checkpoint._sha(data), json.dumps(metadata), saved['artifact']))


@pytest.mark.parametrize('damage', ['producer', 'scope', 'gdt', 'placement', 'instruction', 'machine_ref', 'binding_ref'])
def test_rehashed_invalid_companion_refuses_before_native_restore(source, damage):
    o, s = source, source.session
    saved = checkpoint.save_le_source_state(s)
    def alter(document):
        if damage == 'producer': document['producer']['le.py'] = '0'*64
        elif damage == 'scope': document['source_scope'] = 'allocation lifetime'
        elif damage == 'gdt': document['gdt_hex'] = '00'*16
        elif damage == 'placement': document['recipe']['placements'][0]['runtime_base'] += 1
        elif damage == 'instruction': document['boundary']['source_qualification']['source_instruction_sha256'] = '0'*64
        elif damage == 'machine_ref': document['machine']['sha256'] = '0'*64
        else: document['binding']['size'] += 1
    rewrite(o, saved, alter)
    with pytest.raises(ValueError): checkpoint.load_le_source_state(s, saved['artifact'])
    assert not o.loads and not o.attestations and not o.thawed
    assert not o.closed


def test_source_machine_cpu_join_is_required_before_native_restore(source):
    o, s = source, source.session
    saved = checkpoint.save_le_source_state(s)
    original = owned_checkpoint._read_artifact
    def changed(*args, **kwargs):
        row, metadata, machine, bundle = original(*args, **kwargs)
        bundle['registers']['registers']['eflags'] = '0x3'
        return row, metadata, machine, bundle
    from unittest.mock import patch
    with patch.object(owned_checkpoint, '_read_artifact', changed):
        with pytest.raises(ValueError, match='machine checkpoint identity'):
            checkpoint.load_le_source_state(s, saved['artifact'])
    assert not o.loads and not o.attestations


def test_binding_or_source_drift_across_native_capture_publishes_no_companion(source, monkeypatch):
    o, s = source, source.session
    original = owned_checkpoint.capture_owned_machine_state
    def changed(*args, **kwargs):
        captured = original(*args, **kwargs)
        o.peer.cpu['ip'] += 2
        return captured
    monkeypatch.setattr(owned_checkpoint, 'capture_owned_machine_state', changed)
    with pytest.raises(ValueError, match='changed across machine capture'):
        checkpoint.save_le_source_state(s)
    assert o.closed
    assert o.project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind IN ('le-source-state','machine-state')").fetchone()[0] == 0


def test_atomic_companion_publication_rolls_back_native_artifact(source, monkeypatch):
    o, s = source, source.session
    original = s._artifact
    def fail(name, kind, data, metadata):
        if kind == checkpoint.KIND: raise OSError('authored companion publication failure')
        return original(name, kind, data, metadata)
    monkeypatch.setattr(s, '_artifact', fail)
    with pytest.raises(OSError, match='authored companion publication failure'):
        checkpoint.save_le_source_state(s)
    assert o.closed
    assert o.project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind IN ('le-source-state','machine-state')").fetchone()[0] == 0


@pytest.mark.parametrize('limit', [True, 1, checkpoint.MAX_DESCRIPTOR, checkpoint.MAX_STATE+1])
def test_total_budget_policy_refuses_before_fresh_binding_or_capture(source, limit):
    o, s = source, source.session
    before = s.dos_source_binding()['binding_id']
    with pytest.raises(ValueError, match='charged byte budget'):
        checkpoint.save_le_source_state(s, max_bytes=limit)
    assert not o.captures and s.dos_source_binding()['binding_id'] == before


def test_no_hidden_initial_binding_for_source_checkpoint_capture(source):
    o, s = source, source.session
    s.dos_source_unbind()
    with pytest.raises(ValueError, match='installed current source binding'):
        checkpoint.save_le_source_state(s)
    assert not o.captures


def test_rebound_but_different_source_site_never_attests_or_thaws(source, monkeypatch):
    o, s = source, source.session
    saved = checkpoint.save_le_source_state(s)
    original = s.dos_source_bind
    def changed(*args, **kwargs):
        rebound = original(*args, **kwargs)
        o.peer.cpu['ip'] += 2
        return rebound
    monkeypatch.setattr(s, 'dos_source_bind', changed)
    with pytest.raises(ValueError, match='differs from the selected checkpoint'):
        checkpoint.load_le_source_state(s, saved['artifact'])
    assert len(o.loads) == 1 and not o.attestations and not o.thawed
    assert o.closed


def test_restore_publication_failure_preserves_primary_without_attestation(source, monkeypatch):
    o, s = source, source.session
    saved = checkpoint.save_le_source_state(s)
    original = s._event
    def failed(operation, value):
        if operation == 'load-machine-state': raise OSError('authored load publication failure')
        return original(operation, value)
    monkeypatch.setattr(s, '_event', failed)
    with pytest.raises(OSError, match='authored load publication failure'):
        checkpoint.load_le_source_state(s, saved['artifact'])
    assert o.closed and not o.attestations and not o.thawed


def test_offline_inspection_reopened_project_returns_only_sanitized_proof_summary(source, tmp_path):
    from fdisbull.project import Project
    o, s = source, source.session
    saved = checkpoint.save_le_source_state(s)
    s.dos_source_unbind(); o.peer.mode = 'real'
    before = list(o.peer.reads)
    with Project(o.project.path) as cold:
        report = checkpoint.inspect_le_source_state(cold, saved['artifact'])
        assert report['format'] == checkpoint.FORMAT and report['machine'] == saved['machine']
        assert report['charged_size'] == saved['charged_size']
        assert report['source_binding_restored'] is report['lifetime_qualified'] is False
        assert report['source_location']['source_view'] == 'embedded-le'
        assert 'document' not in report and 'gdt_hex' not in report and 'boundary' not in report
        exported = cold.debug_export(saved['artifact'], tmp_path/'companion.json')
        assert exported['sha256'] == saved['sha256']
    assert o.peer.reads == before


def test_valid_same_cpu_epoch_machine_cannot_be_crossjoined_by_resealing_companion(source):
    o, s = source, source.session
    first = checkpoint.save_le_source_state(s)
    o.peer.memory_regions.append((0x90000, b'changed unrelated native RAM'))
    second = checkpoint.save_le_source_state(s)
    a = checkpoint.read_le_source_state(s, first['artifact'])
    b = checkpoint.read_le_source_state(s, second['artifact'])
    assert a['document']['registers'] == b['document']['registers']
    assert a['document']['capture_epoch'] == b['document']['capture_epoch']
    assert first['machine']['sha256'] != second['machine']['sha256']
    rewrite(o, first, lambda document: document.update(machine=second['machine']))
    row = o.project.db.execute('SELECT metadata FROM debug_artifacts WHERE id=?', (first['artifact'],)).fetchone()
    metadata = json.loads(row['metadata']); metadata['machine'] = second['machine']
    with o.project.transaction(True):
        o.project.db.execute('UPDATE debug_artifacts SET metadata=? WHERE id=?',
                            (json.dumps(metadata), first['artifact']))
    with pytest.raises(ValueError, match='creation receipt'):
        checkpoint.load_le_source_state(s, first['artifact'])
    assert not o.loads and not o.thawed and not o.closed


def test_second_completion_event_failure_rolls_back_both_events_and_never_thaws(native_runtime, monkeypatch):
    """Run the real shared cold loader; only fresh LE admission is substituted.

    Existing native-boundary peers restore a real Project machine artifact.
    This isolates the final publication transaction from LE proof algorithms,
    which are exercised with the real matcher in the source fixture above.
    """
    o, s = native_runtime, native_runtime.session
    saved = owned_checkpoint.save_owned_machine_state(s)
    prepared = dict(artifact='authored-companion', sha256='a'*64, size=100, charged_size=saved['size']+100,
                    machine={k:saved[k] for k in ('artifact', 'sha256', 'size')})
    monkeypatch.setattr(checkpoint, 'read_le_source_state', lambda *args, **kwargs: prepared)
    monkeypatch.setattr('fdisbull.qemu_dos_source_admission._context', lambda _: {})
    monkeypatch.setattr('fdisbull.qemu_dos_source_admission._source', lambda *args, **kwargs: (b'carrier', {}))
    monkeypatch.setattr('fdisbull.le.load_runtime_le_carrier', lambda _: object())
    monkeypatch.setattr(s, 'dos_source_bind', lambda **kwargs: dict(live=True, source_view='embedded-le'))
    monkeypatch.setattr(checkpoint, 'complete_le_restore', lambda *args:
        dict(le_source_checkpoint_restored=True, le_source_checkpoint=prepared))
    original = s._event
    def fail_second(operation, value):
        if operation == 'load-le-source-state':
            raise OSError('authored second completion publication failure')
        return original(operation, value)
    monkeypatch.setattr(s, '_event', fail_second)
    with pytest.raises(OSError, match='second completion publication failure'):
        checkpoint.load_le_source_state(s, prepared['artifact'])
    assert s.closed and s.thawed == 0 and o.spawned[0].closed
    assert o.project.db.execute("SELECT count(*) FROM debug_events WHERE operation IN ('load-machine-state','load-le-source-state')").fetchone()[0] == 0


def test_exact_baseline_companion_restores_with_current_reader(source, monkeypatch):
    o, s = source, source.session
    current = checkpoint._producer()
    with monkeypatch.context() as previous:
        previous.setattr(checkpoint, '_producer', lambda: deepcopy(checkpoint._BASELINE_PRODUCER))
        saved = checkpoint.save_le_source_state(s)
    prepared = checkpoint.read_le_source_state(s, saved['artifact'])
    assert prepared['document']['producer'] == checkpoint._BASELINE_PRODUCER
    assert prepared['reader_producer'] == current
    result = checkpoint.load_le_source_state(s, saved['artifact'])
    assert result['le_source_checkpoint_restored'] is True
    new = checkpoint.save_le_source_state(s)
    assert checkpoint.read_le_source_state(s, new['artifact'])['document']['producer'] == current
    modified = deepcopy(checkpoint._BASELINE_PRODUCER)
    modified['le.py'] = '0' * 64
    assert not checkpoint._compatible_producer(modified, current)


def test_baseline_companion_restore_rejects_reader_drift(source, monkeypatch):
    o, s = source, source.session
    with monkeypatch.context() as previous:
        previous.setattr(checkpoint, '_producer', lambda: deepcopy(checkpoint._BASELINE_PRODUCER))
        saved = checkpoint.save_le_source_state(s)
    prepared = checkpoint.read_le_source_state(s, saved['artifact'])
    changed = dict(checkpoint._producer(), **{'le.py': '0' * 64})
    monkeypatch.setattr(checkpoint, '_producer', lambda: changed)
    with pytest.raises(ValueError, match='producer changed before restore'):
        checkpoint.complete_le_restore(s, prepared, {'live': True})


def test_atomic_batch_companion_manifest_is_exactly_retained():
    from fdisbull import qemu_dos_le_checkpoint as checkpoint
    current = checkpoint._producer()
    old = dict(checkpoint._ATOMIC_BATCH_PRODUCER)
    assert checkpoint._compatible_producer(old, current)
    old['qemu_owned_checkpoint.py'] = '0' * 64
    assert not checkpoint._compatible_producer(old, current)
