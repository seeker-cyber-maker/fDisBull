"""Real policy/script/artifact persistence over an explicit stopped CPU peer."""
from copy import deepcopy
from types import MethodType, SimpleNamespace

import pytest

from fdisbull.debug_script import execute_script, validate_script
from fdisbull.qemu_dos_process import QemuDOSProcessSession
from fdisbull.qemu_screenshot_hooks import validate_native_configuration
from fdisbull.screenshot_hooks import ScreenshotHookError
from test_qemu_io_public import com_project, stopped_session


@pytest.fixture
def capture_owner(com_project, tmp_path):
    session, peer = stopped_session(com_project, tmp_path)
    session.__class__ = QemuDOSProcessSession
    session.metadata.update(backend='qemu-dos', source_sha256=com_project.meta['source_sha256'],
                            version_sha256=session.version['sha256'])
    session._runtime_epoch = 'owned:process:1'
    session._process = None
    session._deadline = None
    session.capabilities.update(code_layers=True)
    session.effects, session.reads = [], []
    session.active = []
    session.on_layer = lambda: None
    session.on_memory = lambda: None
    session.on_capture = lambda: None
    session._layer_positions = lambda definition, patch: list(range(int(patch['address'], 0),
        int(patch['address'], 0) + len(bytes.fromhex(patch['data_hex']))))
    def layers(self, active=None, *, conflict='stop'):
        if active is not None:
            self.effects.append(list(active))
            self.active = list(active)
            self.on_layer()
        return dict(active=deepcopy(self.active), generation=len(self.effects))
    def enable(self, layer, *, enabled=True):
        active = [item for item in self.active if item != layer]
        return self.layers(active + [layer] if enabled else active)
    def memory(self, address, *, length=16, space='physical'):
        self.reads.append((address, length, space))
        self.on_memory()
        return dict(hex='90' if self.active else 'b8', address=hex(address), length=length, space=space)
    session.layers = MethodType(layers, session)
    session.layer_enable = MethodType(enable, session)
    session.memory = MethodType(memory, session)
    session._layer_ram_applied = {}
    session.close = lambda: (setattr(session, 'closed', True), setattr(session.vm, 'qmp', None))
    original_call = peer.call
    def call(command, arguments=None):
        result = original_call(command, arguments)
        if command == 'screendump':
            session.on_capture()
        return result
    peer.call = call
    static = com_project.regions(1)[0].start
    a = com_project.debug_layer('a', kind='ram', patches=[
        dict(address=hex(static), expected_hex='b8', data_hex='90')])['layer']
    b = com_project.debug_layer('b', kind='ram', patches=[
        dict(address=hex(static + 1), expected_hex='00', data_hex='01')])['layer']
    session.active = [b, a]
    return SimpleNamespace(session=session, peer=peer, project=com_project, a=a, b=b)


def policy(**updates):
    return dict(require_fresh_frame=False, **updates)


def test_hook_setter_changes_session_revision_but_policy_reads_are_passive(capture_owner):
    from fdisbull.qemu_session_revision import session_revision
    o = capture_owner
    authority = session_revision(o.session.vm)
    before = authority.snapshot()
    o.session.screenshot_hooks()
    assert authority.snapshot() == before
    o.session.screenshot_hooks(policy())
    changed = authority.snapshot()
    assert changed['state_revision'] > before['state_revision']
    o.session.screenshot_hooks()
    assert authority.snapshot() == changed
    assert o.session.effects == [] and o.session.reads == []


def route(steps):
    return dict(format='fdisbull-script-1', backend='qemu-dos', steps=steps)


@pytest.mark.parametrize('config', [dict(), dict(require_fresh_frame=True),
    policy(pre=[dict(op='run', guest_ms=1)]),
    policy(pre=[dict(op='wait', observations={'x': dict(kind='memory', address=0, length=1)},
                     until=dict(observation='x', equals='00'), guest_ms=1)]),
    policy(post=[dict(op='memory', address=0, length=0)]),
    policy(pre=[dict(op='layer-stack', active='$stack')]),
    policy(pre=[dict(op='layer-enable', layer='$result.id')])])
def test_unsupported_policy_never_persists_or_changes_guest(capture_owner, config):
    o = capture_owner
    with pytest.raises((ValueError, TypeError)):
        o.session.screenshot_hooks(config)
    assert not o.project.debug_screenshot_hooks()['configured']
    assert o.session.effects == o.session.reads == o.peer.calls == []
    assert not o.session.closed


