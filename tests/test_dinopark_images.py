"""Authored indexed images, opacity and malformed envelopes; no game payloads."""
import hashlib
import json
import struct

import pytest

from fdisbull.dinopark_images import decode_act, decode_pic, describe_act, describe_pic, palette_rgb


def sprite(width=2, height=2, commands=b'\x42\x81\x41\0', colors=b'\0\x03\x05',
           bounds=(0, 1, 0, 1)):
    return struct.pack('<8H', width, height, *bounds, len(commands), len(colors)) + commands + colors


def act(records=None, *, magic=b'UNC2', sequences=()):
    records = [sprite()] if records is None else records
    header = 14 if magic == b'UNC2' else 10
    sequence = b''.join(struct.pack('<H', len(s)) + s for s in sequences)
    if sequences:
        sequence += b'\xa7'
    offsets, at = [], header
    for record in records:
        offsets.append(at)
        at += len(record)
    if magic == b'UNC2':
        intro = magic + struct.pack('<HIHH', len(records), at + len(sequence), len(sequences), len(sequence))
        return intro + b''.join(records) + sequence + struct.pack('<' + 'I' * len(offsets), *offsets)
    return magic + struct.pack('<HHH', len(records), len(sequences), len(sequence)) + b''.join(records) + sequence


def pic_frame(width, height, stream, *, palette=None):
    palette = bytes(i % 64 for i in range(768)) if palette is None else palette
    body = struct.pack('<HH', width, height) + palette + struct.pack('<H', len(stream)) + stream
    return struct.pack('<I', len(body)) + body


def pic(frames):
    at, offsets = 4 + 4 * len(frames), []
    for frame in frames:
        offsets.append(at)
        at += len(frame)
    return b'UNCP' + struct.pack('<' + 'I' * len(offsets), *offsets) + b''.join(frames)


@pytest.mark.parametrize('magic', [b'UNC2', b'UNCS'])
def test_actor_pixels_and_opacity_keep_opaque_zero_separate_from_transparency(magic):
    raw = act(magic=magic)
    decoded = decode_act(raw)
    frame = decoded.sprites[0]
    assert (frame.width, frame.height) == (2, 2)
    assert frame.indices == bytes([0, 3, 0, 5])
    assert frame.opacity == bytes([255, 255, 0, 255])
    assert frame.commands == b'\x42\x81\x41\0' and frame.colors == b'\0\x03\x05'
    assert decoded.directory_offset == (None if magic == b'UNCS' else 14 + len(sprite()))
    assert decoded.source_sha256 == hashlib.sha256(raw).hexdigest()


def test_actor_sequences_and_unexplained_trailer_are_preserved_but_not_interpreted():
    decoded = decode_act(act(sequences=(b'SECRET_SEQUENCE', b'abc')))
    assert decoded.sequences == (b'SECRET_SEQUENCE', b'abc')
    assert decoded.sequence_trailer == b'\xa7'
    report = describe_act(decoded)
    assert not report['sequence_semantics_decoded'] and not report['native_runtime_tested']
    encoded = json.dumps(report)
    assert 'SECRET_SEQUENCE' not in encoded and 'sequence_trailer_hex' not in report
    assert 'commands' not in report['sprites'][0] and 'colors' not in report['sprites'][0]


@pytest.mark.parametrize('commands,colors,message', [
    (b'\x42', b'\1\2', 'terminator'),
    (b'\0\0', b'', 'after ACT'),
    (b'\x43\0', b'\1\2\3', 'canvas'),
    (b'\x42\0', b'\1', 'underflow'),
    (b'\0', b'\1', 'Unconsumed'),
    (b'\x80\x80\0', b'', 'canvas'),
])
def test_actor_invalid_command_streams_are_refused(commands, colors, message):
    with pytest.raises(ValueError, match=message):
        decode_act(act([sprite(commands=commands, colors=colors)]))


def test_actor_bounds_directory_and_sequence_extents_are_checked():
    with pytest.raises(ValueError, match='bounds'):
        decode_act(act([sprite(bounds=(1, 1, 0, 1))]))
    raw = bytearray(act())
    struct.pack_into('<I', raw, len(raw) - 4, 99)
    with pytest.raises(ValueError, match='directory differs'):
        decode_act(raw)
    raw = bytearray(act(sequences=(b'abc',)))
    struct.pack_into('<H', raw, 12, 0)
    with pytest.raises(ValueError, match='sequence area'):
        decode_act(raw)
    raw = bytearray(act(sequences=(b'abc',)))
    struct.pack_into('<H', raw, 10, 0)
    with pytest.raises(ValueError, match='sequence trailer'):
        decode_act(raw)


def test_actor_aggregate_preflight_happens_before_first_pixel_decode(monkeypatch):
    import fdisbull.dinopark_images as module
    def forbidden(*args):
        raise AssertionError('Decode happened before cumulative admission')
    monkeypatch.setattr(module, '_sprite', forbidden)
    with pytest.raises(ValueError, match='pixel/work budget'):
        decode_act(act([sprite(), sprite()]), max_pixels=7)
    with pytest.raises(ValueError, match='pixel/work budget'):
        decode_act(act(), max_work=1)


