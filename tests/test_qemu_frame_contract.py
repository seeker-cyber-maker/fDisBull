"""Legacy-shaped frame consumers over one explicitly retained QEMU raster.

The peer supplies source/wire receipts, not native raster-production evidence.
"""
from copy import deepcopy
import base64
import hashlib
import io

from PIL import Image
import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_observation_authority import ObservationAuthority
from test_qemu_video_frame import VideoWire, audio, observation, video


def prepared(o):
    # Bind the production QMP admission path after the fixture installs its wire.
    o.vm.observation_authority = ObservationAuthority(o.vm)
    o.vm.observation_authority.bind(qmp=o.qmp, gdb=o.gdb)
    from fdisbull.qemu_frame_contract import configure_frame_contract
    configure_frame_contract(o.session)
    o.session.video_frame_start()
    o.wire.publish()
    return o.session.video_frame_observe()


def test_public_frame_consumers_keep_one_session_revision_and_true_source(video):
    o = video
    prepared(o)
    before = o.session.status()
    probe = o.session.frame_probe([[319, 199], [0, 0], [319, 199]])
    frame = o.session.frame_rgba(encoding='png')
    after = o.session.status()
    for result in (probe, frame.metadata, after):
        assert result['session_id'] == before['session_id'] == o.session.session_id
        assert result['state_revision'] == before['state_revision']
    assert probe['format'] == 'rgb-samples'
    assert probe['samples'] == [dict(x=x, y=y, rgb=[4, 85, 170])
                               for x, y in ((319, 199), (0, 0), (319, 199))]
    assert frame.pixel(319, 199) == (4, 85, 170, 255)
    assert frame.stride == 1280
    assert frame.sha256 == hashlib.sha256(bytes([4, 85, 170, 255]) * 64000).hexdigest()
    for result in (probe, frame.metadata):
        assert result['source'] == 'qemu_completed_source_raster'
        assert result['frame_profile'] == 'qemu-vga-chain4-scanline-v1'
        assert result['source_bpp'] == 24
        assert result['double_width'] is result['double_height'] is False
        assert result['captured_ticks_clock'] == 'QEMU_CLOCK_VIRTUAL_milliseconds'
        assert result['captured_ticks'] == result['captured_ns'] // 1_000_000
        assert result['application_frame_complete'] is None
        assert result['legacy_phase_equivalence'] is None
        assert result['state_revision_scope'] == 'cooperative-session-control-v1'
    assert probe['frame_identity'] == frame.metadata['frame_identity']
    assert probe['frame_id'] == frame.metadata['frame_id']
    assert probe['mode_id'] == frame.metadata['mode_id']
    assert frame.metadata['codec_origin'] == 'host-adapter'
    assert frame.metadata['transport']['encoding'] == 'png'
    assert frame.metadata['native_transport']['pixel_format'] == 'RGB888'
    assert o.session.capabilities['completed_guest_frames'] is False
    assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == 0
    operations = [row[0] for row in o.project.db.execute('SELECT operation FROM debug_events')]
    assert operations.count('frame-probe') == 1
    assert operations.count('machine-video-frame-probe') == 0
    assert all(command not in ('cont', 'screendump', 'x-fdisbull-query-input')
               for command, _ in o.wire.calls)


@pytest.mark.parametrize('encoding', ['png', 'png-indexed', 'rgba-zstd'])
def test_each_codec_is_real_and_rgba_does_not_publish_or_run_hooks(video, monkeypatch, encoding):
    if encoding == 'rgba-zstd':
        pytest.importorskip('zstandard')
    o = video
    prepared(o)
    revision = o.session.status()['state_revision']
    before_events = o.project.db.execute('SELECT count(*) FROM debug_events').fetchone()[0]
    before_artifacts = o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]
    def forbidden(*args, **kwargs):
        pytest.fail('Direct frame reads must not publish events, artifacts or hooks')
    monkeypatch.setattr(o.session, '_event', forbidden)
    monkeypatch.setattr(o.session, '_artifact', forbidden)
    monkeypatch.setattr(o.session, '_capture_with_hooks', forbidden, raising=False)
    wire = o.session.call('video.screenshot', {'encoding': encoding})
    raw = base64.b64decode(wire['data_base64'] if encoding == 'rgba-zstd' else wire['png_base64'])
    assert hashlib.sha256(raw).hexdigest() == wire['sha256']
    assert wire['codec_origin'] == 'host-adapter'
    assert wire['native_transport']['pixel_format'] == 'RGB888'
    if encoding == 'rgba-zstd':
        import zstandard
        assert zstandard.get_frame_parameters(raw).content_size == 256000
        assert zstandard.ZstdDecompressor().decompress(raw) == bytes([4, 85, 170, 255]) * 64000
    else:
        with Image.open(io.BytesIO(raw)) as image:
            assert image.mode == ('P' if encoding == 'png-indexed' else 'RGBA')
            assert image.convert('RGB').tobytes() == o.wire.rgb
    frame = o.session.frame_rgba(encoding=encoding)
    assert frame.metadata['transport']['encoding'] == encoding
    assert frame.metadata['state_revision'] == revision == o.session.status()['state_revision']
    assert frame.sha256 == hashlib.sha256(bytes([4, 85, 170, 255]) * 64000).hexdigest()
    assert o.project.db.execute('SELECT count(*) FROM debug_events').fetchone()[0] == before_events
    assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == before_artifacts