def test_stored_project_policy_is_checked_before_effects(capture_owner):
    o = capture_owner
    o.project.debug_screenshot_hooks(dict(suspend_layers=[o.a], require_fresh_frame=True))
    with pytest.raises(ValueError, match='require_fresh_frame=false'):
        o.session.screenshot()
    assert o.session.effects == o.peer.calls == [] and not o.session.closed
    raw = o.session.capture_surface()
    assert 'screenshot_hooks' not in raw['metadata']
    assert raw['metadata']['completed_guest_frame'] is None


def test_outer_script_prospective_setter_replaces_invalid_current_policy(capture_owner):
    o = capture_owner
    o.project.debug_screenshot_hooks(dict(require_fresh_frame=True))
    steps = [dict(op='screenshot-hooks', configuration=policy()), dict(op='screenshot')]
    assert validate_script(route(steps), session=o.session) == steps
    assert o.session.effects == o.peer.calls == []
    result = execute_script(o.session, route(steps))
    assert result['ok'], result
    assert result['steps'][1]['result']['screenshot_hooks']['ok']


def test_invalid_prospective_policy_rejects_before_earlier_script_mutation(capture_owner):
    o = capture_owner
    steps = [dict(op='layer-enable', layer=o.a, enabled=False),
        dict(op='screenshot-hooks', configuration=dict(require_fresh_frame=True)), dict(op='screenshot')]
    with pytest.raises(ValueError, match='require_fresh_frame=false'):
        execute_script(o.session, route(steps))
    assert o.session.effects == o.peer.calls == []


def test_passive_pre_post_capture_restores_typed_order_and_pins_artifact(capture_owner):
    o = capture_owner
    original = list(o.session.active)
    saved = o.session.screenshot_hooks(policy(suspend_layers=original,
        pre=[dict(op='memory', address=0x5000, length=1, **{'as': 'byte'}),
             dict(op='assert', value='$byte.hex', equals='b8')],
        post=[dict(op='layer-enable', layer=o.a), dict(op='memory', address=0x5000, length=1)]))
    result = o.session.screenshot('surface.png')
    assert result['screenshot_hooks']['ok'], result
    assert result['screenshot_hooks']['restore'] == dict(ok=True, active=original)
    assert o.session.effects == [[], [o.a], original]
    assert o.session.active == original and not o.session.closed
    metadata = result['metadata']
    assert metadata['screenshot_hooks']['policy_sha256'] == saved['sha256']
    assert metadata['screenshot_hooks']['capture_layers'] == []
    assert metadata['screenshot_hooks']['original_layers'] == original
    assert metadata['completed_guest_frame'] is None and metadata['guest_frame_id'] is None
    assert metadata['capture_id'] and metadata['registers']['linear_pc'] == '0x7c00'
    before, after = metadata['clocks']['before'], metadata['clocks']['after']
    assert before['epoch'] == after['epoch'] and before['counter'] == after['counter']
    assert before.get('virtual_ns') == after.get('virtual_ns')
    assert [command for command, _ in o.peer.calls].count('screendump') == 1
    assert not any(command in ('cont','input-send-event') for command, _ in o.peer.calls)
    assert o.session._qemu_surface_hook_evidence is None


def test_failed_pre_assertion_preserves_prefix_skips_capture_and_suffix(capture_owner):
    o = capture_owner
    original = list(o.session.active)
    o.session.screenshot_hooks(policy(suspend_layers=original,
        pre=[dict(op='assert', value=1, equals=2), dict(op='layer-enable', layer=o.a)],
        post=[dict(op='memory', address=0x5000, length=1)]))
    with pytest.raises(ScreenshotHookError) as failed:
        o.session.screenshot()
    report = failed.value.result
    assert report['pre']['requested_steps'] == 2 and len(report['pre']['steps']) == 1
    assert report['capture'] is None and report['post']['ok']
    assert report['restore'] == dict(ok=True, active=original)
    assert o.session.effects == [[], original]
    assert o.peer.calls == [] and not o.session.closed


