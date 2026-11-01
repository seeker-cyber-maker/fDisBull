#!/usr/bin/env python3
"""Read-only audit of a stock KQ1 JPC-RR power-on keyboard movie.

Contracts: stock r11.2 PC.saveSavestate, EventRecorder, Keyboard.doEvent,
JRSRArchiveReader/Writer and Misc.parseString. Historical SAVESTATE event rows
are rerecord metadata; they are not the forbidden embedded savestate member.
This audit does not run an emulator or certify a game outcome or submission.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys


KEYBOARD = "org.jpc.emulator.peripheral.Keyboard"
CLOCK_NS = 66_666
BOOT_PREFIX_END_NS = 2_845_504_878
EXPECTED_HARDWARE = {
    "BIOS": ["740f01be58103af0996220bdeb7c4d12"],
    "VGABIOS": ["5555c682e62336cb37eb17c903322be1"],
    "HDD": ["bd183c472bf2c054bfa944a768f10592"],
    "CPUDIVIDER": ["50"],
    "MEMORYSIZE": ["4096"],
    "BOOT": ["FLOPPY"],
    "FDA": ["0"],
}
FREEDOS_ID = "f334bc4d5dc5f393feb0ca2d1e1cdc25"
AUTHOR_KEYS = {"AUTHORS", "AUTHORNICKS", "AUTHORFULL"}
TITLE_KEYS = {"GAMENAME", "TITLE"}
CORE_HEADERS = {"SYSTEM", "PROJECTID", "RERECORDS", "SAVESTATEID"}


class AuditError(ValueError):
    pass


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def is_component_space(char: str) -> bool:
    # Matches the stock Misc.isspace contract; U+2028 is a component separator,
    # whereas U+2029 is an archive line break.
    code = ord(char)
    return code in (9, 12, 32, 0x1680, 0x180E, 0x2028, 0x205F, 0x3000) or 0x2000 <= code <= 0x200A


def unescape(value: str) -> str:
    out, escaped = [], False
    for char in value:
        if escaped:
            out.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        else:
            out.append(char)
    if escaped:
        raise AuditError("Dangling component escape")
    return "".join(out)


def components(line: str) -> list[str]:
    """Read stock parenthesized components, including adjacent KEY(value) forms.

    Stock Misc.parseString preserves escapes in components split by outer
    parentheses and unescapes components split by whitespace/end. Match that
    behavior rather than interpreting these lines as shell arguments.
    """
    values, depth, start, escaped = [], 0, 0, False
    for offset, char in enumerate(line):
        value = None
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "(":
            if depth == 0:
                value, start = line[start:offset], offset + 1
            depth += 1
        elif char == ")":
            if depth == 0:
                raise AuditError("Unbalanced closing component parenthesis")
            depth -= 1
            if depth == 0:
                value, start = line[start:offset], offset + 1
        elif depth == 0 and is_component_space(char):
            value, start = unescape(line[start:offset]), offset + 1
        if value:
            values.append(value)
    if depth:
        raise AuditError("Unbalanced opening component parenthesis")
    value = unescape(line[start:])
    if value:
        values.append(value)
    return values


def read_archive(path: Path) -> dict:
    raw = path.read_bytes()
    if len(raw) > 128 * 1024 * 1024:
        raise AuditError("Movie exceeds the 128 MiB audit limit")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuditError("JRSR archive is not valid UTF-8") from exc
    # These are the archive line breaks accepted by the bundled stock reader.
    lines = re.split(r"[\n\r\x1c\x1d\x1e\x85\u2029]", text)
    if not lines or lines[0] != "JRSR":
        raise AuditError("Missing JRSR archive magic")
    sections, current = {}, None
    for line_number, line in enumerate(lines[1:], 2):
        if not line:
            continue
        if line.startswith("!BEGIN") and len(line) > 6 and is_component_space(line[6]):
            name = line[6:]
            while name and is_component_space(name[0]):
                name = name[1:]
            if not name or len(name.encode("utf-8")) > 1024:
                raise AuditError(f"Invalid member name at line {line_number}")
            if name in sections:
                raise AuditError(f"Duplicate archive member {name!r}")
            current = {"name": name, "first_line": line_number, "lines": []}
            sections[name] = current
        elif line == "!END":
            if current is None:
                raise AuditError(f"!END outside a member at line {line_number}")
            current = None
        elif line.startswith("+") and current is not None:
            current["lines"].append({"line": line_number, "text": line[1:]})
        else:
            raise AuditError(f"Unsupported or misplaced archive line {line_number}")
    if current is not None:
        raise AuditError("Archive ends inside a member; final !END is missing")
    required = {"header", "initialization", "events"}
    missing = required - sections.keys()
    if missing:
        raise AuditError(f"Missing required members: {sorted(missing)}")
    return {"path": str(path.resolve()), "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(), "sections": sections}


def token_rows(section: dict) -> list[dict]:
    result = []
    for row in section["lines"]:
        values = components(row["text"])
        if values:
            result.append({"line": row["line"], "tokens": values})
    return result


def parse_events(section: dict) -> dict:
    relative, timestamp, previous_stored = False, 0, 0
    modes, events, markers, key_edges, others, timing_errors = [], [], [], [], [], []
    held, modifier_flags, keyboard_bound = set(), 0, 0
    for row in token_rows(section):
        parts = row["tokens"]
        if len(parts) < 2:
            raise AuditError(f"Malformed event at line {row['line']}")
        try:
            token_time = int(parts[0])
        except ValueError as exc:
            raise AuditError(f"Invalid event time at line {row['line']}") from exc
        timestamp = timestamp + token_time if relative else token_time
        if timestamp < 0 or timestamp > 0x7FFFFFFFFFFFFFFF or timestamp < previous_stored:
            raise AuditError(f"Negative, overflowing or decreasing event time at line {row['line']}")
        target, args = parts[1], parts[2:]
        event = {"line": row["line"], "source_time": token_time,
                 "source_time_mode": "relative" if relative else "absolute",
                 "timestamp_ns": timestamp, "target": target, "args": args}
        if target == "OPTION":
            if len(args) != 1 or args[0] not in ("RELATIVE", "ABSOLUTE"):
                raise AuditError(f"Invalid timestamp OPTION at line {row['line']}")
            relative = args[0] == "RELATIVE"
            modes.append({"timestamp_ns": timestamp, "mode": args[0], "line": row["line"]})
            continue
        previous_stored = timestamp
        event["sequence"] = len(events)
        events.append(event)
        if target == "SAVESTATE":
            if len(args) not in (1, 2):
                raise AuditError(f"Malformed historical SAVESTATE marker at line {row['line']}")
            markers.append(event)
        elif target == KEYBOARD and len(args) == 2 and args[0] == "KEYEDGE":
            try:
                code = int(args[1])
            except ValueError as exc:
                raise AuditError(f"Invalid keyboard scan code at line {row['line']}") from exc
            if not (1 <= code <= 95 or 129 <= code <= 223) or code in (84, 198):
                raise AuditError(f"Unsupported stock KEYEDGE scan code {code}")
            if timestamp % CLOCK_NS:
                timing_errors.append({"line": row["line"], "timestamp_ns": timestamp,
                                      "error": "Keyboard timestamp is not divisible by 66666 ns"})
            if timestamp < keyboard_bound:
                timing_errors.append({"line": row["line"], "timestamp_ns": timestamp,
                                      "earliest_legal_ns": keyboard_bound,
                                      "error": "Keyboard event precedes the stock serialization bound"})
            pressed = code not in held
            held.add(code) if pressed else held.remove(code)
            edge = {**event, "keyboard_sequence": len(key_edges), "scan_code": code,
                    "edge": "press" if pressed else "release"}
            key_edges.append(edge)
            keyboard_bound = timestamp + CLOCK_NS * (10 if code < 128 or (modifier_flags & 6 and code == 183) else 20)
            if code & 0x7F == 29:
                modifier_flags ^= 1
            if code & 0x7F == 56:
                modifier_flags ^= 2
            if modifier_flags & 6 and code == 183:
                modifier_flags ^= 4
        else:
            others.append(event)
    return {"events": events, "timestamp_modes": modes, "historical_savestate_markers": markers,
            "keyboard_edges": key_edges, "other_dispatch_events": others,
            "keyboard_timing_errors": timing_errors, "held_keys_at_end": sorted(held),
            "last_any_event_ns": events[-1]["timestamp_ns"] if events else None}


def prefix_comparison(candidate: dict, reference_path: Path, cutoff_ns: int) -> dict:
    reference = read_archive(reference_path)
    reference_events = parse_events(reference["sections"]["events"])
    reference_edges = [event for event in reference_events["keyboard_edges"] if event["timestamp_ns"] <= cutoff_ns]
    candidate_edges = [event for event in candidate["keyboard_edges"] if event["timestamp_ns"] <= cutoff_ns]
    def values(edges):
        return [(event["timestamp_ns"], event["target"], tuple(event["args"])) for event in edges]
    expected, actual = values(reference_edges), values(candidate_edges)
    mismatch = None
    for offset in range(max(len(expected), len(actual))):
        a = expected[offset] if offset < len(expected) else None
        b = actual[offset] if offset < len(actual) else None
        if a != b:
            mismatch = {"keyboard_sequence": offset, "reference": a, "candidate": b}
            break
    last = reference_edges[-1] if reference_edges else None
    boundary_is_esc_release = bool(last and last["timestamp_ns"] == cutoff_ns and
                                   last["scan_code"] == 1 and last["edge"] == "release")
    return {"reference": reference["path"], "reference_sha256": reference["sha256"],
            "through_native_ns_inclusive": cutoff_ns, "reference_keyboard_edges": len(expected),
            "candidate_keyboard_edges": len(actual), "unchanged_keyboard_events": expected == actual,
            "reference_boundary_is_esc_release": boundary_is_esc_release,
            "first_mismatch": mismatch,
            "reference_header": token_rows(reference["sections"]["header"]),
            "qualification": "Only timed keyboard events in this prefix are compared. Rerecord markers and archive byte layout may differ. Borrowed input needs explicit attribution; equal keys do not prove a matching game-state outcome."}


def audit_movie(path: Path, reference: Path | None = None, cutoff_ns: int = BOOT_PREFIX_END_NS) -> dict:
    archive = read_archive(path)
    sections = archive["sections"]
    header = token_rows(sections["header"])
    initialization = token_rows(sections["initialization"])
    parsed = parse_events(sections["events"])
    errors, warnings, checks = [], [], []
    header_fields = {}
    for row in header:
        parts = row["tokens"]
        header_fields.setdefault(parts[0], []).append(parts[1:])
    if header_fields.get("SYSTEM") != [["PC-JPC-RR-r10"]]:
        errors.append("SYSTEM header is missing, duplicated or outside the stock movie format")
    project_ids = header_fields.get("PROJECTID", [])
    if len(project_ids) != 1 or len(project_ids[0]) != 1:
        errors.append("A single PROJECTID header is required")
    rerecords = header_fields.get("RERECORDS", [])
    if len(rerecords) != 1 or len(rerecords[0]) != 1 or not re.fullmatch(r"[0-9]+", rerecords[0][0]):
        errors.append("A single nonnegative RERECORDS header is required")
    by_key = {}
    for row in initialization:
        parts = row["tokens"]
        by_key.setdefault(parts[0], []).append(parts[1:])
    for key, expected in EXPECTED_HARDWARE.items():
        actual = by_key.get(key, [])
        passed = actual == [expected]
        checks.append({"key": key, "expected": [expected], "actual": actual, "passed": passed})
        if not passed:
            errors.append(f"Initialization {key} differs from the required single value")
    disks = [values for values in by_key.get("DISK", []) if values and values[0] == "0"]
    disk_ok = disks == [["0", FREEDOS_ID]]
    checks.append({"key": "DISK 0", "expected": [["0", FREEDOS_ID]], "actual": disks, "passed": disk_ok})
    if not disk_ok:
        errors.append("Initialization DISK 0 is not the required FreeDOS image")
    forbidden = [name for name in sections if name in ("savestate", "manifest")]
    state_headers = [row for row in header if row["tokens"][0] == "SAVESTATEID"]
    unexpected = [name for name in sections if name not in ("header", "initialization", "events") and
                  not re.fullmatch(r"diskinfo-[0-9a-fA-F]{32}", name) and name not in forbidden]
    if forbidden:
        errors.append(f"Embedded savestate payload members are present: {forbidden}")
    if state_headers:
        errors.append("SAVESTATEID header marks a state-dependent load")
    if unexpected:
        errors.append(f"Unknown members are outside the audited stock power-on movie scope: {unexpected}")
    if parsed["other_dispatch_events"]:
        errors.append("Contains dispatchable events outside ordinary Keyboard KEYEDGE inputs")
    if parsed["keyboard_timing_errors"]:
        errors.append("Keyboard timestamps violate the stock clock/serialization contract")
    if not parsed["keyboard_edges"]:
        errors.append("No keyboard events are present")
    if parsed["held_keys_at_end"]:
        warnings.append("The event stream ends with held keys; this is reported, not assumed invalid for a TAS.")
    authors = [row["tokens"] for row in header if row["tokens"][0] in AUTHOR_KEYS]
    titles = [row["tokens"] for row in header if row["tokens"][0] in TITLE_KEYS]
    comments = [row["tokens"][1:] for row in header if row["tokens"][0] == "COMMENT"]
    if not authors:
        warnings.append("No AUTHORS/AUTHORNICKS/AUTHORFULL metadata; add the actual authorship and borrowed-prefix attribution before export.")
    if not titles:
        warnings.append("No GAMENAME/TITLE metadata; inspect/add a descriptive game/run title before export.")
    prefix = prefix_comparison(parsed, reference, cutoff_ns) if reference else None
    stale_authors = False
    if prefix:
        if not prefix["unchanged_keyboard_events"] or not prefix["reference_boundary_is_esc_release"]:
            errors.append("Published boot-prefix comparison or requested ESC-release boundary failed")
        ref_authors = [row["tokens"] for row in prefix["reference_header"] if row["tokens"][0] in AUTHOR_KEYS]
        stale_authors = bool(authors and authors == ref_authors)
        if stale_authors:
            warnings.append("Author metadata is identical to the reference; review it for stale sole attribution of this derivative route.")
        warnings.append("Review COMMENT/author metadata to credit the reused reference boot inputs; input equality cannot establish attribution text.")
    if sha256(path) != archive["sha256"]:
        raise AuditError("Movie changed during read-only audit")
    keys = parsed["keyboard_edges"]
    return {"format": "kq1-stock-power-on-movie-audit-1", "ok": not errors,
        "movie": archive["path"], "movie_sha256": archive["sha256"], "movie_bytes": archive["bytes"],
        "input_unchanged_during_audit": True, "errors": errors, "warnings": warnings,
        "sections": [{"name": name, "data_lines": len(section["lines"]), "first_line": section["first_line"]}
                     for name, section in sections.items()],
        "power_on_structure": {"no_embedded_savestate_or_manifest": not forbidden,
            "no_savestate_id_header": not state_headers, "unexpected_members": unexpected,
            "historical_savestate_event_markers": len(parsed["historical_savestate_markers"]),
            "marker_qualification": "Stock movie-only saving records historical SAVESTATE event markers; these do not restore guest state on power-on replay."},
        "hardware_checks": checks, "initialization": initialization, "header": header,
        "metadata_review": {"authors": authors, "titles": titles, "comments": comments,
            "author_fields_identical_to_reference": stale_authors,
            "extra_headers": [row["tokens"] for row in header if row["tokens"][0] not in CORE_HEADERS],
            "qualification": "Metadata is exposed for human review. Matching a game name is expected; this audit does not invent authorship or infer attribution from a title."},
        "timestamp_modes": parsed["timestamp_modes"], "event_count_including_markers": len(parsed["events"]),
        "keyboard_edge_count": len(keys), "key_edge_counts_by_scan_code": dict(sorted(Counter(str(key["scan_code"]) for key in keys).items(), key=lambda item: int(item[0]))),
        "first_keyboard_event_ns": keys[0]["timestamp_ns"] if keys else None,
        "last_keyboard_event_ns": keys[-1]["timestamp_ns"] if keys else None,
        "last_any_event_ns": parsed["last_any_event_ns"], "held_keys_at_end": parsed["held_keys_at_end"],
        "keyboard_timing_errors": parsed["keyboard_timing_errors"], "other_dispatch_events": parsed["other_dispatch_events"],
        "keyboard_edges": keys, "boot_prefix": prefix,
        "scope": "Static read-only stock-format, specified-hardware and keyboard-input audit. Does not execute a guest, prove game completion, certify emulator acceptance, or inspect previous authoring sessions."}


def native_video_fingerprint(path: Path) -> dict:
    """Decode every video payload; do not trust pre-existing JSON frame hashes."""
    from encoding.jmd_capture import parse_jmd, decode_frame
    index = parse_jmd(path)
    streams = {}
    with path.open("rb") as source:
        for frame in index["frames"]:
            image, _ = decode_frame(source, frame)
            row = {"timestamp_ns": frame["timestamp_ns"], "width": frame["width"], "height": frame["height"],
                   "rgb_sha256": hashlib.sha256(image.tobytes() if image is not None else b"").hexdigest()}
            streams.setdefault(frame["stream_name"], []).append(row)
    if sha256(path) != index["input_sha256"]:
        raise AuditError("Native capture changed while being decoded")
    canonical = json.dumps(streams, sort_keys=True, separators=(",", ":")).encode()
    return {"path": str(path.resolve()), "sha256": index["input_sha256"],
            "last_native_timestamp_ns": index["last_observed_timestamp_ns"],
            "native_video_frames": len(index["frames"]), "streams": streams,
            "decoded_video_streams_sha256": hashlib.sha256(canonical).hexdigest()}


def compare_native_replays(first: Path, second: Path) -> dict:
    """Compare exact native video clocks, dimensions and decoded RGB per stream."""
    a, b = native_video_fingerprint(first), native_video_fingerprint(second)
    differences = []
    for name in sorted(set(a["streams"]) | set(b["streams"])):
        left, right = a["streams"].get(name, []), b["streams"].get(name, [])
        if left == right:
            continue
        for offset in range(max(len(left), len(right))):
            x = left[offset] if offset < len(left) else None
            y = right[offset] if offset < len(right) else None
            if x != y:
                differences.append({"stream": name, "first_differing_frame_in_stream": offset,
                                    "first": x, "second": y, "first_count": len(left), "second_count": len(right)})
                break
    end_equal = a["last_native_timestamp_ns"] == b["last_native_timestamp_ns"]
    def brief(value):
        return {key: item for key, item in value.items() if key != "streams"} | {
            "video_stream_counts": {name: len(rows) for name, rows in value["streams"].items()}}
    return {"format": "kq1-native-replay-video-comparison-1", "ok": not differences and end_equal and a["native_video_frames"] > 0,
            "first": brief(a), "second": brief(b), "capture_bytes_identical": a["sha256"] == b["sha256"],
            "all_native_video_timestamps_dimensions_and_rgb_hashes_match": not differences,
            "last_native_timestamp_matches": end_equal, "differences": differences,
            "scope": "Freshly decoded native video streams, exact nanosecond times and dimensions, plus capture end timestamp. Audio, memory, unseen game state, input identity and completion are separate checks."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("movie", type=Path, nargs="?")
    parser.add_argument("--reference", type=Path, help="Reference original-BIOS movie for attributed boot-prefix comparison")
    parser.add_argument("--boot-prefix-end-ns", type=int, default=BOOT_PREFIX_END_NS)
    parser.add_argument("--compare-jmd", type=Path, nargs=2, metavar=("FIRST", "SECOND"), help="Instead compare freshly decoded native capture streams")
    parser.add_argument("--out", type=Path, help="Write full JSON report; stdout otherwise receives the full report")
    args = parser.parse_args()
    if bool(args.movie) == bool(args.compare_jmd):
        parser.error("Supply exactly one movie path or --compare-jmd FIRST SECOND")
    if args.compare_jmd and args.reference:
        parser.error("--reference applies to movie audits only")
    if args.out:
        inputs = [path for path in (args.movie, args.reference, *(args.compare_jmd or [])) if path]
        for path in inputs:
            if args.out.resolve() == path.resolve() or (args.out.exists() and path.exists() and args.out.samefile(path)):
                parser.error("Read-only audit output must not overwrite an input movie or capture")
    try:
        report = (compare_native_replays(*args.compare_jmd) if args.compare_jmd else
                  audit_movie(args.movie, args.reference, args.boot_prefix_end_ns))
    except (AuditError, ValueError, OSError, KeyError) as exc:
        report = {"ok": False, "error": type(exc).__name__, "message": str(exc)}
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n")
        summary = {key: report[key] for key in ("ok", "format", "errors", "warnings", "error", "message", "keyboard_edge_count", "first_keyboard_event_ns", "last_keyboard_event_ns", "held_keys_at_end", "metadata_review", "differences") if key in report}
        print(json.dumps({"report": str(args.out.resolve()), **summary}, indent=2))
    else:
        print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
