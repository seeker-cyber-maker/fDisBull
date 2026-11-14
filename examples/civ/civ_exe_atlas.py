"""Build a source/address atlas for the pinned Civilization DOS executable.

The atlas joins four independent artifacts that all describe the same
byte-identical 474.05 build:

* ``CIV.MAP`` - the LINK 5.01 map: 97 segment records and 1,188 publics;
* ``*.COD`` - the MSC 5.1 source/assembly listings: 430 C functions, their
  source lines, instruction offsets and symbolic call sites;
* ``CIV_UNP.EXE`` - the unpacked runtime image: root load module and the 23
  overlay images;
* Civ64's DOS correspondence table - 21 semantic anchors.

It does not execute the game and does not copy game bytes.  The output is
metadata: names, addresses, sizes, call edges and the result of checking the
first instruction of every C function against the binary image.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
import struct
from pathlib import Path

PINNED_PACKED_SHA256 = (
    "22de2748e3089793644c7e501e2a95b553010ddec34a7ff42f4395cf779c9c2a"
)
PINNED_UNPACKED_SHA256 = (
    "aa63aa396cfa62519b131ee6c0a231bed02bb9aefce26b955608b5815a569e57"
)
OVERLAY_BASE = 0x23740

# The 21 anchors already recorded in docs/CIV_DOS_CIV64_CROSSWALK.md.  They
# are Civ64's DOS-side roles; this module only resolves them to a civd source
# function and binary address.  It does not claim Windows byte equivalence.
CIV64_ANCHORS = [
    ("R:1AEA:03BA", "city layer", "DrawMapTile 1110:04D0", "city overlay/UI"),
    ("R:0D12:0045", "city screen", "ProcessCity 1030:0000", "city screen boundary"),
    (
        "R:0D12:7045",
        "building icons",
        "DrawImprovementIcon 1030:8529",
        "improvement presentation",
    ),
    (
        "R:0D12:710D",
        "city panel background",
        "DrawCityPanelBox 1030:895C",
        "city panel frame",
    ),
    (
        "R:1F4D:04F7",
        "truncate to width",
        "TruncateStringToLogicalWidth 11D0:02E4",
        "city-name presentation",
    ),
    ("R:1459:08C6", "city name", "AppendCityName 1038:0BBA", "city labels"),
    ("R:0ADE:03EA", "city caller", "ShowCityScreen 1170:05AF", "caller graph"),
    ("R:0ADE:0093", "city caller", "ShowCityScreen 1170:05AF", "caller graph"),
    ("R:1459:0597", "city caller", "ShowCityScreen 1170:05AF", "caller graph"),
    ("O19:0000", "city view", "ShowCityView 11B0:0000", "city-view transition"),
    (
        "O19:13A1",
        "houses/roads",
        "LoadCityViewSprites 11B0:1653",
        "city-view resources",
    ),
    ("O19:14FB", "buildings", "LoadCityViewSprites 11B0:1653", "city-view resources"),
    ("O19:167B", "invaders", "PlayCityCaptureAnimation 11B0:1B63", "capture animation"),
    (
        "O19:18C1",
        "civil disorder",
        "PlayCivilDisorderAnimation 11B0:1FAC",
        "disorder animation",
    ),
    (
        "O19:1AE1",
        "celebration",
        "PlayCelebrationAnimation 11B0:237C",
        "celebration animation",
    ),
    ("O22:0EAF", "city founded", "ShowCityFoundedAnimation 11B8:14E5", "founding flow"),
    (
        "R:0ADE:0421",
        "production menu",
        "ChooseCityProduction 1170:05CA",
        "production choice UI",
    ),
    (
        "O20:0540",
        "disasters and city events",
        "ProcessCityDisaster 1040:068E",
        "city event boundary",
    ),
    ("O20:047C", "founding caller", "FoundCity 1040:0000", "founding state transition"),
    (
        "R:0238:107E",
        "status panel",
        "DrawStatusCivPanels 1088:13D5",
        "tax/science/luxury projection",
    ),
    ("R:0403:35CE", "rate menus", "MoveCivUnits 11F0:3BF5", "rate-selection UI"),
]

SEGMENT_RE = re.compile(
    r"^\s*([0-9A-Fa-f]+)H\s+([0-9A-Fa-f]+)H\s+([0-9A-Fa-f]+)H\s+(\S+)\s+(\S+)"
)
PUBLIC_RE = re.compile(
    r"^\s*([0-9A-Fa-f]{4}):([0-9A-Fa-f]{4})\s+(Res|Ovl)\s+(\S+)"
    r"(?:\s+\(([0-9A-Fa-f]+)H\))?"
)
COD_SEGMENT_RE = re.compile(r"^(\S+)\s+SEGMENT\b")
PROC_RE = re.compile(r"^(_?[A-Za-z_][\w$@?]*)\s+PROC\b")
ENDP_RE = re.compile(r"^(_?[A-Za-z_][\w$@?]*)\s+ENDP\b")
INSN_RE = re.compile(r"^\t\*\*\* ([0-9A-Fa-f]+)\t([0-9A-Fa-f ]+?)\t+(.*)$")
CALL_RE = re.compile(
    r"\b(call|lcall)\s+(?:(FAR|NEAR)\s+)?(?:PTR\s+)?"
    r"(?!(?:DWORD|WORD|BYTE|FAR|NEAR|CS|DS|ES|SS)\b)"
    r"(_?[A-Za-z_][\w$@?]*)",
    re.IGNORECASE,
)
LINE_RE = re.compile(r"^; Line (\d+)")


class AtlasError(ValueError):
    """An input is not a consistent Civ atlas artifact."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_map(text: str) -> dict:
    """Parse CIV.MAP's segment table and public symbol table."""
    segments: list[dict] = []
    publics: list[dict] = []
    overlay_label: str | None = None
    in_segments = True
    for line in text.splitlines():
        if line.startswith(" Overlay "):
            overlay_label = line.strip()
            continue
        if line.startswith(" Origin"):
            in_segments = False
            continue
        if in_segments:
            match = SEGMENT_RE.match(line)
            if match:
                start, end, length, name, clas = match.groups()
                overlay_decimal = None
                if overlay_label:
                    number = overlay_label.rsplit(" ", 1)[-1]
                    if number.endswith("H"):
                        overlay_decimal = int(number[:-1], 16)
                segments.append(
                    {
                        "name": name,
                        "start": int(start, 16),
                        "end": int(end, 16),
                        "length": int(length, 16),
                        "class": clas,
                        "overlay_label": overlay_label,
                        "overlay_number": overlay_decimal,
                    }
                )
            continue
        match = PUBLIC_RE.match(line)
        if match:
            segment, offset, kind, name, overlay = match.groups()
            publics.append(
                {
                    "name": name,
                    "segment": int(segment, 16),
                    "offset": int(offset, 16),
                    "linear": int(segment, 16) * 16 + int(offset, 16),
                    "kind": kind,
                    "overlay": overlay,
                }
            )
    # The map prints publics twice (by name and by value); dedupe the exact
    # records but keep distinct aliases at the same address.
    unique: dict[tuple, dict] = {}
    for item in publics:
        unique[(item["name"], item["linear"], item["kind"], item["overlay"])] = item
    publics = sorted(unique.values(), key=lambda item: (item["linear"], item["name"]))
    return {"segments": segments, "publics": publics}


