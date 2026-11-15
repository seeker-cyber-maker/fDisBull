"""Real TCG layer witnesses; no DOS, commercial image, or game is required.

The selected candidate must provide the QEMU layer extension. These tests
exercise actual guest reads and instructions, not only reported layer views.
"""
import json
import os
from pathlib import Path
import shutil

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project
from support.dos_process_fixture import digest, prepare_dos_baseline
from support.qemu_dos_fixture import boot_fixture
from support.qemu_paging_aba_fixture import paging_aba_boot


def _candidate():
    selected = os.environ.get('FDISBULL_QEMU_LAYERS')
    if not selected:
        if os.environ.get('FDISBULL_REQUIRE_QEMU_LAYERS') == '1':
            pytest.fail('FDISBULL_QEMU_LAYERS is required for native layer acceptance')
        pytest.skip('Supply FDISBULL_QEMU_LAYERS for native layer acceptance')
    path = Path(selected).expanduser().resolve(strict=True)
    assert path.is_file() and os.access(path, os.X_OK)
    firmware = (os.environ.get('FDISBULL_QEMU_LAYERS_FIRMWARE') or
                os.environ.get('FDISBULL_QEMU_DOS_FIRMWARE'))
    return str(path), {'backend': 'qemu-dos', 'qemu_transport': 'pipe',
                       'qemu_firmware': firmware}


def _stop_at(debug, address):
    point = debug.breakpoint(address)
    result = debug.run(timeout_ms=15000)
    assert result['outcome'] == 'breakpoint', result
    assert point['breakpoint_id'] in result['session']['stop_reason']['breakpoint_ids']
    debug.delete_breakpoint(point['breakpoint_id'])


def _word(debug, address):
    return int.from_bytes(bytes.fromhex(debug.memory(address, length=2, space='physical')['hex']), 'little')


def test_native_fetch_overlay_warmed_translation_and_ram_layer(tmp_path):
    executable, options = _candidate()
    image, symbols = boot_fixture()
    source = tmp_path / 'authored-layer-boot.img'
    source.write_bytes(image)
    loop = symbols['loop']
    with Project.create(tmp_path / 'layer.fdb', source, arch='x86', bits=32,
                        base=0x7c00, entry=0x7c00) as project:
        with project.debugger(executable, tmp_path, **options) as debug:
            _stop_at(debug, loop)
            assert debug.memory(loop, length=4, space='physical')['hex'] == 'ff060050'
            # Execute the original loop repeatedly before installing a layer so
            # the translation cache has already handled the original bytes.
            warm = debug.run(timeout_ms=50)
            assert warm['outcome'] == 'timeout' and warm['timed_out']
            _stop_at(debug, loop)
            before = _word(debug, symbols['counter'])
            with pytest.raises(DebuggerError, match='FDISBULL_LAYER_PRECONDITION'):
                debug.vm.qmp.call('x-fdisbull-layer-configure', {
                    'generation': 0,
                    'ram': [{'address': symbols['counter'],
                             'before': before.to_bytes(2, 'little').hex(), 'after': '0042'}],
                    'execute': [{'address': loop, 'before': '00', 'after': '90'}],
                })
            assert _word(debug, symbols['counter']) == before
            assert debug.layers()['generation'] == 0
            patch = debug.layer_patch('inc-to-dec', loop, expected_hex='ff060050',
                                      data_hex='ff0e0050', kind='execute',
                                      activate=True, space='linear')
            original = debug.code(loop, length=4, view='ram', space='linear')
            replacement = debug.code(loop, length=4, view='execute', space='linear')
            assert original['hex'] == 'ff060050'
            assert replacement['hex'] == 'ff0e0050'
            assert replacement['generation'] == original['generation']
            assert debug.memory(loop, length=4, space='physical')['hex'] == 'ff060050'
            trace = debug.trace(count=1, timeout_ms=5000)
            trace_path = tmp_path / 'native-layer-trace.json'
            project.debug_export(trace['artifact'], trace_path)
            event, = json.loads(trace_path.read_text())['events']
            assert event['bytes'] == 'ff0e0050'
            assert event['active_layers'] == [patch['layer']]
            assert _word(debug, symbols['counter']) == (before - 1) & 0xffff

            debug.layers([])
            assert debug.code(loop, length=4, view='execute', space='linear')['hex'] == 'ff060050'
            _stop_at(debug, loop)
            before = _word(debug, symbols['counter'])
            assert debug.step(timeout_ms=5000)['outcome'] == 'step'
            assert _word(debug, symbols['counter']) == (before + 1) & 0xffff

            # An explicit RAM layer is data visible, unlike the fetch overlay.
            _stop_at(debug, loop)
            base = _word(debug, symbols['counter'])
            data = debug.layer_patch('counter-data', symbols['counter'],
                                     expected_hex=base.to_bytes(2, 'little').hex(),
                                     data_hex='3442', kind='ram', activate=True,
                                     space='physical')
            assert _word(debug, symbols['counter']) == 0x4234
            assert debug.step(timeout_ms=5000)['outcome'] == 'step'
            assert _word(debug, symbols['counter']) == 0x4235
            # The guest modified the RAM overlay; clearing without an explicit
            # conflict policy must refuse instead of discarding its update.
            with pytest.raises(ValueError, match='conflict|changed'):
                debug.layers([])
            assert _word(debug, symbols['counter']) == 0x4235
            debug.layers([], conflict='keep_changed')
            # The guest changed the low byte only. The untouched high
            # byte returns to its original RAM value.
            assert _word(debug, symbols['counter']) == ((base & 0xff00) | 0x35)
            assert patch['layer'] != data['layer']
    assert source.read_bytes() == image


