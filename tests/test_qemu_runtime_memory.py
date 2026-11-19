"""Runtime RAM contracts through public QEMU methods and real FDB storage.

Only the native QMP/GDB boundary is supplied. Protected CPU observations reuse
the authored LE fixture; restore coverage uses the actual owned-machine loader.
"""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from fdisbull.cli import respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.runtime_observations import RuntimeMemoryWriteError
from test_qemu_dos_source_admission import owned
from test_qemu_owned_checkpoint import runtime as checkpoint_runtime


ADDRESS = 0x240010


@pytest.fixture
def ram(owned):
    o, s, peer = owned, owned.session, owned.peer
    s.vm.context = s
    s._staging = None
    s._checkpoint_epoch = 0
    s.capabilities = dict(code_layers=False, runtime_memory_bindings=True)
    s._launching, s._return_breakpoint = True, None
    o.ram = bytearray(b'AB\x12\x34' + bytes(60))
    o.writes, o.reads, o.deadlines = [], [], []
    o.after_read = o.after_write = None
    o.write_fault = None
    original = peer.memory

    def memory(address, length, *, space, timeout_ms=10000, data=None):
        o.deadlines.append((getattr(s, '_rpc_deadline', None), s._deadline, s.vm.operation_deadline,
                            peer.operation_deadline))
        if ADDRESS <= address and address + length <= ADDRESS + len(o.ram):
            offset = address - ADDRESS
            if data is not None:
                o.writes.append((address, bytes(data), space))
                o.ram[offset:offset+length] = data
                if o.after_write is not None:
                    o.after_write()
                if o.write_fault == 'timeout':
                    raise TimeoutError('Authored acknowledgement loss after write')
                if o.write_fault == 'corrupt':
                    o.ram[offset] ^= 0xff
            else:
                o.reads.append((address, length, space))
            value = bytes(o.ram[offset:offset+length])
            callback, o.after_read = o.after_read, None
            if data is None and callback is not None:
                callback()
            return value
        assert data is None, 'Unexpected native write outside authored RAM'
        return original(address, length, space=space, timeout_ms=timeout_ms)

    peer.memory = memory
    return o


def bind(o, *, space='linear', **changes):
    options = dict(name='allocation', address=ADDRESS, length=4, expected_hex='4142',
                   provenance={'source': 'authored RAM witness'}, space=space)
    return o.session.bind_runtime_memory(**dict(options, **changes))


def event_count(o, operation):
    return o.project.db.execute('SELECT count(*) FROM debug_events WHERE operation=?',
                               (operation,)).fetchone()[0]


@pytest.mark.parametrize('space', ['linear', 'physical'])
def test_public_bind_read_write_preserves_ram_contract_and_never_infers_source(ram, space):
    o, s = ram, ram.session
    before = deepcopy(s._process)
    workspace = DebugWorkspace()
    workspace.sessions[s.run_id] = s
    def call(method, **params):
        response = respond(dict(method=method, params=dict(project=str(o.project.path),
                           run=s.run_id, **params)), debugger=workspace)
        assert response['ok'], response
        return response['result']
    try:
        bound = call('debug-bind-runtime-memory', name='allocation', address=ADDRESS, length=4,
                     expected_hex='4142', provenance='authored', space=space)
        read = call('debug-runtime-memory', binding=bound['id'], offset=2, length=2)
        changed = call('debug-write-runtime-memory', binding='allocation', data_hex='aabb',
                       expected_hex='1234', offset=2)
    finally:
        workspace.sessions.clear()
    assert read['hex'] == '1234' and read['witness_hex'] == '4142'
    assert bound['identity']['runtime_load'] is None and bound['observed_cpu_mode'] == 'protected'
    assert bound['identity']['epoch'] == s._runtime_epoch
    assert bound['identity']['memory_context']['space'] == space
    assert 'no source, selector, task or allocation lifetime inference' in bound['mapping_claim']
    assert s._process == before
    assert changed['verified'] and changed['dispatch_outcome'] == 'readback-verified'
    assert not changed['state_restore_used'] and not changed['frame_presentation_verified']
    assert not changed['binding_invalidated'] and not s.closed
    assert s.runtime_memory(bound['id'], offset=2, length=2)['hex'] == 'aabb'
    assert o.writes == [(ADDRESS + 2, b'\xaa\xbb', 'virtual' if space == 'linear' else 'physical')]
    assert event_count(o, 'runtime-memory-bind') == event_count(o, 'runtime-memory-write') == 1