def _source_declaration_line(source_path: Path, name: str) -> int | None:
    """Find the definition line for a C function, if the source is present."""
    if not source_path.exists():
        return None
    stripped = name.removeprefix("_")
    pattern = re.compile(rf"\b{re.escape(stripped)}\s*\(")
    lines = source_path.read_text(errors="replace").splitlines()
    for index, line in enumerate(lines):
        code = line.split("//", 1)[0]
        if ";" in code or not pattern.search(code):
            continue
        prefix = code.split(stripped, 1)[0]
        if "=" in prefix or re.search(
            r"\b(?:if|while|for|switch|return|case|do|else)\b", prefix
        ):
            continue
        if not re.match(r"^\s*(?:static\s+)?(?:[A-Za-z_]\w*\s+)+", code):
            continue
        tail = code.rstrip()
        following = next(
            (item.strip() for item in lines[index + 1 :] if item.strip()),
            "",
        )
        if tail.endswith("{") or following.startswith("{"):
            return index + 1
    return None


def _parse_cod(path: Path) -> dict:
    lines = path.read_text(errors="replace").splitlines()
    segment = None
    for line in lines:
        match = COD_SEGMENT_RE.match(line)
        if match:
            segment = match.group(1)
            break
    if segment is None:
        raise AtlasError(f"{path}: no SEGMENT declaration")
    source_path = path.with_suffix(".C")
    functions: list[dict] = []
    current: dict | None = None
    source_line: int | None = None
    for line in lines:
        line_match = LINE_RE.match(line)
        if line_match:
            source_line = int(line_match.group(1))
            continue
        proc = PROC_RE.match(line)
        if proc:
            if current is not None:
                raise AtlasError(f"{path}: nested PROC {proc.group(1)}")
            name = proc.group(1)
            declaration_line = _source_declaration_line(source_path, name)
            current = {
                "name": name,
                "source": source_path.name,
                "line": (
                    declaration_line
                    if declaration_line is not None
                    else (source_line - 1 if source_line is not None else None)
                ),
                "body_line": source_line,
                "start": None,
                "end": None,
                "entry_bytes": None,
                "instructions": 0,
                "calls": [],
            }
            continue
        end = ENDP_RE.match(line)
        if end:
            if current is None or end.group(1) != current["name"]:
                raise AtlasError(f"{path}: unmatched ENDP {end.group(1)}")
            if current["start"] is not None:
                functions.append(current)
            current = None
            continue
        insn = INSN_RE.match(line)
        if insn and current is not None:
            offset = int(insn.group(1), 16)
            raw = bytes.fromhex(insn.group(2))
            if current["start"] is None:
                current["start"] = offset
                current["entry_bytes"] = raw.hex()
            current["end"] = offset + len(raw)
            current["instructions"] += 1
            call = CALL_RE.search(insn.group(3))
            if call:
                current["calls"].append(
                    {
                        "site": offset,
                        "target": call.group(3),
                        "kind": (call.group(2) or "NEAR").upper(),
                    }
                )
    if current is not None:
        raise AtlasError(f"{path}: unterminated PROC {current['name']}")
    return {"segment": segment, "source": path.name, "functions": functions}


