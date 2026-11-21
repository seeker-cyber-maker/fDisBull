"""Bounded offline inspection of authored bytes, without a running game."""

import hashlib
import json
import os
import struct

import pytest

from dotbox import inspection


def _file(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def _mz(*, entry=0):
    header = struct.pack("<14H", 0x5A4D, 36, 1, 0, 2, 0, 0xFFFF, 0, 0x100, 0, entry, 0, 28, 0)
    return header + b"\0" * 4 + bytes.fromhex("b83412c3")


def test_decodes_authored_x86_window_without_running_it(tmp_path):
    from dotbox.inspection import inspect_disassemble

    program = tmp_path / "fixture.com"
    program.write_bytes(bytes.fromhex("b83412bb7856cd21"))
    result = inspect_disassemble(program, bits=16, length=8)
    assert [(item["bytes"], item["mnemonic"], item["size"]) for item in result["instructions"]] == [
        ("b83412", "mov", 3), ("bb7856", "mov", 3), ("cd21", "int", 2),
    ]
    assert [item["file_offset"] for item in result["instructions"]] == [0, 3, 6]
    assert result["binding"]["kind"] == "file-offset"
    assert program.read_bytes() == bytes.fromhex("b83412bb7856cd21")


def test_identity_binds_only_explicit_resources_and_never_launches(tmp_path, monkeypatch):
    from dotbox import native_session

    def forbidden(*args, **kwargs):
        raise AssertionError("Offline identity must not start an emulator")

    monkeypatch.setattr(native_session.DOSBoxRPC, "__init__", forbidden)
    program = _file(tmp_path, "fixture.com", b"\x90\xc3")
    resource = _file(tmp_path, "ROOM.DAT", b"authored room data")
    ignored = _file(tmp_path, "unselected.bin", b"unselected")
    result = inspection.inspect_identity(program, resources=[resource])
    assert result["source"]["sha256"] == hashlib.sha256(b"\x90\xc3").hexdigest()
    assert result["image"]["format"] == "COM"
    assert result["image"]["entry"] == {"relative_cs": 0, "ip": 0x100, "file_offset": 0, "file_backed": True}
    assert [row["name"] for row in result["resources"]] == ["ROOM.DAT"]
    fingerprint = result["selection_sha256"]
    ignored.write_bytes(b"still unselected")
    assert inspection.inspect_identity(program, resources=[resource])["selection_sha256"] == fingerprint
    resource.write_bytes(b"different room data")
    assert inspection.inspect_identity(program, resources=[resource])["selection_sha256"] != fingerprint
    assert program.read_bytes() == b"\x90\xc3"


@pytest.mark.parametrize("entry, file_offset, backed", [(0, 32, True), (8, None, False)])
def test_mz_identity_distinguishes_file_backed_entry_from_zero_fill(tmp_path, entry, file_offset, backed):
    program = _file(tmp_path, "fixture.exe", _mz(entry=entry))
    result = inspection.inspect_identity(program)
    assert result["image"]["format"] == "MZ"
    assert result["image"]["module_file_offset"] == 32
    assert result["image"]["module_size"] == 4
    assert result["image"]["entry"]["file_offset"] == file_offset
    assert result["image"]["entry"]["file_backed"] is backed


@pytest.mark.parametrize("data", [b"MZ", b"not an executable"])
def test_identity_refuses_malformed_or_unsupported_executable(tmp_path, data):
    program = _file(tmp_path, "fixture.exe", data)
    with pytest.raises(ValueError):
        inspection.inspect_identity(program)


def test_explicit_resource_limits_refuse_duplicates_and_excess_bytes(tmp_path, monkeypatch):
    program = _file(tmp_path, "fixture.com", b"\x90\xc3")
    resource = _file(tmp_path, "room.dat", b"1234")
    with pytest.raises(ValueError, match="distinct"):
        inspection.inspect_identity(program, resources=[resource, resource])
    with pytest.raises(ValueError, match="at most"):
        inspection.inspect_identity(program, resources=[resource] * 9)
    monkeypatch.setattr(inspection, "MAX_IDENTITY_BYTES", 5)
    with pytest.raises(ValueError, match="budget"):
        inspection.inspect_identity(program, resources=[resource])


def test_large_identity_is_refused_before_reading_sparse_file(tmp_path):
    program = tmp_path / "large.exe"
    with program.open("wb") as stream:
        stream.truncate(inspection.MAX_FILE_BYTES + 1)
    with pytest.raises(ValueError, match="budget"):
        inspection.inspect_identity(program)


def test_strings_report_selected_hash_offsets_and_result_limits(tmp_path):
    data = b"xx\0FIRST\0SECOND\0THIRD"
    source = _file(tmp_path, "buffer.bin", data)
    result = inspection.inspect_strings(source, offset=3, length=100, min_length=4, limit=1, origin=0x2000)
    assert result["window"]["sha256"] == hashlib.sha256(data[3:]).hexdigest()
    assert result["window"]["hash_scope"] == "selected bytes only"
    assert result["window"]["window_truncated"]
    assert result["results_truncated"]
    assert result["strings"] == [{"file_offset": 3, "window_offset": 0, "address": 0x2000,
                                  "byte_length": 5, "text": "FIRST", "text_truncated": False}]
    assert result["binding"]["runtime_validated"] is False


def test_long_printable_run_has_bounded_excerpt_and_exact_length(tmp_path):
    source = _file(tmp_path, "buffer.bin", b"A" * 300)
    result = inspection.inspect_strings(source, length=300)
    assert result["strings"][0]["byte_length"] == 300
    assert result["strings"][0]["text"] == "A" * 256
    assert result["strings"][0]["text_truncated"]
    assert not result["results_truncated"]


def test_masked_and_overlapping_searches_are_bounded(tmp_path):
    source = _file(tmp_path, "buffer.bin", bytes.fromhex("a1b2a3b4"))
    result = inspection.inspect_find(source, b"\xa0\xb0", mask=b"\xf0\xf0", length=4)
    assert [row["file_offset"] for row in result["matches"]] == [0, 2]
    assert [row["bytes"] for row in result["matches"]] == ["a1b2", "a3b4"]
    source.write_bytes(b"AAAA")
    limited = inspection.inspect_find(source, b"AA", length=4, limit=2)
    assert [row["file_offset"] for row in limited["matches"]] == [0, 1]
    assert limited["results_truncated"]
    with pytest.raises(ValueError, match="constrain"):
        inspection.inspect_find(source, b"A", mask=b"\0")


@pytest.mark.parametrize("options", [{"length": 65537}, {"length": 0}, {"offset": -1},
                                    {"offset": True}, {"limit": 0}, {"limit": 257}, {"origin": True}])
def test_invalid_windows_or_limits_are_rejected(tmp_path, options):
    source = _file(tmp_path, "buffer.bin", b"test")
    with pytest.raises(ValueError):
        inspection.inspect_strings(source, **options)


def test_regular_file_checks_refuse_symlinks_directories_and_fifo(tmp_path):
    source = _file(tmp_path, "buffer.bin", b"test")
    link = tmp_path / "link.bin"
    link.symlink_to(source)
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    for path in (link, tmp_path, fifo):
        with pytest.raises((ValueError, OSError)):
            inspection.inspect_strings(path)


def test_changed_source_is_rejected_before_returning_findings(tmp_path, monkeypatch):
    source = _file(tmp_path, "buffer.bin", b"first")
    original = os.fstat
    calls = []

    def change_before_final_stat(descriptor):
        calls.append(descriptor)
        if len(calls) == 2:
            source.write_bytes(b"replacement with another size")
        return original(descriptor)

    monkeypatch.setattr(inspection.os, "fstat", change_before_final_stat)
    with pytest.raises(ValueError, match="changed"):
        inspection.inspect_strings(source)


def test_replaced_parent_path_is_rejected_even_when_open_descriptor_is_unchanged(tmp_path, monkeypatch):
    directory = tmp_path / "live"
    directory.mkdir()
    source = _file(directory, "snapshot.bin", b"ORIGINAL")
    original_fstat = os.fstat
    before = source.stat()
    calls = 0

    def replace_path_before_final_stat(descriptor):
        nonlocal calls
        calls += 1
        if calls == 2:
            directory.rename(tmp_path / "retained-original")
            directory.mkdir()
            source.write_bytes(b"REPLACED")
            assert inspection._identity(original_fstat(descriptor)) == inspection._identity(before)
        return original_fstat(descriptor)

    monkeypatch.setattr(inspection.os, "fstat", replace_path_before_final_stat)
    with pytest.raises(ValueError, match="changed"):
        inspection.inspect_strings(source)


def test_disassembly_separates_file_offsets_from_decoder_origins(tmp_path):
    source = _file(tmp_path, "buffer.bin", b"XX" + bytes.fromhex("b8341290"))
    relative = inspection.inspect_disassemble(source, offset=2, length=4)
    assert relative["instructions"][0]["file_offset"] == 2
    assert relative["instructions"][0]["decoder_ip"] == 0
    assert relative["decoder_ip_basis"] == "window-relative, starting at zero"
    supplied = inspection.inspect_disassemble(source, offset=2, length=4, origin=0x100)
    assert supplied["instructions"][0]["file_offset"] == 2
    assert supplied["instructions"][0]["decoder_ip"] == 0x100
    assert supplied["instructions"][0]["address"] == 0x100
    assert not supplied["binding"]["runtime_validated"]


def test_x86_32_and_bounded_linear_decoding(tmp_path):
    source = _file(tmp_path, "buffer.bin", bytes.fromhex("b87856341290"))
    result = inspection.inspect_disassemble(source, bits=32, length=6, limit=1)
    assert result["instructions"][0]["bytes"] == "b878563412"
    assert result["instructions"][0]["size"] == 5
    assert result["decoded_bytes"] == 5 and result["remaining_bytes"] == 1
    assert result["results_truncated"] and result["stop_reason"] == "result-limit"
    with pytest.raises(ValueError, match="width"):
        inspection.inspect_disassemble(source, bits=16, origin=0xFFFF, length=6)


def test_invalid_instruction_stops_without_fabricated_decode(tmp_path):
    source = _file(tmp_path, "buffer.bin", b"\x90\xb8")
    result = inspection.inspect_disassemble(source, length=2)
    assert [row["mnemonic"] for row in result["instructions"]] == ["nop"]
    assert result["decode_error"]["file_offset"] == 1
    assert result["decoded_bytes"] == 1 and result["remaining_bytes"] == 1
    assert result["stop_reason"] == "invalid-or-truncated-instruction"
    assert not result["results_truncated"]


def test_diff_reports_exact_changes_and_keeps_total_when_results_are_limited(tmp_path):
    before = _file(tmp_path, "before.bin", b"abcde")
    after = _file(tmp_path, "after.bin", b"axcye")
    result = inspection.inspect_diff(before, after, length=5, limit=1)
    assert result["changed_bytes"] == 2 and result["results_truncated"]
    assert result["changes"] == [{"window_offset": 1, "before_file_offset": 1, "after_file_offset": 1,
                                  "address": 1, "length": 1, "before_hex": "62", "after_hex": "78",
                                  "hex_truncated": False}]
    assert before.read_bytes() == b"abcde" and after.read_bytes() == b"axcye"


def test_diff_accepts_different_file_offsets_only_with_matching_explicit_origins(tmp_path):
    before = _file(tmp_path, "before.bin", b"Xabc")
    after = _file(tmp_path, "after.bin", b"YYaxc")
    result = inspection.inspect_diff(before, after, before_offset=1, after_offset=2, length=3,
                                     before_origin=0x1000, after_origin=0x1000)
    assert result["changes"][0]["address"] == 0x1001
    assert result["changes"][0]["before_file_offset"] == 2
    assert result["changes"][0]["after_file_offset"] == 3
    assert result["binding"]["runtime_validated"] is False
    with pytest.raises(ValueError, match="matching origins"):
        inspection.inspect_diff(before, after, before_offset=1, after_offset=2, length=3)


@pytest.mark.parametrize("origins", [{"before_origin": 1}, {"before_origin": 1, "after_origin": 2},
                                    {"before_origin": 1, "after_origin": True}])
def test_diff_refuses_mismatched_address_bindings(tmp_path, origins):
    before = _file(tmp_path, "before.bin", b"abc")
    after = _file(tmp_path, "after.bin", b"abc")
    with pytest.raises(ValueError):
        inspection.inspect_diff(before, after, length=3, **origins)


def test_diff_refuses_unequal_captured_lengths(tmp_path):
    before = _file(tmp_path, "before.bin", b"ab")
    after = _file(tmp_path, "after.bin", b"abc")
    with pytest.raises(ValueError, match="equal numbers"):
        inspection.inspect_diff(before, after, length=3)


def test_decoder_self_check_uses_installed_pinned_decoder():
    result = inspection.self_check()
    assert result["ok"] and all(result["checks"].values())
    assert result["decoder"] == {"name": "iced-x86", "version": "1.22.0"}


@pytest.mark.parametrize("operation, extra", [("identity", []), ("strings", ["--min-length", "1"]),
                                             ("find", ["--hex", "90"]), ("disassemble", ["--bits", "16"])])
def test_cli_success_is_json(tmp_path, capsys, operation, extra):
    source = _file(tmp_path, "fixture.com", b"\x90\xc3")
    assert inspection.main([operation, str(source), *extra]) == 0
    output = capsys.readouterr()
    assert not output.err
    result = json.loads(output.out)
    assert result["ok"] and result["result"]["operation"] == operation


def test_cli_diff_and_argument_errors_have_stable_exit_contract(tmp_path, capsys):
    before = _file(tmp_path, "before.bin", b"ab")
    after = _file(tmp_path, "after.bin", b"ac")
    assert inspection.main(["diff", str(before), str(after), "--length", "0x2"]) == 0
    assert json.loads(capsys.readouterr().out)["result"]["changed_bytes"] == 1
    for args in ([], ["find", str(before)], ["strings", str(before), "--offset", "invalid"],
                 ["find", str(before), "--hex", "zz"]):
        assert inspection.main(args) == 1
        output = capsys.readouterr()
        assert not output.out and json.loads(output.err)["ok"] is False
