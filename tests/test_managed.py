"""Synthetic ECMA-335 metadata and real CIL decoding; no managed code executes."""
import struct

import pytest


def managed_fixture():
    """Small PE32 CLI assembly with Main/Answer methods and an mscorlib reference.

    Authored directly from PE/CLI layout rules because this test environment has
    no C# compiler or CLR. It is an analysis fixture, not a claimed runtime test.
    """
    strings = bytearray(b"\0")
    names = {}
    for name in ("ManagedSample.exe", "<Module>", "Controller", "ALD", "Main", "Answer", "ManagedSample", "Object", "System", "mscorlib"):
        names[name] = len(strings)
        strings += name.encode() + b"\0"
    blobs = b"\0\x03\x00\x00\x01\x03\x00\x00\x08\x08\xb7\x7a\x5c\x56\x19\x34\xe0\x89"
    valid = sum(1 << index for index in (0, 1, 2, 6, 32, 35))
    tables = bytearray(struct.pack("<IBBBBQQ", 0, 2, 0, 0, 1, valid, 0))
    tables += struct.pack("<6I", 1, 1, 2, 2, 1, 1)
    tables += struct.pack("<5H", 0, names["ManagedSample.exe"], 1, 0, 0)  # Module
    tables += struct.pack("<3H", 6, names["Object"], names["System"])  # AssemblyRef scope, TypeRef
    tables += struct.pack("<I5H", 0, names["<Module>"], 0, 0, 1, 1)
    tables += struct.pack("<I5H", 0x100181, names["Controller"], names["ALD"], 5, 1, 1)
    tables += struct.pack("<I5H", 0x2400, 0, 0x96, names["Main"], 1, 1)
    tables += struct.pack("<I5H", 0x2420, 0, 0x96, names["Answer"], 5, 1)
    tables += struct.pack("<I4HI3H", 0x8004, 1, 0, 0, 0, 0, 0, names["ManagedSample"], 0)
    tables += struct.pack("<4HI4H", 4, 0, 0, 0, 0, 9, names["mscorlib"], 0, 0)
    user_strings = b"\0\x0b" + "hello".encode("utf-16le") + b"\0"
    streams = [(b"#~", bytes(tables)), (b"#Strings", bytes(strings)), (b"#US", user_strings),
               (b"#GUID", bytes(range(16))), (b"#Blob", blobs)]
    version = b"v4.0.30319\0\0"
    root = bytearray(struct.pack("<IHHII", 0x424A5342, 1, 1, 0, len(version)) + version + struct.pack("<HH", 0, len(streams)))
    header_size = len(root) + sum(8 + ((len(name) + 1 + 3) & ~3) for name, _ in streams)
    stream_headers = bytearray()
    payload = bytearray()
    for name, content in streams:
        offset = header_size + len(payload)
        stream_headers += struct.pack("<II", offset, len(content))
        stream_headers += (name + b"\0").ljust((len(name) + 1 + 3) & ~3, b"\0")
        payload += content
        payload += bytes((-len(payload)) % 4)
    metadata = bytes(root + stream_headers + payload)
    data = bytearray(0xA00)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, 0x84, 0x14C, 1, 0, 0, 0, 224, 0x102)
    optional = 0x98
    struct.pack_into("<H", data, optional, 0x10B)
    struct.pack_into("<I", data, optional + 28, 0x400000)
    struct.pack_into("<II", data, optional + 32, 0x2000, 0x200)
    struct.pack_into("<II", data, optional + 56, 0x4000, 0x200)
    struct.pack_into("<H", data, optional + 68, 3)
    struct.pack_into("<I", data, optional + 92, 16)
    struct.pack_into("<II", data, optional + 96 + 14 * 8, 0x2000, 72)
    section = optional + 224
    data[section:section + 8] = b".text\0\0\0"
    struct.pack_into("<IIII", data, section + 8, 0x800, 0x2000, 0x800, 0x200)
    struct.pack_into("<I", data, section + 36, 0x60000020)
    struct.pack_into("<IHHIIII", data, 0x200, 72, 2, 5, 0x2100, len(metadata), 1, 0x06000001)
    data[0x300:0x300 + len(metadata)] = metadata
    main = bytes.fromhex("7201000070262802000006262b01002a")
    answer = bytes.fromhex("1f2a2a")
    data[0x600:0x601 + len(main)] = bytes([(len(main) << 2) | 2]) + main
    data[0x620:0x621 + len(answer)] = bytes([(len(answer) << 2) | 2]) + answer
    return bytes(data)

