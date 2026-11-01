#!/usr/bin/env python3
"""Optional native PC-speaker PCM extraction and sound muxing; silent video stays untouched.

The native PCM stream is a timestamped sample-and-hold signal. A 48 kHz WAV is
derived by exact time-weighted averaging over each sample interval. Native
events remain in JSON. A separate AAC MP4 can copy the validated silent video
track unchanged. Active FM, other PCM sources and non-unit volume are rejected
rather than silently omitted or approximated.
"""
from __future__ import annotations

import argparse
from array import array
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import wave

try:
    from .jmd_capture import DumpError, digest, exact, parse_jmd, variable, TIME_SKIP
except ImportError:
    from jmd_capture import DumpError, digest, exact, parse_jmd, variable, TIME_SKIP


PC_SPEAKER = "org.jpc.emulator.peripheral.PCSpeaker-0"
NANOSECONDS = 1_000_000_000


def read_native_audio(capture: Path, stream_name: str = PC_SPEAKER) -> dict:
    index = parse_jmd(capture)
    chapters = {chapter["offset"]: chapter for chapter in index["chapters"]}
    channels, timestamp, packet_count = {}, 0, 0
    events, counts, active_pcm, active_fm = [], Counter(), set(), set()
    with capture.open("rb") as source:
        while source.tell() < index["input_bytes"]:
            offset = source.tell()
            if offset in chapters:
                chapter = chapters[offset]
                channels = {channel["id"]: channel for channel in chapter["channels"]}
                header_size = 18 + sum(6 + len(channel["name"].encode("utf-8")) for channel in channels.values())
                source.seek(offset + header_size)
                continue
            prefix = exact(source, 2, "audio scan packet channel")
            if prefix == b"\xff\xff":
                if exact(source, 4, "audio scan time skip") != b"\xff" * 4:
                    raise DumpError("Audio scanner encountered an unindexed chapter or unknown special element")
                timestamp += TIME_SKIP
                continue
            channel = channels[struct.unpack(">H", prefix)[0]]
            delta, subtype = struct.unpack(">IB", exact(source, 5, "audio scan packet header"))
            timestamp += delta
            length = variable(source)
            packet_count += 1
            if channel["type"] not in (1, 2):
                source.seek(length, 1)
                continue
            payload = exact(source, length, "native audio payload")
            counts[f"{channel['name']}:{channel['type']}:{subtype}"] += 1
            event = {"timestamp_ns": timestamp, "packet_offset": offset, "channel": channel["name"],
                     "type": channel["type"], "subtype": subtype, "payload_hex": payload.hex()}
            if subtype == 0:
                if length != 16:
                    raise DumpError("Audio volume payload must contain four DWORDs")
                ln, ld, rn, rd = struct.unpack(">IIII", payload)
                if not ld or not rd:
                    raise DumpError("Audio volume denominator is zero")
                event["volume"] = [[ln, ld], [rn, rd]]
                if channel["type"] == 1 and channel["name"] == stream_name and (ln != ld or rn != rd):
                    raise DumpError("Non-unit PC-speaker volume is outside this helper's declared scope")
            elif channel["type"] == 1 and subtype == 1:
                if length != 4:
                    raise DumpError("Native PCM sample must contain two signed WORDs")
                event["left"], event["right"] = struct.unpack(">hh", payload)
                active_pcm.add(channel["name"])
            elif channel["type"] == 2:
                active_fm.add(channel["name"])
            else:
                raise DumpError(f"Unsupported PCM subtype {subtype}")
            events.append(event)
    if packet_count != index["packet_count"] or timestamp != index["last_observed_timestamp_ns"]:
        raise DumpError("Audio scan disagrees with the independently validated native container index")
    if active_fm:
        raise DumpError(f"Active FM synthesis is outside this helper's scope: {sorted(active_fm)}")
    if active_pcm - {stream_name}:
        raise DumpError(f"Other active PCM streams would be omitted: {sorted(active_pcm - {stream_name})}")
    selected = [event for event in events if event["channel"] == stream_name and event["type"] == 1 and event["subtype"] == 1]
    if not selected:
        raise DumpError(f"No native PCM samples in {stream_name!r}")
    if digest(capture) != index["input_sha256"]:
        raise DumpError("Capture changed during native audio scan")
    return {"format": "jpc-rr-native-pc-speaker-events-1", "capture": str(capture.resolve()),
            "capture_sha256": index["input_sha256"], "capture_bytes": index["input_bytes"],
            "native_last_timestamp_ns": timestamp, "selected_stream": stream_name,
            "active_pcm_streams": sorted(active_pcm), "active_fm_streams": sorted(active_fm),
            "audio_packet_counts": dict(counts), "selected_pcm_event_count": len(selected),
            "selected_first_event_ns": selected[0]["timestamp_ns"],
            "selected_last_event_ns": selected[-1]["timestamp_ns"],
            "events": events,
            "signal_contract": "Big-endian signed stereo 16-bit PCM levels held until the next timestamp; initial silence before the first event. Events at identical timestamps retain native order. Unit gain; no automatic normalization or filtering."}


