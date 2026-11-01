#!/usr/bin/env python3
"""Build or reuse a hash-locked Linux x86-64 dependency bundle.

The bundle contains third-party wheels only.  It deliberately excludes the
fdisbull and fdisbull-player wheels, so a bundle stays reusable across tool
releases while the dependency constraints remain unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from email.parser import BytesParser
from email.policy import default
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
FORMAT = "fdisbull-offline-dependencies-1"
DEFAULT_EXTRAS = ("proof",)
TARGET = {
    "python_tag": "cp313",
    "python": "3.13",
    "platform": "linux-x86_64",
}
WHEEL_SUFFIX = ".whl"
SHA_SUFFIXES = (".tar.gz", ".tgz")


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def canonical_requirement(text: str) -> str:
    """Return a stable spelling for a requirement without normalizing versions."""
    text = text.strip()
    if not text:
        raise ValueError("empty requirement")
    marker = None
    if ";" in text:
        text, marker = text.split(";", 1)
    match = re.fullmatch(
        r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*(.*)", text
    )
    if not match:
        raise ValueError(f"invalid requirement: {text!r}")
    name, extras, specifier = match.groups()
    specifier = specifier.replace(" ", "")
    if not specifier:
        raise ValueError(f"dependency must have a version constraint: {text!r}")
    value = normalize(name) + (extras or "") + specifier
    if marker:
        value += ";" + marker.strip()
    return value


def requirement_name(requirement: str) -> str:
    head = requirement.split(";", 1)[0]
    match = re.match(r"([A-Za-z0-9][A-Za-z0-9._-]*)", head)
    if not match:
        raise ValueError(f"invalid canonical requirement: {requirement}")
    return normalize(match.group(1))


def load_requirements(project_root: Path, extras: tuple[str, ...]) -> list[str]:
    project = tomllib.loads((project_root / "pyproject.toml").read_text())
    data = project["project"]
    definitions = data.get("optional-dependencies", {})
    requirements = list(data.get("dependencies", []))
    for extra in extras:
        if extra not in definitions:
            raise ValueError(f"unknown optional dependency group: {extra}")
        requirements.extend(definitions[extra])
    if not requirements:
        raise ValueError("project declares no dependencies")
    canonical = sorted({canonical_requirement(item) for item in requirements})
    if len({requirement_name(item) for item in canonical}) != len(canonical):
        raise ValueError("dependency name is declared more than once")
    return canonical


def _payload(
    requirements: list[str], extras: tuple[str, ...], target: dict[str, str]
) -> dict:
    return {
        "format": FORMAT,
        "target": dict(sorted(target.items())),
        "extras": sorted(extras),
        "requirements": sorted(requirements),
    }


def fingerprint(
    requirements: list[str], extras: tuple[str, ...], target: dict[str, str] = TARGET
) -> str:
    encoded = json.dumps(
        _payload(requirements, extras, target), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _compatible_wheel(filename: str) -> None:
    if not filename.endswith(WHEEL_SUFFIX):
        raise ValueError(f"not a wheel: {filename}")
    parts = filename[: -len(WHEEL_SUFFIX)].split("-")
    if len(parts) < 5:
        raise ValueError(f"invalid wheel filename: {filename}")
    python_tag, abi_tag, platform_tag = parts[-3:]
    minor = int(TARGET["python_tag"][3:])
    python_ok = False
    for py in python_tag.split("."):
        for abi in abi_tag.split("."):
            if py == "py3" and abi == "none":
                python_ok = True
            elif py == f"cp3{minor}" and abi in ("none", f"cp3{minor}", "abi3"):
                python_ok = True
            elif re.fullmatch(r"cp3\d+", py) and abi == "abi3" and int(py[3:]) <= minor:
                python_ok = True
    platform_ok = platform_tag == "any" or any(
        (tag.startswith("manylinux") or tag.startswith("linux_"))
        and tag.endswith("_x86_64")
        for tag in platform_tag.split(".")
    )
    if not python_ok or not platform_ok:
        raise ValueError(
            f"wheel does not target {TARGET['python_tag']} Linux x86_64: {filename}"
        )


def inspect_wheel(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"wheel must be a regular file: {path}")
    _compatible_wheel(path.name)
    try:
        with zipfile.ZipFile(path) as archive:
            metadata = [
                name
                for name in archive.namelist()
                if name.endswith(".dist-info/METADATA") and name.count("/") == 1
            ]
            if len(metadata) != 1:
                raise ValueError(f"wheel must contain one METADATA: {path.name}")
            message = BytesParser(policy=default).parsebytes(archive.read(metadata[0]))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"invalid wheel archive: {path.name}") from exc
    name = normalize(str(message.get("Name", "")))
    version = str(message.get("Version", ""))
    filename_parts = path.name[: -len(WHEEL_SUFFIX)].split("-")
    if not name or not version:
        raise ValueError(f"wheel metadata is incomplete: {path.name}")
    if normalize(filename_parts[0]) != name or filename_parts[1] != version:
        raise ValueError(f"wheel filename and metadata disagree: {path.name}")
    if name in {"fdisbull", "fdisbull-player"}:
        raise ValueError(
            f"dependency bundle must not contain application wheel: {path.name}"
        )
    return {
        "name": name,
        "version": version,
        "filename": path.name,
        "sha256": digest(path),
        "size": path.stat().st_size,
    }


def collect_wheels(wheels: list[Path]) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for wheel in sorted(wheels):
        entry = inspect_wheel(wheel)
        if entry["name"] in found:
            raise ValueError(f"duplicate wheel for {entry['name']}")
        found[entry["name"]] = entry
    if not found:
        raise ValueError("no compatible wheels were found")
    return dict(sorted(found.items()))


def download_wheels(
    requirements: list[str], destination: Path, python: str
) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    requirement_file = destination / "constraints.txt"
    requirement_file.write_text("\n".join(requirements) + "\n")
    command = [
        python,
        "-m",
        "pip",
        "download",
        "--only-binary=:all:",
        "--dest",
        str(destination),
        "--requirement",
        str(requirement_file),
    ]
    subprocess.run(command, check=True)
    requirement_file.unlink()
    return sorted(destination.glob(f"*{WHEEL_SUFFIX}"))


def _install_script() -> str:
    return """#!/bin/sh
