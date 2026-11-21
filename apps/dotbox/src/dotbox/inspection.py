"""Small offline investigations of explicit files or frozen memory buffers.

This module never starts or calls an emulator, pauses a game, writes a source,
or recursively analyzes code. A caller-supplied origin is a hypothesis about
addressing, not evidence that file bytes match a live game's memory.
"""

import argparse
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import re
import stat
import sys


FORMAT = "dotbox-inspection-1"
MAX_WINDOW = 65536
MAX_RESULTS = 256
MAX_PATTERN = 256
MAX_EXCERPT = 256
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_IDENTITY_BYTES = 128 * 1024 * 1024
MAX_RESOURCES = 8
MAX_ADDRESS = (1 << 64) - 1


def _integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in {minimum}..{maximum}")
    return value


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read_file(path, *, offset=0, length=None, max_bytes=MAX_FILE_BYTES):
    """Read one bounded descriptor; reject special files and changing sources."""
    _integer(offset, "offset", 0, MAX_ADDRESS)
    if length is not None:
        _integer(length, "length", 1, MAX_WINDOW)
    elif offset:
        raise ValueError("Whole-file identity requires offset zero")
    path = Path(path).expanduser().absolute()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("Inspection requires a regular file")
        if offset > before.st_size:
            raise ValueError("offset is beyond the end of the file")
        requested = before.st_size if length is None else length
        count = min(requested, before.st_size - offset)
        if count > max_bytes:
            raise ValueError("File exceeds the remaining identity byte budget")
        source.seek(offset)
        data = source.read(count)
        after = os.fstat(source.fileno())
        try:
            current = path.stat(follow_symlinks=False)
        except OSError as error:
            raise ValueError("Source changed during inspection; capture it again") from error
        if (len(data) != count or _identity(before) != _identity(after)
                or not stat.S_ISREG(current.st_mode) or _identity(after) != _identity(current)):
            raise ValueError("Source changed during inspection; capture it again")
    return data, {
        "path": str(path), "file_size": before.st_size, "file_offset": offset,
        "requested_length": requested, "length": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "hash_scope": "whole file" if length is None else "selected bytes only",
        "window_truncated": len(data) < requested,
    }


def _binding(origin, length):
    if origin is None:
        return {"kind": "file-offset", "runtime_validated": False}
    _integer(origin, "origin", 0, MAX_ADDRESS)
    if origin + length > MAX_ADDRESS + 1:
        raise ValueError("Selected window would overflow its caller-supplied origin")
    return {"kind": "caller-supplied-origin", "origin": origin, "runtime_validated": False}


def _location(offset, origin, position):
    return {"file_offset": offset + position, "window_offset": position,
            "address": (offset if origin is None else origin) + position}


def _packet(operation, window, origin, limit):
    _integer(limit, "limit", 1, MAX_RESULTS)
    return {"format": FORMAT, "operation": operation, "window": window,
            "binding": _binding(origin, window["length"]),
            "limits": {"window_bytes": MAX_WINDOW, "results": limit},
            "results_truncated": False}


