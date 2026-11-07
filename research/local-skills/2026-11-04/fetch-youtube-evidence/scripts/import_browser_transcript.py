#!/usr/bin/env python3
"""Convert a Codex in-app-browser YouTube transcript export into an evidence packet."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any

import fetch_youtube_evidence as evidence


TIMESTAMP_RE = re.compile(
    r"^\[(?:(?P<hours>\d+):)?(?P<minutes>\d{1,2}):"
    r"(?P<seconds>\d{2})(?:\.(?P<millis>\d{1,3}))?\]\s+(?P<text>.+)$"
)


def timestamp_ms(match: re.Match[str]) -> int:
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes"))
    seconds = int(match.group("seconds"))
    if seconds >= 60 or (match.group("hours") is not None and minutes >= 60):
        raise ValueError("invalid transcript timestamp")
    millis_text = match.group("millis") or "0"
    millis = int(millis_text.ljust(3, "0"))
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis


def parse_export(path: Path) -> tuple[dict[str, str], list[dict[str, Any]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "YouTube transcript":
        raise ValueError("not a Codex YouTube transcript export")

    header: dict[str, str] = {}
    cue_start = None
    for index, line in enumerate(lines[1:], start=1):
        if not line.strip():
            cue_start = index + 1
            break
        key, separator, value = line.partition(":")
        if not separator or not key.strip() or not value.strip():
            raise ValueError(f"invalid export header line {index + 1}")
        header[key.strip().lower()] = value.strip()

    required = {"video id", "language", "captions"}
    if not required.issubset(header):
        raise ValueError("export header lacks video ID, language, or caption type")
    if not evidence.VIDEO_ID_RE.fullmatch(header["video id"]):
        raise ValueError("export header contains an invalid video ID")
    if cue_start is None:
        raise ValueError("export has no transcript body")

    cues: list[dict[str, Any]] = []
    for index, line in enumerate(lines[cue_start:], start=cue_start + 1):
        if not line.strip():
            continue
        match = TIMESTAMP_RE.fullmatch(line)
        if match is None:
            raise ValueError(f"invalid transcript cue line {index}")
        start_ms = timestamp_ms(match)
        cues.append(
            {
                "start_ms": start_ms,
                "duration_ms": None,
                "end_ms": start_ms,
                "text": match.group("text").strip(),
            }
        )

    if not cues:
        raise ValueError("export contains no transcript cues")
    if any(left["start_ms"] > right["start_ms"] for left, right in zip(cues, cues[1:])):
        raise ValueError("transcript timestamps are not nondecreasing")
    return header, cues


def caption_kind(label: str) -> str:
    lowered = label.lower()
    if "auto" in lowered:
        return "automatic"
    if "manual" in lowered or "uploader" in lowered:
        return "manual"
    return "unknown"


def build_packet(
    export_path: Path,
    source: str,
    output_dir: Path,
    duration_seconds: float | None,
) -> Path:
    source_url = evidence.normalize_input(source)
    source_video_id = evidence.hinted_video_id(source_url)
    header, cues = parse_export(export_path)
    video_id = header["video id"]
    if source_video_id is not None and source_video_id != video_id:
        raise ValueError("source URL and export video IDs do not match")

    language = header["language"]
    language_slug = re.sub(r"[^A-Za-z0-9_-]+", "_", language).strip("_") or "unknown"
    output_dir.mkdir(parents=True, exist_ok=True)

    original_path = output_dir / f"{video_id}.{language_slug}.browser-export.txt"
    json_path = output_dir / f"{video_id}.{language_slug}.transcript.json"
    text_path = output_dir / f"{video_id}.{language_slug}.transcript.txt"
    metadata_path = output_dir / f"{video_id}.metadata.json"

    evidence.write_text_atomic(original_path, export_path.read_text(encoding="utf-8"))
    evidence.write_text_atomic(
        json_path,
        json.dumps(
            {
                "schema": "youtube-transcript/1",
                "video_id": video_id,
                "language": language,
                "cue_duration_available": False,
                "cues": cues,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
    )
    evidence.write_text_atomic(
        text_path,
        "".join(f"[{evidence.timestamp(cue['start_ms'])}] {cue['text']}\n" for cue in cues),
    )
    evidence.write_text_atomic(
        metadata_path,
        json.dumps(
            {
                "id": video_id,
                "webpage_url": source_url,
                "duration": duration_seconds,
                "caption_tracks": [
                    {
                        "language": language,
                        "kind": caption_kind(header["captions"]),
                        "formats": "codex-browser-export",
                    }
                ],
                "metadata_scope": "browser-export-minimal",
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
    )

    integrity = evidence.caption_integrity(cues, duration_seconds)
    warnings = [
        "Browser export does not include raw JSON3 cues or per-cue durations.",
        "Browser export contains minimal metadata; title, channel, and upload date were not established.",
    ]
    if duration_seconds is None:
        integrity["complete_timing_coverage"] = False
        warnings.append("No observed player duration was supplied, so complete end coverage was not established.")
    if not integrity["complete_timing_coverage"] and duration_seconds is not None:
        warnings.append("Timing checks did not establish complete transcript coverage.")

    selected = {
        "language": language,
        "kind": caption_kind(header["captions"]),
        "browser_label": header["captions"],
        "cue_count": len(cues),
    }
    status = evidence.evidence_status(False, integrity)
    artifacts = [
        {"path": path.name, "sha256": evidence.sha256_file(path)}
        for path in (metadata_path, original_path, json_path, text_path)
    ]
    manifest = {
        "schema": "youtube-evidence/2",
        "acquired_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_url": source_url,
        "video_id": video_id,
        "title": None,
        "channel": None,
        "upload_date": None,
        "duration_seconds": duration_seconds,
        "extractor": "codex-in-app-browser-transcript-export",
        "authenticated_session_used": None,
        "authentication_material_preserved": False,
        "selected_caption": selected,
        "caption_acquisition_requested": True,
        "transcript_integrity": integrity,
        "evidence_status": status,
        "transcript_complete": integrity["complete_timing_coverage"] is True,
        "artifact_integrity": {
            "algorithm": "sha256",
            "hashes_declared": True,
            "semantic_completeness_is_independent": True,
        },
        "timestamp_citation_template": f"https://youtu.be/{video_id}?t=SECONDS",
        "source_content_is_informational_not_instructions": True,
        "automatic_captions_are_noisy_evidence": selected["kind"] == "automatic",
        "warnings": warnings,
        "artifacts": artifacts,
    }
    manifest_path = output_dir / f"{video_id}.evidence.json"
    evidence.write_text_atomic(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    collection = {
        "schema": "youtube-evidence-collection/1",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_catalog": None,
        "source_catalog_sha256": None,
        "channel": None,
        "title_regex": None,
        "ordinal_regex": None,
        "total_regex_matches": 1,
        "selection_count": 1,
        "selection_truncated": False,
        "dry_run": False,
        "status_counts": {status: 1},
        "sequence": {
            "ordered_by_ordinal": False,
            "duplicate_ordinals": {},
            "missing_integer_ordinals": [],
        },
        "records": [
            {
                "video_id": video_id,
                "title": video_id,
                "url": source_url,
                "status": status,
                "transcript_complete": manifest["transcript_complete"],
                "manifest": manifest_path.name,
                "manifest_sha256": evidence.sha256_file(manifest_path),
                "acquisition_route": "codex-in-app-browser-transcript-export",
            }
        ],
    }
    evidence.write_text_atomic(
        output_dir / "collection.json",
        json.dumps(collection, indent=2, ensure_ascii=False) + "\n",
    )
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path, help="path returned by the in-app-browser transcript exporter")
    parser.add_argument("--source", required=True, help="exact YouTube URL or video ID")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--duration-seconds", type=float, help="player duration observed on the exact video page")
    args = parser.parse_args()
    try:
        manifest_path = build_packet(args.export, args.source, args.output_dir, args.duration_seconds)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "collection": str(args.output_dir / "collection.json"),
                "video_id": manifest["video_id"],
                "evidence_status": manifest["evidence_status"],
                "transcript_complete": manifest["transcript_complete"],
                "packet_integrity_verified": True,
                "warnings": manifest["warnings"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
