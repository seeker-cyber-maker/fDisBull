"""Host-only policy tests for native PIC preemption; no guest execution."""
from copy import deepcopy

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_checkpoint_controls import restore_controls
from fdisbull.qemu_dos_preemption import (COMMAND, CONTROLS_FORMAT, FORMAT as IRQ_FORMAT,
    MODEL as IRQ_MODEL, validate_irq_frame)
from fdisbull.qemu_dos_scheduler import (QemuDOSSchedulerMixin, _validate_native_status,
    capture_scheduler, validate_scheduler)
from test_qemu_dos_scheduler import _Session, _status, _checkpoint


def _preemption(**changes):
    value = {'model':IRQ_MODEL, 'enabled':False, 'irq':0,
        'quantum':1, 'quantum-progress':0, 'pending':False,
        'ack-count':0, 'eoi-count':0, 'preemption-count':0, 'last-valid':False,
        'last-irq':0, 'last-vector':0, 'last-from-uuid':'', 'last-from-cookie':0,
        'last-from-incarnation':0, 'last-to-uuid':'', 'last-to-cookie':0,
        'last-to-incarnation':0, 'pic-mask':0, 'pic-irr':0, 'pic-isr':0,
        'pic-irq-base':8, 'inflight':False, 'inflight-irq':0, 'inflight-vector':0,
        'inflight-uuid':'', 'inflight-cookie':0, 'inflight-incarnation':0,
        'inflight-sequence':0, 'inflight-frame-sequence':0}
    value.update(changes)
    return value


def _status_v2(session, **changes):
    status = _status(session.binding)
    status['api-version'] = 2
    status['preemption'] = _preemption(**changes)
    return status


def test_legacy_scheduler_receipt_remains_accepted():
    session = _Session()
    assert _validate_native_status(_status(session.binding))['api-version'] == 1


def test_api2_preemption_receipt_is_accepted():
    session = _Session(); value = _status_v2(session)
    assert _validate_native_status(value) == value


@pytest.mark.parametrize('field,value', [
    ('model','unknown'), ('enabled',1), ('irq',2), ('irq',8), ('irq',True),
    ('quantum',0), ('quantum',65536), ('quantum',True), ('quantum-progress',1),
    ('pending',1), ('ack-count',-1), ('eoi-count',1 << 64),
    ('preemption-count',False), ('pic-mask',256), ('pic-irr',-1),
    ('pic-isr',True), ('pic-irq-base',256), ('inflight',0), ('last-valid',1),
])
def test_api2_rejects_malformed_preemption_fields(field, value):
    session = _Session(); status = _status_v2(session)
    status['preemption'][field] = value
    with pytest.raises(DebuggerError):
        _validate_native_status(status)


def test_api2_rejects_missing_preemption_record():
    session = _Session(); status = _status_v2(session)
    del status['preemption']
    with pytest.raises(DebuggerError):
        _validate_native_status(status)


def _inflight(session):
    binding = session.binding
    status = _status_v2(session, enabled=True, inflight=True,
        **{'pic-isr':1, 'ack-count':1, 'eoi-count':0,
           'inflight-irq':0, 'inflight-vector':8,
           'inflight-uuid':binding['monitor_uuid'], 'inflight-cookie':binding['cookie'],
           'inflight-incarnation':binding['incarnation'], 'inflight-sequence':1,
           'inflight-frame-sequence':7})
    status['tasks'][0]['interrupt-depth'] = 1
    return status


def test_valid_inflight_status_is_not_rejected_just_for_existing():
    session = _Session(); status = _inflight(session)
    assert _validate_native_status(status) == status


@pytest.mark.parametrize('change', ['selected','frame-depth','retired'])
def test_inflight_status_requires_selected_live_cpu_frame(change):
    session = _Session(); status = _inflight(session)
    if change == 'selected': status['selected-cookie'] = 2
    elif change == 'frame-depth': status['tasks'][0]['interrupt-depth'] = 0
    else: status['tasks'][0]['retired'] = True
    with pytest.raises(DebuggerError): _validate_native_status(status)


