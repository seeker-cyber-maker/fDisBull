"""Native Capstone SH-2 instruction facts, with skip-data disabled."""
from __future__ import annotations

import time
from importlib.metadata import version
import hashlib
from pathlib import Path


# Capstone 5.0.9 tests the sign of the selected ISA level instead of the
# signed level in its lookup tables. These encodings are the SH2-ineligible
# entries admitted by that defect, including SH2A and SH4A-only forms. The
# native fact is retained in diagnostics; it is never rewritten as SH-2.
# Cross-checked against the source patch over every 16-bit word.
_PROFILE_EXACT = frozenset((0x005b, 0x0068, 0x006b, 0x00ab))
_PROFILE_REGISTER_FORMS = frozenset((
    0x0039, 0x004a, 0x007b, 0x4042, 0x4046, 0x404a, 0x404b,
    0x4080, 0x4081, 0x4084, 0x4085, 0x408b, 0x40cb, 0x4091,
    0x4094, 0x4095, 0x409b, 0x40db, 0x40a9, 0x40e9, 0x40ab,
    0x40eb, 0x40e1, 0x40e5, 0x40f0, 0x40f4, 0x40f1, 0x40f5,
))


def _outside_sh2_profile(word: int) -> bool:
    return word in _PROFILE_EXACT or (word & 0xf0ff) in _PROFILE_REGISTER_FORMS


def decode(data: bytes, base_address: int, max_instructions: int, *,
           timeout: float = 60.0, scan_all_words: bool = False) -> dict:
    import capstone

    started = time.perf_counter()
    decoder = capstone.Cs(capstone.CS_ARCH_SH, capstone.CS_MODE_SH2 | capstone.CS_MODE_BIG_ENDIAN)
    native = Path(capstone._cs._name)
    identity = {"distribution_version": version("capstone"), "binding_version": capstone.__version__,
                "native_api_version": list(capstone.cs_version()),
                "native_library_sha256": hashlib.sha256(native.read_bytes()).hexdigest(),
                "sh2_profile_correction": {
                    "id": "capstone-5.0.9-sh-negative-level-v1",
                    "guard": "reject known non-SH2 encodings while retaining native facts",
                    "source_patch_sha256": "6f88d820337bcd18cb9bcee116b66ac41036f3e8a25f0af3e58d2adaa753f570",
                }}
    rows = []
    diagnostics = []
    decode_started = time.perf_counter()
    for offset in range(0, min(len(data) // 2, max_instructions) * 2, 2):
        if time.perf_counter() - started > timeout:
            raise RuntimeError(f"Capstone decoding timed out after {timeout} seconds")
        ins = next(decoder.disasm(data[offset:offset + 2], base_address + offset, count=1), None)
        if ins is None:
            if scan_all_words:
                continue
            break
        fact = {"address": ins.address, "size": ins.size, "bytes": bytes(ins.bytes).hex(),
                "mnemonic": ins.mnemonic, "operands": ins.op_str}
        if _outside_sh2_profile(int.from_bytes(data[offset:offset + 2], "big")):
            diagnostics.append({"kind": "rejected_native_fact", "reason": "encoding outside SH-2 profile",
                                "native_fact": fact})
            if scan_all_words:
                continue
            break
        rows.append(fact)
    return {"instructions": rows, "elapsed_seconds": time.perf_counter() - started,
            "decode_seconds": time.perf_counter() - decode_started,
            "engine_version": f"Capstone distribution {version('capstone')}; bindings {capstone.__version__}; native {capstone.cs_version()}",
            "engine_identity": identity,
            "diagnostics": diagnostics}
