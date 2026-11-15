"""Real retained RGB reads, independently compared with authored VGA and exports."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import time
import uuid

import pytest

from fdisbull.cli import respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project
from support.dos_process_fixture import digest
from support.qemu_display_fixture import partial_display
from support.qemu_display_probe_fixture import palette_display
from test_qemu_clock_budget_native import clock_runtime, clock_disk, park, budget_receipt
from test_qemu_display_native import pixels, markers
from test_qemu_dos_process_native import create_project, launch_options, process_record, com_address


@pytest.fixture
def probe_witness(tmp_path, clock_runtime, clock_disk):
    @contextmanager
    def launch(builder=partial_display, *, executable=None):
        code, offsets = builder(tmp_path, clock_runtime['nasm'])
        binary, project = create_project(tmp_path, code)
        debug = None
        try:
            with project:
                try:
                    with project.debugger(executable or clock_runtime['executable'], tmp_path,
                            **launch_options(clock_runtime, clock_disk, qemu_clock='virtual')) as debug:
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


def assert_same_clock(first, second):
    for key in ('run', 'epoch', 'virtual_ns', 'counter'):
        assert first[key] == second[key], key


def marker_points(publication):
    assert publication['width'] % 320 == publication['height'] % 200 == 0
    sx, sy = publication['width'] // 320, publication['height'] // 200
    return [[10 * sx, 10 * sy], [20 * sx, 10 * sy]]


def sample_and_compare(project, debug, points, *, expected=None):
    before = debug.clock_observe()
    registers = debug.registers()
    files = {str(path) for path in Path(debug.vm.temporary.name).rglob('*') if path.is_file()}
    artifacts = project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]
    options = {} if expected is None else dict(window=expected['window'], update_id=expected['update_id'])
    sampled = debug.display_probe(points, **options)
    assert sampled['points'] == points
    assert sampled['completed_renderer_update'] is True
    assert sampled['completed_guest_frame'] is sampled['guest_frame_id'] is None
    assert not {'mode_id', 'frame_id', 'state_revision', 'pixel_sha256'} & sampled.keys()
    assert project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == artifacts
    assert {str(path) for path in Path(debug.vm.temporary.name).rglob('*') if path.is_file()} == files
    assert debug.registers() == registers
    assert_same_clock(before, debug.clock_observe())
    assert_same_clock(sampled['clocks']['before'], sampled['clocks']['after'])
    captured = debug.capture_display()
    metadata = captured['metadata']
    for key in ('window', 'update_id', 'width', 'height', 'published_ns'):
        assert sampled[key] == metadata[key]
    assert sampled['native']['display'] == metadata['native']
    with pixels(project, captured) as image:
        assert sampled['pixels'] == [dict(x=x, y=y, rgb=list(image.getpixel((x, y)))) for x, y in points]
    return sampled


def test_native_probe_distinguishes_retained_partial_and_completed_drawing(probe_witness):
    with probe_witness() as (project, debug, symbols):
        debug.display_start(period_ns=20_000_000)
        with pytest.raises(ValueError, match='No completed renderer'):
            debug.display_probe([])
        budget_receipt(debug.clock_advance(55_000_000, timeout_ms=5000), 55_000_000)
        first = debug.display_observe()
        points = marker_points(first)
        ordered = [points[1], points[0], points[1], [0, 0], [first['width'] - 1, first['height'] - 1]]
        sampled = sample_and_compare(project, debug, ordered, expected=first)
        assert all(pixel['rgb'] == [0, 0, 0] for pixel in sampled['pixels'])
        assert sample_and_compare(project, debug, [], expected=first)['pixels'] == []
        assert len(sample_and_compare(project, debug, [points[0]] * 256, expected=first)['pixels']) == 256

        debug.write_memory(symbols['phase_ip'], '01', expected_hex='00')
        park(debug, symbols['partial_ready_ip'])
        retained = sample_and_compare(project, debug, points, expected=first)
        assert [pixel['rgb'] for pixel in retained['pixels']] == [[0, 0, 0], [0, 0, 0]]
        with pixels(project, debug.capture_surface('current-partial.png')) as image:
            assert markers(image) == ((255, 0, 0), (0, 0, 0))
        assert debug.display_probe(points)['pixels'] == retained['pixels']
        budget_receipt(debug.clock_advance(25_000_000, timeout_ms=5000), 25_000_000)
        partial = sample_and_compare(project, debug, points)
        assert [pixel['rgb'] for pixel in partial['pixels']] == [[255, 0, 0], [0, 0, 0]]
        assert partial['update_id'] > first['update_id']
        with pytest.raises(ValueError, match='different retained'):
            debug.display_probe(points, window=first['window'], update_id=first['update_id'])

        debug.write_memory(symbols['phase_ip'], '02', expected_hex='01')
        park(debug, symbols['complete_ready_ip'])
        budget_receipt(debug.clock_advance(25_000_000, timeout_ms=5000), 25_000_000)
        complete = sample_and_compare(project, debug, points)
        assert [pixel['rgb'] for pixel in complete['pixels']] == [[255, 0, 0], [0, 255, 0]]
        # This authored program's fence is separate from a generic guest frame.
        assert complete['completed_guest_frame'] is None


def test_native_palette_change_does_not_relabel_retained_rgb(probe_witness):
    with probe_witness(palette_display) as (project, debug, symbols):
        debug.display_start(period_ns=20_000_000)
        budget_receipt(debug.clock_advance(55_000_000, timeout_ms=5000), 55_000_000)
        first = debug.display_observe()
        points = marker_points(first)[:1]
        assert sample_and_compare(project, debug, points)['pixels'][0]['rgb'] == [255, 0, 0]
        debug.write_memory(symbols['phase_ip'], '01', expected_hex='00')
        park(debug, symbols['palette_ready_ip'])
        with pixels(project, debug.capture_surface('palette-current.png')) as image:
            assert image.getpixel(tuple(points[0])) == (0, 0, 255)
        retained = sample_and_compare(project, debug, points, expected=first)
        assert retained['pixels'][0]['rgb'] == [255, 0, 0]
        budget_receipt(debug.clock_advance(25_000_000, timeout_ms=5000), 25_000_000)
        changed = sample_and_compare(project, debug, points)
        assert changed['pixels'][0]['rgb'] == [0, 0, 255]
        assert changed['update_id'] > first['update_id']


def test_native_stopped_publication_survives_mode_change_and_new_window_is_distinct(probe_witness):
    with probe_witness() as (project, debug, symbols):
        debug.display_start(period_ns=10_000_000)
        budget_receipt(debug.clock_advance(25_000_000, timeout_ms=5000), 25_000_000)
        old = debug.display_probe([])
        debug.display_stop()
        debug.write_memory(symbols['phase_ip'], '03', expected_hex='00')
        park(debug, symbols['text_ready_ip'])
        budget_receipt(debug.clock_advance(25_000_000, timeout_ms=5000), 25_000_000)
        retained = sample_and_compare(project, debug, [[old['width'] - 1, old['height'] - 1]], expected=old)
        assert (retained['width'], retained['height']) == (old['width'], old['height'])
        assert retained['state'] == 'stopped' and retained['age_ns'] > old['age_ns']
        with pixels(project, debug.capture_surface('current-text.png')) as image:
            assert image.size != (old['width'], old['height'])
        new = debug.display_start(period_ns=10_000_000)
        assert new['window'] != old['window']
        with pytest.raises(ValueError, match='No completed renderer'):
            debug.display_probe([], window=old['window'], update_id=old['update_id'])
        budget_receipt(debug.clock_advance(15_000_000, timeout_ms=5000), 15_000_000)
        current = debug.display_probe([])
        assert current['update_id'] == 1 and current['window'] == new['window']
        assert (current['width'], current['height']) != (old['width'], old['height'])
        sample_and_compare(project, debug, [[0, 0], [current['width'] - 1, current['height'] - 1]], expected=current)
        with pytest.raises(ValueError, match='different retained'):
            debug.display_probe([], window=old['window'], update_id=1)
        for point in ([current['width'], 0], [0, current['height']]):
            with pytest.raises(ValueError, match='outside'):
                debug.display_probe([point])
        assert debug.status()['state'] == 'stopped'


def test_native_probe_json_script_and_journal_survive_reopen(probe_witness):
    with probe_witness() as (project, debug, _):
        workspace = DebugWorkspace()
        workspace.sessions[debug.run_id] = debug
        def invoke(method, **params):
            reply = respond(dict(id='sparse-renderer', method=method, params=dict(
                project=str(project.path), run=debug.run_id, **params)), debugger=workspace)
            assert reply['ok'], reply
            return reply['result']
        try:
            report = debug.script(dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
                dict(op='display-start', period_ns=10_000_000),
                dict(op='clock-advance', delta_ns=25_000_000, timeout_ms=5000),
                dict(op='display-probe', points=[], **{'as': 'publication'}),
                dict(op='display-probe', points=[[0, 0], [1, 1], [0, 0]],
                     window='$publication.window', update_id='$publication.update_id'),
            ]), timeout_ms=6000)
            assert report['ok'] and report['completed_steps'] == 4, report
            scripted = report['steps'][3]['result']
            observed = invoke('debug-display-probe', points=scripted['points'],
                              window=scripted['window'], update_id=scripted['update_id'])
            assert observed['pixels'] == scripted['pixels']
            assert observed['native'] == scripted['native']
            assert project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='screenshot'").fetchone()[0] == 0
            path, run = project.path, debug.run_id
        finally:
            workspace.sessions.clear()
    with Project(path) as reopened:
        rows = reopened.db.execute("SELECT evidence FROM debug_events WHERE run=? AND operation='machine-display-probe' ORDER BY sequence", (run,)).fetchall()
        assert len(rows) == 3
        saved = [json.loads(row[0]) for row in rows]
        assert saved[-1] == observed and saved[1] == scripted
        assert not reopened._live_debuggers


def test_native_invalid_probe_requests_preserve_publication_and_clock(probe_witness):
    with probe_witness() as (_, debug, _):
        debug.display_start(period_ns=10_000_000)
        budget_receipt(debug.clock_advance(25_000_000, timeout_ms=5000), 25_000_000)
        publication = debug.display_observe()
        clock = debug.clock_observe()
        base = dict(token=publication['window'], **{'update-id': publication['update_id']}, points=[])
        invalid = [
            dict(base, token='foreign'), dict(base, **{'update-id': 0}),
            dict(base, **{'update-id': publication['update_id'] - 1}),
            dict(base, **{'update-id': publication['update_id'] + 1}),
            dict(base, **{'update-id': True}), dict(base, **{'update-id': 1 << 64}),
            dict(base, points=[dict(x=-1, y=0)]), dict(base, points=[dict(x=0, y=-1)]),
            dict(base, points=[dict(x=publication['width'], y=0)]),
            dict(base, points=[dict(x=0, y=publication['height'])]),
            dict(base, points=[dict(x=0, y=0), dict(x=8192, y=0)]),
            dict(base, points=[dict(x=0, y=0)] * 257),
            dict(base, points=[dict(x=True, y=0)]), dict(base, points=[dict(x=0.5, y=0)]),
            dict(base, points=[dict(x=0, y=0, extra=1)]), dict(base, points=[dict(x=0)]),
            dict(base, points=[None]), dict(base, points=None), dict(base, extra=1),
            {key: value for key, value in base.items() if key != 'token'},
        ]
        for arguments in invalid:
            with pytest.raises(DebuggerError):
                debug.vm.qmp.call('x-fdisbull-probe-display', arguments)
            assert debug.vm.qmp.call('x-fdisbull-query-display') == publication['native']
            assert_same_clock(clock, debug.clock_observe())
        assert debug.display_probe([])['native']['display'] == publication['native']


def test_native_probe_refuses_armed_budget_and_reset_epoch(probe_witness):
    with probe_witness() as (_, debug, _):
        debug.display_start(period_ns=10_000_000)
        budget_receipt(debug.clock_advance(25_000_000, timeout_ms=5000), 25_000_000)
        publication = debug.display_probe([])
        args = dict(token=publication['window'], **{'update-id': publication['update_id']}, points=[])
        token = uuid.uuid4().hex
        armed = debug.vm.qmp.call('x-fdisbull-arm-clock-budget', dict(token=token, **{'delta-ns': 1_000_000}))
        with pytest.raises(DebuggerError):
            debug.vm.qmp.call('x-fdisbull-probe-display', args)
        assert debug.vm.qmp.call('x-fdisbull-query-clock') == armed
        debug.vm.qmp.call('x-fdisbull-cancel-clock-budget', dict(token=token))
        assert debug.display_probe([])['native']['display'] == publication['native']['display']
        debug.vm.qmp.call('set-action', {'reboot': 'reset'})
        debug.vm.qmp.call('system_reset')
        deadline = time.monotonic() + 2
        while debug.vm.qmp.call('x-fdisbull-query-clock')['epoch'] == armed['epoch']:
            assert time.monotonic() < deadline
        with pytest.raises(DebuggerError):
            debug.vm.qmp.call('x-fdisbull-probe-display', args)
        with pytest.raises(DebuggerError):
            debug.display_probe([])
        assert debug.vm.process.poll() is not None


def test_native_eight_layer_runtime_refuses_only_new_probe(probe_witness, monkeypatch):
    legacy = os.environ.get('FDISBULL_QEMU_DISPLAY_PROBE_LEGACY')
    if not legacy:
        message = 'Supply FDISBULL_QEMU_DISPLAY_PROBE_LEGACY for the eight-layer renderer witness'
        if os.environ.get('FDISBULL_REQUIRE_QEMU_CLOCK') == '1':
            pytest.fail(message)
        pytest.skip(message)
    with probe_witness(executable=legacy) as (project, debug, _):
        assert debug.capabilities['renderer_capture'] is True
        assert debug.capabilities['renderer_probe'] is False
        assert debug.capabilities['virtual_mouse_click'] is True
        calls = []
        call = debug.vm.qmp.call
        def watched(command, *args, **kwargs):
            calls.append(command)
            return call(command, *args, **kwargs)
        monkeypatch.setattr(debug.vm.qmp, 'call', watched)
        with pytest.raises(ValueError, match='native extension'):
            debug.display_probe([])
        assert not calls
        debug.display_start(period_ns=10_000_000)
        budget_receipt(debug.clock_advance(25_000_000, timeout_ms=5000), 25_000_000)
        captured = debug.capture_display('legacy-retained.png')
        with pixels(project, captured) as image:
            assert markers(image) == ((0, 0, 0), (0, 0, 0))
        assert 'x-fdisbull-probe-display' not in calls and debug.status()['state'] == 'stopped'
