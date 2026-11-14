"""Native witnesses for caller-declared renderer-pixel displacement mapping.

FDISBULL_QEMU_CLOCK selects candidate eleven; FDISBULL_QEMU_MAPPED_MOUSE_LEGACY
selects retained ten. An authored IRQ12/main-loop application supplies literal
packet, position and pixel expectations independently of the public planner.
Its gain and clean device state are fixture facts, never generic INT33, FIFO,
cursor-origin, target or completed-frame guarantees.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import time
import uuid

import pytest

from fdisbull.cli import public_addresses, respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.output_limits import OutputPolicy, output_policy_context
from fdisbull.project import Project
from support.dos_process_fixture import digest
from support.qemu_mapped_mouse_fixture import COMMANDS, mapped_mouse_probe
from test_qemu_clock_budget_native import budget_receipt, clock_disk, clock_runtime, park
from test_qemu_dos_process_native import (
    com_address, create_project, launch_options, process_record, read_bytes,
)
from test_qemu_input_retrace_native import frozen, word
from test_qemu_mouse_click_native import assert_guest_packets
from test_qemu_retrace_native import artifact_document
from test_qemu_timing_native import assert_sync, native_executions


COMMAND = 'x-fdisbull-arm-display-motion'
DELAY_NS = 2_000_000
EXECUTE_NS = 5_000_000
PERIOD_NS = 10_000_000


@pytest.fixture
def mapped_mouse_witness(tmp_path, clock_runtime, clock_disk):
    serial = 0

    @contextmanager
    def launch(*, executable=None):
        nonlocal serial
        serial += 1
        directory = tmp_path / f'mapped-mouse-{serial}'
        directory.mkdir()
        code, offsets = mapped_mouse_probe(directory, clock_runtime['nasm'])
        binary, project = create_project(directory, code)
        selected = (clock_runtime['executable'] if executable is None
                    else Path(executable).expanduser().resolve(strict=True))
        debug = None
        try:
            with project:
                try:
                    with project.debugger(selected, directory, **launch_options(
                            clock_runtime, clock_disk, qemu_clock='virtual',
                            qemu_retrace='precise')) as debug:
                        info = process_record(debug)
                        symbols = {key: com_address(info, value) for key, value in offsets.items()}
                        park(debug, symbols['ready_ip'])
                        assert word(debug, symbols, 'setup_status_ip') == 1
                        assert read_bytes(debug, symbols['setup_ack_ip'], 1) == b'\xfa'
                        assert read_bytes(debug, symbols['initial_packet_ip'], 3) == b'\x08\x00\x00'
                        assert_guest_packets(debug, symbols, b'')
                        assert_application(debug, symbols, position=(100, 80), committed=0, drawn=0)
                        yield project, debug, symbols
                finally:
                    if debug is not None:
                        assert debug.vm.process.poll() is not None
        finally:
            assert binary.read_bytes() == code
            assert digest(clock_disk['image']) == clock_disk['prepared_sha256']

    return launch


def set_byte(debug, symbols, name, value):
    address = symbols[name + '_ip']
    old = read_bytes(debug, address, 1)
    debug.write_memory(address, bytes([value]).hex(), expected_hex=old.hex())


def assert_application(debug, symbols, *, position, committed, drawn, drawn_position=None):
    assert word(debug, symbols, 'application_sequence_ip') == committed
    assert word(debug, symbols, 'draw_sequence_ip') == drawn
    assert (word(debug, symbols, 'pointer_x_ip'), word(debug, symbols, 'pointer_y_ip')) == position
    if drawn_position is None:
        drawn_position = position if drawn else (100, 80)
    assert (word(debug, symbols, 'drawn_x_ip'), word(debug, symbols, 'drawn_y_ip')) == drawn_position
    assert word(debug, symbols, 'outside_draws_ip') == 0


def retain_publication(debug):
    debug.display_start(period_ns=PERIOD_NS)
    budget_receipt(debug.clock_advance(25_000_000, timeout_ms=5000), 25_000_000)
    debug.display_stop()
    observed = debug.vga_configuration_observe()
    assert observed['display']['state'] == 'stopped'
    assert observed['display']['updates'] > 0
    assert observed['configuration_matches'] is True
    return observed


def scales(observed):
    display = observed['display']
    assert display['width'] % 320 == display['height'] % 200 == 0
    return display['width'] // 320, display['height'] // 200


def request(observed, x=12, y=9):
    """Declare fixture calibration in the retained image's actual pixel units."""
    sx, sy = scales(observed)
    return dict(dx_pixels=x * sx, dy_pixels=y * sy,
                counts_per_pixel={'x': [1, 2 * sx], 'y': [1, 3 * sy]},
                window=observed['display']['window'], update_id=observed['display']['update_id'],
                configuration_generation=observed['current']['configuration_generation'])


