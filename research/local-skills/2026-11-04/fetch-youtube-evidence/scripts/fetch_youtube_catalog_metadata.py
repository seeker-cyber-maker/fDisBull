#!/usr/bin/env python3
"""Build a resumable YouTube channel title/description catalog without media."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener

DESCRIPTION_RE = re.compile(r'"shortDescription":"((?:[^"\\]|\\.)*)"')


def now() -> str:
    return datetime.now(UTC).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
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


def yt_dlp() -> str:
    executable = shutil.which("yt-dlp")
    if executable is None:
        raise RuntimeError("yt-dlp is not installed or not on PATH")
    return executable


def authentication_args(browser: str | None) -> list[str]:
    return ["--cookies-from-browser", browser] if browser else []


def flat_catalog(channel_url: str, browser: str | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    result = subprocess.run(
        [
            yt_dlp(),
            *authentication_args(browser),
            "--flat-playlist",
            "--dump-single-json",
            "--",
            channel_url,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    rows: list[dict[str, Any]] = []
    for position, entry in enumerate(payload.get("entries") or []):
        video_id = entry.get("id")
        title = entry.get("title")
        if not isinstance(video_id, str) or len(video_id) != 11 or not isinstance(title, str):
            continue
        rows.append(
            {
                "position": position,
                "video_id": video_id,
                "title": title,
                "description": "",
                "duration_seconds": entry.get("duration"),
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "discovery_route": "channel-tab",
            }
        )
    channel = {
        "title": payload.get("title"),
        "channel": payload.get("channel"),
        "channel_id": payload.get("channel_id"),
        "source_url": channel_url,
    }
    return channel, rows


def search_catalog(query: str, browser: str | None, max_results: int) -> list[dict[str, Any]]:
    result = subprocess.run(
        [
            yt_dlp(),
            *authentication_args(browser),
            "--flat-playlist",
            "--dump-single-json",
            "--",
            f"ytsearch{max(1, max_results)}:{query}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    rows: list[dict[str, Any]] = []
    for position, entry in enumerate(payload.get("entries") or []):
        video_id = entry.get("id")
        title = entry.get("title")
        if not isinstance(video_id, str) or len(video_id) != 11 or not isinstance(title, str):
            continue
        rows.append(
            {
                "position": position,
                "video_id": video_id,
                "title": title,
                "description": "",
                "duration_seconds": entry.get("duration"),
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "channel": entry.get("channel") or entry.get("uploader"),
                "channel_id": entry.get("channel_id"),
                "channel_url": entry.get("channel_url"),
                "discovery_route": "youtube-search",
                "search_query": query,
            }
        )
    return rows


def merge_search_rows(
    rows: list[dict[str, Any]],
    supplemental: list[dict[str, Any]],
    channel_id: str | None,
) -> tuple[list[dict[str, Any]], int]:
    seen = {row["video_id"] for row in rows}
    added = 0
    for row in supplemental:
        if channel_id and row.get("channel_id") != channel_id:
            continue
        if row["video_id"] in seen:
            continue
        row = {**row, "position": len(rows)}
        rows.append(row)
        seen.add(row["video_id"])
        added += 1
    return rows, added


def fetch_with_yt_dlp(row: dict[str, Any], browser: str | None, attempts: int) -> dict[str, Any]:
    errors: list[str] = []
    for attempt in range(1, attempts + 1):
        result = subprocess.run(
            [
                yt_dlp(),
                *authentication_args(browser),
                "--skip-download",
                "--dump-single-json",
                "--no-playlist",
                "--",
                row["url"],
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            try:
                payload = json.loads(result.stdout)
            except json.JSONDecodeError as error:
                errors.append(f"attempt {attempt}: invalid JSON: {error}")
            else:
                return {
                    **row,
                    "title": payload.get("title") or row["title"],
                    "description": payload.get("description") or "",
                    "duration_seconds": payload.get("duration") or row.get("duration_seconds"),
                    "upload_date": payload.get("upload_date"),
                    "status": "ok",
                    "route": "yt-dlp",
                    "acquired_at": now(),
                }
        else:
            errors.append(f"attempt {attempt}: {result.stderr[-400:].strip()}")
        time.sleep(min(attempt, 3))
    return {**row, "status": "failed", "route": "yt-dlp", "errors": errors, "acquired_at": now()}


def ensure_yt_dlp_module() -> Any:
    try:
        from yt_dlp.cookies import extract_cookies_from_browser
    except ModuleNotFoundError:
        executable = Path(yt_dlp()).resolve()
        first_line = executable.open(encoding="utf-8", errors="ignore").readline().strip()
        if first_line.startswith("#!"):
            interpreter = first_line[2:]
            os.execv(interpreter, [interpreter, str(Path(__file__).resolve()), *sys.argv[1:]])
        raise RuntimeError(
            "the watch-html route needs yt_dlp's Python module; run this script with yt-dlp's interpreter"
        )
    return extract_cookies_from_browser


def fetch_watch_html(
    row: dict[str, Any],
    cookie_jar: Any,
    attempts: int,
) -> dict[str, Any]:
    errors: list[str] = []
    opener = build_opener(HTTPCookieProcessor(cookie_jar))
    for attempt in range(1, attempts + 1):
        try:
            request = Request(row["url"], headers={"User-Agent": "Mozilla/5.0"})
            html = opener.open(request, timeout=30).read().decode("utf-8", "replace")
            match = DESCRIPTION_RE.search(html)
            if match:
                return {
                    **row,
                    "description": json.loads('"' + match.group(1) + '"'),
                    "status": "ok",
                    "route": "authenticated-watch-html",
                    "acquired_at": now(),
                }
            errors.append(f"attempt {attempt}: shortDescription not present")
        except (OSError, TimeoutError, URLError, json.JSONDecodeError) as error:
            errors.append(f"attempt {attempt}: {type(error).__name__}: {error}")
        time.sleep(min(attempt, 3))
    return {
        **row,
        "status": "failed",
        "route": "authenticated-watch-html",
        "errors": errors,
        "acquired_at": now(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("channel_url")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--route", choices=("yt-dlp", "watch-html"), default="yt-dlp")
    parser.add_argument("--cookies-from-browser")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument(
        "--search-query",
        action="append",
        default=[],
        help="supplement the channel tab with matching YouTube search results; repeatable",
    )
    parser.add_argument("--search-results", type=int, default=100)
    parser.add_argument(
        "--flat-only",
        action="store_true",
        help="catalog the whole channel from playlist metadata without per-video detail requests",
    )
    args = parser.parse_args()

    if args.route == "watch-html" and not args.cookies_from_browser:
        parser.error("watch-html requires --cookies-from-browser and explicit user authorization")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = args.output_dir / "catalog-metadata.jsonl"
    channel, rows = flat_catalog(args.channel_url, args.cookies_from_browser)
    channel_tab_count = len(rows)
    search_added = 0
    for query in args.search_query:
        supplemental = search_catalog(query, args.cookies_from_browser, args.search_results)
        rows, added = merge_search_rows(rows, supplemental, channel.get("channel_id"))
        search_added += added

    if args.flat_only:
        records = [
            {
                **row,
                "status": "flat",
                "route": "yt-dlp-flat-playlist",
                "acquired_at": now(),
            }
            for row in rows
        ]
        output = {
            "schema": "youtube-channel-metadata/2",
            "acquired_at": now(),
            "channel": channel,
            "record_count": len(records),
            "channel_tab_count": channel_tab_count,
            "search_supplement_count": search_added,
            "search_queries": args.search_query,
            "metadata_ok": len(records),
            "metadata_failed": 0,
            "blank_description_count": len(records),
            "detail_metadata_requested": False,
            "authenticated_session_used": bool(args.cookies_from_browser),
            "authentication_material_preserved": False,
            "ledger_sha256": None,
            "records": records,
        }
        output_path = args.output_dir / "catalog.json"
        write_json(output_path, output)
        print(
            json.dumps(
                {
                    "catalog": str(output_path),
                    "record_count": len(records),
                    "channel_tab_count": channel_tab_count,
                    "search_supplement_count": search_added,
                    "metadata_ok": len(records),
                    "metadata_failed": 0,
                    "detail_metadata_requested": False,
                }
            )
        )
        return 0

    latest = latest_jsonl(ledger_path)
    pending = [row for row in rows if latest.get(row["video_id"], {}).get("status") != "ok"]

    cookie_jar = None
    if args.route == "watch-html":
        extract_cookies = ensure_yt_dlp_module()
        cookie_jar = extract_cookies(args.cookies_from_browser)

    worker_count = max(1, args.workers)
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as pool:
        if args.route == "watch-html":
            futures = {
                pool.submit(fetch_watch_html, row, cookie_jar, args.attempts): row
                for row in pending
            }
        else:
            futures = {
                pool.submit(fetch_with_yt_dlp, row, args.cookies_from_browser, args.attempts): row
                for row in pending
            }
        for completed, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            record = future.result()
            append_jsonl(ledger_path, record)
            latest[record["video_id"]] = record
            if completed % 25 == 0 or record["status"] != "ok":
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

    records = [{**row, **latest.get(row["video_id"], {})} for row in rows]
    failures = [record for record in records if record.get("status") != "ok"]
    blank_descriptions = [record["video_id"] for record in records if not record.get("description")]
    output = {
        "schema": "youtube-channel-metadata/2",
        "acquired_at": now(),
        "channel": channel,
        "record_count": len(records),
        "channel_tab_count": channel_tab_count,
        "search_supplement_count": search_added,
        "search_queries": args.search_query,
        "metadata_ok": len(records) - len(failures),
        "metadata_failed": len(failures),
        "blank_description_count": len(blank_descriptions),
        "detail_metadata_requested": True,
        "authenticated_session_used": bool(args.cookies_from_browser),
        "authentication_material_preserved": False,
        "ledger_sha256": sha256_file(ledger_path),
        "records": records,
    }
    output_path = args.output_dir / "catalog.json"
    write_json(output_path, output)
    print(
        json.dumps(
            {
                "catalog": str(output_path),
                "record_count": len(records),
                "metadata_ok": output["metadata_ok"],
                "metadata_failed": output["metadata_failed"],
                "blank_description_count": len(blank_descriptions),
            }
        )
    )
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
