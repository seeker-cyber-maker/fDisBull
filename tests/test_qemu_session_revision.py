"""Session-control revisions at real bound protocol dispatch boundaries."""
from types import SimpleNamespace

import pytest

from fdisbull.qemu_machine import MachineContext, _machine_operation_guard
from fdisbull.qemu_session_revision import session_revision
from test_qemu_observation_authority import owned
from test_qemu_operation_deadlines import packet


def revision(o):
    return session_revision(o.vm).snapshot()['state_revision']


def test_passive_public_and_bound_reads_keep_revision_but_not_conservative_generation(owned):
    o = owned
    before = revision(o)
    generation = o.authority.control_generation
    for operation in ('status', 'frame_probe', 'frame_rgba', 'registers', 'memory'):
        _machine_operation_guard(o.vm, operation)
    assert o.qmp.call('query-status') == {'running': False}
    assert o.gdb.registers() == {'eax': '0x0'}
    assert o.gdb.memory(0x2000, 80) == bytes(80)
    assert o.gwire.mode == b'0'
    assert revision(o) == before
    assert o.authority.control_generation > generation


@pytest.mark.parametrize('operation', [
    lambda o: o.qmp.call('cont'),
    lambda o: o.qmp.call('query-not-a-known-read'),
    lambda o: o.qmp.call('query-status', {'unexpected': True}),
    lambda o: o.qmp.call('human-monitor-command', {'command-line': 'stop'}),
    lambda o: o.gdb.request('P0=00000000'),
    lambda o: o.gdb.request('M2000,1:00'),
    lambda o: o.gdb.request('Qqemu.PhyMemMode:1'),
])
def test_effectful_bound_admissions_include_unchanged_memory_and_register_bytes(owned, operation):
    o = owned
    before = revision(o)
    operation(o)
    assert revision(o) > before


@pytest.mark.parametrize('name,args,kwargs', [
    ('keyboard_key_down', ('a',), {}), ('keyboard_key_up', ('lease',), {}),
    ('input_schedule', (1000,), {}), ('input_cancel_pending', (), {}),
    ('layers', ([],), {}), ('layer_enable', ('layer',), {'enabled': True}),
    ('write_memory', (0x2000, '00'), {'expected_hex': '00'}),
    ('write_registers', ({'eax': {'expected': 0, 'value': 0}},), {}),
    ('video_frame_start', (), {}), ('video_frame_stop', (), {}),
    ('breakpoint', (0x2000,), {}), ('delete_breakpoint', ('bp',), {}),
])
def test_public_control_admission_changes_revision_even_before_native_dispatch(owned, name, args, kwargs):
    o = owned
    before = revision(o)
    _machine_operation_guard(o.vm, name, args, kwargs)
    assert revision(o) > before
    assert not o.qwire.requests and not o.gwire.requests


def test_passive_layer_schemas_and_positional_none_are_stable(owned):
    o = owned
    before = revision(o)
    for args, kwargs in (((), {}), ((None,), {}), ((), {'active': None})):
        _machine_operation_guard(o.vm, 'layers', args, kwargs)
    o.qmp.call('x-fdisbull-layer-observe')
    o.qmp.call('x-fdisbull-layer-observe', {'address': 0x2000, 'length': 16})
    assert revision(o) == before
    o.qmp.call('x-fdisbull-layer-observe', {'address': True, 'length': 16})
    assert revision(o) > before


@pytest.mark.parametrize('command,params', [
    ('x-fdisbull-probe-video-frame', {'token': 'owned', 'frame-id': 1, 'points': [{'x': True, 'y': 0}]}),
    ('x-fdisbull-probe-video-frame', {'token': 'owned', 'frame-id': 1, 'points': [{'x': 0, 'y': 0}] * 257}),
    ('x-fdisbull-probe-video-frame', {'token': 'owned', 'frame-id': 0, 'points': []}),
    ('x-fdisbull-export-video-frame', {'token': 'owned', 'frame-id': 1, 'filename': '/unowned/output.ppm'}),
])
def test_malformed_or_unowned_read_selectors_are_not_silently_exempt(owned, command, params):
    o = owned
    before = revision(o)
    o.qmp.call(command, params)
    assert revision(o) > before


def test_effect_revision_precedes_uncertain_send(owned):
    o = owned
    before = revision(o)
    observed = []
    def broken_send(data):
        observed.append(revision(o))
        raise OSError('partial write')
    o.gwire.sendall = broken_send
    with pytest.raises(OSError, match='partial write'):
        o.gdb.request('M2000,1:00')
    assert observed and observed[0] > before
    assert o.gdb.socket is None


@pytest.mark.parametrize('protocol', ['qmp', 'gdb'])
def test_bound_channel_close_invalidates_session_control_identity(owned, protocol):
    o = owned
    before = revision(o)
    getattr(o, protocol).close()
    assert revision(o) > before


def test_failed_read_selector_restore_changes_revision_even_without_guest_write(owned):
    o = owned
    before = revision(o)
    send = o.gwire.sendall
    def fail_restore(data):
        if data.startswith(b'$Qqemu.PhyMemMode:0#'):
            raise OSError('selector restoration failed')
        return send(data)
    o.gwire.sendall = fail_restore
    with pytest.raises(OSError, match='selector restoration failed'):
        o.gdb.memory(0x2000, 1, space='physical')
    assert o.gdb.socket is None and revision(o) > before


def test_actual_guarded_same_byte_memory_write_changes_public_revision(owned):
    o = owned
    o.vm.debugger = lambda: o.gdb
    context = MachineContext(o.vm)
    o.vm.context = context
    send = o.gwire.sendall
    def acknowledge_write(data):
        if data.startswith(b'$M'):
            o.gwire.requests.append(data[1:-3])
            o.gwire.buffer.extend(packet(b'OK'))
            o.gwire.pending_delay = 0
            return
        send(data)
    o.gwire.sendall = acknowledge_write
    before = context.status()
    result = context.write_memory(0x2000, '00', expected_hex='00')
    after = context.status()
    assert result['before_hex'] == result['after_hex'] == '00'
    assert before['session_id'] == after['session_id']
    assert after['state_revision'] > before['state_revision']
    assert b'M2000,1:00' in o.gwire.requests


def test_new_owner_has_new_session_and_mode_namespace(owned):
    o = owned
    context = MachineContext(o.vm)
    old = context.session_id
    first = session_revision(o.vm)
    assert first.mode(('epoch-1', 'stream-1')) == first.mode(('epoch-1', 'stream-1')) == 1
    assert first.mode(('epoch-2', 'stream-1')) == 2
    assert first.mode(('epoch-1', 'stream-1')) == 3
    replacement = SimpleNamespace()
    context.vm = replacement
    assert context.session_id != old
    assert session_revision(replacement).snapshot()['state_revision'] == 0
    assert session_revision(replacement).mode(('epoch-1', 'stream-1')) == 1
