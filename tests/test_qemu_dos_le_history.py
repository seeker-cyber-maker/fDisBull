"""Authored stopped LE histories over real project artifacts, without a guest."""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pytest

from fdisbull.project import Project
from test_qemu_dos_le_trace import active_le
from test_qemu_dos_source_admission import owned


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


@pytest.fixture
def le_history(active_le, monkeypatch):
    from fdisbull import qemu_dos_le_history as module
    get_provider = module.get_provider
    checkpoint = SimpleNamespace(MAX_DESCRIPTOR=0)
    monkeypatch.setattr(module, '_checkpoints', lambda: checkpoint)

    o, s = active_le, active_le.session
    monkeypatch.setattr('fdisbull.qemu_dos_checkpoint._compatibility', lambda session: {'runtime': 'authored'})
    monkeypatch.setattr('fdisbull.qemu_dos_checkpoint._preflight', lambda session: None)
    monkeypatch.setattr('fdisbull.qemu_dos_checkpoint._serial_idle', lambda session: None)
    s._helper, s._tail = b'authored-history-helper', b''
    s.guest_profile = {'schema': 1, 'profile_sha256': '1' * 64}
    s._checkpoint_launch = {'checkpoint_tool': 'authored-qemu-img'}
    from fdisbull.qemu_dos_checkpoint import COMMAND
    s.vm.qmp_commands = {COMMAND}
    s.capabilities = {'owned_machine_checkpoints': True, 'dos_protected_source': True}
    s.vm.checkpoint_disk = o.project.path.parent / 'authored-history.qcow2'
    s.vm.checkpoint_disk.write_bytes(b'authored-private-disk')
    s._checkpoint_epoch = 0
    s._epoch_number = 1
    s.calls = []
    # The LE provider must never borrow this separate live MZ cursor or busy flag.
    s._qemu_history_live = dict(history='mz-history', history_id='mz-id', cursor='mz-node', valid=True)
    s._history_busy = False

    def admit(session, *, timeout_ms=60000):
        assert session._history_busy is False
        assert session._le_history_busy is True
        session.calls.append(('admit', timeout_ms))
        summary = session.dos_source_binding(refresh=True, timeout_ms=min(timeout_ms, 10000))
        if not summary['live'] or summary['state'] != 'qualified-stopped':
            raise ValueError('Authored checkpoint requires a current LE stop')
        return summary

    def read(session, artifact, *, full_machine=True):
        session.calls.append(('read', artifact, full_machine))
        row = session.project.db.execute('SELECT kind,data,sha256 FROM debug_artifacts WHERE id=?', (artifact,)).fetchone()
        if row is None or row['kind'] != 'le-source-state' or hashlib.sha256(bytes(row['data'])).hexdigest() != row['sha256']:
            raise ValueError('Authored source companion is corrupt')
        document = json.loads(bytes(row['data']))
        machine = document['machine']
        native = session.project.db.execute('SELECT kind,data,sha256 FROM debug_artifacts WHERE id=?', (machine['artifact'],)).fetchone()
        if (native is None or native['kind'] != 'machine-state' or native['sha256'] != machine['sha256']
                or len(native['data']) != machine['size']
                or hashlib.sha256(bytes(native['data'])).hexdigest() != machine['sha256']):
            raise ValueError('Authored machine reference is corrupt')
        return dict(artifact=artifact, sha256=row['sha256'], size=len(row['data']),
                    charged_size=len(row['data']) + machine['size'], machine=deepcopy(machine), document=document)

    def save(session, name='le-source-state.json', *, max_bytes=None, **options):
        admit(session, timeout_ms=options.get('timeout_ms', 60000))
        session.calls.append(('save-le', o.peer.cpu['ip']))
        machine_bytes = _encoded({'ip': o.peer.cpu['ip']}).ljust(8192, b' ')
        machine = session.project._debug_artifact(session.run_id, 'authored-machine.qcow2', 'machine-state', machine_bytes, {})
        document = dict(format='fdisbull-qemu-dos-le-checkpoint-1', source_view='embedded-le',
            lifetime_qualified=False, recipe=deepcopy(session._le_source['recipe']),
            registers=session.registers(), machine={key: machine[key] for key in ('artifact', 'sha256', 'size')})
        data = _encoded(document)
        if max_bytes is not None and len(data) + len(machine_bytes) > max_bytes:
            raise ValueError('Authored checkpoint exceeds complete byte budget')
        companion = session.project._debug_artifact(session.run_id, name, 'le-source-state', data, {})
        return read(session, companion['artifact'], full_machine=False)

    def load(session, artifact, *, timeout_ms=60000):
        selected = read(session, artifact)
        session.calls.append(('load-le', artifact))
        row = session.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?', (selected['machine']['artifact'],)).fetchone()
        o.peer.cpu['ip'] = json.loads(bytes(row['data']))['ip']
        original = session.vm
        session.vm = session.rpc = SimpleNamespace(**vars(original))
        session.vm.history_operation_guard = None
        session._advance_epoch()
        session._process['source_mapping'].update(live=False, live_ranges=[])
        session._owned_machine_restored = True
        session._checkpoint_epoch += 1
        # The native owned loader invokes both guards after VM adoption.
        session._history_bind()
        session._qemu_le_history_provider._history_bind()
        bound = session.dos_source_bind(expected_source_sha256=session.metadata['source_sha256'],
                                        timeout_ms=min(timeout_ms, 10000))
        return dict(artifact=selected['machine']['artifact'], machine_state_restored=True,
            source_binding_restored=False, protected_source_rebound=True,
            le_source_checkpoint_restored=True, protected_source_binding=bound,
            le_source_checkpoint={key: selected[key] for key in ('artifact', 'sha256', 'size')},
            capture_epoch=session._runtime_epoch, checkpoint_epoch=session._checkpoint_epoch)

    monkeypatch.setattr(checkpoint, 'admit_le_source_capture', admit, raising=False)
    monkeypatch.setattr(checkpoint, 'save_le_source_state', save, raising=False)
    monkeypatch.setattr(checkpoint, 'read_le_source_state', read, raising=False)
    monkeypatch.setattr(checkpoint, 'load_le_source_state', load, raising=False)
    o.provider = get_provider(s)
    o.get_provider = get_provider
    o.admit = admit
    o.checkpoint = checkpoint
    return o


