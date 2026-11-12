"""Audit finalized AVI captures without advancing or attaching to a guest.

Each segment retains its own clock. Full-frame decoding/hashing precedes sample
selection; the receipt never promotes video PTS to guest/input timestamps.
FFmpeg/ffprobe are optional external readers, invoked only for this operation.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import html
import io
import json
import math
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import sys
import threading
import time
from fractions import Fraction


class VerificationError(ValueError):
    pass


@dataclass
class _Options:
    every: int
    html: bool
    timeout: float
    max_frames: int
    max_frame_bytes: int
    max_input_bytes: int
    max_metadata_bytes: int
    ffmpeg: str
    ffprobe: str
    output: "_Output"


class _Output:
    """Account for every persisted payload; reserve a small failure-receipt margin."""
    def __init__(self, limit):
        self.limit = limit
        self.used = 0

    def write(self, path, data, *, append=False, receipt=False):
        boundary = self.limit if receipt else self.limit - 1024 * 1024
        if self.used + len(data) > boundary:
            raise VerificationError('Audit output byte budget exceeded')
        with path.open('ab' if append else 'xb') as stream:
            os.chmod(stream.fileno(), 0o600)
            stream.write(data)
        self.used += len(data)


def write_json(path, value, output, *, receipt=False):
    data = (json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + '\n').encode()
    output.write(path, data, receipt=receipt)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def integer(value):
    # ffprobe emits integers or decimal strings. Do not silently truncate a
    # fractional timestamp or accept a boolean as a frame count.
    if type(value) is int:
        return value
    if not isinstance(value, str):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def inspect_riff(path, *, max_frames=10000, timeout=120):
    """Validate chunk boundaries, including truncated/unfinalized captures.

    This does not certify the codec payload. ffprobe and a separate strict
    decode do that below. RIFF size validation is necessary because FFmpeg can
    otherwise salvage a truncated AVI and exit successfully.
    """
    length = path.stat().st_size
    result = {"file_bytes": length, "riff_segments": [], "video_headers": [],
              "main_total_frames": [], "chunk_count": 0}
    deadline = time.monotonic() + timeout
    with path.open("rb") as source:
        def read_at(offset, count):
            source.seek(offset)
            data = source.read(count)
            if len(data) != count:
                raise VerificationError(f"Truncated RIFF data at byte {offset}")
            return data

        def chunks(start, end, depth):
            if depth > 12:
                raise VerificationError("RIFF list nesting exceeds audit limit")
            position = start
            while position < end:
                if time.monotonic() > deadline:
                    raise VerificationError('RIFF inspection exceeded its host timeout')
                if end - position < 8:
                    raise VerificationError(f"Incomplete RIFF chunk header at byte {position}")
                tag, size = struct.unpack("<4sI", read_at(position, 8))
                finish = position + 8 + size
                padded_finish = finish + (size & 1)
                result["chunk_count"] += 1
                if result["chunk_count"] > 1000000:
                    raise VerificationError("RIFF chunk count exceeds audit limit")
                if size == 0xFFFFFFFF or padded_finish > end:
                    raise VerificationError(
                        f"Unfinalized or truncated RIFF chunk {tag!r} at byte {position}: "
                        f"declared end {padded_finish}, enclosing end {end}")
                if tag in (b"RIFF", b"LIST"):
                    if size < 4:
                        raise VerificationError(f"RIFF/LIST chunk lacks type at byte {position}")
                    chunks(position + 12, finish, depth + 1)
                elif tag == b"avih" and size >= 20:
                    result["main_total_frames"].append(struct.unpack("<I", read_at(position + 24, 4))[0])
                elif tag == b"strh" and size >= 36:
                    header = read_at(position + 8, 36)
                    if header[:4] == b"vids":
                        result["video_headers"].append({
                            "codec_tag": header[4:8].decode("ascii", errors="replace"),
                            "scale": struct.unpack_from("<I", header, 20)[0],
                            "rate": struct.unpack_from("<I", header, 24)[0],
                            "start": struct.unpack_from("<I", header, 28)[0],
                            "length": struct.unpack_from("<I", header, 32)[0],
                        })
                        if result['video_headers'][-1]['length'] > max_frames:
                            raise VerificationError('AVI declared frame count exceeds max_frames')
                position = padded_finish

        position = 0
        while position < length:
            if length - position < 12:
                raise VerificationError(f"Incomplete top-level RIFF header at byte {position}")
            tag, size, form = struct.unpack("<4sI4s", read_at(position, 12))
            expected = b"AVI " if position == 0 else b"AVIX"
            if tag != b"RIFF" or form != expected or size < 4:
                raise VerificationError(f"Expected RIFF {expected!r} segment at byte {position}")
            finish = position + 8 + size
            padded_finish = finish + (size & 1)
            if size == 0xFFFFFFFF or padded_finish > length:
                raise VerificationError(
                    f"Unfinalized or truncated AVI: RIFF declares {padded_finish} bytes, file has {length}")
            result["riff_segments"].append({"offset": position, "type": form.decode("ascii").strip(),
                                            "declared_end": finish})
            chunks(position + 12, finish, 1)
            position = padded_finish
        if not result["riff_segments"] or len(result["video_headers"]) != 1:
            raise VerificationError("Expected exactly one AVI video stream header")
    result["boundary_validation"] = "passed"
    return result


def _drain(pipe, limit, data, overflow, process):
    """Drain a child pipe with an actual allocation cap, including failure output."""
    with pipe:
        while True:
            block = pipe.read(65536)
            if not block:
                return
            remaining = max(0, limit - len(data))
            data.extend(block[:remaining])
            if len(block) > remaining:
                overflow.set()
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                return


def run_checked(command, *, timeout, max_bytes, log_path=None, output=None):
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr, overflow = bytearray(), bytearray(), threading.Event()
    readers = [threading.Thread(target=_drain, args=(pipe, limit, data, overflow, process), daemon=True)
               for pipe, limit, data in ((process.stdout, max_bytes, stdout),
                                         (process.stderr, 65536, stderr))]
    for reader in readers:
        reader.start()
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
    finally:
        process.wait()
        for reader in readers:
            reader.join()
    if log_path is not None:
        output.write(log_path, bytes(stderr))
    if timed_out:
        raise VerificationError(f'{Path(command[0]).name} exceeded {timeout:g} host seconds')
    if overflow.is_set():
        raise VerificationError(f'{Path(command[0]).name} output exceeded its byte budget')
    if process.returncode or stderr.strip():
        detail = stderr.decode('utf-8', errors='replace')[-1800:]
        raise VerificationError(f'{Path(command[0]).name} failed strict inspection '
                                f'(exit {process.returncode}): {detail}')
    return bytes(stdout)


def probe(path, directory, options):
    entries = (
        "stream=index,codec_name,codec_long_name,codec_type,width,height,coded_width,coded_height,"
        "pix_fmt,r_frame_rate,avg_frame_rate,time_base,start_pts,start_time,duration_ts,duration,"
        "nb_frames,nb_read_frames:"
        "format=filename,format_name,format_long_name,start_time,duration,size,probe_score:"
        "frame=media_type,stream_index,key_frame,pts,pts_time,pkt_dts,pkt_dts_time,"
        "best_effort_timestamp,best_effort_timestamp_time,pkt_duration,pkt_duration_time,"
        "duration,duration_time,pkt_pos,pkt_size,width,height,pix_fmt,pict_type,repeat_pict"
    )
    command = [options.ffprobe, "-v", "error", "-err_detect", "explode", "-protocol_whitelist", "file,pipe",
               "-f", "avi", "-select_streams", "v:0",
               "-show_streams", "-show_format", "-show_frames", "-count_frames",
               "-show_entries", entries, "-of", "json", str(path)]
    raw = run_checked(command, log_path=directory / "ffprobe.stderr.txt", timeout=options.timeout,
                      max_bytes=options.max_metadata_bytes, output=options.output)
    options.output.write(directory / "ffprobe.json", raw)
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise VerificationError("ffprobe returned invalid JSON") from error
    streams = data.get("streams", [])
    frames = data.get("frames", [])
    if len(streams) != 1 or not frames:
        raise VerificationError("Expected one selected video stream and at least one decoded frame")
    if len(frames) > options.max_frames:
        raise VerificationError(f"{len(frames)} frames exceed --max-frames={options.max_frames}")
    if data.get("format", {}).get("format_name") != "avi":
        raise VerificationError("Input is not an AVI according to ffprobe")
    return data, command


def frame_timing(frame, time_base):
    field = "pts"
    value = integer(frame.get(field))
    if value is None:
        field = "best_effort_timestamp"
        value = integer(frame.get(field))
    if value is None:
        raise VerificationError("Decoded frame has neither PTS nor best-effort timestamp")
    seconds = value * time_base
    return value, field, seconds


def read_frame(pipe, size):
    pieces = []
    remaining = size
    while remaining:
        piece = pipe.read(min(remaining, 1024 * 1024))
        if not piece:
            break
        pieces.append(piece)
        remaining -= len(piece)
    return b"".join(pieces)


def decode(path, directory, stream, frames, options):
    try:
        time_base = Fraction(stream["time_base"])
    except (KeyError, ValueError, ZeroDivisionError) as error:
        raise VerificationError("Missing or invalid video time base") from error
    if time_base <= 0:
        raise VerificationError("Video time base must be positive")
    width, height = integer(stream.get("width")), integer(stream.get("height"))
    if not width or not height or width <= 0 or height <= 0:
        raise VerificationError("Video dimensions must be positive")
    frame_bytes = width * height * 4
    if frame_bytes > options.max_frame_bytes:
        raise VerificationError(f"RGBA frame exceeds --max-frame-bytes={options.max_frame_bytes}")
    for frame in frames:
        if (frame.get("width"), frame.get("height")) != (width, height):
            raise VerificationError("Mid-segment dimensions changed; split/qualify modes explicitly")
    for name in ("nb_frames", "nb_read_frames"):
        count = integer(stream.get(name))
        if count is not None and count != len(frames):
            raise VerificationError(f"{name}={count} differs from ffprobe frame records={len(frames)}; "
                                    "recording may be incomplete or use unsupported repeat chunks")
    if options.every:
        from PIL import Image
        (directory / "png").mkdir(mode=0o700)
    command = [options.ffmpeg, "-v", "error", "-xerror", "-err_detect", "explode", "-threads", "1",
               "-protocol_whitelist", "file,pipe", "-f", "avi", "-i", str(path),
               "-map", "0:v:0", "-an", "-sn", "-dn", "-threads", "1",
               "-fps_mode", "passthrough", "-pix_fmt", "rgba", "-f", "rawvideo", "pipe:1"]
    samples = []
    sequence_hash = hashlib.sha256()
    previous_time = None
    first_time = None
    timestamp_origins = set()
    adjacent_repeats = 0
    previous_hash = None
    timed_out = threading.Event()
    stderr, overflow = bytearray(), threading.Event()
    with subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, bufsize=0) as process:
        error_reader = threading.Thread(target=_drain,
            args=(process.stderr, 65536, stderr, overflow, process), daemon=True)
        error_reader.start()
        def expire():
            timed_out.set()
            try:
                process.kill()
            except ProcessLookupError:
                pass
        timer = threading.Timer(options.timeout, expire)
        timer.daemon = True
        timer.start()
        try:
            assert process.stdout is not None
            for index, frame in enumerate(frames):
                pixels = read_frame(process.stdout, frame_bytes)
                if len(pixels) != frame_bytes:
                    if timed_out.is_set():
                        raise VerificationError(f'Strict decode exceeded {options.timeout:g} host seconds')
                    raise VerificationError(f"Frame {index} decoded {len(pixels)} of {frame_bytes} RGBA bytes")
                pts, origin, seconds = frame_timing(frame, time_base)
                if previous_time is not None and seconds <= previous_time:
                    raise VerificationError(f"Non-increasing video PTS at frame {index}")
                first_time = seconds if first_time is None else first_time
                previous_time = seconds
                timestamp_origins.add(origin)
                digest = hashlib.sha256(pixels).hexdigest()
                adjacent_repeats += int(previous_hash == digest)
                previous_hash = digest
                sequence_hash.update(bytes.fromhex(digest))
                record = {
                    "frame_index": index, "frame_number_base": 0,
                    "stream_index": stream["index"],
                    "source_pts": pts if origin == 'pts' else None, "source_timestamp": pts,
                    "source_timestamp_field": origin, "source_time_base": str(time_base),
                    "source_time_seconds_exact": str(seconds), "source_time_seconds": float(seconds),
                    "clock_domain": "AVI video stream; not guest PIC ticks", "guest_ticks": None,
                    "width": width, "height": height, "source_pixel_format": frame.get("pix_fmt"),
                    "decoded_pixel_format": "rgba", "decoded_bytes": frame_bytes,
                    "decoded_rgba_sha256": digest, "key_frame": bool(frame.get("key_frame")),
                    "packet_position": integer(frame.get("pkt_pos")),
                    "packet_size": integer(frame.get("pkt_size")),
                }
                duration = integer(frame.get("duration", frame.get("pkt_duration")))
                if duration is not None:
                    record["source_duration_units"] = duration
                    record["source_duration_seconds_exact"] = str(duration * time_base)
                if options.every and index % options.every == 0:
                    image_path = directory / "png" / f"frame-{index:08d}.png"
                    image_bytes = io.BytesIO()
                    Image.frombytes("RGBA", (width, height), pixels).save(image_bytes, format='PNG')
                    options.output.write(image_path, image_bytes.getvalue())
                    record["png"] = str(image_path.relative_to(directory))
                    record["png_sha256"] = sha256_file(image_path)
                    samples.append({**record, "image_path": image_path})
                options.output.write(directory / 'frames.jsonl',
                    (json.dumps(record, ensure_ascii=True, allow_nan=False) + '\n').encode(), append=True)
            if process.stdout.read(1):
                raise VerificationError("FFmpeg decoded more frame bytes than ffprobe reported")
            returncode = process.wait()
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill()
            process.wait()
            if process.stdout is not None:
                process.stdout.close()
            error_reader.join()
            options.output.write(directory / 'ffmpeg.stderr.txt', bytes(stderr))
    error_text = stderr.decode('utf-8', errors='replace')
    if timed_out.is_set():
        raise VerificationError(f"Strict decode exceeded {options.timeout:g} host seconds")
    if overflow.is_set():
        raise VerificationError('Strict decode stderr exceeded its byte budget')
    if returncode or error_text.strip():
        raise VerificationError(f"Strict decode failed (exit {returncode}): {error_text[-1800:]}")
    return {
        "decoded_frames": len(frames), "decoded_frame_bytes": frame_bytes,
        "adjacent_identical_frames": adjacent_repeats,
        "rgba_hash_sequence_sha256": sequence_hash.hexdigest(),
        "sequence_hash_definition": "SHA-256 of concatenated 32-byte per-frame RGBA SHA-256 digests",
        "first_source_time_seconds_exact": str(first_time),
        "last_source_time_seconds_exact": str(previous_time),
        "timestamp_fields_used": sorted(timestamp_origins),
        "saved_frames": len(samples), "sampling_every_n": options.every or None,
        "decode_command": command,
    }, samples


def write_viewer(path, samples, title, output):
    # Fail before assembling an excessive self-contained HTML document.
    estimate = sum(4 * ((s['image_path'].stat().st_size + 2) // 3) + 4096 for s in samples) + 8192
    if estimate > min(64 * 1024 * 1024, output.limit - 1024 * 1024 - output.used):
        raise VerificationError('Sample viewer exceeds its byte budget; increase every or omit html')
    payload = []
    for sample in samples:
        item = {name: value for name, value in sample.items() if name != "image_path"}
        item["image"] = "data:image/png;base64," + base64.b64encode(sample["image_path"].read_bytes()).decode("ascii")
        payload.append(item)
    data = json.dumps(payload, ensure_ascii=True, allow_nan=False).replace("<", "\\u003c")
    document = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>AVI frame inspection</title>
<style>body{font:16px system-ui;background:#141b23;color:#eef3f8;max-width:1050px;margin:2em auto;padding:0 1em}
h1{font-size:1.5em}button,select{font:inherit;padding:.4em;margin:.2em}img{display:block;image-rendering:pixelated;
max-width:100%;width:800px;height:auto;margin:1em 0;background:#000}input{width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere}
.note{color:#b9c9da;line-height:1.5}</style>
<h1>__TITLE__</h1><p class="note">Offline sampled-frame inspection. The verifier decoded and hashed every source frame.
This viewer shows the exported sample; original zero-based frame indices and AVI timestamps remain visible.
AVI stream time is not guest PIC time. Guest ticks were not observed.</p>
<button id="previous">Previous</button><button id="play">Play samples</button><button id="next">Next</button>
<label>Inspection speed <select id="speed"><option value="0.1">0.1×</option><option value="0.25" selected>0.25×</option>
<option value="0.5">0.5×</option><option value="1">1×</option></select></label>
<p id="position"></p><input id="slider" type="range" min="0" value="0" aria-label="Sample frame">
<img id="frame" alt="Recorded source frame"><pre id="details"></pre>
<script>const samples=__DATA__;let current=0,timer=null,playing=false;
const el=id=>document.getElementById(id);el('slider').max=samples.length-1;
function show(){const s=samples[current];el('slider').value=current;el('frame').src=s.image;
el('position').textContent=`Sample ${current+1}/${samples.length} · original frame ${s.frame_index} · AVI ${s.source_time_seconds.toFixed(6)} s`;
el('details').textContent=`Frame ${s.frame_index} (zero-based)\n${s.source_timestamp_field} ${s.source_timestamp} × time base ${s.source_time_base} = ${s.source_time_seconds_exact} seconds\n${s.width} × ${s.height}, decoded RGBA\nRGBA SHA-256: ${s.decoded_rgba_sha256}\nGuest ticks: unknown`;}
function stop(){playing=false;clearTimeout(timer);el('play').textContent='Play samples';}
function schedule(){if(!playing)return;if(current===samples.length-1){stop();return;}
const delay=1000*(samples[current+1].source_time_seconds-samples[current].source_time_seconds)/Number(el('speed').value);
timer=setTimeout(()=>{current++;show();schedule();},Math.max(1,delay));}
el('play').onclick=()=>{if(playing){stop();return;}if(current===samples.length-1)current=0;show();playing=true;el('play').textContent='Pause';schedule();};
el('previous').onclick=()=>{stop();current=Math.max(0,current-1);show();};el('next').onclick=()=>{stop();current=Math.min(samples.length-1,current+1);show();};
el('slider').oninput=()=>{stop();current=Number(el('slider').value);show();};el('speed').onchange=()=>{clearTimeout(timer);schedule();};show();
</script></html>"""
    output.write(path, document.replace("__DATA__", data).replace("__TITLE__", html.escape(title)).encode())


