"""Owned-machine recovery after an actual DOS allocation change.

Only the authored COM below is embedded. QEMU, firmware, qemu-img, mcopy and
FreeDOS are caller-supplied native inputs. This is separate from the existing
protected/V86 process-checkpoint witnesses: it proves a changed MCB, open guest
file, backing layers and linear hook without claiming the original MZ/COM
mapping survived. No debugger memory/register write drives the fixture.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct

import pytest

from fdisbull.cli import invoke
from fdisbull.project import Project
from support.dos_process_fixture import assemble, digest, prepare_dos_baseline
from test_qemu_dos_checkpoint_sessions_native import _inputs, _open_debug


FORMAT = 'fdisbull-qemu-owned-machine-qcow2-v1'
KEPT_PARAGRAPHS = 0x80

_SOURCE = r'''
bits 16
org 0x100
    jmp near start
    db 'FOWN'
    dw save_marker, read_marker, changed_marker, mutate_si, ram, layer_ram, output
start:
    mov ax,cs
    mov ds,ax
    mov es,ax
    ; The COM entry stack is in our PSP segment. Keep it inside the smaller
    ; allocation before DOS can release the rest of the original block.
    mov sp,0x7f0
    mov bx,0x80
    mov ah,0x4a
    int 0x21
    jc failed
    mov dx,filename
    xor cx,cx
    mov ah,0x3c
    int 0x21
    jc failed
    mov [handle],ax
    mov bx,ax
    mov dx,initial
    mov cx,2
    mov ah,0x40
    int 0x21
    jc failed
    cmp ax,2
    jne failed
save_marker:
    nop
    ; The open handle and its DOS state must survive cold machine restore.
    mov bx,[handle]
    mov ax,0x4200
    xor cx,cx
    xor dx,dx
    int 0x21
    jc failed
    mov dx,output
    mov cx,2
    mov ah,0x3f
    int 0x21
    jc failed
    cmp ax,2
    jne failed
    cmp word [output],0x4141
    jne failed
read_marker:
    nop
    mov bx,[handle]
    mov ax,0x4200
    xor cx,cx
    xor dx,dx
    int 0x21
    jc failed
    mov dx,changed
    mov cx,2
    mov ah,0x40
    int 0x21
    jc failed
    cmp ax,2
    jne failed
    mov ax,0x4200
    xor cx,cx
    xor dx,dx
    int 0x21
    jc failed
    mov dx,output
    mov cx,2
    mov ah,0x3f
    int 0x21
    jc failed
    cmp ax,2
    jne failed
    cmp word [output],0x4242
    jne failed
    mov word [ram],0x2222
mutate_si:
    mov si,0xbeef
changed_marker:
    nop
    mov bx,[handle]
    mov ah,0x3e
    int 0x21
    jc failed
%if RESIDENT
    mov dx,0x80
    mov ax,0x312a
%else
    mov ax,0x4c2a
%endif
    int 0x21
failed:
    mov ax,0x4c01
    int 0x21
filename: db 'OWNSTATE.DAT',0
initial: db 'AA'
changed: db 'BB'
handle: dw 0
ram: dw 0x1111
layer_ram: dw 0
output: dw 0
'''


def _fixture(directory, nasm, resident):
    program = assemble(directory, 'owned-machine',
                       '%define RESIDENT ' + str(int(resident)) + '\n' + _SOURCE, nasm)
    marker = program.index(b'FOWN')
    names = ('save', 'read', 'changed', 'fetch', 'ram', 'layer_ram', 'output')
    symbols = dict(zip(names, struct.unpack_from('<7H', program, marker + 4)))
    assert len(program) + 0x100 < 0x700 < 0x7f0 < KEPT_PARAGRAPHS * 16
    assert program[symbols['fetch'] - 0x100:symbols['fetch'] - 0x100 + 3] == bytes.fromhex('beefbe')
    return program, symbols


def _word(debug, address):
    return int.from_bytes(bytes.fromhex(debug.memory(address, length=2, space='physical')['hex']), 'little')


def _number(value):
    return int(value, 0) if isinstance(value, str) else value


def _stop_at(debug, address):
    point = debug.breakpoint(address)
    result = debug.run(timeout_ms=15000)
    assert result['outcome'] == 'breakpoint', result
    assert point['breakpoint_id'] in result['session']['stop_reason']['breakpoint_ids']
    debug.delete_breakpoint(point['breakpoint_id'])
    return result


def _assert_retired_source(debug):
    info = debug.dos_process_info()
    assert info['source_mapping']['live'] is False
    assert info['source_mapping']['live_ranges'] == []
    return info


def _assert_restored(debug, restored, saved_cpu, saved_epoch, previous_epoch,
                     previous_owner, base, symbols, original_layers, hook_id, space):
    assert restored['machine_state_restored'] is True
    assert restored['source_binding_restored'] is False
    assert previous_owner.poll() is not None
    assert debug.vm.process is not previous_owner
    info = _assert_retired_source(debug)
    assert info['capture_epoch'] not in (saved_epoch, previous_epoch)
    assert restored['capture_epoch'] == info['capture_epoch']
    actual = debug.registers()
    for field in ('registers', 'instruction_pointer', 'cpu_mode', 'address_state'):
        assert actual[field] == saved_cpu[field], field
    assert _word(debug, base + symbols['ram']) == 0x1111
    assert _word(debug, base + symbols['output']) == 0
    assert _word(debug, base + symbols['layer_ram']) == 0x1234
    layers = [restored['controls']['layers'][identifier] for identifier in original_layers]
    assert all(new != old for new, old in zip(layers, original_layers))
    assert debug.layers()['active'] == layers
    assert debug.code(base + symbols['fetch'], length=3, space=space, view='ram')['hex'] == 'beefbe'
    assert debug.code(base + symbols['fetch'], length=3, space=space, view='execute')['hex'] == 'befeca'
    hooks = debug.hooks()['hooks']
    assert len(hooks) == 1 and hooks[0]['hook'] == hook_id and hooks[0]['hits'] == 0
    assert hooks[0]['space'] == 'linear'
    assert hooks[0]['actions'] == [{'op': 'layers', 'layers': layers}]
    # The new recovery capability must not silently authorize source tracing
    # or turn the ordinary process checkpoint into a weaker machine snapshot.
    with pytest.raises(ValueError, match='source|Source|allocation|mapping|active'):
        debug.trace(count=1, timeout_ms=5000)
    with pytest.raises(ValueError, match='source|Source|allocation|mapping|active'):
        debug.save_state()
    assert debug.vm.process.poll() is None
    return layers


def _read_initial_then_mutate(debug, base, symbols, hook_id):
    first = debug.run(timeout_ms=15000, stop_on_hook=True)
    assert first['outcome'] == 'hook', first
    assert first['hook_hits'][0]['hook'] == hook_id and first['hook_hits'][0]['hit'] == 1
    # This read is performed by the guest through the saved open DOS handle.
    # It fails or returns BB if RAM alone, rather than the whole disk, restored.
    assert _word(debug, base + symbols['output']) == 0x4141
    _stop_at(debug, base + symbols['changed'])
    assert _word(debug, base + symbols['output']) == 0x4242
    assert _word(debug, base + symbols['ram']) == 0x2222
    registers = debug.registers()['registers']
    assert _number(registers.get('rsi', registers.get('esi'))) & 0xffff == 0xcafe
    assert _word(debug, base + symbols['layer_ram']) == 0x1234


@pytest.mark.parametrize(('resident', 'space'), [(False, 'physical'), (True, 'linear')],
                         ids=['exit-physical', 'tsr-linear'])
def test_native_shrunk_allocation_machine_recovery_hot_and_cold(tmp_path, resident, space):
    runtime = _inputs()
    nasm = os.environ.get('NASM')
    if not nasm:
        if os.environ.get('FDISBULL_REQUIRE_QEMU_LAYERS') == '1':
            pytest.fail('NASM is required for the authored owned-machine fixture')
        pytest.skip('Supply NASM for the authored owned-machine fixture')
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot)
    disk = prepare_dos_baseline(boot, tmp_path / 'baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'])
    program, symbols = _fixture(tmp_path, nasm, resident)
    binary = tmp_path / 'OWNED.COM'
    binary.write_bytes(program)
    original_hash = hashlib.sha256(program).hexdigest()
    database = tmp_path / 'owned-machine.fdb'

    with Project.create(database, binary, image='com') as project:
        with _open_debug(project, runtime, tmp_path, disk) as debug:
            assert debug.capabilities['owned_machine_checkpoints'] is True
            launch = debug.dos_process_info()
            base = launch['psp_segment'] * 16
            assert launch['entry']['ss'] == launch['entry']['cs']
            entry_anchor = None
            if not resident:
                # A separately verified source checkpoint remains stronger
                # than subsequent machine recovery and can restore authority.
                entry_anchor = debug.save_state('source-entry-before-shrink.qcow2')['artifact']
            _stop_at(debug, base + symbols['save'])
            mcb_size = _word(debug, base - 16 + 3)
            assert mcb_size == KEPT_PARAGRAPHS
            assert mcb_size != launch['allocation']['paragraphs']
            saved_epoch = debug.dos_process_info()['capture_epoch']
            saved_cpu = debug.registers()
            owner = debug.vm.process
            with pytest.raises(ValueError, match='allocation ownership changed'):
                debug.save_state()
            assert debug.vm.process is owner and owner.poll() is None
            assert debug.registers()['registers'] == saved_cpu['registers']

            fetch = debug.layer_patch('owned-fetch', base + symbols['fetch'],
                expected_hex='beefbe', data_hex='befeca', kind='execute', space=space,
                activate=False)['layer']
            ram = debug.layer_patch('owned-ram', base + symbols['layer_ram'],
                expected_hex='0000', data_hex='3412', kind='ram', space=space,
                activate=False)['layer']
            original_layers = [fetch, ram]
            debug.layers(original_layers)
            hook = debug.hook(base + symbols['read'], space='linear', once=False, max_hits=3,
                actions=[{'op': 'layers', 'layers': original_layers}])
            saved_cpu = debug.registers()
            saved = debug.save_machine_state()
            artifact = saved['artifact']
            assert saved['metadata']['format'] == FORMAT
            row = project.db.execute('SELECT kind,sha256 FROM debug_artifacts WHERE id=?', (artifact,)).fetchone()
            assert row['kind'] == 'machine-state' and row['sha256'] == saved['sha256']
            _read_initial_then_mutate(debug, base, symbols, hook['hook'])
            assert debug.registers()['registers'] != saved_cpu['registers']
            before_load_epoch = debug.dos_process_info()['capture_epoch']
            restored = debug.load_machine_state(artifact, timeout_ms=60000)
            _assert_restored(debug, restored, saved_cpu, saved_epoch, before_load_epoch,
                owner, base, symbols, original_layers, hook['hook'], space)
            _read_initial_then_mutate(debug, base, symbols, hook['hook'])
            hot_owner = debug.vm.process
            hot_epoch = debug.dos_process_info()['capture_epoch']
            hot_run = debug.run_id
        assert hot_owner.poll() is not None

    # Offline metadata inspection and the second restore use a reopened real
    # Project; neither a retained Python session nor the source launch nonce
    # can stand in for the saved machine's helper provenance.
    offline = invoke('debug-state-info', dict(project=str(database), artifact=artifact))
    assert offline['sha256'] == saved['sha256'] and offline['metadata']['format'] == FORMAT
    assert {c['name'] for c in offline['components']} == {'machine.qcow2', 'owned-machine.json'}
    with Project(database) as project:
        with _open_debug(project, runtime, tmp_path, disk) as debug:
            fresh_owner = debug.vm.process
            fresh_epoch = debug.dos_process_info()['capture_epoch']
            assert debug.run_id != hot_run
            restored = debug.load_machine_state(artifact, timeout_ms=60000)
            _assert_restored(debug, restored, saved_cpu, saved_epoch, fresh_epoch,
                fresh_owner, base, symbols, original_layers, hook['hook'], space)
            assert debug.dos_process_info()['capture_epoch'] != hot_epoch
            _read_initial_then_mutate(debug, base, symbols, hook['hook'])
            debug.delete_hook(hook['hook'])
            debug.layers([])
            assert _word(debug, base + symbols['layer_ram']) == 0
            finished = debug.run(timeout_ms=15000)
            assert finished['outcome'] == ('guest_tsr' if resident else 'guest_exit'), finished
            assert finished['process']['termination']['code'] == 42
            assert finished['process']['termination']['resident'] is resident
            _assert_retired_source(debug)
            if not resident:
                completed_owner = debug.vm.process
                source_restored = debug.load_state(entry_anchor, timeout_ms=60000)
                assert completed_owner.poll() is not None
                assert source_restored['source_binding_restored'] is True
                assert debug.dos_process_info()['source_mapping']['live'] is True
                assert debug._owned_machine_restored is False
                ordinary = debug.save_state('source-entry-restored.qcow2')
                assert ordinary['metadata']['format'] == 'fdisbull-qemu-dos-process-qcow2-v2'
            final_owner = debug.vm.process
        assert final_owner.poll() is not None

    assert binary.read_bytes() == program and digest(binary) == original_hash
    assert digest(boot) == boot_hash
    assert digest(disk['image']) == disk['prepared_sha256']


def test_native_owned_machine_restores_instrumented_buffers_and_frame_key_owner(tmp_path):
    """Restore a real tone and retained observer/input data under new owners.

    speaker_tone deliberately disables guest interrupts. Held frame keys are
    device/FIFO ownership evidence here, not a claim of guest consumption.
    """
    from support.dos_process_fixture import BASELINE_CONFIG
    from support.qemu_audio_fixture import speaker_tone
    from test_qemu_clock_budget_native import budget_receipt, park
    from test_qemu_frame_keys_native import _proof
    from test_qemu_instrumented_checkpoint_native import _open_instrumented, _pcm, _pixels

    runtime = _inputs()
    nasm = os.environ.get('NASM')
    if not nasm:
        if os.environ.get('FDISBULL_REQUIRE_QEMU_LAYERS') == '1':
            pytest.fail('NASM is required for the owned-machine instrumented witness')
        pytest.skip('Supply NASM for the owned-machine instrumented witness')
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot)
    disk = prepare_dos_baseline(boot, tmp_path / 'instrumented-baseline.img',
        runtime['FDISBULL_QEMU_DOS_MCOPY'], config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG)
    original, offsets = speaker_tone(tmp_path, nasm)
    program = original + b'\0\0'
    source = tmp_path / 'OWNEDPCM.COM'
    source.write_bytes(program)
    with Project.create(tmp_path / 'owned-instrumented.fdb', source, image='com') as project:
        with _open_instrumented(project, runtime, tmp_path, disk) as debug:
            assert debug.capabilities['owned_machine_checkpoints'] is True
            process = debug.dos_process_info()
            base = _number(process['source_mapping']['runtime_base'])
            fetch = debug.layer_patch('owned-instrumented-fetch', base,
                expected_hex='90', data_hex='f8', kind='execute', space='physical',
                activate=False)['layer']
            ram = debug.layer_patch('owned-instrumented-ram', base + len(original),
                expected_hex='0000', data_hex='3412', kind='ram', space='physical',
                activate=False)['layer']
            debug.layers([fetch, ram])
            park(debug, base + offsets['tone_ready_ip'] - 0x100)
            audio_started = debug.audio_start(max_frames=32000)
            display_started = debug.display_start(period_ns=20_000_000)
            before = debug.clock_observe()
            budget_receipt(debug.clock_advance(150_000_000, timeout_ms=10000),
                           150_000_000, before=before)
            # The program remains in tone_loop: this dormant linear hook is
            # retained, but no pending hook step-over enters the checkpoint.
            hook = debug.hook(base + offsets['quiet_ready_ip'] - 0x100,
                space='linear', once=False, max_hits=3,
                actions=[{'op': 'layers', 'layers': [fetch, ram]}])
            key_before = debug.frame_inputs([dict(key='shift', pressed=True)])['native']
            assert key_before['active'] and key_before['valid'] and key_before['held'] == ['shift']
            key_proof = _proof(key_before)
            cpu = debug.registers()
            clock = debug.clock_observe()
            audio, display = debug.audio_observe(), debug.display_observe()
            retrace = debug.retrace_observe()
            configuration = debug.vga_configuration_observe()
            assert audio['state'] == 'capturing' and audio['frames'] > 0 and audio['dropped_frames'] == 0
            assert display['state'] == 'observing' and display['updates'] > 0
            assert audio['window'] == audio_started['window'] and display['window'] == display_started['window']
            assert audio['observed_ns'] == display['observed_ns'] == retrace['observed_ns'] == clock['virtual_ns']
            pcm = _pcm(project, debug.capture_audio('owned-before.wav'))
            pixels = _pixels(project, debug.capture_display('owned-before.png'))
            assert len(pcm) == audio['frames'] and len(set(pcm)) > 1
            saved = debug.save_machine_state()
            owner = debug.vm.process

            assert debug.frame_inputs([dict(key='shift', pressed=False)])['held'] == []
            later_before = debug.clock_observe()
            budget_receipt(debug.clock_advance(100_000_000, timeout_ms=10000),
                           100_000_000, before=later_before)
            assert debug.clock_observe()['virtual_ns'] > clock['virtual_ns']
            assert debug.audio_observe()['frames'] > audio['frames']
            assert debug.display_observe()['updates'] > display['updates']
            assert debug.keyboard_state()['keyboard']['frame_keys'] == []

            restored = debug.load_machine_state(saved['artifact'], timeout_ms=60000)
            assert restored['machine_state_restored'] is True
            assert restored['source_binding_restored'] is False
            assert owner.poll() is not None and debug.vm.process is not owner
            assert _assert_retired_source(debug)['capture_epoch'] != process['capture_epoch']
            actual = debug.registers()
            for field in ('registers', 'instruction_pointer', 'cpu_mode', 'address_state'):
                assert actual[field] == cpu[field], field
            clock_after = debug.clock_observe()
            audio_after, display_after = debug.audio_observe(), debug.display_observe()
            retrace_after = debug.retrace_observe()
            assert clock_after['virtual_ns'] == clock['virtual_ns']
            assert clock_after['counter']['value'] == clock['counter']['value']
            assert clock_after['virtual_clock']['native']['epoch'] != clock['virtual_clock']['native']['epoch']
            assert audio_after['observed_ns'] == display_after['observed_ns'] == retrace_after['observed_ns'] == clock_after['virtual_ns']
            assert audio_after['state'] == 'capturing' and audio_after['frames'] == audio['frames']
            assert audio_after['dropped_frames'] == audio['dropped_frames']
            assert display_after['state'] == 'observing' and display_after['updates'] == display['updates']
            windows = restored['instrumentation']['windows']
            assert windows['audio'] == {'old': audio['window'], 'new': audio_after['window']}
            assert windows['display'] == {'old': display['window'], 'new': display_after['window']}
            assert audio_after['window'] != audio['window'] and display_after['window'] != display['window']
            assert retrace_after['raw'] == retrace['raw'] and retrace_after['phase'] == retrace['phase']
            assert retrace_after['timing'] == retrace['timing']
            assert debug.vga_configuration_observe()['current']['raw'] == configuration['current']['raw']
            assert _pcm(project, debug.capture_audio('owned-after.wav')) == pcm
            assert _pixels(project, debug.capture_display('owned-after.png')) == pixels
            keys = debug.keyboard_state()['keyboard']
            assert keys['frame_keys'] == ['shift']
            assert keys['native']['active'] and keys['native']['valid']
            assert keys['native']['token'] != key_before['token'] and keys['native']['epoch'] != key_before['epoch']
            assert _proof(keys['native']) == key_proof
            fetch_after = restored['controls']['layers'][fetch]
            ram_after = restored['controls']['layers'][ram]
            assert fetch_after != fetch and ram_after != ram
            assert debug.layers()['active'] == [fetch_after, ram_after]
            assert _word(debug, base + len(original)) == 0x1234
            assert debug.code(base, length=1, space='physical', view='ram')['hex'] == '90'
            assert debug.code(base, length=1, space='physical', view='execute')['hex'] == 'f8'
            hooks = debug.hooks()['hooks']
            assert len(hooks) == 1 and hooks[0]['hook'] == hook['hook'] and hooks[0]['hits'] == 0
            assert hooks[0]['actions'] == [{'op': 'layers', 'layers': [fetch_after, ram_after]}]
            assert debug.frame_inputs([dict(key='shift', pressed=False)])['held'] == []
            debug.delete_hook(hook['hook'])
            debug.audio_stop()
            debug.display_stop()
            debug.layers([])
            final_owner = debug.vm.process
        assert final_owner.poll() is not None
    assert source.read_bytes() == program
    assert digest(boot) == boot_hash and digest(disk['image']) == disk['prepared_sha256']
