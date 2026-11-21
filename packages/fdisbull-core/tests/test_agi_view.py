"""Hand-calculated EGA VIEW rows, authored offsets and malformed boundaries."""
from hashlib import sha256

import pytest

from fdisbull_core.agi_view import decode_view_cel


def single_cel(width=5, height=2, flags=15, rows=b"\x12\x21\0\x33\0"):
    # One loop at 7, one cel at 10, and the first compressed row at 13.
    return bytes([0, 0, 1, 0, 0, 7, 0, 1, 3, 0, width, height, flags]) + rows


def replace(payload, offset, data):
    return payload[:offset] + bytes(data) + payload[offset + len(data):]


def test_exact_rows_transparent_remainder_and_source_boundaries():
    payload = single_cel()
    result = decode_view_cel(payload, loop=0, cel=0)
    assert result == {
        "source_sha256": sha256(payload).hexdigest(), "loop": 0, "cel": 0,
        "width": 5, "height": 2, "transparent_color": 15,
        "mirror_enabled": False, "stored_original_loop": None, "mirrored": False,
        "pixels": bytes([1, 1, 2, 15, 15, 3, 3, 3, 15, 15]),
        "cel_offset": 10, "data_offset": 13, "data_end": 18,
    }
    assert payload == single_cel()
    assert type(result["pixels"]) is bytes


def test_aliased_loop_directory_mirrors_the_full_row_including_transparency():
    # Both loop entries point at the same directory and cel. Loop 0 is the
    # stored original; loop 1 reverses all five pixels, including transparent 15.
    payload = bytes([0, 0, 2, 0, 0, 9, 0, 9, 0,
                     1, 3, 0, 5, 2, 0x8f, 0x12, 0x21, 0, 0x33, 0])
    original = decode_view_cel(payload, loop=0, cel=0)
    mirrored = decode_view_cel(payload, loop=1, cel=0)
    assert original["pixels"] == bytes([1, 1, 2, 15, 15, 3, 3, 3, 15, 15])
    assert mirrored["pixels"] == bytes([15, 15, 2, 1, 1, 15, 15, 3, 3, 3])
    assert original["mirror_enabled"] is True and original["mirrored"] is False
    assert mirrored["mirrored"] is True
    assert original["stored_original_loop"] == mirrored["stored_original_loop"] == 0
    assert original["cel_offset"] == mirrored["cel_offset"] == 12
    assert original["data_end"] == mirrored["data_end"] == 20


def test_distinct_directories_can_share_a_cel_with_original_loop_one():
    payload = bytes([0, 0, 2, 0, 0, 9, 0, 12, 0,
                     1, 6, 0, 1, 3, 0, 3, 1, 0x9e, 0x11, 0x21, 0])
    assert decode_view_cel(payload, loop=0, cel=0)["pixels"] == bytes([14, 2, 1])
    result = decode_view_cel(payload, loop=1, cel=0)
    assert result["pixels"] == bytes([1, 2, 14])
    assert result["stored_original_loop"] == 1 and result["mirrored"] is False


def test_mirror_loop_bits_are_inert_without_enable_bit():
    result = decode_view_cel(single_cel(flags=0x7f), loop=0, cel=0)
    assert result["pixels"] == bytes([1, 1, 2, 15, 15, 3, 3, 3, 15, 15])
    assert result["stored_original_loop"] is None and result["mirrored"] is False


def test_empty_row_and_explicit_transparent_run():
    result = decode_view_cel(single_cel(3, 2, 6, b"\0\x62\0"), loop=0, cel=0)
    assert result["pixels"] == bytes([6] * 6)


def test_empty_unselected_loop_does_not_hide_a_valid_cel():
    # Empty loop 0 at 9; loop 1 at 10 selects cel header 13 and RLE 16..18.
    payload = bytes.fromhex("000002000009000a000001030002010f1200")
    result = decode_view_cel(payload, loop=1, cel=0)
    assert result["pixels"] == b"\x01\x01"
    assert (result["width"], result["height"], result["transparent_color"]) == (2, 1, 15)
    assert (result["cel_offset"], result["data_offset"], result["data_end"]) == (13, 16, 18)
    with pytest.raises(ValueError, match="absent"):
        decode_view_cel(payload, loop=0, cel=0)


def test_duplicate_cel_references_and_padding_are_allowed():
    # Both directory entries point to cel 12. Trailing padding is not RLE.
    payload = bytes([0, 0, 1, 0, 0, 7, 0, 2, 5, 0, 5, 0,
                     2, 1, 15, 0x12, 0, 0xab, 0xcd])
    result = decode_view_cel(payload, loop=0, cel=1)
    assert result["pixels"] == bytes([1, 1])
    assert result["cel_offset"] == 12 and result["data_end"] == 17


def test_two_distinct_cels_allow_padding_between_their_streams():
    payload = bytes([0, 0, 1, 0, 0, 7, 0, 2, 5, 0, 12, 0,
                     2, 1, 15, 0x12, 0, 0xab, 0xcd,
                     1, 1, 3, 0x41, 0])
    first = decode_view_cel(payload, loop=0, cel=0)
    second = decode_view_cel(payload, loop=0, cel=1)
    assert first["pixels"] == bytes([1, 1]) and first["data_end"] == 17
    assert second["pixels"] == bytes([4]) and second["cel_offset"] == 19
    assert second["data_end"] == 24


def test_description_after_pixels_is_bounded_and_not_part_of_rle():
    payload = replace(single_cel(), 3, [18, 0]) + b"Authored cel\0"
    result = decode_view_cel(payload, loop=0, cel=0)
    assert result["data_end"] == 18
    assert result["pixels"] == bytes([1, 1, 2, 15, 15, 3, 3, 3, 15, 15])