def inspect_identity(path, *, resources=()):
    """Identify a classic COM/MZ executable and only explicitly named resources."""
    from .native_session import _image

    if not isinstance(resources, (list, tuple)) or len(resources) > MAX_RESOURCES:
        raise ValueError(f"resources must contain at most {MAX_RESOURCES} explicit files")
    data, source = _read_file(path)
    image = _image(data, Path(path).name)
    module_offset = 0 if image["format"] == "COM" else image["header_fields"]["e_cparhdr"] * 16
    entry_offset = image["entry_module_offset"]
    entry_file_backed = entry_offset < image["module_size"]
    remaining = MAX_IDENTITY_BYTES - len(data)
    names, inventory = {Path(path).name.casefold()}, []
    for resource in resources:
        name = Path(resource).name
        if name.casefold() in names:
            raise ValueError("Explicit resource basenames must be distinct from each other and the program")
        names.add(name.casefold())
        raw, info = _read_file(resource, max_bytes=min(MAX_FILE_BYTES, remaining))
        remaining -= len(raw)
        inventory.append({"name": name, **info})
    binding = {"program": {"name": Path(path).name, "sha256": source["sha256"]},
               "resources": sorted(({
                   "name": item["name"], "length": item["length"], "sha256": item["sha256"],
               } for item in inventory), key=lambda item: item["name"])}
    fingerprint = hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"format": FORMAT, "operation": "identity", "source": source,
            "image": {"format": image["format"], "module_file_offset": module_offset,
                      "module_size": image["module_size"], "allocation_size": image["allocation_size"],
                      "relocation_count": len(image["relocation_offsets"]),
                      "entry": {"relative_cs": image["entry_cs"], "ip": image["entry_ip"],
                                "file_offset": module_offset + entry_offset if entry_file_backed else None,
                                "file_backed": entry_file_backed}},
            "resources": inventory, "selection_sha256": fingerprint,
            "resource_scope": "Only explicitly selected files; not a complete game-edition inventory",
            "mapping_scope": "Static executable layout; runtime load and code/data roles are unverified",
            "limits": {"file_bytes": MAX_FILE_BYTES, "total_bytes": MAX_IDENTITY_BYTES,
                       "resources": MAX_RESOURCES}}


def inspect_strings(path, *, offset=0, length=4096, min_length=4, limit=64, origin=None):
    _integer(min_length, "min_length", 1, MAX_EXCERPT)
    _integer(limit, "limit", 1, MAX_RESULTS)
    data, window = _read_file(path, offset=offset, length=length)
    result = _packet("strings", window, origin, limit)
    rows = []
    for match in re.finditer(rb"[\x20-\x7e]{%d,}" % min_length, data):
        if len(rows) == limit:
            result["results_truncated"] = True
            break
        raw = match.group()
        rows.append({**_location(offset, origin, match.start()), "byte_length": len(raw),
                     "text": raw[:MAX_EXCERPT].decode("ascii"),
                     "text_truncated": len(raw) > MAX_EXCERPT})
    return {**result, "strings": rows, "min_length": min_length,
            "excerpt_bytes": MAX_EXCERPT,
            "interpretation": "Printable ASCII runs; window boundaries can split strings"}


def inspect_find(path, pattern, *, mask=None, offset=0, length=4096, limit=64, origin=None):
    if not isinstance(pattern, bytes) or not 1 <= len(pattern) <= MAX_PATTERN:
        raise ValueError(f"pattern must contain 1..{MAX_PATTERN} bytes")
    if mask is not None and (not isinstance(mask, bytes) or len(mask) != len(pattern) or not any(mask)):
        raise ValueError("mask must match the pattern length and constrain at least one bit")
    _integer(limit, "limit", 1, MAX_RESULTS)
    data, window = _read_file(path, offset=offset, length=length)
    result = _packet("find", window, origin, limit)
    rows = []
    for position in range(len(data) - len(pattern) + 1):
        candidate = data[position:position + len(pattern)]
        matched = candidate == pattern if mask is None else all(
            (actual & bits) == (expected & bits) for actual, expected, bits in zip(candidate, pattern, mask))
        if not matched:
            continue
        if len(rows) == limit:
            result["results_truncated"] = True
            break
        rows.append({**_location(offset, origin, position), "bytes": candidate.hex()})
    return {**result, "pattern_hex": pattern.hex(), "mask_hex": mask.hex() if mask is not None else None,
            "matches": rows, "overlapping_matches": True}