def test_capture_only_history_is_separate_and_charges_machine_plus_companion(le_history):
    o, s, h = le_history, le_history.session, le_history.provider
    mz_live = s._qemu_history_live
    start = h.rewind_start(max_steps=4, max_bytes=200000)
    assert start['format'] == 'fdisbull-qemu-dos-le-history-1'
    assert start['retained_nodes'] == 1 and start['valid']
    node = start['nodes'][0]['checkpoint']
    assert node['size'] == node['manifest_size'] + node['machine']['size']
    assert start['state_bytes_used'] == node['size'] > node['manifest_size']
    assert s._qemu_history_live is mz_live and s._history_busy is False
    assert mz_live['history'] == 'mz-history' and mz_live['history_id'] == 'mz-id'
    assert not mz_live['valid']  # The chained MZ guard observes the new operation.
    mz_after_start = deepcopy(mz_live)
    assert s._qemu_le_history_live['cursor'] == start['cursor']
    o.peer.cpu['ip'] += 2
    captured = h.rewind_record()
    assert captured['retained_nodes'] == 2
    assert captured['nodes'][-1]['edge']['kind'] == 'capture'
    assert all(n['edge'].get('completed_instruction') is not True for n in captured['nodes'])
    assert not o.intervals and s._qemu_history_live == mz_after_start


@pytest.mark.parametrize('options', [dict(advance='step'), dict(advance='run'), dict(count=2)])
def test_unsupported_record_refuses_before_checkpoint_or_guest_effects(le_history, options):
    o, s, h = le_history, le_history.session, le_history.provider
    h.rewind_start(max_steps=4, max_bytes=200000)
    calls = deepcopy(s.calls)
    before = o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]
    with pytest.raises(ValueError):
        h.rewind_record(**options)
    assert s.calls == calls and not o.intervals
    assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == before


@pytest.mark.parametrize('change', ['replacement', 'unbound', 'retired'])
def test_handle_lifecycle_invalidates_only_le_live_cursor(le_history, change):
    o, s, h = le_history, le_history.session, le_history.provider
    h.rewind_start(max_steps=4, max_bytes=200000)
    mz_live = deepcopy(s._qemu_history_live)
    if change == 'replacement':
        s.dos_source_bind()
    elif change == 'unbound':
        s.dos_source_unbind()
    else:
        s._le_source_retire('authored ownership boundary')
    status = h.rewind_status()
    assert status['valid'] is False and status['cursor'] is None
    assert s._qemu_history_live == mz_live


