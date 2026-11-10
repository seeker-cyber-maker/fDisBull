"""Native VGA register identity and publication-stamp witnesses.

Guest port/MMIO reads supply the raw-register oracle. Renderer pixels and guest
configuration are deliberately checked separately, including an invalid text
configuration that leaves an older raster in QEMU's display surface. Overflow
and migration/post-load are not exercised by this suite.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import struct
import time
import uuid

import pytest

from fdisbull.cli import respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project
from support.dos_process_fixture import digest
from support.qemu_vga_configuration_fixture import COMMANDS, configuration_ports
from test_qemu_clock_budget_native import budget_receipt, clock_disk, clock_runtime, park
from test_qemu_dos_process_native import (
    com_address, create_project, launch_options, process_record, read_bytes,
)


COMMAND = 'x-fdisbull-query-vga-configuration'
PERIOD_NS = 10_000_000


@pytest.fixture
def configuration_witness(tmp_path, clock_runtime, clock_disk):
    serial = 0

    @contextmanager
    def launch(*, executable=None, profile='precise'):
        nonlocal serial
        serial += 1
        directory = tmp_path / f'vga-configuration-{serial}'
        directory.mkdir()
        code, offsets = configuration_ports(directory, clock_runtime['nasm'])
        binary, project = create_project(directory, code)
        debug = None
        try:
            with project:
                try:
                    with project.debugger(executable or clock_runtime['executable'], directory,
                            **launch_options(clock_runtime, clock_disk,
                                             qemu_clock='virtual', qemu_retrace=profile)) as debug:
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


def guest_value(debug, symbols, name, size=1):
    return int.from_bytes(read_bytes(debug, symbols[name + '_ip'], size), 'little')


def guest_configuration(debug, symbols):
    """Only values actually read by the guest; derived native fields stay separate."""
    return {
        'sequencer': list(read_bytes(debug, symbols['sequencer_ip'], 8)),
        'graphics': list(read_bytes(debug, symbols['graphics_ip'], 16)),
        'crtc': list(read_bytes(debug, symbols['crtc_ip'], 256)),
        'attribute-controls': list(read_bytes(debug, symbols['attribute_controls_ip'], 5)),
        'vbe': list(struct.unpack('<10H', read_bytes(debug, symbols['vbe_ip'], 20))),
        'misc-output': guest_value(debug, symbols, 'misc_output'),
        'feature-control': guest_value(debug, symbols, 'feature_control'),
        'display-enabled': bool(guest_value(debug, symbols, 'display_enabled') & 0x20),
    }


def command(debug, symbols, name):
    value, fence = COMMANDS[name]
    old = read_bytes(debug, symbols['command_ip'], 1)
    debug.write_memory(symbols['command_ip'], bytes([value]).hex(), expected_hex=old.hex())
    return park(debug, symbols[fence])


def assert_clock_equal(first, second):
    for key in ('run', 'epoch', 'virtual_ns', 'counter'):
        assert first[key] == second[key], key


def observe(debug, *, guest=None):
    value = debug.vga_configuration_observe()
    assert value['format'] == 'fdisbull-vga-configuration-1'
    assert value['context'] == 'machine'
    assert value['clock_domain'] == 'QEMU_CLOCK_VIRTUAL'
    assert value['publication_configuration_semantics'] == 'configuration_observed_at_publication'
    for key in ('raster_coherence', 'completed_guest_frame', 'guest_frame_id', 'cursor_mapping'):
        assert value[key] is None, key
    assert not {'mode_id', 'frame_id', 'state_revision'} & value.keys()
    current = value['current']
    assert current['model'] == 'qemu-vga-configuration-fdisbull-v1'
    assert current['device_type'] == 'VGA'
    assert current['console'] == current['head'] == 0
    assert current['configuration_generation'] > 0
    assert current['raw'] == value['native']['current']['raw']
    assert current['configuration_generation'] == value['native']['current']['configuration-generation']
    assert current['native_epoch'] == value['native_epoch']
    before, after = value['clocks']['before'], value['clocks']['after']
    assert_clock_equal(before, after)
    assert before['sequence'] < after['sequence']
    assert current['observed_ns'] == before['virtual_ns']
    if guest is not None:
        for key, expected in guest.items():
            assert current['raw'][key] == expected, key
    return value


def observe_guest(debug, symbols):
    return observe(debug, guest=guest_configuration(debug, symbols))


def publish(debug, delta_ns=25_000_000):
    budget_receipt(debug.clock_advance(delta_ns, timeout_ms=5000), delta_ns)
    return debug.display_observe()


def extent(value):
    return value['width'], value['height']


def marker_points(display):
    assert display['width'] % 320 == display['height'] % 200 == 0
    sx, sy = display['width'] // 320, display['height'] // 200
    return [[10 * sx, 10 * sy], [20 * sx, 10 * sy]]


def assert_guest_mmio_ready(debug, symbols):
    assert guest_value(debug, symbols, 'pci_status') == 1
    assert guest_value(debug, symbols, 'pci_identity', 4) == 0x11111234
    assert guest_value(debug, symbols, 'pci_command', 2) & 2
    assert guest_value(debug, symbols, 'mmio_bar', 4) > 0
    assert guest_value(debug, symbols, 'qext_size', 4) == 8


def test_native_configuration_is_passive_and_preserves_attribute_data_phase(configuration_witness):
    with configuration_witness() as (project, debug, symbols):
        assert debug.capabilities['vga_configuration'] is True
        registers = debug.registers()
        before = debug.clock_observe()
        files = {str(p) for p in Path(debug.vm.temporary.name).rglob('*') if p.is_file()}
        artifacts = project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]
        first = observe_guest(debug, symbols)
        second = observe_guest(debug, symbols)
        assert first['native'] == second['native']
        assert first['published'] is first['configuration_matches'] is None
        assert debug.registers() == registers
        assert_clock_equal(before, debug.clock_observe())
        assert project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == artifacts
        assert {str(p) for p in Path(debug.vm.temporary.name).rglob('*') if p.is_file()} == files

        command(debug, symbols, 'attribute_pending')
        pending = observe(debug)
        assert pending['current']['raw']['attribute-controls'][2] == 0
        park(debug, symbols['attribute_done_ip'])
        # Reading VGA status to manufacture the query would reset this pending
        # data phase, leaving the plane-enable register at zero instead of 15.
        completed = observe_guest(debug, symbols)
        assert completed['current']['raw']['attribute-controls'][2] == 15
        assert completed['current']['configuration_generation'] > pending['current']['configuration_generation']


def test_native_same_extent_page_pitch_panning_and_line_compare_change_identity(configuration_witness):
    with configuration_witness() as (_, debug, symbols):
        debug.display_start(period_ns=PERIOD_NS)
        initial_display = publish(debug)
        previous = observe_guest(debug, symbols)
        initial_raw = previous['current']['raw']
        cases = (
            ('page', 'crtc', 0x0d, 0x20),
            ('pitch', 'crtc', 0x13, 1),
            ('panning', 'attribute-controls', 3, 1),
            ('line_compare', 'crtc', 0x18, 1),
        )
        for name, field, index, bit in cases:
            command(debug, symbols, name)
            current = observe_guest(debug, symbols)
            assert current['current']['raw'][field][index] == initial_raw[field][index] ^ bit
            assert current['current']['configuration_generation'] > previous['current']['configuration_generation']
            assert current['current']['configuration_sha256'] != previous['current']['configuration_sha256']
            published = publish(debug)
            assert extent(published) == extent(initial_display)
            bound = observe_guest(debug, symbols)
            assert bound['configuration_matches'] is True
            assert bound['published']['raw'] == bound['current']['raw']
            previous = bound


def test_native_unobserved_aba_keeps_raw_equivalence_but_invalidates_publication_identity(configuration_witness):
    with configuration_witness() as (_, debug, symbols):
        debug.display_start(period_ns=PERIOD_NS)
        publish(debug)
        original = observe_guest(debug, symbols)
        debug.display_stop()
        command(debug, symbols, 'page_aba')  # both writes precede the next query
        after = observe_guest(debug, symbols)
        assert after['current']['raw'] == original['current']['raw']
        assert after['current']['configuration_sha256'] == original['current']['configuration_sha256']
        assert after['current']['configuration_generation'] == original['current']['configuration_generation'] + 2
        assert after['published'] == original['published']
        assert after['published']['configuration_sha256'] == after['current']['configuration_sha256']
        assert after['configuration_matches'] is False


def test_native_noop_and_protected_cr0_differ_from_writable_cr7_bit4(configuration_witness):
    with configuration_witness() as (_, debug, symbols):
        first = observe_guest(debug, symbols)
        assert first['current']['raw']['crtc'][0x11] & 0x80
        for name in ('noop', 'protected_cr0'):
            command(debug, symbols, name)
            unchanged = observe_guest(debug, symbols)
            assert unchanged['current']['raw'] == first['current']['raw']
            assert unchanged['current']['configuration_generation'] == first['current']['configuration_generation']
        command(debug, symbols, 'protected_cr7')
        changed = observe_guest(debug, symbols)
        assert changed['current']['raw']['crtc'][7] == first['current']['raw']['crtc'][7] ^ 0x10
        assert changed['current']['configuration_generation'] == first['current']['configuration_generation'] + 1


def test_native_selectors_are_excluded_but_display_enable_is_tracked(configuration_witness):
    with configuration_witness() as (_, debug, symbols):
        first = observe_guest(debug, symbols)
        command(debug, symbols, 'selectors')
        selected = observe_guest(debug, symbols)
        assert selected['current']['raw'] == first['current']['raw']
        assert selected['current']['configuration_generation'] == first['current']['configuration_generation']
        command(debug, symbols, 'disable_display')
        blanked = observe_guest(debug, symbols)
        assert blanked['current']['raw']['display-enabled'] is False
        assert blanked['current']['configuration_generation'] == first['current']['configuration_generation'] + 1
        command(debug, symbols, 'enable_display')
        enabled = observe_guest(debug, symbols)
        assert enabled['current']['raw'] == first['current']['raw']
        assert enabled['current']['configuration_generation'] == blanked['current']['configuration_generation'] + 1


def test_native_palette_and_vram_change_rgb_without_changing_configuration(configuration_witness):
    with configuration_witness() as (_, debug, symbols):
        debug.display_start(period_ns=PERIOD_NS)
        initial_display = publish(debug)
        points = marker_points(initial_display)
        first = observe_guest(debug, symbols)
        initial_pixels = debug.display_probe(points)['pixels']
        assert [p['rgb'] for p in initial_pixels] == [[255, 0, 0], [0, 0, 0]]
        command(debug, symbols, 'palette_vram')
        changed = observe_guest(debug, symbols)
        assert changed['current']['raw'] == first['current']['raw']
        assert changed['current']['configuration_generation'] == first['current']['configuration_generation']
        publish(debug)
        assert [p['rgb'] for p in debug.display_probe(points)['pixels']] == [[0, 0, 255], [0, 255, 0]]
        observed = observe_guest(debug, symbols)
        assert observed['configuration_matches'] is True
        assert observed['current']['configuration_generation'] == first['current']['configuration_generation']


def test_native_vbe_same_dimensions_different_format_and_derived_pitch(configuration_witness):
    with configuration_witness() as (_, debug, symbols):
        command(debug, symbols, 'vbe8')
        first = observe_guest(debug, symbols)
        raw = first['current']['raw']
        assert raw['vbe'][1:4] == [320, 200, 8]
        assert raw['vbe-line-offset'] == 320 and raw['vbe-start-address'] == 0
        assert raw['vbe'][6] == 320
        assert raw['sequencer-vbe'][4] & 8
        debug.display_start(period_ns=PERIOD_NS)
        old_display = publish(debug)
        assert extent(old_display) == (320, 200)
        command(debug, symbols, 'vbe32')
        second = observe_guest(debug, symbols)
        raw32 = second['current']['raw']
        assert raw32['vbe'][1:4] == [320, 200, 32]
        assert raw32['vbe-line-offset'] == 1280 and raw32['vbe-start-address'] == 0
        assert raw32['crtc'][0x13] == 160
        assert second['current']['configuration_generation'] > first['current']['configuration_generation']
        assert extent(publish(debug)) == extent(old_display)
        assert observe_guest(debug, symbols)['configuration_matches'] is True


def test_native_vbe_offsets_bank_and_dac_report_complete_postfix_state(configuration_witness):
    with configuration_witness() as (_, debug, symbols):
        command(debug, symbols, 'vbe8')
        command(debug, symbols, 'vbe32')
        command(debug, symbols, 'vbe_offsets')
        offsets = observe_guest(debug, symbols)
        raw = offsets['current']['raw']
        assert raw['vbe'][6] == 328 and raw['vbe'][8:10] == [4, 2]
        assert raw['vbe-line-offset'] == 1312
        assert raw['vbe-start-address'] == 660  # (2*1312 + 4*4) / four bytes
        assert raw['crtc'][0x13] == 164
        command(debug, symbols, 'vbe_bank')
        banked = observe_guest(debug, symbols)
        assert banked['current']['raw']['vbe'][5] == 3
        assert banked['current']['raw']['bank-offset'] == 3 * 65536
        assert banked['current']['configuration_generation'] > offsets['current']['configuration_generation']
        command(debug, symbols, 'vbe_dac')
        dac = observe_guest(debug, symbols)
        assert dac['current']['raw']['vbe'][4] == 0xa1
        assert dac['current']['raw']['dac-8bit'] is True
        # The enable-register mutator resets the derived bank offset even
        # though the retained BANK register still contains three.
        assert dac['current']['raw']['vbe'][5] == 3
        assert dac['current']['raw']['bank-offset'] == 0
        assert dac['current']['configuration_generation'] > banked['current']['configuration_generation']


def test_native_qom_and_guest_pci_qext_endian_writes_share_configuration_identity(configuration_witness):
    with configuration_witness() as (_, debug, symbols):
        assert_guest_mmio_ready(debug, symbols)
        first = observe_guest(debug, symbols)
        device = first['current']['device']
        assert first['current']['raw']['big-endian-framebuffer'] is False
        before = debug.clock_observe()
        args = dict(path=device, property='big-endian-framebuffer', value=True)
        debug.vm.qmp.call('qom-set', args)
        qom = observe_guest(debug, symbols)
        assert qom['current']['raw']['big-endian-framebuffer'] is True
        assert qom['current']['configuration_generation'] == first['current']['configuration_generation'] + 1
        assert_clock_equal(before, debug.clock_observe())
        debug.vm.qmp.call('qom-set', args)
        assert observe_guest(debug, symbols)['current']['configuration_generation'] == qom['current']['configuration_generation']
        debug.vm.qmp.call('qom-set', dict(args, value=False))
        little = observe_guest(debug, symbols)
        assert little['current']['raw']['big-endian-framebuffer'] is False
        command(debug, symbols, 'qext_big')
        big = observe_guest(debug, symbols)
        assert guest_value(debug, symbols, 'qext_readback', 4) == 0xbebebebe
        assert big['current']['raw']['big-endian-framebuffer'] is True
        assert big['current']['configuration_generation'] == little['current']['configuration_generation'] + 1
        for name in ('qext_noop', 'qext_invalid'):
            command(debug, symbols, name)
            same = observe_guest(debug, symbols)
            assert guest_value(debug, symbols, 'qext_readback', 4) == 0xbebebebe
            assert same['current']['configuration_generation'] == big['current']['configuration_generation']
        command(debug, symbols, 'qext_little')
        final = observe_guest(debug, symbols)
        assert guest_value(debug, symbols, 'qext_readback', 4) == 0x1e1e1e1e
        assert final['current']['raw']['big-endian-framebuffer'] is False
        assert final['current']['configuration_generation'] == big['current']['configuration_generation'] + 1


def test_native_mmio_vga_vbe_and_mono_port_aliases_reach_tracked_mutators(configuration_witness):
    with configuration_witness() as (_, debug, symbols):
        assert_guest_mmio_ready(debug, symbols)
        first = observe_guest(debug, symbols)
        command(debug, symbols, 'mmio_aliases')
        mmio = observe_guest(debug, symbols)
        assert mmio['current']['raw']['crtc'][0x13] == first['current']['raw']['crtc'][0x13] ^ 1
        assert mmio['current']['raw']['vbe'][5] == 2
        assert mmio['current']['raw']['bank-offset'] == 2 * 65536
        assert mmio['current']['configuration_generation'] == first['current']['configuration_generation'] + 2
        command(debug, symbols, 'mono_alias')
        mono = observe_guest(debug, symbols)
        assert mono['current']['raw']['misc-output'] == first['current']['raw']['misc-output'] & ~1
        assert mono['current']['raw']['crtc'][0x0d] == first['current']['raw']['crtc'][0x0d] ^ 0x20
        assert mono['current']['configuration_generation'] == mmio['current']['configuration_generation'] + 2


def test_native_publication_is_stamped_before_first_query_and_survives_stopped_window(configuration_witness, monkeypatch):
    with configuration_witness() as (_, debug, symbols):
        initial_guest = guest_configuration(debug, symbols)
        calls = []
        original_call = debug.vm.qmp.call

        def watched(name, *args, **kwargs):
            calls.append(name)
            return original_call(name, *args, **kwargs)

        monkeypatch.setattr(debug.vm.qmp, 'call', watched)
        debug.display_start(period_ns=PERIOD_NS)
        old_display = publish(debug)
        debug.display_stop()
        command(debug, symbols, 'page')
        assert COMMAND not in calls
        first = observe_guest(debug, symbols)
        assert first['published']['raw']['crtc'] == initial_guest['crtc']
        assert first['published']['observed_ns'] == old_display['published_ns']
        assert first['published']['configuration_generation'] < first['current']['configuration_generation']
        assert first['configuration_matches'] is False
        command(debug, symbols, 'pitch')
        publish(debug)
        later = observe_guest(debug, symbols)
        assert later['published'] == first['published']
        assert later['display']['state'] == 'stopped'
        assert later['display']['window'] == old_display['window']
        assert later['display']['update_id'] == old_display['update_id']
        new_window = debug.display_start(period_ns=PERIOD_NS)
        empty = observe_guest(debug, symbols)
        assert empty['published'] is empty['configuration_matches'] is None
        assert empty['current']['configuration_generation'] == later['current']['configuration_generation']
        assert new_window['window'] != old_display['window']
        publish(debug)
        fresh = observe_guest(debug, symbols)
        assert fresh['configuration_matches'] is True
        assert fresh['published']['raw'] == fresh['current']['raw']
        assert fresh['published']['observed_ns'] > first['published']['observed_ns']


def test_native_invalid_text_reuses_old_raster_without_claiming_coherence(configuration_witness):
    with configuration_witness() as (_, debug, symbols):
        debug.display_start(period_ns=PERIOD_NS)
        old_display = publish(debug)
        points = marker_points(old_display)
        old_pixels = debug.display_probe(points)['pixels']
        assert [p['rgb'] for p in old_pixels] == [[255, 0, 0], [0, 0, 0]]
        first = observe_guest(debug, symbols)
        command(debug, symbols, 'invalid_text')
        invalid = observe_guest(debug, symbols)
        raw = invalid['current']['raw']
        assert raw['graphics'][6] & 1 == 0
        assert raw['crtc'][1] == raw['crtc'][0x12] == 0
        assert raw['crtc'][7] & 0x42 == 0 and raw['crtc'][9] & 0x1f == 0
        assert invalid['current']['configuration_generation'] > first['current']['configuration_generation']
        new_display = publish(debug)
        assert new_display['update_id'] > old_display['update_id']
        assert extent(new_display) == extent(old_display)
        assert debug.display_probe(points)['pixels'] == old_pixels
        final = observe_guest(debug, symbols)
        assert final['configuration_matches'] is True
        assert final['published']['raw'] == final['current']['raw']
        assert final['raster_coherence'] is None


def test_native_configuration_refuses_budget_and_reset_invalidates_owner(configuration_witness):
    with configuration_witness() as (_, debug, _):
        first = observe(debug)
        token = uuid.uuid4().hex
        armed = debug.vm.qmp.call('x-fdisbull-arm-clock-budget',
                                 {'delta-ns': 1_000_000, 'token': token})
        with pytest.raises(DebuggerError):
            debug.vm.qmp.call(COMMAND)
        retained = debug.vm.qmp.call('x-fdisbull-query-clock')
        assert retained['budget-state'] == 'armed'
        assert retained['budget-token'] == armed['budget-token'] == token
        assert retained['virtual-ns'] == first['current']['observed_ns']
        debug.vm.qmp.call('x-fdisbull-cancel-clock-budget', {'token': token})
        cancelled = observe(debug)
        assert cancelled['current'] == first['current']
        debug.vm.qmp.call('set-action', {'reboot': 'reset'})
        debug.vm.qmp.call('system_reset')
        deadline = time.monotonic() + 2
        while debug.vm.qmp.call('x-fdisbull-query-clock')['epoch'] == first['native_epoch']:
            assert time.monotonic() < deadline
        with pytest.raises(DebuggerError):
            debug.vm.qmp.call(COMMAND)
        with pytest.raises(DebuggerError):
            debug.vga_configuration_observe()
        assert debug.vm.process.poll() is not None
        assert debug.dos_process_info()['machine_closed'] is True


def test_native_old_nine_and_default_profile_refuse_only_configuration(configuration_witness, monkeypatch):
    legacy = os.environ.get('FDISBULL_QEMU_VGA_CONFIGURATION_LEGACY')
    if not legacy:
        message = 'Supply FDISBULL_QEMU_VGA_CONFIGURATION_LEGACY for the nine-layer witness'
        if os.environ.get('FDISBULL_REQUIRE_QEMU_CLOCK') == '1':
            pytest.fail(message)
        pytest.skip(message)
    for executable, profile in ((legacy, 'precise'), (None, 'standard')):
        with configuration_witness(executable=executable, profile=profile) as (_, debug, _):
            assert debug.capabilities['vga_configuration'] is False
            assert debug.capabilities['renderer_probe'] is True
            before = debug.clock_observe()
            registers = debug.registers()
            calls = []
            original_call = debug.vm.qmp.call

            def watched(name, *args, **kwargs):
                calls.append(name)
                return original_call(name, *args, **kwargs)

            with monkeypatch.context() as patch:
                patch.setattr(debug.vm.qmp, 'call', watched)
                with pytest.raises(ValueError, match='precise|retrace|extension|configuration'):
                    debug.vga_configuration_observe()
                assert COMMAND not in calls
            assert debug.registers() == registers
            assert_clock_equal(before, debug.clock_observe())
            debug.display_start(period_ns=PERIOD_NS)
            publish(debug)
            assert debug.display_probe([])['completed_renderer_update'] is True
            assert debug.status()['state'] == 'stopped'


def test_native_configuration_json_script_and_journal_survive_reopen(configuration_witness):
    with configuration_witness() as (project, debug, symbols):
        workspace = DebugWorkspace()
        workspace.sessions[debug.run_id] = debug
        try:
            script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
                dict(op='display-start', period_ns=PERIOD_NS),
                dict(op='clock-advance', delta_ns=25_000_000, timeout_ms=5000),
                dict(op='vga-configuration', **{'as': 'configuration'}),
                dict(op='vga-configuration', timeout_ms=1000),
            ])
            report = debug.script(script, timeout_ms=6000)
            assert report['ok'] and report['completed_steps'] == 4, report
            scripted = report['steps'][3]['result']
            reply = respond(dict(id='vga-config', method='debug-vga-configuration',
                params=dict(project=str(project.path), run=debug.run_id, timeout_ms=1000)),
                debugger=workspace)
            assert reply['ok'], reply
            observed = reply['result']
            assert observed['native'] == scripted['native']
            assert observed['current'] == scripted['current']
            assert observed['published'] == scripted['published']
            for key, expected in guest_configuration(debug, symbols).items():
                assert observed['current']['raw'][key] == expected
            assert project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='screenshot'").fetchone()[0] == 0
            path, run = project.path, debug.run_id
        finally:
            workspace.sessions.clear()
    with Project(path) as reopened:
        rows = reopened.db.execute(
            "SELECT evidence FROM debug_events WHERE run=? AND operation='machine-vga-configuration-observe' ORDER BY sequence",
            (run,)).fetchall()
        assert len(rows) == 3
        saved = [json.loads(row[0]) for row in rows]
        assert saved[-1] == observed and saved[1] == scripted
        assert not reopened._live_debuggers
        assert reopened.debug_runs()['live_state_verified'] is False
