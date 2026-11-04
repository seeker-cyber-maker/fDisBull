"""Authored SMK2 containers only; no licensed movies or game bytes."""
import hashlib
import json
from pathlib import Path
import shutil
import struct

import pytest

from fdisbull.smacker import frame_smk, inspect_smk


def authored_smk(frames=32):
    # Independent tiny constant trees: singleton byte trees supply each word;
    # the bigtree has one constant leaf and the decoder supplies cache leaves.
    # Video TYPE=3 fills one 4x4 block with palette index zero. Every input
    # frame has an intentionally redundant full palette, giving framing room.
    bits = []

    def number(value, count):
        bits.extend((value >> i) & 1 for i in range(count))

    for word in (0, 0, 0, 3):
        bits.append(1)
        for byte in (word & 255, word >> 8):
            bits.extend((1, 0))
            number(byte, 8)
            bits.append(0)
        for escape in (65535, 65534, 65533):
            number(escape, 16)
        bits.extend((0, 0))
    trees = bytearray((len(bits) + 7) // 8)
    for index, value in enumerate(bits):
        trees[index // 8] |= value << (index % 8)
    palette = bytes([193, 63, 0, 0]) + bytes(255 * 3 + 3)
    packet = palette + bytes(4)
    header = bytearray(104)
    header[:4] = b'SMK2'
    struct.pack_into('<IIIiI', header, 4, 4, 4, frames, 100, 0)
    struct.pack_into('<5I', header, 52, len(trees), 16, 16, 16, 16)
    return (bytes(header) + struct.pack('<' + 'I' * frames, *([len(packet)] * frames))
            + bytes([1]) * frames + bytes(trees) + packet * frames)


def source_file(tmp_path):
    path = tmp_path / 'authored.smk'
    path.write_bytes(authored_smk())
    return path


def require_decoders():
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('Independent FFmpeg/ffprobe unavailable')


def test_structure_ranges_identity_and_no_payload(tmp_path):
    path = source_file(tmp_path)
    result = inspect_smk(path)
    assert result['logical_frames'] == result['physical_frames'] == 32
    assert (result['width'], result['height']) == (4, 4)
    assert result['palette_packets'] == 32
    assert result['audio_tracks'] == []
    assert result['source']['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result['qualification'] == 'container-structure-only'
    assert result['input_executed'] is False
    assert result['frame_size_table'] == {'offset': 104, 'bytes': 128}
    assert result['frame_type_table'] == {'offset': 232, 'bytes': 32}
    # Public metadata is JSON and contains no raw tree/frame/palette buffers.
    assert isinstance(json.dumps(result), str)
    assert 'data_base64' not in json.dumps(result)


@pytest.mark.parametrize('change,match', [
    (lambda b: b[:3], 'header'),
    (lambda b: b'SMK4' + b[4:], 'SMK4'),
    (lambda b: b[:20] + struct.pack('<I', 1) + b[24:], 'flags'),
    (lambda b: b[:4] + struct.pack('<I', 6) + b[8:], 'geometry'),
    (lambda b: b[:12] + bytes(4) + b[16:], 'frame count'),
    (lambda b: b[:12] + struct.pack('<I', 10001) + b[16:], 'frame count'),
    (lambda b: b[:52] + struct.pack('<I', 0xFFFFFFFF) + b[56:], 'Truncated'),
    (lambda b: b[:104] + struct.pack('<I', 0x7FFFFFFC) + b[108:], 'extent'),
    (lambda b: b[:-10], 'truncated'),
    (lambda b: b + b'junk', 'trailer'),
])
def test_malformed_or_unsupported_refused(tmp_path, change, match):
    path = tmp_path / 'bad.smk'
    path.write_bytes(change(authored_smk()))
    with pytest.raises(ValueError, match=match):
        inspect_smk(path)


def test_audio_chunk_boundary_refused(tmp_path):
    raw = bytearray(authored_smk())
    # Replace first frame's palette flag with audio-track0 present, then declare
    # a chunk which cannot fit into that frame. Other tables remain intact.
    raw[104 + 4 * 32] = 2
    struct.pack_into('<I', raw, 72, 0x60000000 | 8000)
    start = 104 + 5 * 32 + struct.unpack_from('<I', raw, 52)[0]
    struct.pack_into('<I', raw, start, 0xFFFFFFFC)
    path = tmp_path / 'bad.smk'
    path.write_bytes(raw)
    with pytest.raises(ValueError, match='audio chunk'):
        inspect_smk(path)


def test_source_symlink_and_bounded_snapshot(tmp_path, monkeypatch):
    path = source_file(tmp_path)
    link = tmp_path / 'link'
    link.symlink_to(path)
    with pytest.raises(ValueError, match='symlink'):
        inspect_smk(link)
    import fdisbull.smacker as module
    monkeypatch.setattr(module, 'MAX_SOURCE', 20)
    with pytest.raises(ValueError, match='size limit'):
        inspect_smk(path)


def test_missing_decoder_and_invalid_options_leave_no_output(tmp_path):
    path = source_file(tmp_path)
    out = tmp_path / 'new'
    with pytest.raises(ValueError, match='unavailable'):
        frame_smk(path, out, ffmpeg='fdisbull-no-such-decoder')
    for options in ({'keep_frames': 0}, {'keep_frames': True}, {'keep_frames': 65},
                    {'max_output_bytes': True}, {'max_output_bytes': 0},
                    {'timeout': 0}, {'timeout': float('inf')}):
        with pytest.raises(ValueError):
            frame_smk(path, out, **options)
    assert not out.exists()


def test_output_boundary_guards(tmp_path):
    path = source_file(tmp_path)
    existing = tmp_path / 'existing'
    existing.mkdir()
    (existing / 'sentinel').write_text('preserve')
    with pytest.raises(FileExistsError):
        frame_smk(path, existing)
    assert (existing / 'sentinel').read_text() == 'preserve'
    link = tmp_path / 'linked'
    link.symlink_to(existing, target_is_directory=True)
    with pytest.raises(FileExistsError):
        frame_smk(path, link)
    repo = tmp_path / 'repo'
    repo.mkdir(mode=0o700)
    (repo / '.git').write_text('gitdir: irrelevant')
    with pytest.raises(ValueError, match='inside_git'):
        frame_smk(path, repo / 'out')
    public = tmp_path / 'public'
    public.mkdir(mode=0o755)
    public.chmod(0o755)
    with pytest.raises(ValueError, match='not_private'):
        frame_smk(path, public / 'out')
    parent_link = tmp_path / 'parent-link'
    parent_link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match='unsafe_path'):
        frame_smk(path, parent_link / 'out')


def test_independent_decoder_and_new_private_output(tmp_path):
    require_decoders()
    path = source_file(tmp_path)
    before = path.read_bytes()
    out = tmp_path / 'framed'
    receipt = frame_smk(path, out, keep_frames=1)
    assert path.read_bytes() == before
    assert receipt['saved_bytes'] > 0
    assert receipt['logical_frames'] == 32
    assert receipt['retained_frame_indices'] == [0, 31]
    assert receipt['native_hold_frames'] == 30
    expected_palette = bytes([0, 0, 255, 255]) + bytes([0, 0, 0, 255]) * 255
    expected_frame_hash = hashlib.sha256(bytes(16) + expected_palette).hexdigest()
    assert receipt['retained_pal8_sha256'] == {'0': expected_frame_hash, '31': expected_frame_hash}
    assert receipt['all_retained_images_and_palettes_exact']
    assert receipt['compressed_audio_packets_byte_identical']
    assert receipt['native_game_playback'] == 'not_run'
    assert receipt['duration_changed'] is False
    assert receipt['decoder_max_allocation_bytes'] == 67108864
    assert json.loads((out / 'smk-manifest.json').read_text()) == receipt
    framed_info = inspect_smk(out / 'framed.smk')
    assert framed_info['logical_frames'] == 32
    # Real unused bigtrees contain one literal plus three cache leaves:
    # seven initialized four-byte nodes; no spare/uninitialized allocation.
    assert framed_info['huffman_trees']['decoded_allocation_bytes'][:2] == [28, 28]
    assert (out.stat().st_mode & 0o777) == 0o700
    assert all((f.stat().st_mode & 0o777) == 0o600 for f in out.iterdir())
    assert set(f.name for f in out.iterdir()) == {'framed.smk', 'smk-manifest.json'}


def test_budget_refusal_creates_no_partial_media(tmp_path):
    require_decoders()
    path = source_file(tmp_path)
    out = tmp_path / 'too-small'
    with pytest.raises(ValueError, match='budget'):
        frame_smk(path, out, keep_frames=1, max_output_bytes=100)
    assert not out.exists()


@pytest.mark.parametrize('track', [0, 6])
def test_audio_rate_header_words_start_at_offset_72(tmp_path, track):
    raw = bytearray(authored_smk())
    size = struct.unpack_from('<I', raw, 104)[0]
    start = 104 + 5 * 32 + struct.unpack_from('<I', raw, 52)[0]
    struct.pack_into('<I', raw, 104, size + 8)
    raw[104 + 4 * 32] |= 2 << track
    word = 0x60000000 | (8000 + track * 1000)
    struct.pack_into('<I', raw, 72 + track * 4, word)
    struct.pack_into('<I', raw, 100, 0xA5A5A5A5)  # final reserved word, not AudioRate6
    palette_end = start + 772
    raw[palette_end:palette_end] = struct.pack('<I', 8) + bytes(4)
    path = tmp_path / 'audio.smk'
    path.write_bytes(raw)
    result = inspect_smk(path)
    assert result['audio_tracks'] == [{'track': track, 'frame_packets': 1, 'header_word': word}]


def test_expired_deadline_never_starts_reader(monkeypatch):
    import time
    import fdisbull.smacker as module
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError('Expired operation launched a reader')
    monkeypatch.setattr(module.subprocess, 'Popen', forbidden)
    with pytest.raises(ValueError, match='timeout'):
        with module._reader(['unavailable'], b'', time.monotonic() - 1):
            pass
    assert not calls


def test_hanging_reader_is_killed_and_reaped(monkeypatch):
    import sys
    import time
    import fdisbull.smacker as module
    real = module.subprocess.Popen
    processes = []
    def recording(*args, **kwargs):
        process = real(*args, **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(module.subprocess, 'Popen', recording)
    with pytest.raises(ValueError, match='timeout'):
        with module._reader([sys.executable, '-c', 'import time; time.sleep(60)'],
                            b'authored', time.monotonic() + 0.1) as pipe:
            pipe.read(1)
    assert len(processes) == 1 and processes[0].returncode is not None
    assert all(p.closed for p in (processes[0].stdin, processes[0].stdout, processes[0].stderr))


def test_output_budget_includes_manifest(tmp_path):
    require_decoders()
    path = source_file(tmp_path)
    receipt = frame_smk(path, tmp_path / 'first', keep_frames=1)
    second = tmp_path / 'no-manifest-room'
    with pytest.raises(ValueError, match='manifest exceed'):
        frame_smk(path, second, keep_frames=1, max_output_bytes=receipt['framed']['bytes'])
    assert not second.exists()


def test_bad_huffman_payload_never_published(tmp_path):
    require_decoders()
    raw = bytearray(authored_smk())
    start = 104 + 5 * 32
    length = struct.unpack_from('<I', raw, 52)[0]
    raw[start:start + length] = bytes(length)
    path = tmp_path / 'bad-trees.smk'
    path.write_bytes(raw)
    # Structural inspection deliberately does not certify codec semantics.
    assert inspect_smk(path)['qualification'] == 'container-structure-only'
    output = tmp_path / 'refused'
    with pytest.raises(ValueError):
        frame_smk(path, output, keep_frames=1)
    assert not output.exists()


def test_both_libav_readers_have_a_single_allocation_limit():
    from fdisbull.smacker import _command
    for reader in ('ffmpeg', 'ffprobe'):
        command = _command(reader, '-of', 'json')
        assert command[:3] == [reader, '-max_alloc', '67108864']
        assert command.index('-max_alloc') < command.index('-i')
        assert command[command.index('-protocol_whitelist') + 1] == 'pipe'


def authored_audio_smk(*, track=0, word=0x60000000 | 8000):
    raw = bytearray(authored_smk())
    start = 104 + 5 * 32 + struct.unpack_from('<I', raw, 52)[0]
    struct.pack_into('<I', raw, 104, struct.unpack_from('<I', raw, 104)[0] + 8)
    raw[104 + 4 * 32] |= 2 << track
    struct.pack_into('<I', raw, 72 + track * 4, word)
    pcm = struct.pack('<hh', 123, -456)
    raw[start + 772:start + 772] = struct.pack('<I', 8) + pcm
    return bytes(raw), pcm


def test_undeclared_audio_packet_fails_before_decoder_or_output(tmp_path):
    from fdisbull.smacker import _SMK
    raw, _ = authored_audio_smk(word=0)
    with pytest.raises(ValueError, match='undeclared audio track'):
        _SMK(raw)
    path = tmp_path / 'unreferenced-audio.smk'
    path.write_bytes(raw)
    with pytest.raises(ValueError, match='undeclared audio track'):
        inspect_smk(path)
    require_decoders()
    with pytest.raises(ValueError, match='undeclared audio track'):
        frame_smk(path, tmp_path / 'refused', keep_frames=1)
    assert not (tmp_path / 'refused').exists()


@pytest.mark.parametrize('word', [0x60000000, 8000, 0x68000000 | 8000, 0x60000000 | 192001])
def test_incoherent_or_unsupported_audio_headers_refuse(word):
    from fdisbull.smacker import _SMK
    raw, _ = authored_audio_smk(word=word)
    with pytest.raises(ValueError, match='audio'):
        _SMK(raw)


@pytest.mark.parametrize('change', [
    lambda streams: [],
    lambda streams: streams + [dict(streams[0], index=2)],
    lambda streams: [dict(streams[0], codec_name='smackaudio')],
    lambda streams: [dict(streams[0], channels=2)],
    lambda streams: [dict(streams[0], sample_rate='22050')],
    lambda streams: [dict(streams[0], index=2)],
])
def test_independent_audio_stream_coverage_must_match_declared_header(change):
    from fdisbull.smacker import _SMK, _audio_coverage
    raw, _ = authored_audio_smk(track=6)
    smk = _SMK(raw)
    streams = [dict(index=1, codec_type='audio', codec_name='pcm_s16le', channels=1, sample_rate='8000')]
    assert _audio_coverage(smk, streams)[0]['source_track'] == 6
    with pytest.raises(ValueError, match='audio'):
        _audio_coverage(smk, change(streams))


def test_independent_complete_pcm_of_authored_audio_track(tmp_path):
    require_decoders()
    raw, pcm = authored_audio_smk(track=6)
    path = tmp_path / 'authored-audio.smk'
    path.write_bytes(raw)
    result = frame_smk(path, tmp_path / 'framed-audio', keep_frames=1)
    assert len(result['audio']) == 1
    audio = result['audio'][0]
    assert audio['source_track'] == 6 and audio['stream_index'] == 1
    assert audio['codec_name'] == 'pcm_s16le'
    assert audio['pcm_bytes'] == len(pcm) and audio['samples_per_channel'] == 2
    assert audio['pcm_sha256'] == hashlib.sha256(pcm).hexdigest()
    assert audio['exact_pcm_match'] is True
    assert path.read_bytes() == raw
