"""Experimental P00 DOS intake coordinator over existing fDisBull APIs.

Does not execute installers or games. Privately stores exact file identities while
publishing only aggregates. Tested only against qualified Inno 5.6.2 GOG input.
This is NOT a registered fDisBull CLI/API schema or a semantic proof.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import time
from typing import Any

from fdisbull.gog_unpack import list_gog, unpack_gog, MANIFEST
from fdisbull.disc import inspect_disc_path

FORMAT = "fdisbull-p00-dos-study-1"
NON_GAME_PREFIXES = ("dosbox/", "__support/", "__redist/", "tmp/", "app/", "commonappdata/")
NON_GAME_FILES = ("manual.pdf", "readme.txt")


class IntakeRefused(ValueError):
    """An input/receipt cannot safely be promoted to a qualified P00 result."""


def sha256(path: Path) -> str:
    with path.open("rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def safe_name(name: str) -> None:
    p = PurePosixPath(name)
    if (not name or p.is_absolute() or ".." in p.parts or "\\" in name
            or ":" in name or p.as_posix() != name or any(ord(c) < 32 for c in name)):
        raise IntakeRefused("unsafe inventory path")


def role(name: str) -> str:
    low = name.casefold()
    if low.startswith(NON_GAME_PREFIXES) or low.startswith("goggame-"):
        return "distribution_support"
    if low in NON_GAME_FILES:
        return "documentation"
    return "game_candidate"


def executable_format(path: Path) -> str:
    """Classify executable header only; no instruction decoding/runtime inference."""
    with path.open("rb") as f:
        head = f.read(64)
        if len(head) >= 64 and head[:2] == b"MZ":
            secondary = int.from_bytes(head[0x3C:0x40], "little")
            if secondary and secondary < path.stat().st_size - 4:
                f.seek(secondary)
                sig = f.read(4)
                if sig[:4] == b"PE\x00\x00":
                    f.seek(secondary + 24)
                    opt = f.read(2)
                    return "PE32+" if opt == b"\x0b\x02" else "PE32-or-PE"
                if sig[:2] == b"NE":
                    return "Win16-NE"
                if sig[:2] in (b"LE", b"LX"):
                    return "DOS-extender-or-OS2-" + sig[:2].decode()
            return "DOS-MZ-candidate"
        if path.suffix.casefold() == ".com":
            return "DOS-COM-candidate-raw"
    return "unknown-executable-format"


def verify_extraction(source: Path, private_root: Path, *, extract_if_missing=False) -> tuple[dict, str]:
    """Reuse only when every retained output matches source-bound receipt."""
    before_source = source.stat()
    listing = list_gog(source)
    expected = set(listing["files"])
    if not private_root.exists():
        if not extract_if_missing:
            raise IntakeRefused("private extraction is absent; pass --extract-new")
        receipt = unpack_gog(source, private_root, timeout=3600)
        mode = "fresh_extraction"
    else:
        if private_root.is_symlink() or not private_root.is_dir():
            raise IntakeRefused("private root is not a normal directory")
        path = private_root / MANIFEST
        if not path.is_file() or path.is_symlink():
            raise IntakeRefused("existing extraction lacks source-bound manifest")
        receipt = json.loads(path.read_text(encoding="utf-8"))
        mode = "verified_reuse"
    if (receipt.get("format") != "fdisbull-gog-unpack-1" or
            receipt.get("extractor", {}).get("implementation") != "fdisbull-native-inno"):
        raise IntakeRefused("wrong or unauthenticated extraction contract")
    if receipt.get("source_sha256") != listing["source_sha256"]:
        raise IntakeRefused("source or source-bound manifest changed")
    if sorted(item["path"] for item in receipt.get("files", [])) != sorted(expected):
        raise IntakeRefused("extracted member inventory differs from the installer")
    if sorted(receipt.get("include", [])):
        raise IntakeRefused("only complete extraction accepted for comparative P00")
    names = set()
    entries = receipt["files"]
    for member in private_root.rglob("*"):
        if not (member.is_file() or member.is_dir()) or member.is_symlink():
            raise IntakeRefused("non-regular item in private extracted tree")
        if member.is_dir():
            continue
        if not stat.S_ISREG(member.lstat().st_mode):
            raise IntakeRefused("unexpected special file")
        name = member.relative_to(private_root).as_posix()
        if name != MANIFEST:
            safe_name(name)
            names.add(name)
    if names != expected:
        raise IntakeRefused("extra, missing or changed paths in private extracted tree")
    for item in entries:
        name = item["path"]
        safe_name(name)
        p = private_root / name
        if (not p.is_file() or p.is_symlink() or p.stat().st_size != item["size"]
                or sha256(p) != item["sha256"]):
            raise IntakeRefused("member byte-identity mismatch: " + name)
    after_source = source.stat()
    if (before_source.st_dev, before_source.st_ino, before_source.st_size,
        before_source.st_mtime_ns, before_source.st_ctime_ns) != (
        after_source.st_dev, after_source.st_ino, after_source.st_size,
        after_source.st_mtime_ns, after_source.st_ctime_ns):
        raise IntakeRefused("original source changed during P00 validation")
    return receipt, mode


def index_iso(image: Path, extracted_files: list[dict]) -> tuple[dict, list[dict]]:
    """Read only ISO primary tree; nested file SHA-256 checks logical user data.

    Trailer sectors, CDDA audio and CD EDC/ECC remain explicitly unverified.
    """
    scan = inspect_disc_path(image, max_entries=10000,
                             max_directory_bytes=8 * 1024 * 1024, max_depth=32)
    if scan.get("valid") is not True or scan.get("complete") is not True:
        raise IntakeRefused("CD primary metadata tree is not fully qualified")
    if len(scan["data_tracks"]) != 1 or scan["data_tracks"][0]["mode"] != "MODE1/2352":
        raise IntakeRefused("unsupported CD data track arrangement")
    track = scan["data_tracks"][0]
    fs = track["filesystem"]
    loose = defaultdict(list)
    bypath = {}
    for f in extracted_files:
        loose[(f["size"], f["sha256"])].append(f["path"])
        bypath[f["path"].casefold()] = (f["size"], f["sha256"])
    iso_files = []
    # The fDisBull DataTrackReader is intentionally bounded to 32K sampled
    # sectors. P00's *complete* content-identity pass needs streaming hashing
    # instead; it still consumes the already-validated ISO primary tree.
    before = image.stat()
    with image.open("rb") as reader:
        for e in fs["entries"]:
            if e["kind"] != "file":
                continue
            if not e["available"]:
                raise IntakeRefused("ISO metadata points outside available data track")
            h = hashlib.sha256()
            remain = e["size"]
            sector_start = e["extent_lba"]
            reader.seek(sector_start * 2352)
            for sector_index in range(e["extent_sectors"]):
                data = reader.read(2352)
                if (len(data) != 2352 or data[:12] != b"\x00" + b"\xff" * 10 + b"\x00"
                        or data[15] != 1):
                    raise IntakeRefused("invalid physical Mode 1 framing")
                n = min(remain, 2048)
                h.update(data[16:16+n]); remain -= n
            if remain:
                raise IntakeRefused("ISO member extent undershot content size")
            name = e["path"].lstrip("/")
            source_name = name.split(";", 1)[0]
            sha = h.hexdigest()
            pairs = loose.get((e["size"], sha), [])
            iso_files.append({"path": name, "bytes": e["size"], "sha256": sha,
                              "extent_lba": e["extent_lba"],
                              "matches_loose_content": pairs,
                              "same_path_different_content": source_name.casefold() in bypath and
                                  bypath[source_name.casefold()] != (e["size"], sha)})
    after = image.stat()
    if (before.st_ino, before.st_dev, before.st_size, before.st_mtime_ns) != (
            after.st_ino, after.st_dev, after.st_size, after.st_mtime_ns):
        raise IntakeRefused("CD image changed during member hashing")
    accounting = track["sector_accounting"]
    summary = {
        "container_sha256": sha256(image), "file_bytes": image.stat().st_size,
        "framing": track["mode"], "volume_id": fs["volume_id"],
        "primary_tree_valid": fs["valid"], "primary_tree_complete": fs["complete"],
        "primary_tree_entries": len(fs["entries"]),
        "primary_tree_directories": sum(e["kind"] == "directory" for e in fs["entries"]),
        "primary_tree_files": len(iso_files),
        "primary_tree_file_bytes": sum(e["bytes"] for e in iso_files),
        "primary_tree_file_hashes_computed": len(iso_files),
        "matches_loose_by_content": sum(bool(e["matches_loose_content"]) for e in iso_files),
        "same_path_different_content": sum(e["same_path_different_content"] for e in iso_files),
        "declared_iso_sectors": accounting["declared_volume_sectors"],
        "physical_image_sectors": accounting["data_track_program_sectors"],
        "remaining_unclassified_sectors": accounting["data_track_program_sectors"] - accounting["declared_volume_sectors"],
        "track_layout_known": False,
        "audio_validated": False,
        "edc_ecc_validated": False,
        "member_extensions": dict(sorted(Counter(Path(e["path"].split(";", 1)[0]).suffix.casefold() or "<none>"
                                                   for e in iso_files).items())),
    }
    return summary, iso_files


def intake(label: str, installer: Path, extracted: Path, *, extract_if_missing=False) -> dict[str, Any]:
    start = time.perf_counter()
    if installer.is_symlink():
        raise IntakeRefused("installer is a symlink")
    installer = installer.resolve(strict=True)
    if not installer.is_file():
        raise IntakeRefused("installer is not a normal file")
    manifest, mode = verify_extraction(installer, extracted, extract_if_missing=extract_if_missing)
    after_verify = time.perf_counter()
    iso_seconds = 0.0
    files = manifest["files"]
    roles = Counter(role(f["path"]) for f in files)
    role_bytes = Counter()
    exe = []
    discs = []
    for f in files:
        name = f["path"]
        role_name = role(name)
        role_bytes[role_name] += f["size"]
        obj = extracted / name
        if obj.suffix.casefold() in (".exe", ".com"):
            exe.append({"path": name, "format_hint": executable_format(obj),
                        "bytes": f["size"], "sha256": f["sha256"], "role": role_name,
                        "entry_verified": False})
        if obj.suffix.casefold() == ".gog" and role_name == "game_candidate":
            with obj.open("rb") as fh:
                prefix = fh.read(12)
            if prefix == b"\x00" + b"\xff" * 10 + b"\x00":
                before_iso = time.perf_counter()
                disk, disk_files = index_iso(obj, files)
                iso_seconds += time.perf_counter() - before_iso
                disk["path"] = name
                disk["members"] = disk_files
                discs.append(disk)
    native = {
        "format": FORMAT, "phase": "P00 Intake", "status": "observed-and-hash-checked",
        "target_label_user_declared": label,
        "source": {"name": installer.name, "size": installer.stat().st_size,
                   "sha256": manifest["source_sha256"],
                   "installer_profile": manifest["extractor"].get("profile"),
                   "installer_executed": False},
        "extraction": {"mode": mode, "backend": manifest["extractor"]["implementation"],
                       "files": len(files), "bytes": sum(f["size"] for f in files),
                       "all_file_sha256_verified": True,
                       "support_count": roles.get("distribution_support", 0),
                       "game_candidate_count": roles.get("game_candidate", 0),
                       "documentation_count": roles.get("documentation", 0),
                       "role_file_counts": dict(roles), "role_bytes": dict(role_bytes),
                       "private_member_manifest_sha256": sha256(extracted / MANIFEST)},
        "executable_candidates": exe,
        "disc_images": discs,
        "obligations": ["Confirm executable entry and OS/BIOS/driver profile in P01",
                        "Original runtime/semantic compatibility not tested",
                        "Unknown external media/physical disc tail not promoted to game files"],
        "qualification": {"source_bytes_preserved": True,
                          "selected_artifact_hashes_checked": True,
                          "disc_primary_tree_inspected": bool(discs),
                          "run_or_original_semantic_evidence": False},
        "metrics": {"total_wall_s": round(time.perf_counter()-start, 6),
                    "source_and_member_verification_s": round(after_verify-start, 6),
                    "nested_iso_metadata_and_member_hashing_s": round(iso_seconds, 6),
                    "classification_and_receipt_s": round(time.perf_counter()-after_verify-iso_seconds, 6)},
    }
    native["source"]["kind"] = "gog-inno-installer"
    return native


def intake_raw(label: str, path: Path) -> dict[str, Any]:
    """The same P00 identity contract for a directly supplied DOS COM/MZ file.

    This mode deliberately does not infer an OS, an entry point, or execution
    semantics from the filename. It is a control for non-installer sources.
    """
    start = time.perf_counter()
    if path.is_symlink():
        raise IntakeRefused("raw source must not be a symlink")
    path = path.resolve(strict=True)
    if not path.is_file() or not 0 < path.stat().st_size <= 100_000_000:
        raise IntakeRefused("raw source must be a bounded regular file")
    if path.suffix.casefold() not in (".com", ".exe"):
        raise IntakeRefused("direct-file mode admits only candidate DOS COM/MZ inputs")
    fmt = executable_format(path)
    if fmt not in ("DOS-MZ-candidate", "DOS-COM-candidate-raw"):
        raise IntakeRefused("raw target is not a supported DOS executable candidate")
    source_sha = sha256(path)
    size = path.stat().st_size
    return {
        "format": FORMAT, "phase": "P00 Intake", "status": "observed-and-hash-checked",
        "target_label_user_declared": label,
        "source": {"kind": "direct-dos-artifact", "name": path.name,
                   "size": size, "sha256": source_sha,
                   "installer_profile": None, "installer_executed": False},
        "extraction": {"mode": "direct-unpacked", "backend": "exact-byte-reader",
                       "files": 1, "bytes": size, "all_file_sha256_verified": True,
                       "role_file_counts": {"game_candidate": 1},
                       "role_bytes": {"game_candidate": size},
                       "private_member_manifest_sha256": None},
        "executable_candidates": [{"path":path.name,"format_hint":fmt,
                                   "bytes":size,"sha256":source_sha,
                                   "role":"game_candidate", "entry_verified":False}],
        "disc_images": [],
        "obligations": ["Confirm loaded-image mapping and runtime/OS profile in P01",
                        "No source semantics or original guest execution claimed"],
        "qualification": {"source_bytes_preserved": True,
                          "selected_artifact_hashes_checked": True,
                          "disc_primary_tree_inspected": False,
                          "run_or_original_semantic_evidence": False},
        "metrics": {"total_wall_s": round(time.perf_counter()-start, 6),
                    "source_and_member_verification_s": round(time.perf_counter()-start, 6),
                    "nested_iso_metadata_and_member_hashing_s": 0.0,
                    "classification_and_receipt_s": 0.0}
    }


def public_summary(private: dict) -> dict:
    """Only aggregate and source identities; no full private file inventory."""
    e = private["extraction"]
    return {"target": private["target_label_user_declared"],
            "source_kind": private["source"].get("kind", "unspecified"),
            "source_sha256": private["source"]["sha256"],
            "installer_profile": private["source"]["installer_profile"],
            "source_bytes": private["source"]["size"],
            "files": e["files"], "payload_bytes": e["bytes"],
            "role_file_counts": e["role_file_counts"],
            "role_bytes": e["role_bytes"],
            "executable_summary": dict(Counter(x["format_hint"] for x in private["executable_candidates"]
                                        if x["role"] == "game_candidate")),
            "disc_images": [{k: d[k] for k in (
                "framing", "volume_id", "file_bytes", "primary_tree_valid",
                "primary_tree_complete", "primary_tree_entries", "primary_tree_directories",
                "primary_tree_files", "primary_tree_file_hashes_computed",
                "matches_loose_by_content", "same_path_different_content",
                "remaining_unclassified_sectors", "track_layout_known", "audio_validated")}
                for d in private["disc_images"]],
            "qualification": private["qualification"],
            "wall_seconds": private["metrics"]["total_wall_s"],
            "phase_seconds": private["metrics"]}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--installer", action="append", default=[], metavar="LABEL=FILE")
    p.add_argument("--raw", action="append", default=[], metavar="LABEL=COM_OR_MZ")
    p.add_argument("--private-root", required=True, type=Path,
                   help="existing private extraction parent; absent roots require --extract-new")
    p.add_argument("--output-private", required=True, type=Path, help="private output directory; must not exist")
    p.add_argument("--extract-new", action="store_true", help="explicitly extract absent sources")
    a = p.parse_args(argv)
    if a.output_private.exists() or a.output_private.is_symlink():
        p.error("output-private must not already exist")
    specs = []
    for kind, item in [("installer", x) for x in a.installer] + [("raw", x) for x in a.raw]:
        if "=" not in item:
            p.error("--installer requires LABEL=PATH")
        label, path = item.split("=", 1)
        if not label or not path or "/" in label or "\\" in label:
            p.error("unsafe or missing source label")
        specs.append((label, Path(path), kind))
    if not specs:
        p.error("provide at least one --installer or --raw source")
    if len(set(label.casefold() for label, path, kind in specs)) != len(specs):
        p.error("duplicate source labels")
    a.output_private.mkdir(parents=True, exist_ok=False)
    reports = []
    if a.extract_new:
        a.private_root.mkdir(parents=True, exist_ok=True)
    for label, source, kind in specs:
        print("P00 checking", label, flush=True)
        report = (intake_raw(label, source) if kind == "raw" else
                  intake(label, source, a.private_root / label,
                         extract_if_missing=a.extract_new))
        (a.output_private / f"{label}.private.json").write_text(json.dumps(report, indent=2) + "\n")
        reports.append(public_summary(report))
        print("P00 verified", label, "files", report["extraction"]["files"], flush=True)
    public = {"format": FORMAT, "status": "qualified-artifact-intake-only",
              "sources": reports, "limitations": [
                  "Private game originals, byte-retaining data and all game-member paths excluded from public report",
                  "No live game execution or original-to-UIL equivalence",
                  "Disc primary tree verified, but track layout, CDDA and EDC/ECC remain unqualified",
                  "Executable classifications are header-based candidates, not launch success",
              ]}
    (a.output_private / "P00-PUBLIC-AGGREGATES.json").write_text(json.dumps(public, indent=2)+"\n")
    print(json.dumps(public, indent=2), flush=True)


if __name__ == "__main__":
    main()