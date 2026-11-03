"""Read-only capability inventory for the proposed Windows original-program runtime.

This tool NEVER runs Wine on an input EXE, initializes a WINEPREFIX, starts a VM,
compiles a binary or invokes a Windows installer. It is a preliminary host/guest
inventory, not a successful native-debugging or original-game qualification.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

MIN_WINE = (11, 0)
MIN_QEMU = (9, 1)


def _version(text: str, kind: str) -> tuple[int, int, int] | None:
    pattern = {
        "wine": r"(?i)\bwine[- ](?:version\s*)?(\d+)\.(\d+)(?:\.(\d+))?\b",
        "qemu": r"(?i)\bqemu\s+emulator\s+version\s+(\d+)\.(\d+)(?:\.(\d+))?\b",
    }[kind]
    match = re.search(pattern, text)
    return tuple(int(item or 0) for item in match.groups()) if match else None


def _tool(command: str | None, *, kind: str | None = None) -> dict:
    """Find an exact tool and, only for Wine/QEMU, inspect its harmless version flag."""
    if command is None:
        return {"found": False, "version": None, "qualified_version": False if kind else None}
    found = shutil.which(command)
    if not found:
        return {"found": False, "version": None, "qualified_version": False if kind else None}
    result = {"found": True, "version": None, "qualified_version": None}
    if kind:
        try:
            run = subprocess.run(
                [found, "--version"], capture_output=True, text=True,
                timeout=5, check=False,
            )
            parsed = _version(run.stdout + "\n" + run.stderr, kind) if run.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            parsed = None
        minimum = MIN_WINE if kind == "wine" else MIN_QEMU
        result["version"] = ".".join(map(str, parsed)) if parsed else None
        result["qualified_version"] = bool(parsed and parsed[:2] >= minimum)
    return result


def inspect(mode: str, *, wine: str = "wine", qemu: str = "qemu-system-x86_64",
            xvfb: str = "Xvfb", kernel: str | None = None,
            initramfs: str | None = None, env: dict | None = None,
            target: str = "all") -> dict:
    """Inventory independently required tools, without running target processes."""
    if mode not in {"wine-guest", "qemu-host", "compilers", "macos-native"}:
        raise ValueError("mode must be wine-guest, qemu-host, compilers, or macos-native")
    if target not in {"all", "pe32", "pe64", "win16"} or mode != "compilers" and target != "all":
        raise ValueError("target is all, pe32, pe64 or win16 and applies only to compilers")
    env = os.environ if env is None else env
    out = {
        "schema": "fdisbull-windows-runtime-preflight-1",
        "mode": mode,
        "qualification": "preflight-only; no original/native program executed",
        "host": {"system": platform.system(), "architecture": platform.machine()},
        "tools": {},
        "checks": {},
        "ready_to_attempt": False,
        "not_verified": [
            "original Windows program execution", "debugger process/thread contexts",
            "Win16 runtime selectors", "PE32 WoW64 breakpoints and memory",
            "machine-state rewind", "original DOS/Win16/Win32 equivalence",
            "macOS native LLDB entitlement and original target observation",
        ],
    }
    if mode == "wine-guest":
        out["tools"]["wine"] = _tool(wine, kind="wine")
        out["tools"]["xvfb"] = _tool(xvfb)
        winearch = env.get("WINEARCH", "")
        out["checks"]["winearch"] = (
            "64bit-default-or-unspecified" if not winearch else winearch
        )
        out["checks"]["wow64_compatible_requested"] = winearch in ("", "wow64")
        out["checks"]["display_available"] = bool(out["tools"]["xvfb"]["found"] or env.get("DISPLAY"))
        out["checks"]["prefix_architecture_verified"] = False
        out["ready_to_attempt"] = all((
            out["tools"]["wine"]["qualified_version"],
            out["checks"]["wow64_compatible_requested"],
            out["checks"]["display_available"],
        ))
    elif mode == "qemu-host":
        out["tools"]["qemu"] = _tool(qemu, kind="qemu")
        # Do not echo user-specific file paths, original bytes or environment secrets.
        out["checks"]["kernel_file_present"] = bool(kernel and Path(kernel).is_file())
        out["checks"]["initramfs_file_present"] = bool(initramfs and Path(initramfs).is_file())
        out["ready_to_attempt"] = all((
            out["tools"]["qemu"]["qualified_version"],
            out["checks"]["kernel_file_present"],
            out["checks"]["initramfs_file_present"],
        ))
    elif mode == "macos-native":
        # Native Mach-O investigation and local compiler readiness are independent
        # of whether a Wine/QEMU PE32 guest or MinGW toolchain is installed.
        out["tools"].update({
            "clang": _tool("clang"),
            "lldb": _tool("lldb"),
            "xcrun": _tool("xcrun"),
        })
        out["checks"]["supported_macos_host"] = (
            platform.system() == "Darwin" and
            platform.machine().lower() in {"arm64", "aarch64", "x86_64"}
        )
        out["checks"]["debug_permission_verified"] = False
        out["ready_to_attempt"] = bool(
            out["checks"]["supported_macos_host"] and
            all(t["found"] for t in out["tools"].values())
        )
    else:
        out["tools"].update({
            "win16_c": _tool("wcc"),
            "win16_link": _tool("wlink"),
            "win32_c": _tool("i686-w64-mingw32-gcc"),
            "win64_c": _tool("x86_64-w64-mingw32-gcc"),
        })
        out["checks"]["target_toolchains_present"] = {
            "win16_ne": out["tools"]["win16_c"]["found"] and out["tools"]["win16_link"]["found"],
            "win32_pe32": out["tools"]["win32_c"]["found"],
            "win64_pe32_plus": out["tools"]["win64_c"]["found"],
        }
        # Choosing PE32 must not require Open Watcom/Win16 or a PE64 compiler.
        key = {"pe32": "win32_pe32", "pe64": "win64_pe32_plus", "win16": "win16_ne"}.get(target)
        out["checks"]["selected_target"] = target
        out["ready_to_attempt"] = (
            all(out["checks"]["target_toolchains_present"].values())
            if key is None else bool(out["checks"]["target_toolchains_present"][key])
        )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("wine-guest", "qemu-host", "compilers", "macos-native"))
    parser.add_argument("--target", default="all", choices=("all", "pe32", "pe64", "win16"),
                        help="Select an independent compiler gate; default all preserves older behavior")
    parser.add_argument("--wine", default="wine", help="Wine binary; only --version is invoked")
    parser.add_argument("--qemu", default="qemu-system-x86_64", help="QEMU binary; only --version is invoked")
    parser.add_argument("--xvfb", default="Xvfb", help="Xvfb binary; presence only")
    parser.add_argument("--kernel", help="Existing private QEMU kernel (not read or executed)")
    parser.add_argument("--initramfs", help="Existing private guest runtime image (not read or executed)")
    parser.add_argument("--strict", action="store_true", help="Exit 2 when prerequisites are absent")
    args = parser.parse_args(argv)
    result = inspect(args.mode, wine=args.wine, qemu=args.qemu, xvfb=args.xvfb,
                     kernel=args.kernel, initramfs=args.initramfs, target=args.target)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ready_to_attempt"] or not args.strict else 2


if __name__ == "__main__":
    sys.exit(main())