def test_api2_nontagged_frame_requires_typed_zero_pic_metadata():
    frame = {'pic-irq-valid':False, 'pic-controller':0, 'pic-irq':0, 'pic-vector':0,
             'pic-ack-sequence':0, 'pic-eoi-seen':False}
    validate_irq_frame(frame, required=True)
    for field in frame:
        missing = dict(frame); del missing[field]
        with pytest.raises(DebuggerError): validate_irq_frame(missing, required=True)
    for field, value in [('pic-irq-valid',0), ('pic-eoi-seen',0), ('pic-irq',1)]:
        invalid = dict(frame, **{field:value})
        with pytest.raises(DebuggerError): validate_irq_frame(invalid, required=True)
    validate_irq_frame({}, required=False)


@pytest.mark.parametrize('changes', [
    {'pic-isr':0}, {'inflight-uuid':''}, {'inflight-cookie':0},
    {'inflight-incarnation':0}, {'inflight-sequence':0}, {'inflight-frame-sequence':0},
])
def test_inflight_status_requires_pic_and_native_task_identity(changes):
    session = _Session(); status = _inflight(session)
    status['preemption'].update(changes)
    with pytest.raises(DebuggerError):
        _validate_native_status(status)


def test_checkpoint_capture_rejects_uncommitted_eoi_handoff(monkeypatch):
    import fdisbull.qemu_dos_scheduler as scheduler
    session = _Session(); status = _status_v2(session, enabled=True, pending=True)
    monkeypatch.setattr(scheduler, '_status', lambda *args, **kwargs: status)
    with pytest.raises((ValueError, DebuggerError), match='pending|commit|handoff'):
        capture_scheduler(session)


def test_checkpoint_saved_envelope_rejects_uncommitted_eoi_handoff():
    session = _Session(); saved = _checkpoint(session)
    saved['format'] = IRQ_FORMAT
    saved['metadata']['format'] = IRQ_FORMAT
    saved['metadata']['preemption'] = {'enabled':True,'irq':0,'quantum':1}
    session.vm.qmp_commands = set(session.vm.qmp_commands) | {COMMAND}
    saved['native'] = _status_v2(session, enabled=True, pending=True)
    with pytest.raises((ValueError, DebuggerError), match='pending|commit|handoff'):
        validate_scheduler(session, saved, session.binding['process_nonce'],
                           {'views':[{'binding':deepcopy(session.binding)}]}, session._process)


def _inflight_checkpoint(session):
    saved = _checkpoint(session)
    saved['format'] = IRQ_FORMAT
    saved['metadata']['format'] = IRQ_FORMAT
    saved['metadata']['preemption'] = {'enabled':True,'irq':0,'quantum':1}
    session.vm.qmp_commands = set(session.vm.qmp_commands) | {COMMAND}
    saved['native'] = _inflight(session)
    saved['native']['tasks'][0]['interrupt-depth'] = 1
    context = saved['contexts'][session.binding['task_id']]
    context['interrupt-depth'] = 1
    context['frames'] = [dict(sequence=7, vector=8, kind='hardware',
        **{'pre-cs':0x100, 'pre-eip':0x200, 'pre-ss':0x100, 'pre-sp':0xff00,
           'frame-sp':0xfefa, 'width':16, 'error-code-present':False, 'error-code':0,
           'pic-irq-valid':True, 'pic-controller':0, 'pic-irq':0, 'pic-vector':8,
           'pic-ack-sequence':1, 'pic-eoi-seen':False})]
    return saved


@pytest.mark.parametrize('mismatch', ['legacy-format','legacy-metadata','missing-command','wrong-policy'])
def test_api2_checkpoint_requires_scheduler_version_and_policy_fences(mismatch):
    session = _Session(); saved = _inflight_checkpoint(session)
    if mismatch == 'legacy-format': saved['format'] = 'fdisbull-native-dos-scheduler-1'
    elif mismatch == 'legacy-metadata': saved['metadata']['format'] = 'fdisbull-native-dos-scheduler-1'
    elif mismatch == 'missing-command': session.vm.qmp_commands.remove(COMMAND)
    else: saved['metadata']['preemption']['quantum'] = 2
    with pytest.raises(ValueError, match='fence|unsupported'):
        validate_scheduler(session, saved, session.binding['process_nonce'],
                           {'views':[{'binding':deepcopy(session.binding)}]}, session._process)


