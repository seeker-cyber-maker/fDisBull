"""Bounded SH-2 decoding using a separately installed Ghidra headless runtime."""

from __future__ import annotations

import hashlib
import json
import os
import signal
from pathlib import Path
import subprocess
import tempfile
import time


def decode(data: bytes, base_address: int, max_instructions: int, *,
           ghidra_home: str | None = None, timeout: float = 60.0,
           scan_all_words: bool = False) -> dict:
    """Decode consecutive big-endian SH-2 instructions from a private raw image."""
    started = time.monotonic()
    if not isinstance(data, bytes):
        raise ValueError("data must be bytes")
    if not isinstance(base_address, int) or not 0 <= base_address <= 0xffffffff:
        raise ValueError("base_address must be a 32-bit unsigned address")
    if base_address & 1 or base_address + len(data) > 0x100000000:
        raise ValueError("SH-2 image must be aligned and fit in its 32-bit address space")
    if not isinstance(max_instructions, int) or max_instructions < 0:
        raise ValueError("max_instructions must be non-negative")
    if not isinstance(scan_all_words, bool):
        raise ValueError("scan_all_words must be a boolean")
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    home = Path(ghidra_home or os.environ.get("GHIDRA_HOME", ""))
    headless = home / "support" / "analyzeHeadless"
    props = home / "Ghidra" / "application.properties"
    if not headless.is_file() or not props.is_file():
        raise RuntimeError("Ghidra installation unavailable: specify ghidra_home or GHIDRA_HOME")
    version = next((line.split("=", 1)[1].strip() for line in props.read_text().splitlines()
                    if line.startswith("application.version=")), None)
    if not version:
        raise RuntimeError("Ghidra application version is unavailable")
    language = home / "Ghidra" / "Processors" / "SuperH" / "data" / "languages" / "sh-2.sla"
    if not language.is_file():
        raise RuntimeError("Ghidra SH-2 language definition is unavailable")
    try:
        identity = {"application_properties_sha256": hashlib.sha256(props.read_bytes()).hexdigest(),
                    "sh2_sla_sha256": hashlib.sha256(language.read_bytes()).hexdigest(),
                    "headless_launcher_sha256": hashlib.sha256(headless.read_bytes()).hexdigest()}
    except OSError as exc:
        raise RuntimeError(f"Cannot read Ghidra engine identity: {exc}") from exc
    if not data or not max_instructions:
        return {"instructions": [], "elapsed_seconds": time.monotonic() - started,
                "engine_version": version, "engine_identity": identity, "diagnostics": [], "decode_seconds": 0.0}
    script_dir = Path(__file__).resolve().parent / "ghidra_scripts"
    if not (script_dir / "RomAsm.java").is_file():
        raise RuntimeError("Ghidra RomAsm script is unavailable")
    temporary_root = Path(tempfile.gettempdir()).resolve()
    if any((p / ".git").exists() for p in (temporary_root, *temporary_root.parents)):
        raise RuntimeError("Ghidra temporary input must be outside Git; select a private TMPDIR")
    with tempfile.TemporaryDirectory(prefix="fdisbull-ghidra-") as tmp:
        root = Path(tmp)
        image = root / "image.bin"
        result = root / "result.json"
        image.write_bytes(data)
        cmd = [str(headless), str(root), "project", "-import", str(image),
               "-loader", "BinaryLoader", "-loader-baseAddr", hex(base_address),
               "-processor", "SuperH:BE:32:SH-2", "-noanalysis",
               "-scriptPath", str(script_dir), "-postScript", "RomAsm.java",
               str(result), format(base_address, "x"), str(len(data)), str(max_instructions),
               str(scan_all_words).lower()]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, start_new_session=(os.name == "posix"))
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                if os.name == "posix":
                    os.killpg(proc.pid, signal.SIGKILL)
                else:
                    proc.kill()
                proc.communicate()
                raise RuntimeError(f"Ghidra headless timed out after {timeout} seconds") from exc
        except OSError as exc:
            raise RuntimeError(f"Cannot start Ghidra headless: {exc}") from exc
        if proc.returncode or not result.is_file():
            detail = (stderr + "\n" + stdout)[-4000:]
            raise RuntimeError(f"Ghidra headless failed (exit {proc.returncode}): {detail}")
        try:
            payload = json.loads(result.read_text())
            rows = payload["instructions"]
            decode_seconds = payload["decode_seconds"]
            if not isinstance(decode_seconds, (int, float)) or not 0 <= decode_seconds < float("inf"):
                raise ValueError("invalid decode time")
            if not isinstance(rows, list) or len(rows) > max_instructions:
                raise ValueError("unexpected instruction list")
            offset = 0
            for row in rows:
                size = row["size"]
                row_offset = row["address"] - base_address
                if (not isinstance(size, int) or size != 2 or
                    (row_offset < offset if scan_all_words else row_offset != offset) or
                    row_offset % 2 or row_offset + size > len(data) or
                    (scan_all_words and row_offset // 2 >= max_instructions) or
                    row["bytes"] != data[row_offset:row_offset + size].hex() or
                    not isinstance(row["mnemonic"], str) or not isinstance(row["operands"], str)):
                    raise ValueError("invalid instruction row")
                offset = row_offset + size
        except (ValueError, TypeError, KeyError, OSError) as exc:
            raise RuntimeError(f"Invalid Ghidra output: {exc}") from exc
    return {"instructions": rows, "elapsed_seconds": time.monotonic() - started,
            "engine_version": version, "engine_identity": identity, "diagnostics": [], "decode_seconds": decode_seconds}