def render_pcm(events: list[dict], start_ns: int, end_ns: int, rate: int) -> tuple[bytes, dict]:
    """Average the held level over exact rational sample intervals, not video frames."""
    if start_ns < 0 or end_ns <= start_ns or not 8000 <= rate <= 192000:
        raise DumpError("Audio requires a positive interval and a sample rate from 8000 to 192000 Hz")
    if any(events[i]["timestamp_ns"] > events[i+1]["timestamp_ns"] for i in range(len(events)-1)):
        raise DumpError("PCM events are not in native timestamp order")
    sample_count = ((end_ns-start_ns)*rate + NANOSECONDS-1)//NANOSECONDS
    if sample_count > 50_000_000:
        raise DumpError("Audio interval exceeds this helper's 50 million sample-frame memory limit")
    # Coordinates are integer ns*Hz. Every output sample is exactly 1e9 units
    # wide, so a native transition never needs rounding onto an audio frame.
    ticks = [event["timestamp_ns"]*rate for event in events]
    origin, end = start_ns*rate, end_ns*rate
    event_id, left, right = 0, 0, 0
    while event_id < len(events) and ticks[event_id] <= origin:
        left, right = events[event_id]["left"], events[event_id]["right"]
        event_id += 1
    pcm = array("h")
    peak, nonzero = 0, 0
    for sample in range(sample_count):
        cursor = origin + sample*NANOSECONDS
        boundary = min(origin + (sample+1)*NANOSECONDS, end)
        area_left = area_right = 0
        while event_id < len(events) and ticks[event_id] < boundary:
            event_tick = ticks[event_id]
            duration = event_tick-cursor
            area_left += left*duration
            area_right += right*duration
            cursor = event_tick
            left, right = events[event_id]["left"], events[event_id]["right"]
            event_id += 1
        area_left += left*(boundary-cursor)
        area_right += right*(boundary-cursor)
        # C++ stock PCM averaging truncates signed integer division toward zero.
        lvalue = (abs(area_left)//NANOSECONDS)*(-1 if area_left < 0 else 1)
        rvalue = (abs(area_right)//NANOSECONDS)*(-1 if area_right < 0 else 1)
        pcm.extend((lvalue, rvalue))
        peak = max(peak, abs(lvalue), abs(rvalue))
        nonzero += lvalue != 0 or rvalue != 0
    if sys.byteorder != "little":
        pcm.byteswap()
    padding = Fraction(sample_count*NANOSECONDS, rate)-(end_ns-start_ns)
    return pcm.tobytes(), {"sample_rate_hz": rate, "channels": 2, "sample_width_bits": 16,
        "sample_frames": sample_count, "native_start_ns": start_ns, "native_end_ns": end_ns,
        "audio_duration_ns_rational": [sample_count*NANOSECONDS, rate],
        "final_fractional_sample_zero_padding_ns_rational": [padding.numerator, padding.denominator],
        "absolute_peak": peak, "nonzero_sample_frames": nonzero,
        "resampling": "Exact time-weighted sample-and-hold integration in integer ns*Hz units; signed average truncates toward zero. No rate change. Final fractional sample, if any, is padded with zero rather than asserting additional native execution.",
        "qualification": "WAV is a uniformly sampled rendering of the preserved native event signal, not a claim that the emulator emitted uniformly spaced PCM frames. It has unit gain and no analog-speaker response filter."}


def run_json(command: list[str]) -> dict:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise DumpError(f"Command failed: {command[0]}: {result.stderr[-4000:]}")
    return json.loads(result.stdout)


def video_packets(path: Path) -> dict:
    return run_json(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams", "-show_packets",
                     "-show_data_hash", "sha256", "-of", "json", str(path)])


def mux_and_verify(silent: Path, wav: Path, output: Path, wav_info: dict, out: Path) -> dict:
    if output.exists():
        raise DumpError(f"Refusing to overwrite {output}")
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-i", str(silent), "-i", str(wav),
               "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
               "-video_track_timescale", "1000000", "-movflags", "+faststart", str(output)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise DumpError(f"Audio mux failed: {result.stderr[-4000:]}")
    before, after = video_packets(silent), video_packets(output)
    fields = ("pts", "dts", "duration", "size", "data_hash")
    a = [[packet.get(field) for field in fields] for packet in before["packets"]]
    b = [[packet.get(field) for field in fields] for packet in after["packets"]]
    if a != b or before["streams"][0]["time_base"] != after["streams"][0]["time_base"]:
        raise DumpError("Mux changed video packet timestamps, durations, payloads or timebase")
    audio = run_json(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_packets", "-show_streams", "-of", "json", str(output)])
    (out/"mux-video-ffprobe.json").write_text(json.dumps(after, indent=2)+"\n")
    (out/"mux-audio-ffprobe.json").write_text(json.dumps(audio, indent=2)+"\n")
    stream = audio["streams"][0]
    rate = wav_info["sample_rate_hz"]
    if int(stream["sample_rate"]) != rate or Fraction(stream["time_base"]) != Fraction(1, rate):
        raise DumpError("Mux changed the intended audio sample clock")
    if int(stream["start_pts"]) != 0:
        raise DumpError("AAC playback does not start at presentation time zero")
    packets = audio["packets"]
    first_pts = int(packets[0]["pts"])
    skip = sum(int(item.get("skip_samples", 0)) for item in packets[0].get("side_data_list", []))
    if first_pts+skip != 0:
        raise DumpError("AAC priming is not exactly compensated by declared skip samples")
    duration = int(stream["duration_ts"])
    if abs(duration-wav_info["sample_frames"]) > 1:
        raise DumpError("AAC declared duration differs from native-derived WAV by more than one sample")
    return {"output": str(output.resolve()), "output_sha256": digest(output), "ffmpeg_command": command,
            "video_packets_bitstream_and_timestamps_unchanged": True, "video_packet_count": len(a),
            "audio_codec": stream["codec_name"], "audio_sample_rate": rate, "audio_start_pts": 0,
            "audio_duration_samples": duration, "wav_samples": wav_info["sample_frames"],
            "aac_duration_difference_samples": duration-wav_info["sample_frames"],
            "first_aac_packet_pts": first_pts, "aac_priming_skip_samples": skip,
            "aac_priming_compensated_to_zero": True,
            "qualification": "AAC preview audio is lossy. Native event JSON and PCM WAV are retained. The video track is copied without changing its payloads or timing; audio priming is explicitly compensated in the MP4 metadata."}


def process(args) -> dict:
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise DumpError("Audio output directory must be new or empty")
    encoding = json.loads(args.encoding.read_text())
    native_index = json.loads((args.encoding.parent/"index.json").read_text())
    native = read_native_audio(args.capture, args.stream_name)
    if native["capture_sha256"] != native_index["input_sha256"]:
        raise DumpError("Native capture does not match the validated video index")
    silent = Path(encoding["video"])
    if digest(silent) != encoding["video_sha256"]:
        raise DumpError("Silent video differs from its validated encoding receipt")
    start, end = encoding["native_start_ns"], encoding["native_requested_end_ns"]
    selected = [event for event in native["events"] if event["channel"] == args.stream_name and event["type"] == 1 and event["subtype"] == 1]
    pcm, wav_info = render_pcm(selected, start, end, args.rate)
    out.mkdir(parents=True, exist_ok=True)
    (out/"native-audio-events.json").write_text(json.dumps(native, indent=2)+"\n")
    wav = out/"native-pc-speaker-1x.wav"
    with wave.open(str(wav), "wb") as dest:
        dest.setnchannels(2)
        dest.setsampwidth(2)
        dest.setframerate(args.rate)
        dest.writeframes(pcm)
    report = {"format": "jpc-rr-pc-speaker-audio-render-1", "capture_sha256": native["capture_sha256"],
        "native_events": str((out/"native-audio-events.json").resolve()), "wav": str(wav),
        "wav_sha256": digest(wav), "raw_pcm_sha256": hashlib.sha256(pcm).hexdigest(),
        "silent_video": str(silent), "silent_video_sha256": encoding["video_sha256"],
        "audio": wav_info, "presentation_native_origin_ns": start,
        "alignment": "Audio sample zero and video PTS zero share the same declared native crop start. No speed change or empirical offset was applied.",
        "native_tail_hold_after_last_pcm_event_ns": max(0, end-native["selected_last_event_ns"]),
        "tail_beyond_last_jmd_timestamp_ns": max(0, end-native["native_last_timestamp_ns"])}
    if args.mux:
        report["mux"] = mux_and_verify(silent, wav, out/"playback-1x-with-sound.mp4", wav_info, out)
    if digest(args.capture) != native["capture_sha256"] or digest(silent) != encoding["video_sha256"]:
        raise DumpError("An input changed during audio rendering/muxing")
    (out/"audio-render.json").write_text(json.dumps(report, indent=2)+"\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--encoding", type=Path, required=True, help="Validated silent encoding.json; sibling index.json establishes capture identity")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--rate", type=int, default=48000)
    parser.add_argument("--stream-name", default=PC_SPEAKER)
    parser.add_argument("--mux", action="store_true", help="Also produce an AAC MP4 with unchanged copied video")
    args = parser.parse_args()
    try:
        report = process(args)
    except (DumpError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "report": str((args.out/"audio-render.json").resolve()),
                      "wav": report["wav"], "audio": report["audio"], "mux": report.get("mux")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
