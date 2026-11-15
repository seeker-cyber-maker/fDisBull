"""Actual virtual-timer input dispatch, stops and independent guest witnesses."""
from contextlib import contextmanager
import io
import json
import struct
import time

from PIL import Image
import pytest

from fdisbull.cli import respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project
from support.dos_process_fixture import com_exit, digest, resident_com
from support.qemu_input_schedule_fixture import halted_keyboard
from support.qemu_io_fixture import raw_keyboard_mouse
from test_qemu_clock_budget_native import clock_runtime, clock_disk, park, budget_receipt
from test_qemu_dos_process_native import (
    assert_completion, com_address, create_project, launch_options, process_record, read_bytes,
)


@pytest.fixture
def input_witness(tmp_path, clock_runtime, clock_disk):
    @contextmanager
    def launch(builder=raw_keyboard_mouse):
        code, offsets = builder(tmp_path, clock_runtime['nasm'])
        binary, project = create_project(tmp_path, code)
        with project:
            with project.debugger(clock_runtime['executable'], tmp_path,
                    **launch_options(clock_runtime, clock_disk, qemu_clock='virtual')) as debug:
                info = process_record(debug)
                symbols = {key: com_address(info, value) if key.endswith('_ip') else value
                           for key, value in offsets.items()}
                park(debug, symbols['ready_ip'])
                assert debug.capabilities['virtual_input_schedule'] is True
                yield project, debug, symbols
            assert debug.vm.process.poll() is not None
        assert binary.read_bytes() == code
        assert digest(clock_disk['image']) == clock_disk['prepared_sha256']
    return launch


def word(debug, symbols, name):
    return struct.unpack('<H', read_bytes(debug, symbols[name], 2))[0]


def dispatched(result, armed):
    receipt = result['input_delivery']
    assert receipt['state'] == 'dispatched' and receipt['token'] == armed['token']
    assert receipt['deadline_ns'] <= receipt['dispatch_ns'] <= result['clock_budget']['stopped_ns']
    assert receipt['lateness_ns'] == receipt['dispatch_ns'] - receipt['deadline_ns']
    assert receipt['guest_consumed'] is receipt['device_queue_accepted'] is None
    assert receipt['requires_resolution'] is False
    return receipt