def test_post_failure_keeps_published_capture_and_restores(capture_owner):
    o = capture_owner
    original = list(o.session.active)
    o.session.screenshot_hooks(policy(suspend_layers=original,
        post=[dict(op='assert', value=False, equals=True), dict(op='layer-enable', layer=o.a)]))
    with pytest.raises(ScreenshotHookError) as failed:
        o.session.screenshot()
    report = failed.value.result
    assert report['capture']['artifact'] and report['errors'][0]['phase'] == 'post'
    assert len(report['post']['steps']) == 1 and report['restore']['ok']
    assert o.session.effects == [[], original] and not o.session.closed


def test_restore_failure_closes_and_keeps_primary_error(capture_owner):
    o = capture_owner
    o.session.screenshot_hooks(policy(suspend_layers=list(o.session.active),
        pre=[dict(op='assert', value=1, equals=2)]))
    def reject_restore():
        if o.session.active:
            raise ValueError('native restoration refused')
    o.session.on_layer = reject_restore
    with pytest.raises(ScreenshotHookError) as failed:
        o.session.screenshot()
    report = failed.value.result
    assert report['errors'][0]['phase'] == 'pre-or-capture'
    assert report['errors'][1]['phase'] == 'restore'
    assert o.session.closed and not report['restore']['ok']


def test_single_inherited_deadline_expires_without_cleanup_guest_work(capture_owner, monkeypatch):
    o = capture_owner
    o.session.screenshot_hooks(policy(suspend_layers=list(o.session.active),
        pre=[dict(op='memory', address=0x5000, length=1)], post=[dict(op='registers')]))
    now = [100.0]
    monkeypatch.setattr('time.monotonic', lambda: now[0])
    o.session._rpc_deadline = 100.1
    o.session.vm.operation_deadline = 100.2
    o.peer.operation_deadline = 100.3
    o.session.on_memory = lambda: now.__setitem__(0, 100.15)
    with pytest.raises(ScreenshotHookError) as failed:
        o.session.screenshot()
    report = failed.value.result
    assert not report['pre']['ok'] and report['capture'] is None and report['post'] is None
    assert o.session.effects == [[]] and o.session.closed
    assert o.session._rpc_deadline == 100.1 and o.session.vm.operation_deadline == 100.2
    assert o.peer.operation_deadline == 100.3


def test_changed_immutable_layer_after_transition_refuses_and_closes(capture_owner, monkeypatch):
    o = capture_owner
    o.session.screenshot_hooks(policy(suspend_layers=list(o.session.active)))
    real = o.project.debug_layer_info
    def change():
        monkeypatch.setattr(o.project, 'debug_layer_info', lambda identifier: dict(real(identifier), sha256='0' * 64))
    o.session.on_layer = change
    with pytest.raises(ScreenshotHookError) as failed:
        o.session.screenshot()
    assert 'immutable layer' in failed.value.result['errors'][0]['message']
    assert o.session.closed and o.session.effects == [[]] and o.peer.calls == []


def test_unknown_later_post_layer_refuses_before_suspension(capture_owner):
    o = capture_owner
    o.project.debug_screenshot_hooks(policy(suspend_layers=[o.a],
        post=[dict(op='layer-enable', layer='unknown-layer')]))
    with pytest.raises(ValueError, match='Unknown code layer'):
        o.session.screenshot()
    assert o.session.effects == o.peer.calls == [] and not o.session.closed


def test_explicit_bypass_preserves_original_surface_contract(capture_owner):
    o = capture_owner
    o.project.debug_screenshot_hooks(dict(require_fresh_frame=True))
    result = o.session.screenshot(hooks=False)
    assert 'screenshot_hooks' not in result and 'screenshot_hooks' not in result['metadata']
    assert o.session.effects == []


def test_offline_script_validation_rejects_native_fresh_frame_policy():
    with pytest.raises(ValueError, match='require_fresh_frame=false'):
        validate_script(route([dict(op='screenshot-hooks', configuration=dict(require_fresh_frame=True)),
                               dict(op='screenshot')]))


def test_policy_preflight_preserves_callers_existing_input_lease(capture_owner):
    o = capture_owner
    state = o.session._input_storage()
    state['leases']['caller'] = dict(device='keyboard', key='ctrl', make='python_pending', release=None)
    state['pending'].append(dict(lease='caller', pressed=True))
    before = deepcopy(state)
    with pytest.raises(ValueError, match='require_fresh_frame=false'):
        o.session.screenshot_hooks(dict(require_fresh_frame=True))
    assert o.session._input_storage() == before and not o.session.closed
    o.session.screenshot_hooks(policy(pre=[dict(op='assert', value=1, equals=2)]))
    with pytest.raises(ScreenshotHookError):
        o.session.screenshot()
    assert o.session._input_storage() == before and not o.session.closed
    assert o.session.effects == o.peer.calls == []


