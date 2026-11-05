#!/usr/bin/env python3
"""Check native GOG decoder presence/identity in wheels, sources, or offline kits.

This complements check_dist.py, not a replacement for its privacy checks or for
running an installed-wheel extraction. Archive source is parsed, never executed.
"""
from __future__ import annotations

import argparse
import ast
from hashlib import sha256
import io
import json
from pathlib import Path
import re
import tarfile
import zipfile

MODULES = ("native_inno.py", "gog_unpack.py")
PROFILES = {"Inno Setup Setup Data (5.5.7) (u)", "Inno Setup Setup Data (5.6.2) (u)"}
MAX_MODULE = 2 * 1024 * 1024
MAX_INNER_ARCHIVE = 32 * 1024 * 1024


def _module_name(name):
    return next((item for item in MODULES if ("/" + name).endswith("/fdisbull/" + item)), None)


def _inspect(modules):
    missing = set(MODULES) - modules.keys()
    if missing:
        raise ValueError("Package lacks native GOG decoder modules: " + ", ".join(sorted(missing)))
    trees = {name: ast.parse(raw.decode("utf-8"), filename=name) for name, raw in modules.items()}
    wrapper = trees["gog_unpack.py"]
    if not any(isinstance(node, ast.ImportFrom) and node.module == "native_inno"
               and any(alias.name == "NativeInno" for alias in node.names) for node in ast.walk(wrapper)):
        raise ValueError("GOG adapter is not wired to the native reader")
    for tree in trees.values():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(a.name == "subprocess" for a in node.names):
                raise ValueError("GOG extraction still imports subprocess")
            if isinstance(node, ast.ImportFrom) and node.module == "subprocess":
                raise ValueError("GOG extraction still imports subprocess")
    # Read only literal profile declarations; never eval package code.
    values = {}
    for node in trees["native_inno.py"].body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        key = node.targets[0].id
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            values[key] = node.value.value
        elif key == "SUPPORTED_PROFILES" and isinstance(node.value, (ast.Tuple, ast.List)):
            profiles = [values.get(item.id) if isinstance(item, ast.Name)
                        else item.value if isinstance(item, ast.Constant) else None for item in node.value.elts]
            values[key] = profiles
    if set(values.get("SUPPORTED_PROFILES", [])) != PROFILES:
        raise ValueError("Native GOG profile declarations differ from the qualified 5.5.7/5.6.2 set")
    return {name: sha256(raw).hexdigest() for name, raw in modules.items()}


def _zip_modules(archive):
    modules = {}
    for item in archive.infolist():
        name = _module_name(item.filename)
        if name is None:
            continue
        if name in modules or item.file_size > MAX_MODULE:
            raise ValueError("Duplicate or oversized native GOG module")
        modules[name] = archive.read(item)
    return modules


def _tar_modules(archive):
    modules = {}
    for item in archive:
        name = _module_name(item.name)
        if name is None:
            continue
        if name in modules or not item.isfile() or item.size > MAX_MODULE:
            raise ValueError("Duplicate, non-regular or oversized native GOG module")
        with archive.extractfile(item) as stream:
            modules[name] = stream.read(MAX_MODULE + 1)
    return modules


def check_native_gog(path):
    """Return exact packaged source identities; do not imply runtime acceptance."""
    path = Path(path)
    if path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as archive:
            hashes = _inspect(_tar_modules(archive))
        artifacts = {path.name: hashes}
    elif path.suffix in (".whl", ".zip"):
        with zipfile.ZipFile(path) as archive:
            modules = _zip_modules(archive)
            if modules or path.suffix == ".whl":
                artifacts = {path.name: _inspect(modules)}
            else:
                # Only canonical application artifacts, not dependency/native
                # runtime archives; each application artifact must agree.
                selected = [item for item in archive.infolist() if re.fullmatch(
                    r"fdisbull-[0-9][^/]*(?:-py3-none-any\.whl|-tool\.zip|\.tar\.gz)", Path(item.filename).name)
                    and "-linux-" not in item.filename]
                if not selected:
                    raise ValueError("No native GOG modules or canonical application artifacts found")
                artifacts = {}
                for item in selected:
                    if item.filename in artifacts or item.file_size > MAX_INNER_ARCHIVE:
                        raise ValueError("Duplicate or oversized inner application archive")
                    data = io.BytesIO(archive.read(item))
                    if item.filename.endswith(".tar.gz"):
                        with tarfile.open(fileobj=data, mode="r:gz") as inner:
                            modules = _tar_modules(inner)
                    else:
                        with zipfile.ZipFile(data) as inner:
                            modules = _zip_modules(inner)
                    artifacts[item.filename] = _inspect(modules)
    else:
        raise ValueError("Expected a wheel, source ZIP/tar.gz or offline-kit ZIP")
    first = next(iter(artifacts.values()))
    if any(hashes != first for hashes in artifacts.values()):
        raise ValueError("Native GOG source differs across packaged application artifacts")
    return {"format": "fdisbull-native-gog-delivery-1", "artifact": path.name,
            "profiles": sorted(PROFILES), "module_hashes": first,
            "artifacts_checked": len(artifacts), "runtime_validation": "not_run"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="+", type=Path)
    args = parser.parse_args()
    try:
        results = [check_native_gog(path) for path in args.archives]
        if any(row["module_hashes"] != results[0]["module_hashes"] for row in results[1:]):
            raise ValueError("Native GOG source differs across selected archives")
    except (ValueError, OSError, SyntaxError, UnicodeError, zipfile.BadZipFile, tarfile.TarError) as exc:
        parser.exit(1, str(exc) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
