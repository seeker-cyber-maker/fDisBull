"""Installed operational guidance and verified, exportable source resources."""

import argparse
import hashlib
from importlib import resources
import json
import os
from pathlib import Path, PurePosixPath
import re
from subprocess import SubprocessError
import sys
import tomllib

from . import __version__


MAX_RESOURCE_BYTES = 8 * 1024 * 1024


def _manifest():
    package = resources.files("dotbox")
    manifest = json.loads(package.joinpath("resources_manifest.json").read_text())
    if (not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list) or
            not all(isinstance(name, str) for name in manifest["files"]) or
            not isinstance(manifest.get("topics"), dict) or
            not all(isinstance(topic, str) and isinstance(name, str)
                    for topic, name in manifest["topics"].items())):
        raise ValueError("Invalid DotBox resource manifest structure")
    names = manifest["files"]
    if manifest["format"] != "dotbox-resource-manifest-1" or len(set(names)) != len(names):
        raise ValueError("Invalid DotBox resource manifest")
    for name in names:
        path = PurePosixPath(name)
        if (not path.parts or path.is_absolute() or ".." in path.parts or
                "\\" in name or str(path) != name):
            raise ValueError("Invalid DotBox resource path")
    if not set(manifest["topics"].values()) <= set(names):
        raise ValueError("Guide topic is missing from the resource manifest")
    return package, manifest


def _inventory():
    package, manifest = _manifest()
    root = package.joinpath("resources")
    if root.joinpath("catalog.json").is_file():
        catalog = json.loads(root.joinpath("catalog.json").read_text())
        layout = "installed"
    else:
        # Development convenience is explicitly reported, never an installed-wheel check.
        source_root = Path(__file__).resolve().parents[2]
        project = source_root / "pyproject.toml"
        if (not project.is_file() or
                tomllib.loads(project.read_text()).get("project", {}).get("name") != "dotbox" or
                source_root / "src/dotbox/kit.py" != Path(__file__).resolve()):
            raise ValueError("Installed DotBox resources are missing; reinstall the complete wheel")
        root, layout = source_root, "source"
        catalog = {"format": "dotbox-resource-catalog-1", "files": {}}
        for name in manifest["files"]:
            path = root / name
            if not path.is_file() or any(part.is_symlink() for part in (path, *path.parents)):
                raise ValueError("Missing or symlinked source resource: " + name)
            if path.stat().st_size > MAX_RESOURCE_BYTES:
                raise ValueError("Resource exceeds its byte limit: " + name)
            data = path.read_bytes()
            catalog["files"][name] = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
    if (not isinstance(catalog, dict) or not isinstance(catalog.get("files"), dict) or
            catalog.get("format") != "dotbox-resource-catalog-1" or
            set(catalog["files"]) != set(manifest["files"])):
        raise ValueError("Packaged resource catalog does not match the manifest")
    return root, manifest, catalog, layout


def _read(root, name, expected):
    if (not isinstance(expected, dict) or type(expected.get("size")) is not int or
            not 0 <= expected["size"] <= MAX_RESOURCE_BYTES or
            not isinstance(expected.get("sha256"), str) or
            not re.fullmatch(r"[0-9a-f]{64}", expected["sha256"])):
        raise ValueError("Invalid resource identity: " + name)
    with root.joinpath(name).open("rb") as source:
        data = source.read(expected["size"] + 1)
    if len(data) != expected["size"] or hashlib.sha256(data).hexdigest() != expected["sha256"]:
        raise ValueError("Resource hash mismatch: " + name)
    return data


def guide(topic="start"):
    root, manifest, catalog, _ = _inventory()
    if topic not in manifest["topics"]:
        raise ValueError("Unknown guide topic: " + str(topic))
    name = manifest["topics"][topic]
    return _read(root, name, catalog["files"][name]).decode("utf-8")