def colors(debug, observed, points):
    sx, sy = scales(observed)
    display = observed['display']
    sampled = debug.display_probe([[x * sx, y * sy] for x, y in points],
        window=display['window'], update_id=display['update_id'])
    assert sampled['completed_guest_frame'] is sampled['guest_frame_id'] is None
    return [pixel['rgb'] for pixel in sampled['pixels']]


def assert_native_motion(native, counts, *, state, checked):
    assert native['state'] == state
    assert native['event-count'] == sum(value != 0 for value in counts)
    assert native['deadline-ns'] == native['start-ns'] + DELAY_NS
    assert not {'press', 'typing', 'click', 'retrace'} & native.keys()
    motion = native['motion']
    assert (motion['dx'], motion['dy'], motion['delay-ns']) == (*counts, DELAY_NS)
    assert ('checked' in motion) is checked
    assert motion['armed']['display']['state'] == 'stopped'
    assert motion['armed']['display']['updates'] > 0
    if checked:
        assert motion['checked']['current']['virtual-ns'] == native['terminal-ns']
        assert native['terminal-ns'] >= native['deadline-ns']
    if state == 'dispatched':
        assert native['dispatch-ns'] == native['terminal-ns']
    else:
        assert 'dispatch-ns' not in native
    return motion


def assert_motion(value, arguments, counts, *, state, checked=False):
    assert value['format'] == 'fdisbull-qemu-scheduled-input-1'
    assert value['state'] == state
    assert value['guest_consumed'] is value['device_queue_accepted'] is None
    assert value['requires_resolution'] is (state == 'cancelled')
    assert value['edge_count'] == len(value['sequences']) == sum(item != 0 for item in counts)
    native = assert_native_motion(value['native'], counts, state=state, checked=checked)
    motion = value['motion']
    assert motion['format'] == 'fdisbull-mapped-mouse-motion-1'
    for name in ('dx_pixels', 'dy_pixels', 'counts_per_pixel'):
        assert motion[name] == arguments[name]
    assert (motion['dx'], motion['dy']) == counts
    assert motion['delay_ns'] == DELAY_NS
    assert motion['native_arm'] == native['armed'] == motion['before']['native']
    assert motion['native_check'] == native.get('checked')
    assert motion['binding_verified'] is (state == 'dispatched')
    assert motion['before']['display']['window'] == arguments['window']
    assert motion['before']['display']['update_id'] == arguments['update_id']
    assert motion['before']['current']['configuration_generation'] == arguments['configuration_generation']
    for name in ('guest_pixel_displacement', 'guest_pointer_position', 'mapping_verified',
                 'raster_coherence', 'target_reached'):
        assert motion[name] is None
    return motion


def transition(result, armed, arguments, counts, *, state='dispatched', checked=True):
    value = result['input_delivery']
    assert_motion(value, arguments, counts, state=state, checked=checked)
    for name in ('token', 'run', 'epoch', 'start_ns', 'deadline_ns', 'sequences'):
        assert value[name] == armed[name]
    for name in ('before', 'native_arm'):
        assert value['motion'][name] == armed['motion'][name]
    return value


def native_arguments(observed, counts):
    current, display = observed['current'], observed['display']
    expected = {'epoch': observed['native_epoch'], 'virtual-ns': current['observed_ns'],
        'device': current['device'], 'model': current['model'],
        'configuration-generation': current['configuration_generation'],
        'window': display['window'], 'update-id': display['update_id'],
        'published-ns': display['published_ns'], 'width': display['width'], 'height': display['height']}
    return {'token': uuid.uuid4().hex, 'dx': counts[0], 'dy': counts[1], 'expected': expected}


