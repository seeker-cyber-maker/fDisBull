"""CHimpREC-style import recovery over supplied, captured image bytes.

This adapts TiGa's candidate-slot/export-resolution methodology, with explicit
bounds and retained aliases. It neither attaches to a process nor rebuilds an
executable. Static import-directory parsing remains a separate operation.

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
                gap_limit: int = 10) -> dict:
    """Recover candidate IAT ranges from an offline snapshot and export map.

    ``candidate_slots`` are virtual addresses of pointer-sized cells, not their
    contents. Without explicit candidates, scan executable bytes for x86
    ``FF 15/25`` forms and corroborate each with the native decoder; in x64 the
    memory address is signed RIP-relative. This is still heuristic discovery,
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
        "discovery": "explicit_slots" if candidate_slots is not None else "decoded_x86_ff15_ff25_patterns",
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
        full = False
        for region in ordered_regions:
            if not region.executable:
                continue
            for match in re.finditer(b"\xff[\x15\x25]", region.data):
                offset = match.start()
                if offset + 6 > len(region.data):
                    continue
                instruction = decode(region.data[offset:offset + 6], region.start + offset, "x86", bits)
                if (instruction and instruction["size"] == 6
                        and instruction["flow"] in ("indirect_call", "indirect_jump")
                        and len(instruction["data_refs"]) == 1):
                    if not add_candidate(instruction["data_refs"][0]):
                        full = True
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
