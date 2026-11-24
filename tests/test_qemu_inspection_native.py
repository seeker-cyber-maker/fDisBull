"""Opt-in native CPU inventory and owned diagnostic stream for each producer."""
import os

import pytest

from fdisbull.cli import respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.project import Project
from test_qemu_dos_native import selected_qemu, create_boot_project
from test_qemu_chip8_native import _inputs as chip8_inputs


def verify_public(debug, project, expected_arch, expected_route):
    workspace = DebugWorkspace()
    workspace.sessions[debug.run_id] = debug
    def call(method, **params):
        result = respond({'id': 1, 'method': method, 'params': {
            'project': str(project.path), 'run': debug.run_id, **params}}, debugger=workspace)
        assert result['ok'], result
        return result['result']
    inventory = call('debug-cpu-inventory')
    assert inventory['format'] == 'fdisbull-native-cpu-inventory-2'
    assert inventory['expected_target'] in expected_arch
    assert inventory['expected_target_source'] == 'caller-declared'
    assert inventory['cpu_source'] == expected_route
    assert len(inventory['cpu_paths']) == 1
    assert inventory['cpu_paths'][0].startswith('/machine/')
    if expected_route == 'query-cpus-fast':
        assert inventory['target_source'] == 'qmp'
        assert inventory['target']['arch'] in expected_arch
        assert len(inventory['cpus']) == 1
        assert inventory['cpu_paths'] == [inventory['cpus'][0]['qom-path']]
    else:
        assert inventory['target'] is None and inventory['target_source'] is None
        assert inventory['cpus'] is None
        assert len(inventory['qom_cpu_children']) == 1
        assert inventory['cpu_paths'] == [inventory['qom_cpu_children'][0]['qom_path']]
    assert isinstance(inventory['status']['running'], bool)
    assert inventory['status_source'] == 'qmp'
    diagnostics = call('debug-diagnostics', limit=1)
    assert diagnostics['cursor'] == 0
    assert diagnostics['next_cursor'] == len(bytes.fromhex(diagnostics['hex']))
    assert diagnostics['next_cursor'] <= diagnostics['size']
    assert diagnostics['native_exit_code'] is None
    next_chunk = call('debug-diagnostics', cursor=diagnostics['next_cursor'],
                      identity=diagnostics['identity'], limit=1)
    assert next_chunk['cursor'] == diagnostics['next_cursor']
    assert next_chunk['identity'] == diagnostics['identity']
    workspace.sessions.clear()


def test_native_dos_inspection(tmp_path):
    executable, options = selected_qemu()
    source, _, project = create_boot_project(tmp_path)
    before = source.read_bytes()
    with project:
        with project.debugger(executable, tmp_path, **options) as debug:
            process = debug.vm.process
            verify_public(debug, project, {'x86_64'}, 'query-cpus-fast')
        assert process.poll() is not None
    assert source.read_bytes() == before


@pytest.mark.parametrize('producer', ['original', 'frame_keys'])
def test_native_chip8_inspection(tmp_path, producer):
    if producer == 'original':
        binary, tool = chip8_inputs()
    else:
        binary = os.environ.get('FDISBULL_CHIP8_FRAME_KEYS_QEMU')
        tool = os.environ.get('FDISBULL_CHIP8_FRAME_KEYS_QEMU_IMG')
        if not binary or not tool:
            if os.environ.get('FDISBULL_REQUIRE_CHIP8_FRAME_KEYS') == '1':
                pytest.fail('CHIP-8 frame-key QEMU and qemu-img are required')
            pytest.skip('Set CHIP-8 frame-key QEMU and qemu-img')
    rom = tmp_path / 'probe.ch8'
    rom.write_bytes(bytes.fromhex('60011202'))
    with Project.create(tmp_path / 'chip8.fdb', rom, arch='chip8', bits=16) as project:
        with project.debugger(binary, str(tmp_path), backend='qemu-chip8',
                              qemu_checkpoint_tool=tool, boot_timeout_ms=10000) as debug:
            process = debug.vm.process
            before = debug.registers()['linear_pc']
            assert int(before, 0) == 0x200
            verify_public(debug, project, {'chip8'}, 'qom-list')
            assert process.poll() is None
            assert debug.registers()['linear_pc'] == before
            assert debug.step()['outcome'] == 'step'
            assert int(debug.registers()['linear_pc'], 0) == 0x202
            assert int(debug.registers()['registers']['v0'], 0) == 1
            assert process.poll() is None
        assert process.poll() is not None
