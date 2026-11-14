"""Step policy is observed explicitly; a mask never proves retirement."""
from types import SimpleNamespace

import pytest

from fdisbull.debug_semantics import contract, normalize_trace
from fdisbull.qemu_step_policy import observe_step_policy


class Remote:
    def __init__(self, bits=b'ENABLE=1,NOIRQ=2,NOTIMER=4', mask=b'0x7'):
        self.replies = {'qqemu.sstepbits': bits, 'qqemu.sstep': mask}
        self.commands = []

    def request(self, command, **options):
        self.commands.append((command, options))
        return self.replies[command]


@pytest.mark.parametrize('mask,enabled,irqs,timers', [
    (b'0x7', True, True, True),
    (b'0x5', True, False, True),
    (b'0x1', True, False, False),
    (b'0x0', False, False, False),
])
def test_known_masks_are_reported_without_mutation(mask, enabled, irqs, timers):
    remote = Remote(mask=mask)
    observed = observe_step_policy(remote)
    assert observed['status'] == 'observed'
    assert observed['bits'] == {'ENABLE': 1, 'NOIRQ': 2, 'NOTIMER': 4}
    assert observed['mask'] == int(mask, 16)
    assert observed['enabled'] is enabled
    assert observed['interrupts_masked'] is irqs
    assert observed['timers_masked'] is timers
    assert observed['unknown_mask'] == 0 and observed['changed'] is False
    assert [command for command, _ in remote.commands] == ['qqemu.sstepbits', 'qqemu.sstep']
    assert observed['raw_replies']['mask']['hex'] == mask.hex()


@pytest.mark.parametrize('bits,mask,status,query_count', [
    (b'', b'0x7', 'unsupported', 1),
    (b'ENABLE=1,NOIRQ=2,NOTIMER=4', b'', 'unsupported', 2),
    (b'ENABLE=1,ENABLE=2,NOTIMER=4', b'0x7', 'unknown', 1),
    (b'ENABLE=1,NOIRQ=1,NOTIMER=4', b'0x7', 'unknown', 1),
    (b'ENABLE=0,NOIRQ=2,NOTIMER=4', b'0x7', 'unknown', 1),
    (b'ENABLE=3,NOIRQ=2,NOTIMER=4', b'0x7', 'unknown', 1),
    (b'ENABLE=1', b'0x1', 'unknown', 2),
    (b'ENABLE=1,NOIRQ=2,NOTIMER=4', b'0xf', 'unknown', 2),
    (b'ENABLE=1,NOIRQ=2,NOTIMER=4,NEW=8', b'0xf', 'unknown', 2),
    (b'ENABLE=1,NOIRQ=2,NOTIMER=4', b'7', 'unknown', 2),
    (b'ENABLE=1,NOIRQ=2,NOTIMER=4', b'0x100000000', 'unknown', 2),
    (b'\xff', b'0x7', 'unknown', 1),
    (b'x' * 257, b'0x7', 'unknown', 1),
    (None, b'0x7', 'unknown', 1),
])
def test_unknown_and_unsupported_replies_are_explicit(bits, mask, status, query_count):
    remote = Remote(bits, mask)
    observed = observe_step_policy(remote)
    assert observed['status'] == status and observed['reason']
    assert len(remote.commands) == query_count
    assert observed['changed'] is False
    assert all(command.startswith('qqemu.') for command, _ in remote.commands)
    for reply in observed['raw_replies'].values():
        assert len(reply['hex']) <= 512


def test_queries_share_one_deadline_and_never_retry_a_transport_failure(monkeypatch):
    from fdisbull import qemu_step_policy as implementation
    clock = [1.0]
    monkeypatch.setattr(implementation.time, 'monotonic', lambda: clock[0])
    remote = Remote()
    request = remote.request

    def delayed(command, **options):
        result = request(command, **options)
        clock[0] += 0.3
        return result

    remote.request = delayed
    assert observe_step_policy(remote, timeout_ms=1000)['status'] == 'observed'
    assert remote.commands[0][1]['timeout_ms'] == 1000
    assert 699 <= remote.commands[1][1]['timeout_ms'] <= 700
    calls = []

    def failed(command, **options):
        calls.append(command)
        raise TimeoutError('lost reply')

    with pytest.raises(TimeoutError, match='lost reply'):
        observe_step_policy(SimpleNamespace(request=failed))
    assert calls == ['qqemu.sstepbits']


def test_deadline_expiring_after_first_reply_does_not_dispatch_second_query(monkeypatch):
    from fdisbull import qemu_step_policy as implementation
    clock = [1.0]
    monkeypatch.setattr(implementation.time, 'monotonic', lambda: clock[0])
    remote = Remote()
    request = remote.request

    def delayed(command, **options):
        result = request(command, **options)
        clock[0] += 1
        return result

    remote.request = delayed
    with pytest.raises(TimeoutError, match='deadline'):
        observe_step_policy(remote, timeout_ms=1000)
    assert [command for command, _ in remote.commands] == ['qqemu.sstepbits']


@pytest.mark.parametrize('timeout', [0, -1, 600001, True, 1.5])
def test_bad_budget_refuses_before_query(timeout):
    remote = Remote()
    with pytest.raises(ValueError, match='timeout'):
        observe_step_policy(remote, timeout_ms=timeout)
    assert remote.commands == []


@pytest.mark.parametrize('backend', ['qemu-machine', 'qemu-dos'])
def test_native_step_completion_is_not_inferred_from_a_debug_stop(backend):
    events = [{'address': '0x7c00', 'bytes': 'f6f3'}]
    normalize_trace(backend, events, version=1)
    assert events[0]['observation']['instruction_completed'] is None
    assert 'unknown' in contract(backend)['trace_completion']
    # Keep the qualified PE and DOSBox contracts independent of this change.
    pe = [{'address': '0x140001000', 'bytes': '90'}]
    normalize_trace('wine-qemu', pe, version=1)
    assert pe[0]['observation']['instruction_completed'] is True