def doctor():
    report = {"format": "dotbox-kit-doctor-1", "version": __version__,
              "offline_learning_ready": False, "native_runtime_qualified": False,
              "scope": "Offline tools and resource integrity only; no native launch, input or network"}
    try:
        root, _, catalog, layout = _inventory()
        for name, expected in catalog["files"].items():
            _read(root, name, expected)
        report["resources"] = {"layout": layout, "verified": len(catalog["files"]),
                               "integrity": "content matches package catalog; not a publisher signature"}
        from .inspection import self_check
        report["inspection"] = self_check()
        from .learning import clock_identity
        clock_identity()
        report["learning"] = {"clock_identity_available": True, "store_opened": False,
                              "scope": "Journal prerequisites only; no player workspace inspected"}
        from .scenes import look_scene, project_scene, select_choice
        name = "examples/scene_mailbox.json"
        example = json.loads(_read(root, name, catalog["files"][name]))
        view = project_scene(example)
        intent = select_choice(example, "open_mailbox", view["scene_sha256"], view["observation_id"])
        checks = {"authored_choice_available": any(choice["id"] == "open_mailbox" for choice in view["choices"]),
                  "selection_has_no_execution": intent["execution"] == "not_performed"}
        windows = []
        for phase in ("closed", "open"):
            name = f"examples/scene_window_{phase}.json"
            windows.append(json.loads(_read(root, name, catalog["files"][name])))
        closed, opened = (project_scene(packet) for packet in windows)
        checks.update(
            state_change_removes_open="open_window" in closed["suggested_choice_ids"]
            and "open_window" not in {choice["id"] for choice in opened["choices"]},
            incidental_choice_remains_explicit="lick_window" in {choice["id"] for choice in opened["choices"]}
            and "lick_window" not in opened["suggested_choice_ids"],
            passive_look_has_no_execution=look_scene(windows[1])["execution"] == "not_performed",
        )
        report["scenes"] = {"ok": all(checks.values()), "checks": checks,
                            "scope": "Packaged authored fixture only; no game recognition, input or voice"}
        from .agi import self_check as agi_check
        from .navigation import self_check as navigation_check
        report["agi"] = agi_check()
        report["navigation"] = navigation_check()
        report["offline_learning_ready"] = all(
            report[name]["ok"] for name in ("inspection", "scenes", "agi", "navigation")
        )
    except (ValueError, OSError, ImportError, KeyError, TypeError, SubprocessError) as error:
        report["error"] = str(error)
    return report


def export_resources(destination):
    """Materialize a new private source kit; never build, fetch or execute it."""
    root, _, catalog, layout = _inventory()
    payloads = {name: _read(root, name, expected) for name, expected in catalog["files"].items()}
    destination = Path(destination).expanduser().absolute()
    destination.mkdir(mode=0o700)  # Existing destinations, including symlinks, are refused.
    for name, data in payloads.items():
        target = destination / name
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(data)
    descriptor = os.open(destination / "catalog.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:
        output.write(json.dumps(catalog, indent=2, sort_keys=True) + "\n")
    return {"format": "dotbox-kit-export-1", "directory": str(destination),
            "files": len(payloads), "source_layout": layout,
            "native_build_performed": False}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="dotbox")
    commands = parser.add_subparsers(dest="command", required=True)
    guide_parser = commands.add_parser("guide", help="Read one installed operating guide.")
    guide_parser.add_argument("--topic", default="start")
    commands.add_parser("doctor", help="Check the offline kit without contacting a game.")
    export_parser = commands.add_parser("kit-export", help="Export native source resources and guides.")
    export_parser.add_argument("--directory", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "guide":
            print(guide(args.topic), end="")
            return 0
        if args.command == "doctor":
            report = doctor()
            print(json.dumps(report), flush=True)
            return 0 if report["offline_learning_ready"] else 1
        print(json.dumps(export_resources(args.directory)), flush=True)
        return 0
    except (ValueError, OSError, ImportError, KeyError, TypeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
        return 1