def test_cold_attach_and_restore_need_no_current_le_handle_and_reguard_new_owner(le_history):
    o, s, h = le_history, le_history.session, le_history.provider
    root = h.rewind_start(max_steps=4, max_bytes=200000)
    o.peer.cpu['ip'] += 2
    tip = h.rewind_record()
    s.dos_source_unbind()
    database = o.project.path
    o.project.__exit__()
    with Project(database) as cold:
        s.project = cold
        s._qemu_le_history_provider = None
        s.__dict__.pop('_qemu_le_history_live', None)
        reopened = o.get_provider(s)
        attached = reopened.rewind_start(history=tip['history'])
        assert not attached['valid'] and attached['cursor'] is None
        old_owner, old_epoch = s.vm, s._runtime_epoch
        result = reopened.rewind(history=tip['history'], node=root['cursor'])
        assert s.vm is not old_owner and s._runtime_epoch != old_epoch
        assert result['restore']['source_binding_restored'] is False
        assert result['restore']['le_source_checkpoint_restored'] is True
        assert result['restore']['protected_source_rebound'] is True
        assert result['cursor'] == root['cursor'] and o.peer.cpu['ip'] == 0x50040
        assert s.vm.history_operation_guard is not None
        s.vm.history_operation_guard('write_memory', (), {})
        assert reopened.rewind_status()['valid'] is False
        assert any(call[0] == 'read' and call[2] is False for call in s.calls)


def test_record_capacity_counts_full_native_state_before_capture(le_history):
    o, s, h = le_history, le_history.session, le_history.provider
    root = h.rewind_start(max_steps=4, max_bytes=200000)
    manifest_row = o.project.db.execute('SELECT data,metadata FROM debug_artifacts WHERE id=?', (root['history'],)).fetchone()
    manifest = json.loads(bytes(manifest_row['data']))
    # Only one companion's size remains; the 8 KiB native machine must also fit.
    remaining = root['nodes'][0]['checkpoint']['manifest_size']
    manifest['max_bytes'] = root['state_bytes_used'] + remaining
    data = _encoded(manifest)
    digest = hashlib.sha256(data).hexdigest()
    metadata = json.loads(manifest_row['metadata'])
    metadata['manifest_sha256'] = digest
    with o.project.transaction(True):
        o.project.db.execute('UPDATE debug_artifacts SET data=?,sha256=?,metadata=? WHERE id=?',
            (data, digest, json.dumps(metadata), root['history']))
    calls = deepcopy(s.calls)
    with pytest.raises(ValueError, match='budget|capacity|reserve'):
        h.rewind_record()
    assert not any(c[0] == 'save-le' for c in s.calls[len(calls):]) and not o.intervals


def _latest_history(project):
    row = project.db.execute("SELECT data FROM debug_artifacts WHERE kind='rewind-history' ORDER BY rowid DESC LIMIT 1").fetchone()
    return json.loads(bytes(row['data'])) if row is not None else None


def test_failed_admission_precedes_root_history_intent(le_history, monkeypatch):
    o, s, h = le_history, le_history.session, le_history.provider
    primary = ValueError('authored source admission refused')
    def refuse(*args, **kwargs):
        raise primary
    monkeypatch.setattr(o.checkpoint, 'admit_le_source_capture', refuse)
    with pytest.raises(ValueError) as caught:
        h.rewind_start(max_steps=4, max_bytes=200000)
    assert caught.value is primary
    assert _latest_history(o.project) is None
    assert not any(call[0] == 'save-le' for call in s.calls)
    assert not s.closed and not o.intervals


def test_source_save_failure_preserves_primary_through_failed_close(le_history, monkeypatch):
    o, s, h = le_history, le_history.session, le_history.provider
    primary = OSError('authored source checkpoint reply lost')
    primary.result = {'stage': 'authored checkpoint capture'}
    result = primary.result
    closes = []
    def fail_save(*args, **kwargs):
        raise primary
    def fail_close():
        closes.append(True)
        raise RuntimeError('authored cleanup reply lost')
    monkeypatch.setattr(o.checkpoint, 'save_le_source_state', fail_save)
    monkeypatch.setattr(s, 'close', fail_close)
    with pytest.raises(OSError) as caught:
        h.rewind_start(max_steps=4, max_bytes=200000)
    assert caught.value is primary and caught.value.result is result
    assert caught.value.le_history_cleanup_error == 'RuntimeError' and closes == [True]
    assert s.vm._fdisbull_control_quarantine
    pending = _latest_history(o.project)
    assert pending['pending']['kind'] == 'root-capture' and pending['nodes'] == []
    assert not o.intervals