def test_flat_protected_le_source_remains_separate_and_write_retires_its_authority(ram):
    o, s = ram, ram.session
    source = s.dos_source_bind()
    assert source['live']
    item = bind(o)
    assert item['identity']['memory_context'] == dict(space='linear', cpu_mode='protected',
                                                    paging_enabled=False, a20_enabled=True)
    assert s.dos_source_binding()['live']
    s.write_runtime_memory(item['id'], 'aabb', expected_hex='1234', offset=2)
    assert s.dos_source_binding()['state'] == 'retired'


@pytest.mark.parametrize('changes', [
    dict(name='../outside'), dict(address=True), dict(address=0xffffffff, length=2),
    dict(length=0), dict(length=65537), dict(expected_hex=''), dict(mask_hex='0000'),
    dict(mask_hex='ff'), dict(expected_hex='zz'), dict(provenance={}),
    dict(provenance='x' * 65537), dict(space='virtual'),
])
def test_invalid_literal_binding_refuses_before_any_native_call(ram, changes):
    before = list(ram.peer.qmp_calls)
    with pytest.raises((ValueError, TypeError)):
        bind(ram, **changes)
    assert ram.peer.qmp_calls == before and not ram.reads and not ram.writes
    assert not getattr(ram.session, '_runtime_bindings', {})


@pytest.mark.parametrize('case', ['paged', 'a20-unknown', 'cpu-mismatch', 'rom', 'past-ram'])
def test_unqualified_linear_context_and_device_ranges_refuse_before_bytes(ram, case):
    o, options = ram, {}
    monitor = o.peer.monitor
    if case == 'paged':
        o.peer.monitor = lambda: monitor().replace('CR0=00000001', 'CR0=80000001')
    elif case == 'a20-unknown':
        o.peer.monitor = lambda: monitor().replace(' A20=1', '')
    elif case == 'cpu-mismatch':
        o.peer.monitor = lambda: monitor().replace('EIP=00050040', 'EIP=00050041')
    elif case == 'rom':
        options['address'] = 0xa0000
    else:
        options['address'] = 16 << 20
    with pytest.raises(ValueError):
        bind(o, **options)
    assert not o.reads and not o.peer.reads and not o.writes


@pytest.mark.parametrize('field,value', [
    ('_layer_active', ['layer']), ('_layer_exec', {1: 2}), ('_layer_ram_applied', {1: 2}),
    ('_dos_task_binding', {'task': 'declared'}), ('_dos_task_monitor', {'uuid': 'monitor'}),
    ('_dos_task_views', {'task': {}}), ('_dos_scheduler', {'active': True}),
])
def test_task_and_layer_ambiguity_refuses_before_native_observation(ram, field, value):
    setattr(ram.session, field, value)
    with pytest.raises(ValueError, match='layers or task-private'):
        bind(ram)
    assert not ram.peer.qmp_calls and not ram.reads and not ram.writes


def test_explicit_physical_binding_survives_cpu_mode_and_paging_changes_between_reads(ram):
    o = ram
    item = bind(o, space='physical')
    monitor = o.peer.monitor
    o.peer.monitor = lambda: monitor().replace('CR0=00000001', 'CR0=80000001')
    assert o.session.runtime_memory(item['id'], offset=2, length=2)['hex'] == '1234'
    o.peer.mode = 'real'
    assert o.session.runtime_memory(item['id'], offset=2, length=2)['identity'] == item['identity']


def test_linear_binding_refuses_changed_address_context_before_witness_read(ram):
    bind(ram)
    ram.reads.clear()
    monitor = ram.peer.monitor
    ram.peer.monitor = lambda: monitor().replace('A20=1', 'A20=0')
    with pytest.raises(ValueError, match='A20|context changed'):
        ram.session.runtime_memory('allocation', length=1)
    assert not ram.reads and not ram.writes


