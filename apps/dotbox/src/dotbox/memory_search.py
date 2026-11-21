"""Scalar candidate searches over frozen, explicitly identified byte buffers.

The shared kernel owns search semantics. DotBox adds an offline file CLI and an
authored installation check. No capture, live-context attestation, emulator call
or target mutation occurs here; candidate correlation is not semantic proof.
"""
import argparse
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import stat
import sys

from fdisbull_core import memory_search as _kernel
from fdisbull_core.memory_search import (
    refine_search, search_results, snapshot_metadata, start_search,
    validate_search, validate_snapshot,
)


__all__ = ["snapshot_metadata", "validate_snapshot", "start_search", "validate_search",
           "refine_search", "search_results"]
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_INLINE_BYTES = 65536
CLAIM = ("Frozen caller-supplied bytes and context only; no live capture, freshness, "
         "allocation-lifetime or semantic verification")


def self_check():
    """Exercise the installed shared distribution on authored bytes only."""
    before, after = bytes.fromhex("010002000300"), bytes.fromhex("010009000900")
    context = {"source_sha256": hashlib.sha256(b"DotBox authored search fixture").hexdigest(),
               "run_id": "authored-run", "address_space": "authored-linear",
               "region": {"start": 4096, "length": len(before)}, "task_id": "authored-search",
               "mapping_id": "authored-mapping", "version_id": "authored-version"}
    try:
        first = snapshot_metadata(before, context=context, capture_id="before")
        second = snapshot_metadata(after, context=context, capture_id="after")
        initial = start_search(before, first, width=2, stride=2)
        narrowed = refine_search(initial, before, first, after, second, mode="delta", delta=7)
        rows = search_results(narrowed, after, second, before_data=before, before_snapshot=first)
        refused = False
        different = snapshot_metadata(after, context=dict(context, run_id="another-run"), capture_id="other")
        try:
            refine_search(initial, before, first, after, different, mode="changed")
        except ValueError:
            refused = True
        checks = {"all_initial_positions": initial["candidate_count"] == 3,
                  "exact_delta_candidate": narrowed["candidate_count"] == 1
                  and [(row["offset"], row["value"], row["previous_value"]) for row in rows["rows"]]
                  == [(2, 9, 2)], "different_run_refused": refused}
        return {"ok": all(checks.values()), "checks": checks,
                "kernel": {"distribution": "fdisbull-core", "version": version("fdisbull-core")},
                "scope": "Authored offline scalar-search fixture; no native or game qualification"}
    except (ValueError, KeyError, TypeError, ImportError) as error:
        return {"ok": False, "error": str(error), "scope": "Offline shared memory-search check failed"}


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def _number(value):
    try:
        return int(value, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Expected an integer or 0x-prefixed hex value") from error


def _read_bytes(path, limit):
    from .inspection import _read_file
    return _read_file(path, max_bytes=limit)[0]


def _read_json(path):
    def reject_constant(value):
        raise ValueError("Non-finite JSON value is not supported: " + value)
    value = json.loads(_read_bytes(path, MAX_JSON_BYTES), parse_constant=reject_constant)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def _private_parent(info):
    if (not hasattr(os, "getuid") or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise ValueError("Search artifacts require an existing private owned directory (0700)")


def _write_artifact(filename, value, kind):
    """Create a new private metadata file; never overwrite an input or report."""
    target = Path(filename).expanduser().absolute()
    if any(part.is_symlink() for part in (target, *target.parents)):
        raise ValueError("Search artifact destination must not contain symlinks")
    for parent in target.parents:
        marker = parent / ".git"
        bare = ((parent / "HEAD").is_file() and (parent / "objects").is_dir()
                and (parent / "refs").is_dir())
        if marker.exists() or marker.is_symlink() or bare:
            raise ValueError("Private search artifacts must remain outside Git repositories")
    _private_parent(target.parent.lstat())
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    if len(payload) > MAX_JSON_BYTES:
        raise ValueError("Search artifact exceeds its JSON byte budget")
    directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        _private_parent(os.fstat(directory))
        descriptor = os.open(target.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        try:
            with os.fdopen(descriptor, "wb") as output:
                os.fchmod(output.fileno(), 0o600)
                output.write(payload)
        except BaseException:
            os.unlink(target.name, dir_fd=directory)
            raise
    finally:
        os.close(directory)
    summary = {"artifact_kind": kind, "path": str(target), "bytes": len(payload),
               "sha256": hashlib.sha256(payload).hexdigest()}
    summary.update({key: value[key] for key in ("snapshot_sha256", "state_sha256", "candidate_count",
                                               "total_positions", "generation", "complete") if key in value})
    return summary


def _parser():
    parser = _Parser(prog="dotbox memory-search", description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True, parser_class=_Parser)
    snapshot = commands.add_parser("snapshot", help="Bind an existing frozen buffer to explicit context")
    snapshot.add_argument("file")
    snapshot.add_argument("--context", required=True, help="Caller-supplied source/run/mapping context JSON")
    snapshot.add_argument("--capture-id", required=True)
    snapshot.add_argument("--captured-at")
    start = commands.add_parser("start", help="Start a complete bounded scalar candidate search")
    start.add_argument("file")
    start.add_argument("--snapshot", required=True)
    start.add_argument("--width", type=int, choices=(1, 2, 4, 8), default=1)
    start.add_argument("--signed", action="store_true")
    start.add_argument("--byteorder", choices=("little", "big"), default="little")
    start.add_argument("--stride", type=_number, default=1)
    start.add_argument("--bias", type=_number, default=0)
    start.add_argument("--mode", choices=("unknown", "equal", "range"), default="unknown")
    start.add_argument("--minimum", type=_number)
    start.add_argument("--maximum", type=_number)
    refine = commands.add_parser("refine", help="Narrow survivors against a new compatible observation")
    refine.add_argument("state")
    refine.add_argument("before")
    refine.add_argument("after")
    refine.add_argument("--before-snapshot", required=True)
    refine.add_argument("--after-snapshot", required=True)
    refine.add_argument("--mode", required=True,
                        choices=("equal", "not_equal", "changed", "unchanged", "increased", "decreased", "delta"))
    refine.add_argument("--delta", type=_number)
    for command in (start, refine):
        command.add_argument("--value", type=_number)
        command.add_argument("--max-candidates", type=_number, default=_kernel.MAX_CANDIDATES)
    for command in (snapshot, start, refine):
        command.add_argument("--output", required=True, help="New JSON file in a private directory outside Git")
    results = commands.add_parser("results", help="Read a bounded page without dropping retained candidates")
    results.add_argument("state")
    results.add_argument("file")
    results.add_argument("--snapshot", required=True)
    results.add_argument("--before")
    results.add_argument("--before-snapshot")
    results.add_argument("--offset", type=_number, default=0, help="Candidate ordinal, not a byte address")
    results.add_argument("--limit", type=_number, default=64)
    return parser


def main(argv=None):
    try:
        options = vars(_parser().parse_args(argv))
        operation = options.pop("operation")
        output = options.pop("output", None)
        if operation == "snapshot":
            data = _read_bytes(options.pop("file"), _kernel.MAX_SNAPSHOT_BYTES)
            context = _read_json(options.pop("context"))
            value = snapshot_metadata(data, context=context, **options)
        elif operation == "start":
            data = _read_bytes(options.pop("file"), _kernel.MAX_SNAPSHOT_BYTES)
            snapshot = _read_json(options.pop("snapshot"))
            value = start_search(data, snapshot, **options)
        elif operation == "refine":
            state = _read_json(options.pop("state"))
            before = _read_bytes(options.pop("before"), _kernel.MAX_SNAPSHOT_BYTES)
            after = _read_bytes(options.pop("after"), _kernel.MAX_SNAPSHOT_BYTES)
            first, second = (_read_json(options.pop(name)) for name in ("before_snapshot", "after_snapshot"))
            value = refine_search(state, before, first, after, second, **options)
        else:
            state = _read_json(options.pop("state"))
            data = _read_bytes(options.pop("file"), _kernel.MAX_SNAPSHOT_BYTES)
            snapshot = _read_json(options.pop("snapshot"))
            before, before_snapshot = options.pop("before"), options.pop("before_snapshot")
            value = search_results(state, data, snapshot,
                                   before_data=None if before is None else _read_bytes(before, _kernel.MAX_SNAPSHOT_BYTES),
                                   before_snapshot=None if before_snapshot is None else _read_json(before_snapshot),
                                   **options)
        result = _write_artifact(output, value, "snapshot" if operation == "snapshot" else "search") if output else value
        reply = json.dumps({"ok": True, "result": result, "runtime_observed": False, "scope": CLAIM}, allow_nan=False)
        if len(reply.encode()) > MAX_INLINE_BYTES:
            raise ValueError("Result page exceeds 64 KiB; request a smaller --limit")
        print(reply)
        return 0
    except (ValueError, OSError, TypeError, RecursionError, ImportError) as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
