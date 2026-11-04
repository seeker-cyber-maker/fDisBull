"""Independent authored MVE boundary tests, without original-game payloads.

These test offline guarantees only. Original native playback has a separate
private evidence gate; a modern reader agreeing is not a native-player claim.
"""
import os
from contextlib import contextmanager
from pathlib import Path
import shutil
import struct
import subprocess
import time

import pytest

from fdisbull import mve


def _op(code, body=b'', version=0):
    return struct.pack('<HBB', len(body), code, version) + body


def _chunk(kind, *ops):
    body = b''.join(ops)
    return struct.pack('<HH', len(body), kind) + body


def _authored_movie(codec):
    # Two full, independent tiles per frame; no copied game bytes.
    palette = b''.join(bytes((n % 64, (n // 4) % 64, 0)) for n in range(256))
    parts = [mve.HEADER,
        _chunk(2, _op(10, struct.pack('<3H', 16, 8, 19)),
               _op(5, struct.pack('<3H', 2, 1, 1), 1),
               _op(12, struct.pack('<HH', 0, 256) + palette), _op(1)),
        _chunk(0, _op(3, struct.pack('<4H', 0, 0, 11025, 1024)),
               _op(2, struct.pack('<IH', 40000, 1)), _op(1))]
    for i in range(12):
        head = struct.pack('<7H', i + 1, 0, 0, 0, 2, 1, 0)
        tiles = bytes([i * 7]) * 64 + bytes([255 - i * 11]) * 64
        video = ([_op(6, head + bytes(4) + tiles)] if codec == 6 else
                 [_op(14, b'\xff\xff'), _op(15, bytes(4)), _op(16, head + tiles)])
        parts.append(_chunk(3,
            _op(8, struct.pack('<3H', i, 1, 4) + bytes((i, 127, 128, 255 - i))),
            _op(9, struct.pack('<3H', i, 0xfffe, 4)), *video, _op(4),
            _op(7, struct.pack('<3H', 0, 256, 0), 1), _op(1)))
    return b''.join([*parts, _chunk(4, _op(0), _op(1)), _chunk(5)])


def _walk(data):
    """Separate extent walker used for expected container invariants."""
    result, pos = [], 26
    while pos < len(data):
        start = pos
        size, kind = struct.unpack_from('<HH', data, pos)
        pos += 4
        stop = pos + size
        ops = []
        while pos < stop:
            amount, code, version = struct.unpack_from('<HBB', data, pos)
            encoded = data[pos:pos + amount + 4]
            ops.append((code, version, encoded))
            pos += amount + 4
        assert pos == stop
        result.append((kind, size, ops, data[start:stop]))
    assert pos == len(data)
    return result


def _private(tmp_path):
    parent = tmp_path / 'private'
    parent.mkdir(mode=0o700)
    return parent


def _reader():
    executable = shutil.which('ffmpeg')
    if not executable:
        pytest.skip('Independent FFmpeg reader unavailable')
    return executable


def _raw_video(path):
    return subprocess.run([_reader(), '-nostdin', '-v', 'error', '-threads', '1',
        '-f', 'ipmovie', '-i', str(path), '-an', '-fps_mode', 'passthrough',
        '-pix_fmt', 'pal8', '-f', 'rawvideo', 'pipe:1'], check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10).stdout


@pytest.mark.parametrize('codec', [6, 16])
def test_original_codec_tail_controls_pcm_and_pixel_boundaries(tmp_path, codec):
    parent = _private(tmp_path)
    source = parent / 'authored.mve'
    original = _authored_movie(codec)
    source.write_bytes(original)
    report = mve.frame_mve(source, parent / 'result', keep_frames=2, ffmpeg=_reader())
    framed_path = parent / 'result/framed.mve'
    framed = framed_path.read_bytes()
    before, after = _walk(original), _walk(framed)
    assert source.read_bytes() == original
    assert len(before) == len(after)
    assert max(c[1] for c in after) <= max(c[1] for c in before)
    # The final two frame chunks and both shutdown chunks are exact originals.
    assert [c[3] for c in before[-4:]] == [c[3] for c in after[-4:]]
    visual = {6, 14, 15, 16}
    for left, right in zip(before, after):
        assert left[0] == right[0]
        assert [o for o in left[2] if o[0] not in visual] == [o for o in right[2] if o[0] not in visual]
    source_video_codes = [o[0] for c in before for o in c[2] if o[0] in (6, 16)]
    target_video_codes = [o[0] for c in after for o in c[2] if o[0] in (6, 16)]
    assert source_video_codes == target_video_codes == [codec] * 12
    original_pixels, framed_pixels = _raw_video(source), _raw_video(framed_path)
    frame_size = 16 * 8 + 1024
    assert len(original_pixels) == len(framed_pixels) == frame_size * 12
    assert original_pixels[:2 * frame_size] == framed_pixels[:2 * frame_size]
    assert original_pixels[-2 * frame_size:] == framed_pixels[-2 * frame_size:]
    held = original_pixels[frame_size:2 * frame_size]
    assert all(framed_pixels[i * frame_size:(i + 1) * frame_size] == held for i in range(2, 10))
    assert report['native_runtime_tested'] is False
    assert report['original_packet_tail_frames'] == 2


def test_complete_pcm_mismatch_refuses_and_removes_temporary_files(tmp_path, monkeypatch):
    parent = _private(tmp_path)
    source = parent / 'authored.mve'
    original = _authored_movie(6)
    source.write_bytes(original)
    pcm = mve._pcm
    def mismatch(path, *args):
        result = pcm(path, *args)
        return {**result, 'pcm_sha256': '0' * 64} if Path(path).name == 'framed.mve' else result
    monkeypatch.setattr(mve, '_pcm', mismatch)
    with pytest.raises(ValueError, match='audio PCM mismatch'):
        mve.frame_mve(source, parent / 'refused', keep_frames=2, ffmpeg=_reader())
    assert source.read_bytes() == original
    assert not (parent / 'refused').exists()
    assert not list(parent.glob('.mve-check-*'))


def test_partial_publication_failure_removes_owned_output(tmp_path, monkeypatch):
    parent = _private(tmp_path)
    source = parent / 'authored.mve'
    original = _authored_movie(6)
    source.write_bytes(original)
    open_file = Path.open
    def refused_manifest(path, *args, **kwargs):
        if path.name == 'mve-manifest.json':
            raise OSError('authored publication failure')
        return open_file(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', refused_manifest)
    with pytest.raises(OSError, match='authored publication failure'):
        mve.frame_mve(source, parent / 'refused', keep_frames=2, ffmpeg=_reader())
    assert source.read_bytes() == original
    assert not (parent / 'refused').exists()
    assert not list(parent.glob('.mve-check-*'))


def test_deadline_expiring_at_final_source_check_refuses_publication(tmp_path, monkeypatch):
    parent = _private(tmp_path)
    source = parent / 'authored.mve'
    original = _authored_movie(6)
    source.write_bytes(original)
    snapshot, clock = mve._snapshot, time.monotonic
    calls, elapsed = [], [0]
    def delayed_final_snapshot(path, limit):
        value = snapshot(path, limit)
        calls.append(None)
        if len(calls) == 2:
            # A monotonic jump models a final regular-file read which returns
            # after the overall deadline, without slowing the test itself.
            elapsed[0] = 120
        return value
    monkeypatch.setattr(mve, '_snapshot', delayed_final_snapshot)
    monkeypatch.setattr(mve.time, 'monotonic', lambda: clock() + elapsed[0])
    with pytest.raises(ValueError, match='deadline'):
        mve.frame_mve(source, parent / 'refused', keep_frames=2, ffmpeg=_reader(), timeout=60)
    assert len(calls) == 2
    assert source.read_bytes() == original
    assert not (parent / 'refused').exists()
    assert not list(parent.glob('.mve-check-*'))


@pytest.mark.parametrize('filename', ['framed.mve', 'mve-manifest.json'])
def test_deadline_expiring_during_publication_removes_owned_output(tmp_path, monkeypatch, filename):
    parent = _private(tmp_path)
    source = parent / 'authored.mve'
    original = _authored_movie(6)
    source.write_bytes(original)
    open_file, clock = Path.open, time.monotonic
    elapsed = [0]
    @contextmanager
    def slow_write(path, *args, **kwargs):
        with open_file(path, *args, **kwargs) as stream:
            yield stream
        if path.parent == parent / 'refused' and path.name == filename:
            elapsed[0] = 120
    monkeypatch.setattr(Path, 'open', slow_write)
    monkeypatch.setattr(mve.time, 'monotonic', lambda: clock() + elapsed[0])
    with pytest.raises(ValueError, match='deadline'):
        mve.frame_mve(source, parent / 'refused', keep_frames=2, ffmpeg=_reader(), timeout=60)
    assert source.read_bytes() == original
    assert not (parent / 'refused').exists()
    assert not list(parent.glob('.mve-check-*'))


@pytest.mark.parametrize('kind', ['diagnostics', 'output', 'cancellation'])
def test_reader_budget_and_early_cancel_reap_owned_process(tmp_path, monkeypatch, kind):
    parent = _private(tmp_path)
    pidfile = parent / 'owned.pid'
    executable = parent / 'authored-reader'
    program = ('#!/usr/bin/env python3\nimport os,time\n'
               f'open({str(pidfile)!r}, "w").write(str(os.getpid()))\n')
    if kind == 'diagnostics':
        program += 'os.write(2, b"e" * 20000)\ntime.sleep(10)\n'
    elif kind == 'output':
        monkeypatch.setattr(mve, 'MAX_DECODED', 64)
        program += 'os.write(1, b"v" * 65)\ntime.sleep(10)\n'
    else:
        program += 'os.write(1, b"v")\ntime.sleep(10)\n'
    executable.write_text(program)
    executable.chmod(0o700)
    stream = mve._decoded(parent / 'unused', str(executable), [], time.monotonic() + 3)
    if kind == 'cancellation':
        assert next(stream) == b'v'
        stream.close()
    else:
        with pytest.raises(ValueError, match=f'{"diagnostic" if kind == "diagnostics" else "output"} budget'):
            list(stream)
    assert pidfile.exists()
    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), 0)
