#!/usr/bin/env python3
"""Fetch resumable caption-evidence packets for a bounded catalog selection."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(UTC).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_atomic(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def append_jsonl(path: Path, value: Any) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n")


def latest_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    if not path.is_file():
        return latest
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        video_id = record.get("video_id")
        if isinstance(video_id, str):
            latest[video_id] = record
    return latest


def cached_record_valid(record: dict[str, Any], output_dir: Path) -> bool:
    manifest_name = record.get("manifest")
    expected_manifest_hash = record.get("manifest_sha256")
    if not isinstance(manifest_name, str) or not isinstance(expected_manifest_hash, str):
        return False
    manifest_path = output_dir / manifest_name
    if not manifest_path.is_file() or sha256_file(manifest_path) != expected_manifest_hash:
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return False
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            return False
        name = artifact.get("path")
        expected = artifact.get("sha256")
        if not isinstance(name, str) or not isinstance(expected, str):
            return False
        path = manifest_path.parent / name
        if not path.is_file() or sha256_file(path) != expected:
            return False
    return True


def select_records(
    catalog: dict[str, Any],
    title_regex: str,
    max_videos: int,
    ordinal_regex: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    pattern = re.compile(title_regex, re.IGNORECASE)
    ordinal_pattern = re.compile(ordinal_regex, re.IGNORECASE) if ordinal_regex else None
    seen: set[str] = set()
    matches: list[dict[str, Any]] = []
    for record in catalog.get("records") or []:
        if not isinstance(record, dict):
            continue
        video_id = record.get("video_id")
        title = record.get("title")
        if not isinstance(video_id, str) or len(video_id) != 11 or not isinstance(title, str):
            continue
        if video_id in seen or not pattern.search(title):
            continue
        seen.add(video_id)
        ordinal = None
        if ordinal_pattern:
            ordinal_match = ordinal_pattern.search(title)
            if ordinal_match:
                try:
                    ordinal = float(ordinal_match.group(1))
                except (IndexError, ValueError):
                    ordinal = None
        matches.append({**record, "series_ordinal": ordinal})
    if ordinal_pattern:
        matches.sort(
            key=lambda record: (
                record.get("series_ordinal") is None,
                record.get("series_ordinal") or 0,
                record.get("position", 0),
            )
        )
    total_matches = len(matches)
    if max_videos > 0:
        matches = matches[:max_videos]
    return matches, total_matches


def fetch_one(
    record: dict[str, Any],
    output_dir: Path,
    attempts: int,
    languages: str,
    refresh: bool,
) -> dict[str, Any]:
    video_id = record["video_id"]
    video_dir = output_dir / "videos" / video_id
    video_dir.mkdir(parents=True, exist_ok=True)
    script = Path(__file__).with_name("fetch_youtube_evidence.py")
    command = [
        sys.executable,
        str(script),
        record.get("url") or f"https://www.youtube.com/watch?v={video_id}",
        "--output-dir",
        str(video_dir),
        "--attempts",
        str(max(1, attempts)),
        "--languages",
        languages,
    ]
    if refresh:
        command.append("--refresh")
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    payload: dict[str, Any] = {}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        pass
    status = payload.get("evidence_status")
    if result.returncode == 0 and status in {"complete_transcript", "partial_transcript"}:
        batch_status = status
    elif payload.get("manifest"):
        batch_status = "unusable_transcript"
    else:
        batch_status = "failed"
    manifest_path = Path(payload["manifest"]) if payload.get("manifest") else None
    return {
        "video_id": video_id,
        "title": record.get("title"),
        "url": record.get("url") or f"https://www.youtube.com/watch?v={video_id}",
        "status": batch_status,
        "transcript_complete": payload.get("transcript_complete"),
        "reused_verified_packet": payload.get("reused_verified_packet", False),
        "manifest": str(manifest_path.relative_to(output_dir)) if manifest_path else None,
        "manifest_sha256": sha256_file(manifest_path) if manifest_path and manifest_path.is_file() else None,
        "warnings": payload.get("warnings", []),
        "returncode": result.returncode,
        "error": result.stderr[-800:].strip() or None,
        "acquired_at": now(),
    }


def build_collection(
    catalog_path: Path,
    catalog: dict[str, Any],
    title_regex: str,
    ordinal_regex: str | None,
    selected: list[dict[str, Any]],
    total_matches: int,
    records: list[dict[str, Any]],
    dry_run: bool,
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for record in records:
        status = str(record.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    ordinals: dict[str, list[str]] = {}
    for record in records:
        ordinal = record.get("series_ordinal")
        if isinstance(ordinal, (int, float)):
            ordinals.setdefault(str(ordinal), []).append(str(record.get("video_id")))
    integer_ordinals = {
        int(value)
        for value in (record.get("series_ordinal") for record in records)
        if isinstance(value, (int, float)) and float(value).is_integer()
    }
    missing_integer_ordinals: list[int] = []
    if integer_ordinals:
        missing_integer_ordinals = [
            value
            for value in range(min(integer_ordinals), max(integer_ordinals) + 1)
            if value not in integer_ordinals
        ]
    return {
        "schema": "youtube-evidence-collection/1",
        "created_at": now(),
        "source_catalog": str(catalog_path),
        "source_catalog_sha256": sha256_file(catalog_path),
        "channel": catalog.get("channel"),
        "title_regex": title_regex,
        "ordinal_regex": ordinal_regex,
        "total_regex_matches": total_matches,
        "selection_count": len(selected),
        "selection_truncated": len(selected) < total_matches,
        "dry_run": dry_run,
        "status_counts": counts,
        "sequence": {
            "ordered_by_ordinal": bool(ordinal_regex),
            "duplicate_ordinals": {
                ordinal: video_ids for ordinal, video_ids in ordinals.items() if len(video_ids) > 1
            },
            "missing_integer_ordinals": missing_integer_ordinals,
        },
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--title-regex", required=True)
    parser.add_argument(
        "--ordinal-regex",
        help="optional regex with one numeric capture group, for example 'Day +([0-9]+(?:[.][0-9]+)?)'",
    )
    parser.add_argument("--max-videos", type=int, default=25, help="0 means all matches")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--languages", default="en-orig,en-US,en-GB,en")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="write the selected collection without network fetches")
    args = parser.parse_args()

    try:
        catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
        selected, total_matches = select_records(
            catalog, args.title_regex, args.max_videos, args.ordinal_regex
        )
    except (OSError, json.JSONDecodeError, re.error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if not selected:
        print("error: title regex selected no catalog records", file=sys.stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    collection_path = args.output_dir / "collection.json"
    ledger_path = args.output_dir / "batch-events.jsonl"

    if args.dry_run:
        records = [
            {
                "video_id": record["video_id"],
                "title": record["title"],
                "url": record.get("url"),
                "series_ordinal": record.get("series_ordinal"),
                "status": "selected_not_fetched",
            }
            for record in selected
        ]
        collection = build_collection(
            args.catalog,
            catalog,
            args.title_regex,
            args.ordinal_regex,
            selected,
            total_matches,
            records,
            True,
        )
        write_json_atomic(collection_path, collection)
        print(json.dumps({"collection": str(collection_path), **collection["status_counts"]}, indent=2))
        return 0

    latest = latest_jsonl(ledger_path)
    reusable = {"complete_transcript", "partial_transcript"}
    cached_terminal = reusable | {"unusable_transcript"}
    pending = [
        record
        for record in selected
        if args.refresh
        or latest.get(record["video_id"], {}).get("status") not in cached_terminal
        or not cached_record_valid(latest.get(record["video_id"], {}), args.output_dir)
    ]
    workers = min(4, max(1, args.workers))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                fetch_one,
                record,
                args.output_dir,
                args.attempts,
                args.languages,
                args.refresh,
            ): record
            for record in pending
        }
        for completed, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            record = future.result()
            append_jsonl(ledger_path, record)
            latest[record["video_id"]] = record
            if completed % 10 == 0 or record["status"] not in reusable:
                print(
                    json.dumps(
                        {
                            "completed_this_run": completed,
                            "remaining": len(pending) - completed,
                            "last_video_id": record["video_id"],
                            "last_status": record["status"],
                        }
                    ),
                    flush=True,
                )

    records = []
    for selected_record in selected:
        stored = latest.get(selected_record["video_id"])
        records.append(
            {**selected_record, **stored} if stored else {**selected_record, "status": "missing"}
        )
    collection = build_collection(
        args.catalog,
        catalog,
        args.title_regex,
        args.ordinal_regex,
        selected,
        total_matches,
        records,
        False,
    )
    collection["ledger_sha256"] = sha256_file(ledger_path) if ledger_path.is_file() else None
    write_json_atomic(collection_path, collection)
    print(
        json.dumps(
            {
                "collection": str(collection_path),
                "selection_count": len(selected),
                "total_regex_matches": total_matches,
                "selection_truncated": collection["selection_truncated"],
                "status_counts": collection["status_counts"],
            },
            indent=2,
        )
    )
    failed = sum(
        count
        for status, count in collection["status_counts"].items()
        if status not in reusable
    )
    return 0 if failed == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
