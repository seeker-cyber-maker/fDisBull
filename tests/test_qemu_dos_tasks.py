"""Host policy for the cooperating monitor task observation protocol."""
from copy import deepcopy
import struct
from types import SimpleNamespace

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_checkpoint_controls import restore_controls
from fdisbull.qemu_dos_tasks import COMMAND, FORMAT, MODEL, _CONTEXT_FIELDS, observe_task


MONITOR = '12' * 16
NONCE = '34' * 16


def _binding(*, nonce=NONCE):
    return dict(format=FORMAT, anchor_address=0x5000, monitor_uuid=MONITOR,
                cookie=7, incarnation=3, process_nonce=nonce)


def _receipt(*, sequence=2, cookie=7, incarnation=3, generation=1,
             epoch=1, state=1, reserved=0, magic=b'FDBTASK1'):
    context = {name: 0 for name in _CONTEXT_FIELDS if name != 'mode'}
    anchor = magic + bytes.fromhex(MONITOR) + struct.pack(
        '<QQQII', sequence, cookie, incarnation, state, reserved)
    return dict(context, **{'api-version': 1, 'model': MODEL, 'cpu-index': 0,
        'mode': 'v86', 'epoch': epoch, 'context-generation': generation,
        'anchor-address': 0x5000, 'anchor-hex': anchor.hex()})


class _Qmp:
    def __init__(self, receipt):
        self.receipt = receipt
        self.calls = []

    def call(self, command, arguments=None):
        self.calls.append((command, arguments))
        return deepcopy(self.receipt)


def _session(receipt=None, binding=None):
    qmp = _Qmp(_receipt() if receipt is None else receipt)
    vm = SimpleNamespace(qmp=qmp, qmp_commands={COMMAND}, machine_configuration={'memory_mib': 32})
    class Session:
        run_id = 'run-a'
        _dos_task_binding = binding
        def _layer_epoch(self): return 9
    session = Session()
    session.vm = vm
    return session


def test_monitor_task_a_b_a_has_stable_lifetime_and_distinct_b():
    session = _session(binding=_binding())
    a = observe_task(session)
    session.vm.qmp.receipt = _receipt(sequence=4, cookie=8, generation=2)
    b = observe_task(session)
    session.vm.qmp.receipt = _receipt(sequence=6, generation=3)
    a_again = observe_task(session)
    assert (a['matches_binding'], b['matches_binding'], a_again['matches_binding']) == (True, False, True)
    assert a['task_id'] == a_again['task_id'] != b['task_id']
    assert [a['scheduler_generation'], b['scheduler_generation'], a_again['scheduler_generation']] == [2, 4, 6]
    assert session.vm.qmp.calls == [(COMMAND, {'anchor-address': 0x5000})] * 6


@pytest.mark.parametrize('changed', [dict(sequence=2, generation=4), dict(sequence=6, generation=2),
                                     dict(sequence=6, generation=4, epoch=2)])
def test_monitor_task_rejects_regressing_fences_or_new_native_epoch(changed):
    session = _session(_receipt(sequence=4, generation=3), _binding())
    observe_task(session)
    session.vm.qmp.receipt = _receipt(**changed)
    with pytest.raises(DebuggerError, match='epoch changed or task observation regressed'):
        observe_task(session)


@pytest.mark.parametrize('changes', [dict(sequence=3), dict(cookie=0), dict(incarnation=0),
                                    dict(state=0), dict(reserved=1), dict(magic=b'BADTASK1')])
def test_monitor_task_rejects_invalid_or_in_progress_anchor(changes):
    session = _session(_receipt(**changes), _binding())
    with pytest.raises(ValueError, match='anchor|transition|lifetime'):
        observe_task(session)


def test_monitor_task_process_nonce_separates_lifetimes():
    a = observe_task(_session(binding=_binding()))
    other = observe_task(_session(binding=_binding(nonce='56' * 16)))
    assert a['matches_binding'] and other['matches_binding']
    assert a['task_id'] != other['task_id']


def test_task_lifetime_change_requires_scheduler_transition():
    session = _session(binding=_binding())
    observe_task(session)
    session.vm.qmp.receipt = _receipt(cookie=8, generation=2)
    with pytest.raises(DebuggerError, match='without a scheduler generation transition'):
        observe_task(session)


@pytest.mark.parametrize('mode', ['real', 'protected', 'v86'])
def test_source_view_refuses_foreign_bound_task_before_source_access(mode):
    from fdisbull.qemu_layers import QemuLayerSessionMixin
    session = _session(_receipt(sequence=4, cookie=8), _binding())
    session._process = {'source_mapping': {}}
    with pytest.raises(ValueError, match='differs from the bound task lifetime'):
        QemuLayerSessionMixin._layer_source_address(session, 0x100, 1, {'cpu_mode': mode}, None)


def test_source_trace_refuses_foreign_task_before_ownership_reads():
    from fdisbull.qemu_dos_trace import _ownership
    session = _session(_receipt(sequence=4, cookie=8), _binding())
    session._process = dict(state='active', source_mapping={'live': True}, capture_epoch=9)
    session._runtime_epoch = 9
    session.closed = False
    session.vm.process = SimpleNamespace(poll=lambda: None)
    def no_read(*args):
        pytest.fail('Foreign source ownership must fail before reading task memory')
    session._read = no_read
    with pytest.raises(ValueError, match='differs from the bound task lifetime'):
        _ownership(session, {'capture_epoch': 9})


@pytest.mark.parametrize('change, message', [
    ({'task_identity': None}, 'Legacy checkpoint controls'),
    ({'hooks': [{'task_identity': None}]}, 'Legacy checkpoint controls'),
    ({'definitions': {'layer': {'native_binding': {'task_identity': None}}}}, 'Legacy checkpoint controls'),
    ({'format': 'fdisbull-qemu-controls-task-2'}, 'require a task binding'),
])
def test_checkpoint_control_format_fence(change, message):
    class Session:
        project = SimpleNamespace(db=SimpleNamespace(in_transaction=False))
        metadata = {'source_sha256': 's'}
        version = {'id': 1, 'sha256': 'v'}
        _dos_task_binding = None
        def _stopped(self): return None
    controls = dict(format='fdisbull-qemu-controls-1', epoch=1, source_sha256='s',
                    version=1, version_sha256='v', definitions={}, hooks=[])
    controls.update(change)
    with pytest.raises(ValueError, match=message):
        restore_controls(Session(), controls, 1)
