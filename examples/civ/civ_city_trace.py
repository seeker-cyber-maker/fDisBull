"""Reproducible static caller/field trace for the Civ DOS city routine.

The unpacked root is the only input.  This module decodes the ``R:0D12:0045``
entry, proves which ``townbuf`` fields the routine touches, and lists every
far call that targets it.  It never executes the game and makes no claim about
reachability at runtime.
"""

from __future__ import annotations

import hashlib
import re
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
SHIELD_RESET_SIZE = 0x2B


def identity(root: bytes) -> dict:
    return {"sha256": hashlib.sha256(root).hexdigest(), "bytes": len(root)}


def _header(root: bytes) -> dict:
    if len(root) < 28:
        raise ValueError("truncated MZ header")
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
    declared = cp * 512 - (512 - cblp if cblp else 0)
    if (not cp or cblp > 511 or not 28 <= header_size <= declared <= len(root)
            or lfarlc < 28 or lfarlc + 4 * crlc > header_size):
        raise ValueError("invalid MZ root/relocation boundaries")
    module = declared - header_size
    relocations = {struct.unpack_from("<HH", root, lfarlc + 4 * i) for i in range(crlc)}
    normalized = {segment * 16 + offset for offset, segment in relocations}
    if any(offset + 2 > module for offset in normalized):
        raise ValueError("MZ relocation exceeds the load module")
    return {
        "header_size": header_size,
        "module": module,
        "relocations": relocations,
        "relocation_offsets": normalized,
        "declared_file_end": declared,
        "overlays": len(root) - declared,
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
    decode_basis = "candidate-prologue linear decoding"
    # This resident function contains INT 3F overlay dispatch descriptors;
    # decoding their inline data as x86 can stop before the actual call. Admit
    # only this complete, reviewed MSC tail, not an arbitrary guessed boundary.
    tail = root[header_size + max(0, site_linear-9):header_size + site_linear]
    if (not decoded or decoded[-1]["address"]+decoded[-1]["size"]!=site_linear) and re.fullmatch(
            rb"\xb8..\x99\x52\x50\xff\x76.", tail, re.S):
        start_tail = site_linear-len(tail)
        native_tail = list(md.disasm(tail,start_tail))
        decoded = [dict(address=i.address,mnemonic=i.mnemonic,operands=i.op_str,
                        bytes=i.bytes.hex(),size=i.size) for i in native_tail]
        text = tail
        native_start = start_tail
        decode_basis = "reviewed MOV AX,imm16; CWD; PUSH DX; PUSH AX; PUSH [BP+disp8] call tail"
    else:
        native_start = start
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
    # Local constant propagation on a straight-line suffix. Crossing a control
    # transfer discards values; this is not an all-path reaching-definition proof.
    known, push_values = {}, {}
    native_decoded = list(md.disasm(text, native_start))
    for ins in native_decoded:
        if ins.mnemonic.startswith(("j", "loop", "call", "lcall", "ret")):
            known.clear()
            continue
        operands = ins.operands
        if ins.mnemonic == "push":
            operand = operands[0]
            value = (operand.imm & 0xffff) if operand.type == capstone.x86.X86_OP_IMM else (
                known.get(ins.reg_name(operand.reg)) if operand.type == capstone.x86.X86_OP_REG else None)
            push_values[ins.address] = value
            continue
        assigned = {}
        if ins.mnemonic == "mov" and operands[0].type == capstone.x86.X86_OP_REG:
            assigned[ins.reg_name(operands[0].reg)] = (
                operands[1].imm & 0xffff if operands[1].type == capstone.x86.X86_OP_IMM else None)
        elif ins.mnemonic in ("xor", "sub") and all(o.type == capstone.x86.X86_OP_REG for o in operands) and operands[0].reg == operands[1].reg:
            assigned[ins.reg_name(operands[0].reg)] = 0
        elif ins.mnemonic == "cwd" and known.get("ax") is not None:
            assigned["dx"] = 0xffff if known["ax"] & 0x8000 else 0
        _, writes = ins.regs_access()
        for reg in writes:
            name = ins.reg_name(reg)
            known.pop(name, None)
            if name in ("ax","ah","al"): known.pop("ax", None)
            if name in ("dx","dh","dl"): known.pop("dx", None)
        known.update({k:v for k,v in assigned.items() if v is not None})
    values, regs = [], []
    for item in pushes:
        try:
            values.append(int(item["operands"], 0))
        except ValueError:
            values.append(push_values.get(item["address"]))
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
        "decode_basis": decode_basis,
        "mode_word": (None if len(values)<2 or values[-2] is None else
                      values[-2] - 65536 if values[-2] >= 32768 else values[-2]),
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
        site = (_pushes_before(root, header_size, linear) if in_root else
                dict(function_start=None, values=[], register_arguments=[], preceding=[], mode_word=None))
        found.append(
            {
                "file_offset": index,
                "linear": linear if in_root else None,
                "runtime_linear": 0x10000 + linear if in_root else None,
                "overlay_tail_offset": None if in_root else index - header["declared_file_end"],
                "segment_offset": f"{segment:04X}:{offset:04X}",
                "in_root_module": in_root,
                "segment_word_relocated": relocated,
                "caller_function": site["function_start"],
                "mode_push": site["values"][0] if site["values"] else None,
                "mode_word": site.get("mode_word"),
                "mode_evidence": "local constant slice at the callee BP+8 word; not all-path proof" if in_root else "overlay mapping unresolved",
                "argument_decode_basis": site.get("decode_basis"),
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
        "matches_rule": shape == [
            "cmp word ptr [bx + 0x70fa], 0x3e7", "jle 0xd24f", "jmp 0xd261",
            "mov ax, 0x1c", "imul word ptr [bp + 6]", "mov bx, ax",
            "cmp word ptr [bx + 0x70fa], 0", "jl 0xd261", "jmp 0xd26f",
            "mov ax, 0x1c", "imul word ptr [bp + 6]", "mov bx, ax",
            "mov word ptr [bx + 0x70fa], 0"],
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
