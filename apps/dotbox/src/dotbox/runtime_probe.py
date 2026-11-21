"""Noninvasive, stdlib-only runtime inventory; also runnable as one attached file.

This module never launches DOSBox, imports an optional runtime package, loads a
model, or guesses desktop ownership. A successful probe is inventory evidence,
not proof that this process is running on Dot's computer or that a game works.
"""

from __future__ import annotations

import argparse
import ctypes.util
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import stat
import sys
import sysconfig
import uuid


FORMAT = "dotbox-runtime-probe-1"
CONTEXTS = ("unspecified", "local", "dot-cloud")
DISTRIBUTIONS = (
    "fdisbull", "fdisbull-player", "Pillow", "capstone", "iced-x86", "lief",
    "zstandard", "PySDL2",
)
DISPLAY_VARIABLES = ("DISPLAY", "WAYLAND_DISPLAY", "SDL_VIDEODRIVER")
AUDIO_VARIABLES = (
    "PULSE_SERVER", "PIPEWIRE_REMOTE", "ALSA_CONFIG_PATH", "SDL_AUDIODRIVER",
)


def _presence(names):
    # Values can contain host names, paths or credentials. Presence is enough
    # for this inventory and does not establish that a display/server works.
    return {name: bool(os.environ.get(name)) for name in names}


def _distributions():
    found = {}
    for name in DISTRIBUTIONS:
        try:
            found[name] = {"status": "installed", "version": metadata.version(name)}
        except metadata.PackageNotFoundError:
            found[name] = {"status": "not_found"}
        except (OSError, ValueError) as error:
            found[name] = {"status": "unavailable", "error": type(error).__name__}
    return found


def _libraries():
    found = {}
    for name in ("SDL2", "pulse", "pipewire-0.3", "asound", "CoreAudio"):
        try:
            match = ctypes.util.find_library(name)
            found[name] = {"lookup_match_found": bool(match)}
        except (OSError, ValueError) as error:
            found[name] = {"lookup_match_found": None, "error": type(error).__name__}
    return found


def _backend(path):
    if path is None:
        return {"status": "not_supplied", "capabilities": "not_queried"}
    source = Path(path).expanduser()
    try:
        if not source.is_file():
            return {"status": "unavailable", "error": "not_regular_file"}
        # The regular-file check avoids opening devices; nonblocking open also
        # prevents a swapped FIFO from hanging before fstat can reject it.
        descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                return {"status": "unavailable", "error": "not_regular_file"}
            digest = hashlib.sha256()
            size = 0
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
                size += len(block)
            after = os.fstat(stream.fileno())
        identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            return {"status": "unavailable", "error": "changed_during_read"}
        return {
            "status": "inventoried", "filename": source.name,
            "bytes": size, "sha256": digest.hexdigest(),
            "executable_bit_set": bool(info.st_mode & 0o111),
            "capabilities": "not_queried", "launched": False,
        }
    except OSError as error:
        # Avoid propagating a private full path from exception text.
        return {"status": "unavailable", "error": type(error).__name__}


def collect_runtime(*, backend=None, context="unspecified", label=None):
    """Return observed inventory without asserting target identity or readiness.

    ``context`` is an operator-supplied label. It cannot verify that this process
    is attached to a particular computer. Optional ``backend`` is read and hashed
    only; native capabilities require a later explicit launch/check.
    """
    if context not in CONTEXTS:
        raise ValueError("context must be unspecified, local or dot-cloud")
    if label is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", label):
        raise ValueError("label must contain 1-64 letters, digits, dots, dashes or underscores")
    return {
        "format": FORMAT,
        "probe_id": uuid.uuid4().hex,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "label": label,
        "context": {"requested": context, "identity_verified": False,
                    "evidence": "current_process_only"},
        "runtime": {
            "system": platform.system(), "release": platform.release(),
            "architecture": platform.machine(),
            "python": {
                "implementation": platform.python_implementation(),
                "version": platform.python_version(),
                "executable_name": Path(sys.executable).name,
                "abi": sysconfig.get_config_var("SOABI"),
                "cache_tag": sys.implementation.cache_tag,
            },
        },
        "distributions": _distributions(),
        "display": {"environment_presence": _presence(DISPLAY_VARIABLES),
                    "visible_window_verified": False},
        "audio": {"environment_presence": _presence(AUDIO_VARIABLES),
                  "device_directory_present": Path("/dev/snd").is_dir(),
                  "audible_output_verified": False},
        "library_lookup": _libraries(),
        "backend": _backend(backend),
        "takeover": {"owner": "unknown", "source": "unavailable",
                     "supported_provider_observed": False,
                     "note": "No ownership inferred from UI labels, focus, sandbox metadata or input silence."},
        "qualification": {
            "status": "inventory_only", "dot_computer_verified": False,
            "native_game_launch_verified": False,
            "built_in_takeover_integration_verified": False,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backend", help="Optional explicit backend file to hash; never executed")
    parser.add_argument("--context", choices=CONTEXTS, default="unspecified",
                        help="Operator-supplied label, not a verified computer identity")
    parser.add_argument("--label", help="Short receipt label, for example before-takeover")
    parser.add_argument("--output", type=Path, help="Create a private JSON receipt; refuses overwrite")
    args = parser.parse_args(argv)
    try:
        report = collect_runtime(backend=args.backend, context=args.context, label=args.label)
    except ValueError as error:
        parser.error(str(error))
    encoded = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output is None:
        sys.stdout.write(encoded)
    else:
        try:
            fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                output.write(encoded)
        except OSError as error:
            parser.exit(2, f"Cannot create receipt ({type(error).__name__}); existing files are preserved.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
