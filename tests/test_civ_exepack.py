import struct

import pytest

# Source examples are deliberately omitted from release distributions.
pytest.importorskip("examples", reason="source-checkout examples are not packaged")

from examples.civ.civ_exepack import ExepackError, unpack_exepack

DOS_HEADER = struct.Struct("<14H")
EXEPACK_HEADER = struct.Struct("<9H")


def exepack_fixture(*, tail=b""):
    """Build a small backward EXEPACK image with one relocation."""
    cparhdr = 2
    relative_cs = 2
    payload_offset = cparhdr * 16
    exepack_offset = (cparhdr + relative_cs) * 16
    payload = bytes(range(16))
    reversed_output = payload[::-1]
    command_stream = b"\xb3\x00\x10" + reversed_output
    reversed_stream = b"\xff" * (exepack_offset - payload_offset - len(command_stream))
    reversed_stream += command_stream
    packed_payload = reversed_stream[::-1]
    assert len(packed_payload) == exepack_offset - payload_offset

    marker = b"Packed file is corrupt"
    relocation_counts = struct.pack("<H", 1) + struct.pack("<H", 6)
    relocation_counts += b"\x00" * (15 * 2)
    exepack_size = EXEPACK_HEADER.size + len(marker) + len(relocation_counts)
    exepack = EXEPACK_HEADER.pack(
        4,
        3,
        0,
        exepack_size,
        0x80,
        0x22,
        1,
        0x4252,
        0,
    )
    body = packed_payload + exepack + marker + relocation_counts
    declared_size = exepack_offset + exepack_size
    assert len(body) + payload_offset == declared_size
    pages, last_page = divmod(declared_size, 512)
    header = DOS_HEADER.pack(
        0x5A4D,
        last_page,
        pages + bool(last_page),
        0,
        cparhdr,
        0x20,
        0xFFFF,
        0,
        0,
        0,
        0,
        relative_cs,
        28,
        0,
    )
    return header + b"\x00" * (payload_offset - len(header)) + body + tail


def test_unpack_exepack_rebuilds_root_and_preserves_tail():
    image = exepack_fixture(tail=b"OVERLAY")

    unpacked = unpack_exepack(image)
    header = DOS_HEADER.unpack_from(unpacked)

    assert header[0] == 0x5A4D
    assert header[1:3] == (48, 1)
    assert header[5] == 37
    assert header[3] == 1
    assert header[4] == 2
    assert header[10:12] == (4, 3)
    assert unpacked[28:32] == struct.pack("<HH", 6, 0)
    assert unpacked[32:48] == bytes(range(16))
    assert unpacked.endswith(b"OVERLAY")


def test_unpack_exepack_rejects_non_mz_input():
    with pytest.raises(ExepackError, match="MZ signature"):
        unpack_exepack(b"X" * DOS_HEADER.size)
