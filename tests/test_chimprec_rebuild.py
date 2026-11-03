import hashlib
import json
import struct

import pytest

from fdisbull.chimprec import build_import_plan, recover_iat, rebuild_captured_pe
from fdisbull.chimprec_capture import validate_capture_manifest
from fdisbull.chimprec_pe import inspect_pe_imports, parse_pe_layout, pe_checksum
from fdisbull.gog_galaxy import inspect_galaxy_wrapper, rebuild_galaxy_capture, rebuild_galaxy_files
from fdisbull.model import Region


def make_pe(bits=32, *, section_names=(".text",), mapped=True, image_base=None, entry_rva=None):
    image_base = image_base if image_base is not None else (0x400000 if bits == 32 else 0x140000000)
    pe = 0x80
    optional_size = 0xE0 if bits == 32 else 0xF0
    section_count = len(section_names)
    section_table = pe + 24 + optional_size
    headers = 0x200
    section_alignment = 0x1000
    file_alignment = 0x200
    size_image = 0x1000 * (section_count + 2)
    total = size_image if mapped else headers + section_count * 0x200
    data = bytearray(total)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, pe)
    data[pe:pe + 4] = b"PE\0\0"
    machine = 0x14C if bits == 32 else 0x8664
    struct.pack_into("<HHIIIHH", data, pe + 4, machine, section_count, 0, 0, 0,
                     optional_size, 0x0102)
    optional = pe + 24
    struct.pack_into("<H", data, optional, 0x10B if bits == 32 else 0x20B)
    if entry_rva is None:
        entry_rva = 0x2000 if "UPX1" in section_names else 0x1000
    struct.pack_into("<I", data, optional + 16, entry_rva)
    if bits == 32:
        struct.pack_into("<I", data, optional + 28, image_base)
        directory_offset, count_offset = 96, 92
    else:
        struct.pack_into("<Q", data, optional + 24, image_base)
        directory_offset, count_offset = 112, 108
    struct.pack_into("<II", data, optional + 32, section_alignment, file_alignment)
    struct.pack_into("<II", data, optional + 56, size_image, headers)
    struct.pack_into("<H", data, optional + 68, 3)
    struct.pack_into("<H", data, optional + 70, 0x140)
    struct.pack_into("<I", data, optional + count_offset, 16)
    raw = headers
    for index, name in enumerate(section_names):
        off = section_table + index * 40
        va = 0x1000 * (index + 1)
        chars = 0x60000020 if index == 0 or name.upper() == "UPX1" else 0xC0000040
        data[off:off + 8] = name.encode().ljust(8, b"\0")
        struct.pack_into("<IIIIIIHHI", data, off + 8, 0x1000, va, 0x200, raw,
                         0, 0, 0, 0, chars)
        raw += 0x200
    return bytes(data), image_base


def export(address, module="kernel32.dll", name="ExitProcess", ordinal=1, forwarder=None):
    return {"address": address, "module": module, "name": name,
            "ordinal": ordinal, "forwarder": forwarder}


def capture(wrapper, image_base, size_image, oep, bits=32, transfer="jump"):
    return {
        "format": "fdisbull-chimprec-capture-1",
        "bits": bits,
        "source": {"sha256": hashlib.sha256(wrapper).hexdigest(), "size": len(wrapper),
                   "label": "authored Galaxy wrapper"},
        "processes": [{"id": "p1", "image_base": image_base,
                       "image_size": size_image, "label": "wrapper"}],
        "threads": [{"id": "t1", "process_id": "p1"}],
        "regions": [{"process_id": "p1", "start": image_base,
                     "size": size_image, "protection": "rwx", "kind": "image"}],
        "selected": {"process_id": "p1", "thread_id": "t1",
                     "module_base": image_base, "module_size": size_image, "oep": oep},
        "transfer": {"kind": transfer, "process_id": "p1", "thread_id": "t1",
                     "from": image_base + 0x2000, "to": oep, "observed": True},
    }


