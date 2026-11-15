"""Opt-in real QEMU execution-hook witnesses; no vendor code is embedded."""
import os
from pathlib import Path
import shutil

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import digest, prepare_dos_baseline
from support.qemu_dos_fixture import boot_fixture
from test_qemu_layers_native import _candidate


def _boot_project(tmp_path):
    image, symbols = boot_fixture()
    path = tmp_path / 'hook-boot.img'
    path.write_bytes(image)
    return image, path, symbols, Project.create(tmp_path / 'hook.fdb', path,
                                                arch='x86', bits=32,
                                                base=0x7c00, entry=0x7c00)


def _register(debug):
    values = debug.registers()['registers']
    name = 'rax' if 'rax' in values else 'eax'
    return name, int(values[name], 16)


def test_native_one_shot_hook_stops_and_edits_guarded_register(tmp_path):
    executable, options = _candidate()
    image, path, symbols, project = _boot_project(tmp_path)
    with project:
        with project.debugger(executable, tmp_path, **options) as debug:
            name, _ = _register(debug)
            hook = debug.hook(symbols['loop'], space='linear', actions=[{
                'op': 'registers', 'registers': {name: {'expected': 0x1357, 'value': 0xbeef}},
            }])
            with pytest.raises(ValueError, match='Hook-owned'):
                debug.delete_breakpoint(hook['breakpoint_id'])
            result = debug.run(timeout_ms=15000, stop_on_hook=True)
            assert result['outcome'] == 'hook', result
            assert result['hook_hits'][0]['hook'] == hook['hook']
            assert result['hook_hits'][0]['hit'] == 1
            assert _register(debug)[1] & 0xffff == 0xbeef
            assert debug.memory(symbols['counter'], length=2)['hex'] == '0700'
            assert debug.hooks()['hooks'] == []
            assert debug.step(timeout_ms=5000)['outcome'] == 'step'
            assert debug.memory(symbols['counter'], length=2)['hex'] == '0800'
    assert path.read_bytes() == image


def test_native_repeat_hook_steps_over_and_exhausts(tmp_path):
    executable, options = _candidate()
    image, path, symbols, project = _boot_project(tmp_path)
    with project:
        with project.debugger(executable, tmp_path, **options) as debug:
            name, _ = _register(debug)
            hook = debug.hook(symbols['loop'], space='linear', once=False, max_hits=2,
                              actions=[{'op': 'registers', 'registers': {
                                  name: {'expected': 0x1357, 'value': 0x1357}}}])
            first = debug.run(timeout_ms=15000, stop_on_hook=True)
            assert first['outcome'] == 'hook' and first['hook_hits'][0]['hit'] == 1
            assert debug.memory(symbols['counter'], length=2)['hex'] == '0700'
            second = debug.run(timeout_ms=15000, stop_on_hook=True)
            assert second['outcome'] == 'hook' and second['hook_hits'][0]['hit'] == 2
            assert second['hook_hits'][0]['hook'] == hook['hook']
            assert debug.memory(symbols['counter'], length=2)['hex'] == '0800'
            assert debug.hooks()['hooks'] == []
            assert debug.step(timeout_ms=5000)['outcome'] == 'step'
            assert debug.memory(symbols['counter'], length=2)['hex'] == '0900'
    assert path.read_bytes() == image


