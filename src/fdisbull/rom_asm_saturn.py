"""Bounded SH-2 decoding through a pinned, separately obtained saturn-recomp checkout.

The upstream SH7604 decoder is MIT licensed; it is not distributed here.
"""
from __future__ import annotations

import json
import hashlib
import math
import os
from pathlib import Path
import subprocess
import sys
import time

SATURN_RECOMP_REVISION = "532fd6054ba3171339c972fab05ebd159f29260d"

# Run under -I, explicitly adding only the selected checkout. No installed
# saturnrecomp package is used. The decoder returns .word for unknown words.
_WORKER = r'''
import json, sys, time
sys.path.insert(0, sys.argv[1])
from saturnrecomp import sh2
request = json.load(sys.stdin)
data = bytes.fromhex(request["data"])
base = request["base"]
rows = []
unknown = None
started = time.perf_counter()
for offset in range(0, len(data) - 1, 2):
    word = int.from_bytes(data[offset:offset + 2], "big")
    ins = sh2.decode(word, base + offset)
    if ins.op == ".word":
        if unknown is None:
            unknown = {"address": base + offset, "text": ins.text}
        if request["scan_all_words"]:
            continue
        break
    parts = ins.text.split(None, 1)
    rows.append({"address": base + offset, "size": 2,
                 "bytes": data[offset:offset + 2].hex(),
                 "mnemonic": parts[0], "operands": parts[1] if len(parts) > 1 else ""})
decode_seconds = time.perf_counter() - started
json.dump({"instructions": rows, "unknown": unknown, "decode_seconds": decode_seconds}, sys.stdout)
'''


def decode(data: bytes, base_address: int, max_instructions: int, *,
           saturn_recomp_root: str | None = None, timeout: float = 60.0,
           scan_all_words: bool = False) -> dict:
    """Decode sequential big-endian SH-2 words, stopping before an unknown word."""
    started = time.monotonic()
    if not isinstance(data, bytes):
        raise ValueError("data must be bytes")
    if type(base_address) is not int or not 0 <= base_address <= 0xffffffff:
        raise ValueError("base_address must be a 32-bit unsigned address")
    if base_address & 1 or base_address + len(data) > 0x100000000:
        raise ValueError("SH-2 image must be aligned and fit in its 32-bit address space")
    if type(max_instructions) is not int or max_instructions < 0:
        raise ValueError("max_instructions must be non-negative")
    if type(scan_all_words) is not bool:
        raise ValueError("scan_all_words must be a boolean")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be a finite positive number")
    selected = saturn_recomp_root or os.environ.get("SATURN_RECOMP_ROOT")
    if not selected:
        raise RuntimeError("saturn-recomp unavailable: specify saturn_recomp_root or SATURN_RECOMP_ROOT")
    root = Path(selected).expanduser().resolve()
    if not (root / "src/saturnrecomp/sh2.py").is_file():
        raise RuntimeError("saturn-recomp unavailable: selected checkout lacks src/saturnrecomp/sh2.py")

    def run(args: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess:
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0:
            raise RuntimeError(f"saturn-recomp timed out after {timeout} seconds")
        try:
            return subprocess.run(args, input=input_text, capture_output=True, text=True,
                                  timeout=remaining, check=False, cwd=root)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"saturn-recomp timed out after {timeout} seconds") from exc
        except OSError as exc:
            raise RuntimeError(f"Cannot start saturn-recomp process: {exc}") from exc

    rev = run(["git", "rev-parse", "HEAD"])
    if rev.returncode or rev.stdout.strip() != SATURN_RECOMP_REVISION:
        raise RuntimeError(f"saturn-recomp checkout must be at pinned revision {SATURN_RECOMP_REVISION}")
    status = run(["git", "status", "--porcelain", "--", "src/saturnrecomp"])
    if status.returncode or status.stdout.strip():
        raise RuntimeError("saturn-recomp decoder checkout has uncommitted changes or cannot be verified")
    version = f"saturn-recomp 0.1.0 ({SATURN_RECOMP_REVISION})"
    bounded = data[:max_instructions * 2]
    request = json.dumps({"data": bounded.hex(), "base": base_address, "scan_all_words": scan_all_words})
    proc = run([sys.executable, "-I", "-c", _WORKER, str(root / "src")], input_text=request)
    if proc.returncode:
        raise RuntimeError(f"saturn-recomp decoder failed (exit {proc.returncode}): {proc.stderr[-4000:]}")
    try:
        result = json.loads(proc.stdout)
        rows = result["instructions"]
        unknown = result["unknown"]
        decode_seconds = result["decode_seconds"]
        if not isinstance(decode_seconds, (int, float)) or not math.isfinite(decode_seconds) or decode_seconds < 0:
            raise ValueError("invalid decoder timing")
        if not isinstance(rows, list) or len(rows) > min(max_instructions, len(data) // 2):
            raise ValueError("unexpected instruction count")
        previous_offset = -2
        for index, row in enumerate(rows):
            if not isinstance(row, dict) or type(row.get("address")) is not int:
                raise ValueError("invalid instruction row")
            offset = row["address"] - base_address
            if (offset % 2 or offset <= previous_offset or offset + 2 > len(bounded)
                    or (not scan_all_words and offset != index * 2)):
                raise ValueError("invalid instruction address")
            previous_offset = offset
            if (not isinstance(row, dict) or row["address"] != base_address + offset
                    or row["size"] != 2 or row["bytes"] != data[offset:offset + 2].hex()
                    or not isinstance(row["mnemonic"], str) or not row["mnemonic"]
                    or not isinstance(row["operands"], str)):
                raise ValueError("invalid instruction row")
        diagnostics = []
        if unknown is not None:
            if (not isinstance(unknown, dict) or (type(unknown.get("address")) is not int
                        or unknown["address"] < base_address
                        or unknown["address"] >= base_address + len(bounded) - 1
                        or (unknown["address"] - base_address) % 2
                        or (not scan_all_words and unknown["address"] != base_address + len(rows) * 2))
                    or not isinstance(unknown["text"], str) or not unknown["text"].startswith(".word ")):
                raise ValueError("invalid unknown instruction")
            diagnostics.append(f"Unknown instruction at 0x{unknown['address']:08x}: {unknown['text']}")
        if len(bounded) % 2 and (scan_all_words or len(rows) == len(bounded) // 2):
            diagnostics.append(f"Trailing incomplete byte at 0x{base_address + len(bounded) - 1:08x}")
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Invalid saturn-recomp decoder output: {exc}") from exc
    identity = {"revision": SATURN_RECOMP_REVISION,
                "sh2_py_sha256": hashlib.sha256((root / "src/saturnrecomp/sh2.py").read_bytes()).hexdigest(),
                "hw_py_sha256": hashlib.sha256((root / "src/saturnrecomp/hw.py").read_bytes()).hexdigest()}
    return {"instructions": rows, "elapsed_seconds": time.monotonic() - started,
            "engine_version": version, "diagnostics": diagnostics, "decode_seconds": decode_seconds,
            "engine_identity": identity}
