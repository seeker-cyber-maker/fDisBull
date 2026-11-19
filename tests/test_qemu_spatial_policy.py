"""Full host spatial-policy parity without native action or frame authority."""
from copy import deepcopy
import json
import time
from types import SimpleNamespace

import pytest

from fdisbull.cli import respond
from fdisbull.debugger import DebugProjectMixin, DebugWorkspace
from fdisbull.debug_script import validate_script
from fdisbull.project import Project
from fdisbull.spatial import SpatialSessionMixin
from test_qemu_dos_source_admission import owned
from test_qemu_runtime_memory import ram, ADDRESS
from test_qemu_owned_checkpoint import runtime as checkpoint_runtime


def fields(session):
    return (getattr(session, '_spatial_mode', 'assisted'),
            getattr(session, '_fair_play', False),
            getattr(session, '_allow_assisted_travel', True))


def events(project, run):
    return [json.loads(row[0]) for row in project.db.execute(
        "SELECT evidence FROM debug_events WHERE run=? AND operation='spatial-policy' ORDER BY sequence", (run,))]


def no_native(o):
    assert not o.peer.qmp_calls and not o.peer.reads and not o.peer.register_reads
    assert not o.peer.monitor_reads and not o.closed


@pytest.mark.parametrize('options', [{}, {'mode': 'physical'}, {'mode': 'assisted'},
    {'mode': 'story'}, {'mode': 'physical', 'fair_play': True}])
def test_public_policy_matches_existing_dosbox_result_and_event(owned, options):
    reference_events = []
    legacy = SimpleNamespace(_event=lambda name, value: reference_events.append((name, value)))
    expected = SpatialSessionMixin.spatial_policy(legacy, **options)
    workspace = DebugWorkspace()
    workspace.sessions[owned.session.run_id] = owned.session
    try:
        reply = respond(dict(method='debug-spatial-policy', params=dict(project=str(owned.project.path),
            run=owned.session.run_id, **options)), debugger=workspace)
    finally:
        workspace.sessions.clear()
    assert reply['ok'], reply
    assert reply['result'] == expected
    assert fields(owned.session) == fields(legacy)
    assert events(owned.project, owned.session.run_id) == [reference_events[0][1]]
    assert set(expected) == {'spatial_mode', 'fair_play', 'assisted_travel', 'voluntary'}
    assert expected['voluntary'] is True
    no_native(owned)


def test_policy_does_not_grant_missing_consumers_or_touch_frozen_source_input(owned):
    s = owned.session
    s._qemu_cpu_delta_history = dict(id='selected', cursor='frozen', frozen=True, valid=False)
    s._dos_history = {'cursor': 'current', 'valid': True}
    s.vm._physical_input = {'leases': {'caller': {'key': 'a'}}, 'pending': ['caller-edge']}
    before = deepcopy((s._qemu_cpu_delta_history, s._dos_history, s.vm._physical_input, s._process))
    def forbidden(*args, **kwargs): pytest.fail('Host policy touched native controls or lock')
    s.vm.lock = SimpleNamespace(acquire=forbidden, release=forbidden)
    s.vm.operation_guard = s.vm.history_operation_guard = forbidden
    assert s.spatial_policy('assisted')['assisted_travel'] is True
    assert all(not hasattr(s, operation) for operation in (
        'assisted_travel', 'spatial_action', 'scene_check', 'click', 'frame_probe', 'move'))
    assert (s._qemu_cpu_delta_history, s._dos_history, s.vm._physical_input, s._process) == before
    no_native(owned)


@pytest.mark.parametrize('options', [{'mode': 'story'}, {'mode': 'assisted'},
    {'fair_play': False}, {'mode': 'physical', 'fair_play': False}])
def test_fair_play_latch_cannot_be_relaxed_and_failed_attempts_do_not_publish(owned, options):
    s = owned.session
    locked = s.spatial_policy('physical', fair_play=True)
    with pytest.raises(ValueError, match='Fair play'):
        s.spatial_policy(**options)
    assert fields(s) == ('physical', True, False)
    assert events(owned.project, s.run_id) == [locked]
    no_native(owned)