@pytest.mark.parametrize("payload", [None, "", bytearray(single_cel()),
                                    memoryview(single_cel()), b"", b"\0" * 4,
                                    single_cel() + b"\0" * 65536])
def test_payload_types_and_length_bounds(payload):
    with pytest.raises(ValueError):
        decode_view_cel(payload, loop=0, cel=0)


@pytest.mark.parametrize("field", ["loop", "cel"])
@pytest.mark.parametrize("value", [True, False, -1, 256, 1.0, "0", None])
def test_index_types_and_byte_bounds(field, value):
    arguments = {"loop": 0, "cel": 0, field: value}
    with pytest.raises(ValueError):
        decode_view_cel(single_cel(), **arguments)


@pytest.mark.parametrize("arguments", [{"loop": 1, "cel": 0}, {"loop": 0, "cel": 1}])
def test_missing_requested_loop_or_cel(arguments):
    with pytest.raises(ValueError, match="absent"):
        decode_view_cel(single_cel(), **arguments)


@pytest.mark.parametrize("offset,data", [
    (2, [0]), (2, [255]), (5, [6, 0]), (5, [255, 255]),
    (7, [0]), (7, [255]), (8, [2, 0]), (8, [255, 255]),
    (10, [0]), (10, [161]), (11, [0]), (11, [169]),
])
def test_malformed_directories_headers_and_dimensions(offset, data):
    with pytest.raises(ValueError):
        decode_view_cel(replace(single_cel(), offset, data), loop=0, cel=0)


@pytest.mark.parametrize("payload", [
    bytes([0, 0, 1, 0, 0, 7, 0, 1]),
    single_cel()[:12],
    replace(single_cel(), 3, [3, 0]),
    replace(single_cel(), 3, [255, 255]),
    replace(single_cel(), 3, [18, 0]) + b"no terminator",
])
def test_truncated_tables_headers_and_invalid_descriptions(payload):
    with pytest.raises(ValueError):
        decode_view_cel(payload, loop=0, cel=0)


@pytest.mark.parametrize("rows", [b"", b"\x12", b"\x13\0", b"\x10\0", b"\xf0\0"])
def test_missing_row_terminators_zero_length_runs_and_overflow(rows):
    with pytest.raises(ValueError):
        decode_view_cel(single_cel(2, 1, 15, rows), loop=0, cel=0)


def test_exactly_full_row_still_requires_its_terminator():
    result = decode_view_cel(single_cel(2, 1, 15, b"\x12\0"), loop=0, cel=0)
    assert result["pixels"] == bytes([1, 1]) and result["data_end"] == 15


def test_missing_later_row_is_rejected():
    with pytest.raises(ValueError, match="row"):
        decode_view_cel(single_cel(2, 2, 15, b"\x12\0"), loop=0, cel=0)


def test_distinct_cel_headers_cannot_partially_overlap():
    payload = bytes([0, 0, 1, 0, 0, 7, 0, 2, 5, 0, 6, 0,
                     1, 1, 1, 15, 0, 0])
    with pytest.raises(ValueError, match="Overlapping"):
        decode_view_cel(payload, loop=0, cel=0)


def test_cel_header_cannot_alias_a_loop_directory():
    payload = bytes([0, 0, 2, 0, 0, 9, 0, 12, 0,
                     1, 3, 0, 1, 3, 0, 1, 1, 15, 0])
    with pytest.raises(ValueError, match="Overlapping"):
        decode_view_cel(payload, loop=0, cel=0)


def test_description_cannot_alias_a_loop_directory():
    payload = replace(single_cel(), 3, [7, 0])
    with pytest.raises(ValueError, match="Overlapping"):
        decode_view_cel(payload, loop=0, cel=0)


def test_rle_cannot_consume_a_description_terminator():
    payload = replace(single_cel(1, 1, 15, b"\x11\0"), 3, [14, 0])
    with pytest.raises(ValueError, match="row"):
        decode_view_cel(payload, loop=0, cel=0)


@pytest.mark.parametrize("selected", [0, 1])
def test_rle_cannot_cross_into_the_next_cel_even_when_unselected(selected):
    payload = bytes([0, 0, 1, 0, 0, 7, 0, 2, 5, 0, 9, 0,
                     1, 1, 15, 0x11,
                     1, 1, 15, 0x21, 0])
    with pytest.raises(ValueError, match="row"):
        decode_view_cel(payload, loop=0, cel=selected)


def many_aliases(loop_count):
    # 255 cel references in one shared loop table; each cel aliases one pixel.
    start = 5 + 2 * loop_count
    return (bytes([0, 0, loop_count, 0, 0]) + start.to_bytes(2, "little") * loop_count
            + b"\xff" + (511).to_bytes(2, "little") * 255
            + bytes([1, 1, 15, 0x11, 0]))


def test_cel_reference_walk_is_bounded_even_for_aliases():
    allowed = decode_view_cel(many_aliases(4), loop=3, cel=254)
    assert allowed["pixels"] == b"\x01"
    with pytest.raises(ValueError, match="budget"):
        decode_view_cel(many_aliases(5), loop=0, cel=0)


def test_maximum_geometry_and_payload_length():
    rows = (b"\x2f" * 10 + b"\x2a\0") * 168
    payload = single_cel(160, 168, 15, rows)
    payload += b"\0" * (65535 - len(payload))
    result = decode_view_cel(payload, loop=0, cel=0)
    assert len(result["pixels"]) == 26880
    assert result["pixels"] == bytes([2]) * 26880
    assert result["data_end"] == 2029
