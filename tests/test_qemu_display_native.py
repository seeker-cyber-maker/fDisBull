"""Native renderer fences must retain pixels without inventing guest frames."""
from contextlib import contextmanager
import io
import json

from PIL import Image
import pytest

from fdisbull.project import Project
from fdisbull.cli import respond
from fdisbull.debugger import DebugWorkspace
from support.dos_process_fixture import digest
from support.qemu_display_fixture import partial_display
from test_qemu_clock_budget_native import clock_runtime, clock_disk, park, budget_receipt
from test_qemu_dos_process_native import create_project, launch_options, process_record, com_address


@pytest.fixture
def display_witness(tmp_path, clock_runtime, clock_disk):
    @contextmanager
    def launch():
        code, offsets = partial_display(tmp_path, clock_runtime['nasm'])
        binary, project = create_project(tmp_path, code)
        with project:
            with project.debugger(clock_runtime['executable'], tmp_path,
                    **launch_options(clock_runtime, clock_disk, qemu_clock='virtual')) as debug:
                info = process_record(debug)
                symbols = {key: com_address(info, value) for key, value in offsets.items()}
                park(debug, symbols['ready_ip'])
                yield project, debug, symbols
            assert debug.vm.process.poll() is not None
        assert binary.read_bytes() == code
        assert digest(clock_disk['image']) == clock_disk['prepared_sha256']
    return launch


def pixels(project, artifact):
    data = project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',
                              (artifact['artifact'],)).fetchone()[0]
    with Image.open(io.BytesIO(data)) as image:
        return image.convert('RGB')


def markers(image):
    assert image.width % 320 == image.height % 200 == 0
    sx, sy = image.width // 320, image.height // 200
    return image.getpixel((10*sx, 10*sy)), image.getpixel((20*sx, 10*sy))


def test_native_retained_publication_is_immutable_across_partial_guest_drawing(display_witness):
    with display_witness() as (project, debug, symbols):
        started = debug.display_start(period_ns=20_000_000)
        assert started['updates'] == 0 and started['completed_renderer_update'] is False
        assert debug.display_observe()['updates'] == 0
        with pytest.raises(ValueError, match='No completed renderer'):
            debug.capture_display()
        budget_receipt(debug.clock_advance(55_000_000, timeout_ms=5000), 55_000_000)
        first = debug.capture_display('before-drawing.png')
        initial = first['metadata']
        assert initial['updates'] >= 2 and initial['completed_renderer_update'] is True
        assert initial['completed_guest_frame'] is None and initial['guest_frame_id'] is None
        assert markers(pixels(project, first)) == ((0, 0, 0), (0, 0, 0))
        before = debug.clock_observe()
        debug.write_memory(symbols['phase_ip'], '01', expected_hex='00')
        point = debug.breakpoint(symbols['partial_ready_ip'])
        try:
            stop = debug.clock_advance(100_000_000, timeout_ms=5000)
            budget_receipt(stop, 100_000_000, before=before, reached=False)
            assert stop['outcome'] == 'breakpoint'
            assert point['breakpoint_id'] in stop['session']['stop_reason']['breakpoint_ids']
        finally:
            debug.delete_breakpoint(point['breakpoint_id'])
        retained = debug.capture_display('retained-before-drawing.png')
        assert retained['metadata']['update_id'] == initial['update_id']
        assert retained['metadata']['pixel_sha256'] == initial['pixel_sha256']
        assert markers(pixels(project, retained)) == ((0, 0, 0), (0, 0, 0))
        # A conventional screendump intentionally refreshes current VRAM and
        # sees the first write. It must not overwrite the owned publication.
        surface = debug.capture_surface('partial-current-surface.png')
        assert markers(pixels(project, surface)) == ((255, 0, 0), (0, 0, 0))
        assert debug.capture_display()['metadata']['pixel_sha256'] == initial['pixel_sha256']
        with pytest.raises(ValueError, match='No newer renderer'):
            debug.capture_display(after_update=initial['update_id'])
        # The next explicit interval can publish a half-drawn guest image.
        # Renderer completion is deliberately not relabeled guest completion.
        budget_receipt(debug.clock_advance(25_000_000, timeout_ms=5000), 25_000_000)
        partial = debug.capture_display('partial-published.png', after_update=initial['update_id'])
        assert markers(pixels(project, partial)) == ((255, 0, 0), (0, 0, 0))
        assert partial['metadata']['completed_renderer_update'] is True
        assert partial['metadata']['completed_guest_frame'] is None


def test_native_mode_change_stop_and_new_window_keep_publication_identity(display_witness):
    with display_witness() as (project, debug, symbols):
        first = debug.display_start(period_ns=10_000_000)
        budget_receipt(debug.clock_advance(25_000_000, timeout_ms=5000), 25_000_000)
        graphics = debug.capture_display('graphics.png')
        debug.write_memory(symbols['phase_ip'], '03', expected_hex='00')
        park(debug, symbols['text_ready_ip'])
        budget_receipt(debug.clock_advance(25_000_000, timeout_ms=5000), 25_000_000)
        text = debug.capture_display('text.png', after_update=graphics['metadata']['update_id'])
        assert pixels(project, text).size != pixels(project, graphics).size
        assert text['metadata']['window'] == first['window']
        stopped = debug.display_stop()
        assert stopped['state'] == 'stopped'
        assert debug.display_stop()['native'] == stopped['native']
        budget_receipt(debug.clock_advance(50_000_000, timeout_ms=5000), 50_000_000)
        retained = debug.capture_display('stopped.png')
        assert retained['metadata']['update_id'] == text['metadata']['update_id']
        assert retained['metadata']['pixel_sha256'] == text['metadata']['pixel_sha256']
        assert retained['metadata']['age_ns'] > text['metadata']['age_ns']
        second = debug.display_start()
        assert second['window'] != first['window'] and second['updates'] == 0
        with pytest.raises(ValueError, match='No completed renderer'):
            debug.capture_display()
        path, artifact_id = project.path, text['artifact']
    with Project(path) as reopened:
        saved = json.loads(reopened.db.execute('SELECT metadata FROM debug_artifacts WHERE id=?',
                                               (artifact_id,)).fetchone()[0])
        assert saved['window'] == first['window'] and saved['completed_guest_frame'] is None


def test_native_json_and_saved_script_capture_the_same_renderer_publication(display_witness):
    with display_witness() as (project, debug, _):
        workspace = DebugWorkspace()
        workspace.sessions[debug.run_id] = debug
        def invoke(method, **params):
            result = respond(dict(id=1, method=method, params=dict(
                project=str(project.path), run=debug.run_id, **params)), debugger=workspace)
            assert result['ok'], result
            return result['result']
        started = invoke('debug-display-start', period_ns=10_000_000)
        script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
            dict(op='clock-advance', delta_ns=25_000_000, timeout_ms=5000),
            dict(op='display-stop'), dict(op='capture-display', name='script-display.png', after_update=0)])
        report = debug.script(script, timeout_ms=6000)
        assert report['ok'] and report['completed_steps'] == 3, report
        observed = invoke('debug-display-observe')
        artifact = invoke('debug-capture-display', name='json-display.png', after_update=0)
        assert observed['window'] == started['window']
        assert artifact['metadata']['native'] == observed['native']
        assert artifact['metadata']['pixel_sha256'] == report['steps'][2]['result']['metadata']['pixel_sha256']
