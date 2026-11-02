"""Bounded SH-2 decoding using a separately installed Ghidra headless runtime."""

from __future__ import annotations

import hashlib
import json
import math
import os
import signal
from pathlib import Path
import subprocess
import tempfile
import threading
import time


def decode(data: bytes, base_address: int, max_instructions: int, *,
           ghidra_home: str | None = None, timeout: float = 60.0,
           scan_all_words: bool = False, session: "GhidraDecodeSession | None" = None) -> dict:
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
    if session is not None:
        return session.decode(data, base_address, max_instructions, scan_all_words=scan_all_words, timeout=timeout)
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
            rows, decode_seconds = _validate_payload(payload, data, base_address, max_instructions, scan_all_words)
        except (ValueError, TypeError, KeyError, OSError) as exc:
            raise RuntimeError(f"Invalid Ghidra output: {exc}") from exc
    return {"instructions": rows, "elapsed_seconds": time.monotonic() - started,
            "engine_version": version, "engine_identity": identity, "diagnostics": [], "decode_seconds": decode_seconds}


def _validate_payload(payload, data, base_address, max_instructions, scan_all_words):
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
    return rows, decode_seconds


class GhidraDecodeSession:
    """Own one headless Ghidra process; close it after the bounded work is done."""

    def __init__(self, *, ghidra_home: str | None = None, timeout: float = 60.0):
        _validate_session_timeout(timeout)
        self.ghidra_home = ghidra_home
        self.timeout = timeout
        self._proc = None
        self._tmp = None
        self._counter = 0
        self._lock = threading.Lock()
        self.startup_seconds = None

    def __enter__(self):
        if self._tmp is not None:
            raise RuntimeError("Ghidra session is already started")
        # Validate the installation and obtain the exact identity without launching Ghidra.
        metadata = decode(b"", 0, 0, ghidra_home=self.ghidra_home, timeout=self.timeout)
        self.engine_version = metadata["engine_version"]
        self.engine_identity = metadata["engine_identity"]
        home = Path(self.ghidra_home or os.environ.get("GHIDRA_HOME", ""))
        temporary_root = Path(tempfile.gettempdir()).resolve()
        if any((p / ".git").exists() for p in (temporary_root, *temporary_root.parents)):
            raise RuntimeError("Ghidra temporary input must be outside Git; select a private TMPDIR")
        self._tmp = tempfile.TemporaryDirectory(prefix="fdisbull-ghidra-session-")
        self._root = Path(self._tmp.name)
        image = self._root / "initial.bin"
        image.write_bytes(b"\x00\x09")
        scripts = Path(__file__).resolve().parent / "ghidra_scripts"
        cmd = [str(home / "support" / "analyzeHeadless"), str(self._root), "project",
               "-import", str(image), "-loader", "BinaryLoader", "-loader-baseAddr", "0x0",
               "-processor", "SuperH:BE:32:SH-2", "-noanalysis", "-scriptPath", str(scripts),
               "-postScript", "RomAsmServer.java", str(self._root)]
        started = time.monotonic()
        try:
            self._log = (self._root / "headless.log").open("w+")
            self._proc = subprocess.Popen(cmd, stdout=self._log, stderr=subprocess.STDOUT,
                                          start_new_session=(os.name == "posix"))
            self._wait_for(self._root / "ready", self.timeout)
            self.startup_seconds = time.monotonic() - started
            return self
        except BaseException:
            self.close()
            raise

    def _wait_for(self, path, timeout):
        deadline = time.monotonic() + timeout
        while not path.exists():
            if self._proc.poll() is not None:
                self._log.flush()
                detail = (self._root / "headless.log").read_text(errors="replace")[-4000:]
                raise RuntimeError(f"Ghidra session exited ({self._proc.returncode}): {detail}")
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Ghidra session timed out after {timeout} seconds")
            time.sleep(0.01)

    def decode(self, data, base_address, max_instructions, *, scan_all_words=False, timeout=None):
        """Decode with a timeout covering both queue wait and worker execution."""
        effective_timeout = self.timeout if timeout is None else timeout
        _validate_session_timeout(effective_timeout)
        started = time.monotonic()
        if not self._lock.acquire(timeout=effective_timeout):
            raise RuntimeError("Ghidra session timed out waiting for another request")
        try:
            remaining = effective_timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise RuntimeError("Ghidra session timed out waiting for another request")
            result = self._decode(data, base_address, max_instructions, scan_all_words=scan_all_words, timeout=remaining)
            result["elapsed_seconds"] = time.monotonic() - started
            return result
        finally:
            self._lock.release()

    def _decode(self, data, base_address, max_instructions, *, scan_all_words=False, timeout=None):
        if self._proc is None or self._proc.poll() is not None:
            raise RuntimeError("Ghidra session is not running")
        if not isinstance(data, bytes) or len(data) > 65536 or type(base_address) is not int or not 0 <= base_address <= 0xffffffff:
            raise ValueError("invalid SH-2 image or base address")
        if base_address & 1 or base_address + len(data) > 0x100000000:
            raise ValueError("SH-2 image must be aligned and fit in its 32-bit address space")
        if type(max_instructions) is not int or not 0 <= max_instructions <= 32768 or not isinstance(scan_all_words, bool):
            raise ValueError("invalid instruction budget or scan mode")
        if timeout is not None:
            _validate_session_timeout(timeout)
        started = time.monotonic()
        if not data or not max_instructions:
            return {"instructions": [], "elapsed_seconds": time.monotonic() - started,
                    "engine_version": self.engine_version, "engine_identity": self.engine_identity,
                    "diagnostics": [], "decode_seconds": 0.0, "startup_seconds": self.startup_seconds}
        self._counter += 1
        request = self._root / "request"
        response = self._root / "response"
        try:
            content = f"{self._counter}\n{base_address:x}\n{data.hex()}\n{max_instructions}\n{str(scan_all_words).lower()}\n{hashlib.sha256(data).hexdigest()}\nend"
            temp = self._root / "request.tmp"
            temp.write_text(content)
            temp.replace(request)
            self._wait_for(response, self.timeout if timeout is None else timeout)
            raw = response.read_text()
            response.unlink()
            ident, payload_text = raw.split("\n", 1)
            if ident != str(self._counter) or payload_text.startswith("ERROR "):
                raise ValueError(f"invalid response: {payload_text[:500]}")
            rows, seconds = _validate_payload(json.loads(payload_text), data, base_address,
                                               max_instructions, scan_all_words)
        except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
            self.close()
            raise RuntimeError(f"Ghidra session request failed: {exc}") from exc
        except BaseException:
            self.close()
            raise
        return {"instructions": rows, "elapsed_seconds": time.monotonic() - started,
                "engine_version": self.engine_version, "engine_identity": self.engine_identity,
                "diagnostics": [], "decode_seconds": seconds, "startup_seconds": self.startup_seconds}

    def close(self):
        proc, self._proc = self._proc, None
        if proc is not None:
            if proc.poll() is None:
                if os.name == "posix":
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    proc.kill()
            proc.wait()
        if getattr(self, "_log", None):
            self._log.close()
            self._log = None
        if self._tmp is not None:
            self._tmp.cleanup()
            self._tmp = None

    def __exit__(self, *args):
        self.close()


def _validate_session_timeout(timeout):
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 3600:
        raise ValueError("session timeout must be finite and between 0 and 3600 seconds")