from fdisbull.managed import managed_kind, inspect_managed, disassemble_managed


def with_method_body(code, *, more_sections=False):
    data = bytearray(managed_fixture())
    row = data.find(struct.pack("<I", 0x2400), 0x300, 0x600)
    assert row >= 0
    struct.pack_into("<I", data, row, 0x2500)
    header = struct.pack("<HHII", 0x3003 | (8 if more_sections else 0), 8, len(code), 0)
    data[0x700:0x700 + len(header) + len(code)] = header + code
    if more_sections:
        position = (0x700 + len(header) + len(code) + 3) & ~3
        section = b"\x01\x10\0\0" + struct.pack("<HHBHBI", 2, 0, 1, 1, 1, 0)
        data[position:position + len(section)] = section
    return bytes(data)


def test_managed_probe_is_dependency_free_and_reports_pure_il():
    result = managed_kind(managed_fixture())
    assert result["managed"] and result["recognized"] and result["status"] == "managed"
    assert result["il_only"] is True and result["native_entrypoint"] is False
    assert result["clr_header"]["entrypoint"] == 0x06000001
    assert result["metadata"]["version"] == "v4.0.30319"
    assert result["metadata"]["table_rows"]["6"] == 2


def test_managed_metadata_names_tokens_and_rvas_are_real_cli_fields():
    result = inspect_managed(managed_fixture())
    assert result["status"] == "managed"
    assert result["assembly"] == {"name": "ManagedSample", "version": "1.0.0.0", "culture": ""}
    assert result["method_count"] == result["methods_returned"] == 2 and not result["budget_exhausted"]
    first, second = result["methods"]
    assert (first["token"], first["full_name"], first["rva"], first["file_offset"]) == ("0x06000001", "ALD.Controller::Main", 0x2400, 0x600)
    assert second["full_name"] == "ALD.Controller::Answer" and second["signature"] == "000008"
    assert all(item["has_cil_body"] for item in result["methods"])


def test_cil_decoder_resolves_call_string_and_method_local_branch():
    result = disassemble_managed(managed_fixture(), "0x06000001")
    assert result["complete"] and not result["budget_exhausted"]
    assert [row["mnemonic"] for row in result["instructions"]] == ["ldstr", "pop", "call", "pop", "br.s", "nop", "ret"]
    assert result["instructions"][2]["address"] == "0x06000001:IL_0006"
    assert result["instructions"][2]["file_offset"] == 0x607
    assert [(item["kind"], item["token"], item["name"]) for item in result["token_references"]] == [
        ("string", "0x70000001", "hello"), ("call", "0x06000002", "ALD.Controller::Answer")]
    assert result["branch_references"] == [{"source_offset": 12, "target_offset": 15, "kind": "branch", "target_in_code": True, "target_is_instruction": True}]
    answer = disassemble_managed(managed_fixture(), 0x06000002)
    assert [row["mnemonic"] for row in answer["instructions"]] == ["ldc.i4.s", "ret"]
    assert answer["instructions"][0]["operand"] == 42


def test_cil_instruction_budget_reports_partial_without_claiming_complete():
    result = disassemble_managed(managed_fixture(), 0x06000001, max_instructions=2)
    assert result["status"] == "partial" and result["budget_exhausted"] and not result["complete"]
    assert len(result["instructions"]) == 2 and len(result["token_references"]) == 1
    assert result["branch_references"] == []


def test_native_and_nativeaot_origin_are_not_mistaken_for_managed_cil():
    from fixtures_formats import pe64
    for data in (b"not a managed file", pe64()):
        result = inspect_managed(data)
        assert not result["managed"] and result["status"] == "non_managed"
        assert result["methods"] == [] and result["native_aot"] == "not_determined"
        assert any("NativeAOT" in warning for warning in result["warnings"])


