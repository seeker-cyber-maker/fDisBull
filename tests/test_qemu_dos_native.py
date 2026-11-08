"""Opt-in, real native-QEMU migration acceptance.

FDISBULL_QEMU_DOS selects the QEMU binary; FDISBULL_QEMU_DOS_FIRMWARE optionally
selects its firmware directory. FDISBULL_REQUIRE_QEMU_DOS=1 refuses a skipped
core qualification. The independent DOS-service case also needs a caller-owned
FreeDOS Floppy Edition image and mcopy; FDISBULL_REQUIRE_QEMU_DOS_OS=1 makes
those inputs mandatory. No vendor image, kernel, game or state is committed.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil

from PIL import Image
import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project
from support.qemu_dos_fixture import (
    PROBE_MESSAGE, PROBE_REPORT_ADDRESS, PROBE_REPORT_SIZE, boot_fixture,
    parse_dos_report, prepare_freedos_image,
)


def selected_qemu():
    executable = os.environ.get('FDISBULL_QEMU_DOS')
    if not executable:
        if os.environ.get('FDISBULL_REQUIRE_QEMU_DOS') == '1' or os.environ.get('FDISBULL_REQUIRE_QEMU_DOS_OS') == '1':
            pytest.fail('Missing FDISBULL_QEMU_DOS: native QEMU qualification cannot be skipped')
        pytest.skip('Supply FDISBULL_QEMU_DOS for native QEMU migration acceptance')
    path = Path(executable).expanduser().resolve(strict=True)
    assert path.is_file() and os.access(path, os.X_OK), 'FDISBULL_QEMU_DOS must be executable'
    return str(path), dict(backend='qemu-dos', qemu_transport='pipe',
                          qemu_firmware=os.environ.get('FDISBULL_QEMU_DOS_FIRMWARE'))


def create_boot_project(tmp_path):
    image, symbols = boot_fixture()
    path = tmp_path / 'authored-boot.img'
    path.write_bytes(image)
    # The raw file view covers the whole floppy and therefore needs 32-bit
    # addresses. CPU instruction width comes from the observed CS descriptor.
    return path, symbols, Project.create(tmp_path / 'boot.fdb', path, arch='x86',
                                         bits=32, base=0x7c00, entry=0x7c00)


def enter_loop(debug, symbols):
    point = debug.breakpoint(symbols['loop'])
    result = debug.run(timeout_ms=15000)
    assert result['outcome'] == 'breakpoint', result
    assert point['breakpoint_id'] in result['session']['stop_reason']['breakpoint_ids']
    debug.delete_breakpoint(point['breakpoint_id'])
    return debug.registers()


def test_native_dos_selection_nonzero_segment_edits_trace_frame_and_reopen(tmp_path):
    executable, options = selected_qemu()
    path, symbols, project = create_boot_project(tmp_path)
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    with project:
        with project.debugger(executable, tmp_path, **options) as debug:
            assert debug.status()['state'] == 'stopped'
            assert debug.metadata['backend'] == 'qemu-dos'
            assert debug.contexts()['selected'] == 'machine'
            registers = enter_loop(debug, symbols)
            assert registers['cpu_mode'] == 'real'
            assert registers['address_state']['code_bits'] == 16
            assert int(registers['registers']['cs'], 16) == symbols['segment']
            assert int(registers['instruction_pointer'], 16) == symbols['loop_ip']
            assert int(registers['linear_pc'], 16) == symbols['loop']
            assert debug.memory(symbols['counter'], length=2, space='physical')['hex'] == '0700'
            assert debug.memory(symbols['counter'], length=2, space='virtual')['hex'] == '0700'
            mapping = debug.memory_translation(symbols['counter'])
            assert mapping['status'] == 'mapped'
            assert int(mapping['physical_address'], 16) == symbols['counter']

            # Failed expected-value guards must not advance or modify the CPU.
            with pytest.raises(DebuggerError, match='guard'):
                debug.write_memory(symbols['counter'], '2900', expected_hex='0800')
            general = 'rax' if 'rax' in registers['registers'] else 'eax'
            with pytest.raises(DebuggerError, match='guard'):
                debug.write_registers({general: {'expected': 0x1356, 'value': 0x1234}})
            unchanged = debug.registers()
            assert unchanged['instruction_pointer'] == registers['instruction_pointer']
            assert int(unchanged['registers'][general], 16) == 0x1357
            debug.write_registers({general: {'expected': 0x1357, 'value': 0x1234}})
            assert int(debug.registers()['registers'][general], 16) == 0x1234
            debug.write_memory(symbols['counter'], '2900', expected_hex='0700')
            trace = debug.trace('qemu-dos-trace.json', count=3, timeout_ms=10000)
            assert trace['metadata']['complete']
            assert debug.memory(symbols['counter'], length=2)['hex'] == '2a00'
            frame = debug.screenshot('qemu-dos-frame.png')
            timeout = debug.run(timeout_ms=40)
            assert timeout['timed_out'] and timeout['outcome'] == 'timeout'
            assert debug.status()['state'] == 'stopped'
            # A bounded continue timeout leaves a usable stopped control path.
            assert debug.step(timeout_ms=1000)['outcome'] == 'step'
            assert debug.resume()['state'] == 'running'
            assert debug.pause()['state'] == 'stopped'
            assert debug.step(timeout_ms=1000)['outcome'] == 'step'
            assert debug.memory(0xb8000, length=4)['hex'] == '511f461f'
            run_id = debug.run_id
            process = debug.vm.process
            temporary = Path(debug.vm.temporary.name)
        assert process.poll() is not None and not temporary.exists()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source_hash
    with Project(tmp_path / 'boot.fdb') as reopened:
        trace_path = tmp_path / 'trace.json'
        reopened.debug_export(trace['artifact'], trace_path)
        events = json.loads(trace_path.read_text())['events']
        assert [event['bytes'] for event in events] == symbols['trace_bytes']
        assert all(event['completion'] == 'confirmed native step' for event in events)
        assert int(events[0]['address'], 16) == symbols['loop']
        picture = tmp_path / 'frame.png'
        reopened.debug_export(frame['artifact'], picture)
        with Image.open(io.BytesIO(picture.read_bytes())) as image:
            assert image.format == 'PNG' and image.width > 0 and image.height > 0
        runs = reopened.debug_runs()['runs']
        assert any(run['id'] == run_id and run['state'] == 'exited' for run in runs)


@pytest.mark.parametrize('access', ['r', 'w', 'rw'])
def test_native_machine_data_watchpoints(access, tmp_path):
    executable, options = selected_qemu()
    _, symbols, project = create_boot_project(tmp_path)
    with project:
        with project.debugger(executable, tmp_path, **options) as debug:
            enter_loop(debug, symbols)
            point = debug.breakpoint(symbols['counter'], access=access, length=2)
            stopped = debug.run(timeout_ms=5000)
            assert stopped['outcome'] == 'watchpoint', stopped
            assert point['breakpoint_id'] in stopped['session']['stop_reason']['breakpoint_ids']
            # Read-modify-write stops need not imply that INC completed.
            assert debug.memory(symbols['counter'], length=2)['hex'] in ('0700', '0800')
            debug.delete_breakpoint(point['breakpoint_id'])
            assert debug.breakpoints == {}


def test_native_boot_uses_owned_image_and_a_fresh_launch(tmp_path):
    executable, options = selected_qemu()
    path, symbols, project = create_boot_project(tmp_path)
    original = path.read_bytes()
    with project:
        with project.debugger(executable, tmp_path, **options) as debug:
            # Deliberately invalidate this authored source AFTER admission. The
            # owned machine must keep executing its verified private copy.
            path.write_bytes(bytes(len(original)))
            enter_loop(debug, symbols)
            assert debug.memory(symbols['counter'], length=2)['hex'] == '0700'
            debug.write_memory(symbols['counter'], '6300', expected_hex='0700')
        path.write_bytes(original)
        with project.debugger(executable, tmp_path, **options) as fresh:
            enter_loop(fresh, symbols)
            assert fresh.memory(symbols['counter'], length=2)['hex'] == '0700'
        assert path.read_bytes() == original


def test_native_snapshot_search_guarded_edit_and_explicit_rule_tick(tmp_path):
    executable, options = selected_qemu()
    _, symbols, project = create_boot_project(tmp_path)
    with project:
        with project.debugger(executable, tmp_path, **options) as debug:
            enter_loop(debug, symbols)
            first = debug.memory_snapshot(symbols['counter'], length=8,
                                          task_id='authored-boot-counter')['artifact']
            initial = project.memory_search_start(first, width=2, stride=2,
                                                  mode='unknown')['artifact']
            assert debug.trace(count=3)['metadata']['complete']
            second = debug.memory_snapshot(symbols['counter'], length=8,
                                           task_id='authored-boot-counter')['artifact']
            narrowed = project.memory_search_refine(initial, second, mode='delta', delta=1)['artifact']
            candidates = project.memory_search_results(narrowed)
            assert candidates['candidate_count'] == 1
            assert candidates['rows'][0]['value'] == 8
            assert candidates['rows'][0]['previous_value'] == 7
            plan = project.memory_edit_plan(narrowed, offset=0, value=42)['artifact']
            receipt = debug.memory_apply(plan)
            assert receipt['applied'] and receipt['verified']
            assert debug.memory(symbols['counter'], length=2)['hex'] == '2a00'
            with pytest.raises(ValueError, match='already dispatched'):
                debug.memory_apply(plan)
            rule = project.memory_rule_create(narrowed, offset=0, value=99,
                                               max_applications=1, max_ticks=1)['artifact']
            tick = debug.memory_rule_tick(rule)
            assert tick['applied'] and tick['status'] == 'exhausted'
            assert debug.memory(symbols['counter'], length=2)['hex'] == '6300'
            assert not debug.memory_rule_tick(rule)['applied']
    with Project(tmp_path / 'boot.fdb') as reopened:
        assert reopened.memory_search_results(narrowed)['candidate_count'] == 1
        assert reopened.memory_search_results(initial)['candidate_count'] == 4
        assert reopened.memory_rule_info(rule)['progress']['applications'] == 1


def test_native_backend_through_retained_json_workspace(tmp_path):
    from fdisbull.cli import respond
    from fdisbull.debugger import DebugWorkspace
    executable, options = selected_qemu()
    _, symbols, project = create_boot_project(tmp_path)
    with project:
        pass
    workspace = DebugWorkspace()
    database = tmp_path / 'boot.fdb'

    def invoke(method, **params):
        response = respond(dict(method=method, params=dict(project=str(database), **params)),
                           debugger=workspace)
        assert response['ok'], response
        return response['result']

    try:
        start = invoke('debug-launch', executable=executable, game_dir=str(tmp_path), **options)
        run = start['run']
        assert invoke('debug-contexts', run=run)['selected'] == 'machine'
        point = invoke('debug-breakpoint', run=run, context='machine', address=symbols['loop'])
        stopped = invoke('debug-run', run=run, context='machine', timeout_ms=15000)
        assert stopped['outcome'] == 'breakpoint'
        assert point['breakpoint_id'] in stopped['session']['stop_reason']['breakpoint_ids']
        registers = invoke('debug-registers', run=run, context='machine')
        assert int(registers['instruction_pointer'], 16) == symbols['loop_ip']
        assert invoke('debug-stop', run=run)['process_reaped']
    finally:
        workspace.close()


def test_native_script_composes_observations_and_single_step(tmp_path):
    executable, options = selected_qemu()
    _, symbols, project = create_boot_project(tmp_path)
    with project:
        with project.debugger(executable, tmp_path, **options) as debug:
            enter_loop(debug, symbols)
            result = debug.script({'format': 'fdisbull-script-1', 'backend': 'qemu-dos', 'steps': [
                {'op': 'status', 'as': 'status'},
                {'op': 'assert', 'value': '$status.state', 'equals': 'stopped'},
                {'op': 'registers', 'as': 'registers'},
                {'op': 'assert', 'value': '$registers.cpu_mode', 'equals': 'real'},
                {'op': 'memory-snapshot', 'address': symbols['counter'], 'length': 2,
                 'task_id': 'authored-script-counter', 'as': 'snapshot'},
                {'op': 'step'},
                {'op': 'memory', 'address': symbols['counter'], 'length': 2, 'as': 'after'},
                {'op': 'assert', 'value': '$after.hex', 'equals': '0800'},
            ]})
            assert result['ok'] and result['completed_steps'] == 8, result


def test_real_freedos_boot_executes_dos_services(tmp_path):
    executable, options = selected_qemu()
    source = os.environ.get('FDISBULL_QEMU_DOS_BOOT_IMAGE')
    mcopy = os.environ.get('FDISBULL_QEMU_DOS_MCOPY') or shutil.which('mcopy')
    if not source or not mcopy:
        message = 'DOS-service qualification needs FDISBULL_QEMU_DOS_BOOT_IMAGE and mcopy'
        if os.environ.get('FDISBULL_REQUIRE_QEMU_DOS_OS') == '1':
            pytest.fail(message)
        pytest.skip(message)
    source = Path(source).expanduser().resolve(strict=True)
    nonce = bytes.fromhex('6373228f083b4b15921df1d665d97a0b')
    image = tmp_path / 'freedos-probe.img'
    identity = prepare_freedos_image(source, image, mcopy, nonce)
    with Project.create(tmp_path / 'freedos.fdb', image, arch='x86', bits=32,
                        base=0x7c00, entry=0x7c00) as project:
        with project.debugger(executable, tmp_path, **options) as debug:
            # Bounded CPU runs inspect the helper's nonce-bound report; an
            # execution breakpoint then establishes its exact completion PC.
            # A timed stop could otherwise land inside a BIOS timer interrupt.
            report = None
            for _ in range(5):
                stopped = debug.run(timeout_ms=1000)
                assert stopped['outcome'] == 'timeout', stopped
                data = bytes.fromhex(debug.memory(PROBE_REPORT_ADDRESS,
                                                  length=PROBE_REPORT_SIZE)['hex'])
                try:
                    report = parse_dos_report(data)
                except ValueError:
                    continue
                assert report['nonce'] == nonce.hex()
                ready = debug.breakpoint(report['linear_pc'])
                reached = debug.run(timeout_ms=1000)
                assert reached['outcome'] == 'breakpoint', reached
                debug.delete_breakpoint(ready['breakpoint_id'])
                registers = debug.registers()
                assert int(registers['linear_pc'], 16) == report['linear_pc']
                break
            assert report is not None, 'FreeDOS did not execute the authored DOS-service probe'
            assert report['nonce'] == nonce.hex()
            assert report['dos_major'] > 0 and report['dos_oem'] == 0xfd  # FreeDOS OEM ID
            assert report['wait_ip'] == identity['probe']['wait_ip']
            assert registers['cpu_mode'] == 'real'
            assert int(registers['registers']['cs'], 16) == report['cs'] != 0
            # AH=09h must have reached DOS's display path, independently of
            # the report's own stores into the unused text-memory page.
            screen = bytes.fromhex(debug.memory(0xb8000, length=4000)['hex'])[::2]
            assert PROBE_MESSAGE in screen
            frame = debug.screenshot('freedos-service-probe.png')
            assert frame['metadata']['width'] > 0
    assert hashlib.sha256(source.read_bytes()).hexdigest() == identity['source_sha256']
    assert hashlib.sha256(image.read_bytes()).hexdigest() == identity['prepared_sha256']
