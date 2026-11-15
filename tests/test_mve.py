"""Authored old-profile MVE examples: no game-derived media bytes."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct

import pytest

from fdisbull import mve


def operation(code, data=b'', version=0):
    return struct.pack('<HBB', len(data), code, version) + data


def chunk(kind, *operations):
    data = b''.join(operations)
    return struct.pack('<HH', len(data), kind) + data


def fixture_movie(*, frames=8, width=16, height=16, sample_rate=11025,
                  video_version=1, video_opcode=6):
    """Independent raw-tile samples described by the public old-MVE layout."""
    palette = bytes(channel for i in range(256) for channel in (i % 64, (i // 4) % 64, 0))
    video_init = struct.pack('<3H', width // 8, height // 8, 1)
    if video_version == 2:
        video_init += b'\0\0'
    result = bytearray(mve.HEADER)
    result.extend(chunk(2, operation(10, struct.pack('<3H', width, height, 19)),
                        operation(5, video_init, video_version),
                        operation(12, struct.pack('<HH', 0, 256) + palette), operation(1)))
    result.extend(chunk(0, operation(3, struct.pack('<4H', 0, 0, sample_rate, 4096)),
                        operation(2, struct.pack('<IH', 100000, 1)), operation(1)))
    for frame in range(frames):
        header = struct.pack('<7H', frame + 1, 0, 0, 0, width // 8, height // 8, 0)
        tiles = b''.join(bytes([(frame * 13 + block * 3) % 256]) * 64
                         for block in range(width * height // 64))
        video = header + b'\0\0' * (width * height // 64) + tiles
        result.extend(chunk(3, operation(8, struct.pack('<3H', frame, 1, 16) +
                                            bytes((frame + i) % 256 for i in range(16))),
                            operation(9, struct.pack('<3H', frame, 0xfffe, 16)),
                            operation(video_opcode, video), operation(4),
                            operation(7, struct.pack('<3H', 0, 256, 0), 1), operation(1)))
    result.extend(chunk(4, operation(0), operation(1)))
    result.extend(chunk(5))
    return bytes(result)


def positions(data, code):
    p = 26
    result = []
    while p < len(data):
        n, _ = struct.unpack_from('<HH', data, p)
        p += 4
        end = p + n
        while p < end:
            n, opcode, _ = struct.unpack_from('<HBB', data, p)
            if opcode == code:
                result.append(p)
            p += 4 + n
    return result


def private_parent(tmp_path):
    parent = tmp_path / 'private'
    parent.mkdir(mode=0o700)
    return parent


def decoder_required():
    if not shutil.which('ffmpeg'):
        pytest.skip('Independent FFmpeg reader is not installed')


def test_inspection_reports_fixed_geometry_timing_pcm_and_scope():
    data = fixture_movie(sample_rate=10989)
    report = mve.inspect_mve_bytes(data)
    assert report['source'] == {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    assert (report['width'], report['height'], report['logical_frames']) == (16, 16, 8)
    assert report['frame_microseconds'] == 100000
    assert report['duration_microseconds'] == 800000
    assert report['audio'] == dict(codec='pcm_u8', channels=1, sample_rate=10989,
                                    packet_count=8, pcm_bytes=128)
    assert report['writer_supported']
    assert not report['full_decode']
    assert not report['input_executed']
    assert not report['source_modified']
    assert not report['native_runtime_tested']
    assert 'payload' not in report
    assert data.hex() not in json.dumps(report)


def test_video_v2_mono_profile_is_structurally_accepted():
    assert mve.inspect_mve_bytes(fixture_movie(video_version=2))['logical_frames'] == 8


@pytest.mark.parametrize('cut', [0, 1, 19, 25, 26, 29, -1, -2, -4, -9, -13])
def test_truncated_inputs_are_refused(cut):
    with pytest.raises(ValueError):
        mve.inspect_mve_bytes(fixture_movie()[:cut])


def test_signature_and_later_codec_are_explicit_refusals():
    with pytest.raises(ValueError, match='signature'):
        mve.inspect_mve_bytes(b'?' + fixture_movie()[1:])
    with pytest.raises(ValueError, match='operation/version'):
        mve.inspect_mve_bytes(fixture_movie(video_opcode=17))


def test_chunk_extent_cannot_reach_past_eof():
    data = bytearray(fixture_movie())
    struct.pack_into('<H', data, 26, 65535)
    with pytest.raises(ValueError, match='truncated extent'):
        mve.inspect_mve_bytes(bytes(data))


def test_operation_extent_cannot_escape_its_chunk():
    data = bytearray(fixture_movie())
    struct.pack_into('<H', data, positions(data, 10)[0], 65535)
    with pytest.raises(ValueError, match='outside its chunk'):
        mve.inspect_mve_bytes(bytes(data))


@pytest.mark.parametrize('opcode,byte_offset,replacement,reason', [
    (3, 6, b'\x01\x00', 'unsigned-8 mono'),
    (5, 8, b'\x02\x00', 'extra-buffer'),
    (2, 4, b'\0\0\0\0', 'timer'),
    (6, 8, b'\x01\x00', 'subrectangle'),
    (8, 6, b'\x02\x00', 'stream mask'),
    (9, 6, b'\x01\x00', 'silence'),
    (12, 8, b'\x40', 'palette depth'),
])
def test_profile_changes_are_refused(opcode, byte_offset, replacement, reason):
    data = bytearray(fixture_movie())
    p = positions(data, opcode)[0] + byte_offset
    data[p:p + len(replacement)] = replacement
    with pytest.raises(ValueError, match=reason):
        mve.inspect_mve_bytes(bytes(data))


def test_missing_audio_initialization_is_not_silently_inferred():
    data = bytearray(fixture_movie())
    p = positions(data, 3)[0]
    data[p + 2] = 12
    with pytest.raises(ValueError):
        mve.inspect_mve_bytes(bytes(data))


def test_inspection_accepts_regular_file_and_refuses_file_link(tmp_path):
    source = tmp_path / 'original.mve'
    source.write_bytes(fixture_movie())
    assert mve.inspect_mve(source)['logical_frames'] == 8
    link = tmp_path / 'alias.mve'
    link.symlink_to(source)
    with pytest.raises(ValueError, match='symlink'):
        mve.inspect_mve(link)


@pytest.mark.parametrize('argument,value', [
    ('keep_frames', 0), ('keep_frames', 65), ('keep_frames', True),
    ('max_output_bytes', 0), ('max_output_bytes', mve.MAX_OUTPUT + 1),
    ('max_output_bytes', True), ('timeout', 0), ('timeout', 601),
    ('timeout', float('nan')), ('timeout', True),
])
def test_typed_budgets_refuse_before_output(tmp_path, argument, value):
    output = tmp_path / 'absent'
    with pytest.raises(ValueError):
        mve.frame_mve(tmp_path / 'missing.mve', output, **{argument: value})
    assert not output.exists()


def test_existing_output_and_output_link_are_not_touched(tmp_path):
    source = tmp_path / 'source.mve'
    source.write_bytes(fixture_movie())
    output = tmp_path / 'existing'
    output.mkdir()
    sentinel = output / 'sentinel'
    sentinel.write_text('keep')
    with pytest.raises(FileExistsError):
        mve.frame_mve(source, output)
    link = tmp_path / 'link'
    link.symlink_to(output)
    with pytest.raises(FileExistsError):
        mve.frame_mve(source, link)
    assert sentinel.read_text() == 'keep'


def test_nonprivate_and_git_outputs_are_refused(tmp_path):
    parent = tmp_path / 'public'
    parent.mkdir(mode=0o755)
    with pytest.raises(ValueError):
        mve.frame_mve(tmp_path / 'absent', parent / 'new')
    parent.chmod(0o700)
    (parent / '.git').mkdir()
    with pytest.raises(ValueError):
        mve.frame_mve(tmp_path / 'absent', parent / 'new')


def test_missing_decoder_creates_no_output(tmp_path):
    parent = private_parent(tmp_path)
    with pytest.raises(ValueError, match='decoder is unavailable'):
        mve.frame_mve(tmp_path / 'absent', parent / 'new', ffmpeg='nonexistent-mve-decoder')
    assert not (parent / 'new').exists()


def test_short_movie_has_no_frame_interval_and_no_output(tmp_path):
    decoder_required()
    parent = private_parent(tmp_path)
    source = parent / 'short.mve'
    source.write_bytes(fixture_movie(frames=2))
    with pytest.raises(ValueError, match='no intermediate'):
        mve.frame_mve(source, parent / 'new', keep_frames=1)
    assert not (parent / 'new').exists()


def test_old06_full_decode_framing_pcm_and_prefix_final_images(tmp_path):
    decoder_required()
    parent = private_parent(tmp_path)
    source = parent / 'source.mve'
    data = fixture_movie()
    source.write_bytes(data)
    output = parent / 'framed'
    report = mve.frame_mve(source, output, keep_frames=2)
    assert source.read_bytes() == data
    assert report['retained_frame_indices'] == [0, 1, 6, 7]
    assert report['native_hold_packets'] == 4
    assert report['logical_frames'] == 8
    assert report['frame_microseconds'] == 100000
    assert report['all_retained_images_and_palettes_exact']
    assert report['every_pure_hold_image_and_palette_exact']
    assert report['warmup_frame_range'] is None
    assert report['pure_hold_frame_range'] == [2, 5]
    assert report['codec_family_preserved']
    assert report['video_codec_opcode'] == 6
    assert report['maximum_framed_chunk_payload_bytes'] <= report['maximum_source_chunk_payload_bytes']
    assert len(report['decoded_frame_pal8_sha256']) == 8
    assert report['audio']['exact_pcm_match']
    assert report['audio']['pcm_bytes'] == 128
    assert not report['native_runtime_tested']
    assert not report['source_modified']
    assert report['saved_bytes'] > 0
    assert json.loads((output / 'mve-manifest.json').read_text()) == report
    framed = mve.inspect_mve(output / 'framed.mve')
    assert framed['logical_frames'] == 8
    assert framed['source']['sha256'] == report['framed']['sha256']
    assert (output / 'framed.mve').stat().st_mode & 0o777 == 0o600


def test_output_budget_counts_manifest_and_no_partial_output(tmp_path):
    decoder_required()
    parent = private_parent(tmp_path)
    source = parent / 'source.mve'
    source.write_bytes(fixture_movie())
    with pytest.raises(ValueError, match='budget'):
        mve.frame_mve(source, parent / 'new', keep_frames=1, max_output_bytes=256)
    assert not (parent / 'new').exists()
    assert not list(parent.glob('.mve-check-*'))


def test_source_change_during_decode_refuses_publication(tmp_path, monkeypatch):
    decoder_required()
    parent = private_parent(tmp_path)
    source = parent / 'source.mve'
    data = fixture_movie()
    source.write_bytes(data)
    reads = []
    original = mve._snapshot
    def snapshot(path, limit):
        value = original(path, limit)
        reads.append(None)
        return value if len(reads) == 1 else value + b'changed'
    monkeypatch.setattr(mve, '_snapshot', snapshot)
    with pytest.raises(ValueError, match='source changed'):
        mve.frame_mve(source, parent / 'new', keep_frames=1)
    assert source.read_bytes() == data
    assert not (parent / 'new').exists()


def test_tail_search_has_explicit_deterministic_nonoverlap_and_work_bounds():
    assert mve._tail_candidates(1571, 32) == (32, 64, 128, 256, 512)
    assert mve._tail_candidates(141, 32) == (32, 64, 108)
    assert max(mve._tail_candidates(20000, 1)) == mve.MAX_TAIL_FRAMES
    assert not mve._tail_candidates(2, 1)


def test_valid_incremental_source_with_unrepresentable_endpoint_refuses(tmp_path):
    decoder_required()
    parent = private_parent(tmp_path)
    width, height = 320, 200
    result = bytearray(fixture_movie(frames=0, width=width, height=height)[:-16])
    # Start with a black keyframe, using one literal per row and same-frame
    # backward references. Then update 250 distinct tiles per frame. Every
    # original operation fits, but the final independent endpoint does not.
    for frame in range(5):
        codes = []
        raw = bytearray()
        for block in range(1000):
            if frame == 0:
                column = block % 40
                codes.append(0 if column == 0 else 0x4000 - column * 8)
                if column == 0:
                    raw.extend(bytes(64))
            elif (frame - 1) * 250 <= block < frame * 250:
                codes.append(0)
                raw.extend(bytes([block & 255, block >> 8]) * 32)
            else:
                codes.append(0xc000)
        payload = struct.pack('<7H', frame + 1, 0, 0, 0, 40, 25, 0)
        payload += struct.pack('<1000H', *codes) + raw
        result.extend(chunk(3, operation(8, struct.pack('<3H', frame, 1, 16) + bytes(16)),
                            operation(9, struct.pack('<3H', frame, 0xfffe, 16)),
                            operation(6, payload), operation(4),
                            operation(7, struct.pack('<3H', 0, 256, 0), 1), operation(1)))
    result.extend(chunk(4, operation(0), operation(1)))
    result.extend(chunk(5))
    source = parent / 'complex-endpoint.mve'
    source.write_bytes(result)
    assert mve.inspect_mve(source)['logical_frames'] == 5
    with pytest.raises(ValueError, match='No bounded original MVE tail'):
        mve.frame_mve(source, parent / 'refused', keep_frames=1)
    assert not (parent / 'refused').exists()


def test_decoder_deadline_terminates_owned_process_and_leaves_no_output(tmp_path):
    parent = private_parent(tmp_path)
    source = parent / 'source.mve'
    source.write_bytes(fixture_movie())
    pidfile = parent / 'reader.pid'
    reader = parent / 'sleeping-decoder'
    reader.write_text('#!/usr/bin/env python3\nimport os,time\n'
                      f'open({str(pidfile)!r},"w").write(str(os.getpid()))\n'
                      'time.sleep(10)\n')
    reader.chmod(0o700)
    with pytest.raises(ValueError, match='deadline'):
        mve.frame_mve(source, parent / 'refused', keep_frames=1, ffmpeg=reader, timeout=0.5)
    assert not (parent / 'refused').exists()
    assert not list(parent.glob('.mve-check-*'))
    if pidfile.exists():
        with pytest.raises(ProcessLookupError):
            os.kill(int(pidfile.read_text()), 0)


def test_source_bytes_are_not_returned_in_report():
    data = fixture_movie()
    report = mve.inspect_mve_bytes(data)
    text = json.dumps(report)
    assert data.hex() not in text
    assert 'native_runtime_tested": false' in text


def old10_movie(*, mixed=False):
    """Convert authored raw tiles into the documented old10 all-changed map."""
    source = fixture_movie()
    result = bytearray(source[:26])
    pos = 26
    converted = 0
    while pos < len(source):
        amount, kind = struct.unpack_from('<HH', source, pos)
        pos += 4
        end = pos + amount
        operations = []
        while pos < end:
            amount, code, version = struct.unpack_from('<HBB', source, pos)
            pos += 4
            payload = source[pos:pos + amount]
            pos += amount
            if code == 6 and (not mixed or converted == 0):
                blocks = 4
                operations.extend([operation(14, struct.pack('<H', 0xffff)),
                                   operation(15, payload[14:14 + 2 * blocks])])
                payload = payload[:14] + payload[14 + 2 * blocks:]
                code = 16
                converted += 1
            operations.append(operation(code, payload, version))
        result.extend(chunk(kind, *operations))
    return bytes(result)


def test_mixed_codec_families_refuse_even_with_valid_packet_extents():
    with pytest.raises(ValueError, match='homogeneous'):
        mve.inspect_mve_bytes(old10_movie(mixed=True))


def test_old10_framing_never_switches_to_old06_or_synthesizes_large_endpoints(tmp_path):
    decoder_required()
    parent = private_parent(tmp_path)
    source = parent / 'source.mve'
    source.write_bytes(old10_movie())
    result = mve.frame_mve(source, parent / 'out', keep_frames=2)
    assert result['video_codec_opcode'] == 16 and result['codec_family_preserved']
    assert result['retained_frame_indices'] == [0, 1, 6, 7]
    assert result['retained_final_frames'] == result['retained_prefix_frames'] == 2
    assert result['original_packet_tail_frames'] == 2
    assert result['original_tail_packets_byte_identical']
    assert not result['chunk_payload_growth']
    assert result['maximum_framed_chunk_payload_bytes'] <= result['maximum_source_chunk_payload_bytes']
    movie = mve._MVE((parent / 'out/framed.mve').read_bytes())
    assert movie.counts['10.0'] == 8
    assert movie.counts['06.0'] == 0
    assert result['audio']['exact_pcm_match']


def test_tail_recovery_declares_nonoriginal_warmup_and_exact_last_images(tmp_path):
    decoder_required()
    parent = private_parent(tmp_path)
    result = bytearray(fixture_movie(frames=0, width=16, height=8)[:-16])
    updates = [(10, 20), (30, 40), (None, None), (50, None), (None, 60)]
    for frame, tiles in enumerate(updates):
        codes = [0 if value is not None else 0xc000 for value in tiles]
        pixels = b''.join(bytes([value]) * 64 for value in tiles if value is not None)
        payload = struct.pack('<7H', frame + 1, 0, 0, 0, 2, 1, 1)
        payload += struct.pack('<2H', *codes) + (pixels or b'\0')
        result.extend(chunk(3, operation(8, struct.pack('<3H', frame, 1, 16) + bytes(16)),
                            operation(9, struct.pack('<3H', frame, 0xfffe, 16)),
                            operation(6, payload), operation(4),
                            operation(7, struct.pack('<3H', 0, 256, 0), 1), operation(1)))
    result.extend(chunk(4, operation(0), operation(1)))
    result.extend(chunk(5))
    source = parent / 'incremental.mve'
    source.write_bytes(result)
    report = mve.frame_mve(source, parent / 'out', keep_frames=1)
    assert report['tail_search_attempts'][0]['tail_frames'] == 1
    assert report['tail_search_attempts'][0]['status'] == 'retained-image-mismatch'
    assert report['tail_search_attempts'][1] == {'tail_frames': 2, 'status': 'complete-video-verified'}
    assert report['original_packet_tail_frames'] == 2
    assert report['pure_hold_frame_range'] == [1, 2]
    assert report['warmup_frame_range'] == [3, 3]
    assert report['warmup_frames_differing_from_source'] == [3]
    assert report['retained_frame_indices'] == [0, 4]
    assert report['original_tail_packets_byte_identical']
    assert report['every_warmup_image_fully_decoded']
    assert not report['native_runtime_tested']
