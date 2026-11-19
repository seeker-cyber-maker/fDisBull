from copy import deepcopy
import time

import pytest

from test_qemu_dos_source_admission import owned
from test_qemu_runtime_memory import ram
from test_qemu_movement import moving, options


def test_two_distinct_held_leases_release_in_reverse_order(moving):
    o, s = moving, moving.session
    identifier = o.project.debug_define_macros(dict(
        format='fdisbull-macro-set-1', name='independent-chord', macros={
            'start': dict(steps=[dict(op='keyboard.key-down', key='a', **{'as': 'first'}),
                                dict(op='keyboard.key-down', key='b', **{'as': 'second'})],
                          outputs=dict(a='$first.lease', b='$second.lease')),
            'stop': dict(parameters={'a': {'type': 'input-lease'}, 'b': {'type': 'input-lease'}},
                         steps=[dict(op='keyboard.key-up', lease='$args.b'),
                                dict(op='keyboard.key-up', lease='$args.a')]),
        }))['id']
    selected = options(identifier)
    selected['stop']['args'] = dict(a='$start.outputs.a', b='$start.outputs.b')
    result = s.move(**selected)
    assert result['ok'] and result['cleanup']['settled']
    assert len(o.arms) == 2 and all(len(x['sequences']) == 2 for x in o.arms)
    assert [x['event']['data']['down'] for x in o.deliveries] == [True, True, False, False]
    assert not s.input_state()['leases'] and not s._input_pending()


def test_native_arm_failure_keeps_receipt_without_any_advance(moving):
    o, s = moving, moving.session
    primary = TimeoutError('Independent ambiguous native arm reply')
    primary.result = dict(token='owned-arm', state='outcome_unknown')
    def failed(delta_ns):
        assert delta_ns > 0
        raise primary
    s.input_schedule = failed
    with pytest.raises(TimeoutError) as caught:
        s.move(**options(o.identifier))
    assert caught.value is primary and primary.result['token'] == 'owned-arm'
    assert primary.movement_result['failure_result'] is primary.result
    assert not o.runs and not o.deliveries and o.closed


def test_epoch_change_after_first_advance_closes_without_a_release(moving):
    o, s = moving, moving.session
    advance = s._clock_advance_with_hooks
    def changed(*args, **kwargs):
        result = advance(*args, **kwargs)
        s._runtime_epoch += ':independent-change'
        return result
    s._clock_advance_with_hooks = changed
    result = s.move(**options(o.identifier))
    assert not result['ok'] and result['error_type'] == 'ValueError'
    assert len(o.runs) == 1 and len(o.arms) == 1 and len(o.deliveries) == 1
    assert o.closed and 'changed' in result['error']


def test_late_publication_retains_result_and_closes(moving):
    o, s = moving, moving.session
    original = s._artifact
    def late(name, *args, **kwargs):
        result = original(name, *args, **kwargs)
        if name == 'movement-result.json':
            time.sleep(0.15)
        return result
    s._artifact = late
    with pytest.raises(TimeoutError) as caught:
        s.move(**dict(options(o.identifier), timeout_ms=100))
    result = caught.value.result
    assert result['outcome'] == 'arrived' and result['cleanup']['settled']
    assert o.closed and not s._input_pending()