def test_lock_remains_conservative_after_publication_failure(owned):
    def failed(*args): raise OSError('Authored evidence failure')
    owned.session._event = failed
    with pytest.raises(OSError, match='evidence'):
        owned.session.spatial_policy('physical', fair_play=True)
    assert fields(owned.session) == ('physical', True, False)
    with pytest.raises(ValueError, match='Fair play'):
        owned.session.spatial_policy('assisted', fair_play=False)
    no_native(owned)


def test_owned_native_loader_replaces_owner_without_rewinding_session_policy(checkpoint_runtime):
    o, s = checkpoint_runtime, checkpoint_runtime.session
    assert s.spatial_policy('story')['spatial_mode'] == 'story'
    saved = s.save_machine_state()
    s.spatial_policy('physical', fair_play=True)
    owner, epoch = s.vm, s._runtime_epoch
    restored = s.load_machine_state(saved['artifact'])
    assert restored['machine_state_restored'] and s.vm is not owner and owner.closed
    assert s._runtime_epoch != epoch and fields(s) == ('physical', True, False)
    with pytest.raises(ValueError, match='Fair play'): s.spatial_policy('assisted')
    assert s.spatial_policy()['fair_play'] is True


def test_policy_events_reopen_without_reconstructing_live_ownership(owned):
    result = owned.session.spatial_policy('physical', fair_play=True)
    with Project(owned.project.path) as reopened:
        assert events(reopened, owned.session.run_id) == [result]
    no_native(owned)


@pytest.mark.parametrize('options', [{'mode': 'elsewhere'}, {'mode': []}, {'fair_play': 1},
    {'fair_play': 'true'}, {'mode': 'story', 'fair_play': True}])
def test_invalid_policy_options_refuse_before_state_or_event_change(owned, options):
    with pytest.raises(ValueError): owned.session.spatial_policy(**options)
    assert fields(owned.session) == ('assisted', False, True)
    assert not events(owned.project, owned.session.run_id)
    no_native(owned)


def test_wrong_source_context_and_expired_deadline_are_effect_free(owned):
    s = owned.session
    original = s.metadata['source_sha256']
    s.metadata['source_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='exact project'): s.spatial_policy('story')
    s.metadata['source_sha256'] = original
    s._rpc_deadline = time.monotonic() - 1
    with pytest.raises(TimeoutError, match='before admission'): s.spatial_policy('physical', fair_play=True)
    assert fields(s) == ('assisted', False, True) and not events(owned.project, s.run_id)
    no_native(owned)


def test_wrong_policy_source_context_refuses_before_earlier_script_write(ram):
    ram.session.metadata['source_sha256'] = '0' * 64
    script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        dict(op='write-memory', address=ADDRESS + 2, data_hex='aabb', expected_hex='1234'),
        dict(op='spatial-policy', mode='physical', fair_play=True)])
    with pytest.raises(ValueError, match='exact project'): ram.session.script(script=script)
    assert not ram.writes and fields(ram.session) == ('assisted', False, True)
    no_native(ram)


def test_late_return_preserves_selected_latch_and_receipt_without_native_cleanup(owned, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(time, 'monotonic', lambda: clock[0])
    s, original = owned.session, owned.session._event
    s._rpc_deadline = 100.5
    def event(name, value):
        original(name, value)
        clock[0] = 101.0
    s._event = event
    with pytest.raises(TimeoutError, match='exceeded') as caught:
        s.spatial_policy('physical', fair_play=True)
    assert caught.value.result == events(owned.project, s.run_id)[0]
    assert fields(s) == ('physical', True, False) and s._rpc_deadline == 100.5
    no_native(owned)


@pytest.mark.parametrize('later', [
    dict(op='spatial-policy', mode='$earlier.mode', fair_play=1),
    dict(op='spatial-policy', mode='invalid', fair_play='$earlier.fair'),
    dict(op='spatial-policy', mode='story', fair_play=True),
])
def test_each_known_policy_literal_refuses_before_an_earlier_ram_write(ram, later):
    script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        dict(op='write-memory', address=ADDRESS + 2, data_hex='aabb', expected_hex='1234'), later])
    with pytest.raises(ValueError): ram.session.script(script=script)
    assert not ram.writes and fields(ram.session) == ('assisted', False, True)
    no_native(ram)