def _root_header(data: bytes) -> dict:
    if len(data) < 28 or data[:2] != b"MZ":
        raise AtlasError("root is not an MZ image")
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
    ) = struct.unpack_from("<14H", data, 0)
    if magic != 0x5A4D:
        raise AtlasError("root has the wrong MZ signature")
    header_size = cparhdr * 16
    declared = cp * 512 - (512 - cblp if cblp else 0)
    if (
        not cp
        or cblp > 511
        or header_size < 28
        or header_size > declared
        or declared > len(data)
        or lfarlc < 28
        or lfarlc + 4 * crlc > header_size
    ):
        raise AtlasError("root MZ boundaries are inconsistent")
    return {
        "header_size": header_size,
        "declared_file_end": declared,
        "module_size": declared - header_size,
        "relocations": crlc,
    }


def _overlay_records(data: bytes, start: int) -> list[dict]:
    """Scan the preserved overlay tail for the 23 MZ-headed records."""
    records: list[dict] = []
    cursor = start
    while cursor + 28 <= len(data):
        at = data.find(b"MZ", cursor)
        if at < 0:
            break
        try:
            (
                magic,
                cblp,
                cp,
                _crlc,
                cparhdr,
                _minalloc,
                _maxalloc,
                _ss,
                _sp,
                _csum,
                _ip,
                _cs,
                _lfarlc,
                ovno,
            ) = struct.unpack_from("<14H", data, at)
        except struct.error:
            break
        header_size = cparhdr * 16
        declared = cp * 512 - (512 - cblp if cblp else 0)
        if (
            magic == 0x5A4D
            and 0 < ovno <= 23
            and 28 <= header_size <= declared
            and at + declared <= len(data)
            and declared - header_size > 0
        ):
            image = data[at + header_size : at + declared]
            records.append(
                {
                    "number": ovno,
                    "file_offset": at,
                    "header_size": header_size,
                    "declared_size": declared,
                    "image": image,
                    "image_size": len(image),
                }
            )
            cursor = at + declared
        else:
            cursor = at + 2
    # The tail must describe each overlay number exactly once.
    numbers = [record["number"] for record in records]
    if sorted(numbers) != list(range(1, 24)):
        raise AtlasError(f"overlay scan found numbers {numbers}, expected 1..23")
    return records