def test_invalid_clr_is_still_recognized_and_never_falls_back_to_native():
    data = bytearray(managed_fixture())
    data[0x300:0x304] = b"BAD!"
    result = managed_kind(bytes(data))
    assert result["managed"] and result["recognized"] and result["status"] == "invalid_managed"
    assert result["il_only"] is True
    assert inspect_managed(bytes(data))["methods"] == []
    struct.pack_into("<I", data, 0x208, 0x7FFFFFFF)
    assert managed_kind(bytes(data))["status"] == "invalid_managed"


def test_missing_optional_dependencies_leave_clr_guard_available(monkeypatch):
    import builtins
    original = builtins.__import__
    def without_managed(name, *args, **kwargs):
        if name == "dnfile" or name.startswith("dncil"):
            raise ImportError("optional decoder absent")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", without_managed)
    assert managed_kind(managed_fixture())["il_only"] is True
    result = inspect_managed(managed_fixture())
    assert result["status"] == "dependencies_missing" and result["managed"]
    assert any("fdisbull[managed]" in warning for warning in result["warnings"])


def test_fat_cil_header_and_switch_targets_are_decoded_with_eh_left_explicit():
    code = b"\x16\x45" + struct.pack("<Iii", 2, 0, 1) + b"\0\x2a"
    result = disassemble_managed(with_method_body(code, more_sections=True), 0x06000001)
    assert result["complete"] and result["header_size"] == 12 and result["max_stack"] == 8
    assert result["exception_sections_present"] is True
    assert [(item["target_offset"], item["target_is_instruction"]) for item in result["branch_references"]] == [(14, True), (15, True)]
    assert any("Exception-handling" in warning for warning in result["warnings"])


def test_bad_switch_and_truncated_instruction_are_bounded_errors():
    for code in (b"\x45" + struct.pack("<I", 0xFFFFFFFF) + b"\x2a", b"\x28\x01"):
        result = disassemble_managed(with_method_body(code), 0x06000001)
        assert result["status"] == "invalid_cil" and not result["complete"]
        assert result["instructions"] == [] and result["warnings"]


def test_invalid_metadata_token_stays_unresolved_while_cil_bytes_decode():
    result = disassemble_managed(with_method_body(bytes.fromhex("28ffff00062a")), 0x06000001)
    assert result["complete"]
    reference = result["token_references"][0]
    assert not reference["resolved"] and reference["name"] is None
    outside = disassemble_managed(with_method_body(bytes.fromhex("2b7f2a")), 0x06000001)
    assert outside["branch_references"][0]["target_in_code"] is False
    assert any("branch targets" in warning for warning in outside["warnings"])


def test_metadata_row_budget_is_checked_before_external_parser_and_output_is_capped(monkeypatch):
    import fdisbull.managed as module
    data = bytearray(managed_fixture())
    table_stream = next(item for item in managed_kind(bytes(data))["metadata"]["streams"] if item["name"] == "#~")
    struct.pack_into("<I", data, 0x300 + table_stream["offset"] + 24, module.MAX_TABLE_ROWS + 1)
    result = managed_kind(bytes(data))
    assert result["status"] == "invalid_managed" and any("table rows" in warning for warning in result["warnings"])
    monkeypatch.setattr(module, "MAX_METHODS", 1)
    result = inspect_managed(managed_fixture())
    assert result["method_count"] == 2 and result["methods_returned"] == 1 and result["budget_exhausted"]


def test_wrong_or_missing_method_tokens_and_native_method_are_explicit():
    with pytest.raises(ValueError, match="MethodDef"):
        disassemble_managed(managed_fixture(), 0x02000001)
    with pytest.raises(ValueError, match="not present"):
        disassemble_managed(managed_fixture(), 0x0600FFFF)
    data = bytearray(managed_fixture())
    row = data.find(struct.pack("<I", 0x2400), 0x300, 0x600)
    struct.pack_into("<H", data, row + 4, 1)  # miNative
    result = inspect_managed(bytes(data))
    assert result["methods"][0]["body_kind"] == "native_or_runtime"
    with pytest.raises(ValueError, match="no managed CIL body"):
        disassemble_managed(bytes(data), 0x06000001)
