"""Pair original Doom's protected offset32 capture with an independent DOSBox GDT read."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

import pytest

from support.doom_le_qemu import CODE_OFFSET, DATA_OFFSET, PINS


def phases(stage, backend):
    helper = Path(__file__).parent / "support" / f"doom_le_{backend}.py"
    results = []
    for phase in ("hot", "cold"):
        subprocess.run([sys.executable, str(helper), str(stage), phase], check=True, timeout=180)
        results.append(json.loads((stage / f"{backend}-{phase}.json").read_bytes()))
    return results


def test_paired_doom_le_public_capture_fixup_and_cold_restore(tmp_path):
    if os.environ.get("FDISBULL_REQUIRE_DOOM_LE_PAIRED") != "1":
        pytest.skip("Supply the private Doom LE native profile to run this comparison")
    source = Path(os.environ["FDISBULL_DOOM_LE_SOURCE"])
    originals = {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in PINS}
    assert originals == PINS
    raw = (source / "DOOM.EXE").read_bytes()
    qemu_stage = tmp_path / "qemu"
    qemu = phases(qemu_stage, "qemu")
    dosbox = phases(tmp_path / "dosbox", "dosbox")
    assert dosbox[0] == dosbox[1]
    assert qemu[0]["analysis"]["artifact"] != qemu[1]["analysis"]["artifact"]
    for captured, ref in zip(qemu, dosbox):
        analysis = captured["analysis"]
        location = analysis["source_location"]
        assert analysis["source_sha256"] == ref["source_sha256"] == originals["DOOM.EXE"]
        assert location["object_index"] == ref["object_index"] == 1
        assert location["object_offset"] == ref["object_offset"] == CODE_OFFSET
        assert location["preferred_address"] == ref["preferred_address"]
        fixup, = analysis["fixups"]
        off = fixup["record_file_offset"]
        assert off == ref["fixup_record_file_offset"]
        # Decode the four independently stored LE record fields and target ordinal.
        kind, flags, src_off, obj, target = struct.unpack_from("<BBhBI", raw, off)
        assert (kind, flags, src_off) == (7, 0x10, (CODE_OFFSET + 2) % 4096)
        assert obj == fixup["target_object"] == ref["target_object"] == 3
        assert target == fixup["target_offset"] == ref["target_offset"] == DATA_OFFSET
        assert analysis["canonical_bytes"] == ref["canonical_bytes"]
        source_word, = fixup["source_file_fragments"]
        assert source_word["size"] == 4 and source_word["word_offset"] == 0
        assert bytes.fromhex(analysis["canonical_bytes"])[:2] == raw[source_word["file_offset"]-2:source_word["file_offset"]]
        assert int.from_bytes(bytes.fromhex(fixup["runtime_hex"]), "little") == captured["target"]
        assert int.from_bytes(bytes.fromhex(ref["runtime_bytes"])[2:], "little") == ref["runtime_target"]
        sel = analysis["selector"]
        assert sel["cs"] == ref["cs"] and sel["cs_base"] == ref["cs_base"] and sel["cs_limit"] == ref["cs_limit"]
        assert sel["cs_base"] + int(analysis["instruction_selector_offset"], 16) == captured["pc"]
        descriptor = bytes.fromhex(ref["descriptor_hex"])
        # The access bit may be set by the CPU on a descriptor read.
        assert (sel["cs_attributes"] >> 8) & 0xfe == descriptor[5] & 0xfe
        assert (sel["cs_attributes"] >> 16) & 0xf0 == descriptor[6] & 0xf0
        assert sel["ip"] == int(analysis["instruction_selector_offset"], 16)
        assert not analysis["execution_proven"]
        # Exercise one-shot public routing with both emulator processes closed.
        output = subprocess.check_output([sys.executable, "-m", "fdisbull", "debug-analyze-le-code",
                                          str(qemu_stage / "doom.fdb"), analysis["artifact"]], text=True)
        reply = json.loads(output)
        assert reply["ok"] and reply["result"] == analysis
    assert {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in PINS} == originals