@pytest.mark.parametrize('pixels,counts,packet,position,executor', [
    ((12, 9), (6, 3), b'\x28\x06\xfd', (112, 89), 'run'),
    ((-12, -9), (-6, -3), b'\x18\xfa\x03', (88, 71), 'advance'),
    ((0, 12), (0, 4), b'\x28\x00\xfc', (100, 92), 'sync'),
], ids=['positive-anisotropic', 'signed-anisotropic', 'single-axis-explicit-sync'])
def test_native_mapped_motion_is_passive_with_independent_packet_commit_and_draw_fences(
        mapped_mouse_witness, monkeypatch, pixels, counts, packet, position, executor):
    with mapped_mouse_witness() as (_, debug, symbols):
        assert debug.capabilities['mapped_mouse_motion'] is True
        for capability in ('timed_input', 'absolute_mouse', 'guest_time_control', 'completed_guest_frames'):
            assert debug.capabilities[capability] is False
        observed = retain_publication(debug)
        arguments = request(observed, *pixels)
        assert colors(debug, observed, [(100, 80), position]) == [[255, 0, 0], [0, 0, 0]]
        synchronization = (debug.clock_sync_start(tolerance_ns=0,
            max_lag_ns=2_000_000_000, max_wait_ns=2_000_000_000) if executor == 'sync' else None)
        before = debug.clock_observe()
        registers = debug.registers()
        calls = native_executions(debug, monkeypatch)
        armed = debug.mouse_move_mapped(**arguments)
        assert_motion(armed, arguments, counts, state='armed')
        assert not calls and debug.registers() == registers
        paused = debug.clock_observe()
        assert paused['virtual_ns'] == before['virtual_ns'] == armed['start_ns']
        assert paused['counter']['value'] == before['counter']['value']
        assert_guest_packets(debug, symbols, b'')
        pending = debug.input_state()
        assert pending['leases'] == {}
        assert [item['event'] for item in pending['pending']] == [
            dict(type='rel', data=dict(axis=axis, value=count))
            for axis, count in zip(('x', 'y'), counts, strict=True) if count]
        assert debug.input_schedule_observe()['motion'] == armed['motion']

        if executor == 'run':
            result = park(debug, symbols['after_packet_ip'])
            assert result['outcome'] == 'breakpoint'
        elif executor == 'sync':
            # Deliberate bounded caller work, outside the passive arm. The
            # observed host interval and actual native budget remain evidence.
            time.sleep(.020)
            synced = debug.clock_sync_step(timeout_ms=5000)
            assert_sync(synced, anchor=synchronization)
            assert synced['action'] == 'advance' and synced['outcome'] == 'advanced'
            result = synced['execution']
            assert result['clock_budget']['deadline_ns'] == synced['target_ns']
            assert synced['target_ns'] > armed['deadline_ns']
            debug.clock_sync_stop()
        else:
            result = debug.clock_advance(EXECUTE_NS, timeout_ms=5000)
            budget_receipt(result, EXECUTE_NS, before=before)
        delivered = transition(result, armed, arguments, counts)
        assert len(calls) == 1 and calls[0]['command'] == 'c'
        assert_guest_packets(debug, symbols, packet)
        assert_application(debug, symbols, position=(100, 80), committed=0, drawn=0)
        assert debug.input_state()['pending_edges'] == 0

        set_byte(debug, symbols, 'commit_gate', 1)
        park(debug, symbols['after_commit_ip'])
        assert_application(debug, symbols, position=position, committed=1, drawn=0)
        assert read_bytes(debug, 0xa0000 + 80 * 320 + 100, 1) == b'\x04'
        assert read_bytes(debug, 0xa0000 + position[1] * 320 + position[0], 1) == b'\x00'
        set_byte(debug, symbols, 'draw_gate', 1)
        park(debug, symbols['after_draw_ip'])
        assert_application(debug, symbols, position=position, committed=1, drawn=1)
        assert read_bytes(debug, 0xa0000 + 80 * 320 + 100, 1) == b'\x00'
        assert read_bytes(debug, 0xa0000 + position[1] * 320 + position[0], 1) == b'\x04'
        # A stopped retained raster remains older than this known guest draw.
        assert colors(debug, observed, [(100, 80), position]) == [[255, 0, 0], [0, 0, 0]]
        later = retain_publication(debug)
        assert colors(debug, later, [(100, 80), position]) == [[0, 0, 0], [255, 0, 0]]
        assert debug.input_schedule_observe()['motion'] == delivered['motion']
        assert_guest_packets(debug, symbols, packet)


def test_native_wrong_declared_scale_and_axis_sign_are_not_verified_pixel_travel(mapped_mouse_witness):
    with mapped_mouse_witness() as (_, debug, symbols):
        observed = retain_publication(debug)
        arguments = request(observed)
        sx, sy = scales(observed)
        arguments['counts_per_pixel'] = {'x': [1, sx], 'y': [-1, 3 * sy]}
        set_byte(debug, symbols, 'commit_gate', 1)
        set_byte(debug, symbols, 'draw_gate', 1)
        armed = debug.mouse_move_mapped(**arguments)
        result = debug.clock_advance(EXECUTE_NS, timeout_ms=5000)
        delivered = transition(result, armed, arguments, (12, -3))
        assert_guest_packets(debug, symbols, b'\x08\x0c\x03')
        assert_application(debug, symbols, position=(124, 71), committed=1, drawn=1)
        later = retain_publication(debug)
        assert colors(debug, later, [(112, 89), (124, 71)]) == [[0, 0, 0], [255, 0, 0]]
        assert delivered['motion']['binding_verified'] is True
        assert delivered['motion']['mapping_verified'] is delivered['motion']['target_reached'] is None