def test_context_change_during_binding_cannot_publish_handle(ram):
    ram.after_read = lambda: setattr(ram.peer, 'mode', 'real')
    with pytest.raises(ValueError, match='context|real-mode'):
        bind(ram)
    assert not ram.session._runtime_bindings and event_count(ram, 'runtime-memory-bind') == 0


def test_actual_process_epoch_change_invalidates_both_name_and_id_without_rewriting_epoch(ram):
    s = ram.session
    item = bind(ram)
    epoch = s._runtime_epoch
    s._runtime_state()
    assert s._runtime_epoch == epoch
    s._advance_epoch()
    assert s._runtime_epoch != epoch and s._process['capture_epoch'] == s._runtime_epoch
    ram.reads.clear()
    for identifier in ('allocation', item['id']):
        with pytest.raises(ValueError, match='invalidated'):
            s.runtime_memory(identifier, length=1)
    assert not ram.reads
    rebound = bind(ram)
    assert rebound['id'] != item['id'] and rebound['identity']['epoch'] == s._runtime_epoch


def test_actual_owned_checkpoint_loader_replaces_owner_and_requires_fresh_witness(checkpoint_runtime):
    o, s = checkpoint_runtime, checkpoint_runtime.session
    address = 0x110020
    s.vm.memory[address:address+4] = b'ABCD'
    item = s.bind_runtime_memory('old', address, length=4, expected_hex='4142',
                                provenance='authored owned-machine RAM', space='physical')
    old_owner, old_epoch = s.vm, s._runtime_epoch
    saved = s.save_machine_state()
    s.vm.memory[address:address+4] = b'WXYZ'
    restored = s.load_machine_state(saved['artifact'])
    assert restored['source_binding_restored'] is False and s.vm is not old_owner
    assert s._runtime_epoch != old_epoch and s._checkpoint_epoch > item['identity']['checkpoint_epoch']
    calls = list(s.vm.calls)
    for identifier in ('old', item['id']):
        with pytest.raises(ValueError, match='invalidated'):
            s.runtime_memory(identifier, length=1)
    assert s.vm.calls == calls
    fresh = s.bind_runtime_memory('old', address, length=4, expected_hex='4142',
                                 provenance='fresh restored-machine witness', space='physical')
    assert fresh['id'] != item['id']
    assert s.runtime_memory(fresh['id'], length=4)['hex'] == '41424344'
    assert s._process['source_mapping']['live'] is False


def test_wrong_expected_bytes_and_witness_drift_never_dispatch_a_write(ram):
    item = bind(ram)
    with pytest.raises(ValueError, match='expected bytes mismatch'):
        ram.session.write_runtime_memory(item['id'], 'aabb', expected_hex='ffff', offset=2)
    assert not ram.writes and event_count(ram, 'runtime-memory-write-attempt') == 0
    ram.ram[0] = 0
    ram.reads.clear()
    with pytest.raises(ValueError, match='witness mismatch'):
        ram.session.runtime_memory(item['id'], offset=2, length=2)
    assert ram.reads == [(ADDRESS, 2, 'virtual')] and not ram.session.closed


def test_masked_witness_and_consumption_invalidate_only_after_verified_commit(ram):
    item = bind(ram, mask_hex='ff00')
    result = ram.session.write_runtime_memory(item['id'], '43', expected_hex='42', offset=1)
    assert result['verified'] and not result['binding_invalidated']
    assert ram.session.runtime_memory(item['id'], length=2)['hex'] == '4143'
    result = ram.session.write_runtime_memory(item['id'], '44', expected_hex='41')
    assert result['verified'] and result['binding_invalidated']
    assert not ram.session.closed
    with pytest.raises(ValueError, match='invalidated'):
        ram.session.runtime_memory(item['id'], length=1)


