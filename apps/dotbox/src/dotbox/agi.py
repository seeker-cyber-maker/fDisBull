"""Bounded offline AGI source inspection; no game execution or live state reads."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import sys

from .agi_layout import logic_layout
from .agi_resources import DEFAULT_MAX_MESSAGE_BYTES, logic_messages
from .agi_scenes import DEFAULT_MAX_REPORT_BYTES, _decode, inspect_scenes, serialize_report


_LIMITATIONS = [
    "Partial uncompressed DOS AGI 2.917 profile; no AGI3, GAL/booters or SCI",
    "High-bit IF displacements and context-dependent trace.on remain opaque",
    "Static conditions, write sites and room targets do not establish current scene facts",
    "No live flags, save-file decoder, current inventory or qualified executable interactions",
    "Local value analysis does not recover named state meanings or qualify native behavior",
]


def self_check():
    """Check authored LOGIC bytes in memory, without file, game or native I/O."""
    def payload(code):
        return len(code).to_bytes(2, "little") + code + b"\0\x02\0"

    def refused(code):
        try:
            logic_layout(payload(code))
        except ValueError:
            return True
        return False

    try:
        # set f42; if f42: reset f42; return. Source facts, not a live flag.
        source = payload(bytes.fromhex("0c2a ff072aff0200 0d2a 00"))
        layout, instructions, _ = _decode(source, 16, 64)
        _, loop, _ = _decode(payload(bytes.fromhex("011e fefbff")), 16, 64)
        checks = {
            "flag_write_and_condition_layout": layout["instructions"] == [2, 4, 10, 12]
            and [row["operation"] for row in instructions] == ["set", "if", "reset", "return"],
            "ordinary_if_successors": instructions[1]["successors"] == [
                {"kind": "true", "offset": 10}, {"kind": "false", "offset": 12}],
            "signed_backward_goto": loop[1]["successors"] == [{"kind": "branch", "offset": 2}],
            "high_bit_if_refused": refused(bytes.fromhex("ff0700fffaff00")),
            "non_boundary_branch_refused": refused(bytes.fromhex("feffff00")),
            "empty_message_table": logic_messages(source) == [],
        }
        return {"ok": all(checks.values()), "profile": "2.917", "checks": checks,
                "qualified_interactions": 0,
                "scope": "Authored offline LOGIC fixtures only; no native runtime or game qualification"}
    except (ValueError, KeyError, IndexError, TypeError) as error:
        return {"ok": False, "profile": "2.917", "error": str(error),
                "qualified_interactions": 0, "scope": "Offline AGI source check failed"}


def _check_private_parent(info):
    if (not hasattr(os, "getuid") or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise ValueError("AGI report requires an existing private owned directory (0700)")


def _destination(filename, game_directory):
    """Refuse existing, shared, symlinked, input-tree or Git destinations."""
    target = Path(filename).expanduser().absolute()
    if any(part.is_symlink() for part in (target, *target.parents)):
        raise ValueError("AGI report destination must not contain symlinks")
    target = target.resolve(strict=False)
    root = Path(game_directory).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Expected an AGI resource directory")
    if target.is_relative_to(root):
        raise ValueError("AGI report must be outside the read-only resource directory")
    for parent in target.parents:
        marker = parent / ".git"
        bare = ((parent / "HEAD").is_file() and (parent / "objects").is_dir()
                and (parent / "refs").is_dir())
        if marker.exists() or marker.is_symlink() or bare:
            raise ValueError("Private AGI reports must remain outside Git repositories")
    _check_private_parent(target.parent.lstat())
    if target.exists():
        raise ValueError("AGI report output must be a new file")
    return target


def _write_report(target, data):
    # A directory descriptor keeps the create/cleanup on this checked parent.
    directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        _check_private_parent(os.fstat(directory))
        descriptor = os.open(target.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(data)
        except BaseException:
            os.unlink(target.name, dir_fd=directory)
            raise
    finally:
        os.close(directory)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def main(argv=None):
    """Inspect frozen AGI resources and write a new private census report."""
    parser = _Parser(prog="dotbox agi", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
    inspect = commands.add_parser("inspect", help="Inventory bounded AGI resources without running a game")
    inspect.add_argument("directory")
    inspect.add_argument("--profile", required=True, choices=("2.917",),
                         help="Caller-selected resource profile; not automatic edition detection")
    inspect.add_argument("--stage", choices=("outline", "resolve"), default="resolve")
    inspect.add_argument("--output", required=True,
                         help="New private report file under an existing owned 0700 directory outside Git")
    inspect.add_argument("--include-ir", action="store_true", help="Include full low-level instruction rows in the private report")
    inspect.add_argument("--include-text", action="store_true", help="Include literal target text in the private report")
    inspect.add_argument("--max-updates", type=int, default=200000,
                         help="Global value-analysis updates: 1..2000000 (default: 200000)")
    inspect.add_argument("--max-instructions", type=int, default=100000,
                         help="Global attempted instruction records: 1..1000000 (default: 100000)")
    inspect.add_argument("--max-code-bytes", type=int, default=1048576,
                         help="Global admitted code spans: 1..4194304 bytes (default: 1048576)")
    inspect.add_argument("--max-message-bytes", type=int, default=DEFAULT_MAX_MESSAGE_BYTES,
                         help="Shared expanded text/work: 1..4194304 bytes (default: 262144)")
    inspect.add_argument("--max-report-bytes", type=int, default=DEFAULT_MAX_REPORT_BYTES,
                         help="Complete JSON report including newline: 16384..16777216 bytes (default: 8388608)")
    try:
        options = vars(parser.parse_args(argv))
        options.pop("command")
        game_directory = Path(options.pop("directory")).expanduser()
        output = options.pop("output")
        _destination(output, game_directory)  # Fail before reading target resources.
        report = inspect_scenes(game_directory, **options)
        data = serialize_report(report, options["max_report_bytes"])
        destination = _destination(output, game_directory)
        _write_report(destination, data)
        summary = {
            "ok": True, "format": "dotbox-agi-inspection-summary-1",
            "profile": report["profile"], "stage": report["stage"],
            "qualification": report["qualification"], "qualified_interactions": 0,
            "executable": False, "coverage": report["coverage"],
            "limits": report["budgets"], "limitations": list(_LIMITATIONS),
            "report": {"path": str(destination), "sha256": sha256(data).hexdigest(),
                       "format": report["format"], "private": True, "bytes": len(data)},
        }
        print(json.dumps(summary, allow_nan=False))
        return 0
    except (ValueError, OSError, TypeError, RecursionError) as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