@pytest.mark.parametrize('later', [
    dict(op='spatial-policy', mode='assisted'),
    dict(op='spatial-policy', mode='$earlier.mode', fair_play=False),
])
def test_later_impossible_transition_refuses_whole_script_before_policy_or_ram_effect(ram, later):
    script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        dict(op='spatial-policy', mode='physical', fair_play=True),
        dict(op='write-memory', address=ADDRESS + 2, data_hex='aabb', expected_hex='1234'), later])
    with pytest.raises(ValueError, match='no valid transition'): ram.session.script(script=script)
    assert not ram.writes and fields(ram.session) == ('assisted', False, True)
    assert not events(ram.project, ram.session.run_id)
    no_native(ram)


def test_saved_script_references_and_unknown_future_mode_are_validated_when_resolved(owned):
    s = owned.session
    s.capabilities = {'code_layers': False}
    script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        dict(op='spatial-policy', mode='physical', fair_play=True, **{'as': 'policy'}),
        dict(op='spatial-policy', mode='$policy.spatial_mode', fair_play='$policy.fair_play')])
    result = s.script(script=script)
    assert result['ok'] and result['completed_steps'] == 2
    assert events(owned.project, s.run_id) == [result['steps'][0]['result'], result['steps'][1]['result']]
    assert validate_script(dict(format='fdisbull-script-1', backend='qemu-dos',
        steps=[dict(op='spatial-policy', mode='$external.mode', fair_play=True)]), session=s)
    no_native(owned)


@pytest.mark.parametrize(('options', 'expected'), [
    ({}, ('assisted', False)), ({'fair_play': True}, ('physical', True)),
    ({'spatial_mode': 'story'}, ('story', False)),
    ({'spatial_mode': 'physical', 'fair_play': False}, ('physical', False)),
])
def test_factory_routes_native_process_policy_and_preserves_defaults(tmp_path, monkeypatch, options, expected):
    import fdisbull.qemu_dos_process as implementation
    captured = {}
    monkeypatch.setattr(implementation, 'QemuDOSProcessSession',
        lambda *args, **kwargs: captured.update(kwargs) or captured)
    project = SimpleNamespace(meta={'format': 'COM', 'filename': 'program.com'})
    result = DebugProjectMixin.debugger(project, 'not-launched', tmp_path, backend='qemu-dos', **options)
    assert (result['spatial_mode'], result['fair_play']) == expected


@pytest.mark.parametrize(('backend', 'format'), [('qemu-machine', 'raw'), ('qemu-dos', 'raw'),
    ('wine-qemu', 'PE'), ('qemu-chip8', 'raw')])
def test_policy_extension_does_not_relax_other_launch_profiles(tmp_path, backend, format):
    project = SimpleNamespace(meta={'format': format, 'filename': 'source'})
    with pytest.raises(ValueError):
        DebugProjectMixin.debugger(project, 'not-launched', tmp_path, backend=backend, fair_play=True)


@pytest.mark.parametrize('options', [{'spatial_mode': 'invalid'}, {'fair_play': 1},
    {'spatial_mode': 'story', 'fair_play': True}])
def test_direct_constructor_validates_policy_before_project_or_disk_access(options):
    from fdisbull.qemu_dos_process import QemuDOSProcessSession
    with pytest.raises(ValueError):
        QemuDOSProcessSession(object(), 'not-launched', 'not-opened', **options)