@pytest.mark.parametrize('fault', ['timeout', 'corrupt', 'epoch', 'context', 'publication'])
def test_uncertain_dispatched_write_closes_without_rollback_or_replay(ram, fault):
    item = bind(ram)
    if fault in ('timeout', 'corrupt'):
        ram.write_fault = fault
    elif fault == 'epoch':
        ram.after_write = ram.session._advance_epoch
    elif fault == 'context':
        ram.after_write = lambda: setattr(ram.peer, 'mode', 'real')
    else:
        original = ram.session._event
        def event(name, value):
            if name == 'runtime-memory-write':
                raise OSError('Authored final publication failure')
            return original(name, value)
        ram.session._event = event
    with pytest.raises(RuntimeMemoryWriteError) as caught:
        ram.session.write_runtime_memory(item['id'], 'aabb', expected_hex='1234', offset=2)
    assert len(ram.writes) == 1 and ram.session.closed and ram.closed
    receipt = caught.value.result
    assert not receipt['verified'] and receipt['dispatch_outcome'] == 'unknown'
    assert not receipt['state_restore_used']
    assert event_count(ram, 'runtime-memory-write-unknown') == 1


def test_reads_preserve_history_and_frozen_state_but_write_cannot_bypass_freeze(ram):
    s = ram.session
    s._qemu_history_live = dict(valid=True, id='history')
    s._qemu_cpu_delta_history = dict(valid=True, frozen=False, id='selected', cursor=1)
    item = bind(ram)
    assert s.runtime_memory(item['id'], offset=2, length=2)['hex'] == '1234'
    assert s._qemu_history_live['valid'] and s._qemu_cpu_delta_history['valid']
    s._qemu_cpu_delta_history.update(valid=False, frozen=True)
    with pytest.raises(ValueError, match='invalidated'):
        s.runtime_memory(item['id'], length=1)
    fresh = bind(ram)
    assert s.runtime_memory(fresh['id'], length=1)['hex'] == '41'
    with pytest.raises(ValueError, match='partial state is frozen'):
        s.write_runtime_memory(fresh['id'], 'ff', expected_hex='41')
    assert not ram.writes and s._qemu_cpu_delta_history['frozen']


def test_saved_script_routes_bind_read_and_expected_byte_edit(ram):
    script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        dict(op='bind-runtime-memory', name='route', address=ADDRESS, length=4,
             expected_hex='4142', provenance='authored route', **{'as': 'bound'}),
        dict(op='runtime-memory', binding='$bound.id', offset=2, length=2, **{'as': 'read'}),
        dict(op='write-runtime-memory', binding='$bound.id', data_hex='aabb', expected_hex='$read.hex', offset=2),
    ])
    result = ram.session.script(script=script)
    assert result['ok'] and result['completed_steps'] == 3, result
    assert len(ram.writes) == 1 and not ram.session.closed


def test_one_inherited_deadline_is_installed_and_restored(ram):
    s, vm, peer = ram.session, ram.session.vm, ram.peer
    import time
    bound = time.monotonic() + 2
    s._rpc_deadline, s._deadline, vm.operation_deadline, peer.operation_deadline = bound + 3, bound + 2, bound + 1, bound
    bind(ram)
    assert all(all(value == bound for value in observed) for observed in ram.deadlines)
    assert (s._rpc_deadline, s._deadline, vm.operation_deadline, peer.operation_deadline) == (bound + 3, bound + 2, bound + 1, bound)


def test_outer_expiry_after_verified_write_preserves_receipt_and_closes(ram, monkeypatch):
    s = ram.session
    item = bind(ram)
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr('time.monotonic', lambda: clock.now)
    original = s._event
    def event(name, value):
        result = original(name, value)
        if name == 'runtime-memory-write':
            clock.now = 111.0
        return result
    s._event = event
    with pytest.raises(TimeoutError) as caught:
        s.write_runtime_memory(item['id'], 'aabb', expected_hex='1234', offset=2)
    assert caught.value.result['verified'] is True
    assert s.closed and len(ram.writes) == 1


