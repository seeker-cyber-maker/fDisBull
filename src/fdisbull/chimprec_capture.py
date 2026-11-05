"""Bounded provenance records for CHimpREC-style runtime captures.

The record identifies the process, thread, module, runtime regions and observed
control transfer that produced a captured image.  It deliberately contains no
memory bytes.  Capture and attachment remain backend responsibilities.
"""
from __future__ import annotations

import re

_MAX_PROCESSES = 64
_MAX_THREADS = 4096
_MAX_REGIONS = 4096
_TRANSFER_KINDS = {"jump", "call", "resume", "thread_start", "return", "unknown"}
_REGION_KINDS = {"image", "code", "data", "iat", "injected", "stack", "heap", "unknown"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _uint(value, bits, label):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 1 << bits:
        raise ValueError(f"{label} must be an unsigned {bits}-bit integer")
    return value


def _identifier(value, label):
    if not isinstance(value, str) or not value or len(value) > 256 or "\x00" in value:
        raise ValueError(f"{label} must be a nonempty string of at most 256 characters")
    return value


def _hash(value, label):
    if not isinstance(value, str) or not _SHA256.fullmatch(value.casefold()):
        raise ValueError(f"{label} must be a lowercase SHA-256 string")
    return value.casefold()


def validate_capture_manifest(document: dict, *, bits: int | None = None) -> dict:
    """Validate and normalize a source-free process/module capture receipt.

    A valid record proves only that the caller supplied a coherent description.
    It does not authenticate the debugger or establish that the OEP is correct.
    """
    if not isinstance(document, dict) or document.get("format") != "fdisbull-chimprec-capture-1":
        raise ValueError("capture format must be fdisbull-chimprec-capture-1")
    declared_bits = document.get("bits")
    if declared_bits not in (32, 64):
        raise ValueError("capture bits must be 32 or 64")
    if bits is not None and declared_bits != bits:
        raise ValueError("capture bitness does not match the selected image")
    source = document.get("source")
    if not isinstance(source, dict):
        raise ValueError("capture source must be a dictionary")
    normalized_source = {
        "sha256": _hash(source.get("sha256"), "capture source sha256"),
        "size": _uint(source.get("size"), 64, "capture source size"),
        "label": source.get("label", "captured executable"),
    }
    if normalized_source["size"] == 0:
        raise ValueError("capture source size must be nonzero")
    _identifier(normalized_source["label"], "capture source label")

    processes = document.get("processes")
    if not isinstance(processes, list) or not 1 <= len(processes) <= _MAX_PROCESSES:
        raise ValueError("capture processes must contain 1..64 records")
    normalized_processes, process_ids = [], set()
    for item in processes:
        if not isinstance(item, dict):
            raise ValueError("capture process entries must be dictionaries")
        process_id = _identifier(item.get("id"), "process id")
        if process_id in process_ids:
            raise ValueError("capture process ids must be unique")
        process_ids.add(process_id)
        parent = item.get("parent_id")
        if parent is not None:
            _identifier(parent, "parent process id")
        image_base = _uint(item.get("image_base"), declared_bits, "process image base")
        image_size = _uint(item.get("image_size"), 64, "process image size")
        if not image_size or image_base + image_size > 1 << declared_bits:
            raise ValueError("process image must be nonempty and fit its address space")
        normalized_processes.append({
            "id": process_id,
            "parent_id": parent,
            "image_base": image_base,
            "image_size": image_size,
            "label": _identifier(item.get("label", process_id), "process label"),
        })
    for item in normalized_processes:
        if item["parent_id"] is not None and item["parent_id"] not in process_ids:
            raise ValueError("capture parent process is not present")

    threads = document.get("threads", [])
    if not isinstance(threads, list) or len(threads) > _MAX_THREADS:
        raise ValueError("capture threads must be a list of at most 4096 records")
    normalized_threads, thread_ids = [], set()
    for item in threads:
        if not isinstance(item, dict):
            raise ValueError("capture thread entries must be dictionaries")
        thread_id = _identifier(item.get("id"), "thread id")
        if thread_id in thread_ids:
            raise ValueError("capture thread ids must be unique")
        process_id = _identifier(item.get("process_id"), "thread process id")
        if process_id not in process_ids:
            raise ValueError("capture thread refers to an unknown process")
        thread_ids.add(thread_id)
        normalized_threads.append({"id": thread_id, "process_id": process_id})

    regions = document.get("regions")
    if not isinstance(regions, list) or not 1 <= len(regions) <= _MAX_REGIONS:
        raise ValueError("capture regions must contain 1..4096 records")
    normalized_regions = []
    by_process = {process_id: [] for process_id in process_ids}
    for item in regions:
        if not isinstance(item, dict):
            raise ValueError("capture region entries must be dictionaries")
        process_id = _identifier(item.get("process_id"), "region process id")
        if process_id not in process_ids:
            raise ValueError("capture region refers to an unknown process")
        start = _uint(item.get("start"), declared_bits, "region start")
        size = _uint(item.get("size"), 64, "region size")
        if size == 0 or start + size > 1 << declared_bits:
            raise ValueError("capture region must be nonempty and fit its address space")
        protection = item.get("protection")
        if not isinstance(protection, str) or not protection or len(protection) > 16:
            raise ValueError("region protection must be a short nonempty string")
        kind = item.get("kind", "unknown")
        if kind not in _REGION_KINDS:
            raise ValueError("unknown capture region kind")
        digest = item.get("sha256")
        if digest is not None:
            digest = _hash(digest, "region sha256")
        record = {"process_id": process_id, "start": start, "size": size,
                  "protection": protection, "kind": kind, "sha256": digest}
        normalized_regions.append(record)
        by_process[process_id].append(record)
    for process_id, items in by_process.items():
        previous = 0
        for item in sorted(items, key=lambda row: row["start"]):
            if item["start"] < previous:
                raise ValueError(f"capture regions overlap in process {process_id}")
            previous = item["start"] + item["size"]

    selected = document.get("selected")
    if not isinstance(selected, dict):
        raise ValueError("capture selected module must be a dictionary")
    selected_process = _identifier(selected.get("process_id"), "selected process id")
    if selected_process not in process_ids:
        raise ValueError("selected process is not present")
    selected_thread = selected.get("thread_id")
    if selected_thread is not None:
        _identifier(selected_thread, "selected thread id")
        matching = next((row for row in normalized_threads if row["id"] == selected_thread), None)
        if matching is None or matching["process_id"] != selected_process:
            raise ValueError("selected thread is not present in the selected process")
    module_base = _uint(selected.get("module_base"), declared_bits, "selected module base")
    module_size = _uint(selected.get("module_size"), 64, "selected module size")
    oep = _uint(selected.get("oep"), declared_bits, "selected OEP")
    if not module_size or not module_base <= oep < module_base + module_size <= 1 << declared_bits:
        raise ValueError("selected OEP must lie within the selected module")
    if not any(region["process_id"] == selected_process
               and region["start"] <= module_base
               and module_base + module_size <= region["start"] + region["size"]
               for region in normalized_regions):
        raise ValueError("selected module is not wholly covered by a captured region")

    transfer = document.get("transfer")
    if not isinstance(transfer, dict):
        raise ValueError("capture transfer must be a dictionary")
    kind = transfer.get("kind")
    if kind not in _TRANSFER_KINDS:
        raise ValueError("unknown capture transfer kind")
    transfer_process = _identifier(transfer.get("process_id"), "transfer process id")
    if transfer_process != selected_process:
        raise ValueError("capture transfer must belong to the selected process")
    transfer_thread = transfer.get("thread_id")
    if transfer_thread is not None:
        _identifier(transfer_thread, "transfer thread id")
        if selected_thread is not None and transfer_thread != selected_thread:
            raise ValueError("capture transfer thread differs from the selected thread")
    source_address = transfer.get("from")
    if source_address is not None:
        source_address = _uint(source_address, declared_bits, "transfer source")
    target = _uint(transfer.get("to"), declared_bits, "transfer target")
    if target != oep:
        raise ValueError("capture transfer target must equal the selected OEP")
    observed = transfer.get("observed")
    if type(observed) is not bool:
        raise ValueError("capture transfer observed must be a boolean")

    normalized = {
        "format": "fdisbull-chimprec-capture-1",
        "bits": declared_bits,
        "source": normalized_source,
        "processes": normalized_processes,
        "threads": normalized_threads,
        "regions": normalized_regions,
        "selected": {"process_id": selected_process, "thread_id": selected_thread,
                     "module_base": module_base, "module_size": module_size, "oep": oep},
        "transfer": {"kind": kind, "process_id": transfer_process,
                     "thread_id": transfer_thread, "from": source_address,
                     "to": target, "observed": observed},
    }
    return normalized


def executable_code_ranges(manifest: dict) -> list[dict]:
    """Return caller-qualified executable spans for the selected process."""
    selected = manifest["selected"]["process_id"]
    ranges = []
    for region in manifest["regions"]:
        if region["process_id"] == selected and "x" in region["protection"].casefold():
            ranges.append({"address": region["start"], "length": region["size"],
                           "evidence": "runtime executable protection in capture manifest"})
    return ranges
