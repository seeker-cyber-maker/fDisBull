"""Authored native RAM witnesses and actual cold-owner invalidation.

The existing MZ/LE bootstrap establishes flat protected mode through guest
instructions. Native QEMU, FreeDOS and build tools remain caller inputs.
"""
from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, prepare_dos_baseline
from support.qemu_dos_le_fixture import build_fixture
from test_qemu_dos_process_native import launch_options, process_record, process_runtime
from test_qemu_dos_le_checkpoint_native import _checkpoint_tool
from test_qemu_dos_modes_checkpoint_native import _fixture, _inputs, _launch


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_native_flat_le_ram_write_witness_consumption_and_cold_owner_restore(tmp_path, process_runtime):
    runtime, tool = process_runtime, _checkpoint_tool()
    fixture = build_fixture(tmp_path, runtime['nasm'])
    originals = {str(path): digest(path) for path in
                 (fixture['path'], runtime['executable'], runtime['boot_image'], tool)}
    disk = prepare_dos_baseline(runtime['boot_image'], tmp_path / 'ram-baseline.img', runtime['mcopy'],
                               config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG)
    database = tmp_path / 'runtime-ram.fdb'
    witness = bytes((i * 37 + 11) % 256 for i in range(8)).hex()
    with Project.create(database, fixture['path']) as project:
        options = launch_options(runtime, disk, qemu_checkpoint_tool=str(tool))
        with project.debugger(runtime['executable'], tmp_path, **options) as debug:
            initial = deepcopy(process_record(debug)['source_mapping'])
            point = debug.breakpoint(fixture['code_base'])
            assert debug.run(timeout_ms=10000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            observed = debug.registers()
            assert observed['cpu_mode'] == 'protected'
            assert observed['address_state']['code_bits'] == 32
            assert observed['address_state']['paging'] is False
            source = debug.dos_source_bind(expected_source_sha256=fixture['sha256'])
            assert source['live']
            assert debug.capabilities['runtime_memory_bindings'] is True
            bindings = {space: debug.bind_runtime_memory(space, fixture['data_base'], length=132,
                expected_hex=witness, provenance='authored relocated LE data bytes', space=space)
                for space in ('physical', 'linear')}
            for item in bindings.values():
                assert debug.runtime_memory(item['id'], offset=128, length=4)['hex'] == '00000000'
                assert item['identity']['runtime_load'] is None
            assert debug.dos_process_info()['source_mapping'] == initial
            saved = debug.save_machine_state()
            with pytest.raises(ValueError, match='expected bytes mismatch'):
                debug.write_runtime_memory('linear', '11223344', expected_hex='ffffffff', offset=128)
            changed = debug.write_runtime_memory('linear', '11223344', expected_hex='00000000', offset=128)
            assert changed['verified'] and not changed['state_restore_used']
            assert not changed['binding_invalidated'] and not changed['frame_presentation_verified']
            assert debug.runtime_memory('physical', offset=128, length=4)['hex'] == '11223344'
            assert debug.dos_source_binding()['state'] == 'retired'
            consumed = debug.write_runtime_memory('linear', 'ff', expected_hex=witness[:2])
            assert consumed['verified'] and consumed['binding_invalidated']
            with pytest.raises(ValueError, match='invalidated'):
                debug.runtime_memory(bindings['linear']['id'], length=1)

            owner, epoch = debug.vm, debug._runtime_epoch
            restored = debug.load_machine_state(saved['artifact'])
            assert debug.vm is not owner and owner.process.poll() is not None
            assert debug._runtime_epoch != epoch
            assert restored['machine_state_restored'] and restored['source_binding_restored'] is False
            for identifier in ('physical', bindings['physical']['id'], bindings['linear']['id']):
                with pytest.raises(ValueError, match='invalidated'):
                    debug.runtime_memory(identifier, length=1)
            fresh = debug.bind_runtime_memory('physical', fixture['data_base'], length=132,
                expected_hex=witness, provenance='fresh restored-machine witness', space='physical')
            assert fresh['id'] != bindings['physical']['id']
            assert debug.runtime_memory(fresh['id'], offset=128, length=4)['hex'] == '00000000'
            assert debug.dos_process_info()['source_mapping']['live'] is False
            assert debug.dos_source_binding()['state'] in ('retired', 'unbound')
            run = debug.run_id
            evidence = [dict(row) for row in project.db.execute(
                "SELECT operation,evidence FROM debug_events WHERE run=? AND operation LIKE 'runtime-memory-%' ORDER BY rowid",
                (run,))]
            native = debug.vm.process
        assert native.poll() is not None
    with Project(database) as reopened:
        assert [dict(row) for row in reopened.db.execute(
            "SELECT operation,evidence FROM debug_events WHERE run=? AND operation LIKE 'runtime-memory-%' ORDER BY rowid",
            (run,))] == evidence
    assert {path: digest(path) for path in originals} == originals


def test_native_paged_linear_refuses_while_explicit_physical_witness_remains_available(tmp_path):
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    before = digest(boot)
    disk = prepare_dos_baseline(boot, tmp_path / 'paged-baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'])
    data, marker = _fixture(tmp_path, runtime['NASM'], 'paged')
    source = tmp_path / 'MODE.COM'
    source.write_bytes(data)
    with Project.create(tmp_path / 'paged-ram.fdb', source, image='com') as project:
        with _launch(project, runtime, tmp_path, disk) as debug:
            base = process_record(debug)['source_mapping']['runtime_base']
            point = debug.breakpoint(base + marker['ready'])
            assert debug.run(timeout_ms=15000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            state = debug.registers()['address_state']
            assert state['cpu_mode'] == 'v86' and state['paging'] is True
            options = dict(name='scratch', address=base + marker['scratch'], length=2,
                           expected_hex='0000', provenance='authored paged V86 scratch')
            with pytest.raises(ValueError, match='Paged linear'):
                debug.bind_runtime_memory(**options)
            item = debug.bind_runtime_memory(**options, space='physical')
            assert debug.runtime_memory(item['id'], length=2)['hex'] == '0000'
            assert debug.vm.process.poll() is None and not debug.closed
    assert source.read_bytes() == data and digest(boot) == before