@pytest.mark.parametrize('later', [
    dict(op='bind-runtime-memory', name='later', address=ADDRESS, length=0,
         expected_hex='4142', provenance='authored'),
    dict(op='bind-runtime-memory', name='$earlier.name', address=ADDRESS, length=4,
         expected_hex='4142', provenance=[]),
    dict(op='bind-runtime-memory', name='later', address='$earlier.address', length=0,
         expected_hex='4142', provenance='authored'),
    dict(op='bind-runtime-memory', name='later', address=ADDRESS, length=4,
         expected_hex='$earlier.hex', mask_hex='0000', provenance='authored'),
    dict(op='bind-runtime-memory', name='later', address=ADDRESS, length=4,
         expected_hex='zz', mask_hex='$earlier.mask', provenance='authored'),
    dict(op='bind-runtime-memory', name='later', address=ADDRESS, length=4,
         expected_hex='$earlier.hex', provenance='authored', space='virtual'),
    dict(op='bind-runtime-memory', name='later', address=0xffffffff, length='$earlier.length',
         expected_hex='4142', provenance='authored'),
    dict(op='bind-runtime-memory', name='later', address=0xa0000, length=4,
         expected_hex='$earlier.hex', provenance='authored'),
    dict(op='runtime-memory', binding='allocation', length=0),
    dict(op='runtime-memory', binding='$earlier.id', length=0),
    dict(op='runtime-memory', binding='$earlier.id', offset=65535, length=2),
    dict(op='runtime-memory', binding=None, length='$earlier.length'),
    dict(op='write-runtime-memory', binding=None, data_hex='aabb', expected_hex='1234'),
    dict(op='write-runtime-memory', binding='$earlier.id', data_hex='$earlier.hex',
         expected_hex='1234', offset=65535),
])
def test_script_checks_each_static_runtime_field_before_any_native_effect(ram, later):
    bind(ram)
    calls, reads = list(ram.peer.qmp_calls), list(ram.reads)
    script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        dict(op='write-memory', address=ADDRESS + 2, data_hex='aabb', expected_hex='1234'), later])
    with pytest.raises((ValueError, TypeError)):
        ram.session.script(script=script)
    assert not ram.writes and bytes(ram.ram[2:4]) == b'\x12\x34'
    assert ram.peer.qmp_calls == calls and ram.reads == reads


def test_script_reference_samples_do_not_reject_a_possible_valid_range(ram):
    from fdisbull.debug_script import validate_script
    script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        dict(op='bind-runtime-memory', name='$earlier.name', address=ADDRESS, length='$earlier.length',
             expected_hex='4142', mask_hex='$earlier.mask', provenance='authored'),
        dict(op='runtime-memory', binding='$earlier.id', offset=65535, length='$earlier.length'),
    ])
    assert len(validate_script(script, session=ram.session)) == 2
    assert not ram.peer.qmp_calls and not ram.reads


def test_direct_stopped_admission_transport_loss_closes_owner_and_keeps_primary_error(ram):
    from fdisbull.dosbox_rpc import DebuggerError
    def lost(command, *args, **kwargs):
        ram.peer.socket = None
        raise DebuggerError('Authored socket loss before stopped admission')
    ram.peer.call = lost
    original_close = ram.session.vm.close
    def close():
        original_close()
        raise OSError('Authored cleanup failure after owner close')
    ram.session.vm.close = close
    with pytest.raises(DebuggerError, match='socket loss') as caught:
        bind(ram)
    assert ram.closed and not ram.writes
    assert caught.value.runtime_memory_cleanup_error == 'OSError'


def test_outer_write_timeout_preserves_primary_receipt_when_close_publication_fails(ram, monkeypatch):
    item = bind(ram)
    clock = [100.0]
    monkeypatch.setattr('time.monotonic', lambda: clock[0])
    original_event, original_close = ram.session._event, ram.session.close
    def event(name, value):
        result = original_event(name, value)
        if name == 'runtime-memory-write':
            clock[0] = 111.0
        return result
    def close():
        original_close()
        raise OSError('Authored publication failure after cleanup')
    ram.session._event, ram.session.close = event, close
    with pytest.raises(TimeoutError) as caught:
        ram.session.write_runtime_memory(item['id'], 'aabb', expected_hex='1234', offset=2)
    assert caught.value.result['verified'] is True
    assert caught.value.runtime_memory_cleanup_error == 'OSError'
    assert len(ram.writes) == 1 and ram.closed