def test_native_ram_layer_tracks_a_b_a_physical_backing(tmp_path):
    executable, options = _candidate()
    nasm = os.environ.get('NASM') or shutil.which('nasm')
    if not nasm:
        if os.environ.get('FDISBULL_REQUIRE_QEMU_LAYERS') == '1':
            pytest.fail('NASM is required for the native paging witness')
        pytest.skip('Supply NASM for the native paging witness')
    image, witness = paging_aba_boot(tmp_path, nasm)
    source = tmp_path / 'authored-paging-aba.img'
    source.write_bytes(image)
    a, b = witness['backing_a'], witness['backing_b']
    linear = witness['linear_address']
    original_a = witness['sentinel_a'].to_bytes(4, 'little').hex()
    original_b = witness['sentinel_b'].to_bytes(4, 'little').hex()
    changed_a = '78563412'
    with Project.create(tmp_path / 'paging-layer.fdb', source, arch='x86', bits=32) as project:
        with project.debugger(executable, tmp_path, **options) as debug:
            _stop_at(debug, witness['markers'][0])
            assert debug.memory(witness['observation_addresses'][0], length=4)['hex'] == original_a
            layer = debug.layer_patch('backing-a-data', linear, expected_hex=original_a,
                                      data_hex=changed_a, kind='ram', activate=True,
                                      space='linear')
            assert debug.memory_translation(linear, length=4)['data_hex'] == changed_a
            assert debug.memory(a, length=4, space='physical')['hex'] == changed_a
            assert debug.memory(b, length=4, space='physical')['hex'] == original_b

            _stop_at(debug, witness['markers'][1])
            assert debug.memory(witness['observation_addresses'][1], length=4)['hex'] == original_b
            assert debug.memory_translation(linear, length=4)['data_hex'] == original_b
            assert debug.memory(a, length=4, space='physical')['hex'] == changed_a
            assert debug.memory(b, length=4, space='physical')['hex'] == original_b

            _stop_at(debug, witness['markers'][2])
            assert debug.memory(witness['observation_addresses'][2], length=4)['hex'] == changed_a
            assert debug.memory_translation(linear, length=4)['data_hex'] == changed_a
            assert debug.memory(b, length=4, space='physical')['hex'] == original_b
            debug.layer_enable(layer['layer'], enabled=False)
            assert debug.memory(a, length=4, space='physical')['hex'] == original_a
            assert debug.memory(b, length=4, space='physical')['hex'] == original_b
    assert source.read_bytes() == image


