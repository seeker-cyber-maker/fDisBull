"""Optional, bounded Ghidra facts for explicitly selected Mach-O ARM64 code.

The fDisBull analyzer selects addresses and owns traversal and persistence. This
adapter imports an exact temporary ARM64 slice, asks Ghidra to decode the
requested four-byte instruction slots (and optionally a bounded diagnostic
function window), and joins each loaded instruction to the original file
bytes. Ghidra's loaded memory may contain fixups; it is never substituted for
the immutable source or treated as a runtime address. No decompiled C is used
as an instruction fact or as UIL.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import tempfile

import lief

from .loader import load_image
from .macho_metadata import inspect_macho
from .macho_slices import select_macho_slice

_SCRIPT = Path(__file__).parent / "data" / "FdisbullGhidraArm64.txt"
_MAX_REQUESTS = 4096
_MAX_PER_RUN = 256
_MAX_TIMEOUT_S = 3600


def _address(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 1 << 64:
        raise ValueError("addresses must be unsigned 64-bit integers")
    if value % 4:
        raise ValueError("ARM64 addresses must be four-byte aligned")
    return value


def _requests(addresses: object) -> list[int]:
    if isinstance(addresses, (str, bytes, bytearray)):
        raise ValueError("addresses must be an iterable of integers")
    try:
        iterator = iter(addresses)
    except TypeError as exc:
        raise ValueError("addresses must be an iterable of integers") from exc
    result, seen = [], set()
    for index, value in enumerate(iterator):
        if index >= _MAX_REQUESTS:
            raise ValueError("at most 4096 address items may be requested")
        address = _address(value)
        if address not in seen:
            result.append(address)
            seen.add(address)
    if not result:
        raise ValueError("at least one address is required")
    return result


def _source_offset(address: int, mappings: list[dict], source: bytes) -> int:
    matches = []
    for mapping in mappings:
        begin = mapping["virtual_address"]
        size = mapping["file_size"]
        if begin <= address and address + 4 <= begin + size:
            offset = mapping["file_offset"] + address - begin
            if 0 <= offset and offset + 4 <= len(source):
                matches.append(offset)
    if len(matches) != 1:
        raise ValueError(f"address 0x{address:x} has no unique original file span")
    return matches[0]


def _b64(value: str) -> str:
    try:
        return base64.b64decode(value, validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
        raise RuntimeError("malformed Ghidra facts") from exc


def _log_tail(path: Path, limit: int = 2000) -> str:
    with path.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        stream.seek(max(0, stream.tell() - limit))
        return stream.read(limit).decode("utf-8", errors="replace")


def _parse_facts(lines: list[str], addresses: list[int], decompile_entry: int | None) -> tuple[str, str, str, dict[int, dict], dict | None]:
    """Require one record per address and a complete terminal count."""
    if len(lines) < 4 or not lines[0].startswith("VERSION\t") or not lines[1].startswith("FORMAT\t") or not lines[2].startswith("LANGUAGE\t"):
        raise RuntimeError("Ghidra facts lack version, format, or language")
    version = lines[0].split("\t", 1)[1]
    image_format = _b64(lines[1].split("\t", 1)[1])
    language = _b64(lines[2].split("\t", 1)[1])
    if not version or "Mach-O" not in image_format or not language.startswith("AARCH64:LE:64"):
        raise RuntimeError("Ghidra did not load an ARM64 Mach-O program")
    if lines[-1] != f"COMPLETE\t{len(addresses)}":
        raise RuntimeError("Ghidra facts ended before the requested count")
    diagnostic = None
    records_end = -1
    if decompile_entry is not None:
        fields = lines[-2].split("\t") if len(lines) >= 5 else []
        if len(fields) != 5 or fields[0] != "DECOMP" or fields[1] != f"{decompile_entry:x}" or fields[2] not in ("complete", "truncated", "failed"):
            raise RuntimeError("Ghidra decompiler diagnostic is missing or malformed")
        diagnostic = {"entry": decompile_entry, "status": fields[2],
                      "c": _b64(fields[3]), "warnings": _b64(fields[4]),
                      "role": "diagnostic only; not instruction facts or UIL",
                      "window_bytes": 4096,
                      "function_coverage": "unknown; disassembly restricted to 4 KiB from entry"}
        if diagnostic["status"] == "complete" and not diagnostic["c"].strip():
            raise RuntimeError("Ghidra reported an empty completed decompilation")
        records_end = -2
    result = {}
    expected = set(addresses)
    for line in lines[3:records_end]:
        fields = line.split("\t")
        if not fields or fields[0] not in ("INS", "ERROR"):
            raise RuntimeError("unexpected Ghidra fact record")
        if len(fields) != (10 if fields[0] == "INS" else 3):
            raise RuntimeError("malformed Ghidra fact record")
        try:
            address = int(fields[1], 16)
        except ValueError as exc:
            raise RuntimeError("malformed Ghidra fact address") from exc
        if address not in expected or address in result:
            raise RuntimeError("Ghidra returned an unexpected or duplicate address")
        if fields[0] == "ERROR":
            result[address] = {"error": _b64(fields[2])}
            continue
        try:
            length = int(fields[2])
            loaded = bytes.fromhex(fields[3])
            operands = _b64(fields[6]).split("\x1f") if fields[6] else []
            flows = [int(item, 16) for item in fields[8].split(",") if item]
            fallthrough = int(fields[9], 16) if fields[9] else None
        except (ValueError, TypeError) as exc:
            raise RuntimeError("malformed Ghidra instruction data") from exc
        if length != 4 or len(loaded) != length or len(flows) > 64:
            raise RuntimeError("Ghidra returned an invalid ARM64 instruction extent")
        result[address] = {"length": length, "loaded_bytes": loaded.hex(),
                           "mnemonic": _b64(fields[4]), "display": _b64(fields[5]),
                           "operands": operands, "flow_type": _b64(fields[7]),
                           "flow_targets": flows, "fallthrough": fallthrough}
    if set(result) != expected:
        raise RuntimeError("Ghidra facts omitted requested addresses")
    return version, image_format, language, result, diagnostic


def _fixups(thin: bytes, slice_offset: int, addresses: list[int]) -> tuple[dict[int, list[dict]], str]:
    """Join existing LIEF/record evidence without inventing resolved targets."""
    parsed = lief.parse(thin)
    if not isinstance(parsed, lief.MachO.Binary):
        raise RuntimeError("cannot parse selected Mach-O slice for fixup provenance")
    metadata = inspect_macho(parsed, thin, max_items=10000)
    availability = metadata["availability"]
    chained_status = availability["chained_fixups"]["status"]
    dyld_status = availability["dyld_bindings"]["status"]
    incomplete = (metadata["truncated"]["imports"] or metadata["truncated"]["relocations"]
                  or availability["partial_categories"]
                  or chained_status not in ("absent", "parsed_by_lief")
                  or dyld_status not in ("absent", "parsed_by_lief"))
    status = "partial" if incomplete else "enumerated"
    result = {address: [] for address in addresses}
    for category, records in (("relocation", metadata["relocations"]), ("binding", metadata["imports"])):
        for record in records:
            at = record.get("address")
            if at is None:
                continue
            width = record.get("width") if category == "relocation" else record.get("pointer_width")
            if not isinstance(width, int) or width <= 0:
                width = 1
            for address in addresses:
                if at < address + 4 and address < at + width:
                    file_offset = record.get("file_offset")
                    result[address].append({"category": category, "kind": record.get("kind"),
                                            "source": record.get("source"), "address": at,
                                            "width": width,
                                            "original_file_offset": file_offset + slice_offset if file_offset is not None else None,
                                            "target": record.get("target"),
                                            "binding_state": record.get("binding_state")})
    return result, status


def probe_macho_arm64(path: str | os.PathLike, addresses, *, analyze_headless: str | os.PathLike,
                      java_home: str | os.PathLike | None = None, max_instructions: int = 64,
                      timeout_s: int | float = 120, decompile_entry: int | None = None,
                      decompile_timeout_s: int = 10) -> dict:
    """Probe caller-selected preferred VAs in a Mach-O ARM64 image.

    This is static evidence, not app execution or a UIL translation. Inputs are
    read-only. Requested instruction facts are capped at ``max_instructions``
    unique addresses per call. An optional C diagnostic disassembles within a
    separate 4 KiB entry window and has its own timeout. The whole subprocess
    has a wall timeout. An instruction cap returns ``status='partial'`` and
    ``stop_reason='budget'``; repeat with the remaining addresses to continue.
    """
    requested = _requests(addresses)
    if isinstance(max_instructions, bool) or not isinstance(max_instructions, int) or not 1 <= max_instructions <= _MAX_PER_RUN:
        raise ValueError("max_instructions must be an integer in 1..256")
    if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)) or not 0 < timeout_s <= _MAX_TIMEOUT_S:
        raise ValueError("timeout_s must be in 0..3600")
    try:
        headless = os.fspath(analyze_headless)
    except TypeError as exc:
        raise ValueError("analyze_headless path is required") from exc
    if not headless:
        raise ValueError("analyze_headless path is required")
    selected = requested[:max_instructions]
    if decompile_entry is not None:
        decompile_entry = _address(decompile_entry)
        if decompile_entry not in selected:
            raise ValueError("decompile_entry must be among addresses selected for this run")
    if isinstance(decompile_timeout_s, bool) or not isinstance(decompile_timeout_s, int) or not 1 <= decompile_timeout_s <= 60:
        raise ValueError("decompile_timeout_s must be an integer in 1..60")
    input_path = Path(path)
    if not input_path.is_file() or not 0 < input_path.stat().st_size <= 64 * 1024 * 1024:
        raise ValueError("Mach-O source must be a nonempty regular file at most 64 MiB")
    with input_path.open("rb") as stream:
        original = stream.read(64 * 1024 * 1024 + 1)
    if len(original) > 64 * 1024 * 1024:
        raise ValueError("Mach-O source grew beyond the 64 MiB probe limit")
    thin, selection = select_macho_slice(original, "arm64")
    if selection["endian"] != "little" or selection["bits"] != 64:
        raise ValueError("Ghidra ARM64 probe requires little-endian Mach-O 64")
    image = load_image(path, slice_arch="arm64")
    if image.format != "Mach-O" or image.arch != "arm64" or image.bits != 64:
        raise ValueError("selected image is not Mach-O ARM64")
    if image.source_bytes != original or image.metadata.get("source_sha256") != selection["source_sha256"]:
        raise RuntimeError("Mach-O source changed during the probe")
    mappings = image.metadata["file_mappings"]
    offsets = {}
    for address in selected:
        if not any(region.executable and region.start <= address and address + 4 <= region.start + len(region.data)
                   for region in image.regions):
            raise ValueError(f"address 0x{address:x} is not wholly executable")
        offsets[address] = _source_offset(address, mappings, original)
    fixups, fixup_status = _fixups(thin, selection["slice_offset"], selected)
    with tempfile.TemporaryDirectory(prefix="fdisbull-ghidra-arm64-") as temporary:
        root = Path(temporary)
        source = root / "arm64.macho"
        source.write_bytes(thin)
        script = root / "FdisbullGhidraArm64.java"
        script_bytes = _SCRIPT.read_bytes()
        script.write_bytes(script_bytes)
        facts_path = root / "facts.txt"
        # Imported programs are untrusted inputs. Do not pass inherited tokens,
        # cloud credentials, or unrelated process configuration into Ghidra.
        environment = {key: os.environ[key] for key in
                       ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "LC_CTYPE", "JAVA_HOME")
                       if key in os.environ}
        if java_home is not None:
            environment["JAVA_HOME"] = os.fspath(java_home)
        command = [headless, str(root), "project", "-import", str(source), "-noanalysis",
                   "-scriptPath", str(root), "-postScript", script.name,
                   str(facts_path), str(len(selected)), *[f"0x{address:x}" for address in selected]]
        if decompile_entry is not None:
            command.extend([f"0x{decompile_entry:x}", str(decompile_timeout_s)])
        stdout_path, stderr_path = root / "stdout.log", root / "stderr.log"
        try:
            with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                with subprocess.Popen(command, stdout=stdout, stderr=stderr,
                                      env=environment, start_new_session=True) as process:
                    try:
                        process.wait(timeout=timeout_s)
                    except subprocess.TimeoutExpired as exc:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        process.wait()
                        raise RuntimeError("Ghidra ARM64 probe timed out") from exc
        except OSError as exc:
            raise RuntimeError("Ghidra ARM64 probe could not start") from exc
        if process.returncode or not facts_path.is_file():
            raise RuntimeError("Ghidra ARM64 probe failed or produced no facts: " +
                               _log_tail(stderr_path) + _log_tail(stdout_path))
        lines = facts_path.read_text(encoding="utf-8").splitlines()
    version, image_format, language, decoded, diagnostic = _parse_facts(lines, selected, decompile_entry)
    if diagnostic is not None:
        diagnostic["timeout_s"] = decompile_timeout_s
    facts, failures = [], []
    for address in selected:
        item = decoded[address]
        offset = offsets[address]
        original_bytes = original[offset:offset + 4].hex()
        provenance = fixups[address]
        if "error" in item:
            failures.append({"loaded_address": address, "reason": item["error"]})
            continue
        relation = "same_as_original" if item["loaded_bytes"] == original_bytes else (
            "differs_with_recorded_fixup_overlap" if provenance else "differs_unattributed")
        facts.append({"loaded_address": address, "runtime_address": None,
                      "source_file_offset": offset, "source_bytes": original_bytes,
                      "source_layer": "original_file", "loaded_byte_relation": relation,
                      "fixup_provenance": provenance, **item})
    incomplete = bool(failures or len(requested) > len(selected))
    return {"format": "fdisbull-ghidra-arm64-facts-1", "status": "partial" if incomplete else "complete",
            "stop_reason": "budget" if len(requested) > len(selected) else "decode_failure" if failures else None,
            "requested_count": len(requested), "queried_count": len(selected),
            "remaining_addresses": requested[len(selected):], "failed": failures,
            "source_sha256": selection["source_sha256"], "source_size": selection["source_size"],
            "slice_sha256": selection["slice_sha256"], "slice_offset": selection["slice_offset"],
            "slice_size": selection["slice_size"], "slice_index": selection["slice_index"],
            "ghidra_version": version, "ghidra_image_format": image_format,
            "ghidra_language": language, "ghidra_script_sha256": hashlib.sha256(script_bytes).hexdigest(),
            "fixup_enumeration_status": fixup_status,
            "decompiler_diagnostic": diagnostic,
            "address_space": "preferred static VA; runtime slide unresolved",
            "source_byte_policy": "Original fat-container offsets and bytes; temporary imported slice is byte-identical",
            "facts": facts}
