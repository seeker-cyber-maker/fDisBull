"""Reproducible static caller/field trace for the Civ DOS city routine.

The unpacked root is the only input.  This module decodes the ``R:0D12:0045``
entry, proves which ``townbuf`` fields the routine touches, and lists every
far call that targets it.  It never executes the game and makes no claim about
reachability at runtime.
"""

from __future__ import annotations

import hashlib
import struct

import capstone

CITY_PROCESS = (0x0D12, 0x0045)
CITY_ENTRY_LINEAR = 0xD165
CITY_SEGMENT_START = 0xD120
TOWNBUF_BASE = 0x70EC
CITY_RECORD_SIZE = 0x1C
FIELD_NAMES = {
    0x00: "buildings",
    0x06: "status",
    0x07: "size",
    0x09: "production",
    0x0B: "owner",
    0x0C: "food_box",
    0x0E: "shield_box",
    0x10: "workers",
}
SHIELD_RESET_LINEAR = 0xD244
SHIELD_RESET_SIZE = 0x30


def identity(root: bytes) -> dict:
    return {"sha256": hashlib.sha256(root).hexdigest(), "bytes": len(root)}


def _header(root: bytes) -> dict:
    (
        magic,
        cblp,
        cp,
        crlc,
        cparhdr,
        _minalloc,
        _maxalloc,
        _ss,
        _sp,
        _csum,
        _ip,
        _cs,
        lfarlc,
        _ovno,
    ) = struct.unpack_from("<14H", root, 0)
    if magic != 0x5A4D:
        raise ValueError("expected an MZ root module")
    header_size = cparhdr * 16
    module = cp * 512 - (512 - cblp if cblp else 0)
    relocations = {struct.unpack_from("<HH", root, lfarlc + 4 * i) for i in range(crlc)}
    return {
        "header_size": header_size,
        "module": module,
        "relocations": relocations,
        "relocation_offsets": {offset for offset, _segment in relocations},
        "overlays": len(root) - header_size - module,
    }


def _decoder() -> capstone.Cs:
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)
    md.detail = True
    return md


def _disasm(root: bytes, header_size: int, start: int, size: int) -> list[dict]:
    md = _decoder()
    text = root[header_size + start : header_size + start + size]
    return [
        {
            "address": i.address,
            "bytes": i.bytes.hex(),
            "mnemonic": i.mnemonic,
            "operands": i.op_str,
        }
        for i in md.disasm(text, start)
    ]


def _function_start(
    root: bytes, header_size: int, site_linear: int, limit: int = 0x900
) -> int | None:
    """Nearest preceding standard prologue inside the entry segment."""
    for back in range(limit):
        candidate = site_linear - back
        if candidate < 0:
            return None
        if (
            root[header_size + candidate : header_size + candidate + 3]
            == b"\x55\x8b\xec"
        ):
            return candidate
    return None


def _pushes_before(root: bytes, header_size: int, site_linear: int) -> dict:
    """Decode the argument pushes that immediately precede a far call.

    Decoding must begin at a real instruction boundary; a mid-stream start
    desynchronises and silently invents arguments.
    """
    start = _function_start(root, header_size, site_linear)
    if start is None:
        return {
            "site_linear": site_linear,
            "pushes": [],
            "values": [],
            "register_arguments": [],
            "preceding": [],
            "function_start": None,
        }
    md = _decoder()
    text = root[header_size + start : header_size + site_linear]
    decoded = [
        {
            "address": i.address,
            "mnemonic": i.mnemonic,
            "operands": i.op_str,
            "bytes": i.bytes.hex(),
            "size": i.size,
        }
        for i in md.disasm(text, start)
    ]
    pushes: list[dict] = []
    cursor = site_linear
    for item in reversed(decoded):
        if item["address"] + item["size"] != cursor:
            break
        if item["mnemonic"] != "push":
            break
        pushes.append(item)
        cursor = item["address"]
    pushes.reverse()
    values, regs = [], []
    for item in pushes:
        try:
            values.append(int(item["operands"], 0))
        except ValueError:
            values.append(None)
            regs.append(item["operands"])
    preceding = decoded[-9 : -len(pushes) - 1] if len(decoded) > len(pushes) else []
    return {
        "site_linear": site_linear,
        "pushes": pushes,
        "values": values,
        "register_arguments": regs,
        "preceding": [
            {
                "address": item["address"],
                "mnemonic": item["mnemonic"],
                "operands": item["operands"],
            }
            for item in preceding
        ],
        "function_start": start,
    }