@pytest.mark.parametrize('controls_format,scheduler_format', [
    ('fdisbull-qemu-controls-task-4', IRQ_FORMAT),
    (CONTROLS_FORMAT, 'fdisbull-native-dos-scheduler-1'),
])
def test_control_format_fence_matches_scheduler_capability(controls_format, scheduler_format):
    session = _Session(); session.version = {'id':1, 'sha256':'v'}
    session._stopped = lambda: None
    session._dos_scheduler['format'] = scheduler_format
    controls = dict(format=controls_format,epoch=1,source_sha256='s',version=1,version_sha256='v',
                    task_identity=deepcopy(session.binding))
    with pytest.raises(ValueError, match='version-5 control fence'):
        restore_controls(session, controls, 1)


def test_consistent_inflight_irq_checkpoint_is_accepted():
    session = _Session(); saved = _inflight_checkpoint(session)
    validate_scheduler(session, saved, session.binding['process_nonce'],
                       {'views':[{'binding':deepcopy(session.binding)}]}, session._process)


def test_legacy_scheduler_cannot_hide_a_tagged_pic_frame():
    session = _Session(); saved = _inflight_checkpoint(session)
    saved['format'] = 'fdisbull-native-dos-scheduler-1'
    saved['metadata']['format'] = saved['format']
    saved['metadata'].pop('preemption')
    saved['native']['api-version'] = 1
    del saved['native']['preemption']
    with pytest.raises((ValueError, DebuggerError)):
        validate_scheduler(session, saved, session.binding['process_nonce'],
                           {'views':[{'binding':deepcopy(session.binding)}]}, session._process)


@pytest.mark.parametrize('field,value', [
    ('pic-irq-valid',False), ('pic-controller',1), ('pic-irq',1), ('pic-vector',9),
    ('pic-ack-sequence',2), ('pic-eoi-seen',True), ('sequence',8),
])
def test_inflight_checkpoint_requires_matching_unacknowledged_frame(field, value):
    session = _Session(); saved = _inflight_checkpoint(session)
    saved['contexts'][session.binding['task_id']]['frames'][0][field] = value
    with pytest.raises((ValueError, DebuggerError)):
        validate_scheduler(session, saved, session.binding['process_nonce'],
                           {'views':[{'binding':deepcopy(session.binding)}]}, session._process)


@pytest.mark.parametrize('arguments', [
    {'irq':2}, {'irq':8}, {'irq':True}, {'irq':-1},
    {'quantum':0}, {'quantum':65536}, {'quantum':True}, {'enabled':1},
])
def test_configuration_rejects_invalid_inputs_before_native_mutation(monkeypatch, arguments):
    import fdisbull.qemu_dos_scheduler as scheduler
    import fdisbull.qemu_dos_task_views as views
    session = _Session()
    session.vm.qmp_commands = set(session.vm.qmp_commands) | {'x-fdisbull-task-preemption-configure'}
    monkeypatch.setattr(views, '_preflight', lambda *_: None)
    monkeypatch.setattr(scheduler, '_status', lambda *_, **__: _status_v2(session))
    with pytest.raises(ValueError):
        QemuDOSSchedulerMixin.dos_task_preemption.__wrapped__(session, **arguments)
    assert not any(command == 'x-fdisbull-task-preemption-configure'
                   for command, _ in session.vm.qmp.calls)
    assert not session.closed


@pytest.mark.parametrize('failure,closed', [
    (DebuggerError('PRECONDITION: refused'),False),
    (DebuggerError('transport failure'),True),
    (TimeoutError('lost response'),True),
])
def test_configuration_failure_preserves_only_explicit_precondition(monkeypatch, failure, closed):
    import fdisbull.qemu_dos_scheduler as scheduler
    import fdisbull.qemu_dos_task_views as views
    session = _Session()
    session.vm.qmp_commands = set(session.vm.qmp_commands) | {'x-fdisbull-task-preemption-configure'}
    monkeypatch.setattr(views, '_preflight', lambda *_: None)
    monkeypatch.setattr(scheduler, '_status', lambda *_, **__: _status_v2(session))
    session.vm.qmp.failure = failure
    with pytest.raises(type(failure)):
        QemuDOSSchedulerMixin.dos_task_preemption.__wrapped__(session, irq=0, quantum=1, enabled=True)
    assert session.closed is closed


