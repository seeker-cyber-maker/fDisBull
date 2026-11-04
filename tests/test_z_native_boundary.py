import pytest

from fdisbull.z_dos import reach_flat32_boundary
from fdisbull.dosbox_rpc import DebuggerError


class Session:
    def __init__(self, *, mode='real', foreign=False, never_qualifies=False):
        self.mode = mode
        self.foreign = foreign
        self.never_qualifies = never_qualifies
        self.armed = False
        self.at_boundary = False
        self.events = []

    def registers(self):
        return {'cpu_mode': self.mode, 'flags': '0x202',
                'segments': {'cs': '0x0150' if self.mode == 'protected' else '0xC402'},
                'instruction_pointer': '0x001D99BE' if self.at_boundary else '0x0000001D'}

    def call(self, method, params):
        self.events.append((method, params))
        if method == 'breakpoints.create':
            # Real/v8086 registration would freeze the wrong physical address.
            assert self.mode == 'protected'
            assert params['address']['offset'] == '0x001D99BE'
            self.armed = True
            return {'breakpoint_id': 'owned'}
        return {}

    def run(self, **kwargs):
        self.events.append(('run', kwargs))
        if self.armed:
            self.at_boundary = True
            return {'stop': {'trigger': 'breakpoint'},
                    'session': {'stop_reason': {'breakpoint_id': 'other' if self.foreign else 'owned'}}}
        if not self.never_qualifies:
            self.mode = 'protected'
        return {'stop': {'trigger': 'guest_time'}, 'guest_elapsed_ms': 10}


def test_transient_real_service_is_left_before_protected_breakpoint_registration():
    session = Session()
    result = reach_flat32_boundary(session, 0x1D99BE, 0x150)
    assert result['initial']['cpu_mode'] == 'real'
    assert result['qualification_guest_ms'] == 10
    assert result['registers']['instruction_pointer'] == '0x001D99BE'
    assert [op for op, _ in session.events] == ['run', 'breakpoints.create', 'run']


def test_qualification_exhaustion_never_arms_wrong_mode_breakpoint():
    session = Session(never_qualifies=True)
    with pytest.raises(RuntimeError, match='selector not reached'):
        reach_flat32_boundary(session, 0x1D99BE, 0x150, qualification_guest_ms=20)
    assert [op for op, _ in session.events] == ['run', 'run']


def test_foreign_breakpoint_at_same_pc_is_not_success_and_only_owned_bp_is_removed():
    session = Session(mode='protected', foreign=True)
    with pytest.raises(RuntimeError, match='boundary not reached'):
        reach_flat32_boundary(session, 0x1D99BE, 0x150)
    assert session.events[-1] == ('breakpoints.delete', {'breakpoint_id': 'owned'})


def test_already_qualified_boundary_does_not_run_or_arm_again():
    session = Session(mode='protected')
    session.at_boundary = True
    result = reach_flat32_boundary(session, 0x1D99BE, 0x150)
    assert result['already_at_boundary'] and not session.events


def test_phase_locked_fast_forward_qualification_gets_short_normal_probe():
    class PhaseLocked(Session):
        def run(self, **kwargs):
            if not self.armed and kwargs['fast_forward']:
                self.events.append(('run', kwargs))
                return {'stop': {'trigger': 'guest_time'}, 'guest_elapsed_ms': kwargs['guest_ms']}
            return super().run(**kwargs)
    session = PhaseLocked()
    reached = reach_flat32_boundary(session, 0x1D99BE, 0x150, qualification_guest_ms=100)
    assert reached['qualification_guest_ms'] == 80  # reported elapsed wins over requested 1 ms
    samples = [params for op, params in session.events if op == 'run']
    assert samples[7]['guest_ms'] == 1 and not samples[7]['fast_forward']


def test_consumed_temporary_native_breakpoint_does_not_mask_a_foreign_stop():
    session = Session(mode='protected', foreign=True)
    original = session.call

    def call(method, params):
        if method == 'breakpoints.delete':
            session.events.append((method, params))
            assert params == {'breakpoint_id': 'owned'}
            raise DebuggerError('Breakpoint no longer exists in the debugger (BREAKPOINT_NOT_FOUND)')
        return original(method, params)

    session.call = call
    with pytest.raises(RuntimeError, match='flat32 boundary not reached') as error:
        reach_flat32_boundary(session, 0x1D99BE, 0x150)
    assert 'observed_breakpoint=other' in str(error.value)
    assert session.events == [
        ('breakpoints.create', {'kind': 'execution', 'once': True,
                                'address': {'space': 'segmented', 'segment': '0x0150', 'offset': '0x001D99BE'}}),
        ('run', session.events[1][1]),
        ('breakpoints.delete', {'breakpoint_id': 'owned'}),
    ]
