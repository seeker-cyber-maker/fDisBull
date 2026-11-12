"""Safely unpack supported GOG Inno Setup payloads with fDisBull's native reader.

No subprocess, Wine, or external innoextract binary is needed. Unsupported
Inno versions and external slices fail closed instead of guessing file data.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import shutil
import stat
import tempfile
import time
from pathlib import Path, PurePosixPath

from .library import check_library
from .native_inno import SUPPORTED, NativeInno

MANIFEST = "gog-unpack-manifest.json"


def _digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _identity(path):
    st = path.stat()
    return (st.st_size, st.st_mtime_ns, st.st_ino, st.st_dev)


def _parts(path):
    # These adjacent parts are provenance candidates, not proof of consumption.
    prefix = path.stem.casefold() + "-"
    return sorted(
        p
        for p in path.parent.iterdir()
        if p.is_file()
        and p.name.casefold().startswith(prefix)
        and p.suffix.casefold() == ".bin"
    )


def _inputs(path, *, source_sha256, source_size):
    """Admit one installer identity without re-hashing the main executable."""
    entries = [{"name": path.name, "size": source_size, "sha256": source_sha256}]
    admissions = {path: _identity(path)}
    for part in _parts(path):
        entries.append(
            {"name": part.name, "size": part.stat().st_size, "sha256": _digest(part)}
        )
        admissions[part] = _identity(part)
    return entries, admissions


def _unchanged(admissions):
    return all(_identity(path) == identity for path, identity in admissions.items())


def _safe_inventory(files):
    seen = set()
    for name in files:
        path = PurePosixPath(name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or not path.parts
            or "\\" in name
            or ":" in name
            or "\x00" in name
            or any(ord(c) < 32 or ord(c) == 127 for c in name)
            or path.as_posix() != name
        ):
            raise ValueError(f"Unsafe or ambiguous installer member: {name!r}")
        folded = name.casefold()
        if folded in seen or folded == MANIFEST.casefold():
            raise ValueError(f"Colliding installer member: {name!r}")
        seen.add(folded)
    if not files:
        raise ValueError("No files matched the installer selection")
    return sorted(files)


def _prepare(path, include, timeout):
    if type(timeout) is not int or not 1 <= timeout <= 3600:
        raise ValueError("timeout must be an integer from 1 to 3600 seconds")
    if include is None:
        include = []
    if not isinstance(include, list) or any(
        not isinstance(p, str) or not p or "\x00" in p for p in include
    ):
        raise ValueError("include must be a list of nonempty path filters")
    source = Path(path).expanduser().resolve(strict=True)
    if not source.is_file():
        raise ValueError("Expected a local GOG Inno Setup installer file")
    deadline = time.monotonic() + timeout
    native = NativeInno.open(source, deadline=deadline)
    inputs, admissions = _inputs(
        source,
        source_sha256=native.source_sha256,
        source_size=getattr(native, "size", source.stat().st_size),
    )
    if not _unchanged(admissions):
        raise ValueError("Installer inputs changed during admission")
    names = [item["path"] for item in native.inventory]
    if include:
        selected = []
        for name in names:
            folded = name.casefold()
            if any(
                fnmatch.fnmatchcase(folded, pattern.casefold())
                or folded.startswith(pattern.casefold().rstrip("/") + "/")
                for pattern in include
            ):
                selected.append(name)
        names = selected
    files = _safe_inventory(names)
    result = {
        "format": "fdisbull-gog-unpack-1",
        "installer": str(source),
        "inputs": inputs,
        "adjacent_parts": (
            "Matching basename-*.bin files hashed; only embedded slices supported."
        ),
        "extractor": {
            "implementation": "fdisbull-native-inno",
            "profile": SUPPORTED,
            "requires_innoextract": False,
        },
        "include": include,
        "files": files,
        "warnings": "",
        "installer_executed": False,
        "source_sha256": native.source_sha256,
    }
    return source, native, result, deadline, admissions


def list_gog(path, *, include=None, timeout=300, library_config=None):
    """Return a read-only, filtered installer inventory; never launch its EXE."""
    source, native, result, _, admissions = _prepare(path, include, timeout)
    if not _unchanged(admissions):
        raise ValueError("Installer inputs changed during inventory")
    result["library"] = check_library(
        [(source.name, native.source_sha256)], library_config
    )
    return result


def unpack_gog(path, output, *, include=None, timeout=300, library_config=None):
    """Extract to a new directory, verify the listing, and retain file hashes."""
    destination = Path(output).expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("Output already exists; choose a new private directory")
    if not destination.parent.is_dir():
        raise ValueError("Output parent must already be a directory")
    source, native, result, deadline, admissions = _prepare(path, include, timeout)
    # Exclusive mkdir owns the new destination even if another writer races us.
    # Staging and final payload share a filesystem, so publication moves files
    # without copying large disc images a second time.
    destination.mkdir()
    try:
        with tempfile.TemporaryDirectory(prefix=".inno-", dir=destination) as temp:
            staging = Path(temp)
            data_root = staging / "payload"
            written = native.extract_selected(
                data_root, result["files"], emit_manifest=False, deadline=deadline
            )
            files = []
            actual = set()
            for item in sorted(data_root.rglob("*")):
                mode = item.lstat().st_mode
                if stat.S_ISDIR(mode):
                    continue
                if not stat.S_ISREG(mode):
                    raise ValueError("Native decoder produced a non-regular file")
                actual.add(item.relative_to(data_root).as_posix())
            for record in written:
                item = data_root / record["path"]
                if item.stat().st_size != record["bytes"]:
                    raise ValueError("Extracted file size changed during publication")
                with item.open("rb") as stream:
                    magic = stream.read(4)
                files.append(
                    {
                        "path": record["path"],
                        "size": record["bytes"],
                        "sha256": record["sha256"],
                        "executable_candidate": (
                            item.suffix.casefold() in (".exe", ".com")
                            or magic[:2] in (b"MZ", b"ZM")
                        ),
                    }
                )
            if actual != {item["path"] for item in files} or sorted(
                item["path"] for item in files
            ) != result["files"]:
                raise ValueError("Extracted files do not match the selected inventory")
            if not _unchanged(admissions):
                raise ValueError("Installer inputs changed during extraction")
            result.update(
                output=str(destination),
                files=files,
                manifest=str(destination / MANIFEST),
            )
            result["library"] = check_library(
                [(item["path"], item["sha256"]) for item in files], library_config
            )
            for member in data_root.iterdir():
                member.rename(destination / member.name)
        with (destination / MANIFEST).open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, ensure_ascii=True)
            stream.write("\n")
        return result
    except BaseException:
        # Only the exclusively created directory belongs to this attempt.
        shutil.rmtree(destination)
        raise
