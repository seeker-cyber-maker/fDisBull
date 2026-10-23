import hashlib
import struct

import pytest

from fdisbull.dos import load_mz


def mz_file(module=b"\xc3" + bytes(31), *, relocations=(), header_size=64, minalloc=0,
            cs=0, ip=0, ss=0, sp=32, overlay=b"", relocation_offset=28):
    size = header_size + len(module)
    pages, tail = (size + 511) // 512, size % 512
    header = bytearray(header_size)
    struct.pack_into("<14H", header, 0, 0x5A4D, tail, pages, len(relocations), header_size // 16,
                     minalloc, 0xFFFF, ss, sp, 0, ip, cs, relocation_offset, 0)
    for index, (offset, segment) in enumerate(relocations):
        struct.pack_into("<HH", header, relocation_offset + index * 4, offset, segment)
    return bytes(header) + module + overlay


def test_mz_maps_minimum_allocation_and_preserves_source_and_overlay():
    data = mz_file(b"\xc3" + bytes(17), minalloc=2, overlay=b"OVERLAY")
    image = load_mz(data)
    dos = image.metadata["dos"]
    assert (image.format, image.arch, image.bits, image.entry) == ("MZ", "x86", 16, 0x10000)
    assert image.source_bytes == data and image.metadata["source_sha256"] == hashlib.sha256(data).hexdigest()
    assert (dos["module_size"], dos["allocation_size"], dos["overlay_offset"], dos["overlay_size"]) == (18, 64, 82, 7)
    assert len(image.regions) == 1 and image.regions[0].data == data[64:82] + bytes(46)
    assert image.regions[0].writable and image.regions[0].executable
    assert image.metadata["file_mappings"] == [{"virtual_address": 0x10000, "file_offset": 64, "file_size": 18}]
    assert len(image.seeds) == 1 and image.seeds[0].address == image.entry
    assert dos["psp_segment"] == 0xFF0


def test_mz_relocations_and_segmented_entry_registers():
    module = bytearray(128)
    struct.pack_into("<H", module, 4, 0x1234)
    data = mz_file(bytes(module), relocations=[(4, 0)], cs=2, ip=1, ss=3, sp=0x20)
    image = load_mz(data, load_segment=0x2000)
    dos = image.metadata["dos"]
    assert image.entry == 0x20021
    assert (dos["entry_cs"], dos["entry_ip"], dos["stack_ss"], dos["sp"]) == (0x2002, 1, 0x2003, 0x20)
    assert image.regions[0].data[4:6] == struct.pack("<H", 0x3234)
    assert dos["relocations"] == [{"offset": 4, "segment": 0, "linear_address": 0x20004,
                                    "file_offset": 68, "original_value": 0x1234, "relocated_value": 0x3234}]
    candidates = {item["segment"] for item in dos["segment_candidates"]}
    assert {0x2002, 0x2003, 0x3234} <= candidates
    assert all(item["status"] == "candidate" for item in dos["segment_candidates"])


def test_relocation_word_addition_wraps_without_changing_original_source():
    module = b"\xff\xff" + bytes(30)
    data = mz_file(module, relocations=[(0, 0)])
    image = load_mz(data)
    assert image.regions[0].data[:2] == b"\xff\x0f"
    assert image.source_bytes[64:66] == b"\xff\xff"
    assert image.metadata["dos"]["relocations"][0]["relocated_value"] == 0x0FFF


def test_zero_tail_field_means_a_complete_512_byte_page():
    data = mz_file(b"\xc3" + bytes(447), overlay=b"unused")
    assert struct.unpack_from("<H", data, 2)[0] == 0
    image = load_mz(data)
    assert image.metadata["dos"]["declared_file_size"] == 512
    assert image.metadata["dos"]["module_size"] == 448
    assert image.metadata["dos"]["overlay_size"] == 6


def test_truncated_or_inconsistent_mz_header_is_rejected():
    with pytest.raises(ValueError, match="header"):
        load_mz(b"MZ")
    data = bytearray(mz_file())
    with pytest.raises(ValueError, match="Truncated"):
        load_mz(bytes(data[:-1]))
    struct.pack_into("<H", data, 2, 512)
    with pytest.raises(ValueError, match="last-page"):
        load_mz(bytes(data))
    struct.pack_into("<H", data, 2, len(data))
    struct.pack_into("<H", data, 8, 1)
    with pytest.raises(ValueError, match="header"):
        load_mz(bytes(data))


def test_relocation_table_and_full_word_targets_are_bounded():
    data = bytearray(mz_file())
    struct.pack_into("<H", data, 6, 20)
    with pytest.raises(ValueError, match="relocation table"):
        load_mz(bytes(data))
    data = mz_file(relocations=[(31, 0)])
    with pytest.raises(ValueError, match="relocation target"):
        load_mz(data)
    data = bytearray(mz_file(relocations=[(0, 0)]))
    struct.pack_into("<H", data, 24, 20)
    with pytest.raises(ValueError, match="relocation table"):
        load_mz(bytes(data))


@pytest.mark.parametrize("signature", [b"NE", b"LE", b"LX", b"PE\0\0"])
def test_secondary_executable_signatures_are_rejected_explicitly(signature):
    data = bytearray(mz_file(overlay=signature + bytes(16), relocation_offset=64))
    struct.pack_into("<I", data, 0x3C, 96)
    with pytest.raises(ValueError, match="secondary"):
        load_mz(bytes(data))


def test_legacy_lfanew_bytes_are_not_assumed_to_be_secondary_header():
    data = bytearray(mz_file())
    struct.pack_into("<I", data, 0x3C, 0x12345678)
    assert load_mz(bytes(data)).entry == 0x10000
    # Like classic executables, relocation data may overlap the later e_lfanew
    # field. These bytes are relocation data, not a mandatory secondary header.
    data = mz_file(relocations=[(1, 0)], relocation_offset=62, header_size=80)
    assert load_mz(data).metadata["dos"]["relocations"][0]["offset"] == 1


def test_real_mode_bounds_and_override_entry_are_explicit():
    with pytest.raises(ValueError, match="load_segment"):
        load_mz(mz_file(), load_segment=0)
    with pytest.raises(ValueError, match="1 MiB"):
        load_mz(mz_file(bytes(64)), load_segment=0xFFFF)
    with pytest.raises(ValueError, match="entry"):
        load_mz(mz_file(), entry=0x90000)
    with pytest.raises(ValueError, match="1 MiB"):
        load_mz(mz_file(minalloc=0xFFFF))
    image = load_mz(mz_file(), entry=0x10001)
    assert image.entry == 0x10001
    assert image.metadata["dos"]["entry_cs"] == 0x1000


def test_duplicate_relocations_preserve_dos_sequential_word_additions():
    data = mz_file(b"\x01\0" + bytes(30), relocations=[(0, 0), (0, 0)])
    image = load_mz(data)
    assert image.regions[0].data[:2] == b"\x01\x20"
    records = image.metadata["dos"]["relocations"]
    assert [(item["original_value"], item["relocated_value"]) for item in records] == [(1, 0x1001), (0x1001, 0x2001)]
    assert image.source_bytes[64:66] == b"\x01\0"
