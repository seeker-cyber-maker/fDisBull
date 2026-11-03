"""CHimpREC-style recovery and PE reconstruction over captured image bytes.

The recovery pass adapts TiGa's candidate-slot/export-resolution methodology,
with explicit bounds, runtime-code-range evidence and retained aliases. The
rebuild pass writes a bounded PE32/PE32+ analysis image with a qualified OEP,
OriginalFirstThunk tables and original IAT slots. Process attachment and export
enumeration remain backend responsibilities and are never fabricated here.

Only export addresses supplied by the caller establish a match. Forwarder
strings are retained as evidence; this API does not guess missing runtime
module mappings or select one of several export aliases.
"""
from __future__ import annotations

import re

from .decoder import decode
from .model import Region

CHIMPREC_COMMIT = "50495c0b9962130c17939bfbef806aecd41040ad"
_MAX_IMAGE = 64 * 1024 * 1024
_MAX_SLOTS = 1_000_000


def _unsigned(value, bits, label):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 1 << bits:
        raise ValueError(f"{label} must be an unsigned {bits}-bit integer")
    return value


def _export_index(exports, bits):
    index = {}
    if len(exports) > _MAX_SLOTS:
        raise ValueError("module_exports exceeds the one-million-record limit")
    for item in exports:
        if not isinstance(item, dict):
            raise ValueError("module_exports entries must be dictionaries")
        address = _unsigned(item.get("address"), bits, "export address")
        module = item.get("module")
        name, ordinal, forwarder = item.get("name"), item.get("ordinal"), item.get("forwarder")
        if not isinstance(module, str) or not module or len(module) > 4096:
            raise ValueError("export module must be a nonempty string of at most 4096 characters")
        if name is not None and (not isinstance(name, str) or len(name) > 65536):
            raise ValueError("export name must be a string of at most 65536 characters or None")
        if forwarder is not None and (not isinstance(forwarder, str) or len(forwarder) > 65536):
            raise ValueError("export forwarder must be a string of at most 65536 characters or None")
        if ordinal is not None:
            _unsigned(ordinal, 32, "export ordinal")
        # A zero target is padding, never a resolved runtime function pointer.
        if not address:
            continue
        alternative = {"address": address, "module": module, "name": name,
                       "ordinal": ordinal, "forwarder": forwarder}
        bucket = index.setdefault(address, [])
        if alternative not in bucket:
            bucket.append(alternative)
    for alternatives in index.values():
        alternatives.sort(key=lambda item: (item["module"].casefold(), item["module"],
                                            item["name"] or "", item["ordinal"] if item["ordinal"] is not None else -1,
                                            item["forwarder"] or ""))
    return index


