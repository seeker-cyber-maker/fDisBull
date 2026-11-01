"""Optional Ghidra integration against authored static Mach-O bytes."""
import hashlib
from itertools import repeat
import os
from pathlib import Path
import shlex
import struct
import time

import pytest

from fdisbull.ghidra_arm64 import _fixups, probe_macho_arm64
from fixtures_formats import macho_arm64
from fixtures_macho import NONLAZY_SLOT, macho_fixture


ENTRY = 0x100000100


def _fat_arm64(thin):
    """One exact ARM64 slice at a nonzero original-container offset."""
    data = bytearray(4096 + len(thin))
    struct.pack_into(">II", data, 0, 0xCAFEBABE, 1)
    struct.pack_into(">5I", data, 8, 0x0100000C, 0, 4096, len(thin), 12)
    data[4096:] = thin
    return bytes(data)


def test_fixup_provenance_reports_original_fat_offsets_and_unresolved_binding():
    thin = macho_fixture("arm64", chained=True)
    records, status = _fixups(thin, 4096, [NONLAZY_SLOT])
    assert status == "enumerated"
    binding = next(item for item in records[NONLAZY_SLOT] if item["category"] == "binding")
    assert binding["source"] == "dyld_chained_fixups"
    assert binding["original_file_offset"] == 4096 + 0x1000
    assert binding["binding_state"] == "runtime_unresolved"
    assert binding["target"] is None


def test_unrepresented_chained_slots_make_fixup_coverage_partial():
    thin = bytearray(macho_fixture("arm64", chained=True))
    thin[0x1000:0x1008] = bytes(8)
    records, status = _fixups(bytes(thin), 0, [NONLAZY_SLOT])
    assert status == "partial"
    assert records[NONLAZY_SLOT]  # Other record sources do not complete the chain.


def test_invalid_requests_are_rejected_before_launch(tmp_path):
    source = tmp_path / "authored.macho"
    source.write_bytes(macho_arm64())
    headless = "/missing/analyzeHeadless"
    with pytest.raises(ValueError, match="aligned"):
        probe_macho_arm64(source, [ENTRY + 1], analyze_headless=headless)
    with pytest.raises(ValueError, match="decompile_entry"):
        probe_macho_arm64(source, [ENTRY], analyze_headless=headless, decompile_entry=ENTRY + 4)
    with pytest.raises(ValueError, match="wholly executable"):
        probe_macho_arm64(source, [0x100002000], analyze_headless=headless)
    with pytest.raises(ValueError, match="4096 address items"):
        probe_macho_arm64(source, repeat(ENTRY), analyze_headless=headless)


@pytest.mark.skipif(os.name != "posix", reason="process groups require POSIX")
def test_timeout_kills_java_process_group_without_inherited_secret(tmp_path, monkeypatch):
    source = tmp_path / "authored.macho"
    source.write_bytes(macho_arm64())
    child_marker = tmp_path / "orphan-child-ran"
    secret_marker = tmp_path / "secret-was-inherited"
    fake_headless = tmp_path / "timeout-only-launcher.sh"
    fake_headless.write_text(
        "#!/bin/sh\n"
        f"if [ -n \"$FDISBULL_TEST_SECRET\" ]; then touch {shlex.quote(str(secret_marker))}; fi\n"
        f"(sleep 1; touch {shlex.quote(str(child_marker))}) &\n"
        "sleep 10\n"
    )
    fake_headless.chmod(0o700)
    monkeypatch.setenv("FDISBULL_TEST_SECRET", "harmless-marker")
    with pytest.raises(RuntimeError, match="timed out"):
        probe_macho_arm64(source, [ENTRY], analyze_headless=fake_headless, timeout_s=0.25)
    time.sleep(1.1)
    assert not secret_marker.exists()
    assert not child_marker.exists()


def test_real_ghidra_fat_slice_has_source_bytes_budget_status_and_separate_c(tmp_path):
    headless = os.environ.get("FDISBULL_TEST_GHIDRA_HEADLESS")
    if not headless or not Path(headless).is_file():
        pytest.skip("set FDISBULL_TEST_GHIDRA_HEADLESS for the optional native integration")
    thin = macho_arm64()
    fat = _fat_arm64(thin)
    source = tmp_path / "authored-fat.macho"
    source.write_bytes(fat)
    result = probe_macho_arm64(
        source, [ENTRY, ENTRY + 4, ENTRY + 8], analyze_headless=headless,
        java_home=os.environ.get("FDISBULL_TEST_GHIDRA_JAVA_HOME"),
        max_instructions=2, decompile_entry=ENTRY, decompile_timeout_s=15,
    )
    assert result["source_sha256"] == hashlib.sha256(fat).hexdigest()
    assert result["slice_sha256"] == hashlib.sha256(thin).hexdigest()
    assert result["slice_offset"] == 4096
    assert result["status"] == "partial" and result["stop_reason"] == "budget"
    assert result["remaining_addresses"] == [ENTRY + 8]
    assert result["queried_count"] == 2 and result["failed"] == []
    assert result["ghidra_language"].startswith("AARCH64:LE:64")
    assert len(result["ghidra_script_sha256"]) == 64
    assert "Mach-O" in result["ghidra_image_format"]
    assert result["fixup_enumeration_status"] == "enumerated"
    first, second = result["facts"]
    assert first["loaded_address"] == ENTRY and first["runtime_address"] is None
    assert first["source_file_offset"] == 4096 + 0x100
    assert first["source_bytes"] == first["loaded_bytes"] == "02000094"
    assert first["mnemonic"] == "bl" and first["flow_targets"] == [ENTRY + 8]
    assert first["loaded_byte_relation"] == "same_as_original" and first["fixup_provenance"] == []
    assert second["source_file_offset"] == 4096 + 0x104
    assert second["source_bytes"] == second["loaded_bytes"] == "c0035fd6"
    assert second["mnemonic"] == "ret"
    diagnostic = result["decompiler_diagnostic"]
    assert diagnostic["entry"] == ENTRY and diagnostic["status"] == "complete"
    assert "void entry" in diagnostic["c"]
    assert diagnostic["role"] == "diagnostic only; not instruction facts or UIL"
    assert diagnostic["window_bytes"] == 4096 and diagnostic["timeout_s"] == 15
