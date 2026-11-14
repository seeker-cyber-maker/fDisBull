"""State-machine checks; actual controller consumption has separate native witnesses."""
from copy import deepcopy
import time
from types import SimpleNamespace

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_input import QemuPhysicalInputMixin


class QMP:
    def __init__(self):
        self.running = False
        self.calls = []
        self.failure = None

    def call(self, method, arguments=None, **options):
        self.calls.append((method, deepcopy(arguments)))
        if method == 'query-status':
            return dict(running=self.running, status='running' if self.running else 'debug')
        assert method == 'input-send-event'
        if self.failure is not None:
            raise self.failure
        return {}


class Session(QemuPhysicalInputMixin):
    def __init__(self, vm=None):
        self.project = None
        self.run_id = 'authored-run'
        self.events = []
        self.vm = vm or SimpleNamespace(qmp=QMP(), qmp_commands={'input-send-event'}, closed=False)
        self.vm.close = self.close

    def close(self):
        self._input_on_close()
        self.vm.closed = True

    def _event(self, operation, value):
        self.events.append((operation, deepcopy(value)))

    def dispatch(self):
        return self._input_after_continue(time.monotonic() + 1)


def test_input_remains_python_owned_until_one_running_qmp_batch():
    session = Session()
    down = session.keyboard.key_down('esc')
    up = session.keyboard.key_up(down['lease'])
    assert down['key'] == 'escape' and down['delivery'] == up['delivery'] == 'python_pending'
    assert down['guest_consumed'] is None and up['guest_consumed'] is None
    assert session.input_state()['pending_edges'] == 2
    assert not any(method == 'input-send-event' for method, _ in session.vm.qmp.calls)
    stopped = session.dispatch()
    assert stopped['delivery'] == 'not_dispatched' and session._input_pending()
    session.vm.qmp.running = True
    accepted = session.dispatch()
    assert accepted['delivery'] == 'qmp_accepted' and accepted['guest_consumed'] is None
    calls = [args for method, args in session.vm.qmp.calls if method == 'input-send-event']
    assert calls == [{'events': [
        {'type': 'key', 'data': {'key': {'type': 'qcode', 'data': 'esc'}, 'down': True}},
        {'type': 'key', 'data': {'key': {'type': 'qcode', 'data': 'esc'}, 'down': False}},
    ]}]
    assert session.input_state()['leases'] == {} and not session._input_pending()
    assert session.dispatch()['delivery'] == 'not_dispatched'
    assert len([method for method, _ in session.vm.qmp.calls if method == 'input-send-event']) == 1


def test_lease_ownership_alias_duplicate_wrong_device_and_double_release():
    session, other = Session(), Session()
    down = session.keyboard_key_down('escape')
    with pytest.raises(ValueError, match='active lease'):
        session.keyboard_key_down('esc')
    with pytest.raises(ValueError, match='owned unused'):
        other.keyboard_key_up(down['lease'])
    with pytest.raises(ValueError, match='owned unused'):
        session.mouse_button_up(down['lease'])
    session.keyboard_key_up(down['lease'])
    with pytest.raises(ValueError, match='owned unused'):
        session.keyboard_key_up(down['lease'])
    assert session.input_state()['pending_edges'] == 2
    # A second view of the same owned VM shares leases and queue, not copies.
    same_vm = Session(session.vm)
    assert same_vm.input_state()['session_id'] == session.input_state()['session_id']
    assert same_vm.input_state()['pending_edges'] == 2


def test_cancelling_unsent_release_preserves_accepted_hold():
    session = Session()
    held = session.keyboard_key_down('ctrl')['lease']
    session.vm.qmp.running = True
    session.dispatch()
    session.vm.qmp.running = False
    session.keyboard_key_up(held)
    unsent = session.keyboard_key_down('a')['lease']
    session.mouse_move_relative(10, -3)
    cancelled = session.input_cancel_pending()
    assert cancelled['cancelled_edges'] == 4
    assert cancelled['cancelled_leases'] == [unsent]
    assert cancelled['retained_dispatched_holds'] == [held]
    state = session.input_state()
    assert state['pending_edges'] == 0
    assert state['leases'][held] == dict(device='keyboard', key='ctrl', make='qmp_accepted', release=None)
    session.keyboard_key_up(held)
    session.vm.qmp.running = True
    session.dispatch()
    assert session.input_state()['leases'] == {}


def test_mouse_events_are_relative_and_buttons_have_separate_owned_leases():
    session = Session()
    session.mouse_move_relative(7, -4)
    token = session.mouse_button_down('left')['lease']
    session.mouse_button_up(token)
    session.vm.qmp.running = True
    receipt = session.dispatch()
    events = session.vm.qmp.calls[-1][1]['events']
    assert events == [dict(type='rel', data=dict(axis='x', value=7)),
                      dict(type='rel', data=dict(axis='y', value=-4)),
                      dict(type='btn', data=dict(button='left', down=True)),
                      dict(type='btn', data=dict(button='left', down=False))]
    assert receipt['edge_count'] == 4 and receipt['guest_consumed'] is None


@pytest.mark.parametrize('dx,dy', [(True, 0), (1, 1.0), (32768, 0), (0, -32768), (0, 0), ('1', 0)])
def test_relative_validation_never_changes_queue(dx, dy):
    session = Session()
    before = session.input_state()
    with pytest.raises(ValueError):
        session.mouse_move_relative(dx, dy)
    assert session.input_state() == before and session.vm.qmp.calls == []