def recover_iat(regions: list[Region], bits: int, module_exports: list[dict],
                candidate_slots: list[int] | None = None, max_slots: int = 4096,
                gap_limit: int = 10, code_ranges: list[dict] | None = None) -> dict:
    """Recover candidate IAT ranges from an offline snapshot and export map.

    ``candidate_slots`` are virtual addresses of pointer-sized cells, not their
    contents. Without explicit candidates, scan executable bytes for common x86
    absolute/RIP-relative import references (indirect call/jump/push and selected
    MOV loads), corroborating each with the native decoder. ``code_ranges`` can
    explicitly qualify runtime-executable or independently established code spans
    even when file section flags are stale. Discovery remains heuristic and is
    not proof that a byte pattern lies on an executed instruction boundary.

    Any cell matching a supplied export is an anchor. Expand in pointer-sized
    steps within that anchor's region, preserving zero padding and unresolved
    targets. Stop after ``gap_limit`` consecutive unresolved nonzero cells;
    zero padding does not reset or increment that count. ``max_slots`` caps
    unique cell reads across candidate checks and expansion. Scanned bytes are
    capped at 64 MiB. An exhausted budget is reported, never called complete.

    A resolved target may still have several aliases. Every alternative is
    returned and ambiguity remains explicit; no arbitrary symbol is selected.
    """
    if bits not in (32, 64):
        raise ValueError("IAT recovery requires 32 or 64 bits")
    if isinstance(max_slots, bool) or not isinstance(max_slots, int) or not 1 <= max_slots <= _MAX_SLOTS:
        raise ValueError("max_slots must be between 1 and 1000000")
    if isinstance(gap_limit, bool) or not isinstance(gap_limit, int) or not 1 <= gap_limit <= _MAX_SLOTS:
        raise ValueError("gap_limit must be between 1 and 1000000")
    source = {
        "method": "CHimpREC-style offline captured-IAT recovery",
        "repository": "seeker-cyber-maker/CHimpREC",
        "commit": CHIMPREC_COMMIT,
        "runtime_attachment": False,
        "executable_rebuilding": False,
        "rebuild_api": "fdisbull.chimprec.rebuild_captured_pe",
        "discovery": "explicit_slots" if candidate_slots is not None else "decoded_x86_import_reference_patterns",
        "bits": bits,
        "pointer_width": bits // 8,
        "code_range_override": code_ranges is not None,
    }
    result = {"source": source, "entries": [], "groups": [], "warnings": [],
              "candidates_examined": 0, "budget_exhausted": False}
    width = bits // 8
    ordered_regions = sorted(regions, key=lambda region: region.start)
    previous_end, mapped_size = 0, 0
    for region in ordered_regions:
        _unsigned(region.start, 64, "region address")
        end = region.start + len(region.data)
        if end > 1 << 64 or region.start < previous_end:
            raise ValueError("regions must be nonoverlapping and fit the 64-bit address space")
        previous_end = end
        mapped_size += len(region.data)
        if mapped_size > _MAX_IMAGE:
            raise ValueError("IAT snapshot exceeds the 64 MiB limit")
    export_index = _export_index(module_exports, bits)
    if not export_index:
        result["warnings"].append("No nonzero runtime export addresses supplied; IAT recovery requires a captured-module export map.")
        return result

    def containing(address):
        return next((region for region in ordered_regions
                     if region.start <= address and address + width <= region.start + len(region.data)), None)

    candidates = []
    seen_candidates = set()

    def add_candidate(address):
        _unsigned(address, 64, "candidate slot address")
        if address in seen_candidates:
            return True
        if len(candidates) >= max_slots:
            result["budget_exhausted"] = True
            return False
        seen_candidates.add(address)
        candidates.append(address)
        return True

    if candidate_slots is not None:
        for address in candidate_slots:
            if not add_candidate(address):
                break
    else:
        scan_regions = []
        if code_ranges is None:
            scan_regions = [region for region in ordered_regions if region.executable]
        else:
            if not isinstance(code_ranges, list) or len(code_ranges) > 4096:
                raise ValueError("code_ranges must be a list of at most 4096 records")
            previous_end = 0
            total = 0
            for item in sorted(code_ranges, key=lambda row: row.get("address", -1) if isinstance(row, dict) else -1):
                if not isinstance(item, dict):
                    raise ValueError("code_ranges entries must be dictionaries")
                address = item.get("address")
                length = item.get("length")
                _unsigned(address, 64, "code range address")
                _unsigned(length, 64, "code range length")
                if not length or address < previous_end:
                    raise ValueError("code_ranges must be nonempty and nonoverlapping")
                source_region = next((region for region in ordered_regions
                                      if region.start <= address and address + length <= region.start + len(region.data)), None)
                if source_region is None:
                    raise ValueError("code range is not wholly backed by a supplied region")
                total += length
                if total > _MAX_IMAGE:
                    raise ValueError("code_ranges exceed the 64 MiB scan limit")
                offset = address - source_region.start
                evidence = item.get("evidence", "qualified code range")
                if not isinstance(evidence, str) or not evidence or len(evidence) > 4096:
                    raise ValueError("code range evidence must be a nonempty string of at most 4096 characters")
                scan_regions.append(Region(evidence, address,
                                           source_region.data[offset:offset + length], True,
                                           source_region.writable))
                previous_end = address + length
            result["warnings"].append(
                "Explicit code ranges are caller-qualified evidence; they override stale file flags but do not prove execution.")
        full = False
        pattern = re.compile(b"(?:\xff[\x15\x25\x35]|\x8b[\x0d\x15\x1d\x25\x2d\x35\x3d]|\xa1)")
        for region in scan_regions:
            for match in pattern.finditer(region.data):
                offset = match.start()
                instruction = decode(region.data[offset:offset + 15], region.start + offset, "x86", bits)
                if (instruction and instruction.get("data_refs")
                        and instruction.get("flow") in ("indirect_call", "indirect_jump", "fallthrough")):
                    for reference in instruction["data_refs"]:
                        if not add_candidate(reference):
                            full = True
                            break
                if full:
                    break
            if full:
                break
        if candidates:
            result["warnings"].append("Automatic x86 byte-pattern discovery is heuristic; decoded patterns are not proof of executed instruction boundaries.")

    cache = {}
    recovered = {}
    anchors = []
    skipped_candidates = 0

    def read_cell(address, region):
        if address in cache:
            return cache[address]
        if len(cache) >= max_slots:
            result["budget_exhausted"] = True
            return None
        offset = address - region.start
        target = int.from_bytes(region.data[offset:offset + width], "little")
        alternatives = [dict(item) for item in export_index.get(target, [])]
        modules = {item["module"].casefold() for item in alternatives}
        module = alternatives[0]["module"] if len(modules) == 1 else None
        ambiguous = len(alternatives) > 1
        record = {"address": address, "target": target, "resolved": bool(alternatives),
                  "alternatives": alternatives, "ambiguous": ambiguous,
                  "module": module, "group": module,
                  "candidate": address in seen_candidates,
                  "status": ("ambiguous" if ambiguous else "resolved") if alternatives else ("padding" if target == 0 else "unresolved")}
        cache[address] = record
        return record

    for address in candidates:
        result["candidates_examined"] += 1
        region = containing(address)
        if region is None:
            skipped_candidates += 1
            continue
        record = read_cell(address, region)
        if record is None:
            break
        if record["resolved"]:
            anchors.append((address, region))
            recovered[address] = record
    if skipped_candidates:
        result["warnings"].append(f"Skipped {skipped_candidates} candidate slots without a fully mapped {width}-byte cell.")

    # Candidate checks precede expansion so every supplied anchor is preserved
    # before one wide range can consume the remaining work budget.
    expanded = set()
    for anchor_address, region in anchors:
        for direction in (-1, 1):
            address, junk_count = anchor_address + direction * width, 0
            while region.start <= address and address + width <= region.start + len(region.data):
                # Once another anchor's traversal has covered this direction,
                # its resolved cells already reset the same gap state. Reuse
                # that coverage rather than walking a dense table N times.
                expansion_key = (direction, address)
                if expansion_key in expanded:
                    break
                record = read_cell(address, region)
                if record is None:
                    break
                recovered[address] = record
                expanded.add(expansion_key)
                if record["resolved"]:
                    junk_count = 0
                elif record["target"]:
                    junk_count += 1
                    if junk_count >= gap_limit:
                        break
                address += direction * width
    result["entries"] = [recovered[address] for address in sorted(recovered)]
    current_group = None
    for record in result["entries"]:
        module = record["module"]
        if module is None:
            current_group = None
            continue
        if (current_group is not None and current_group["module"].casefold() == module.casefold()
                and current_group["end"] == record["address"]):
            current_group["end"] = record["address"] + width
            current_group["addresses"].append(record["address"])
        else:
            current_group = {"module": module, "start": record["address"],
                             "end": record["address"] + width, "addresses": [record["address"]]}
            result["groups"].append(current_group)
    if not anchors:
        result["warnings"].append("No candidate slot matched a supplied runtime export address; no imports were inferred.")
    if any(record["ambiguous"] for record in result["entries"]):
        result["warnings"].append("Some targets match multiple exports; all aliases are retained without selecting a symbol.")
    if result["budget_exhausted"]:
        result["warnings"].append(f"IAT recovery reached the {max_slots}-slot work budget; results are partial.")
    return result