@pytest.mark.parametrize('mutation,increments', [('page', 1), ('page_aba', 2)])
def test_native_running_configuration_change_cancels_before_any_rel_callback(
        mapped_mouse_witness, mutation, increments):
    with mapped_mouse_witness() as (_, debug, symbols):
        observed = retain_publication(debug)
        arguments = request(observed)
        armed = debug.mouse_move_mapped(**arguments)
        set_byte(debug, symbols, 'command', COMMANDS[mutation])
        # No intermediate breakpoint or configuration query hides the race.
        result = debug.clock_advance(EXECUTE_NS, timeout_ms=5000)
        cancelled = transition(result, armed, arguments, (6, 3), state='cancelled')
        assert cancelled['native']['reason'] == 'display-motion-configuration-changed'
        assert word(debug, symbols, 'commands_completed_ip') == 1
        assert word(debug, symbols, 'configuration_writes_ip') == increments
        assert read_bytes(debug, symbols['last_command_ip'], 1) == bytes([COMMANDS[mutation]])
        before = armed['motion']['native_arm']['current']
        checked = cancelled['motion']['native_check']['current']
        assert checked['configuration-generation'] == before['configuration-generation'] + increments
        guest_page = read_bytes(debug, symbols['page_read_ip'], 1)[0]
        assert guest_page == checked['raw']['crtc'][0x0d]
        if mutation == 'page_aba':
            assert checked['raw'] == before['raw']
        else:
            assert guest_page == before['raw']['crtc'][0x0d] ^ 0x20
        assert_guest_packets(debug, symbols, b'')
        assert_application(debug, symbols, position=(100, 80), committed=0, drawn=0)
        assert debug.input_state()['pending_edges'] == 2
        assert debug.input_cancel_pending()['cancelled_edges'] == 2


def test_native_paused_qom_change_precedes_simultaneous_publication_change(mapped_mouse_witness):
    with mapped_mouse_witness() as (_, debug, symbols):
        observed = retain_publication(debug)
        arguments = request(observed)
        armed = debug.mouse_move_mapped(**arguments)
        before = debug.clock_observe()
        original = observed['current']['raw']['big-endian-framebuffer']
        debug.vm.qmp.call('qom-set', {'path': observed['current']['device'],
            'property': 'big-endian-framebuffer', 'value': not original})
        debug.display_start(period_ns=PERIOD_NS)
        debug.display_stop()
        assert debug.clock_observe()['virtual_ns'] == before['virtual_ns']
        result = debug.clock_advance(EXECUTE_NS, timeout_ms=5000)
        cancelled = transition(result, armed, arguments, (6, 3), state='cancelled')
        checked = cancelled['motion']['native_check']
        assert checked['current']['raw']['big-endian-framebuffer'] is (not original)
        assert checked['current']['configuration-generation'] == arguments['configuration_generation'] + 1
        assert checked['display']['token'] != armed['motion']['native_arm']['display']['token']
        assert cancelled['native']['reason'] == 'display-motion-configuration-changed'
        assert_guest_packets(debug, symbols, b'')
        debug.input_cancel_pending()


def test_native_ignored_writes_palette_and_vram_preserve_binding_without_raster_claim(mapped_mouse_witness):
    with mapped_mouse_witness() as (_, debug, symbols):
        observed = retain_publication(debug)
        arguments = request(observed)
        armed = debug.mouse_move_mapped(**arguments)
        set_byte(debug, symbols, 'command', COMMANDS['excluded'])
        result = debug.clock_advance(EXECUTE_NS, timeout_ms=5000)
        delivered = transition(result, armed, arguments, (6, 3))
        assert word(debug, symbols, 'commands_completed_ip') == 1
        assert read_bytes(debug, symbols['cr0_read_ip'], 1) == read_bytes(debug, symbols['original_cr0_ip'], 1)
        assert read_bytes(debug, symbols['page_read_ip'], 1) == read_bytes(debug, symbols['original_page_ip'], 1)
        checked = delivered['motion']['native_check']['current']
        original = armed['motion']['native_arm']['current']
        assert checked['configuration-generation'] == original['configuration-generation']
        assert checked['raw'] == original['raw']
        assert_guest_packets(debug, symbols, b'\x28\x06\xfd')
        assert_application(debug, symbols, position=(100, 80), committed=0, drawn=0)
        assert colors(debug, observed, [(100, 80), (20, 20)]) == [[255, 0, 0], [0, 0, 0]]
        later = retain_publication(debug)
        assert colors(debug, later, [(100, 80), (20, 20)]) == [[0, 0, 255], [0, 255, 0]]
        assert delivered['motion']['raster_coherence'] is delivered['motion']['guest_pixel_displacement'] is None