def test_runtime_code_range_can_override_stale_section_flag():
    target = 0x70001000
    code = b"\xff\x15" + struct.pack("<I", 0x2000) + b"\xc3"
    regions = [Region("stale code", 0x1000, code, False),
               Region("iat", 0x2000, target.to_bytes(4, "little"), False)]
    assert recover_iat(regions, 32, [export(target)])["entries"] == []
    result = recover_iat(regions, 32, [export(target)],
                         code_ranges=[{"address": 0x1000, "length": len(code),
                                       "evidence": "observed executable page"}])
    assert result["entries"][0]["address"] == 0x2000
    assert result["source"]["code_range_override"] is True


def test_invalid_and_ambiguous_thunks_require_explicit_decisions():
    recovery = {"entries": [
        {"address": 0x401000, "resolved": True, "status": "resolved", "candidate": True,
         "alternatives": [export(0x7000, name="A")]},
        {"address": 0x401004, "resolved": False, "status": "unresolved", "candidate": True, "alternatives": []},
        {"address": 0x401008, "resolved": True, "status": "ambiguous", "candidate": True,
         "alternatives": [export(0x7004, name="B"), export(0x7004, module="user32.dll", name="B2")]},
    ]}
    with pytest.raises(ValueError, match="unresolved"):
        build_import_plan(recovery, 32)
    with pytest.raises(ValueError, match="ambiguous"):
        build_import_plan(recovery, 32, {0x401004: "cut"})
    plan = build_import_plan(recovery, 32, {0x401004: "cut", 0x401008: {"alternative": 1}})
    assert [group["module"] for group in plan] == ["kernel32.dll", "user32.dll"]
    assert plan[1]["entries"][0]["name"] == "B2"


@pytest.mark.parametrize("bits", [32, 64])
def test_rebuild_imports_sets_oep_original_iat_and_valid_directory(bits):
    mapped, base = make_pe(bits)
    mapped = bytearray(mapped)
    width = bits // 8
    slot = base + 0x1100
    second = slot + width
    target1 = 0x76001000 if bits == 32 else 0x7FFB76001000
    target2 = target1 + 0x100
    mapped[0x1100:0x1100 + width] = target1.to_bytes(width, "little")
    mapped[0x1100 + width:0x1100 + 2 * width] = target2.to_bytes(width, "little")
    recovery = recover_iat([Region("text", base + 0x1000, bytes(mapped[0x1000:0x2000]), True)],
                           bits,
                           [export(target1, name="ExitProcess", ordinal=1),
                            export(target2, name=None, ordinal=17)],
                           candidate_slots=[slot, second])
    rebuilt = rebuild_captured_pe(bytes(mapped), recovery, oep=base + 0x1010)
    layout = parse_pe_layout(rebuilt["image"])
    assert layout["entry_rva"] == 0x1010
    assert layout["sections"][-1]["name"] == ".reimp"
    assert rebuilt["receipt"]["import_count"] == 2
    imports = inspect_pe_imports(rebuilt["image"])
    assert imports == [
        {"module": "kernel32.dll", "iat_rva": 0x1100, "name": "ExitProcess", "ordinal": None},
        {"module": "kernel32.dll", "iat_rva": 0x1100 + width, "name": None, "ordinal": 17},
    ]
    checksum = struct.unpack_from("<I", rebuilt["image"], layout["checksum_offset"])[0]
    assert checksum == pe_checksum(rebuilt["image"], layout["checksum_offset"])
    assert struct.unpack_from("<II", rebuilt["image"], layout["directory_offset"] + 4 * 8) == (0, 0)
    assert struct.unpack_from("<II", rebuilt["image"], layout["directory_offset"] + 5 * 8) == (0, 0)


def test_capture_manifest_keeps_process_thread_region_and_call_transfer():
    wrapper, base = make_pe(32, section_names=("UPX0", "UPX1"))
    doc = capture(wrapper, base, 0x4000, base + 0x1010, transfer="call")
    normalized = validate_capture_manifest(doc, bits=32)
    assert normalized["transfer"]["kind"] == "call"
    assert normalized["selected"]["thread_id"] == "t1"
    doc["transfer"]["to"] += 1
    with pytest.raises(ValueError, match="target"):
        validate_capture_manifest(doc)