def callers(root: bytes) -> list[dict]:
    """Direct far calls to the city entry, excluding coincidental byte matches.

    A root-module far call must have its segment word in the relocation table;
    overlay bytes are not relocated, so a match there is retained with that
    qualification made explicit.
    """
    header = _header(root)
    header_size, module = header["header_size"], header["module"]
    segment, offset = CITY_PROCESS
    targeted = struct.pack("<HH", offset, segment)
    found, coincidental = [], 0
    for index in range(header_size, len(root) - 4):
        if root[index] not in (0x9A, 0xEA) or root[index + 1 : index + 5] != targeted:
            continue
        linear = index - header_size
        relocated = (index + 3 - header_size) in header["relocation_offsets"]
        in_root = linear < module
        if in_root and not relocated:
            coincidental += 1
            continue
        site = _pushes_before(root, header_size, linear)
        found.append(
            {
                "file_offset": index,
                "linear": linear,
                "runtime_linear": 0x10000 + linear,
                "segment_offset": f"{segment:04X}:{offset:04X}",
                "in_root_module": in_root,
                "segment_word_relocated": relocated,
                "caller_function": site["function_start"],
                "mode_push": site["values"][0] if site["values"] else None,
                "arguments": site["values"],
                "register_arguments": site["register_arguments"],
                "preceding": site["preceding"],
            }
        )
    return {"sites": found, "coincidental_byte_matches": coincidental}


def function_entry(root: bytes) -> dict:
    header_size = _header(root)["header_size"]
    prologue = root[
        header_size + CITY_ENTRY_LINEAR : header_size + CITY_ENTRY_LINEAR + 40
    ]
    return {
        "segment_offset": f"{CITY_PROCESS[0]:04X}:{CITY_PROCESS[1]:04X}",
        "linear": CITY_ENTRY_LINEAR,
        "runtime_linear": 0x10000 + CITY_ENTRY_LINEAR,
        "file_offset": header_size + CITY_ENTRY_LINEAR,
        "prologue_hex": prologue.hex(),
        "instructions": _disasm(root, header_size, CITY_ENTRY_LINEAR, 24),
    }


def townbuf_fields(root: bytes) -> dict:
    """Count in-segment references to each city-record field offset."""
    header_size = _header(root)["header_size"]
    window = root[
        header_size + CITY_SEGMENT_START : header_size + CITY_SEGMENT_START + 0x10000
    ]
    result = {}
    for rel, name in FIELD_NAMES.items():
        needle = struct.pack("<H", TOWNBUF_BASE + rel)
        addresses = []
        start = 0
        while True:
            at = window.find(needle, start)
            if at < 0:
                break
            addresses.append(CITY_SEGMENT_START + at)
            start = at + 1
        result[name] = {
            "offset": rel,
            "references": len(addresses),
            "first": addresses[:6],
        }
    return result


def shield_reset(root: bytes) -> dict:
    header_size = _header(root)["header_size"]
    instructions = _disasm(root, header_size, SHIELD_RESET_LINEAR, SHIELD_RESET_SIZE)
    shape = [f"{i['mnemonic']} {i['operands']}".strip() for i in instructions]
    return {
        "linear": SHIELD_RESET_LINEAR,
        "file_offset": header_size + SHIELD_RESET_LINEAR,
        "bytes_hex": root[
            header_size + SHIELD_RESET_LINEAR : header_size
            + SHIELD_RESET_LINEAR
            + SHIELD_RESET_SIZE
        ].hex(),
        "instructions": instructions,
        "rule": "if (shield_box > 999 || shield_box < 0) shield_box = 0;",
        "matches_rule": any("cmp word ptr [bx + 0x70fa], 0x3e7" in s for s in shape)
        and any("cmp word ptr [bx + 0x70fa], 0" in s for s in shape)
        and any("mov word ptr [bx + 0x70fa], 0" in s for s in shape),
    }


def analyze(root: bytes) -> dict:
    """One receipt for the static city-route question."""
    sites = callers(root)
    in_root = [s for s in sites["sites"] if s["in_root_module"]]
    return {
        "format": "fdisbull-civ-city-static-trace-1",
        "identity": identity(root),
        "entry": function_entry(root),
        "fields": townbuf_fields(root),
        "shield_reset": shield_reset(root),
        "callers": {
            "total": len(sites["sites"]),
            "in_root_module": len(in_root),
            "coincidental_byte_matches": sites["coincidental_byte_matches"],
            "sites": sites["sites"],
        },
        "scope": (
            "Static decode of the unpacked root only. Call sites and field "
            "offsets are proven for these bytes; runtime reachability, "
            "mode-1 parameter layout and naming remain open."
        ),
    }
