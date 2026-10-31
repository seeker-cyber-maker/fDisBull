"""Native Capstone SH-2 instruction facts, with skip-data disabled."""
from __future__ import annotations

import time
from importlib.metadata import version
import hashlib
from pathlib import Path


def decode(data: bytes, base_address: int, max_instructions: int, *,
           timeout: float = 60.0, scan_all_words: bool = False) -> dict:
    import capstone

    started = time.perf_counter()
    decoder = capstone.Cs(capstone.CS_ARCH_SH, capstone.CS_MODE_SH2 | capstone.CS_MODE_BIG_ENDIAN)
    native = Path(capstone._cs._name)
    identity = {"distribution_version": version("capstone"), "binding_version": capstone.__version__,
                "native_api_version": list(capstone.cs_version()),
                "native_library_sha256": hashlib.sha256(native.read_bytes()).hexdigest()}
    rows = []
    decode_started = time.perf_counter()
    for offset in range(0, min(len(data) // 2, max_instructions) * 2, 2):
        if time.perf_counter() - started > timeout:
            raise RuntimeError(f"Capstone decoding timed out after {timeout} seconds")
        ins = next(decoder.disasm(data[offset:offset + 2], base_address + offset, count=1), None)
        if ins is None:
            if scan_all_words:
                continue
            break
        rows.append({"address": ins.address, "size": ins.size, "bytes": bytes(ins.bytes).hex(),
                     "mnemonic": ins.mnemonic, "operands": ins.op_str})
    return {"instructions": rows, "elapsed_seconds": time.perf_counter() - started,
            "decode_seconds": time.perf_counter() - decode_started,
            "engine_version": f"Capstone distribution {version('capstone')}; bindings {capstone.__version__}; native {capstone.cs_version()}",
            "engine_identity": identity,
            "diagnostics": []}