def verify_segment(source, directory, options):
    source = Path(os.path.abspath(os.path.expanduser(os.fspath(source))))
    directory.mkdir(mode=0o700)
    result = {"input": str(source), "status": "failed", "guest_ticks": None,
              "clock_domain": "AVI video stream only", "directory": str(directory)}
    try:
        if source.is_symlink() or not source.is_file():
            raise VerificationError(f"Input AVI is missing or not a regular file: {source}")
        identity = source.stat()
        if not stat.S_ISREG(identity.st_mode) or identity.st_size > options.max_input_bytes:
            raise VerificationError('Source AVI exceeds the input byte budget or is not regular')
        result["input_sha256"] = sha256_file(source)
        result["input_bytes"] = identity.st_size
        riff = inspect_riff(source, max_frames=options.max_frames, timeout=options.timeout)
        write_json(directory / "riff.json", riff, options.output)
        metadata, probe_command = probe(source, directory, options)
        stream, frames = metadata["streams"][0], metadata["frames"]
        declared = riff["video_headers"][0]["length"]
        if declared and declared != len(frames):
            raise VerificationError(f"AVI stream header length={declared} but ffprobe decoded {len(frames)} frames")
        decoded, samples = decode(source, directory, stream, frames, options)
        if (source.stat().st_size, source.stat().st_mtime_ns) != (identity.st_size, identity.st_mtime_ns) \
                or sha256_file(source) != result["input_sha256"]:
            raise VerificationError("Source AVI changed during verification; close/finalize capture first")
        result.update({"status": "verified", "stream": stream, "format": metadata["format"],
                       "probe_command": probe_command, "riff_header_frames": declared or None,
                       "riff_segments": riff["riff_segments"], **decoded})
        if options.html:
            write_viewer(directory / "inspection.html", samples, source.name, options.output)
            result["inspection_html"] = str(directory / "inspection.html")
        result["limitations"] = [
            "Video PTS do not establish guest PIC ticks, input-delivery times, or a game completion predicate.",
            "Consistency proves this AVI decoded as recorded, not that the emulator recorded every guest scanout.",
            "Each AVI segment has its own timebase/start; cross-segment guest timing was not inferred.",
            "Pixels are canonically decoded to RGBA; codec/source pixel bytes are not hashed as if equivalent.",
        ]
    except (VerificationError, OSError, ValueError, ImportError) as error:
        result["status"] = "failed"
        result["error"] = str(error)
    write_json(directory / "result.json", result, options.output, receipt=True)
    return result


