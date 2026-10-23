import struct

from fdisbull.inspection import identify_header, inspect_binary
from fixtures_formats import pe64


def mz_image(*, relocation=None, overlay=b"OVERLAY_TEXT\0"):
    module = b"\0MODULE_TEXT\0" + bytes(19)
    header = bytearray(64)
    size = len(header) + len(module)
    struct.pack_into("<14H", header, 0, 0x5A4D, size, 1, int(relocation is not None), 4,
                     2, 0xFFFF, 1, 16, 0, 0, 0, 28, 0)
    if relocation is not None:
        struct.pack_into("<HH", header, 28, relocation, 0)
    header[32:43] = b"HEADER_TEXT"
    return bytes(header) + module + overlay


def test_identify_classic_dos_reports_header_facts_without_runtime_base():
    header = identify_header(mz_image())
    assert header["format"] == "DOS MZ" and header["valid"]
    assert header["dos_header"]["e_minalloc"] == 2
    assert header["header_size"] == 64 and header["declared_file_size"] == 96
    assert header["relocation_count"] == 0
    assert "load_segment" not in header and "imagebase" not in header and "entrypoint" not in header


def test_inspect_dos_maps_only_file_backed_module_strings():
    result = inspect_binary(mz_image())
    header, section = result["header"], result["sections"][0]
    assert header["load_segment"] == 0x1000 and header["entrypoint"] == 0x10000
    assert (header["entry_cs"], header["entry_ip"], header["stack_ss"], header["stack_sp"]) == (0x1000, 0, 0x1001, 16)
    assert (section["virtual_address"], section["virtual_size"], section["file_offset"], section["file_size"]) == (0x10000, 64, 64, 32)
    strings = {item["text"]: item for item in result["strings"]}
    assert strings["MODULE_TEXT"]["address"] == 0x10001
    assert strings["HEADER_TEXT"]["address"] is None and strings["OVERLAY_TEXT"]["address"] is None
    assert result["imports"] == result["exports"] == []
    assert result["dos"]["relocation_count"] == 0 and "relocations" not in result["dos"]
    assert result["dos"]["segment_candidates"][0]["status"] == "candidate"
    assert any("static" in warning for warning in result["warnings"])


def test_legacy_lfanew_is_ignored_and_invalid_relocations_do_not_fake_mapping():
    legacy = bytearray(mz_image())
    struct.pack_into("<I", legacy, 0x3C, 0x12345678)
    header = identify_header(bytes(legacy))
    assert header["format"] == "DOS MZ" and header["valid"]
    assert inspect_binary(bytes(legacy))["sections"]
    invalid = inspect_binary(mz_image(relocation=31))
    assert invalid["header"]["format"] == "DOS MZ" and invalid["header"]["valid"]
    assert invalid["sections"] == []
    assert all(item["address"] is None for item in invalid["strings"])
    assert any("DOS memory mapping unavailable" in warning for warning in invalid["warnings"])


def test_pe_header_recognition_and_exports_remain_native_pe():
    result = inspect_binary(pe64())
    assert result["header"]["format"] == "PE32+" and result["header"]["valid"]
    assert result["header"]["entrypoint"] == 0x140001000
    assert result["exports"][0]["name"] == "helper"
    assert result["exports"][0]["address"] == 0x140001010
    assert "dos" not in result
