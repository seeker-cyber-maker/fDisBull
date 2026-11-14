"""Native witnesses for passive, explicitly selected QEMU VGA retrace.

These tests compare a declared emulator timing model with actual guest port
reads. Retrace phase, renderer publication and guest frame completion remain
different observations; no automatic synchronization is exercised here.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import time
import uuid

import pytest

from fdisbull.cli import respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project
from support.dos_process_fixture import com_exit, digest
from support.qemu_retrace_fixture import (
    guest_timing, precise_phase, precise_timing, retrace_ports,
)
from test_qemu_clock_budget_native import (
    budget_receipt, clock_disk, clock_runtime, park,
)
from test_qemu_dos_process_native import (
    assert_completion, com_address, create_project, launch_options, live_word,
    process_disk, process_record, process_runtime, read_bytes,
)


@pytest.fixture
def retrace_witness(tmp_path, clock_runtime, clock_disk):
    serial = 0

    @contextmanager
    def launch(*, profile='precise'):
        nonlocal serial
        serial += 1
        directory = tmp_path / f'retrace-{serial}'
        directory.mkdir()
        code, offsets = retrace_ports(directory, clock_runtime['nasm'])
        binary, project = create_project(directory, code)
        options = launch_options(clock_runtime, clock_disk, qemu_clock='virtual')
        if profile is not None:
            options['qemu_retrace'] = profile
        debug = None
        try:
            with project:
                try:
                    with project.debugger(clock_runtime['executable'], directory, **options) as debug:
                        info = process_record(debug)
                        symbols = {key: com_address(info, value) for key, value in offsets.items()}
                        park(debug, symbols['ready_ip'])
                        yield project, debug, symbols
                finally:
                    if debug is not None:
                        assert debug.vm.process.poll() is not None
        finally:
            assert binary.read_bytes() == code
            assert digest(clock_disk['image']) == clock_disk['prepared_sha256']

    return launch


def raw_timing(debug, symbols):
    return guest_timing(read_bytes(debug, symbols['timing_raw_ip'], 11))


def command(debug, symbols, value, fence):
    old = read_bytes(debug, symbols['command_ip'], 1)
    debug.write_memory(symbols['command_ip'], bytes([value]).hex(), expected_hex=old.hex())
    return park(debug, symbols[fence])


def artifact_document(project, artifact):
    row = project.db.execute('SELECT data,sha256 FROM debug_artifacts WHERE id=?',
                             (artifact,)).fetchone()
    data = bytes(row['data'])
    assert hashlib.sha256(data).hexdigest() == row['sha256']
    return json.loads(data)


def assert_observation(value):
    assert value['format'] == 'fdisbull-retrace-observation-1'
    assert value['context'] == 'machine'
    assert value['clock_domain'] == 'QEMU_CLOCK_VIRTUAL'
    assert value['model'] == 'qemu-vga-precise-fdisbull-v1'
    assert value['device_type'] == 'VGA' and value['device'].startswith('/')
    assert value['console'] == value['head'] == 0
    assert type(value['timing_generation']) is int and value['timing_generation'] >= 1
    native = value['native']
    assert native['api-version'] == 1
    assert native['epoch'] == value['native_epoch']
    assert native['virtual-ns'] == value['observed_ns']
    assert native['timing-generation'] == value['timing_generation']
    assert native['phase-supported'] is value['phase_supported']
    assert native['raw'] == value['raw'] and native['timing'] == value['timing']
    assert native.get('phase') == value['phase']
    assert native.get('unsupported-reason') == value['unsupported_reason']
    before, after = value['clocks']['before'], value['clocks']['after']
    assert before['run'] == after['run'] == value['run']
    assert before['epoch'] == after['epoch'] == value['epoch']
    assert before['sequence'] < after['sequence']
    assert before['virtual_ns'] == after['virtual_ns'] == value['observed_ns']
    assert before['counter']['value'] == after['counter']['value']
    assert before['virtual_clock']['native']['epoch'] == after['virtual_clock']['native']['epoch'] == value['native_epoch']
    assert value['completed_renderer_update'] is value['completed_guest_frame'] is value['guest_frame_id'] is None


def assert_legacy_model(value, raw):
    assert_observation(value)
    assert raw['vbe-enable'] & 1 == 0
    assert value['phase_supported'] and value['unsupported_reason'] is None
    assert value['raw'] == raw
    timing = precise_timing(raw)
    assert value['timing'] == timing
    assert value['phase'] == precise_phase(timing, value['observed_ns'])


def test_native_precise_phase_matches_actual_guest_status_reads(retrace_witness):
    with retrace_witness() as (_, debug, symbols):
        raw = raw_timing(debug, symbols)
        timing = precise_timing(raw)
        first = debug.retrace_observe()
        assert_legacy_model(first, raw)
        command(debug, symbols, 1, 'sample_status_ip')
        period = timing['ticks-per-char'] * timing['total-chars']
        # Both selected points are well inside a modeled line and away from
        # sync edges. Explicit budgets are test setup, not a retrace wait API.
        lines = (timing['vstart'] // 2, (timing['vstart'] + timing['vend']) // 2)
        for vertical, line in zip((False, True), lines, strict=True):
            now = debug.clock_observe()['virtual_ns']
            selected = (line * timing['htotal'] + timing['htotal'] // 4) * timing['ticks-per-char']
            delta = (selected - now) % period or period
            budget_receipt(debug.clock_advance(delta, timeout_ms=3000), delta)
            park(debug, symbols['sample_status_ip'])
            before = debug.retrace_observe()
            assert_legacy_model(before, raw)
            assert before['phase']['vertical-retrace'] is vertical
            result = debug.step(timeout_ms=1000)
            assert result['outcome'] == 'step', result
            sampled = live_word(result['registers'], 'rax', 'eax', 'ax') & 0xff
            after = debug.retrace_observe()
            assert_legacy_model(after, raw)
            # The port read occurred inside this native instruction interval.
            # An unchanged timing bit over the interval avoids inventing its
            # exact intra-instruction I/O timestamp from the later stop.
            assert before['phase']['status1-timing-bits'] == after['phase']['status1-timing-bits']
            assert sampled & 9 == before['phase']['status1-timing-bits']
            assert before['timing_generation'] == after['timing_generation'] == first['timing_generation']
            park(debug, symbols['status_done_ip'])
            assert read_bytes(debug, symbols['sampled_status_ip'], 1) == bytes([sampled])


def test_native_passive_query_preserves_stopped_time_and_attribute_flip_flop(retrace_witness):
    with retrace_witness() as (project, debug, symbols):
        command(debug, symbols, 2, 'attribute_pending_ip')
        registers = debug.registers()
        anchor = debug.clock_observe()
        clock_events = project.db.execute(
            "SELECT count(*) FROM debug_events WHERE run=? AND operation='machine-clock-observe'",
            (debug.run_id,)).fetchone()[0]
        observations = [debug.retrace_observe(timeout_ms=1000) for _ in range(3)]
        for value in observations:
            assert_legacy_model(value, raw_timing(debug, symbols))
            assert value['observed_ns'] == anchor['virtual_ns']
            assert value['clocks']['before']['counter']['value'] == anchor['counter']['value']
        assert observations[0]['native'] == observations[1]['native'] == observations[2]['native']
        assert project.db.execute(
            "SELECT count(*) FROM debug_events WHERE run=? AND operation='machine-clock-observe'",
            (debug.run_id,)).fetchone()[0] == clock_events
        assert debug.registers() == registers
        park(debug, symbols['attribute_done_ip'])
        # If a host query read 3DAh, its ATC flip-flop reset would turn the
        # pending data write into an index write and leave this owned value 0.
        assert read_bytes(debug, symbols['attribute_result_ip'], 1)[0] & 15 == 15
        assert debug.retrace_observe()['timing_generation'] == observations[-1]['timing_generation']


def test_native_cr10_and_unobserved_aba_change_timing_generation(retrace_witness):
    with retrace_witness() as (_, debug, symbols):
        initial = debug.retrace_observe()
        assert_legacy_model(initial, raw_timing(debug, symbols))
        command(debug, symbols, 3, 'cr10_changed_ip')
        changed = debug.retrace_observe()
        assert_legacy_model(changed, raw_timing(debug, symbols))
        assert changed['raw']['cr10'] == initial['raw']['cr10'] ^ 4
        assert changed['timing']['vstart'] != initial['timing']['vstart']
        assert changed['timing_generation'] > initial['timing_generation']
        command(debug, symbols, 4, 'cr10_restored_ip')
        restored = debug.retrace_observe()
        assert_legacy_model(restored, raw_timing(debug, symbols))
        assert restored['raw'] == initial['raw'] and restored['timing'] == initial['timing']
        assert restored['timing_generation'] > changed['timing_generation']
        command(debug, symbols, 5, 'cr10_aba_done_ip')
        aba = debug.retrace_observe()
        assert_legacy_model(aba, raw_timing(debug, symbols))
        assert aba['raw'] == restored['raw'] and aba['timing'] == restored['timing']
        assert aba['timing_generation'] >= restored['timing_generation'] + 2
        command(debug, symbols, 9, 'cr10_noop_done_ip')
        noop = debug.retrace_observe()
        assert_legacy_model(noop, raw_timing(debug, symbols))
        assert noop['timing_generation'] == aba['timing_generation']


def test_native_vbe_and_invalid_timing_have_no_phase_until_legacy_reentry(retrace_witness):
    with retrace_witness() as (_, debug, symbols):
        initial = debug.retrace_observe()
        assert_legacy_model(initial, raw_timing(debug, symbols))
        command(debug, symbols, 6, 'vbe_enabled_ip')
        vbe = debug.retrace_observe()
        assert_observation(vbe)
        assert vbe['raw']['vbe-enable'] & 1
        assert vbe['phase_supported'] is False and vbe['phase'] is None
        assert vbe['unsupported_reason'] == 'vbe-enabled'
        assert vbe['timing_generation'] > initial['timing_generation']
        command(debug, symbols, 7, 'vbe_disabled_ip')
        disabled = debug.retrace_observe()
        assert_legacy_model(disabled, raw_timing(debug, symbols))
        assert disabled['timing_generation'] > vbe['timing_generation']
        command(debug, symbols, 8, 'mode13_reentered_ip')
        reentered = debug.retrace_observe()
        assert_legacy_model(reentered, raw_timing(debug, symbols))
        assert reentered['raw'] == initial['raw'] and reentered['timing'] == initial['timing']
        assert reentered['timing_generation'] > disabled['timing_generation']
        command(debug, symbols, 10, 'cr10_invalid_done_ip')
        invalid = debug.retrace_observe()
        assert_observation(invalid)
        assert invalid['raw'] == raw_timing(debug, symbols)
        assert invalid['timing'] == precise_timing(invalid['raw'])
        assert invalid['timing']['vstart'] >= invalid['timing']['total-chars'] // invalid['timing']['htotal']
        assert invalid['phase_supported'] is False and invalid['phase'] is None
        assert invalid['unsupported_reason'] == 'invalid-timing'
        assert invalid['timing_generation'] > reentered['timing_generation']
        command(debug, symbols, 8, 'mode13_reentered_ip')
        recovered = debug.retrace_observe()
        assert_legacy_model(recovered, raw_timing(debug, symbols))
        assert recovered['timing'] == initial['timing']
        assert recovered['timing_generation'] > invalid['timing_generation']


def test_native_retrace_clock_source_and_renderer_provenance_survive_script_reopen(retrace_witness):
    with retrace_witness() as (project, debug, symbols):
        anchor = debug.clock_observe()
        debug.display_start(period_ns=1_000_000)
        budget_receipt(debug.clock_advance(3_000_000, timeout_ms=3000), 3_000_000)
        trace = debug.trace('retrace-source-clock.json', count=2, timeout_ms=3000)
        document = artifact_document(project, trace['artifact'])
        endpoint = document['collector']['current_stop']['clock']
        workspace = DebugWorkspace()
        workspace.sessions[debug.run_id] = debug
        try:
            reply = respond(dict(id='retrace', method='debug-retrace-observe',
                params=dict(project=str(project.path), run=debug.run_id, timeout_ms=1000)),
                debugger=workspace)
            assert reply['ok'], reply
            observed = reply['result']
            assert_legacy_model(observed, raw_timing(debug, symbols))
            script = dict(format='fdisbull-script-1', backend='qemu-dos',
                          steps=[dict(op='retrace-observe', timeout_ms=1000)])
            report = debug.script(script, timeout_ms=3000)
            assert report['ok'] and report['completed_steps'] == 1, report
            scripted = report['steps'][0]['result']
            assert_legacy_model(scripted, raw_timing(debug, symbols))
            assert scripted['native'] == observed['native']
        finally:
            workspace.sessions.clear()
        published = debug.capture_display('same-clock-renderer.png')['metadata']
        assert published['completed_renderer_update'] is True
        assert published['completed_guest_frame'] is None
        assert observed['completed_renderer_update'] is observed['completed_guest_frame'] is None
        assert observed['run'] == endpoint['run'] == anchor['run'] == published['run'] == debug.run_id
        assert observed['epoch'] == endpoint['epoch'] == anchor['epoch'] == published['epoch']
        assert observed['native_epoch'] == endpoint['native_epoch'] == published['native']['epoch']
        assert observed['observed_ns'] == endpoint['virtual_ns']
        assert observed['clocks']['before']['counter']['value'] == endpoint['icount']
        assert published['published_ns'] <= observed['observed_ns']
        predicate = dict(kind='virtual-time-range', run=debug.run_id, epoch=observed['epoch'],
            native_epoch=observed['native_epoch'], start_ns=document['events'][0]['clock']['virtual_ns'],
            end_ns=observed['observed_ns'] + 1)
        query = project.event_trace_query(trace['artifact'], predicate=predicate)
        assert query['matched_count'] == 2 and query['endpoint_clock'] == endpoint
        path = project.path
    with Project(path) as reopened:
        assert artifact_document(reopened, report['script_artifact']) == script
        assert artifact_document(reopened, report['artifact'])['steps'][0]['result'] == scripted
        assert reopened.event_trace_query(trace['artifact'], predicate=predicate) == query
        evidence = [json.loads(row[0]) for row in reopened.db.execute(
            "SELECT evidence FROM debug_events WHERE run=? AND operation='machine-retrace-observe' ORDER BY sequence",
            (observed['run'],))]
        assert observed in evidence and scripted in evidence
        assert reopened.debug_runs()['live_state_verified'] is False


def test_native_default_profile_refuses_retrace_without_changing_stopped_guest(retrace_witness, monkeypatch):
    with retrace_witness(profile=None) as (_, debug, symbols):
        assert debug.capabilities['retrace_observation'] is False
        assert 'std,retrace=precise' not in debug.vm.command
        assert 'VGA.x-fdisbull-retrace=on' not in debug.vm.command
        registers = debug.registers()
        before = debug.clock_observe()
        qmp_call = debug.vm.qmp.call
        calls = []

        def observed_call(command, *args, **kwargs):
            calls.append(command)
            return qmp_call(command, *args, **kwargs)

        monkeypatch.setattr(debug.vm.qmp, 'call', observed_call)
        with pytest.raises(ValueError, match='precise|retrace'):
            debug.retrace_observe()
        assert 'x-fdisbull-query-retrace' not in calls
        assert debug.registers() == registers
        after = debug.clock_observe()
        assert after['virtual_ns'] == before['virtual_ns']
        assert after['counter']['value'] == before['counter']['value']
        # The opt-in guard does not remove ordinary surface observation or
        # native source/clock functionality from the default profile.
        assert debug.capture_surface('standard-vga-surface.png')['artifact']
        assert debug.trace('standard-profile-source.json', count=1, timeout_ms=3000)['metadata']['complete']
        assert debug.status()['state'] == 'stopped'
        assert raw_timing(debug, symbols)['vbe-enable'] & 1 == 0


def test_native_standard_profile_keeps_ordinary_dos_runtime_usable(
        tmp_path, process_runtime, process_disk):
    code = com_exit(37)
    binary, project = create_project(tmp_path, code)
    with project, project.debugger(process_runtime['executable'], tmp_path,
            **launch_options(process_runtime, process_disk)) as debug:
        process_record(debug)
        assert debug.capabilities['retrace_observation'] is False
        before = debug.registers()
        with pytest.raises(ValueError, match='precise|retrace'):
            debug.retrace_observe()
        assert debug.registers() == before
        assert_completion(debug, debug.run(timeout_ms=3000), exit_code=37)
    assert debug.vm.process.poll() is not None
    assert binary.read_bytes() == code
    assert digest(process_disk['image']) == process_disk['prepared_sha256']


def test_native_retrace_refuses_armed_budget_and_invalidated_epoch(retrace_witness):
    with retrace_witness() as (_, debug, _):
        before = debug.retrace_observe()
        token = uuid.uuid4().hex
        armed = debug.vm.qmp.call('x-fdisbull-arm-clock-budget',
                                  {'delta-ns': 1_000_000, 'token': token})
        with pytest.raises(DebuggerError):
            debug.vm.qmp.call('x-fdisbull-query-retrace')
        retained = debug.vm.qmp.call('x-fdisbull-query-clock')
        assert retained['budget-token'] == armed['budget-token'] == token
        assert retained['budget-state'] == 'armed'
        assert retained['virtual-ns'] == armed['virtual-ns'] == before['observed_ns']
        debug.vm.qmp.call('x-fdisbull-cancel-clock-budget', {'token': token})
        cancelled = debug.retrace_observe()
        assert cancelled['timing_generation'] == before['timing_generation']
        assert cancelled['observed_ns'] == before['observed_ns']
        # Reset is explicitly enabled only to witness native invalidation in
        # an otherwise surviving emulator; the production profile is no-reboot.
        debug.vm.qmp.call('set-action', {'reboot': 'reset'})
        debug.vm.qmp.call('system_reset')
        deadline = time.monotonic() + 2
        while debug.vm.qmp.call('x-fdisbull-query-clock')['epoch'] == before['native_epoch']:
            assert time.monotonic() < deadline
        with pytest.raises(DebuggerError):
            debug.vm.qmp.call('x-fdisbull-query-retrace')
        with pytest.raises(DebuggerError):
            debug.retrace_observe()
        assert debug.vm.process.poll() is not None
        assert debug.dos_process_info()['machine_closed'] is True
