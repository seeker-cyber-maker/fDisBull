"""Real-codec capture checks with independently authored, known pixels."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import random
import shutil
import struct
import subprocess
import sys

from PIL import Image
import pytest

from fdisbull import capture_audit as module
from fdisbull.cli import main, respond


COLORS = [(255, 0, 0), (255, 0, 0), (0, 255, 0),
          (0, 0, 255), (0, 0, 255), (255, 255, 0)]
WIDTH, HEIGHT = 64, 48


@pytest.fixture
def readers(request):
    tools = {name: shutil.which(name) for name in ('ffmpeg', 'ffprobe')}
    if not all(tools.values()):
        if request.config.getoption('--require-native', default=False):
            pytest.fail('Required native acceptance also needs ffmpeg and ffprobe for capture audits')
        pytest.skip('ffmpeg and ffprobe are optional capture-audit readers')
    return tools


def make_video(path, readers, pixels, width=WIDTH, height=HEIGHT, rate=6):
    # Lossless ZMBV is the recorded codec used by the native DOS investigation.
    command = [readers['ffmpeg'], '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
               '-s', f'{width}x{height}', '-framerate', str(rate), '-i', 'pipe:0',
               '-threads', '1', '-c:v', 'zmbv', '-pix_fmt', 'bgr0', str(path)]
    run = subprocess.run(command, input=pixels, capture_output=True, timeout=30)
    assert run.returncode == 0, run.stderr.decode(errors='replace')
    return path


@pytest.fixture
def video(tmp_path, readers):
    data = b''.join(bytes(color) * (WIDTH * HEIGHT) for color in COLORS)
    return make_video(tmp_path / 'authored.avi', readers, data)


def read_audit(receipt):
    summary_path = Path(receipt['summary'])
    assert hashlib.sha256(summary_path.read_bytes()).hexdigest() == receipt['summary_sha256']
    summary = json.loads(summary_path.read_text())
    return summary, summary_path.parent


@pytest.mark.parametrize('every', [0, 1, 2, 4])
def test_all_frames_hashed_before_sampling_with_exact_pts(video, tmp_path, every):
    original = video.read_bytes()
    receipt = module.audit_capture([video], tmp_path / 'audit', every=every, html=bool(every))
    assert receipt['ok'] and receipt['status'] == 'passed'
    summary, directory = read_audit(receipt)
    segment = summary['segments'][0]
    records = [json.loads(line) for line in (directory / 'segment-000/frames.jsonl').read_text().splitlines()]
    expected = [hashlib.sha256(bytes((*color, 255)) * (WIDTH * HEIGHT)).hexdigest() for color in COLORS]
    assert [r['decoded_rgba_sha256'] for r in records] == expected
    assert segment['rgba_hash_sequence_sha256'] == hashlib.sha256(b''.join(bytes.fromhex(h) for h in expected)).hexdigest()
    assert segment['decoded_frames'] == 6 and segment['adjacent_identical_frames'] == 2
    assert [r['source_pts'] for r in records] == list(range(6))
    assert [Fraction(r['source_time_seconds_exact']) for r in records] == [Fraction(i, 6) for i in range(6)]
    assert all(r['source_time_base'] == '1/6' and r['guest_ticks'] is None for r in records)
    indices = [r['frame_index'] for r in records if 'png' in r]
    assert indices == (list(range(0, 6, every)) if every else [])
    assert segment['saved_frames'] == len(indices)
    for r in records:
        if 'png' in r:
            with Image.open(directory / 'segment-000' / r['png']) as image:
                assert hashlib.sha256(image.convert('RGBA').tobytes()).hexdigest() == r['decoded_rgba_sha256']
    assert receipt['output_bytes'] == sum(p.stat().st_size for p in directory.rglob('*') if p.is_file())
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in directory.rglob('*') if p.is_file())
    assert video.read_bytes() == original
    if every:
        html = (directory / 'segment-000/inspection.html').read_text()
        assert 'Guest ticks: unknown' in html and 'Inspection speed' in html


def test_segments_keep_independent_clocks_and_modes(video, tmp_path, readers):
    second = make_video(tmp_path / 'other-mode.avi', readers, bytes((12, 34, 56)) * 8 * 8 * 2,
                        width=8, height=8, rate=2)
    receipt = module.audit_capture([video, second], tmp_path / 'audit')
    summary, directory = read_audit(receipt)
    assert receipt['ok'] and receipt['guest_clock_mapping'] is None
    assert [s['decoded_frames'] for s in summary['segments']] == [6, 2]
    assert [s['stream']['time_base'] for s in summary['segments']] == ['1/6', '1/2']
    for index in (0, 1):
        first = json.loads((directory / f'segment-{index:03d}/frames.jsonl').read_text().splitlines()[0])
        assert first['source_pts'] == 0
    assert 'no inferred chronological concatenation' in summary['segment_order']


@pytest.mark.parametrize('failure', ['missing', 'truncated', 'payload'])
def test_capture_failures_are_retained_without_certification(video, tmp_path, failure):
    damaged = tmp_path / f'{failure}.avi'
    if failure == 'truncated':
        damaged.write_bytes(video.read_bytes()[:-23])
    elif failure == 'payload':
        data = bytearray(video.read_bytes())
        # Locate the first video payload within movi; corrupt bytes, not container lengths.
        movi = data.index(b'movi')
        chunk = data.index(b'00dc', movi)
        size = struct.unpack_from('<I', data, chunk + 4)[0]
        assert size > 40
        data[chunk + 8 + 12:chunk + 8 + 40] = b'\xff' * 28
        damaged.write_bytes(data)
    receipt = module.audit_capture([damaged], tmp_path / 'audit')
    assert not receipt['ok'] and receipt['status'] == 'failed'
    summary, _ = read_audit(receipt)
    assert summary['segments'][0]['status'] == 'failed'
    assert summary['segments'][0]['error']


def test_cli_and_json_need_no_project_and_cli_failure_is_nonzero(video, tmp_path, capsys):
    reply = respond({'method': 'capture-audit', 'params': {'inputs': [str(video)],
                    'output': str(tmp_path / 'json-audit')}}, default_project='/missing.fdb')
    assert reply['ok'] and reply['result']['ok']
    assert main(['capture-audit', str(video), '--output', str(tmp_path / 'cli-audit'), '--every', '2']) == 0
    assert json.loads(capsys.readouterr().out)['result']['ok']
    assert main(['capture-audit', str(tmp_path / 'missing.avi'), '--output', str(tmp_path / 'failed-cli')]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result['ok'] and not result['result']['ok']  # Dispatch success is not audit success.


def test_output_delivery_reference_preserves_audit_failure(video, tmp_path, capsys):
    # A small reply budget must not turn failed execution into CLI exit zero.
    missing = [str(tmp_path / (f'missing-{i}-' + 'x' * 120 + '.avi')) for i in range(16)]
    assert main(['--max-output-bytes', '4096', '--output-artifact-dir', str(tmp_path / 'artifacts'),
                 'capture-audit', *missing,
                 '--output', str(tmp_path / 'failed')]) == 1
    reply = json.loads(capsys.readouterr().out)
    assert reply['ok'] and reply['result']['format'] == 'fdisbull-output-ref-1'
    assert reply['result']['execution']['status'] == 'failed'


def test_timestamp_fallback_is_explicit_and_never_truncates_floats():
    assert module.frame_timing({'best_effort_timestamp': '7'}, Fraction(1, 6)) == (
        7, 'best_effort_timestamp', Fraction(7, 6))
    with pytest.raises(module.VerificationError, match='neither PTS'):
        module.frame_timing({'pts': 1.5, 'best_effort_timestamp': True}, Fraction(1, 6))


@pytest.mark.parametrize('params', [
    {'max_frames': 5}, {'max_frame_bytes': 64}, {'max_input_bytes': 12}, {'max_metadata_bytes': 1024},
])
def test_reader_budgets_fail_and_retain_receipts(video, tmp_path, params):
    receipt = module.audit_capture([video], tmp_path / 'audit', **params)
    assert not receipt['ok']
    summary, _ = read_audit(receipt)
    assert summary['segments'][0]['error']


def test_output_budget_stops_png_export(tmp_path, readers):
    pixels = random.Random(7261).randbytes(1024 * 512 * 3)
    noisy = make_video(tmp_path / 'noise.avi', readers, pixels, width=1024, height=512, rate=1)
    receipt = module.audit_capture([noisy], tmp_path / 'audit', every=1, max_output_bytes=2*1024*1024)
    assert not receipt['ok']
    summary, directory = read_audit(receipt)
    assert 'output byte budget' in summary['segments'][0]['error']
    assert sum(p.stat().st_size for p in directory.rglob('*') if p.is_file()) <= 2*1024*1024


@pytest.mark.parametrize('failure', ['viewer', 'source-change'])
def test_late_failures_do_not_inherit_verified_status(video, tmp_path, monkeypatch, failure):
    if failure == 'viewer':
        def broken_viewer(*args):
            raise OSError('Authored test: viewer write failed')
        monkeypatch.setattr(module, 'write_viewer', broken_viewer)
    else:
        original = module.decode
        def changed_source(*args):
            result = original(*args)
            with video.open('ab') as stream:
                stream.write(b'changed')
            return result
        monkeypatch.setattr(module, 'decode', changed_source)
    receipt = module.audit_capture([video], tmp_path / 'audit', every=2, html=True)
    assert not receipt['ok'] and receipt['segments'][0]['status'] == 'failed'


def test_source_and_destination_guards(video, tmp_path):
    output = tmp_path / 'exists'
    output.mkdir()
    sentinel = output / 'keep.txt'
    sentinel.write_text('original')
    with pytest.raises(FileExistsError):
        module.audit_capture([video], output)
    assert sentinel.read_text() == 'original'
    repository = tmp_path / 'repo'
    repository.mkdir()
    (repository / '.git').write_text('gitdir: elsewhere')
    with pytest.raises(ValueError, match='inside_git'):
        module.audit_capture([video], repository / 'audit')
    linked = tmp_path / 'linked.avi'
    linked.symlink_to(video)
    assert not module.audit_capture([linked], tmp_path / 'link-audit')['ok']
    with pytest.raises(ValueError, match='Duplicate'):
        module.audit_capture([video, video], tmp_path / 'duplicate')


@pytest.mark.parametrize('params', [
    {'every': True}, {'every': -1}, {'html': True}, {'timeout': float('nan')},
    {'timeout': True}, {'timeout': 0}, {'max_frames': 0}, {'max_output_bytes': 1},
])
def test_invalid_budgets_rejected_before_output(video, tmp_path, params):
    with pytest.raises(ValueError):
        module.audit_capture([video], tmp_path / 'audit', **params)
    assert not (tmp_path / 'audit').exists()


def test_bounded_process_timeout_and_output_limit(tmp_path):
    with pytest.raises(module.VerificationError, match='host seconds'):
        module.run_checked([sys.executable, '-c', 'import time; time.sleep(10)'],
                           timeout=0.05, max_bytes=4096)
    with pytest.raises(module.VerificationError, match='byte budget'):
        module.run_checked([sys.executable, '-c', 'print("x"*100000)'],
                           timeout=5, max_bytes=1024)