def test_native_dos_source_hook_activates_portable_layer(tmp_path):
    executable, options = _candidate()
    boot = os.environ.get('FDISBULL_QEMU_DOS_BOOT_IMAGE')
    mcopy = os.environ.get('FDISBULL_QEMU_DOS_MCOPY') or shutil.which('mcopy')
    if not boot or not mcopy:
        if os.environ.get('FDISBULL_REQUIRE_QEMU_LAYERS') == '1':
            pytest.fail('A FreeDOS boot image and mcopy are required for the DOS hook witness')
        pytest.skip('Supply FDISBULL_QEMU_DOS_BOOT_IMAGE and FDISBULL_QEMU_DOS_MCOPY')
    disk = prepare_dos_baseline(Path(boot).expanduser().resolve(strict=True),
                                tmp_path / 'hook-dos.img',
                                Path(mcopy).expanduser().absolute())
    # NOP; MOV AX,1234h; MOV [0120h],AX; MOV AX,4c00h; INT 21h.
    code = (bytes.fromhex('90b83412a32001b8004ccd21').ljust(0x10, b'\x90')
            + bytes.fromhex('b82a4ccd21')).ljust(0x22, b'\0')
    source = tmp_path / 'HOOK.COM'
    source.write_bytes(code)
    with Project.create(tmp_path / 'hook-com.fdb', source, image='com') as project:
        static = project.regions(1)[0].start
        layer = project.debug_layer('hook-mov', kind='execute', patches=[{
            'address': hex(static + 1), 'expected_hex': 'b83412', 'data_hex': 'b8efbe',
        }])
        with project.debugger(executable, tmp_path, **options,
                              dos_boot_image=str(disk['image']),
                              dos_mcopy=str(Path(mcopy).expanduser().absolute()),
                              dos_startup_batch='FDAUTO.BAT', boot_timeout_ms=15000) as debug:
            process = debug.dos_process_info()
            psp = process['psp_segment']
            point = debug.hook(hex(static + 1), space='source',
                               actions=[{'op': 'layers', 'layers': [layer['layer']]}])
            hit = debug.run(timeout_ms=15000, stop_on_hook=True)
            assert hit['outcome'] == 'hook' and hit['hook_hits'][0]['hook'] == point['hook']
            assert debug.code(hex(static + 1), length=3, view='ram', space='source')['hex'] == 'b83412'
            assert debug.code(hex(static + 1), length=3, view='execute', space='source')['hex'] == 'b8efbe'
            assert debug.step(timeout_ms=5000)['outcome'] == 'step'
            assert _register(debug)[1] & 0xffff == 0xbeef
            assert debug.step(timeout_ms=5000)['outcome'] == 'step'
            assert debug.memory(psp * 16 + 0x120, length=2, space='physical')['hex'] == 'efbe'
            debug.layers([])
            redirect = debug.hook(hex(static + 7), space='source',
                                  actions=[{'op': 'redirect', 'address': hex(static + 0x10)}])
            hit = debug.run(timeout_ms=5000, stop_on_hook=True)
            assert hit['outcome'] == 'hook' and hit['hook_hits'][0]['hook'] == redirect['hook']
            assert int(debug.registers()['linear_pc'], 16) == psp * 16 + 0x110
            debug.hook(hex(static), space='source', actions=[{'op': 'layers', 'layers': []}])
            result = debug.run(timeout_ms=5000)
            assert result['outcome'] == 'guest_exit' and result['process']['termination']['code'] == 42
            assert debug.hooks()['hooks'] == []
    assert source.read_bytes() == code
    assert digest(disk['image']) == disk['prepared_sha256']


def test_native_write_watch_hook_observes_guest_change_and_repeats(tmp_path):
    executable, options = _candidate()
    image, path, symbols, project = _boot_project(tmp_path)
    with project:
        with project.debugger(executable, tmp_path, **options) as debug:
            entry = debug.breakpoint(symbols['loop'])
            assert debug.run(timeout_ms=15000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(entry['breakpoint_id'])
            name, expected = _register(debug)
            hook = debug.hook(symbols['counter'], space='linear', access='w', length=2,
                              once=False, max_hits=2, actions=[
                                  {'op': 'registers', 'registers': {
                                      name: {'expected': expected, 'value': expected}}}])
            for count in (1, 2):
                result = debug.run(timeout_ms=5000, stop_on_hook=True)
                assert result['outcome'] == 'hook', result
                hit, = result['hook_hits']
                assert hit['hook'] == hook['hook'] and hit['hit'] == count
                assert hit['stop']['outcome'] == 'watchpoint'
                assert debug.memory(symbols['counter'], length=2)['hex'] == (7 + count).to_bytes(2, 'little').hex()
            assert debug.hooks()['hooks'] == []
    assert path.read_bytes() == image