def test_native_portable_source_layer_on_real_dos_com(tmp_path):
    executable, options = _candidate()
    boot = os.environ.get('FDISBULL_QEMU_DOS_BOOT_IMAGE')
    mcopy = os.environ.get('FDISBULL_QEMU_DOS_MCOPY') or shutil.which('mcopy')
    if not boot or not mcopy:
        if os.environ.get('FDISBULL_REQUIRE_QEMU_LAYERS') == '1':
            pytest.fail('A FreeDOS boot image and mcopy are required for the source layer witness')
        pytest.skip('Supply FDISBULL_QEMU_DOS_BOOT_IMAGE and FDISBULL_QEMU_DOS_MCOPY')
    disk = prepare_dos_baseline(Path(boot).expanduser().resolve(strict=True),
                                tmp_path / 'dos-baseline.img',
                                Path(mcopy).expanduser().absolute())
    # Original MOV AX,1234h; MOV [0120h],AX; MOV AX,4c00h; INT 21h.
    # The writable data word is included in the original COM source extent.
    code = bytes.fromhex('b83412a32001b8004ccd21').ljust(0x22, b'\0')
    source = tmp_path / 'SOURCE.COM'
    source.write_bytes(code)
    with Project.create(tmp_path / 'source-layer.fdb', source, image='com') as project:
        static = project.regions(1)[0].start
        layer = project.debug_layer('portable-source-mov', kind='execute', patches=[{
            'address': hex(static), 'expected_hex': 'b83412', 'data_hex': 'b8efbe',
        }])
        with project.debugger(executable, tmp_path, **options,
                              dos_boot_image=str(disk['image']),
                              dos_mcopy=str(Path(mcopy).expanduser().absolute()),
                              dos_startup_batch='FDAUTO.BAT', boot_timeout_ms=15000) as debug:
            process = debug.dos_process_info()
            assert process['state'] == 'active'
            psp = process['psp_segment']
            runtime = process['source_mapping']['runtime_base']
            assert runtime == psp * 16 + 0x100
            assert int(debug.registers()['linear_pc'], 16) == runtime
            assert debug.memory(runtime, length=3, space='physical')['hex'] == 'b83412'
            debug.layer_enable(layer['layer'])
            assert debug.code(hex(static), length=3, view='ram', space='source')['hex'] == 'b83412'
            assert debug.code(hex(static), length=3, view='execute', space='source')['hex'] == 'b8efbe'
            assert debug.memory(runtime, length=3, space='physical')['hex'] == 'b83412'
            assert debug.step(timeout_ms=5000)['outcome'] == 'step'
            registers = debug.registers()['registers']
            assert int(registers['rax' if 'rax' in registers else 'eax'], 16) & 0xffff == 0xbeef
            assert debug.step(timeout_ms=5000)['outcome'] == 'step'
            assert debug.memory(psp * 16 + 0x120, length=2, space='physical')['hex'] == 'efbe'
            debug.layers([])
            assert debug.memory(runtime, length=3, space='physical')['hex'] == 'b83412'
            result = debug.run(timeout_ms=5000)
            assert result['outcome'] == 'guest_exit', result
            assert result['process']['termination']['code'] == 0
    assert source.read_bytes() == code
    assert digest(disk['image']) == disk['prepared_sha256']


def test_native_self_modification_stops_before_fetching_stale_layer(tmp_path):
    from struct import unpack_from

    from support.dos_process_fixture import assemble

    executable, options = _candidate()
    nasm = os.environ.get('NASM') or shutil.which('nasm')
    if not nasm:
        if os.environ.get('FDISBULL_REQUIRE_QEMU_LAYERS') == '1':
            pytest.fail('NASM is required for the self-modification witness')
        pytest.skip('Supply NASM for the self-modification witness')
    # The writer executes on a different page than the target. A translated
    # block at the target cannot be assumed to have protected its backing.
    sector = assemble(tmp_path, 'layer-smc', r'''
bits 16
org 0x7c00
    jmp short start
    nop
    dd writer
start:
    cli
    xor ax,ax
    mov ds,ax
    mov ss,ax
    mov sp,0x7000
    mov word [0x8000],0x11b8
    mov byte [0x8002],0x11
    mov word [0x8003],0xfeeb
writer:
    mov word [0x8001],0x3333
    jmp 0x8000
times 510-($-$$) db 0
dw 0xaa55
''', nasm)
    writer, = unpack_from('<I', sector, 3)
    source = tmp_path / 'selfmod-layer.img'
    source.write_bytes(sector.ljust(1440 * 1024, b'\0'))
    with Project.create(tmp_path / 'selfmod-layer.fdb', source, arch='x86', bits=32) as project:
        with project.debugger(executable, tmp_path, **options) as debug:
            _stop_at(debug, writer)
            debug.layer_patch('self-modifying immediate', 0x8001, space='physical',
                              kind='execute', expected_hex='1111', data_hex='2222')
            result = debug.run(timeout_ms=3000)
            assert result['outcome'] == 'stopped' and result['layer_conflict']['fault'], result
            registers = result['registers']['registers']
            assert int(registers.get('rax', registers.get('eax')), 16) & 0xffff == 0
            assert debug.memory(0x8001, length=2)['hex'] == '3333'
            with pytest.raises(DebuggerError, match='layer.*faulted'):
                debug.run(timeout_ms=100)
            debug.layers([])
            _stop_at(debug, 0x8003)
            registers = debug.registers()['registers']
            assert int(registers.get('rax', registers.get('eax')), 16) & 0xffff == 0x3333
            debug.layer_patch('debugger-modified immediate', 0x8001, space='physical',
                              kind='execute', expected_hex='3333', data_hex='4444')
            debug.write_memory(0x8001, '5555', expected_hex='3333')
            with pytest.raises(DebuggerError, match='backing changed'):
                debug.run(timeout_ms=100)
            assert debug.registers()['linear_pc'] == '0x8003'
            debug.layers([])
            assert debug.memory(0x8001, length=2)['hex'] == '5555'