set -eu
unset PYTHONPATH PYTHONHOME
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ "$#" -ne 1 ]; then echo "Usage: $0 NEW_VENV_PATH" >&2; exit 2; fi
DEST=$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$1")
if [ -e "$DEST" ] || [ -L "$DEST" ]; then echo "Destination already exists" >&2; exit 1; fi
cd "$HERE"
sha256sum -c SHA256SUMS
python3 -c 'import platform,sys; assert sys.version_info[:2] == (3,13), "Python 3.13 required"; assert sys.platform == "linux" and platform.machine() == "x86_64", "Linux x86_64 required"'
python3 -m venv "$DEST"
"$DEST/bin/python" -m pip install --no-index --find-links "$HERE/wheels" --require-hashes -r "$HERE/requirements.txt"
"$DEST/bin/python" -c 'import capstone, iced_x86, lief, PIL, z3; x=z3.Int("x"); s=z3.Solver(); s.add(x+1 != 1+x); assert s.check()==z3.unsat; s=z3.Solver(); s.add(x+1 != x); assert s.check()==z3.sat; print("Offline dependencies installed; decoder and Z3 checks passed")'
"""


def _readme(
    requirements: list[str], extras: tuple[str, ...], target: dict[str, str]
) -> str:
    return (
        "fDisBull third-party offline dependency bundle\n"
        "================================================\n\n"
        f"Target: Python {target['python']} ({target['python_tag']}), {target['platform']}\n"
        f"Optional groups: {', '.join(extras) if extras else 'none'}\n\n"
        "This bundle contains third-party wheels only. It does not contain the\n"
        "fdisbull or fdisbull-player wheels. Run ./install.sh /absolute/new-venv\n"
        "on a compatible Linux x86_64 machine, then install the application wheels\n"
        "with pip --no-index --find-links <directory containing app wheels>.\n\n"
        "Declared constraints:\n"
        + "".join(f"  {item}\n" for item in requirements)
        + "\nThe manifest records the exact resolved wheel hashes and the dependency\n"
        "fingerprint. Reuse is allowed only while that fingerprint and all hashes\n"
        "still match.\n"
    )


def _write_archive(root: Path, archive: Path) -> None:
    import gzip

    archive.parent.mkdir(parents=True, exist_ok=True)
    with (
        archive.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gzip_stream,
        tarfile.open(fileobj=gzip_stream, mode="w", format=tarfile.PAX_FORMAT) as tar,
    ):
        for path in [root, *sorted(root.rglob("*"))]:
            info = tar.gettarinfo(str(path), arcname=str(path.relative_to(root.parent)))
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            if path.is_file():
                with path.open("rb") as stream:
                    tar.addfile(info, stream)
            else:
                tar.addfile(info)


def write_bundle(
    requirements: list[str],
    extras: tuple[str, ...],
    wheels: dict[str, dict],
    wheel_sources: dict[str, Path],
    output: Path,
    *,
    target: dict[str, str] = TARGET,
    root_name: str | None = None,
) -> dict:
    spec_fingerprint = fingerprint(requirements, extras, target)
    root_name = (
        root_name
        or f"fdisbull-{target['python_tag']}-{target['platform']}-dependencies-{spec_fingerprint[:12]}"
    )
    with tempfile.TemporaryDirectory(prefix="fdisbull-dependencies-") as temporary:
        root = Path(temporary) / root_name
        (root / "wheels").mkdir(parents=True)
        for name, entry in wheels.items():
            source = wheel_sources[name]
            shutil.copyfile(source, root / "wheels" / entry["filename"])
        manifest = {
            "format": FORMAT,
            "fingerprint": spec_fingerprint,
            "target": dict(sorted(target.items())),
            "extras": sorted(extras),
            "requirements": sorted(requirements),
            "wheels": wheels,
            "entrypoint": "install.sh",
            "requirements_file": "requirements.txt",
        }
        (root / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        (root / "requirements.txt").write_text(
            "".join(
                f"{entry['name']}=={entry['version']} --hash=sha256:{entry['sha256']}\n"
                for entry in wheels.values()
            )
        )
        (root / "README.txt").write_text(_readme(requirements, extras, target))
        installer = root / "install.sh"
        installer.write_text(_install_script())
        installer.chmod(0o755)
        files = sorted(path for path in root.rglob("*") if path.is_file())
        (root / "SHA256SUMS").write_text(
            "".join(
                f"{digest(path)}  {path.relative_to(root).as_posix()}\n"
                for path in files
            )
        )
        _write_archive(root, output)
    archive_hash = digest(output)
    checksum = output.with_name(output.name + ".sha256")
    checksum.write_text(f"{archive_hash}  {output.name}\n")
    return {
        "status": "built",
        "archive": str(output),
        "sha256": archive_hash,
        "checksum": str(checksum),
        "fingerprint": spec_fingerprint,
        "wheels": wheels,
    }


def _member_name(name: str) -> str:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"invalid archive path: {name}")
    return path.as_posix()


def _read_sums(data: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in data.decode().splitlines():
        if not line.strip():
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            raise ValueError("invalid SHA256SUMS line")
        value, path = parts
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("invalid SHA256SUMS hash")
        path = path.lstrip("*")
        if path in result:
            raise ValueError(f"duplicate SHA256SUMS entry: {path}")
        result[path] = value
    return result


def _manifest_from_dir(path: Path) -> tuple[dict, dict[str, Path], dict[str, str]]:
    manifest = json.loads((path / "manifest.json").read_text())
    wheels = {
        entry["filename"]: path / "wheels" / entry["filename"]
        for entry in manifest.get("wheels", {}).values()
    }
    sums = _read_sums((path / "SHA256SUMS").read_bytes())
    return manifest, wheels, sums


def _manifest_from_archive(
    path: Path, destination: Path
) -> tuple[dict, dict[str, Path], dict[str, str]]:
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        if any(item.issym() or item.islnk() for item in members):
            raise ValueError("dependency archive contains links")
        names = [_member_name(item.name) for item in members if item.isfile()]
        if len(names) != len(set(names)):
            raise ValueError("dependency archive contains duplicate files")
        roots = {
            PurePosixPath(name).parent.as_posix()
            for name in names
            if PurePosixPath(name).name == "manifest.json"
        }
        if len(roots) != 1:
            raise ValueError(
                "dependency archive must contain exactly one manifest.json"
            )
        root = next(iter(roots))
        if any(
            not (name == f"{root}/manifest.json" or name.startswith(root + "/"))
            for name in names
        ):
            raise ValueError("dependency archive contains files outside its root")
        archive.extractall(destination, filter="data")
    return _manifest_from_dir(destination / PurePosixPath(root).name)


def _verify_bundle(
    manifest: dict, wheel_files: dict[str, Path], sums: dict[str, str], path: Path
) -> None:
    if manifest.get("format") != FORMAT:
        raise ValueError("unsupported dependency bundle format")
    if manifest.get("target") != dict(sorted(TARGET.items())):
        raise ValueError("dependency bundle target does not match this builder")
    requirements = manifest.get("requirements")
    extras = manifest.get("extras")
    if not isinstance(requirements, list) or not isinstance(extras, list):
        raise ValueError("dependency manifest is incomplete")
    canonical = [canonical_requirement(item) for item in requirements]
    if canonical != requirements:
        raise ValueError("dependency manifest has non-canonical requirements")
    if manifest.get("fingerprint") != fingerprint(
        requirements, tuple(extras), manifest["target"]
    ):
        raise ValueError("dependency fingerprint does not match manifest contents")
    wheels = manifest.get("wheels")
    if not isinstance(wheels, dict) or not wheels:
        raise ValueError("dependency manifest has no wheels")
    expected = {entry["filename"] for entry in wheels.values()}
    if set(wheel_files) != expected:
        raise ValueError("dependency archive wheel members do not match manifest")
    for entry in wheels.values():
        filename = entry["filename"]
        wheel_path = wheel_files[filename]
        if not wheel_path.is_file():
            raise ValueError(f"dependency wheel is missing: {filename}")
        if digest(wheel_path) != entry["sha256"]:
            raise ValueError(f"dependency wheel hash mismatch: {filename}")
        if wheel_path.stat().st_size != entry["size"]:
            raise ValueError(f"dependency wheel size mismatch: {filename}")
        inspect_wheel(wheel_path)
    files = {
        item.relative_to(path).as_posix() for item in path.rglob("*") if item.is_file()
    }
    files.discard("SHA256SUMS")
    if set(sums) != files:
        raise ValueError(
            "dependency bundle SHA256SUMS does not cover exactly its files"
        )
    for member, value in sums.items():
        candidate = path / member
        if not candidate.is_file() or digest(candidate) != value:
            raise ValueError(f"dependency bundle hash mismatch: {member}")


def load_bundle(path: Path) -> dict:
    path = path.resolve()
    if path.is_dir():
        manifest, wheels, sums = _manifest_from_dir(path)
        _verify_bundle(manifest, wheels, sums, path)
        return {"manifest": manifest, "path": path, "kind": "directory"}
    if path.is_file() and path.name.endswith(SHA_SUFFIXES):
        with tempfile.TemporaryDirectory(
            prefix="fdisbull-dependency-check-"
        ) as temporary:
            extracted = Path(temporary)
            manifest, wheels, sums = _manifest_from_archive(path, extracted)
            root = next(extracted.glob("*/manifest.json")).parent
            _verify_bundle(manifest, wheels, sums, root)
        return {"manifest": manifest, "path": path, "kind": "archive"}
    raise ValueError(f"dependency bundle must be a directory or .tar.gz: {path}")


def extract_bundle(path: Path, destination: Path) -> Path:
    """Verify a bundle and extract it, returning the directory containing the wheels."""
    path = path.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if path.is_dir():
        manifest, wheels, sums = _manifest_from_dir(path)
        _verify_bundle(manifest, wheels, sums, path)
        return path
    if path.is_file() and path.name.endswith(SHA_SUFFIXES):
        manifest, wheels, sums = _manifest_from_archive(path, destination)
        root = next(destination.glob("*/manifest.json")).parent
        _verify_bundle(manifest, wheels, sums, root)
        return root
    raise ValueError(f"dependency bundle must be a directory or .tar.gz: {path}")


def compare_specs(
    previous: dict,
    requirements: list[str],
    extras: tuple[str, ...],
    target: dict[str, str] = TARGET,
) -> dict:
    previous_manifest = previous["manifest"]
    previous_requirements = previous_manifest.get("requirements", [])
    before = {requirement_name(item): item for item in previous_requirements}
    after = {requirement_name(item): item for item in requirements}
    added = sorted(name for name in after if name not in before)
    removed = sorted(name for name in before if name not in after)
    changed = sorted(
        name for name in after.keys() & before.keys() if after[name] != before[name]
    )
    target_changed = previous_manifest.get("target") != dict(sorted(target.items()))
    extras_changed = sorted(previous_manifest.get("extras", [])) != sorted(extras)
    return {
        "changed": bool(
            added or removed or changed or target_changed or extras_changed
        ),
        "added": added,
        "removed": removed,
        "version_changed": changed,
        "target_changed": target_changed,
        "extras_changed": extras_changed,
    }


def _resolve_output(output: Path, project_root: Path) -> Path:
    if output.name.endswith(".tar.gz") or output.suffix == ".tgz":
        return output
    version = tomllib.loads((project_root / "pyproject.toml").read_text())["project"][
        "version"
    ]
    return output / f"fdisbull-{version}-linux-x86_64-dependencies.tar.gz"


def _host_ok(python: str) -> None:
    if sys.version_info[:2] != (3, 13):
        raise ValueError("offline dependency builds require Python 3.13")
    if sys.platform != "linux" or platform.machine() != "x86_64":
        raise ValueError("offline dependency builds must run on Linux x86_64")
    probe = subprocess.run(
        [
            python,
            "-c",
            "import platform,sys; print(sys.version_info[:2]); print(platform.machine()); print(sys.platform)",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    if probe != ["(3, 13)", "x86_64", "linux"]:
        raise ValueError("selected Python is not Linux x86_64 Python 3.13")


def build(args: argparse.Namespace) -> dict:
    project_root = args.project_root.resolve()
    extras = () if args.no_extras else tuple(args.extra or DEFAULT_EXTRAS)
    requirements = load_requirements(project_root, extras)
    target = dict(TARGET)
    output = _resolve_output(args.output, project_root)
    if args.previous:
        previous = load_bundle(args.previous)
        difference = compare_specs(previous, requirements, extras, target)
        if not difference["changed"]:
            if args.require_reuse and previous["kind"] != "archive":
                raise ValueError("previous bundle must be an archive to reuse it")
            output.parent.mkdir(parents=True, exist_ok=True)
            if previous["kind"] == "archive":
                if previous["path"].resolve() != output.resolve():
                    shutil.copyfile(previous["path"], output)
            else:
                raise ValueError(
                    "reuse requires an archive, not an extracted directory"
                )
            archive_hash = digest(output)
            (output.with_name(output.name + ".sha256")).write_text(
                f"{archive_hash}  {output.name}\n"
            )
            return {
                "status": "reused",
                "archive": str(output),
                "sha256": archive_hash,
                "fingerprint": previous["manifest"]["fingerprint"],
                "previous": str(previous["path"]),
                "diff": difference,
            }
        if args.require_reuse:
            raise ValueError(
                f"dependency specification changed and reuse was required: {difference}"
            )
    else:
        if args.require_reuse:
            raise ValueError("reuse was required but no previous bundle was supplied")
        difference = {"changed": True, "reason": "no previous bundle supplied"}
    if args.wheelhouse:
        wheel_paths = sorted(args.wheelhouse.resolve().glob(f"*{WHEEL_SUFFIX}"))
        if not wheel_paths:
            raise ValueError(f"wheelhouse has no wheels: {args.wheelhouse}")
        wheels = collect_wheels(wheel_paths)
        sources = {
            entry["name"]: path
            for entry in wheels.values()
            for path in [Path(args.wheelhouse.resolve()) / entry["filename"]]
        }
        result = write_bundle(
            requirements, extras, wheels, sources, output, target=target
        )
    else:
        _host_ok(args.python)
        with tempfile.TemporaryDirectory(prefix="fdisbull-wheels-") as temporary:
            wheel_paths = download_wheels(requirements, Path(temporary), args.python)
            wheels = collect_wheels(wheel_paths)
            sources = {
                entry["name"]: path
                for entry in wheels.values()
                for path in [Path(temporary) / entry["filename"]]
            }
            result = write_bundle(
                requirements, extras, wheels, sources, output, target=target
            )
    result["diff"] = difference
    result["requirements"] = requirements
    return result


def check(args: argparse.Namespace) -> dict:
    project_root = args.project_root.resolve()
    extras = () if args.no_extras else tuple(args.extra or DEFAULT_EXTRAS)
    requirements = load_requirements(project_root, extras)
    previous = load_bundle(args.previous)
    difference = compare_specs(previous, requirements, extras)
    return {
        "status": "reuse" if not difference["changed"] else "rebuild",
        "fingerprint": fingerprint(requirements, extras),
        "previous_fingerprint": previous["manifest"]["fingerprint"],
        "previous": str(previous["path"]),
        "diff": difference,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser(
        "build", help="build a dependency bundle or reuse a previous one"
    )
    build_parser.add_argument("--project-root", type=Path, default=ROOT)
    build_parser.add_argument(
        "--output", type=Path, required=True, help="archive path or output directory"
    )
    build_parser.add_argument(
        "--previous",
        type=Path,
        help="previous dependency archive or extracted directory",
    )
    build_parser.add_argument(
        "--wheelhouse", type=Path, help="use existing wheels instead of downloading"
    )
    build_parser.add_argument(
        "--extra",
        action="append",
        default=[],
        help=f"optional group (default: {', '.join(DEFAULT_EXTRAS)})",
    )
    build_parser.add_argument("--no-extras", action="store_true")
    build_parser.add_argument("--python", default=sys.executable)
    build_parser.add_argument(
        "--require-reuse",
        action="store_true",
        help="fail instead of rebuilding when the diff changed",
    )
    build_parser.set_defaults(handler=build)
    check_parser = subparsers.add_parser(
        "check", help="compare constraints with a previous bundle without downloading"
    )
    check_parser.add_argument("--project-root", type=Path, default=ROOT)
    check_parser.add_argument("--previous", type=Path, required=True)
    check_parser.add_argument("--extra", action="append", default=[])
    check_parser.add_argument("--no-extras", action="store_true")
    check_parser.add_argument(
        "--require-reuse",
        action="store_true",
        help="exit non-zero unless the previous bundle is reusable",
    )
    check_parser.set_defaults(handler=check)
    args = parser.parse_args()
    try:
        result = args.handler(args)
    except (
        ValueError,
        OSError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
    ) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))
    if (
        args.command == "check"
        and getattr(args, "require_reuse", False)
        and result["status"] != "reuse"
    ):
        raise SystemExit(3)


if __name__ == "__main__":
    main()
