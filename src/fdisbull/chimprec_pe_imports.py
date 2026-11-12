"""Import-layout parsing and deterministic table helpers for CHimpREC PE output."""
from __future__ import annotations

import struct
from typing import Any

from .chimprec_pe_image import _align, _bounded, parse_pe

_MAX_IMPORTS = 1_000_000

def _normalize_plan(plan: dict, pe: dict) -> tuple[list[dict], list[dict]]:
    if not isinstance(plan, dict) or plan.get("format") != "chimprec-import-plan-1":
        raise ValueError("import plan must use chimprec-import-plan-1")
    if plan.get("bits") != pe["bits"] or plan.get("pointer_width") != pe["pointer_width"]:
        raise ValueError("import plan architecture does not match PE")
    descriptors = plan.get("descriptors")
    if not isinstance(descriptors, list) or len(descriptors) > 65535:
        raise ValueError("invalid import descriptor list")
    flat = []
    normalized = []
    seen = set()
    for group_index, descriptor in enumerate(descriptors):
        if not isinstance(descriptor, dict):
            raise ValueError("import descriptors must be dictionaries")
        module = descriptor.get("module")
        entries = descriptor.get("entries")
        if not isinstance(module, str) or not module or len(module) > 4096 or "\0" in module:
            raise ValueError("invalid import module name")
        try:
            module.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError("import module names must be ASCII") from exc
        if not isinstance(entries, list) or not entries:
            raise ValueError("each import descriptor needs at least one entry")
        group = {"module": module, "entries": []}
        previous = None
        for entry_index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise ValueError("import entries must be dictionaries")
            address = entry.get("address")
            if isinstance(address, bool) or not isinstance(address, int):
                raise ValueError("import slot address must be an integer")
            if address >= pe["image_base"]:
                rva = address - pe["image_base"]
            else:
                rva = address
            if not 0 <= rva <= pe["size_of_image"] - pe["pointer_width"]:
                raise ValueError("import slot lies outside mapped image")
            if rva % pe["pointer_width"]:
                raise ValueError("import slot is not pointer-aligned")
            if previous is not None and rva != previous + pe["pointer_width"]:
                raise ValueError("entries within one descriptor must occupy contiguous slots")
            previous = rva
            if rva in seen:
                raise ValueError("duplicate import slot")
            seen.add(rva)
            name, ordinal = entry.get("name"), entry.get("ordinal")
            if (name is None) == (ordinal is None):
                raise ValueError("each import needs exactly one of name or ordinal")
            if name is not None:
                if not isinstance(name, str) or not name or len(name) > 65536 or "\0" in name:
                    raise ValueError("invalid import name")
                try:
                    name.encode("ascii")
                except UnicodeEncodeError as exc:
                    raise ValueError("import names must be ASCII") from exc
            else:
                if isinstance(ordinal, bool) or not isinstance(ordinal, int) or not 0 <= ordinal <= 0xFFFF:
                    raise ValueError("import ordinal must fit 16 bits")
            item = {"group": group_index, "index": entry_index, "module": module,
                    "slot_rva": rva, "address": pe["image_base"] + rva,
                    "name": name, "ordinal": ordinal,
                    "selected_by": entry.get("selected_by"), "forwarder": entry.get("forwarder")}
            group["entries"].append(item)
            flat.append(item)
        normalized.append(group)
    if len(flat) > _MAX_IMPORTS:
        raise ValueError("import plan exceeds the one-million-entry limit")
    return normalized, flat


def _append(blob: bytearray, base_rva: int, payload: bytes, alignment: int = 1) -> int:
    while len(blob) % alignment:
        blob.append(0)
    rva = base_rva + len(blob)
    blob.extend(payload)
    return rva


def _pack_pointer(value: int, width: int) -> bytes:
    return value.to_bytes(width, "little")


def _checksum(data: bytes, checksum_offset: int) -> int:
    work = bytearray(data)
    work[checksum_offset:checksum_offset + 4] = b"\0" * 4
    if len(work) & 1:
        work.append(0)
    total = 0
    for offset in range(0, len(work), 2):
        total += work[offset] | work[offset + 1] << 8
        total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    return (total + len(data)) & 0xFFFFFFFF