def test_native_active_and_replaced_windows_refuse_or_cancel_the_exact_publication(
        mapped_mouse_witness, monkeypatch):
    with mapped_mouse_witness() as (_, debug, symbols):
        debug.display_start(period_ns=PERIOD_NS)
        debug.clock_advance(25_000_000, timeout_ms=5000)
        active = debug.vga_configuration_observe()
        arguments = request(active)
        calls = native_executions(debug, monkeypatch)
        before = debug.clock_observe()
        with pytest.raises(ValueError):
            debug.mouse_move_mapped(**arguments)
        assert not calls and debug.input_state()['pending_edges'] == 0
        assert debug.clock_observe()['virtual_ns'] == before['virtual_ns']
        debug.display_stop()
        with pytest.raises(ValueError):
            debug.mouse_move_mapped(**{**arguments, 'update_id': arguments['update_id'] + 1})
        assert not calls and debug.input_state()['pending_edges'] == 0

        for leave_active in (False, True):
            current = retain_publication(debug)
            arguments = request(current)
            armed = debug.mouse_move_mapped(**arguments)
            debug.display_start(period_ns=PERIOD_NS)
            if not leave_active:
                debug.display_stop()
            result = debug.clock_advance(EXECUTE_NS, timeout_ms=5000)
            cancelled = transition(result, armed, arguments, (6, 3), state='cancelled')
            assert cancelled['native']['reason'] == 'display-motion-publication-changed'
            checked = cancelled['motion']['native_check']
            assert checked['current']['configuration-generation'] == arguments['configuration_generation']
            assert checked['display']['token'] != current['native']['display']['token']
            assert checked['display']['updates'] == 0 and 'published' not in checked
            assert checked['display']['state'] == ('observing' if leave_active else 'stopped')
            assert_guest_packets(debug, symbols, b'')
            assert debug.input_cancel_pending()['cancelled_edges'] == 2
            debug.display_stop()


@pytest.mark.parametrize('budget_first', [False, True], ids=['motion-first', 'budget-first'])
def test_native_equal_budget_precedes_guard_sampling_and_motion_in_both_arm_orders(
        mapped_mouse_witness, budget_first):
    with mapped_mouse_witness() as (_, debug, symbols):
        observed = retain_publication(debug)
        arguments = request(observed)
        if budget_first:
            budget_token = uuid.uuid4().hex
            clock_arm = debug.vm.qmp.call('x-fdisbull-arm-clock-budget',
                {'token': budget_token, 'delta-ns': DELAY_NS})
            raw_arguments = native_arguments(observed, (6, 3))
            native_arm = debug.vm.qmp.call(COMMAND, raw_arguments)
            assert_native_motion(native_arm, (6, 3), state='armed', checked=False)
            assert native_arm['start-ns'] == clock_arm['budget-start-ns']
            result = debug.run(timeout_ms=5000)
            assert result['outcome'] == 'stopped' and result['timed_out'] is False
            stopped = debug.vm.qmp.call('x-fdisbull-query-clock')
            native = debug.vm.qmp.call('x-fdisbull-query-input')
            assert stopped['budget-state'] == 'stopped'
            assert_native_motion(native, (6, 3), state='cancelled', checked=False)
            assert native['deadline-ns'] == stopped['budget-deadline-ns']
            assert native['terminal-ns'] == stopped['budget-stopped-ns']
            debug.vm.qmp.call('x-fdisbull-cancel-clock-budget', {'token': budget_token})
            assert debug.vm.qmp.call('x-fdisbull-cancel-input', {'token': raw_arguments['token']}) == native
        else:
            armed = debug.mouse_move_mapped(**arguments)
            result = debug.clock_advance(DELAY_NS, timeout_ms=5000)
            budget_receipt(result, DELAY_NS)
            cancelled = transition(result, armed, arguments, (6, 3), state='cancelled', checked=False)
            native = cancelled['native']
            assert native['deadline-ns'] == result['clock_budget']['deadline_ns']
            assert debug.input_cancel_pending()['cancelled_edges'] == 2
        assert native['reason'] in ('machine-stop', 'stop-pending', 'budget-deadline')
        assert_guest_packets(debug, symbols, b'')
        debug.clock_advance(EXECUTE_NS, timeout_ms=5000)
        assert_guest_packets(debug, symbols, b'')
        assert frozen(debug.vm.qmp.call('x-fdisbull-query-input')) == frozen(native)


