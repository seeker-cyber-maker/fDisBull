"""Rebuild caller-captured GOG Galaxy UPX wrapper images.

The coordinator validates a source wrapper, a source-free capture receipt and a
mapped module image.  It does not launch Galaxy, attach to a process, download a
game or fabricate export identities.  Capture and export enumeration remain
backend responsibilities.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

from .chimprec import recover_iat, rebuild_captured_pe
from .chimprec_capture import executable_code_ranges, validate_capture_manifest
from .chimprec_pe import parse_pe_layout, regions_from_mapped_pe

_MAX_FILE = 512 * 1024 * 1024


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _read(path, label):
    supplied = Path(path).expanduser()
    if supplied.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    selected = supplied.resolve(strict=True)
    if not selected.is_file() or not 0 < selected.stat().st_size <= _MAX_FILE:
        raise ValueError(f"{label} must be a nonempty file of at most 512 MiB")
    return selected, selected.read_bytes()


def inspect_galaxy_wrapper(data: bytes) -> dict:
    """Recognize the bounded UPX-section shape used by inspected Galaxy wrappers."""
    layout = parse_pe_layout(data)
    names = [section["name"] for section in layout["sections"]]
    folded = {name.casefold() for name in names}
    if "upx0" not in folded or "upx1" not in folded:
        raise ValueError("GOG Galaxy wrapper profile requires UPX0 and UPX1 sections")
    packed_entry = layout["image_base"] + layout["entry_rva"]
    entry_section = next((section["name"] for section in layout["sections"]
                          if section["virtual_address"] <= layout["entry_rva"]
                          < section["virtual_address"] + max(section["virtual_size"], section["raw_size"])), None)
    if entry_section is None or entry_section.casefold() != "upx1":
        raise ValueError("GOG Galaxy wrapper profile expects its packed entry in UPX1")
    return {"format": "fdisbull-gog-galaxy-wrapper-1", "bits": layout["bits"],
            "image_base": layout["image_base"], "packed_entry": packed_entry,
            "entry_section": entry_section, "sections": names}


def rebuild_galaxy_capture(wrapper: bytes, mapped_image: bytes, capture: dict,
                           module_exports: list[dict], *, candidate_slots=None,
                           decisions=None, max_slots=4096, gap_limit=10,
                           fixed_base=True) -> dict:
    """Recover imports and rebuild one captured Galaxy wrapper module."""
    wrapper_info = inspect_galaxy_wrapper(wrapper)
    mapped_layout, regions = regions_from_mapped_pe(mapped_image)
    if mapped_layout["bits"] != wrapper_info["bits"]:
        raise ValueError("wrapper and mapped capture bitness differ")
    normalized_capture = validate_capture_manifest(capture, bits=mapped_layout["bits"])
    if normalized_capture["source"]["sha256"] != _sha256(wrapper):
        raise ValueError("capture source hash does not match the Galaxy wrapper")
    if normalized_capture["source"]["size"] != len(wrapper):
        raise ValueError("capture source size does not match the Galaxy wrapper")
    selected = normalized_capture["selected"]
    if selected["module_base"] != mapped_layout["image_base"]:
        raise ValueError("captured module base differs from the mapped image base")
    if selected["module_size"] > mapped_layout["size_image"]:
        raise ValueError("captured module size exceeds the mapped PE image")
    if not normalized_capture["transfer"]["observed"]:
        raise ValueError("Galaxy rebuild requires an observed OEP transfer")
    if normalized_capture["transfer"]["kind"] not in ("jump", "call", "resume", "thread_start"):
        raise ValueError("Galaxy rebuild requires a qualified control-transfer kind")

    lower = mapped_layout["image_base"]
    upper = lower + mapped_layout["size_image"]
    code_ranges = []
    for item in executable_code_ranges(normalized_capture):
        start = max(item["address"], lower)
        end = min(item["address"] + item["length"], upper)
        if start < end:
            code_ranges.append({"address": start, "length": end - start,
                                "evidence": item["evidence"]})
    recovery = recover_iat(regions, mapped_layout["bits"], module_exports,
                           candidate_slots=candidate_slots, max_slots=max_slots,
                           gap_limit=gap_limit,
                           code_ranges=code_ranges if candidate_slots is None else None)
    if not recovery["entries"]:
        raise ValueError("CHimpREC recovered no import entries from the supplied capture")
    rebuilt = rebuild_captured_pe(mapped_image, recovery, oep=selected["oep"],
                                  decisions=decisions, source_layout="mapped",
                                  fixed_base=fixed_base)
    receipt = dict(rebuilt["receipt"])
    receipt.update({
        "format": "fdisbull-gog-galaxy-rebuild-1",
        "wrapper": wrapper_info,
        "source_sha256": _sha256(wrapper),
        "mapped_image_sha256": _sha256(mapped_image),
        "output_sha256": _sha256(rebuilt["image"]),
        "capture": normalized_capture,
        "capture_attachment_performed": False,
        "galaxy_network_download_performed": False,
        "export_map_supplied": True,
        "export_provenance": "caller-supplied; not authenticated by this coordinator",
    })
    return {"image": rebuilt["image"], "receipt": receipt,
            "imports": rebuilt["imports"], "recovery": recovery}


def rebuild_galaxy_files(wrapper, mapped_image, capture, exports, output, *,
                         candidate_slots=None, decisions=None, max_slots=4096,
                         gap_limit=10, fixed_base=True):
    """File-oriented projectless API; output must be a new private directory."""
    wrapper_path, wrapper_bytes = _read(wrapper, "Galaxy wrapper")
    mapped_path, mapped_bytes = _read(mapped_image, "mapped PE image")
    capture_supplied = Path(capture).expanduser()
    exports_supplied = Path(exports).expanduser()
    if capture_supplied.is_symlink() or exports_supplied.is_symlink():
        raise ValueError("capture and exports inputs must not be symlinks")
    capture_path = capture_supplied.resolve(strict=True)
    exports_path = exports_supplied.resolve(strict=True)
    if (not capture_path.is_file() or not exports_path.is_file()
            or capture_path.stat().st_size > 8 * 1024 * 1024
            or exports_path.stat().st_size > 64 * 1024 * 1024):
        raise ValueError("capture JSON must be at most 8 MiB and exports JSON at most 64 MiB")
    try:
        capture_document = json.loads(capture_path.read_text(encoding="utf-8"))
        export_document = json.loads(exports_path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("capture and exports files must contain UTF-8 JSON") from error
    if isinstance(export_document, dict):
        export_document = export_document.get("exports")
    if not isinstance(export_document, list):
        raise ValueError("exports JSON must be a list or an object with an exports list")
    destination = Path(output).expanduser().absolute()
    if destination.exists() or destination.is_symlink() or not destination.parent.is_dir():
        raise ValueError("output must name a new directory under an existing parent")
    result = rebuild_galaxy_capture(wrapper_bytes, mapped_bytes, capture_document,
                                    export_document, candidate_slots=candidate_slots,
                                    decisions=decisions, max_slots=max_slots,
                                    gap_limit=gap_limit, fixed_base=fixed_base)
    destination.mkdir()
    try:
        executable = destination / "galaxy-wrapper-unpacked.exe"
        manifest = destination / "gog-galaxy-rebuild.json"
        executable.write_bytes(result["image"])
        receipt = dict(result["receipt"])
        receipt.update({"inputs": {"wrapper": str(wrapper_path), "mapped_image": str(mapped_path),
                                    "capture": str(capture_path), "exports": str(exports_path)},
                        "output": str(executable)})
        with manifest.open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, indent=2, ensure_ascii=True)
            stream.write("\n")
        return {"format": receipt["format"], "output": str(executable),
                "manifest": str(manifest), "output_sha256": receipt["output_sha256"],
                "import_count": receipt["import_count"],
                "capture_attachment_performed": False}
    except BaseException:
        shutil.rmtree(destination)
        raise
