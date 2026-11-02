#!/usr/bin/env python3
"""Decode stock JPC-RR multi-stream dumps and encode timestamp-faithful silent video.

The parser follows new-jpcrr-dumpformat and independently checks the RGBx layout
against OutputFrameImage.java. Native timestamps remain integer nanoseconds in
index.json. MP4 presentation uses a microsecond timebase, checked by ffprobe.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import zlib

from PIL import Image


MAGIC = b"\xff\xffJPCRRMULTIDUMP"
TIME_SKIP = 0xFFFFFFFF
MAX_PACKET = 256 * 1024 * 1024
MAX_PIXELS = 32 * 1024 * 1024
VIDEO_TIMEBASE = 1_000_000


class DumpError(ValueError):
    """Malformed, truncated, ambiguous or unsupported capture data."""


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def exact(source, length: int, label: str) -> bytes:
    data = source.read(length)
    if len(data) != length:
        raise DumpError(f"Truncated {label} at offset {source.tell() - len(data)}")
    return data


def variable(source) -> int:
    value = 0
    for _ in range(10):
        byte = exact(source, 1, "VARIABLE payload length")[0]
        value = (value << 7) | (byte & 0x7F)
        if value > MAX_PACKET:
            raise DumpError(f"Payload exceeds the {MAX_PACKET}-byte decoder limit")
        if not byte & 0x80:
            return value
    raise DumpError("Unterminated VARIABLE payload length")


def parse_jmd(path: Path) -> dict:
    """Index a closed JMD without keeping decoded frame buffers in memory."""
    size = path.stat().st_size
    channels = {}
    chapters, frames = [], []
    counts = Counter()
    timestamp = 0
    skips = 0
    packets = 0
    last_event_ns = None
    with path.open("rb") as source:
        while True:
            offset = source.tell()
            prefix = source.read(2)
            if not prefix:
                break
            if len(prefix) != 2:
                raise DumpError(f"Truncated channel/special prefix at offset {offset}")
            if prefix == b"\xff\xff":
                special = exact(source, 4, "special element")
                if special == b"\xff" * 4:
                    if not chapters:
                        raise DumpError("Time skip before initial chapter header")
                    timestamp += TIME_SKIP
                    skips += 1
                    continue
                remainder = exact(source, 10, "chapter magic")
                if prefix + special + remainder != MAGIC:
                    raise DumpError(f"Invalid chapter/special magic at offset {offset}")
                count = struct.unpack(">H", exact(source, 2, "channel count"))[0]
                if count == 0:
                    raise DumpError("A chapter must declare at least one channel")
                channels = {}
                for _ in range(count):
                    channel, kind, length = struct.unpack(">HHH", exact(source, 6, "channel header"))
                    if channel == 0xFFFF or channel in channels:
                        raise DumpError(f"Reserved or duplicate channel {channel}")
                    raw_name = exact(source, length, "channel name")
                    try:
                        name = raw_name.decode("utf-8")
                    except UnicodeDecodeError as exc:
                        raise DumpError("Channel name is not valid UTF-8") from exc
                    channels[channel] = {"id": channel, "type": kind, "name": name}
                chapters.append({"index": len(chapters), "offset": offset,
                                 "start_ns": timestamp, "channels": list(channels.values())})
                continue
            if not chapters:
                raise DumpError("Data precedes the initial JPCRRMULTIDUMP header")
            channel = struct.unpack(">H", prefix)[0]
            if channel not in channels:
                raise DumpError(f"Undeclared channel {channel} at offset {offset}")
            delta, subtype = struct.unpack(">IB", exact(source, 5, "data element header"))
            timestamp += delta
            length = variable(source)
            payload_offset = source.tell()
            if payload_offset + length > size:
                raise DumpError(f"Truncated payload at offset {payload_offset}")
            stream = channels[channel]
            packets += 1
            counts[f"{stream['type']}:{subtype}"] += 1
            last_event_ns = timestamp
            if stream["type"] == 0:
                if subtype not in (0, 1):
                    raise DumpError(f"Unsupported video subtype {subtype}")
                if length < 4:
                    raise DumpError("Video frame lacks its width/height header")
                width, height = struct.unpack(">HH", exact(source, 4, "video dimensions"))
                if width * height > MAX_PIXELS:
                    raise DumpError(f"Invalid or excessive dimensions {width}x{height}")
                if subtype == 0 and length != 4 + width * height * 4:
                    raise DumpError("Raw RGBx length does not match width and height")
                frames.append({"id": len(frames), "timestamp_ns": timestamp,
                    "chapter": len(chapters) - 1, "channel": channel,
                    "stream_name": stream["name"], "subtype": subtype,
                    "packet_offset": offset, "payload_offset": payload_offset,
                    "payload_bytes": length, "width": width, "height": height})
            source.seek(payload_offset + length)
    if not chapters:
        raise DumpError("Empty input or missing JPCRRMULTIDUMP header")
    return {"format": "jpc-rr-native-jmd-index-1", "input": str(path.resolve()),
        "input_sha256": digest(path), "input_bytes": size, "chapters": chapters,
        "packet_count": packets, "packet_type_subtype_counts": dict(counts),
        "time_skip_count": skips, "last_event_ns": last_event_ns,
        "last_observed_timestamp_ns": timestamp, "frames": frames,
        "audio_policy": "Audio packets are indexed in counts but not decoded; video is explicitly silent."}


def decode_frame(source, frame: dict) -> tuple[Image.Image | None, bytes]:
    source.seek(frame["payload_offset"] + 4)
    encoded = exact(source, frame["payload_bytes"] - 4, "video pixels")
    expected = frame["width"] * frame["height"] * 4
    if frame["subtype"] == 0:
        raw = encoded
    else:
        decoder = zlib.decompressobj()
        try:
            raw = decoder.decompress(encoded, expected + 1)
        except zlib.error as exc:
            raise DumpError(f"Invalid zlib frame {frame['id']}: {exc}") from exc
        if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise DumpError(f"Incomplete, oversized or trailing zlib data in frame {frame['id']}")
    if len(raw) != expected:
        raise DumpError(f"Decoded RGBx length mismatch in frame {frame['id']}")
    image = (Image.frombytes("RGB", (frame["width"], frame["height"]), raw, "raw", "RGBX")
             if frame["width"] and frame["height"] else None)
    return image, raw


def choose_stream(index: dict, name: str | None) -> list[dict]:
    names = sorted({frame["stream_name"] for frame in index["frames"]})
    if not names:
        raise DumpError("Capture contains no video frames")
    if name is None:
        if len(names) != 1:
            raise DumpError(f"Multiple video streams {names!r}; choose --stream-name")
        name = names[0]
    frames = [frame for frame in index["frames"] if frame["stream_name"] == name]
    if not frames:
        raise DumpError(f"No video frames in stream {name!r}")
    index["selected_stream_name"] = name
    return frames


def ns_to_us(ns: int) -> int:
    """Round nonnegative absolute presentation offsets, avoiding accumulated drift."""
    return (ns + 500) // 1000


def presentation_plan(frames: list[dict], start_ns: int, end_ns: int) -> tuple[list[dict], list[dict]]:
    if start_ns < 0 or end_ns <= start_ns:
        raise DumpError("Video requires 0 <= start_ns < end_ns")
    times = [frame["timestamp_ns"] for frame in frames]
    first = bisect_right(times, start_ns) - 1
    if first < 0:
        raise DumpError("No captured frame exists at/before requested start; no artificial black lead is inserted")
    rows = [{"frame_id": frames[first]["id"], "native_timestamp_ns": frames[first]["timestamp_ns"],
             "presentation_ns": 0, "carry_from_before_start": frames[first]["timestamp_ns"] < start_ns}]
    for frame in frames[first + 1:]:
        if frame["timestamp_ns"] >= end_ns:
            break
        rows.append({"frame_id": frame["id"], "native_timestamp_ns": frame["timestamp_ns"],
                     "presentation_ns": frame["timestamp_ns"] - start_ns,
                     "carry_from_before_start": False})
    kept, collapsed = [], []
    for row in rows:
        row["pts_us"] = ns_to_us(row["presentation_ns"])
        if kept and row["pts_us"] == kept[-1]["pts_us"]:
            prior = kept.pop()
            prior["reason"] = "Zero-duration native frame or two timestamps quantize to the same microsecond; latest visible state wins."
            collapsed.append(prior)
        kept.append(row)
    end_us = ns_to_us(end_ns - start_ns)
    if end_us <= 0:
        raise DumpError("Requested interval is below the encoder's microsecond resolution")
    while kept and kept[-1]["pts_us"] >= end_us:
        prior = kept.pop()
        prior["reason"] = "Frame rounds to the exclusive video end. Native frame remains in index/PNG extraction."
        collapsed.append(prior)
    if not kept:
        raise DumpError("No positive-duration frame remains in the presentation interval")
    for i, row in enumerate(kept):
        next_us = kept[i + 1]["pts_us"] if i + 1 < len(kept) else end_us
        row["duration_us"] = next_us - row["pts_us"]
        if row["duration_us"] <= 0:
            raise DumpError("Nonpositive VFR presentation duration")
    return kept, collapsed


def canvas_image(image: Image.Image | None, width: int, height: int) -> tuple[Image.Image, dict]:
    if image is None:
        return Image.new("RGB", (width, height), (0, 0, 0)), {
            "source": [0, 0], "canvas": [width, height],
            "representation": "Black presentation of a native zero-area/empty video event, following stock streamtools empty-frame handling."}
    scale = min(Fraction(width, image.width), Fraction(height, image.height))
    target_width = max(1, image.width * scale.numerator // scale.denominator)
    target_height = max(1, image.height * scale.numerator // scale.denominator)
    left, top = (width - target_width) // 2, (height - target_height) // 2
    resized = image.resize((target_width, target_height), Image.Resampling.NEAREST)
    canvas = Image.new("RGB", (width, height), (0, 0, 0))
    canvas.paste(resized, (left, top))
    return canvas, {"source": [image.width, image.height], "scaled": [target_width, target_height],
                    "offset": [left, top], "canvas": [width, height], "resampling": "nearest"}


def command_output(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise DumpError(f"Command failed ({result.returncode}): {command[0]}\n{result.stderr[-8000:]}")
    return result.stdout


def encode_video(out: Path, video: Path, rows: list[dict], video_files: dict[int, str],
                 start_ns: int, end_ns: int, index: dict, canvas: list[int], collapsed: list[dict]) -> dict:
    if video.exists():
        raise DumpError(f"Refusing to overwrite {video}")
    video.parent.mkdir(parents=True, exist_ok=True)
    concat = out / "presentation.ffconcat"
    lines = ["ffconcat version 1.0"]
    for row in rows:
        filename = video_files[row["frame_id"]]
        lines += [f"file '{filename}'", "option framerate 1000000",
                  f"duration {row['duration_us'] // VIDEO_TIMEBASE}.{row['duration_us'] % VIDEO_TIMEBASE:06d}"]
    # A 1us duplicate establishes the last real frame's requested duration in MP4.
    # It is explicitly synthetic, never counted as another native captured frame.
    lines += [f"file '{video_files[rows[-1]['frame_id']]}'", "option framerate 1000000"]
    concat.write_text("\n".join(lines) + "\n")
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-n",
        "-f", "concat", "-safe", "0", "-i", str(concat), "-an", "-fps_mode", "passthrough",
        "-c:v", "libx264", "-preset", "fast", "-crf", "0", "-pix_fmt", "yuv420p", "-bf", "0",
        "-enc_time_base", "1:1000000", "-video_track_timescale", "1000000", "-movflags", "+faststart", str(video)]
    command_output(command)
    probe_command = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_frames", "-show_streams",
                     "-show_format", "-of", "json", str(video)]
    probe = json.loads(command_output(probe_command))
    (out / "ffprobe.json").write_text(json.dumps(probe, indent=2) + "\n")
    stream = probe["streams"][0]
    if Fraction(stream["time_base"]) != Fraction(1, VIDEO_TIMEBASE):
        raise DumpError(f"Unexpected MP4 timebase {stream['time_base']}")
    expected_pts = [row["pts_us"] for row in rows] + [ns_to_us(end_ns - start_ns)]
    actual_frames = probe["frames"]
    actual_pts = [int(frame["pts"]) for frame in actual_frames]
    if actual_pts != expected_pts:
        raise DumpError("ffprobe PTS differ from the explicit native-derived presentation schedule")
    expected_durations = [row["duration_us"] for row in rows] + [1]
    actual_durations = [int(frame.get("duration", frame.get("pkt_duration", -1))) for frame in actual_frames]
    if actual_durations != expected_durations:
        raise DumpError("ffprobe sample durations differ from the explicit presentation schedule")
    endpoint_us = actual_pts[-1] + actual_durations[-1]
    if int(stream["duration_ts"]) != endpoint_us:
        raise DumpError("MP4 track duration does not match its samples")
    errors = [abs(row["pts_us"] * 1000 - row["presentation_ns"]) for row in rows]
    if errors and max(errors) > 500:
        raise DumpError("Native-to-presentation quantization exceeded half a microsecond")
    last_video_ns = max(frame["timestamp_ns"] for frame in index["frames"]
                        if frame["stream_name"] == index["selected_stream_name"] and frame["timestamp_ns"] < end_ns)
    report = {"format": "jpc-rr-1x-vfr-encoding-1", "video": str(video.resolve()),
        "video_sha256": digest(video), "silent": True, "playback_speed": "1x",
        "native_start_ns": start_ns, "native_requested_end_ns": end_ns,
        "native_requested_interval_ns": end_ns - start_ns, "canvas": canvas,
        "native_indexed_frames": len(index["frames"]), "presentation_frames": len(actual_frames),
        "native_derived_presentation_frames": len(rows), "synthetic_endpoint_frames": 1,
        "synthetic_endpoint_duration_us": 1,
        "synthetic_endpoint_qualification": "Duplicate last captured image at the requested end solely to encode the preceding frame duration; not a new native render.",
        "time_base": "1/1000000", "max_native_pts_quantization_error_ns": max(errors, default=0),
        "native_end_quantization_error_ns": ns_to_us(end_ns - start_ns) * 1000 - (end_ns - start_ns),
        "encoded_duration_ns": endpoint_us * 1000,
        "encoded_minus_requested_ns": endpoint_us * 1000 - (end_ns - start_ns),
        "last_video_timestamp_before_exclusive_end_ns": last_video_ns,
        "last_presented_native_timestamp_ns": rows[-1]["native_timestamp_ns"],
        "held_tail_after_last_video_ns": max(0, end_ns - last_video_ns),
        "tail_beyond_last_jmd_timestamp_ns": max(0, end_ns - index["last_observed_timestamp_ns"]),
        "tail_qualification": "The presentation holds the last captured image through the caller's end; no additional native frame or execution is asserted.",
        "collapsed_zero_duration_frames": collapsed, "ffmpeg_command": command,
        "ffprobe_command": probe_command, "pts_verified_exactly_at_microsecond_timebase": True,
        "sample_durations_verified": True, "schedule": rows}
    (out / "encoding.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def process(args) -> dict:
    source_path = args.capture.resolve()
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise DumpError(f"Output directory must be new or empty: {out}")
    if args.export_every < 0:
        raise DumpError("--export-every must be nonnegative; zero exports only explicitly selected frames")
    index = parse_jmd(source_path)
    frames = choose_stream(index, args.stream_name)
    start_ns = frames[0]["timestamp_ns"] if args.start_ns is None else args.start_ns
    end_ns = index["last_observed_timestamp_ns"] if args.end_ns is None else args.end_ns
    rows, collapsed = (presentation_plan(frames, start_ns, end_ns) if args.video else ([], []))
    wanted_video = {row["frame_id"] for row in rows}
    selected = {frame["id"] for n, frame in enumerate(frames) if args.export_every and n % args.export_every == 0}
    queries = []
    for requested in args.select_ns:
        frame = min(frames, key=lambda row: (abs(row["timestamp_ns"] - requested), row["timestamp_ns"]))
        selected.add(frame["id"])
        queries.append({"requested_ns": requested, "frame_id": frame["id"],
                        "actual_ns": frame["timestamp_ns"], "difference_ns": frame["timestamp_ns"] - requested})
    out.mkdir(parents=True, exist_ok=True)
    if selected:
        (out / "frames").mkdir()
    if args.video:
        (out / "video-frames").mkdir()
        if args.canvas:
            try:
                canvas = [int(value) for value in args.canvas.lower().split("x")]
            except ValueError as exc:
                raise DumpError("Canvas must be WIDTHxHEIGHT") from exc
            if len(canvas) != 2 or any(value <= 0 or value % 2 for value in canvas):
                raise DumpError("H.264 presentation canvas dimensions must be positive even integers")
        else:
            included = [frame for frame in frames if frame["id"] in wanted_video]
            canvas = [(max(frame[key] for frame in included) + 1) // 2 * 2 for key in ("width", "height")]
            if not all(canvas):
                raise DumpError("Only empty video events; specify a canvas for a labeled blank presentation")
    else:
        canvas = None
    video_files, video_cache, transforms = {}, {}, {}
    by_stream = {}
    with source_path.open("rb") as source:
        for frame in index["frames"]:
            image, raw = decode_frame(source, frame)
            frame["rgbx_sha256"] = hashlib.sha256(raw).hexdigest()
            frame["rgb_sha256"] = hashlib.sha256(image.tobytes() if image is not None else b"").hexdigest()
            frame["empty_native_video_event"] = image is None
            frame["png"] = None
            prior = by_stream.get(frame["stream_name"])
            if prior is not None:
                prior["next_frame_interval_ns"] = frame["timestamp_ns"] - prior["timestamp_ns"]
            by_stream[frame["stream_name"]] = frame
            if frame["id"] in selected:
                filename = f"frames/frame-{frame['id']:06d}.png"
                if image is None:
                    Image.new("RGB", (1, 1), (0, 0, 0)).save(out / filename)
                    frame["png_qualification"] = "A zero-area native video event has no PNG dimensions; this is an explicitly labeled 1x1 black placeholder."
                else:
                    image.save(out / filename)
                frame["png"] = filename
                frame["png_sha256"] = digest(out / filename)
            if frame["id"] in wanted_video:
                key = (frame["width"], frame["height"], frame["rgb_sha256"])
                if key not in video_cache:
                    presented, transform = canvas_image(image, *canvas)
                    filename = f"video-frames/image-{len(video_cache):06d}.png"
                    presented.save(out / filename)
                    video_cache[key] = filename
                    transforms[f"{frame['width']}x{frame['height']}"] = transform
                video_files[frame["id"]] = video_cache[key]
    for last in by_stream.values():
        last["next_frame_interval_ns"] = None
    if source_path.stat().st_size != index["input_bytes"] or digest(source_path) != index["input_sha256"]:
        raise DumpError("Capture changed while being decoded; close the native dumper before processing")
    index.update({"decoded_all_video_payloads": True, "export_every": args.export_every,
        "input_unchanged_after_decode": True,
        "exported_png_count": len(selected), "selection_queries": queries,
        "native_frame_count": len(index["frames"]), "selected_stream_frame_count": len(frames),
        "first_selected_video_ns": frames[0]["timestamp_ns"], "last_selected_video_ns": frames[-1]["timestamp_ns"],
        "resolution_transforms_for_video_only": transforms,
        "output_scope": "PNG files retain native dimensions and RGB values. Any letterbox/nearest scaling is confined to MP4 presentation."})
    (out / "index.json").write_text(json.dumps(index, indent=2) + "\n")
    result = {"out": str(out), "index": str(out / "index.json"), "frames": len(frames),
        "exported_pngs": len(selected), "first_video_ns": frames[0]["timestamp_ns"],
        "last_video_ns": frames[-1]["timestamp_ns"], "last_dump_timestamp_ns": index["last_observed_timestamp_ns"],
        "selected_frames": queries}
    if args.video:
        video = Path(args.video)
        if not video.is_absolute():
            video = out / video
        report = encode_video(out, video, rows, video_files, start_ns, end_ns, index, canvas, collapsed)
        result["video"] = str(video)
        result["encoding"] = str(out / "encoding.json")
        result["encoded_duration_ns"] = report["encoded_duration_ns"]
        result["max_pts_quantization_error_ns"] = report["max_native_pts_quantization_error_ns"]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--video", nargs="?", const="playback-1x.mp4", help="Encode silent 1x VFR MP4; optional path is relative to --out")
    parser.add_argument("--start-ns", type=int, help="MP4 interval start; default first captured video frame")
    parser.add_argument("--end-ns", type=int, help="MP4 exclusive end; caller-supplied tail is explicitly labeled")
    parser.add_argument("--export-every", type=int, default=1, help="Export every Nth native PNG; default1=all,0=only selections")
    parser.add_argument("--select-ns", type=int, action="append", default=[], help="Also export the closest native frame to this timestamp; repeatable")
    parser.add_argument("--stream-name", help="Required if capture contains multiple named video streams")
    parser.add_argument("--canvas", help="Optional positive even WIDTHxHEIGHT presentation canvas; native PNGs stay unchanged")
    args = parser.parse_args()
    try:
        result = process(args)
    except (DumpError, OSError, KeyError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