def _directory(pe: dict, index: int) -> tuple[int, int]:
    if index >= pe["directory_count"]:
        return 0, 0
    row = pe["directories"][index]
    return row["rva"], row["size"]


def _resource_payloads(image: bytes, pe: dict) -> list[dict]:
    root, size = _directory(pe, 2)
    if not root or not size:
        return []
    if root + min(size, 16) > len(image):
        raise ValueError("resource directory lies outside mapped image")
    found = []
    visiting = set()

    def read(offset: int, amount: int) -> bytes:
        return bytes(_bounded(image, offset, amount, "resource structure"))

    def walk(relative: int, path: list[Any], depth: int):
        if depth > 8 or relative in visiting:
            raise ValueError("resource directory cycle or excessive depth")
        visiting.add(relative)
        header = read(root + relative, 16)
        named, identified = struct.unpack_from("<HH", header, 12)
        count = named + identified
        if count > 4096:
            raise ValueError("resource directory has excessive entries")
        for index in range(count):
            name, target = struct.unpack("<II", read(root + relative + 16 + index * 8, 8))
            if name & 0x80000000:
                string_rva = root + (name & 0x7FFFFFFF)
                chars = struct.unpack("<H", read(string_rva, 2))[0]
                label = read(string_rva + 2, chars * 2).decode("utf-16-le")
            else:
                label = name
            child = path + [label]
            if target & 0x80000000:
                walk(target & 0x7FFFFFFF, child, depth + 1)
            else:
                data_rva, data_size, code_page, _ = struct.unpack("<IIII", read(root + target, 16))
                payload = read(data_rva, data_size)
                found.append({"path": child, "rva": data_rva, "size": data_size,
                              "code_page": code_page, "sha256": _sha256(payload)})
        visiting.remove(relative)

    walk(0, [], 0)
    return sorted(found, key=lambda item: json.dumps(item["path"], sort_keys=True))


def parse_imports(image: bytes, pe: dict | None = None) -> dict:
    """Independently parse an unbound import directory from a mapped PE image."""
    pe = pe or parse_pe(image)
    start, size = _directory(pe, 1)
    if not start or size < 20 or start + size > len(image):
        raise ValueError("missing or invalid import directory")
    width, ordinal_flag = pe["pointer_width"], pe["ordinal_flag"]

    def string(rva: int) -> str:
        if not 0 < rva < len(image):
            raise ValueError("import string RVA lies outside image")
        end = image.find(b"\0", rva, min(len(image), rva + 65537))
        if end < 0:
            raise ValueError("unterminated import string")
        return image[rva:end].decode("ascii")

    descriptors, entries = [], []
    terminal = None
    for offset in range(0, size, 20):
        fields = struct.unpack_from("<IIIII", image, start + offset)
        if not any(fields):
            terminal = start + offset
            break
        original_first_thunk, timestamp, forwarder_chain, name_rva, first_thunk = fields
        if timestamp or forwarder_chain:
            raise ValueError("rebuilt import descriptors must be unbound")
        if not original_first_thunk or not first_thunk:
            raise ValueError("rebuilt import descriptor lacks ILT or IAT")
        module = string(name_rva)
        count = 0
        while True:
            if count >= _MAX_IMPORTS:
                raise ValueError("import thunk count exceeds limit")
            ilt_at = original_first_thunk + count * width
            iat_at = first_thunk + count * width
            ilt = int.from_bytes(_bounded(image, ilt_at, width, "ILT cell"), "little")
            if not ilt:
                break
            iat = int.from_bytes(_bounded(image, iat_at, width, "IAT cell"), "little")
            if ilt != iat:
                raise ValueError("unbound ILT and IAT differ")
            if ilt & ordinal_flag:
                name, ordinal = None, ilt & 0xFFFF
            else:
                _bounded(image, ilt, 2, "import hint")
                name, ordinal = string(ilt + 2), None
            entries.append({"module": module, "slot_rva": iat_at,
                            "address": pe["image_base"] + iat_at,
                            "name": name, "ordinal": ordinal})
            count += 1
        descriptors.append({"module": module, "original_first_thunk": original_first_thunk,
                            "first_thunk": first_thunk, "count": count})
    if terminal is None:
        raise ValueError("missing terminal import descriptor")
    return {"descriptors": descriptors, "entries": entries, "terminal_rva": terminal}

