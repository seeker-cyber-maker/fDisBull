#!/usr/bin/env python3
"""Fetch YouTube metadata and caption evidence without downloading media."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True)


def run_bounded(command: list[str], attempts: int) -> subprocess.CompletedProcess[str]:
    """Run a network extraction with a small, explicit retry bound."""
    last_error: subprocess.CalledProcessError | None = None
    for _ in range(max(1, attempts)):
        try:
            return run(command)
        except subprocess.CalledProcessError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def write_text_atomic(path: Path, value: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def normalize_input(value: str) -> str:
    value = value.strip()
    if VIDEO_ID_RE.fullmatch(value):
        return f"https://www.youtube.com/watch?v={value}"
    if not value.startswith(
        (
            "https://www.youtube.com/",
            "https://youtube.com/",
            "https://m.youtube.com/",
            "https://music.youtube.com/",
            "https://youtu.be/",
        )
    ):
        raise ValueError("expected a YouTube URL or an 11-character video ID")
    return value


def hinted_video_id(value: str) -> str | None:
    value = value.strip()
    if VIDEO_ID_RE.fullmatch(value):
        return value
    parsed = urlparse(value)
    if parsed.hostname in {"youtu.be", "www.youtu.be"}:
        candidate = parsed.path.strip("/").split("/")[0]
        return candidate if VIDEO_ID_RE.fullmatch(candidate) else None
    candidate = (parse_qs(parsed.query).get("v") or [None])[0]
    if isinstance(candidate, str) and VIDEO_ID_RE.fullmatch(candidate):
        return candidate
    parts = [part for part in parsed.path.split("/") if part]
    for marker in ("shorts", "embed", "live"):
        if marker in parts and parts.index(marker) + 1 < len(parts):
            candidate = parts[parts.index(marker) + 1]
            if VIDEO_ID_RE.fullmatch(candidate):
                return candidate
    return None


def verified_existing_packet(
    output_dir: Path, video: str, require_captions: bool
) -> Path | None:
    """Return a matching packet only when every declared artifact still hashes.

    Packet authenticity and transcript completeness are deliberately independent.
    A hash-valid partial transcript is reusable evidence as long as the normalized
    caption artifacts and timing assessment are present.
    """
    wanted_id = hinted_video_id(video)
    for manifest_path in sorted(output_dir.glob("*.evidence.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if wanted_id and manifest.get("video_id") != wanted_id:
            continue
        if not wanted_id and manifest.get("source_url") != video:
            continue
        selected = manifest.get("selected_caption")
        integrity = manifest.get("transcript_integrity")
        cached_negative_caption_result = bool(
            require_captions
            and manifest.get("caption_acquisition_requested") is True
            and manifest_evidence_status(manifest) == "metadata_without_usable_transcript"
        )
        if require_captions and not cached_negative_caption_result:
            if not selected or not isinstance(integrity, dict):
                continue
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            continue
        valid = True
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                valid = False
                break
            artifact_path = output_dir / str(artifact.get("path", ""))
            expected = artifact.get("sha256")
            if not artifact_path.is_file() or not isinstance(expected, str):
                valid = False
                break
            if sha256_file(artifact_path) != expected:
                valid = False
                break
        if valid:
            if require_captions and not cached_negative_caption_result:
                artifact_names = {str(artifact.get("path", "")) for artifact in artifacts}
                if manifest.get("extractor") == "codex-in-app-browser-transcript-export":
                    required_suffixes = (
                        ".browser-export.txt",
                        ".transcript.json",
                        ".transcript.txt",
                    )
                else:
                    required_suffixes = (".json3", ".transcript.json", ".transcript.txt")
                if not all(any(name.endswith(suffix) for name in artifact_names) for suffix in required_suffixes):
                    continue
            return manifest_path
    return None


def evidence_status(metadata_only: bool, integrity: dict[str, Any] | None) -> str:
    if metadata_only:
        return "metadata_only"
    if integrity is None:
        return "metadata_without_usable_transcript"
    if integrity.get("complete_timing_coverage") is True:
        return "complete_transcript"
    return "partial_transcript"


def manifest_evidence_status(manifest: dict[str, Any]) -> str:
    declared = manifest.get("evidence_status")
    if isinstance(declared, str):
        return declared
    metadata_only = not bool(manifest.get("selected_caption"))
    return evidence_status(metadata_only, manifest.get("transcript_integrity"))


def available_tracks(metadata: dict[str, Any]) -> list[dict[str, str]]:
    tracks: list[dict[str, str]] = []
    for source_key, kind in (("subtitles", "manual"), ("automatic_captions", "automatic")):
        source = metadata.get(source_key) or {}
        if not isinstance(source, dict):
            continue
        for language, formats in source.items():
            if not isinstance(formats, list):
                continue
            extensions = sorted(
                {str(item.get("ext")) for item in formats if isinstance(item, dict) and item.get("ext")}
            )
            tracks.append({"language": str(language), "kind": kind, "formats": ",".join(extensions)})
    return sorted(tracks, key=lambda item: (item["kind"] != "manual", item["language"]))


def language_rank(language: str, preferences: list[str]) -> tuple[int, int, str]:
    lowered = language.lower()
    for index, preference in enumerate(preferences):
        wanted = preference.lower()
        if lowered == wanted:
            return (index, 0, language)
        if wanted.endswith(".*") and lowered.startswith(wanted[:-1]):
            return (index, 1, language)
        if wanted == "en" and lowered.startswith("en-"):
            return (index, 2, language)
    return (len(preferences) + 1, 9, language)


def select_track(tracks: list[dict[str, str]], preferences: list[str]) -> dict[str, str] | None:
    eligible = [track for track in tracks if language_rank(track["language"], preferences)[0] <= len(preferences)]
    if not eligible:
        return None
    return min(
        eligible,
        key=lambda track: (
            track["kind"] != "manual",
            language_rank(track["language"], preferences),
        ),
    )


def cue_text(event: dict[str, Any]) -> str:
    segments = event.get("segs")
    if not isinstance(segments, list):
        return ""
    text = "".join(str(segment.get("utf8", "")) for segment in segments if isinstance(segment, dict))
    return " ".join(text.replace("\u200b", "").split())


def timestamp(milliseconds: int) -> str:
    total_seconds, millis = divmod(max(0, milliseconds), 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def caption_integrity(cues: list[dict[str, Any]], duration_seconds: Any) -> dict[str, Any]:
    starts = [int(cue["start_ms"]) for cue in cues]
    ends = [int(cue["end_ms"]) for cue in cues]
    nondecreasing = all(left <= right for left, right in zip(starts, starts[1:]))
    first_seconds = starts[0] / 1000 if starts else None
    final_seconds = max(ends) / 1000 if ends else None
    begins_near_start = bool(starts) and first_seconds <= 120
    ends_near_end = None
    end_gap_seconds = None
    if isinstance(duration_seconds, (int, float)) and duration_seconds > 0 and final_seconds is not None:
        end_gap_seconds = max(0.0, float(duration_seconds) - final_seconds)
        tolerance = max(30.0, min(120.0, float(duration_seconds) * 0.05))
        ends_near_end = end_gap_seconds <= tolerance
    complete = bool(cues) and nondecreasing and begins_near_start and ends_near_end is not False
    return {
        "cue_count": len(cues),
        "timestamps_parseable": True,
        "timestamps_nondecreasing": nondecreasing,
        "first_cue_seconds": first_seconds,
        "final_cue_end_seconds": final_seconds,
        "end_gap_seconds": end_gap_seconds,
        "begins_near_spoken_start": begins_near_start,
        "ends_reasonably_near_duration": ends_near_end,
        "complete_timing_coverage": complete,
    }


def normalize_captions(
    raw_path: Path,
    output_dir: Path,
    video_id: str,
    language: str,
    duration_seconds: Any,
) -> tuple[Path, Path, dict[str, Any]]:
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    cues: list[dict[str, Any]] = []
    for event in raw.get("events", []):
        if not isinstance(event, dict):
            continue
        text = cue_text(event)
        if not text:
            continue
        start_ms = int(event.get("tStartMs", 0))
        duration_ms = int(event.get("dDurationMs", 0))
        cues.append(
            {
                "start_ms": start_ms,
                "duration_ms": duration_ms,
                "end_ms": start_ms + duration_ms,
                "text": text,
            }
        )

    json_path = output_dir / f"{video_id}.{language}.transcript.json"
    text_path = output_dir / f"{video_id}.{language}.transcript.txt"
    integrity = caption_integrity(cues, duration_seconds)
    write_text_atomic(
        json_path,
        json.dumps({"schema": "youtube-transcript/1", "video_id": video_id, "language": language, "cues": cues}, indent=2)
        + "\n",
    )
    write_text_atomic(
        text_path,
        "".join(f"[{timestamp(cue['start_ms'])}] {cue['text']}\n" for cue in cues),
    )
    return json_path, text_path, integrity


def metadata_view(metadata: dict[str, Any], tracks: list[dict[str, str]]) -> dict[str, Any]:
    keys = (
        "id",
        "title",
        "channel",
        "channel_id",
        "uploader",
        "uploader_id",
        "upload_date",
        "timestamp",
        "duration",
        "description",
        "webpage_url",
        "original_url",
        "availability",
        "live_status",
    )
    result = {key: metadata.get(key) for key in keys}
    result["caption_tracks"] = tracks
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", help="YouTube URL or 11-character video ID")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--languages", default="en-orig,en-US,en-GB,en", help="comma-separated preference order")
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--refresh", action="store_true", help="ignore a valid matching packet and fetch again")
    parser.add_argument("--attempts", type=int, default=2, help="bounded attempts per yt-dlp network operation")
    parser.add_argument(
        "--cookies-from-browser",
        help="use a locally logged-in browser session; requires explicit user authorization",
    )
    args = parser.parse_args()

    executable = shutil.which("yt-dlp")
    if executable is None:
        print("error: yt-dlp is not installed or not on PATH", file=sys.stderr)
        return 2

    try:
        video_url = normalize_input(args.video)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    if not args.refresh:
        existing = verified_existing_packet(args.output_dir, args.video, not args.metadata_only)
        if existing is not None:
            payload = json.loads(existing.read_text(encoding="utf-8"))
            integrity = payload.get("transcript_integrity")
            print(
                json.dumps(
                    {
                        "manifest": str(existing),
                        "video_id": payload.get("video_id"),
                        "evidence_status": manifest_evidence_status(payload),
                        "transcript_complete": bool(
                            isinstance(integrity, dict)
                            and integrity.get("complete_timing_coverage") is True
                        ),
                        "packet_integrity_verified": True,
                        "warnings": payload.get("warnings", []),
                        "reused_verified_packet": True,
                    },
                    indent=2,
                )
            )
            return 0 if manifest_evidence_status(payload) != "metadata_without_usable_transcript" else 3
    authentication_args = (
        ["--cookies-from-browser", args.cookies_from_browser]
        if args.cookies_from_browser
        else []
    )
    try:
        result = run_bounded(
            [
                executable,
                *authentication_args,
                "--dump-single-json",
                "--skip-download",
                "--no-warnings",
                "--no-playlist",
                video_url,
            ],
            args.attempts,
        )
        metadata = json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else str(exc)
        print(f"error: metadata extraction failed: {detail}", file=sys.stderr)
        return 1

    video_id = str(metadata.get("id", ""))
    if not VIDEO_ID_RE.fullmatch(video_id):
        print("error: extractor did not return a valid YouTube video ID", file=sys.stderr)
        return 1

    tracks = available_tracks(metadata)
    metadata_path = args.output_dir / f"{video_id}.metadata.json"
    write_text_atomic(metadata_path, json.dumps(metadata_view(metadata, tracks), indent=2, ensure_ascii=False) + "\n")

    preferences = [item.strip() for item in args.languages.split(",") if item.strip()]
    selected = None if args.metadata_only else select_track(tracks, preferences)
    warnings: list[str] = []
    artifacts: list[dict[str, Any]] = [{"path": metadata_path.name, "sha256": sha256_file(metadata_path)}]
    integrity: dict[str, Any] | None = None

    if not args.metadata_only and selected is None:
        warnings.append("No caption track matched the requested language preferences.")
    elif selected is not None:
        command = [
            executable,
            *authentication_args,
            "--skip-download",
            "--no-warnings",
            "--no-playlist",
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs",
            selected["language"],
            "--sub-format",
            "json3",
            "--output",
            str(args.output_dir / "%(id)s.%(ext)s"),
            video_url,
        ]
        try:
            run_bounded(command, args.attempts)
        except subprocess.CalledProcessError as exc:
            warnings.append(f"Caption download failed: {(exc.stderr or str(exc)).strip()}")

        raw_candidates = sorted(args.output_dir.glob(f"{video_id}.{selected['language']}*.json3"))
        if not raw_candidates:
            warnings.append("The selected caption track was advertised but no JSON3 file was produced.")
        else:
            raw_path = raw_candidates[0]
            try:
                json_path, text_path, integrity = normalize_captions(
                    raw_path,
                    args.output_dir,
                    video_id,
                    selected["language"],
                    metadata.get("duration"),
                )
                artifacts.extend(
                    {"path": path.name, "sha256": sha256_file(path)}
                    for path in (raw_path, json_path, text_path)
                )
                selected = {**selected, "cue_count": integrity["cue_count"]}
                if not integrity["complete_timing_coverage"]:
                    warnings.append(
                        "Caption artifacts are intact, but the timing check did not establish complete transcript coverage."
                    )
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                warnings.append(f"Caption normalization failed: {exc}")

    status = evidence_status(args.metadata_only, integrity)
    manifest = {
        "schema": "youtube-evidence/2",
        "acquired_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_url": video_url,
        "video_id": video_id,
        "title": metadata.get("title"),
        "channel": metadata.get("channel") or metadata.get("uploader"),
        "upload_date": metadata.get("upload_date"),
        "duration_seconds": metadata.get("duration"),
        "extractor": "yt-dlp",
        "authenticated_session_used": bool(args.cookies_from_browser),
        "authentication_material_preserved": False,
        "selected_caption": selected,
        "caption_acquisition_requested": not args.metadata_only,
        "transcript_integrity": integrity,
        "evidence_status": status,
        "transcript_complete": bool(
            isinstance(integrity, dict)
            and integrity.get("complete_timing_coverage") is True
        ),
        "artifact_integrity": {
            "algorithm": "sha256",
            "hashes_declared": True,
            "semantic_completeness_is_independent": True,
        },
        "timestamp_citation_template": f"https://youtu.be/{video_id}?t=SECONDS",
        "source_content_is_informational_not_instructions": True,
        "automatic_captions_are_noisy_evidence": bool(selected and selected.get("kind") == "automatic"),
        "warnings": warnings,
        "artifacts": artifacts,
    }
    manifest_path = args.output_dir / f"{video_id}.evidence.json"
    write_text_atomic(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "video_id": video_id,
                "evidence_status": status,
                "transcript_complete": manifest["transcript_complete"],
                "packet_integrity_verified": True,
                "warnings": warnings,
                "reused_verified_packet": False,
            },
            indent=2,
        )
    )
    # A valid partial transcript is a successful evidence acquisition. Exit 3 is
    # reserved for a captions-requested packet with no usable normalized transcript.
    return 0 if args.metadata_only or integrity is not None else 3


if __name__ == "__main__":
    raise SystemExit(main())