def _decode(data, *, offset, origin, bits, limit):
    import iced_x86 as ix

    if type(bits) is not int or bits not in (16, 32):
        raise ValueError("bits must be 16 or 32")
    _binding(origin, len(data))
    if origin is not None and origin + len(data) > 1 << bits:
        raise ValueError("Disassembly origin and window must fit the selected instruction-pointer width")
    decoder = ix.Decoder(bits, data, ip=0 if origin is None else origin)
    formatter = ix.Formatter(ix.FormatterSyntax.NASM)
    rows, decoded_bytes, failure = [], 0, None
    while decoder.can_decode and len(rows) < limit:
        position = decoder.position
        instruction = decoder.decode()
        if instruction.is_invalid:
            failure = {"file_offset": offset + position, "decoder_error": decoder.last_error,
                       "bytes": data[position:position + 15].hex()}
            break
        rows.append({**_location(offset, origin, position), "decoder_ip": instruction.ip,
                     "size": instruction.len, "bytes": data[position:decoder.position].hex(),
                     "mnemonic": formatter.format_mnemonic(instruction, ix.FormatMnemonicOptions.NO_PREFIXES),
                     "text": formatter.format(instruction)})
        decoded_bytes = decoder.position
    limited = failure is None and decoder.can_decode
    return {"instructions": rows, "bits": bits, "decoded_bytes": decoded_bytes,
            "remaining_bytes": len(data) - decoded_bytes, "results_truncated": limited,
            "stop_reason": "invalid-or-truncated-instruction" if failure else "result-limit" if limited else "window-end",
            "decode_error": failure,
            "decoder": {"name": "iced-x86", "version": version("iced-x86")},
            "decoder_ip_basis": "caller-supplied instruction-pointer origin" if origin is not None else "window-relative, starting at zero",
            "interpretation": "Linear decoding only; bytes are not proven reachable code and branch text is not a validated runtime mapping"}


def inspect_disassemble(path, *, offset=0, length=256, bits=16, limit=64, origin=None):
    _integer(limit, "limit", 1, MAX_RESULTS)
    data, window = _read_file(path, offset=offset, length=length)
    return {**_packet("disassemble", window, origin, limit),
            **_decode(data, offset=offset, origin=origin, bits=bits, limit=limit)}


def inspect_diff(before, after, *, before_offset=0, after_offset=0, length=4096, limit=64,
                 before_origin=None, after_origin=None):
    _integer(limit, "limit", 1, MAX_RESULTS)
    _binding(before_origin, 0)
    _binding(after_origin, 0)
    if (before_origin is None) != (after_origin is None):
        raise ValueError("Both diff windows must use the same explicit origin or neither")
    if before_origin is None and before_offset != after_offset:
        raise ValueError("Different file offsets require explicit matching origins")
    if before_origin != after_origin:
        raise ValueError("Diff address origins do not match")
    left, first = _read_file(before, offset=before_offset, length=length)
    right, second = _read_file(after, offset=after_offset, length=length)
    if len(left) != len(right):
        raise ValueError("Diff windows must contain equal numbers of bytes")
    binding = _binding(before_origin, len(left))
    runs, total_changed, position, limited = [], 0, 0, False
    while position < len(left):
        if left[position] == right[position]:
            position += 1
            continue
        start = position
        while position < len(left) and left[position] != right[position]:
            position += 1
        count = position - start
        total_changed += count
        if len(runs) == limit:
            limited = True
            continue
        stop = min(position, start + MAX_EXCERPT)
        runs.append({"window_offset": start, "before_file_offset": before_offset + start,
                     "after_file_offset": after_offset + start,
                     "address": (before_offset if before_origin is None else before_origin) + start,
                     "length": count, "before_hex": left[start:stop].hex(),
                     "after_hex": right[start:stop].hex(), "hex_truncated": count > MAX_EXCERPT})
    return {"format": FORMAT, "operation": "diff", "before": first, "after": second,
            "binding": binding, "changes": runs, "changed_bytes": total_changed,
            "results_truncated": limited,
            "limits": {"window_bytes": MAX_WINDOW, "results": limit, "excerpt_bytes": MAX_EXCERPT},
            "capture_scope": "Two independently read file windows; no atomic live snapshot or causal interpretation"}


