"""Native PCM witnesses using the separately selected fDisBull QEMU extension.

These use the same explicit private runtime inputs and require switch as the
clock witnesses. Tone expectations come from the guest PIT program. No host
audio hardware, wall-time pacing, or sample-count-to-guest-time conversion.
"""
from contextlib import contextmanager
import io
import json
import time
import wave

import pytest

from fdisbull.project import Project
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.debugger import DebugWorkspace
from fdisbull.cli import respond
from support.dos_process_fixture import digest
from support.qemu_audio_fixture import PIT_INPUT_HZ, SPEAKER_DIVISOR, speaker_tone
from test_qemu_clock_budget_native import clock_runtime, clock_disk, park, budget_receipt
from test_qemu_dos_process_native import create_project, launch_options, process_record, com_address


@pytest.fixture
def audio_witness(tmp_path, clock_runtime, clock_disk):
    @contextmanager
    def launch():
        code, offsets = speaker_tone(tmp_path, clock_runtime['nasm'])
        binary, project = create_project(tmp_path, code)
        with project:
            with project.debugger(clock_runtime['executable'], tmp_path,
                    **launch_options(clock_runtime, clock_disk, qemu_clock='virtual',
                                     qemu_audio='pc-speaker')) as debug:
                info = process_record(debug)
                symbols = {key: com_address(info, value) for key, value in offsets.items()}
                park(debug, symbols['ready_ip'])
                yield project, debug, symbols
            assert debug.vm.process.poll() is not None
        assert binary.read_bytes() == code
        assert digest(clock_disk['image']) == clock_disk['prepared_sha256']
    return launch


def pcm_bytes(project, artifact):
    row = project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',
                             (artifact['artifact'],)).fetchone()
    with wave.open(io.BytesIO(row[0]), 'rb') as stream:
        assert stream.getparams()[:3] == (1, 1, 32000)
        assert stream.getnframes() == artifact['metadata']['frames']
        return stream.readframes(stream.getnframes())


def assert_tone(pcm):
    assert len(pcm) >= 3200
    # Discard onset/tail buffer boundaries. Count rising edges independently
    # of the native receipt and compare against the authored PIT divisor.
    steady = pcm[1024:-512]
    assert min(steady) < 64 and max(steady) > 192
    edges = sum(a < 128 <= b for a, b in zip(steady, steady[1:]))
    frequency = edges * 32000 / len(steady)
    assert frequency == pytest.approx(PIT_INPUT_HZ / SPEAKER_DIVISOR, rel=.03)


def test_native_tone_output_passive_reads_and_retained_wav(audio_witness):
    with audio_witness() as (project, debug, symbols):
        idle = debug.audio_observe()
        assert idle['state'] == 'idle' and idle['frames'] == 0
        started = debug.audio_start(max_frames=16000)
        display = debug.display_start(period_ns=20_000_000)
        assert display['epoch'] == started['epoch']
        assert started['state'] == 'capturing' and started['frames'] == 0
        park(debug, symbols['tone_ready_ip'])
        before = debug.clock_observe()
        budget_receipt(debug.clock_advance(200_000_000, timeout_ms=5000), 200_000_000, before=before)
        first = debug.audio_observe()
        second = debug.audio_observe()
        assert first['native'] == second['native']
        assert first['observed_ns'] == second['observed_ns']
        assert first['frames'] > 3200 and first['dropped_frames'] == 0
        chunks = first['native']['chunks']
        assert sum(chunk['frames'] for chunk in chunks) == first['frames']
        assert all(started['start_ns'] <= chunk['virtual-ns'] <= first['observed_ns'] for chunk in chunks)
        artifact = debug.capture_audio('speaker.wav')
        frame = debug.capture_display('speaker-display.png')
        assert frame['metadata']['updates'] > 0
        assert frame['metadata']['epoch'] == artifact['metadata']['epoch']
        assert frame['metadata']['observed_ns'] == artifact['metadata']['observed_ns']
        assert_tone(pcm_bytes(project, artifact))
        assert artifact['metadata']['device_queue_drained'] is None
        assert artifact['metadata']['guest_audio_complete'] is None
        assert debug.audio_observe()['native'] == first['native']
        stopped = debug.audio_stop()
        debug.display_stop()
        assert stopped['state'] == 'stopped' and stopped['frames'] == first['frames']
        assert debug.audio_stop()['native'] == stopped['native']
        budget_receipt(debug.clock_advance(50_000_000, timeout_ms=5000), 50_000_000)
        assert debug.audio_observe()['frames'] == first['frames']
        retained = debug.capture_audio('retained.wav')
        assert pcm_bytes(project, retained) == pcm_bytes(project, artifact)
        path, artifact_id, token = project.path, artifact['artifact'], started['window']
    with Project(path) as reopened:
        metadata = json.loads(reopened.db.execute('SELECT metadata FROM debug_artifacts WHERE id=?',
                                                  (artifact_id,)).fetchone()[0])
        assert metadata['window'] == token and metadata['frames'] == first['frames']