def test_failed_source_restore_scope_never_publishes_valid_cursor(le_history, monkeypatch):
    o, s, h = le_history, le_history.session, le_history.provider
    root = h.rewind_start(max_steps=4, max_bytes=200000)
    o.peer.cpu['ip'] += 2
    tip = h.rewind_record()
    restore = o.checkpoint.load_le_source_state
    def wrong_scope(*args, **kwargs):
        result = restore(*args, **kwargs)
        result['le_source_checkpoint_restored'] = False
        return result
    monkeypatch.setattr(o.checkpoint, 'load_le_source_state', wrong_scope)
    monkeypatch.setattr(s, 'close', lambda: setattr(s, 'closed', True))
    with pytest.raises(ValueError, match='scoped source checkpoint'):
        h.rewind(history=tip['history'], node=root['cursor'])
    assert s.closed and s.vm._fdisbull_control_quarantine
    status = h.rewind_status()
    assert not status['valid'] and status['cursor'] is None
    pending = _latest_history(o.project)
    assert pending['pending']['kind'] == 'restore'
    assert len([call for call in s.calls if call[0] == 'load-le']) == 1
    assert not o.intervals


def test_legacy_mz_history_reader_rejects_le_manifest(le_history):
    o, s, h = le_history, le_history.session, le_history.provider
    root = h.rewind_start(max_steps=4, max_bytes=200000)
    calls = deepcopy(s.calls)
    with pytest.raises(ValueError, match='[Hh]istory manifest'):
        s._history_row(root['history'])
    assert s.calls == calls and not s.closed and not o.intervals


def test_root_descriptor_reservation_refuses_before_admission_or_intent(le_history, monkeypatch):
    o, s, h = le_history, le_history.session, le_history.provider
    monkeypatch.setattr(o.checkpoint, 'MAX_DESCRIPTOR', 8 * 1024**2)
    calls = deepcopy(s.calls)
    with pytest.raises(ValueError, match='budget|descriptor|reserve'):
        h.rewind_start(max_steps=4, max_bytes=8 * 1024**2)
    assert s.calls == calls and _latest_history(o.project) is None
    assert not s.closed and not o.intervals


@pytest.mark.parametrize('operation', ['dos_source_bind', 'dos_source_unbind'])
def test_plain_handle_change_invalidates_le_cursor_before_source_body(le_history, monkeypatch, operation):
    o, s, h = le_history, le_history.session, le_history.provider
    h.rewind_start(max_steps=4, max_bytes=200000)
    s._qemu_history_live.update(valid=True, cursor='mz-node', invalid_reason=None)
    mz_live = deepcopy(s._qemu_history_live)
    retire = s._le_source_retire
    observed = []
    def before_retire(reason, **options):
        assert s._qemu_le_history_live['valid'] is False
        assert s._qemu_le_history_live['cursor'] is None
        assert s._qemu_history_live == mz_live
        observed.append(reason)
        return retire(reason, **options)
    monkeypatch.setattr(s, '_le_source_retire', before_retire)
    getattr(s, operation)()
    assert observed and s._qemu_history_live == mz_live and not o.intervals


def test_le_busy_handle_guard_preserves_own_cursor_without_hiding_legacy_mutation(le_history):
    o, s, h = le_history, le_history.session, le_history.provider
    h.rewind_start(max_steps=4, max_bytes=200000)
    le_live = deepcopy(s._qemu_le_history_live)
    s._qemu_history_live.update(valid=True, cursor='mz-node', invalid_reason=None)
    assert s._history_busy is False
    s._le_history_busy = True
    try:
        s.vm.history_operation_guard('dos_source_bind', (), {})
        assert s._qemu_le_history_live == le_live and s._qemu_history_live['valid']
        s.vm.history_operation_guard('write_memory', (), {})
        assert not s._qemu_history_live['valid'] and s._qemu_history_live['cursor'] is None
        assert s._qemu_le_history_live == le_live
    finally:
        s._le_history_busy = False
    assert not o.intervals


def test_changed_source_producer_invalidates_cursor_without_replacing_handle(le_history, monkeypatch):
    from fdisbull import qemu_dos_le_binding
    o, s, h = le_history, le_history.session, le_history.provider
    h.rewind_start(max_steps=4, max_bytes=200000)
    s._qemu_history_live.update(valid=True, cursor='mz-node', invalid_reason=None)
    mz_live = deepcopy(s._qemu_history_live)
    handle = s._le_source
    producer = deepcopy(handle['producer'])
    changed = deepcopy(producer)
    first = next(iter(changed))
    changed[first] = 'f' * 64 if changed[first] != 'f' * 64 else '0' * 64
    monkeypatch.setattr(qemu_dos_le_binding, '_producer', lambda: deepcopy(changed))
    status = h.rewind_status()
    assert not status['valid'] and status['cursor'] is None
    assert s._le_source is handle and handle['producer'] == producer
    assert s._qemu_history_live == mz_live and not o.intervals