def test_picture_raw_even_stride_preserves_padding_without_showing_it():
    raw = pic([pic_frame(3, 2, bytes([1, 2, 3, 99, 4, 5, 6, 98]))])
    decoded = decode_pic(raw)
    frame = decoded.frames[0]
    assert frame.stride == 4 and frame.row_data == bytes([1, 2, 3, 99, 4, 5, 6, 98])
    assert frame.indices == bytes([1, 2, 3, 4, 5, 6])
    assert frame.palette6 == bytes(i % 64 for i in range(768))
    report = describe_pic(decoded)
    assert report['full_indexed_decode'] and not report['native_runtime_tested']
    assert 'palette6' not in report['frames'][0] and 'indices' not in report['frames'][0]
    assert decoded.source_size == len(raw)


def test_picture_rle_128_means_129_repeats_and_literal_crosses_row_boundary():
    # The original profile consumes 0x80 as a 129-repeat, unlike a PackBits no-op.
    frame = decode_pic(pic([pic_frame(65, 2, b'\x80\x07\x02\x08\x09\x0a')])).frames[0]
    assert frame.row_data == b'\x07' * 129 + bytes([8, 9, 10])
    assert frame.indices == b'\x07' * 128 + bytes([8, 9])


@pytest.mark.parametrize('width,height,stream,message', [
    (3, 1, b'\1\2\3', 'even-stride'),
    (65, 1, b'\x80\7', 'run exceeds'),
    (65, 1, b'\x01\7', 'literal'),
    (65, 1, b'\xc0', 'repeat'),
    (65, 1, b'\xff\7', 'do not fill'),
])
def test_picture_invalid_row_streams_refuse(width, height, stream, message):
    with pytest.raises(ValueError, match=message):
        decode_pic(pic([pic_frame(width, height, stream)]))


def test_picture_palette_geometry_and_directory_are_qualified():
    with pytest.raises(ValueError, match='six-bit'):
        decode_pic(pic([pic_frame(2, 1, b'\1\2', palette=bytes([64]) + bytes(767))]))
    with pytest.raises(ValueError, match='geometry'):
        decode_pic(pic([pic_frame(0, 1, b'')]))
    raw = bytearray(pic([pic_frame(2, 1, b'\1\2'), pic_frame(2, 1, b'\3\4')]))
    struct.pack_into('<I', raw, 8, 12)
    with pytest.raises(ValueError, match='strictly increasing'):
        decode_pic(raw)


def test_picture_aggregate_preflight_happens_before_first_raster_decode(monkeypatch):
    import fdisbull.dinopark_images as module
    def forbidden(*args):
        raise AssertionError('Raster decode preceded cumulative admission')
    monkeypatch.setattr(module, '_picture_rows', forbidden)
    raw = pic([pic_frame(2, 1, b'\1\2'), pic_frame(2, 1, b'\3\4')])
    with pytest.raises(ValueError, match='pixel/work budget'):
        decode_pic(raw, max_pixels=3)
    with pytest.raises(ValueError, match='pixel/work budget'):
        decode_pic(raw, max_work=1)


@pytest.mark.parametrize('decoder,raw', [(decode_act, act()), (decode_pic, pic([pic_frame(2, 1, b'\1\2')]))])
def test_every_truncated_prefix_refuses_as_a_format_error(decoder, raw):
    for length in range(len(raw)):
        with pytest.raises(ValueError):
            decoder(raw[:length])


@pytest.mark.parametrize('option', ['max_source_bytes', 'max_pixels', 'max_work'])
@pytest.mark.parametrize('value', [True, 0, -1, 1.5])
def test_non_integer_or_nonpositive_budgets_refuse(option, value):
    with pytest.raises(ValueError):
        decode_pic(pic([pic_frame(2, 1, b'\1\2')]), **{option: value})


def test_source_budget_and_container_counts_refuse():
    with pytest.raises(ValueError, match='source byte budget'):
        decode_act(act(), max_source_bytes=1)
    with pytest.raises(ValueError, match='count budget'):
        decode_act(act([sprite(), sprite()]), max_sprites=1)
    with pytest.raises(ValueError, match='count budget'):
        decode_pic(pic([pic_frame(2, 1, b'\1\2'), pic_frame(2, 1, b'\1\2')]), max_frames=1)


def test_palette_preview_policies_are_explicit_mathematical_choices():
    palette = bytes([0, 31, 63]) * 256
    assert palette_rgb(palette, policy='shift2')[:3] == bytes([0, 124, 252])
    assert palette_rgb(palette, policy='replicate6')[:3] == bytes([0, 125, 255])
    with pytest.raises(ValueError):
        palette_rgb(palette, policy='native')
    with pytest.raises(ValueError):
        palette_rgb(bytes([255]) * 768, policy='shift2')


def test_mutable_input_is_snapshotted_without_aliasing_retained_buffers():
    raw=bytearray(act(sequences=(b'abc',)))
    original=bytes(raw);decoded=decode_act(memoryview(raw))
    raw[:]=bytes(len(raw))
    assert decoded.source_sha256==hashlib.sha256(original).hexdigest()
    assert decoded.sprites[0].indices==bytes([0,3,0,5])
    assert decoded.sequences==(b'abc',)