def test_native_inactive_speaker_is_not_synthetic_silence(audio_witness):
    with audio_witness() as (project, debug, symbols):
        park(debug, symbols['tone_ready_ip'])
        budget_receipt(debug.clock_advance(50_000_000, timeout_ms=5000), 50_000_000)
        debug.write_memory(symbols['phase_ip'], '01', expected_hex='00')
        park(debug, symbols['quiet_ready_ip'])
        # Let existing device buffers finish under explicit guest execution.
        budget_receipt(debug.clock_advance(200_000_000, timeout_ms=5000), 200_000_000)
        started = debug.audio_start()
        budget_receipt(debug.clock_advance(100_000_000, timeout_ms=5000), 100_000_000)
        observed = debug.audio_observe()
        assert observed['observed_ns'] - started['start_ns'] >= 100_000_000
        assert observed['frames'] == 0 and observed['native']['chunks'] == []
        assert pcm_bytes(project, debug.capture_audio('inactive.wav')) == b''


def test_native_overflow_is_visible_and_new_windows_do_not_replay(audio_witness):
    with audio_witness() as (project, debug, symbols):
        first = debug.audio_start(max_frames=32)
        park(debug, symbols['tone_ready_ip'])
        budget_receipt(debug.clock_advance(50_000_000, timeout_ms=5000), 50_000_000)
        observed = debug.audio_observe()
        assert observed['state'] == 'overflow' and observed['frames'] == 32
        assert observed['dropped_frames'] > 0
        with pytest.raises(ValueError, match='overflowed'):
            debug.capture_audio()
        assert project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='audio'").fetchone()[0] == 0
        debug.audio_stop()
        second = debug.audio_start(max_frames=6400)
        assert second['window'] != first['window'] and second['frames'] == 0
        assert second['native']['chunks'] == []
        budget_receipt(debug.clock_advance(100_000_000, timeout_ms=5000), 100_000_000)
        assert debug.audio_observe()['frames'] > 0


def test_native_json_and_saved_script_reach_audio_capture(audio_witness):
    with audio_witness() as (project, debug, symbols):
        workspace = DebugWorkspace()
        workspace.sessions[debug.run_id] = debug
        def invoke(method, **params):
            result = respond(dict(id=1, method=method, params=dict(
                project=str(project.path), run=debug.run_id, **params)), debugger=workspace)
            assert result['ok'], result
            return result['result']
        started = invoke('debug-audio-start', max_frames=16000)
        park(debug, symbols['tone_ready_ip'])
        script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
            dict(op='clock-advance', delta_ns=200_000_000, timeout_ms=5000),
            dict(op='audio-stop'), dict(op='capture-audio', name='script.wav')])
        result = debug.script(script, timeout_ms=6000)
        assert result['ok'] and result['completed_steps'] == len(script['steps']), result
        observed = invoke('debug-audio-observe')
        assert observed['window'] == started['window'] and observed['state'] == 'stopped'
        artifact = invoke('debug-capture-audio', name='json.wav')
        assert_tone(pcm_bytes(project, artifact))


def test_native_media_tokens_and_reset_cannot_rebind_retained_evidence(audio_witness):
    with audio_witness() as (_, debug, _):
        audio = debug.audio_start()
        display = debug.display_start()
        for command in ('x-fdisbull-stop-audio', 'x-fdisbull-stop-display'):
            with pytest.raises(DebuggerError, match='token'):
                debug.vm.qmp.call(command, {'token': 'not-the-owner'})
        assert debug.audio_observe()['native'] == audio['native']
        assert debug.display_observe()['native'] == display['native']
        epoch = debug.clock_observe()['virtual_clock']['native']['epoch']
        # Match the explicit reset probe in the clock suite; production still
        # exits on reboot, and no restore or automatic recovery is attempted.
        debug.vm.qmp.call('set-action', {'reboot': 'reset'})
        debug.vm.qmp.call('system_reset')
        deadline = time.monotonic() + 2
        while debug.vm.qmp.call('x-fdisbull-query-clock')['epoch'] == epoch:
            assert time.monotonic() < deadline
        for command in ('x-fdisbull-query-audio', 'x-fdisbull-query-display'):
            with pytest.raises(DebuggerError, match='invalid|epoch'):
                debug.vm.qmp.call(command)
        with pytest.raises(DebuggerError, match='virtual clock'):
            debug.display_observe()
        assert debug.vm.process.poll() is not None