@pytest.mark.parametrize('count', [256, 257])
def test_indexed_boundary_preserves_every_color_or_reports_exact_png_fallback(video, count):
    o = video
    colors = [bytes((index % 256, index // 256, 17)) for index in range(count)]
    o.wire.rgb = b''.join(colors[index % count] for index in range(64000))
    prepared(o)
    result = o.session.call('video.screenshot', {'encoding': 'png-indexed'})
    with Image.open(io.BytesIO(base64.b64decode(result['png_base64']))) as image:
        assert image.convert('RGB').tobytes() == o.wire.rgb
        assert image.mode == ('P' if count == 256 else 'RGBA')
    if count == 256:
        assert result['encoding'] == 'png-indexed' and result['palette_colors'] == 256
        assert 'fallback_reason' not in result
    else:
        assert result['encoding'] == 'png'
        assert result['requested_encoding'] == 'png-indexed'
        assert result['fallback_reason'] == 'more_than_256_colors'


@pytest.mark.parametrize('points', [[], [[7, 9]] * 4096])
def test_empty_and_maximum_public_probe_are_ordered_and_publish_once(video, points):
    o = video
    prepared(o)
    before = len(o.wire.calls)
    result = o.session.call('video.probe', {'points': points})
    assert result['samples'] == [dict(x=x, y=y, rgb=[4, 85, 170]) for x, y in points]
    chunks = [args for command, args in o.wire.calls[before:] if command == 'x-fdisbull-probe-video-frame']
    assert len(chunks) == (16 if points else 0)
    assert all(len(chunk['points']) == 256 for chunk in chunks)
    assert 'png_base64' not in result and 'data_base64' not in result
    assert o.project.db.execute("SELECT count(*) FROM debug_events WHERE operation='frame-probe'").fetchone()[0] == 1
    assert o.project.db.execute("SELECT count(*) FROM debug_events WHERE operation='machine-video-frame-probe'").fetchone()[0] == 0


@pytest.mark.parametrize('points', [[[0, 0]] * 4097, [[True, 0]], [[320, 0]], [[0, 200]], [[0, 0, 0]]])
def test_invalid_public_probe_is_refused_before_io(video, points):
    o = video
    prepared(o)
    before = list(o.wire.calls)
    with pytest.raises(ValueError):
        o.session.frame_probe(points)
    assert o.wire.calls == before and not o.vm.closed


def test_missing_or_unadvertised_codec_fails_before_native_io(video):
    o = video
    prepared(o)
    before = list(o.wire.calls)
    with pytest.raises(ValueError, match='encoding'):
        o.session.frame_rgba(encoding='ignored-codec')
    o.session.capabilities['video']['screenshot_encodings'] = ['png']
    with pytest.raises(DebuggerError, match='advertise'):
        o.session.frame_rgba(encoding='png-indexed')
    assert o.wire.calls == before and not o.vm.closed


def test_reads_require_existing_raster_and_never_restart_invalidated_stream(video):
    o = video
    from fdisbull.qemu_frame_contract import configure_frame_contract
    o.vm.observation_authority = ObservationAuthority(o.vm)
    o.vm.observation_authority.bind(qmp=o.qmp, gdb=o.gdb)
    configure_frame_contract(o.session)
    for action in (lambda: o.session.frame_probe([]), lambda: o.session.frame_rgba(encoding='png')):
        with pytest.raises(ValueError, match='No completed source raster'):
            action()
    assert not any(command == 'x-fdisbull-start-video-frame' for command, _ in o.wire.calls)
    o.session.video_frame_start(); o.wire.publish()
    first = o.session.frame_probe([])
    o.wire.video.update(state='invalidated', reason='configuration-changed', **{'in-progress': False, 'rows-sampled': 0})
    o.wire.video.pop('frame'); o.wire.video.pop('next-deadline-ns')
    before = len(o.wire.calls)
    with pytest.raises(ValueError, match='No completed source raster'):
        o.session.frame_rgba(encoding='png')
    assert not o.vm.closed
    assert not any(command in ('cont', 'x-fdisbull-start-video-frame') for command, _ in o.wire.calls[before:])
    o.session.video_frame_start(); o.wire.publish()
    second = o.session.frame_probe([])
    assert second['session_id'] == first['session_id']
    assert second['mode_id'] > first['mode_id']
    assert second['frame_identity']['stream'] != first['frame_identity']['stream']
    assert second['state_revision'] > first['state_revision']


def test_same_pixels_new_native_ordinal_and_stop_retains_frame_identity(video):
    o = video
    prepared(o)
    first = o.session.frame_probe([])
    o.wire.publish()
    second = o.session.frame_probe([])
    assert second['frame_id'] == first['frame_id'] + 1
    assert second['mode_id'] == first['mode_id']
    assert second['frame']['pixel-sha256'] == first['frame']['pixel-sha256']
    o.session.video_frame_stop()
    third = o.session.frame_rgba(encoding='png').metadata
    assert third['frame_identity'] == second['frame_identity']
    assert third['mode_id'] == second['mode_id']
    assert third['state_revision'] > second['state_revision']


@pytest.mark.parametrize('terminal', ['cancelled', 'dispatched'])
def test_frame_reads_remain_available_after_native_input_schedule(video, terminal):
    from test_qemu_input_schedule import InputWire, COMMANDS
    class FrameInputWire(VideoWire, InputWire):
        pass
    o = video
    o.wire = FrameInputWire(o.clock); o.qmp.socket = o.wire
    o.vm.qmp_commands |= COMMANDS | {'input-send-event'}
    o.session.capabilities['virtual_input_schedule'] = True
    prepared(o)
    initial = o.session.frame_probe([])
    o.session.keyboard_key_down('a')
    o.session.input_schedule(1000)
    if terminal == 'cancelled':
        o.session.input_cancel_pending()
    else:
        o.wire.finish()
        unreconciled = o.session.status()['state_revision']
        o.session.input_schedule_observe()
        reconciled = o.session.status()['state_revision']
        assert reconciled > unreconciled
        o.session.input_schedule_observe()
        assert o.session.status()['state_revision'] == reconciled
    assert o.wire.input['state'] == terminal
    before = o.session.status()
    offset = len(o.wire.calls)
    probe = o.session.frame_probe([[0, 0]])
    rgba = o.session.frame_rgba(encoding='png')
    assert probe['frame_identity'] == initial['frame_identity'] == rgba.metadata['frame_identity']
    assert probe['state_revision'] == before['state_revision'] == rgba.metadata['state_revision']
    assert probe['state_revision'] > initial['state_revision']
    assert not any(command in ('x-fdisbull-query-input', 'x-fdisbull-query-frame-keys', 'cont')
                   for command, _ in o.wire.calls[offset:])


def test_control_effect_during_probe_rejects_result_without_probe_event(video, monkeypatch):
    o = video
    o.vm.qmp_commands |= {'input-send-event'}
    prepared(o)
    selected = o.session._video_frame_selected_probe
    def change_control(*args):
        value = selected(*args)
        # The native read has completed; a reentrant public queue admission
        # changes only control state before the facade publishes its result.
        o.session.keyboard_key_down('a')
        return value
    monkeypatch.setattr(o.session, '_video_frame_selected_probe', change_control)
    with pytest.raises(DebuggerError, match='Session control or owner changed'):
        o.session.frame_probe([[0, 0]])
    assert o.vm.closed
    assert o.project.db.execute("SELECT count(*) FROM debug_events WHERE operation='frame-probe'").fetchone()[0] == 0


def test_python_json_and_saved_script_probe_routes_share_the_contract(video):
    from fdisbull.debug_script import execute_script, validate_script
    from fdisbull.debugger import DebugWorkspace
    o = video
    prepared(o)
    workspace = DebugWorkspace.__new__(DebugWorkspace)
    workspace.sessions = {o.session.run_id: o.session}
    workspace.async_runs = {}
    result = workspace.invoke('debug-frame-probe', o.project.path,
                              {'run': o.session.run_id, 'points': [[0, 0]]})
    assert result['source_bpp'] == 24
    route = dict(format='fdisbull-script-1', backend='qemu-machine', steps=[
        dict(op='frame-probe', points=[[0, 0]], **{'as': 'frame'}),
        dict(op='assert', value='$frame.source_bpp', equals=24)])
    scripted = execute_script(o.session, route)
    assert scripted['ok']
    before = list(o.wire.calls)
    route['steps'] = [dict(op='keyboard.key-down', key='a'), dict(op='frame-probe', points=[[320, 0]])]
    with pytest.raises(ValueError):
        validate_script(route, session=o.session)
    assert o.wire.calls == before


def test_generic_coherence_accepts_explicit_qemu_profile_and_complete_identity(video):
    from fdisbull.frame_coherence import capture_frame_state
    from test_frame_coherence import Fake
    o = video
    prepared(o)
    c = Fake(); c.session = o.session
    result = capture_frame_state(c, o.session.capture_video_frame)
    assert result['complete'] and result['issues'] == []
    assert result['atomic'] is False and result['frame_state_equivalence'] is None
    assert result['frame']['metadata']['source'] == 'qemu_completed_source_raster'
    assert result['status_before']['frame_identity'] == result['frame']['metadata']['frame_identity']
    assert not c.calls


@pytest.mark.parametrize('change', ['profile', 'clock', 'bpp', 'stream', 'generation', 'missing-identity'])
def test_generic_coherence_rejects_wrong_source_contract_or_bracket_identity(video, change):
    from fdisbull.frame_coherence import capture_frame_state
    from test_frame_coherence import Fake
    o = video
    prepared(o)
    c = Fake(); c.session = o.session
    def capture():
        result = deepcopy(o.session.capture_video_frame())
        metadata = result['metadata']
        if change == 'profile': metadata['frame_profile'] = 'legacy'
        elif change == 'clock': metadata['captured_ticks_clock'] = 'PIC_Ticks_milliseconds'
        elif change == 'bpp': metadata['source_bpp'] = 32
        elif change == 'stream': metadata['frame_identity']['stream'] = 'foreign'
        elif change == 'generation': metadata['frame_identity']['configuration_generation'] += 1
        else: metadata.pop('frame_identity')
        return result
    result = capture_frame_state(c, capture)
    assert not result['complete'] and result['issues']
    assert not c.calls


@pytest.mark.parametrize('ticks', [False, 0.0])
def test_custom_qemu_status_requires_integer_clock_ticks(video, ticks):
    from fdisbull.frame_coherence import _status_issue
    o = video
    prepared(o)
    status = dict(o.session.frame_probe([]), state='stopped', captured_ticks=ticks)
    assert _status_issue(status) == 'QEMU frame profile, layout or clock is invalid'


def test_freshness_does_not_cross_a_native_generation_hidden_by_same_mode_id(video):
    from fdisbull.frame_coherence import capture_frame_state
    from test_frame_coherence import Fake
    o = video
    prepared(o)
    first = dict(o.session.frame_probe([]), state='stopped')
    second = deepcopy(first)
    second['frame_id'] += 1
    second['frame_identity'].update(frame_id=second['frame_id'], clock_epoch='different-clock')
    statuses = [first, second]
    c = Fake(); c.session = o.session
    c.on_advance = lambda ms: setattr(c, 'guest_elapsed', c.guest_elapsed + ms)
    def no_capture():
        pytest.fail('Cross-generation freshness must refuse before capture')
    result = capture_frame_state(c, no_capture, status_reader=lambda: statuses.pop(0), require_fresh=True)
    assert not result['complete']
    assert result['issues'] == ['source generation changed during freshness wait']


@pytest.mark.parametrize('frozen', [False, True])
def test_passive_frame_facade_preserves_full_and_selected_history_guards(video, frozen):
    from fdisbull.qemu_cpu_undo_guard import before_operation
    from fdisbull.qemu_dos_history import QemuDOSHistoryMixin
    o = video
    prepared(o)
    s = o.session
    s._qemu_history_live = dict(valid=True, cursor='retained')
    s._qemu_cpu_delta_history = dict(id='selected', valid=True, frozen=frozen)
    s._cpu_delta_before_operation = lambda name, args, kwargs: before_operation(s, name, args, kwargs)
    o.vm.history_operation_guard = lambda name, args, kwargs: QemuDOSHistoryMixin._history_before_operation(s, name, args, kwargs)
    original = deepcopy((s._qemu_history_live, s._qemu_cpu_delta_history))
    before = s.status()['state_revision']
    s.frame_probe([])
    s.frame_rgba(encoding='png')
    s.call('video.screenshot')
    assert before == s.status()['state_revision']
    assert (s._qemu_history_live, s._qemu_cpu_delta_history) == original
