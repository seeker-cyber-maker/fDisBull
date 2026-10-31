"""Interchangeable, bounded SH-2 decode proposals from explicitly mapped bytes.

This seam does not discover executable mappings or insert instructions into the
persistent analyzer. A successful decode is not evidence that a word is code.
"""
from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
import re
import stat
import time

BACKENDS = ("capstone", "ghidra", "saturn-recomp")
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_RANGE_BYTES = 65536
MAX_INSTRUCTIONS = MAX_RANGE_BYTES // 2


def _integer(name, value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in {minimum}..{maximum}")


def normalize_instruction(mnemonic: str, operands: str, *, dialect: str | None = None) -> dict:
    """Normalize spelling only; do not repair an engine's decoded semantics.

    Ghidra prefixes delay-slot mnemonics with '_'. Hex/decimal formatting,
    whitespace, case and BT/BF delayed-branch spellings have no semantic force.
    Ghidra prints resolved PC-relative addresses inside @(address,pc), and omits
    '#' on some immediate operands. Normalize those documented renderings, not
    their values. Unrecognized syntax remains visible for comparison.
    """
    name = mnemonic.lower().lstrip("_")
    name = {"bt.s": "bt/s", "bf.s": "bf/s"}.get(name, name)
    text = re.sub(r"\s+", "", operands.lower())
    text = re.sub(r"(?<![a-z0-9_])(-?(?:0x[0-9a-f]+|[0-9]+))(?![a-z0-9_])",
                  lambda m: str(int(m.group(), 16 if "x" in m.group() else 10)), text)
    if dialect == "ghidra":
        if name in ("mov.w", "mov.l", "mova"):
            text = re.sub(r"@\(([0-9]+),pc\)", r"\1", text)
        if name in ("mov", "add", "cmp/eq", "and", "or", "xor", "tst", "trapa",
                    "and.b", "or.b", "xor.b", "tst.b") and re.match(r"^-?[0-9]+(?:,|$)", text):
            text = "#" + text
    return {"mnemonic": name, "operands": text}


def disassemble_rom(data: bytes, *, base_address: int, backend: str = "capstone",
                    arch: str = "sh2", offset: int = 0, length: int | None = None,
                    max_instructions: int = 256, mode: str = "linear",
                    ghidra_home: str | None = None,
                    saturn_recomp_root: str | None = None,
                    timeout: float = 60.0) -> dict:
    """Decode one explicitly mapped range; all engines receive identical bytes.

    ``base_address`` maps source offset zero. ``linear`` stops before the first
    undecodable word. ``word-scan`` tries each aligned word independently and
    retains unknown positions. Both are static proposals, not code discovery.
    The instruction budget counts attempted word positions in word-scan mode.
    """
    started = time.perf_counter()
    if not isinstance(data, bytes) or not 1 <= len(data) <= MAX_SOURCE_BYTES:
        raise ValueError("data must be immutable bytes containing 1..64 MiB")
    if backend not in BACKENDS:
        raise ValueError(f"backend must be one of {BACKENDS}")
    if arch != "sh2":
        raise ValueError("ROM-to-ASM currently supports explicitly mapped big-endian SH-2 only")
    if mode not in ("linear", "word-scan"):
        raise ValueError("mode must be linear or word-scan")
    _integer("base_address", base_address, 0, 0xffffffff)
    _integer("offset", offset, 0, len(data) - 1)
    _integer("max_instructions", max_instructions, 1, MAX_INSTRUCTIONS)
    if base_address % 2 or offset % 2 or base_address + len(data) > 0x100000000:
        raise ValueError("SH-2 mapping must be even-aligned and fit the 32-bit address space")
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or not 0 < timeout <= 3600):
        raise ValueError("timeout must be finite and in (0, 3600] seconds")
    if length is None:
        length = min(len(data) - offset, max_instructions * 2)
    _integer("length", length, 1, MAX_RANGE_BYTES)
    if offset + length > len(data):
        raise ValueError("requested range exceeds source bytes")
    selected = data[offset:offset + length]
    address = base_address + offset
    kwargs = {"timeout": timeout, "scan_all_words": mode == "word-scan"}
    if backend == "capstone":
        from .rom_asm_capstone import decode
    elif backend == "ghidra":
        from .rom_asm_ghidra import decode
        kwargs["ghidra_home"] = ghidra_home
    else:
        from .rom_asm_saturn import decode
        kwargs["saturn_recomp_root"] = saturn_recomp_root
    result = decode(selected, address, max_instructions, **kwargs)
    candidate_count = min(length // 2, max_instructions)
    instructions = []
    previous = -1
    for row in result["instructions"]:
        relative = row["address"] - address
        if (type(relative) is not int or relative % 2 or relative <= previous
                or not 0 <= relative < candidate_count * 2 or row["size"] != 2
                or row["bytes"] != selected[relative:relative + 2].hex()
                or not isinstance(row["mnemonic"], str) or not row["mnemonic"]
                or not isinstance(row["operands"], str)
                or (mode == "linear" and relative != len(instructions) * 2)):
            raise RuntimeError(f"Invalid {backend} instruction facts")
        previous = relative
        instructions.append({**row, "file_offset": offset + relative,
                             "classification": "unconfirmed decode proposal",
                             "normalized": normalize_instruction(row["mnemonic"], row["operands"], dialect=backend)})
    known = {x["address"] for x in instructions}
    attempted = candidate_count if mode == "word-scan" else min(candidate_count, len(instructions) + 1)
    unknown = [{"file_offset": offset + i * 2, "address": address + i * 2,
                "bytes": selected[i * 2:i * 2 + 2].hex(), "reason": "engine did not decode SH-2 word"}
               for i in range(attempted) if address + i * 2 not in known]
    budget_stop = length // 2 > max_instructions and not (mode == "linear" and unknown)
    trailing = bool(length % 2) and attempted == length // 2 and not budget_stop and not (mode == "linear" and unknown)
    stop = ("unknown_word" if mode == "linear" and unknown else "instruction_budget" if budget_stop
            else "truncated_word" if trailing else "range_end")
    complete = not unknown and not trailing and not budget_stop
    return {
        "report_format": "fdisbull-rom-asm-1", "backend": backend,
        "engine_version": result["engine_version"], "arch": "sh2", "bits": 32, "endian": "big",
        "engine_identity": result.get("engine_identity", {}),
        "mode": mode, "source_size": len(data), "source_sha256": hashlib.sha256(data).hexdigest(),
        "mapping": {"base_address": base_address, "file_offset": offset, "address": address,
                    "length": length, "provenance": "caller-supplied static mapping; not execution evidence"},
        "range_sha256": hashlib.sha256(selected).hexdigest(), "max_instructions": max_instructions,
        "attempted_words": attempted, "decoded_words": len(instructions),
        "instructions": instructions, "undecoded_words": unknown,
        "complete_scope": complete, "status": "complete" if complete else "partial",
        "stop_reason": stop, "trailing_bytes": selected[-1:].hex() if trailing else "",
        "backend_elapsed_seconds": result["elapsed_seconds"],
        "decode_seconds": result.get("decode_seconds"),
        "elapsed_seconds": time.perf_counter() - started,
        "executed": False, "code_discovered": False, "persisted": False,
        "diagnostics": result.get("diagnostics", []),
        "validation_scope": "bounded static instruction decoding; agreement does not prove code or semantics",
    }


def disassemble_rom_path(path: str | Path, **kwargs) -> dict:
    """Read one bounded regular file and bind output to its complete byte hash."""
    path = Path(path)
    if not path.is_file():
        raise ValueError("ROM-to-ASM requires one regular file")
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= MAX_SOURCE_BYTES:
            raise ValueError("ROM-to-ASM requires one nonempty regular file at most 64 MiB")
        data = stream.read(MAX_SOURCE_BYTES + 1)
        after = os.fstat(stream.fileno())
        current = path.stat()
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if identity(before) != identity(after) or identity(after) != identity(current) or len(data) != before.st_size:
            raise ValueError("input changed during ROM-to-ASM read")
    return disassemble_rom(data, **kwargs)
