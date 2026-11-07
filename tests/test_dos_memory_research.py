"""Authored controls for research witnesses; no original target files embedded."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import random
import struct
import subprocess
import sys
import zipfile

import pytest


HELPERS = Path(__file__).resolve().parents[1] / "research/dos-memory-tools/2026-11-07"


@pytest.fixture(scope="module")
def helpers():
    sys.path.insert(0, str(HELPERS))
    modules = {}
    names = ["compare_bytes", "check_gw_update", "check_gw32_fix", "intake_versions",
             "createinstall_decoder", "unpack_win085", "verify_createinstall_decoder",
             "qext_branch_probe", "intake_pro"]
    saved = {name: sys.modules.get(name) for name in names}
    try:
        for name in names:
            spec = importlib.util.spec_from_file_location(name, HELPERS / (name + ".py"))
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            modules[name] = module
        yield modules
    finally:
        sys.path.remove(str(HELPERS))
        for name, old in saved.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


def test_byte_comparison_preserves_shift_and_complete_reconstruction(helpers):
    original = random.Random(73).randbytes(8192)
    changed = original[:511] + b"AUTHORED INSERT" + original[511:6000] + original[6011:]
    result = helpers["compare_bytes"].compare(original, changed)
    before_cursor = after_cursor = 0
    forward, reverse = bytearray(), bytearray()
    for operation in result["exact_alignment"]["operations"]:
        a, b = operation["before_start"], operation["after_start"]
        ae, be = operation["before_end"], operation["after_end"]
        assert (a, b) == (before_cursor, after_cursor)
        if operation["operation"] == "equal":
            assert original[a:ae] == changed[b:be]
            forward.extend(original[a:ae])
            reverse.extend(changed[b:be])
        else:
            forward.extend(changed[b:be])
            reverse.extend(original[a:ae])
        before_cursor, after_cursor = ae, be
    assert bytes(forward) == changed
    assert bytes(reverse) == original
    assert (before_cursor, after_cursor) == (len(original), len(changed))
    assert result["exact_alignment"]["counts"]["shifted_equal_bytes"] > 7000
    assert result["exact_alignment"]["semantic_equivalence"] is False


def test_byte_controls_and_budget(helpers):
    comparator = helpers["compare_bytes"]
    assert len(comparator.controls()) == 8
    assert comparator.compare(b"", b"")["identical"]
    with pytest.raises(ValueError, match="budget"):
        comparator.compare(b"x" * (comparator.MAX_BYTES + 1), b"")


def test_byte_verifier_remains_active_with_python_optimization():
    code = "import compare_bytes; compare_bytes.require(False, 'deliberate invalid witness')"
    result = subprocess.run([sys.executable, "-O", "-c", code], cwd=HELPERS,
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert "deliberate invalid witness" in result.stderr


def test_configuration_preflight_is_complete_and_does_not_mutate_input(helpers):
    witness = helpers["check_gw32_fix"]
    target = bytes(32)
    records = [{"target_offset": 16, "expected_value": 0, "replacement_value": 106}]
    result = witness.reconstruct(target, records)
    assert result == bytes(16) + b"j" + bytes(15)
    assert target == bytes(32)
    records.append({"target_offset": 31, "expected_value": 1, "replacement_value": 2})
    with pytest.raises(ValueError, match="guard"):
        witness.reconstruct(target, records)
    assert target == bytes(32)


@pytest.mark.parametrize("offset", [-1, 32, True])
def test_configuration_invalid_offsets_fail(helpers, offset):
    with pytest.raises(ValueError):
        helpers["check_gw32_fix"].reconstruct(bytes(32), [
            {"target_offset": offset, "expected_value": 0, "replacement_value": 106}
        ])


def test_configuration_comparison_catches_unrelated_and_eof_edits(helpers):
    compare = helpers["check_gw32_fix"].compare_complete
    assert compare(b"abc", b"xbc")["first_overlap_mismatch"] == 0
    assert compare(b"abc", b"abcd")["unmatched_eof_bytes"] == 1
    assert not compare(b"abc", b"abcd")["equal"]


def test_original_input_identity_is_required(helpers, tmp_path):
    with pytest.raises(ValueError, match="identity"):
        helpers["check_gw32_fix"].inspect_patcher(bytes(442))
    with pytest.raises(ValueError, match="exact inspected"):
        helpers["check_gw_update"].reconstruct(bytes(25207), bytes(121912))
    with pytest.raises(ValueError, match="exact inspected"):
        helpers["unpack_win085"].inspect_installer(bytes(94830))
    qext = tmp_path / "QEXT.SYS"
    qext.write_bytes(bytes(5853))
    with pytest.raises(RuntimeError, match="SHA256"):
        helpers["qext_branch_probe"].read_source(qext, "dv242")


def test_decoder_eos_and_budgets(helpers):
    decode = helpers["createinstall_decoder"].decode
    # Initial complete tree: leaf 629+256=885, root-to-leaf bits 101110101.
    # Remaining seven bits are padding, not part of this empty EOS stream.
    decoded = decode(b"\xba\x80", output_limit=0)
    assert decoded.data == b""
    assert (decoded.consumed_bytes, decoded.consumed_bits) == (2, 9)
    with pytest.raises(ValueError, match="before EOS"):
        decode(b"\xba")
    with pytest.raises(ValueError, match="budget"):
        # Literal 'A': initial leaf 694, path 010110110, before any EOS.
        decode(b"\x5b\x00", output_limit=0)
    with pytest.raises(ValueError, match="Negative"):
        decode(b"\xba\x80", output_limit=-1)


@pytest.fixture
def canonical_inventory():
    # Authored metadata only. The production call site gets this structure
    # from a complete hash-pinned parse, never from the supplied JSON.
    return {"schema": "authored-control", "source": {"size": 500, "sha256": "0" * 64},
            "final_offset": 500, "file_length": 500, "decoded_member_bytes": 90,
            "declared_uncompressed": 90, "streams": [
                {"name": f"member-{i}", "compressed_start": 20 * i,
                 "compressed_bytes": 10, "compressed_bits": 79,
                 "decoded_size": 10, "sha256": str(i) * 64}
                for i in range(9)]}


@pytest.mark.parametrize("mutation", ["empty", "missing", "duplicate", "reordered", "oversized",
                                      "negative", "bit_count", "output_hash", "wrong_source", "boolean"])
def test_decoder_witness_rejects_incomplete_or_forged_inventory(helpers, canonical_inventory, mutation):
    supplied = deepcopy(canonical_inventory)
    if mutation == "empty":
        supplied["streams"] = []
    elif mutation == "missing":
        supplied["streams"].pop()
    elif mutation == "duplicate":
        supplied["streams"][-1] = deepcopy(supplied["streams"][0])
    elif mutation == "reordered":
        supplied["streams"].reverse()
    elif mutation == "oversized":
        supplied["streams"][0]["decoded_size"] = 2**40
    elif mutation == "negative":
        supplied["streams"][0]["compressed_start"] = -1
    elif mutation == "bit_count":
        supplied["streams"][0]["compressed_bits"] += 1
    elif mutation == "output_hash":
        supplied["streams"][0]["sha256"] = "f" * 64
    elif mutation == "wrong_source":
        supplied["source"]["sha256"] = "f" * 64
    else:
        supplied["streams"][0]["compressed_start"] = False
    with pytest.raises(ValueError, match="Inventory"):
        helpers["verify_createinstall_decoder"].validate_inventory(supplied, canonical_inventory)


def test_decoder_witness_uses_canonical_rows(helpers, canonical_inventory):
    supplied = deepcopy(canonical_inventory)
    result = helpers["verify_createinstall_decoder"].validate_inventory(supplied, canonical_inventory)
    assert result is canonical_inventory["streams"]
    assert result is not supplied["streams"]


@pytest.mark.parametrize("name", ["../outside", "/absolute", "C:\\DOS\\file", "dir/../../outside"])
def test_archive_traversal_is_rejected(helpers, tmp_path, name):
    archive = tmp_path / "authored.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(name, b"authored")
    with pytest.raises(ValueError, match="[Uu]nsafe"):
        helpers["intake_versions"].extract_zip(archive, tmp_path / "new", "control")
    with pytest.raises(ValueError, match="unsafe"):
        helpers["intake_pro"].member_path(name)
    assert not (tmp_path / "outside").exists()


def test_dos_short_header_does_not_invent_secondary_header(helpers):
    data = bytearray(128)
    struct.pack_into("<HHHHH", data, 0, 0x5A4D, 128, 1, 0, 2)
    struct.pack_into("<I", data, 0x3C, 64)
    data[64:68] = b"PE\0\0"
    result = helpers["intake_versions"].executable_header(bytes(data))
    assert result["format"] == "MZ"
    assert "secondary_header_offset" not in result