def test_complete_reservation_prevents_partial_two_axis_enqueue():
    session = Session()
    for _ in range(255):
        session.mouse_move_relative(1, 0)
    before = session.input_state()
    with pytest.raises(ValueError, match='256'):
        session.mouse_move_relative(1, 1)
    assert session.input_state() == before
    session.mouse_move_relative(0, 1)
    with pytest.raises(ValueError, match='256'):
        session.keyboard_key_down('a')
    assert session.input_state()['pending_edges'] == 256 and not session.input_state()['leases']


def test_active_lease_capacity_is_reserved_before_queuing():
    from fdisbull.keyboard_input import KEYS
    session = Session()
    keys = sorted(KEYS - {'esc'})
    for key in keys[:64]:
        session.keyboard_key_down(key)
    before = session.input_state()
    with pytest.raises(ValueError, match='64 active'):
        session.keyboard_key_down(keys[64])
    assert session.input_state() == before


def test_known_qmp_run_state_race_preserves_unsent_queue_without_retry():
    session = Session()
    session.keyboard_key_down('a')
    session.vm.qmp.running = True
    session.vm.qmp.failure = DebuggerError('QMP input-send-event: {"class":"GenericError","desc":"VM not running"}')
    receipt = session.dispatch()
    assert receipt['delivery'] == 'not_dispatched'
    assert session._input_pending() and not session.vm.closed
    assert len([method for method, _ in session.vm.qmp.calls if method == 'input-send-event']) == 1


@pytest.mark.parametrize('failure', [TimeoutError('lost reply'), DebuggerError('ambiguous error')])
def test_uncertain_dispatch_invalidates_all_ownership_closes_and_never_replays(failure):
    session = Session()
    token = session.keyboard_key_down('a')['lease']
    session.vm.qmp.running = True
    session.vm.qmp.failure = failure
    with pytest.raises(type(failure)):
        session.dispatch()
    state = session.input_state()
    assert not state['valid'] and state['pending_edges'] == 0 and state['leases'] == {}
    assert state['last_delivery']['delivery'] == 'delivery_unknown' and session.vm.closed
    with pytest.raises(ValueError, match='invalid'):
        session.keyboard_key_up(token)
    with pytest.raises(ValueError, match='invalid'):
        session.dispatch()
    assert len([method for method, _ in session.vm.qmp.calls if method == 'input-send-event']) == 1


def test_input_snapshot_is_detached_and_close_never_injects_release():
    session = Session()
    token = session.keyboard_key_down('a')['lease']
    snapshot = session.input_state()
    snapshot['leases'][token]['make'] = 'invented'
    snapshot['pending'].clear()
    assert session.input_state()['pending_edges'] == 1
    assert session.input_state()['leases'][token]['make'] == 'python_pending'
    calls = list(session.vm.qmp.calls)
    session.close()
    assert session.vm.qmp.calls == calls
    assert not session.input_state()['valid'] and session.input_state()['invalidated_leases'] == 1


def test_mutations_reject_caller_transaction_or_running_vm_before_queueing():
    session = Session()
    session.project = SimpleNamespace(db=SimpleNamespace(in_transaction=True))
    with pytest.raises(ValueError, match='caller-owned transaction'):
        session.keyboard_key_down('a')
    assert session.vm.qmp.calls == [] and not session._input_pending()
    session.project.db.in_transaction = False
    session.vm.qmp.running = True
    with pytest.raises(ValueError, match='Pause'):
        session.keyboard_key_down('a')
    assert not session._input_pending()


def test_project_queue_and_dispatch_events_are_persisted_and_failure_closes():
    session = Session()
    session.project = SimpleNamespace(db=SimpleNamespace(in_transaction=False))
    session.keyboard_key_down('a')
    assert session.events[-1][0] == 'keyboard.key_down'
    session.vm.qmp.running = True
    session.dispatch()
    assert session.events[-1][0] == 'input.dispatch'
    assert session.events[-1][1]['delivery'] == 'qmp_accepted'
    session.vm.qmp.running = False
    def broken_event(*args):
        raise OSError('disk full')
    session._event = broken_event
    with pytest.raises(OSError, match='disk full'):
        session.mouse_button_down('left')
    assert session.vm.closed and not session.input_state()['valid']


def test_persistence_failure_after_qmp_acceptance_does_not_leave_live_unrecorded_input():
    session = Session()
    session.project = SimpleNamespace(db=SimpleNamespace(in_transaction=False))
    session.keyboard_key_down('a')
    session.vm.qmp.running = True
    def broken_event(*args):
        raise OSError('disk full after dispatch')
    session._event = broken_event
    with pytest.raises(OSError, match='disk full after dispatch'):
        session.dispatch()
    state = session.input_state()
    assert not state['valid'] and session.vm.closed and state['pending_edges'] == 0
    assert state['last_delivery']['delivery'] == 'qmp_accepted'
    assert state['invalidated_leases'] == 1
    assert len([method for method, _ in session.vm.qmp.calls if method == 'input-send-event']) == 1


def test_expired_dispatch_deadline_does_not_query_resume_or_send_input():
    session = Session()
    session.keyboard_key_down('a')
    calls = list(session.vm.qmp.calls)
    receipt = session._input_after_continue(time.monotonic() - 1)
    assert receipt['delivery'] == 'not_dispatched' and session._input_pending()
    assert session.vm.qmp.calls == calls and not session.vm.closed


def test_timed_input_explicitly_refused_without_mutation():
    session = Session()
    for operation in (lambda: session.keyboard.press('a'), lambda: session.keyboard.type('hello')):
        with pytest.raises(ValueError, match='guest-time control'):
            operation()
    assert session.vm.qmp.calls == [] and not session._input_pending()