def test_native_fetch_layer_tracks_a_b_a_physical_backing(tmp_path):
    executable, options = _candidate()
    nasm = os.environ.get('NASM') or shutil.which('nasm')
    if not nasm:
        if os.environ.get('FDISBULL_REQUIRE_QEMU_LAYERS') == '1':
            pytest.fail('NASM is required for the remapped fetch witness')
        pytest.skip('Supply NASM for the remapped fetch witness')
    image, witness = paging_aba_boot(tmp_path, nasm, execute=True)
    source = tmp_path / 'authored-paging-fetch.img'
    source.write_bytes(image)
    a, b = witness['backing_a'], witness['backing_b']
    linear = witness['linear_address']
    original_a = 'b8df9b5713c3'
    original_b = 'b8e0ac6824c3'
    replacement = 'b878563412c3'
    markers = witness['markers']
    observations = witness['observation_addresses']
    with Project.create(tmp_path / 'paging-fetch.fdb', source, arch='x86', bits=32) as project:
        with project.debugger(executable, tmp_path, **options) as debug:
            _stop_at(debug, markers[0])
            assert debug.memory(observations[0], length=4)['hex'] == 'df9b5713'
            debug.layer_patch('fetch backing A', linear, space='linear', kind='execute',
                              expected_hex=original_a, data_hex=replacement)
            for marker, observed_at, expected_fetch, expected_value in (
                (markers[1], observations[1], original_b, 'e0ac6824'),
                (markers[2], observations[2], replacement, '78563412'),
            ):
                _stop_at(debug, marker)
                assert debug.memory(observed_at, length=4)['hex'] == expected_value
                assert debug.code(linear, length=6, space='linear')['hex'] == expected_fetch
                assert debug.memory(a, length=6)['hex'] == original_a
                assert debug.memory(b, length=6)['hex'] == original_b
            debug.layers([])
            assert debug.code(linear, length=6, space='linear')['hex'] == original_a
    assert source.read_bytes() == image


def test_native_source_fetch_layer_preserves_mz_relocations(tmp_path):
    from support.dos_process_fixture import mz_exit

    executable, options = _candidate()
    boot = os.environ.get('FDISBULL_QEMU_DOS_BOOT_IMAGE')
    mcopy = os.environ.get('FDISBULL_QEMU_DOS_MCOPY') or shutil.which('mcopy')
    if not boot or not mcopy:
        if os.environ.get('FDISBULL_REQUIRE_QEMU_LAYERS') == '1':
            pytest.fail('FreeDOS boot image and mcopy required for the MZ layer witness')
        pytest.skip('Supply FDISBULL_QEMU_DOS_BOOT_IMAGE and FDISBULL_QEMU_DOS_MCOPY')
    disk = prepare_dos_baseline(boot, tmp_path / 'mz-dos.img', mcopy)
    image, fixture = mz_exit()
    source = tmp_path / 'LAYER.EXE'
    source.write_bytes(image)
    with Project.create(tmp_path / 'layer-mz.fdb', source) as project:
        static = project.regions(1)[0].start
        with project.debugger(executable, tmp_path, **options,
                              dos_boot_image=str(disk['image']), dos_mcopy=mcopy,
                              dos_startup_batch='FDAUTO.BAT', boot_timeout_ms=15000) as debug:
            process = debug.dos_process_info()
            mapping = process['source_mapping']
            entry_offset = fixture['relative_cs'] * 16 + fixture['entry_ip']
            runtime = mapping['runtime_base']
            debug.layer_patch('relocated MZ immediate', static + entry_offset + 10,
                              kind='execute', expected_hex='efbe', data_hex='feca')
            assert debug.memory(runtime + entry_offset + 10, length=2)['hex'] == 'efbe'
            _stop_at(debug, runtime + entry_offset + 12)
            assert debug.memory(runtime + fixture['written_offset'], length=2)['hex'] == 'feca'
            assert int(debug.registers()['registers']['ds'], 16) == mapping['load_segment'] + 7
            debug.layers([])
            result = debug.run(timeout_ms=5000)
            assert result['outcome'] == 'guest_exit' and result['process']['termination']['code'] == 42
    assert source.read_bytes() == image