def test_owner_replacement_while_waiting_rejects_without_touching_new_owner(capture_owner):
    o = capture_owner
    o.session.screenshot_hooks(policy(suspend_layers=[o.a]))
    owner = o.session.vm
    replacement = SimpleNamespace(process=None, qmp=SimpleNamespace(operation_deadline=77),
                                  operation_deadline=88)
    class Lock:
        released = False
        def acquire(self, timeout):
            o.session.vm = replacement
            return True
        def release(self):
            self.released = True
    owner.lock = Lock()
    with pytest.raises(ValueError, match='owner'):
        o.session.screenshot()
    assert owner.lock.released and o.session.effects == o.peer.calls == []
    assert replacement.operation_deadline == 88 and replacement.qmp.operation_deadline == 77
    assert not o.session.closed


def test_deadline_tightened_while_waiting_is_not_extended(capture_owner, monkeypatch):
    o = capture_owner
    o.session.screenshot_hooks(policy())
    monkeypatch.setattr('time.monotonic', lambda: 100)
    owner = o.session.vm
    owner.operation_deadline = 150
    class Lock:
        released = False
        def acquire(self, timeout):
            owner.operation_deadline = 99
            return True
        def release(self):
            self.released = True
    owner.lock = Lock()
    with pytest.raises(TimeoutError, match='deadline'):
        o.session.screenshot()
    assert owner.operation_deadline == 99 and owner.lock.released
    assert o.session.effects == o.peer.calls == [] and not o.session.closed


def test_original_stack_requires_typed_receipt(capture_owner):
    o = capture_owner
    o.session.screenshot_hooks(policy())
    o.session.active = tuple(o.session.active)
    with pytest.raises(ValueError, match='literal, ordered'):
        o.session.screenshot()
    assert o.session.effects == o.peer.calls == [] and not o.session.closed


def test_runtime_epoch_change_after_layer_transition_quarantines_owner(capture_owner):
    o = capture_owner
    o.session.screenshot_hooks(policy(suspend_layers=list(o.session.active)))
    o.session.on_layer = lambda: setattr(o.session, '_runtime_epoch', 'replacement:epoch')
    with pytest.raises(ScreenshotHookError) as failed:
        o.session.screenshot()
    assert 'lifetime changed' in failed.value.result['errors'][0]['message']
    assert o.session.closed and o.session.effects == [[]]
    assert o.session.vm._fdisbull_control_quarantine


def test_grid_inherits_surface_provenance_without_new_guest_observations(capture_owner):
    o = capture_owner
    o.session.screenshot_hooks(policy())
    result = o.session.screenshot(grid=True)
    assert result['metadata']['screenshot_hooks']['policy'] == result['screenshot_hooks']['policy']
    assert result['metadata']['completed_guest_frame'] is None
    assert result['metadata']['coordinate_grid']['source_artifact']
    assert [name for name, _ in o.peer.calls].count('screendump') == 1


def test_provenance_can_only_add_a_nested_field_not_replace_surface_claims(capture_owner):
    from fdisbull.qemu_screenshot_hooks import _SurfaceEvidence, _identity
    import time
    o = capture_owner
    o.session._qemu_surface_hook_evidence = _SurfaceEvidence(o.session, _identity(o.session),
        time.monotonic() + 10, {}, dict(capture_id='forged', completed_guest_frame=99,
                                       clocks='forged', registers='forged'))
    result = o.session.capture_surface()
    assert result['metadata']['capture_id'] != 'forged'
    assert result['metadata']['completed_guest_frame'] is None
    assert isinstance(result['metadata']['clocks'], dict)
    assert isinstance(result['metadata']['registers'], dict)
    assert result['metadata']['screenshot_hooks']['capture_id'] == 'forged'


def test_existing_machine_guard_refuses_before_layer_effects(capture_owner):
    o = capture_owner
    o.session.screenshot_hooks(policy(suspend_layers=[o.a]))
    def guard(name, args, kwargs):
        if name == 'screenshot':
            raise ValueError('existing history/frozen-state fence')
    o.session.vm.history_operation_guard = guard
    with pytest.raises(ValueError, match='existing history'):
        o.session.screenshot()
    assert o.session.effects == o.peer.calls == [] and not o.session.closed