def test_native_first_stop_requires_explicit_cancel_and_never_converts_or_replays_motion(
        mapped_mouse_witness, monkeypatch):
    with mapped_mouse_witness() as (_, debug, symbols):
        observed = retain_publication(debug)
        arguments = request(observed)
        armed = debug.mouse_move_mapped(**arguments)
        point = debug.breakpoint(symbols['main_loop_ip'])
        calls = native_executions(debug, monkeypatch)
        try:
            result = debug.run(timeout_ms=5000)
            assert result['outcome'] == 'breakpoint'
            cancelled = transition(result, armed, arguments, (6, 3), state='cancelled', checked=False)
            assert cancelled['terminal_ns'] < armed['deadline_ns']
            assert_guest_packets(debug, symbols, b'')
            pending = deepcopy(debug.input_state()['pending'])
            for operation in (lambda: debug.input_schedule(DELAY_NS), debug.input_schedule_retrace,
                              lambda: debug.mouse_move_mapped(**arguments), lambda: debug.run(timeout_ms=1000)):
                with pytest.raises(ValueError):
                    operation()
            assert len(calls) == 1 and debug.input_state()['pending'] == pending
        finally:
            debug.delete_breakpoint(point['breakpoint_id'])
        resolved = debug.input_cancel_pending()
        assert resolved['cancelled_edges'] == 2 and resolved['cancelled_leases'] == []
        assert debug.input_state()['pending_edges'] == 0 and debug.input_state()['leases'] == {}
        debug.clock_advance(EXECUTE_NS, timeout_ms=5000)
        assert_guest_packets(debug, symbols, b'')
        second = debug.mouse_move_mapped(**arguments)
        assert second['token'] != armed['token']
        assert debug.input_cancel_pending()['cancelled_edges'] == 2
        debug.clock_advance(EXECUTE_NS, timeout_ms=5000)
        assert_guest_packets(debug, symbols, b'')
        fresh = debug.mouse_move_mapped(**arguments)
        delivered = debug.clock_advance(EXECUTE_NS, timeout_ms=5000)
        transition(delivered, fresh, arguments, (6, 3))
        assert_guest_packets(debug, symbols, b'\x28\x06\xfd')