def _parse_anchor(address: str) -> tuple[int, int | None]:
    if address.startswith("R:"):
        segment, offset = address[2:].split(":")
        return int(segment, 16) * 16 + int(offset, 16), None
    if address.startswith("O"):
        overlay, offset = address[1:].split(":")
        return OVERLAY_BASE + int(offset, 16), int(overlay, 10)
    raise AtlasError(f"unsupported anchor address {address}")


def _containing(
    functions: list[dict], linear: int, overlay: int | None = None
) -> dict | None:
    for function in functions:
        if function["overlay"] != overlay:
            continue
        if function["start"] <= linear < function["end"]:
            return function
    return None


def _public_for(
    publics_by_name: dict[str, list[dict]],
    name: str,
    linear: int,
    overlay: int | None,
) -> dict | None:
    for public in publics_by_name.get(name, []):
        public_overlay = int(public["overlay"], 16) if public["overlay"] else None
        if public["linear"] == linear and public_overlay == overlay:
            return public
    return None


def build_atlas(
    *,
    map_path: Path,
    cod_dir: Path,
    root_path: Path,
    packed_path: Path | None = None,
) -> dict:
    map_text = map_path.read_text(errors="replace")
    map_sha256 = sha256(map_path.read_bytes())
    parsed_map = parse_map(map_text)
    segments = parsed_map["segments"]
    publics = parsed_map["publics"]
    segments_by_name = {segment["name"]: segment for segment in segments}
    publics_by_name: dict[str, list[dict]] = {}
    for public in publics:
        publics_by_name.setdefault(public["name"], []).append(public)

    root = root_path.read_bytes()
    root_hash = sha256(root)
    if root_hash != PINNED_UNPACKED_SHA256:
        raise AtlasError(
            f"unpacked root hash {root_hash} != pinned {PINNED_UNPACKED_SHA256}"
        )
    header = _root_header(root)
    packed_sha256 = None
    if packed_path is not None:
        packed_sha256 = sha256(packed_path.read_bytes())
        if packed_sha256 != PINNED_PACKED_SHA256:
            raise AtlasError(
                f"packed root hash {packed_sha256} != pinned {PINNED_PACKED_SHA256}"
            )
    overlays = _overlay_records(root, header["declared_file_end"])
    overlay_by_number = {record["number"]: record for record in overlays}

    functions: list[dict] = []
    for cod_path in sorted(cod_dir.glob("*.COD")):
        parsed = _parse_cod(cod_path)
        segment_name = parsed["segment"]
        segment = segments_by_name.get(segment_name)
        if segment is None:
            raise AtlasError(f"{cod_path.name}: segment {segment_name} absent from map")
        for function in parsed["functions"]:
            start = segment["start"] + function["start"]
            end = segment["start"] + function["end"]
            segment_end = segment["start"] + segment["length"]
            if end <= start or end > segment_end:
                raise AtlasError(
                    f"{function['source']}:{function['name']} escapes segment {segment_name}"
                )
            public = _public_for(
                publics_by_name, function["name"], start, segment["overlay_number"]
            )
            function.update(
                {
                    "segment": segment_name,
                    "overlay": segment["overlay_number"],
                    "overlay_label": segment["overlay_label"],
                    "start": start,
                    "end": end,
                    "size": end - start,
                    "public": public is not None,
                    "map_symbol": public["name"] if public else None,
                    "calls": [
                        {
                            **call,
                            "linear": segment["start"] + call["site"],
                        }
                        for call in function["calls"]
                    ],
                }
            )
            functions.append(function)

    functions.sort(key=lambda item: (item["start"], item["name"]))
    for segment_name in segments_by_name:
        group = [item for item in functions if item["segment"] == segment_name]
        group.sort(key=lambda item: item["start"])
        for left, right in itertools.pairwise(group):
            if left["end"] > right["start"]:
                raise AtlasError(
                    f"{segment_name}: {left['name']} overlaps {right['name']}"
                )

    # Resolve named call sites against the map and the C function intervals.
    unresolved: list[dict] = []
    starts = {(item["overlay"], item["start"]): item for item in functions}
    for function in functions:
        for call in function["calls"]:
            target = call["target"]
            candidates = publics_by_name.get(target, [])
            target_linear = None
            target_overlay = function["overlay"]
            if candidates:
                # Prefer a candidate that names a function start in the
                # caller's overlay.  Overlay load addresses overlap, so the
                # overlay identity is mandatory.
                selected = None
                for candidate in candidates:
                    candidate_overlay = (
                        int(candidate["overlay"], 16) if candidate["overlay"] else None
                    )
                    if (candidate_overlay, candidate["linear"]) in starts:
                        selected = (candidate_overlay, candidate["linear"])
                        break
                if selected is None:
                    candidate = candidates[0]
                    selected = (
                        int(candidate["overlay"], 16) if candidate["overlay"] else None,
                        candidate["linear"],
                    )
                target_overlay, target_linear = selected
            if target_linear is None:
                local = next(
                    (
                        item
                        for item in functions
                        if item["name"] == target
                        and item["overlay"] == function["overlay"]
                    ),
                    None,
                )
                target_linear = local["start"] if local else None
                target_overlay = local["overlay"] if local else function["overlay"]
            if target_linear is None:
                call["resolution"] = "unresolved"
                unresolved.append(
                    {
                        "caller": function["name"],
                        "site": call["linear"],
                        "target": target,
                    }
                )
                continue
            target_function = starts.get((target_overlay, target_linear))
            if target_function is None:
                target_function = _containing(functions, target_linear, target_overlay)
            call["target_linear"] = target_linear
            call["target_function"] = (
                target_function["name"] if target_function else None
            )
            call["target_overlay"] = target_overlay
            call["resolution"] = "internal" if target_function else "external"

    # Verify each C entry and each call opcode against the root module or
    # extracted overlay image.  COD operands are pre-link placeholders, so
    # only the entry opcode (not the whole first instruction) is universal.
    for function in functions:
        segment = segments_by_name[function["segment"]]
        entry = bytes.fromhex(function["entry_bytes"])
        if segment["overlay_number"] is None:
            offset = header["header_size"] + function["start"]
            source = root[offset : offset + len(entry)]
        else:
            overlay = overlay_by_number[segment["overlay_number"]]
            offset = function["start"] - OVERLAY_BASE
            source = overlay["image"][offset : offset + len(entry)]
        function["entry_verified"] = source.hex() == function["entry_bytes"]
        function["entry_opcode_verified"] = source[:1] == entry[:1]
        function["entry_image_offset"] = offset
        for call in function["calls"]:
            linear = call["linear"]
            if segment["overlay_number"] is None:
                at = header["header_size"] + linear
                opcode = root[at]
                operand = root[at + 1 : at + 5]
            else:
                image = overlay_by_number[segment["overlay_number"]]["image"]
                at = linear - OVERLAY_BASE
                opcode = image[at]
                operand = image[at + 1 : at + 5]
            target = call.get("target_linear")
            target_overlay = call.get("target_overlay")
            call["opcode"] = opcode
            if target_overlay is not None and target_overlay != function["overlay"]:
                # The linker turns a cross-overlay far call into INT 3Fh,
                # overlay number, entry offset.
                call["opcode_verified"] = opcode == 0xCD and operand[:1] == b"\x3f"
                if opcode == 0xCD and operand[:1] == b"\x3f":
                    decoded_overlay = operand[1]
                    decoded_offset = int.from_bytes(operand[2:4], "little")
                    call["decoded_target_overlay"] = decoded_overlay
                    call["decoded_target_linear"] = OVERLAY_BASE + decoded_offset
                    call["target_verified"] = (
                        target is not None
                        and decoded_overlay == target_overlay
                        and call["decoded_target_linear"] == target
                    )
            else:
                expected = 0x9A if call["kind"] == "FAR" else 0xE8
                call["opcode_verified"] = opcode == expected
                if target is not None and call["kind"] == "NEAR" and opcode == 0xE8:
                    displacement = int.from_bytes(operand[:2], "little", signed=True)
                    call["decoded_target_linear"] = linear + 3 + displacement
                    call["target_verified"] = call["decoded_target_linear"] == target
                elif target is not None and call["kind"] == "FAR" and opcode == 0x9A:
                    call["decoded_target_linear"] = int.from_bytes(
                        operand[2:4], "little"
                    ) * 16 + int.from_bytes(operand[:2], "little")
                    call["target_verified"] = call["decoded_target_linear"] == target

    # Resolve Civ64's semantic anchors to the civd function that contains them.
    anchors = []
    for dos_address, role, civ64_name, use in CIV64_ANCHORS:
        linear, overlay = _parse_anchor(dos_address)
        containing = _containing(functions, linear, overlay)
        anchors.append(
            {
                "dos_address": dos_address,
                "linear": linear,
                "role": role,
                "civ64": civ64_name,
                "use": use,
                "function": containing["name"] if containing else None,
                "function_source": containing["source"] if containing else None,
                "function_start": containing["start"] if containing else None,
                "inside_function": bool(containing and containing["start"] != linear),
                "resolution": "civd-source-function" if containing else "unresolved",
            }
        )

    # Summaries by source and by overlay.
    source_rows: dict[str, dict] = {}
    for function in functions:
        row = source_rows.setdefault(
            function["source"],
            {
                "source": function["source"],
                "segment": function["segment"],
                "overlay": function["overlay"],
                "functions": 0,
                "bytes": 0,
                "calls": 0,
            },
        )
        row["functions"] += 1
        row["bytes"] += function["size"]
        row["calls"] += len(function["calls"])
    sources = sorted(
        source_rows.values(), key=lambda item: (-item["bytes"], item["source"])
    )

    overlay_rows = []
    for segment in segments:
        if segment["overlay_number"] is None:
            continue
        group = [item for item in functions if item["segment"] == segment["name"]]
        overlay = overlay_by_number[segment["overlay_number"]]
        overlay_rows.append(
            {
                "overlay": segment["overlay_number"],
                "label": segment["overlay_label"],
                "segment": segment["name"],
                "map_start": segment["start"],
                "map_end": segment["end"],
                "map_bytes": segment["length"],
                "image_file_offset": overlay["file_offset"],
                "image_bytes": overlay["image_size"],
                "size_matches_map": overlay["image_size"] == segment["length"],
                "sources": sorted({item["source"] for item in group}),
                "functions": len(group),
                "function_bytes": sum(item["size"] for item in group),
            }
        )

    root_code = [
        segment
        for segment in segments
        if segment["overlay_number"] is None
        and segment["class"] == "CODE"
        and segment["length"]
    ]
    counts = {
        "segments": len(segments),
        "root_code_segments": len(root_code),
        "root_code_extent_bytes": sum(segment["length"] for segment in root_code),
        "overlays": len(overlays),
        "overlay_image_bytes": sum(record["image_size"] for record in overlays),
        "publics": len(publics),
        "c_functions": len(functions),
        "c_function_bytes": sum(item["size"] for item in functions),
        "c_sources": len(sources),
        "calls": sum(len(item["calls"]) for item in functions),
        "internal_calls": sum(
            1
            for item in functions
            for call in item["calls"]
            if call.get("resolution") == "internal"
        ),
        "external_calls": sum(
            1
            for item in functions
            for call in item["calls"]
            if call.get("resolution") == "external"
        ),
        "unresolved_calls": len(unresolved),
        "call_opcodes_verified": sum(
            1
            for item in functions
            for call in item["calls"]
            if call.get("opcode_verified")
        ),
        "call_targets_verified": sum(
            1
            for item in functions
            for call in item["calls"]
            if call.get("target_verified")
        ),
        "entries_verified": sum(1 for item in functions if item["entry_verified"]),
        "entry_opcodes_verified": sum(
            1 for item in functions if item["entry_opcode_verified"]
        ),
        "map_entry_matches": sum(1 for item in functions if item["public"]),
        "anchors_resolved": sum(1 for item in anchors if item["function"]),
        "anchors_total": len(anchors),
    }

    return {
        "format": "fdisbull-civ-exe-atlas-1",
        "edition": {
            "label": "Civ DOS 474.05 (civd verified build)",
            "packed_sha256": PINNED_PACKED_SHA256,
            "unpacked_sha256": PINNED_UNPACKED_SHA256,
            "packed_path": str(packed_path) if packed_path else None,
            "packed_sha256_observed": packed_sha256,
            "root_path": str(root_path),
        },
        "inputs": {
            "map": str(map_path),
            "cod_dir": str(cod_dir),
            "map_sha256": map_sha256,
            "root_header": header,
            "overlay_records": [
                {
                    "number": record["number"],
                    "file_offset": record["file_offset"],
                    "header_size": record["header_size"],
                    "declared_size": record["declared_size"],
                    "image_size": record["image_size"],
                }
                for record in overlays
            ],
        },
        "counts": counts,
        "verification": {
            "map_public_entry_matches": counts["map_entry_matches"],
            "c_entry_bytes_verified": counts["entries_verified"],
            "c_entry_opcodes_verified": counts["entry_opcodes_verified"],
            "c_entry_bytes_total": len(functions),
            "call_opcodes_verified": counts["call_opcodes_verified"],
            "call_targets_verified": counts["call_targets_verified"],
            "overlay_size_matches": sum(
                1 for row in overlay_rows if row["size_matches_map"]
            ),
            "overlay_size_total": len(overlay_rows),
            "unresolved_calls": unresolved,
        },
        "segments": segments,
        "publics": publics,
        "overlays": overlay_rows,
        "sources": sources,
        "anchors": anchors,
        "functions": functions,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--map", required=True, type=Path, help="CIV.MAP from the verified build"
    )
    parser.add_argument(
        "--cod-dir", required=True, type=Path, help="directory holding *.COD listings"
    )
    parser.add_argument("--root", required=True, type=Path, help="unpacked CIV_UNP.EXE")
    parser.add_argument("--packed", type=Path, help="optional original packed CIV.EXE")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    atlas = build_atlas(
        map_path=args.map,
        cod_dir=args.cod_dir,
        root_path=args.root,
        packed_path=args.packed,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(atlas, indent=1, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "functions": atlas["counts"]["c_functions"],
                "entries_verified": atlas["counts"]["entries_verified"],
                "entry_opcodes_verified": atlas["counts"]["entry_opcodes_verified"],
                "map_entry_matches": atlas["counts"]["map_entry_matches"],
                "calls": atlas["counts"]["calls"],
                "call_opcodes_verified": atlas["counts"]["call_opcodes_verified"],
                "call_targets_verified": atlas["counts"]["call_targets_verified"],
                "unresolved_calls": atlas["counts"]["unresolved_calls"],
                "anchors": f"{atlas['counts']['anchors_resolved']}/{atlas['counts']['anchors_total']}",
                "overlays": f"{atlas['verification']['overlay_size_matches']}/{atlas['verification']['overlay_size_total']}",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
