"""Contract checks from the Renesas SH-1/SH-2 instruction descriptions."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from fdisbull.rom_asm import disassemble_rom, normalize_instruction

VECTORS = json.loads(Path(__file__).with_name("rom_asm_sh2_vectors.json").read_text())
BASE = VECTORS["base_address"]


def _golden(backend, **kwargs):
    failures = []
    for case in VECTORS["cases"]:
        data = bytes.fromhex(case["hex"])
        report = disassemble_rom(data, base_address=case.get("address", BASE),
                                 backend=backend, mode="word-scan", **kwargs)
        expected = case["mnemonic"]
        if expected is None:
            if report["instructions"]:
                failures.append((case["name"], report["instructions"]))
        elif not report["instructions"]:
            failures.append((case["name"], "no decode"))
        else:
            got = report["instructions"][0]["normalized"]
            if got != {"mnemonic": expected, "operands": case["operands"]}:
                failures.append((case["name"], got))
    assert not failures, failures


def test_capstone_independent_golden():
    _golden("capstone")


@pytest.mark.skipif(not os.environ.get("GHIDRA_HOME"), reason="GHIDRA_HOME not configured")
def test_ghidra_independent_golden():
    from fdisbull.rom_asm_ghidra import GhidraDecodeSession
    with GhidraDecodeSession(ghidra_home=os.environ["GHIDRA_HOME"]) as session:
        _golden("ghidra", ghidra_session=session)


@pytest.mark.skipif(not os.environ.get("SATURN_RECOMP_ROOT"), reason="SATURN_RECOMP_ROOT not configured")
def test_saturn_independent_golden():
    _golden("saturn-recomp", saturn_recomp_root=os.environ["SATURN_RECOMP_ROOT"])


def test_normalization_changes_spelling_only():
    assert normalize_instruction("_BT.S", " 0x10 ") == {"mnemonic": "bt/s", "operands": "16"}
    assert normalize_instruction("MOV", "#-0x1, R0") == {"mnemonic": "mov", "operands": "#-1,r0"}
    assert normalize_instruction("MOV", "@r1,r0") != normalize_instruction("MOV", "r1,r0")
    assert normalize_instruction("ADD", "0x1,r0", dialect="ghidra") == {"mnemonic":"add", "operands":"#1,r0"}
    assert normalize_instruction("MOV.L", "@(0x6010008,pc),r0", dialect="ghidra") == {"mnemonic":"mov.l", "operands":"100728840,r0"}
    assert normalize_instruction("MOV.L", "@(0x8,r1),r0", dialect="ghidra")["operands"] == "@(8,r1),r0"


@pytest.mark.parametrize("backend", [
    "capstone",
    pytest.param("ghidra", marks=pytest.mark.skipif(not os.environ.get("GHIDRA_HOME"), reason="GHIDRA_HOME not configured")),
    pytest.param("saturn-recomp", marks=pytest.mark.skipif(not os.environ.get("SATURN_RECOMP_ROOT"), reason="SATURN_RECOMP_ROOT not configured")),
])
def test_engines_reject_sh2a_only_rtv_n(backend):
    # Renesas SH-2A/SH2A-FPU Software Manual 6.3.32: 0000mmmm01111011.
    # m=2 produces this authored word; SH7604 does not provide RTV/N.
    result = disassemble_rom(bytes.fromhex("027b"), base_address=BASE, backend=backend,
                             ghidra_home=os.environ.get("GHIDRA_HOME"),
                             saturn_recomp_root=os.environ.get("SATURN_RECOMP_ROOT"))
    assert not result["instructions"]


def test_capstone_profile_rejection_preserves_native_evidence():
    import capstone
    engine = capstone.Cs(capstone.CS_ARCH_SH, capstone.CS_MODE_SH2 | capstone.CS_MODE_BIG_ENDIAN)
    native = next(engine.disasm(bytes.fromhex("027b"), BASE, count=1), None)
    result = disassemble_rom(bytes.fromhex("027b0009"), base_address=BASE, mode="word-scan")
    assert [r["normalized"]["mnemonic"] for r in result["instructions"]] == ["nop"]
    rejected = result["rejected_native_facts"]
    if native is None:
        assert rejected == []  # A corrected native library needs no guard rejection.
    else:
        assert len(rejected) == 1 and rejected[0]["bytes"] == "027b"
        assert rejected[0]["mnemonic"] == "rtv/n" and rejected[0]["file_offset"] == 0
        assert result["undecoded_words"][0]["reason"] == "encoding outside SH-2 profile"


def test_mapping_hashes_range_and_word_scan():
    data = bytes.fromhex("1122e001ffff700133")
    r = disassemble_rom(data, base_address=BASE, offset=2, length=6, mode="word-scan")
    assert r["source_sha256"] == hashlib.sha256(data).hexdigest()
    assert r["range_sha256"] == hashlib.sha256(data[2:8]).hexdigest()
    assert [(x["file_offset"], x["address"], x["bytes"]) for x in r["instructions"]] == [
        (2, BASE + 2, "e001"), (6, BASE + 6, "7001")]
    assert [(x["file_offset"], x["bytes"]) for x in r["undecoded_words"]] == [(4, "ffff")]
    assert r["status"] == "partial" and not r["complete_scope"]
    assert not r["executed"] and not r["code_discovered"] and not r["persisted"]


def test_linear_stops_scan_continues_and_budget_counts_attempts():
    data = bytes.fromhex("e001ffff7001")
    linear = disassemble_rom(data, base_address=BASE, length=6)
    assert [x["bytes"] for x in linear["instructions"]] == ["e001"]
    assert linear["stop_reason"] == "unknown_word" and linear["attempted_words"] == 2
    scan = disassemble_rom(data, base_address=BASE, length=6, mode="word-scan", max_instructions=2)
    assert [x["bytes"] for x in scan["instructions"]] == ["e001"]
    assert scan["stop_reason"] == "instruction_budget" and scan["attempted_words"] == 2
    assert scan["undecoded_words"][0]["bytes"] == "ffff"


def test_truncation_and_delay_slot():
    r = disassemble_rom(bytes.fromhex("000b0009e0"), base_address=BASE, length=5)
    assert [i["normalized"]["mnemonic"] for i in r["instructions"]] == ["rts", "nop"]
    assert r["stop_reason"] == "truncated_word" and r["trailing_bytes"] == "e0"


@pytest.mark.parametrize("backend", [
    "capstone",
    pytest.param("ghidra", marks=pytest.mark.skipif(not os.environ.get("GHIDRA_HOME"), reason="GHIDRA_HOME not configured")),
    pytest.param("saturn-recomp", marks=pytest.mark.skipif(not os.environ.get("SATURN_RECOMP_ROOT"), reason="SATURN_RECOMP_ROOT not configured")),
])
def test_word_scan_does_not_inherit_previous_branch_delay_context(backend):
    # Each word is an independent candidate. A branch in a preceding candidate
    # must not make a standalone BRAF disappear from the scan.
    result = disassemble_rom(bytes.fromhex("a0010023"), base_address=BASE,
        backend=backend, mode="word-scan", ghidra_home=os.environ.get("GHIDRA_HOME"),
        saturn_recomp_root=os.environ.get("SATURN_RECOMP_ROOT"))
    assert [x["normalized"] for x in result["instructions"]] == [
        {"mnemonic":"bra", "operands":str(BASE + 6)}, {"mnemonic":"braf", "operands":"r0"}]


@pytest.mark.parametrize("kwargs", [
    {"backend": "missing"}, {"arch": "sh4"}, {"mode": "unknown"},
    {"base_address": BASE + 1}, {"offset": 1}, {"offset": 4},
    {"length": 5}, {"max_instructions": 0}, {"timeout": float("nan")},
])
def test_invalid_contract_values(kwargs):
    args = {"base_address": BASE, **kwargs}
    with pytest.raises(ValueError):
        disassemble_rom(bytes.fromhex("e0017001"), **args)


def test_no_fallback_for_unavailable_explicit_engine(tmp_path):
    with pytest.raises(RuntimeError):
        disassemble_rom(bytes.fromhex("e001"), base_address=BASE, backend="ghidra", ghidra_home=str(tmp_path))


def test_cli_and_request_json(tmp_path):
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    source = tmp_path / "sample.bin"
    source.write_bytes(bytes.fromhex("1122e001ffff7001"))
    args = ["rom-disasm", str(source), "--backend", "capstone", "--base-address", hex(BASE),
            "--offset", "2", "--length", "6", "--max-instructions", "3", "--mode", "word-scan"]
    cli = subprocess.run([sys.executable, "-m", "fdisbull", *args], capture_output=True, text=True, check=True, env=env)
    envelope = json.loads(cli.stdout)
    assert envelope["ok"]
    result = envelope["result"]
    assert result["mapping"]["file_offset"] == 2
    assert [r["bytes"] for r in result["instructions"]] == ["e001", "7001"]
    assert result["undecoded_words"][0]["bytes"] == "ffff"

    request = {"method": "rom-disasm", "params": {"path": str(source), "backend": "capstone",
               "base_address": BASE, "offset": 2, "length": 6,
               "max_instructions": 3, "mode": "word-scan"}}
    reply = subprocess.run([sys.executable, "-m", "fdisbull", "request", json.dumps(request)],
                           capture_output=True, text=True, check=True, env=env)
    parsed = json.loads(reply.stdout)
    assert parsed["ok"]
    assert parsed["result"]["source_sha256"] == result["source_sha256"]
    assert parsed["result"]["undecoded_words"][0]["bytes"] == "ffff"