def test_reconfiguration_preserves_counters_and_resets_progress(monkeypatch):
    import fdisbull.qemu_dos_scheduler as scheduler
    import fdisbull.qemu_dos_task_views as views
    session = _Session()
    session.vm.qmp_commands = set(session.vm.qmp_commands) | {'x-fdisbull-task-preemption-configure'}
    before = _status_v2(session, enabled=True, quantum=4,
                        **{'quantum-progress':2, 'ack-count':8, 'eoi-count':8, 'preemption-count':3})
    after = deepcopy(before)
    after['preemption'].update(enabled=True, irq=0, quantum=2, **{'quantum-progress':0})
    calls = []
    monkeypatch.setattr(views, '_preflight', lambda *_: None)
    def status(*args, **kwargs):
        return before if not calls else after
    monkeypatch.setattr(scheduler, '_status', status)
    def qmp_call(command, arguments=None):
        calls.append((command, arguments))
        return deepcopy(after)
    session.vm.qmp.call = qmp_call
    session._event = lambda *args, **kwargs: None
    result = QemuDOSSchedulerMixin.dos_task_preemption.__wrapped__(session, irq=0, quantum=2, enabled=True)
    assert calls == [('x-fdisbull-task-preemption-configure', {'enabled':True, 'irq':0, 'quantum':2})]
    assert result['preemption']['quantum-progress'] == 0
    for key in ('ack-count','eoi-count','preemption-count'):
        assert result['preemption'][key] == before['preemption'][key]


def test_reconfiguration_counter_reset_closes_owner(monkeypatch):
    import fdisbull.qemu_dos_scheduler as scheduler
    import fdisbull.qemu_dos_task_views as views
    session = _Session()
    session.vm.qmp_commands = set(session.vm.qmp_commands) | {'x-fdisbull-task-preemption-configure'}
    before = _status_v2(session, enabled=True, **{'ack-count':3, 'eoi-count':3, 'preemption-count':1})
    after = _status_v2(session, enabled=True, quantum=2)
    monkeypatch.setattr(views, '_preflight', lambda *_: None)
    calls = []
    monkeypatch.setattr(scheduler, '_status', lambda *args, **kwargs: before if not calls else after)
    def qmp_call(*args, **kwargs):
        calls.append(args)
        return deepcopy(after)
    session.vm.qmp.call = qmp_call
    session._event = lambda *args, **kwargs: None
    with pytest.raises(DebuggerError):
        QemuDOSSchedulerMixin.dos_task_preemption.__wrapped__(session, irq=0, quantum=2, enabled=True)
    assert session.closed


def _admitted_api2(session, monkeypatch):
    import fdisbull.qemu_dos_scheduler as scheduler
    session._dos_scheduler['format'] = IRQ_FORMAT
    session._dos_scheduler['preemption'] = {'enabled':True,'irq':0,'quantum':1}
    session.vm.qmp_commands = set(session.vm.qmp_commands) | {COMMAND}
    session.vm.qmp.status = _status_v2(session, enabled=True,
        **{'ack-count':3,'eoi-count':3,'preemption-count':1})
    monkeypatch.setattr(scheduler, '_observe', lambda *_: {
        'selected-uuid':session.binding['monitor_uuid'],
        'selected-cookie':session.binding['cookie'],
        'selected-incarnation':session.binding['incarnation']})
    return scheduler


@pytest.mark.parametrize('bad', ['format','policy'])
def test_live_api2_status_requires_matching_admission(monkeypatch, bad):
    session = _Session(); scheduler = _admitted_api2(session, monkeypatch)
    if bad == 'format': session._dos_scheduler['format'] = 'fdisbull-native-dos-scheduler-1'
    else: session._dos_scheduler['preemption']['quantum'] = 2
    with pytest.raises(DebuggerError, match='admitted policy'):
        scheduler._status(session)


def test_live_preemption_counter_frontier_cannot_regress(monkeypatch):
    session = _Session(); scheduler = _admitted_api2(session, monkeypatch)
    scheduler._status(session)
    session.vm.qmp.status['preemption'].update({'ack-count':2,'eoi-count':2,'preemption-count':1})
    with pytest.raises(DebuggerError, match='regress'):
        scheduler._status(session)