def test_native_scheduled_keyboard_mouse_and_renderer_join(input_witness):
    with input_witness() as (project, debug, symbols):
        assert word(debug, symbols, 'setup_status_ip') == 1
        display = debug.display_start(period_ns=2_000_000)
        lease = debug.keyboard_key_down('a')['lease']
        armed = debug.input_schedule(5_000_000)
        assert armed['state'] == 'armed'
        assert debug.input_schedule_observe()['native'] == armed['native']
        assert word(debug, symbols, 'keyboard_count_ip') == 0
        for operation in (debug.resume, debug.step, debug.trace):
            with pytest.raises(ValueError, match='Queued physical input'):
                operation()
        result = debug.clock_advance(20_000_000, timeout_ms=5000)
        receipt = dispatched(result, armed)
        assert word(debug, symbols, 'keyboard_count_ip') == 1
        assert read_bytes(debug, symbols['keyboard_bytes_ip'], 1) == b'\x1e'
        assert debug.input_state()['leases'][lease]['make'] == 'native_dispatched'
        captured = debug.capture_display('scheduled-keyboard.png')
        metadata = captured['metadata']
        assert metadata['epoch'] == receipt['epoch'] == display['epoch']
        assert metadata['published_ns'] >= receipt['dispatch_ns']
        assert metadata['completed_guest_frame'] is None
        row = project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',
                                 (captured['artifact'],)).fetchone()
        with Image.open(io.BytesIO(row[0])) as image:
            image = image.convert('RGB')
            assert image.getpixel((10 * (image.width // 320), 10 * (image.height // 200))) == (255, 0, 0)
        debug.keyboard_key_up(lease)
        armed = debug.input_schedule(3_000_000)
        dispatched(debug.clock_advance(15_000_000, timeout_ms=5000), armed)
        assert read_bytes(debug, symbols['keyboard_bytes_ip'], 2) == b'\x1e\x9e'
        debug.mouse_move_relative(5, 0)
        mouse = debug.mouse_button_down('left')['lease']
        armed = debug.input_schedule(3_000_000)
        dispatched(debug.clock_advance(15_000_000, timeout_ms=5000), armed)
        assert read_bytes(debug, symbols['last_mouse_packet_ip'], 3) == b'\x09\x05\x00'
        debug.mouse_button_up(mouse)
        armed = debug.input_schedule(3_000_000)
        dispatched(debug.clock_advance(15_000_000, timeout_ms=5000), armed)
        assert read_bytes(debug, symbols['mouse_bytes_ip'], 6) == b'\x09\x05\x00\x08\x00\x00'
        assert debug.input_state()['leases'] == {} and debug.input_state()['pending_edges'] == 0


def test_native_early_stop_disarms_without_replay_and_allows_explicit_reschedule(input_witness):
    with input_witness() as (_, debug, symbols):
        lease = debug.keyboard_key_down('a')['lease']
        first = debug.input_schedule(5_000_000)
        result = park(debug, symbols['before_draw_ip'])
        receipt = result['input_delivery']
        assert result['outcome'] == 'breakpoint'
        assert receipt['state'] == 'cancelled' and receipt['dispatch_ns'] is None
        assert receipt['terminal_ns'] < receipt['deadline_ns']
        assert receipt['requires_resolution'] is True
        assert word(debug, symbols, 'keyboard_count_ip') == 0
        with pytest.raises(ValueError, match='reschedule or cancel'):
            debug.run(timeout_ms=1000)
        second = debug.input_schedule(3_000_000)
        assert second['token'] != first['token']
        dispatched(debug.clock_advance(15_000_000, timeout_ms=5000), second)
        assert word(debug, symbols, 'keyboard_count_ip') == 1
        debug.keyboard_key_up(lease)
        debug.input_schedule(3_000_000)
        cancelled = debug.input_cancel_pending()
        assert cancelled['cancelled_edges'] == 1
        assert cancelled['retained_dispatched_holds'] == [lease]
        assert debug.input_state()['leases'][lease]['release'] is None
        debug.clock_advance(15_000_000, timeout_ms=5000)
        assert word(debug, symbols, 'keyboard_count_ip') == 1


def test_native_scheduled_input_wakes_hlt_without_host_pacing(input_witness):
    with input_witness(halted_keyboard) as (_, debug, symbols):
        before = debug.clock_observe()
        debug.keyboard_key_down('a')
        armed = debug.input_schedule(5_000_000)
        result = debug.clock_advance(20_000_000, timeout_ms=5000)
        receipt = dispatched(result, armed)
        assert word(debug, symbols, 'key_count_ip') == 1
        assert read_bytes(debug, symbols['last_key_ip'], 1) == b'\x1e'
        assert word(debug, symbols, 'wakes_ip') == 1
        after = debug.clock_observe()
        assert after['virtual_ns'] - before['virtual_ns'] >= 20_000_000
        assert 0 < after['counter']['value'] - before['counter']['value'] < 1000
        assert receipt['dispatch_ns'] < result['clock_budget']['stopped_ns']


@pytest.mark.parametrize('input_delay', [5_000_000, 10_000_000], ids=['equal-deadline', 'later-input'])
def test_native_budget_stop_wins_equal_or_later_input_without_hidden_delivery(input_witness, input_delay):
    with input_witness() as (_, debug, symbols):
        debug.keyboard_key_down('a')
        debug.input_schedule(input_delay)  # Input timer is inserted first.
        result = debug.clock_advance(5_000_000, timeout_ms=5000)
        budget_receipt(result, 5_000_000)
        assert result['input_delivery']['state'] == 'cancelled'
        assert result['input_delivery']['dispatch_ns'] is None
        assert word(debug, symbols, 'keyboard_count_ip') == 0
        debug.input_cancel_pending()
        debug.clock_advance(20_000_000, timeout_ms=5000)
        assert word(debug, symbols, 'keyboard_count_ip') == 0


def test_native_wrong_token_reset_and_owner_invalidation(input_witness):
    with input_witness() as (_, debug, _):
        debug.keyboard_key_down('a')
        armed = debug.input_schedule(1_000_000)
        with pytest.raises(DebuggerError, match='token'):
            debug.vm.qmp.call('x-fdisbull-cancel-input', {'token': 'not-the-owner'})
        assert debug.input_schedule_observe()['native'] == armed['native']
        epoch = debug.clock_observe()['virtual_clock']['native']['epoch']
        debug.vm.qmp.call('set-action', {'reboot': 'reset'})
        debug.vm.qmp.call('system_reset')
        deadline = time.monotonic() + 2
        while debug.vm.qmp.call('x-fdisbull-query-clock')['epoch'] == epoch:
            assert time.monotonic() < deadline
        with pytest.raises(DebuggerError, match='invalid|epoch'):
            debug.vm.qmp.call('x-fdisbull-query-input')
        with pytest.raises(DebuggerError, match='virtual clock'):
            debug.input_schedule_observe()
        assert debug.vm.process.poll() is not None


@pytest.mark.parametrize('resident', [False, True], ids=['dos-exit', 'dos-tsr'])
def test_native_scheduled_input_preserves_dos_completion(tmp_path, clock_runtime, clock_disk, resident):
    code = resident_com(exit_code=37)[0] if resident else com_exit(37)
    binary, project = create_project(tmp_path, code)
    with project:
        with project.debugger(clock_runtime['executable'], tmp_path,
                **launch_options(clock_runtime, clock_disk, qemu_clock='virtual')) as debug:
            process_record(debug)
            debug.keyboard_key_down('a')
            debug.input_schedule(1_000_000_000)
            result = debug.clock_advance(2_000_000_000, timeout_ms=5000)
            assert_completion(debug, result, resident=resident, exit_code=37)
            assert result['input_delivery']['state'] == 'cancelled'
            assert result['input_delivery']['dispatch_ns'] is None
            debug.input_cancel_pending()
        assert debug.vm.process.poll() is not None
    assert binary.read_bytes() == code
    assert digest(clock_disk['image']) == clock_disk['prepared_sha256']


def test_native_json_saved_script_and_reopened_dispatch_evidence(input_witness):
    with input_witness() as (project, debug, symbols):
        workspace = DebugWorkspace()
        workspace.sessions[debug.run_id] = debug
        def invoke(method, **params):
            result = respond(dict(id=1, method=method, params=dict(
                project=str(project.path), run=debug.run_id, **params)), debugger=workspace)
            assert result['ok'], result
            return result['result']
        lease = invoke('debug-keyboard-down', key='a')['lease']
        armed = invoke('debug-input-schedule', delta_ns=3_000_000)
        script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
            dict(op='clock-advance', delta_ns=15_000_000, timeout_ms=5000),
            dict(op='input-schedule-observe', **{'as': 'make'}),
            dict(op='keyboard.key-up', lease=lease),
            dict(op='input-schedule', delta_ns=3_000_000),
            dict(op='clock-advance', delta_ns=15_000_000, timeout_ms=5000),
            dict(op='input-schedule-observe')])
        result = debug.script(script, timeout_ms=12000)
        assert result['ok'] and result['completed_steps'] == len(script['steps']), result
        assert result['steps'][1]['result']['token'] == armed['token']
        last = invoke('debug-input-schedule-observe')
        assert last['state'] == 'dispatched' and last['token'] != armed['token']
        assert read_bytes(debug, symbols['keyboard_bytes_ip'], 2) == b'\x1e\x9e'
        database, artifact = project.path, result['artifact']
        workspace.sessions.clear()
    with Project(database) as reopened:
        row = reopened.db.execute('SELECT data FROM debug_artifacts WHERE id=?', (artifact,)).fetchone()
        saved = json.loads(bytes(row[0]))
        assert saved['steps'][1]['result']['token'] == armed['token']
        assert saved['steps'][5]['result']['state'] == 'dispatched'
        assert reopened.debug_runs()['live_state_verified'] is False