def test_galaxy_coordinator_rebuilds_synthetic_upx_wrapper():
    wrapper, base = make_pe(32, section_names=("UPX0", "UPX1"))
    mapped, _ = make_pe(32, image_base=base)
    mapped = bytearray(mapped)
    target = 0x76001000
    mapped[0x1000:0x1007] = b"\xff\x15" + struct.pack("<I", base + 0x1100) + b"\xc3"
    mapped[0x1100:0x1104] = target.to_bytes(4, "little")
    manifest = capture(wrapper, base, 0x3000, base + 0x1010)
    result = rebuild_galaxy_capture(wrapper, bytes(mapped), manifest,
                                    [export(target)], candidate_slots=[base + 0x1100])
    assert result["receipt"]["format"] == "fdisbull-gog-galaxy-rebuild-1"
    assert result["receipt"]["capture_attachment_performed"] is False
    assert inspect_galaxy_wrapper(wrapper)["entry_section"] == "UPX1"
    assert inspect_pe_imports(result["image"])[0]["name"] == "ExitProcess"


def test_file_api_writes_new_private_directory(tmp_path):
    wrapper, base = make_pe(32, section_names=("UPX0", "UPX1"))
    mapped, _ = make_pe(32, image_base=base)
    mapped = bytearray(mapped)
    target = 0x76001000
    mapped[0x1100:0x1104] = target.to_bytes(4, "little")
    wrapper_path = tmp_path / "wrapper.exe"
    mapped_path = tmp_path / "mapped.bin"
    capture_path = tmp_path / "capture.json"
    exports_path = tmp_path / "exports.json"
    wrapper_path.write_bytes(wrapper)
    mapped_path.write_bytes(mapped)
    capture_path.write_text(json.dumps(capture(wrapper, base, 0x3000, base + 0x1010)))
    exports_path.write_text(json.dumps([export(target)]))
    output = tmp_path / "out"
    result = rebuild_galaxy_files(wrapper_path, mapped_path, capture_path, exports_path,
                                  output, candidate_slots=[base + 0x1100])
    assert (output / "galaxy-wrapper-unpacked.exe").is_file()
    assert (output / "gog-galaxy-rebuild.json").is_file()
    assert result["capture_attachment_performed"] is False
    with pytest.raises(ValueError, match="new directory"):
        rebuild_galaxy_files(wrapper_path, mapped_path, capture_path, exports_path,
                             output, candidate_slots=[base + 0x1100])


def test_projectless_module_cli_and_media_catalog(tmp_path, capsys):
    from fdisbull.gog_galaxy_cli import main
    from fdisbull.media import media_modules

    wrapper, base = make_pe(32, section_names=("UPX0", "UPX1"))
    mapped, _ = make_pe(32, image_base=base)
    mapped = bytearray(mapped)
    target = 0x76001000
    mapped[0x1100:0x1104] = target.to_bytes(4, "little")
    inputs = {
        "wrapper": tmp_path / "wrapper.exe",
        "mapped_image": tmp_path / "mapped.bin",
        "capture": tmp_path / "capture.json",
        "exports": tmp_path / "exports.json",
    }
    inputs["wrapper"].write_bytes(wrapper)
    inputs["mapped_image"].write_bytes(mapped)
    inputs["capture"].write_text(json.dumps(capture(wrapper, base, 0x3000, base + 0x1010)))
    inputs["exports"].write_text(json.dumps([export(target)]))
    output = tmp_path / "result"
    assert main([str(inputs["wrapper"]), str(inputs["mapped_image"]),
                 str(inputs["capture"]), str(inputs["exports"]), str(output),
                 "--candidate-slot", hex(base + 0x1100)]) == 0
    response = json.loads(capsys.readouterr().out)
    assert response["complete"] and response["import_count"] == 1
    modules = {item["name"]: item for item in media_modules()["modules"]}
    assert modules["gog-galaxy-upx"]["methods"] == ["python-module:gog_galaxy_cli"]