def audit_capture(inputs, output, *, every=0, html=False, timeout=120,
                  max_frames=10000, max_frame_bytes=16*1024*1024,
                  max_input_bytes=512*1024*1024, max_metadata_bytes=32*1024*1024,
                  max_output_bytes=512*1024*1024, ffmpeg='ffmpeg', ffprobe='ffprobe'):
    """Audit each finalized segment and retain hashes/frames in a private directory.

    Returns a compact receipt. Inspect its ``ok`` field before consuming samples;
    a failed segment can retain partial diagnostics but never certifies a run.
    No emulator, project database or network service is opened.
    """
    if not isinstance(inputs, (list, tuple)) or not 1 <= len(inputs) <= 16:
        raise ValueError('inputs must contain 1..16 AVI paths')
    for value, name, lower, upper in (
        (every, 'every', 0, 100000), (max_frames, 'max_frames', 1, 100000),
        (max_frame_bytes, 'max_frame_bytes', 4, 64*1024*1024),
        (max_input_bytes, 'max_input_bytes', 12, 1024*1024*1024),
        (max_metadata_bytes, 'max_metadata_bytes', 1024, 64*1024*1024),
        (max_output_bytes, 'max_output_bytes', 2*1024*1024, 1024*1024*1024),
    ):
        if type(value) is not int or not lower <= value <= upper:
            raise ValueError(f'{name} must be an integer in {lower}..{upper}')
    if type(html) is not bool or (html and every == 0):
        raise ValueError('html must be boolean and requires every > 0')
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 600:
        raise ValueError('timeout must be finite and in (0,600] host seconds')
    paths = [Path(os.fspath(p)).expanduser().absolute() for p in inputs]
    if len(set(paths)) != len(paths):
        raise ValueError('Duplicate input segment paths are not allowed')
    tools = {}
    for name, selected in (('ffmpeg', ffmpeg), ('ffprobe', ffprobe)):
        executable = shutil.which(os.fspath(selected))
        if not executable:
            raise ValueError(f'Required capture reader not found: {selected}')
        tools[name] = executable
    from .output_artifacts import _private_directory
    destination = Path(os.path.abspath(os.path.expanduser(os.fspath(output))))
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Audit output must be a new directory; existing evidence is never overwritten')
    if not destination.parent.is_dir():
        raise ValueError('Output parent must already exist and be private')
    _private_directory(destination.parent)
    destination.mkdir(mode=0o700)
    _private_directory(destination)
    budget = _Output(max_output_bytes)
    options = _Options(every, html, timeout, max_frames, max_frame_bytes,
                       max_input_bytes, max_metadata_bytes, tools['ffmpeg'], tools['ffprobe'], budget)
    results = [verify_segment(source, destination / f'segment-{number:03d}', options)
               for number, source in enumerate(paths)]
    summary = {
        "schema": "fdisbull.capture-audit.v1", "ok": all(x["status"] == "verified" for x in results),
        "verifier_sha256": sha256_file(Path(__file__).resolve()),
        "python_version": sys.version.splitlines()[0],
        "tools": {},
        "pixel_hash_format": "row-major RGBA, 8 bits per channel",
        "guest_ticks": None, "guest_clock_mapping": "not observed; no synchronization sidecar supplied",
        "segment_order": "input argument order; no inferred chronological concatenation",
        "segments": results,
        "limits": {"max_frames_per_segment": max_frames, "max_rgba_bytes_per_frame": max_frame_bytes,
                   "max_input_bytes_per_segment": max_input_bytes, "max_metadata_bytes": max_metadata_bytes,
                   "max_output_bytes": max_output_bytes, "host_timeout_per_reader_seconds": timeout},
    }
    for name in ("ffmpeg", "ffprobe"):
        executable = getattr(options, name)
        try:
            version = run_checked([executable, '-version'], timeout=min(timeout, 10),
                                  max_bytes=65536).decode('utf-8', errors='replace').splitlines()[0]
        except (OSError, VerificationError, IndexError) as error:
            version = f"Version query unavailable: {error}"
        summary["tools"][name] = {"executable": executable, "version": version}
    summary['status'] = 'passed' if summary['ok'] else 'failed'
    write_json(destination / 'summary.json', summary, budget, receipt=True)
    compact = {'format': 'fdisbull-capture-audit-1', 'ok': summary['ok'], 'status': summary['status'],
               'summary': str(destination / 'summary.json'),
               'summary_sha256': sha256_file(destination / 'summary.json'),
               'output_bytes': budget.used, 'guest_clock_mapping': None, 'segments': []}
    for number, result in enumerate(results):
        compact['segments'].append({'index': number, 'status': result['status'],
            'result': str(destination / f'segment-{number:03d}' / 'result.json'),
            **{key: result[key] for key in ('input_sha256', 'decoded_frames', 'saved_frames',
               'rgba_hash_sequence_sha256', 'adjacent_identical_frames', 'error') if key in result}})
    return compact