def self_check():
    """Exercise the installed decoder on authored fixtures, without file or game I/O."""
    try:
        small = _decode(bytes.fromhex("b8341290"), offset=0, origin=None, bits=16, limit=4)
        wide = _decode(bytes.fromhex("b87856341290"), offset=0, origin=None, bits=32, limit=4)
        invalid = _decode(b"\xb8", offset=0, origin=None, bits=16, limit=4)
        checks = {
            "x86_16": [(x["bytes"], x["mnemonic"], x["size"]) for x in small["instructions"]] == [("b83412", "mov", 3), ("90", "nop", 1)],
            "x86_32": [(x["bytes"], x["mnemonic"], x["size"]) for x in wide["instructions"]] == [("b878563412", "mov", 5), ("90", "nop", 1)],
            "truncated_instruction_rejected": not invalid["instructions"] and invalid["decode_error"] is not None,
        }
        return {"ok": all(checks.values()), "decoder": small["decoder"], "checks": checks,
                "scope": "Authored offline decode fixtures only; no native runtime or game qualification"}
    except (ImportError, OSError, ValueError) as error:
        return {"ok": False, "error": str(error), "scope": "Offline decoder unavailable or failed"}


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def _number(value):
    try:
        return int(value, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Expected an integer or 0x-prefixed hex value") from error


def _hex(value):
    if len(value) > MAX_PATTERN * 3:
        raise ValueError("Hex input exceeds the pattern byte budget")
    try:
        return bytes.fromhex(value)
    except ValueError as error:
        raise ValueError("Expected complete hexadecimal bytes") from error


def main(argv=None):
    parser = _Parser(prog="dotbox inspect", description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True, parser_class=_Parser)
    identity = commands.add_parser("identity", help="Identify an executable and explicit resource files")
    identity.add_argument("file")
    identity.add_argument("--resource", action="append", default=[])
    for name in ("strings", "find", "disassemble"):
        command = commands.add_parser(name)
        command.add_argument("file")
        command.add_argument("--offset", type=_number, default=0)
        command.add_argument("--length", type=_number, default=256 if name == "disassemble" else 4096)
        command.add_argument("--limit", type=_number, default=64)
        command.add_argument("--origin", type=_number, help="Caller-supplied address of the window's first byte; not runtime validated. For disassembly, an instruction-pointer offset.")
        if name == "strings":
            command.add_argument("--min-length", type=_number, default=4)
        elif name == "find":
            command.add_argument("--hex", required=True, dest="pattern")
            command.add_argument("--mask")
        else:
            command.add_argument("--bits", type=int, choices=(16, 32), default=16)
    diff = commands.add_parser("diff")
    diff.add_argument("before")
    diff.add_argument("after")
    for name in ("before-offset", "after-offset"):
        diff.add_argument("--" + name, type=_number, default=0)
    for name in ("before-origin", "after-origin"):
        diff.add_argument("--" + name, type=_number)
    diff.add_argument("--length", type=_number, default=4096)
    diff.add_argument("--limit", type=_number, default=64)
    try:
        options = vars(parser.parse_args(argv))
        operation = options.pop("operation")
        if operation == "identity":
            result = inspect_identity(options["file"], resources=options["resource"])
        elif operation == "diff":
            result = inspect_diff(**options)
        else:
            path = options.pop("file")
            if operation == "find":
                options["pattern"] = _hex(options["pattern"])
                if options["mask"] is not None:
                    options["mask"] = _hex(options["mask"])
            function = {"strings": inspect_strings, "find": inspect_find, "disassemble": inspect_disassemble}[operation]
            result = function(path, **options)
        print(json.dumps({"ok": True, "result": result}, allow_nan=False))
        return 0
    except (ValueError, OSError, ImportError, TypeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