def test_cleanup_and_evidence_failures_do_not_mask_first_failed_step(capture_owner):
    o = capture_owner
    o.session.screenshot_hooks(policy(suspend_layers=list(o.session.active),
        pre=[dict(op='assert', value='first', equals='stop')]))
    def reject_restore():
        if o.session.active:
            raise ValueError('restoration refused')
    o.session.on_layer = reject_restore
    def close():
        o.session.closed = True
        raise OSError('close observer failed')
    o.session.close = close
    o.session._event = lambda *args: (_ for _ in ()).throw(OSError('event failed'))
    with pytest.raises(ScreenshotHookError) as failed:
        o.session.screenshot()
    report = failed.value.result
    assert report['pre']['error']['op'] == 'assert'
    assert [item['phase'] for item in report['errors']] == ['pre-or-capture', 'restore', 'close', 'evidence']
    assert not report['ok'] and o.session.closed


def test_all_possible_failed_pre_prefix_post_destinations_are_preflighted(capture_owner):
    o = capture_owner
    static = o.project.regions(1)[0].start
    conflicting = o.project._store_debug_layer('conflicting-base', 1, dict(kind='ram', patches=[
        dict(address=hex(static), expected_hex='00', data_hex='01')]))['layer']
    o.session.screenshot_hooks(policy(pre=[dict(op='assert', value=1, equals=2),
                                          dict(op='layer-stack', active=[])],
                                     post=[dict(op='layer-enable', layer=conflicting)]))
    with pytest.raises(ValueError, match='disagree about base bytes'):
        o.session.screenshot()
    assert o.session.effects == o.peer.calls == [] and not o.session.closed


@pytest.mark.parametrize('operation', ['configure', 'capture'])
def test_closed_owner_admission_is_explicit(capture_owner, operation):
    o = capture_owner
    o.project.debug_screenshot_hooks(policy())
    o.session.closed, o.session.vm = True, None
    with pytest.raises(ValueError, match='owner|machine|live'):
        if operation == 'configure':
            o.session.screenshot_hooks(policy())
        else:
            o.session.screenshot()


def test_late_final_event_preserves_capture_restore_and_refuses_success(capture_owner, monkeypatch):
    o = capture_owner
    o.session.screenshot_hooks(policy())
    now = [100.0]
    monkeypatch.setattr('time.monotonic', lambda: now[0])
    o.session._rpc_deadline = 100.5
    event = o.session._event
    def late(operation, data):
        event(operation, data)
        if operation == 'screenshot-hooks':
            now[0] = 101.0
    o.session._event = late
    with pytest.raises(ScreenshotHookError) as failed:
        o.session.screenshot()
    report = failed.value.result
    assert report['capture']['artifact'] and report['restore']['ok']
    assert not report['ok'] and not o.session.closed
    assert report['errors'][-1]['phase'] == 'completion'
    assert o.session.effects == []


def test_grid_failure_preserves_already_published_surface(capture_owner, monkeypatch):
    o = capture_owner
    o.session.screenshot_hooks(policy(suspend_layers=[o.a]))
    def fail_grid(*args, **kwargs):
        raise OSError('grid derivation failed')
    monkeypatch.setattr(o.project, 'debug_grid', fail_grid)
    with pytest.raises(ScreenshotHookError) as failed:
        o.session.screenshot(grid=True)
    report = failed.value.result
    assert report['capture']['artifact']
    assert report['capture']['metadata']['completed_guest_frame'] is None
    assert report['restore']['ok'] and not o.session.closed
    assert [name for name, _ in o.peer.calls].count('screendump') == 1


def test_expired_outer_capture_return_keeps_publication_receipt(capture_owner, monkeypatch):
    o = capture_owner
    o.session.screenshot_hooks(policy())
    now = [100.0]
    monkeypatch.setattr('time.monotonic', lambda: now[0])
    o.session._rpc_deadline = 100.5
    event = o.session._event
    def late(operation, data):
        event(operation, data)
        if operation == 'machine-capture-surface':
            now[0] = 101.0
    o.session._event = late
    with pytest.raises(ScreenshotHookError) as failed:
        o.session.screenshot()
    assert failed.value.result['capture']['artifact']
    assert not failed.value.result['ok'] and not o.session.closed
    assert o.session.effects == []