def _decision_map(decisions):
    if decisions is None:
        return {}
    if not isinstance(decisions, dict) or len(decisions) > _MAX_SLOTS:
        raise ValueError("thunk decisions must be a bounded dictionary")
    normalized = {}
    for raw_address, decision in decisions.items():
        try:
            address = int(raw_address, 0) if isinstance(raw_address, str) else raw_address
        except ValueError as error:
            raise ValueError("thunk decision address is invalid") from error
        _unsigned(address, 64, "thunk decision address")
        if decision in ("cut", "separator"):
            normalized[address] = decision
        elif isinstance(decision, dict):
            alternative = decision.get("alternative")
            if isinstance(alternative, bool) or not isinstance(alternative, int) or alternative < 0:
                raise ValueError("thunk alternative selection must be a nonnegative integer")
            normalized[address] = {"alternative": alternative}
        else:
            raise ValueError("thunk decision must be cut, separator or an alternative selection")
    return normalized


def build_import_plan(recovery: dict, bits: int, decisions: dict | None = None) -> list[dict]:
    """Turn a recovery result and explicit invalid-thunk decisions into import groups.

    Ambiguous entries require an alternative selection. Unresolved candidate
    slots require ``cut`` or ``separator``; noncandidate expansion noise is
    retained by recovery but omitted from the import plan. No symbol or
    separator is invented.
    """
    if bits not in (32, 64):
        raise ValueError("import plan requires 32 or 64 bits")
    if not isinstance(recovery, dict) or not isinstance(recovery.get("entries"), list):
        raise ValueError("recovery result is invalid")
    choices = _decision_map(decisions)
    width = bits // 8
    groups, current, previous = [], None, None
    for entry in sorted(recovery["entries"], key=lambda row: row.get("address", -1)):
        if not isinstance(entry, dict):
            raise ValueError("recovery entries must be dictionaries")
        address = _unsigned(entry.get("address"), 64, "recovered thunk address")
        decision = choices.pop(address, None)
        status = entry.get("status")
        if decision in ("cut", "separator") or status == "padding":
            current, previous = None, None
            continue
        alternatives = entry.get("alternatives")
        if not isinstance(alternatives, list):
            raise ValueError("recovery alternatives must be a list")
        selected = None
        if entry.get("resolved"):
            if decision is None:
                if len(alternatives) != 1:
                    raise ValueError(f"ambiguous import at {address:#x} needs an explicit alternative")
                selected = alternatives[0]
            elif isinstance(decision, dict):
                if decision["alternative"] >= len(alternatives):
                    raise ValueError("selected import alternative is out of range")
                selected = alternatives[decision["alternative"]]
        else:
            # Expansion deliberately retains nearby nonzero junk as evidence.
            # Only an unresolved candidate supplied or referenced by code needs
            # an explicit repair decision; expansion noise never becomes an import.
            if entry.get("candidate"):
                raise ValueError(f"unresolved import at {address:#x} needs an explicit cut or separator decision")
            current, previous = None, None
            continue
        if not isinstance(selected, dict):
            raise ValueError("resolved import selection is invalid")
        module = selected.get("module")
        if not isinstance(module, str) or not module:
            raise ValueError("selected import has no module")
        item = {"address": address, "name": selected.get("name"),
                "ordinal": selected.get("ordinal"), "forwarder": selected.get("forwarder")}
        if (current is None or current["module"].casefold() != module.casefold()
                or previous is None or address != previous + width):
            current = {"module": module, "entries": []}
            groups.append(current)
        current["entries"].append(item)
        previous = address
    if choices:
        raise ValueError("thunk decisions contain addresses absent from the recovery result")
    return groups


def rebuild_captured_pe(captured_image: bytes, recovery: dict, *, oep: int,
                        decisions: dict | None = None, source_layout: str = "mapped",
                        section_name: str = ".reimp", fixed_base: bool = True) -> dict:
    """Rebuild imports and OEP for a captured PE32/PE32+ analysis image."""
    from .chimprec_pe import parse_pe_layout, rebuild_pe_imports
    layout = parse_pe_layout(captured_image)
    plan = build_import_plan(recovery, layout["bits"], decisions)
    result = rebuild_pe_imports(captured_image, plan, oep=oep,
                                source_layout=source_layout, section_name=section_name,
                                fixed_base=fixed_base)
    result["receipt"]["recovery_source"] = recovery.get("source")
    result["receipt"]["explicit_thunk_decisions"] = len(decisions or {})
    return result


# Public provenance helper retained beside the recovery API.
from .chimprec_capture import validate_capture_manifest  # noqa: E402,F401
