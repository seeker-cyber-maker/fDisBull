#!/usr/bin/env python3
"""Verify source-bound Sona entrypoints for the private Genesis audio adapter.

The receipt contains hashes and decoded entry/call facts only. It never copies
ROM, driver or stream bytes into the repository or the receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from capstone import CS_ARCH_M68K, CS_MODE_BIG_ENDIAN, CS_MODE_M68K_000, Cs

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
from fdisbull.miniplanets_audio import (  # noqa: E402
    AUDIO_RANGES,
    INSTRUMENT_RANGES,
    ROM_SHA256 as PROFILE_ROM_SHA256,
    recover_audio,
)


ROM_SHA256 = "e8aee1b9fedca87b638a7624709d7f6e1a2aff8a5222083346d1cd63963acbe7"
CORE_SHA256 = "27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268"
SONA_ENTRY = 0x0D5C
SONA_CODE_END = 0x100C
SONA_BLOB_START = 0x60360
SONA_BLOB_END = SONA_BLOB_START + 0x1380
INIT_WRAPPER = 0x06F4
BGM_CALL = 0x0740
SFX_CALL = 0x0782
STATUS_CALL = 0x0788
STOP_CALL = 0x074C


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode(md, rom: bytes, start: int, end: int):
    instructions = list(md.disasm(rom[start:end], start))
    if not instructions or instructions[0].address != start:
        raise ValueError("no decoded instruction at " + hex(start))
    return instructions


def by_address(instructions, address):
    for item in instructions:
        if item.address == address:
            return item
    raise ValueError("missing instruction at " + hex(address))


def require_call(md, rom: bytes, address: int, target: int):
    item = by_address(decode(md, rom, address, address + 6), address)
    expected = "$" + format(target, "x") + ".w"
    if item.mnemonic != "jsr" or item.op_str.lower() != expected:
        raise ValueError(
            "unexpected call at " + hex(address) + ": " +
            item.mnemonic + " " + item.op_str
        )
    return {"address": address, "target": target}


def check(
    rom_path: Path,
    probe_path: Path,
    candidate_path: Path | None = None,
    native_smoke_path: Path | None = None,
):
    rom = rom_path.read_bytes()
    if sha(rom) != ROM_SHA256:
        raise ValueError("ROM is not the qualified Miniplanets REV04 source")
    if PROFILE_ROM_SHA256 != ROM_SHA256:
        raise ValueError("Genesis audio and full-game ROM profiles disagree")
    recover_audio(rom)

    def pointer_table(table, records, kind):
        selected = [record for record in records if record[0] == kind]
        result = []
        for index, record in enumerate(selected):
            target = int.from_bytes(
                rom[table + index * 4:table + index * 4 + 4], "big"
            )
            if target != record[2]:
                raise ValueError(
                    kind + " table entry " + str(index + 1) +
                    " no longer points at its guarded source stream"
                )
            result.append(target)
        return result

    bgm_targets = pointer_table(0x04C458, AUDIO_RANGES, "bgm")
    sfx_targets = pointer_table(0x054FE2, AUDIO_RANGES, "sfx")
    instrument_targets = []
    for index, record in enumerate(INSTRUMENT_RANGES):
        target = int.from_bytes(
            rom[0x0554F4 + index * 4:0x0554F4 + index * 4 + 4], "big"
        )
        if target != record[3]:
            raise ValueError(
                "instrument table entry " + str(index) +
                " no longer points at its guarded source data"
            )
        instrument_targets.append(target)

    probe = json.loads(probe_path.read_text())
    if (probe.get("complete") is not True or
            probe.get("inputs_unchanged") is not True or
            probe.get("core_sha256") != CORE_SHA256):
        raise ValueError("the native initializer probe is incomplete or changed")
    cases = probe.get("cases")
    if not isinstance(cases, list) or len(cases) != 1:
        raise ValueError("expected one controlled Sona_Init probe case")
    case = cases[0]
    contract = case.get("contract", {})
    if (contract.get("entry") != SONA_ENTRY or
            case.get("complete") is not True or
            case.get("status") != "returned" or
            case.get("registers_after", {}).get("PC") !=
            contract.get("return_address", 0xFFFD00)):
        raise ValueError("Sona_Init did not return through its controlled boundary")

    md = Cs(CS_ARCH_M68K, CS_MODE_BIG_ENDIAN | CS_MODE_M68K_000)
    init = decode(md, rom, SONA_ENTRY, SONA_ENTRY + 0x60)
    if init[0].mnemonic != "movem.l":
        raise ValueError("Sona_Init entry prologue changed")
    if not any(x.mnemonic == "lea.l" and "$60360" in x.op_str.lower()
               for x in init):
        raise ValueError("Sona_Init no longer references the guarded Z80 blob")
    if not any(x.mnemonic == "move.w" and "$137f" in x.op_str.lower()
               for x in init):
        raise ValueError("Sona_Init no longer copies the expected blob extent")
    if not any(x.mnemonic == "rts" for x in init):
        raise ValueError("Sona_Init return instruction not found")

    wrapper = decode(md, rom, INIT_WRAPPER, INIT_WRAPPER + 0x20)
    expected_init = "$" + format(SONA_ENTRY, "x") + ".w"
    if (wrapper[0].mnemonic != "jsr" or
            wrapper[0].op_str.lower() != expected_init):
        raise ValueError("original initialization wrapper no longer calls Sona_Init")

    update = decode(md, rom, 0x0712, 0x079C)
    calls = {
        "init_wrapper": {"address": INIT_WRAPPER, "target": SONA_ENTRY},
        "bgm": require_call(md, rom, BGM_CALL, 0x0ED0),
        "sfx": require_call(md, rom, SFX_CALL, 0x0EE4),
        "stop": require_call(md, rom, STOP_CALL, 0x0F2C),
        "status": require_call(md, rom, STATUS_CALL, 0x0FB6),
    }
    text = [(x.address, x.mnemonic, x.op_str.lower()) for x in update]
    checks = {
        "bgm_list": any(a == 0x072E and "$4c458" in op for a, _, op in text),
        "sfx_list": any(a == 0x076E and "$54fe2" in op for a, _, op in text),
        "instrument_list": sum("$554f4" in op for _, _, op in text) == 2,
        "instrument_count": sum(
            m == "moveq" and op == "#$1c, d0" for _, m, op in text
        ) == 2,
        "sfx_priority": any(
            a == 0x0780 and m == "move.b" and op == "d7, d1"
            for a, m, op in text
        ),
        "sfx1_busy_bit": any(
            a == 0x078C and m == "btst.b" and op == "#$5, d0"
            for a, m, op in text
        ),
    }
    if not all(checks.values()):
        raise ValueError("original audio call setup no longer matches the adapter ABI")

    sfx = decode(md, rom, 0x0EE4, 0x0F10)
    sfx_ex = decode(md, rom, 0x0EF6, 0x0F10)
    preserves = {
        "play_sfx_saves_d2_d4": any(
            x.mnemonic == "movem.l" and x.op_str.lower() == "d2-d4, -(a7)"
            for x in sfx
        ),
        "play_sfx_restores_d2_d4": any(
            x.mnemonic == "movem.l" and x.op_str.lower() == "(a7)+, d2-d4"
            for x in sfx
        ),
        "play_sfx_ex_saves_d0_d5": any(
            x.mnemonic == "movem.l" and x.op_str.lower() == "d0-d5, -(a7)"
            for x in sfx_ex
        ),
        "play_sfx_ex_restores_d0_d5": any(
            x.mnemonic == "movem.l" and x.op_str.lower() == "(a7)+, d0-d5"
            for x in sfx_ex
        ),
    }
    if not all(preserves.values()):
        raise ValueError("original Sona_PlaySfx wrapper callee-save guard changed")

    native_smoke = None
    if native_smoke_path:
        if candidate_path is None:
            raise ValueError("--native-smoke-receipt requires --candidate-receipt")
        candidate = json.loads(candidate_path.read_text())
        smoke = json.loads(native_smoke_path.read_text())
        current_sources = {
            "adapter_c_sha256": sha(
                (Path(__file__).resolve().parents[1] /
                 "src/fdisbull/game_sources/genesis_game_audio.c").read_bytes()
            ),
            "adapter_asm_sha256": sha(
                (Path(__file__).resolve().parents[1] /
                 "src/fdisbull/game_sources/genesis_game_audio.S").read_bytes()
            ),
        }
        if (candidate.get("source_rom_sha256") != ROM_SHA256 or
                any(candidate.get(key) != value for key, value in current_sources.items()) or
                candidate.get("private_only") is not True or
                smoke.get("format") != "fdisbull-genesis-audio-abi-native-smoke-1" or
                smoke.get("core_sha256") != CORE_SHA256 or
                smoke.get("rom_sha256") != candidate.get("candidate_sha256") or
                smoke.get("register_mismatch_flags") != 0 or
                not all(smoke.get(key) is True for key in
                        ("bgm_status_seen", "sfx1_status_seen",
                         "audio_busy_seen")) or
                smoke.get("audio_samples", 0) <= 0 or
                smoke.get("main_loop_marker") != 1):
            raise ValueError("native adapter smoke or source binding is incomplete")
        readback = smoke.get("readback", {})
        if any(readback.get("result_" + str(i)) != 0 for i in range(5, 10)):
            raise ValueError("native smoke detected a callee-saved register change")
        native_smoke = {
            "complete": True,
            "core_sha256": CORE_SHA256,
            "rom_sha256": smoke["rom_sha256"],
            "frames": smoke.get("frames"),
            "audio_samples": smoke.get("audio_samples"),
            "audio_peak": smoke.get("audio_peak"),
            "register_mismatch_flags": 0,
            "bgm_status_seen": True,
            "sfx1_status_seen": True,
            "audio_busy_seen": True,
        }

    code = rom[SONA_ENTRY:SONA_CODE_END]
    blob = rom[SONA_BLOB_START:SONA_BLOB_END]
    if len(blob) != 0x1380:
        raise ValueError("unexpected original Sona Z80 blob extent")
    return {
        "format": "fdisbull-genesis-audio-source-binding-1",
        "complete": True,
        "original_rom_sha256": ROM_SHA256,
        "pinned_core_sha256": CORE_SHA256,
        "native_init_probe": {
            "complete": True,
            "entry": SONA_ENTRY,
            "instructions": case.get("instructions_executed"),
            "master_cycles": case.get("master_cycles"),
            "returned": True,
        },
        "driver": {
            "provenance": "original Sona 0.50 routines retained at source addresses",
            "code_range": [SONA_ENTRY, SONA_CODE_END],
            "code_sha256": sha(code),
            "blob_range": [SONA_BLOB_START, SONA_BLOB_END],
            "blob_bytes": len(blob),
            "blob_sha256": sha(blob),
        },
        "entrypoints": {
            "init": SONA_ENTRY,
            "play_bgm": 0x0ED0,
            "play_sfx": 0x0EE4,
            "stop_all": 0x0F2C,
            "get_status": 0x0FB6,
        },
        "original_asset_tables": {
            "bgm_list": 0x04C458,
            "bgm_count": len(bgm_targets),
            "sfx_list": 0x054FE2,
            "sfx_count": len(sfx_targets),
            "instrument_list": 0x0554F4,
            "instrument_count": len(instrument_targets),
            "all_pointer_targets_match_qualified_source_ranges": True,
        },
        "original_call_sites": calls,
        "abi_checks": checks,
        "callee_saved_guards": preserves,
        "native_adapter_smoke": native_smoke,
        "limits": [
            "qualifies original driver source addresses and its initializer boundary",
            "does not certify new-ROM startup or audio-output parity",
            "stream, instrument, PCM and Z80 blob bytes remain private external inputs",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", required=True, type=Path)
    parser.add_argument("--probe-receipt", required=True, type=Path)
    parser.add_argument("--candidate-receipt", type=Path)
    parser.add_argument("--native-smoke-receipt", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error("output must be a fresh file and its parent must exist")
    receipt = check(
        args.rom, args.probe_receipt, args.candidate_receipt,
        args.native_smoke_receipt
    )
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