def test_native_mapped_motion_json_script_journal_and_reopen_preserve_frozen_evidence(
        mapped_mouse_witness, monkeypatch):
    with (tempfile.TemporaryDirectory(prefix='fdisbull-mapped-output-', dir='/tmp') as temporary,
          mapped_mouse_witness() as (project, debug, symbols)):
        output_directory = Path(temporary).resolve(strict=True)
        observed = retain_publication(debug)
        arguments = request(observed, 4, 6)
        set_byte(debug, symbols, 'commit_gate', 1)
        set_byte(debug, symbols, 'draw_gate', 1)
        workspace = DebugWorkspace()
        workspace.sessions[debug.run_id] = debug
        policy = OutputPolicy(artifact_dir=output_directory / 'artifacts')
        assert policy.max_inline_bytes == 65536
        calls = native_executions(debug, monkeypatch)
        spills = []

        def invoke(method, **params):
            with output_policy_context(policy):
                reply = respond(dict(id='mapped-mouse', method=method,
                    params=dict(project=str(project.path), run=debug.run_id, **params)), debugger=workspace)
                assert reply['ok'], reply
                reference = reply['result']
                if reference.get('format') == 'fdisbull-output-ref-1':
                    assert reference['complete'] is False and reference['status'] == 'artifact_required', reference
                    assert reference['retry_safe'] is False and reference['execution']['ok'] is True
                    assert reference['execution']['returned'] is True
                    assert reference['inline_limit_bytes'] == policy.max_inline_bytes
                    artifact = reference['artifact']
                    assert reference['total_bytes'] == artifact['bytes']
                    assert artifact['bytes'] + 1 > policy.max_inline_bytes
                    spills.append((method, deepcopy(reference)))
                    destination = output_directory / f'mapped-response-{len(spills)}.json'
                    executions_before_export = len(calls)
                    exported = respond(dict(id='mapped-output-export', method='output-export',
                        params=dict(artifact=artifact['id'], output=str(destination))))
                    assert exported['ok'], exported
                    metadata = exported['result']
                    assert metadata['complete'] is True
                    assert {key: metadata[key] for key in artifact} == artifact
                    assert metadata['path'] == str(destination)
                    payload = destination.read_bytes()
                    assert len(payload) == artifact['bytes']
                    assert digest(destination) == artifact['sha256']
                    original = json.loads(payload)
                    assert original['id'] == reply['id']
                    assert original['ok'] is reference['execution']['ok']
                    assert len(calls) == executions_before_export
                    # The retained artifact is the full original RPC response.
                    # Retrieval never repeats the operation that produced it.
                    reply = original
            assert reply['ok'], reply
            return reply['result']

        try:
            armed = invoke('debug-mouse-move-mapped', **arguments)
            assert_motion(armed, arguments, (2, 2), state='armed')
            first = invoke('debug-clock-advance', delta_ns=EXECUTE_NS, timeout_ms=5000)
            transition(first, armed, arguments, (2, 2))
            assert_guest_packets(debug, symbols, b'\x28\x02\xfe')
            assert_application(debug, symbols, position=(104, 86), committed=1, drawn=1)
            opposite = request(observed, -4, -6)
            script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
                dict(op='mouse.move-mapped', **opposite),
                dict(op='clock-advance', delta_ns=EXECUTE_NS, timeout_ms=5000),
                dict(op='input-schedule-observe')])
            report = invoke('debug-script', script=script, timeout_ms=10000)
            assert [method for method, _ in spills].count('debug-script') == 1
            assert policy.delivery_failed is False
            assert report['ok'] and report['completed_steps'] == 3, report
            second_arm, second_result, retained = [row['result'] for row in report['steps']]
            delivered = transition(second_result, second_arm, opposite, (-2, -2))
            assert second_arm['token'] != armed['token']
            assert retained['motion'] == delivered['motion']
            assert_guest_packets(debug, symbols, b'\x28\x02\xfe\x18\xfe\x02')
            assert_application(debug, symbols, position=(100, 80), committed=2, drawn=2)
            assert [call['command'] for call in calls] == ['c', 'c']
            assert project.db.execute(
                "SELECT count(*) FROM debug_events WHERE run=? AND operation='input.schedule-arm'",
                (debug.run_id,)).fetchone()[0] == 2
            assert debug.input_state()['pending_edges'] == 0 and debug.input_state()['leases'] == {}
            path, run = project.path, debug.run_id
        finally:
            workspace.sessions.clear()
    with Project(path) as reopened:
        assert artifact_document(reopened, report['script_artifact']) == script
        saved = artifact_document(reopened, report['artifact'])
        assert public_addresses(saved) == {key: value for key, value in report.items() if key != 'artifact'}
        evidence = [json.loads(row[0]) for row in reopened.db.execute(
            "SELECT evidence FROM debug_events WHERE run=? AND operation IN "
            "('input.schedule-arm','input.schedule-result','input.schedule-observe') ORDER BY sequence", (run,))]
        assert armed in [public_addresses(item) for item in evidence]
        assert saved['steps'][0]['result'] in evidence
        assert saved['steps'][1]['result']['input_delivery'] in evidence
        assert saved['steps'][2]['result'] in evidence
        assert reopened.debug_runs()['live_state_verified'] is False
        assert not reopened._live_debuggers


def test_native_ten_layer_runtime_refuses_only_new_mapping_and_retains_relative_input(
        mapped_mouse_witness, monkeypatch):
    legacy = os.environ.get('FDISBULL_QEMU_MAPPED_MOUSE_LEGACY')
    if not legacy:
        message = 'Set FDISBULL_QEMU_MAPPED_MOUSE_LEGACY to the retained ten-layer QEMU'
        if os.environ.get('FDISBULL_REQUIRE_QEMU_CLOCK') == '1':
            pytest.fail(message)
        pytest.skip(message)
    with mapped_mouse_witness(executable=legacy) as (_, debug, symbols):
        assert COMMAND not in debug.vm.qmp_commands
        assert debug.capabilities['mapped_mouse_motion'] is False
        assert debug.capabilities['vga_configuration'] is True
        assert debug.capabilities['virtual_input_schedule'] is True
        observed = retain_publication(debug)
        arguments = request(observed)
        before = debug.clock_observe()
        registers = debug.registers()
        calls = native_executions(debug, monkeypatch)
        with pytest.raises(ValueError):
            debug.mouse_move_mapped(**arguments)
        assert not calls and debug.registers() == registers
        assert debug.clock_observe()['virtual_ns'] == before['virtual_ns']
        assert debug.input_state()['pending_edges'] == 0 and debug.input_state()['leases'] == {}
        assert_guest_packets(debug, symbols, b'')
        set_byte(debug, symbols, 'commit_gate', 1)
        set_byte(debug, symbols, 'draw_gate', 1)
        debug.mouse_move_relative(6, 3)
        ordinary = debug.input_schedule(DELAY_NS)
        result = debug.clock_advance(EXECUTE_NS, timeout_ms=5000)
        assert result['input_delivery']['state'] == 'dispatched'
        assert result['input_delivery']['token'] == ordinary['token']
        assert 'motion' not in ordinary['native'] and 'motion' not in result['input_delivery']
        assert_guest_packets(debug, symbols, b'\x28\x06\xfd')
        assert_application(debug, symbols, position=(112, 89), committed=1, drawn=1)


def test_native_raw_motion_rejections_preserve_terminal_receipt_and_reusable_tokens(
        mapped_mouse_witness, monkeypatch):
    with mapped_mouse_witness() as (_, debug, symbols):
        observed = retain_publication(debug)
        before = debug.clock_observe()
        registers = debug.registers()
        calls = native_executions(debug, monkeypatch)
        seed = native_arguments(observed, (6, 3))
        seeded = debug.vm.qmp.call(COMMAND, seed)
        assert_native_motion(seeded, (6, 3), state='armed', checked=False)
        terminal = debug.vm.qmp.call('x-fdisbull-cancel-input', {'token': seed['token']})
        assert_native_motion(terminal, (6, 3), state='cancelled', checked=False)
        assert terminal['terminal-ns'] == before['virtual_ns']

        expected = seed['expected']
        wrong_expected = {
            'epoch': expected['epoch'] + 1,
            'virtual-ns': expected['virtual-ns'] + 1,
            'device': '/machine/not-the-owned-vga',
            'model': 'not-the-vga-configuration-model',
            'configuration-generation': expected['configuration-generation'] + 1,
            'window': expected['window'] + '-stale',
            'update-id': expected['update-id'] + 1,
            'published-ns': expected['published-ns'] + 1,
            'width': expected['width'] + 1,
            'height': expected['height'] + 1,
        }
        assert set(wrong_expected) == set(expected)
        invalid = [dict(expected={**expected, field: value})
                   for field, value in wrong_expected.items()]
        invalid += [dict(dx=dx, dy=dy) for dx, dy in
                    ((0, 0), (128, 3), (-128, 3), (6, 128), (6, -128))]
        for change in invalid:
            valid = native_arguments(observed, (6, 3))
            with pytest.raises(DebuggerError):
                debug.vm.qmp.call(COMMAND, {**valid, **change})
            assert debug.vm.qmp.call('x-fdisbull-query-input') == terminal
            # Each rejected request must leave its own proposed token unused.
            # A valid retry of that exact token proves this for every boundary.
            accepted = debug.vm.qmp.call(COMMAND, valid)
            assert_native_motion(accepted, (6, 3), state='armed', checked=False)
            assert accepted['token'] == valid['token']
            assert accepted['start-ns'] == before['virtual_ns']
            terminal = debug.vm.qmp.call('x-fdisbull-cancel-input', {'token': valid['token']})
            assert_native_motion(terminal, (6, 3), state='cancelled', checked=False)
            assert terminal['terminal-ns'] == before['virtual_ns']
            assert debug.vm.qmp.call('x-fdisbull-query-input') == terminal

        # These are raw native plans throughout; no Python ownership is
        # reconstructed from their receipts and no continue drives a callback.
        ordinary = debug.vm.qmp.call('x-fdisbull-arm-input', {
            'token': uuid.uuid4().hex, 'delta-ns': DELAY_NS,
            'events': [dict(type='rel', data=dict(axis='x', value=1))]})
        assert ordinary['state'] == 'armed' and ordinary['event-count'] == 1
        assert 'motion' not in ordinary
        cancelled = debug.vm.qmp.call('x-fdisbull-cancel-input', {'token': ordinary['token']})
        assert cancelled['state'] == 'cancelled' and 'motion' not in cancelled
        assert debug.vm.qmp.call('x-fdisbull-query-input') == cancelled
        assert not calls and debug.registers() == registers
        after = debug.clock_observe()
        assert after['virtual_ns'] == before['virtual_ns']
        assert after['counter']['value'] == before['counter']['value']
        assert_guest_packets(debug, symbols, b'')
        assert_application(debug, symbols, position=(100, 80), committed=0, drawn=0)
        state = debug.input_state()
        assert state['pending_edges'] == 0 and state['leases'] == {} and state['schedule'] is None
