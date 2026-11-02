#!/usr/bin/env python3
"""Find the first complete KQ1 endpoint windows in a closed native JPC-RR dump.

This is a read-only image comparison, not an emulator or game-state observer.
Each accepted match is byte-exact RGB for the whole fixed modal window. Full
matching and immediately preceding native images are saved for visual review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent / "encoding"))
import jmd_capture


WINDOWS = {
    # Pillow's right and lower coordinates are exclusive. These rectangles
    # include the complete white/red border and no score or room background.
    "king_steps_aside": (92, 150, 548, 202),
    "final_credits": (60, 86, 564, 266),
}


def rgb_hash(image: Image.Image | None) -> str:
    return hashlib.sha256(image.tobytes() if image is not None else b"").hexdigest()


def frame_record(frame: dict, image: Image.Image | None, sequence: int) -> dict:
    return {
        "frame_id": frame["id"],
        "selected_stream_frame_index": sequence,
        "timestamp_ns": frame["timestamp_ns"],
        "width": frame["width"],
        "height": frame["height"],
        "rgb_sha256": rgb_hash(image),
    }


def scan(capture: Path, output: Path, endpoint: Path, credits: Path,
         stream_name: str | None = None) -> dict:
    started = time.monotonic_ns()
    capture, output = capture.resolve(), output.resolve()
    if output.exists():
        raise ValueError("Output directory must be new; existing evidence is preserved")
    initial_bytes = capture.stat().st_size
    initial_hash = jmd_capture.digest(capture)
    index = jmd_capture.parse_jmd(capture)
    if index["input_bytes"] != initial_bytes or index["input_sha256"] != initial_hash:
        raise ValueError("Capture changed while its index was read")
    frames = jmd_capture.choose_stream(index, stream_name)

    references, expected, retained = {}, {}, {}
    for name, reference in (("king_steps_aside", endpoint), ("final_credits", credits)):
        reference = reference.resolve()
        original_hash = jmd_capture.digest(reference)
        with Image.open(reference) as opened:
            image = opened.convert("RGB")
        if image.size != (640, 400):
            raise ValueError(f"Reference {name} is not a native 640x400 image")
        crop = image.crop(WINDOWS[name]).tobytes()
        references[name] = {
            "path": str(reference), "file_sha256": original_hash,
            "native_dimensions": list(image.size),
            "crop_ltrb_exclusive": list(WINDOWS[name]),
            "crop_rgb_sha256": hashlib.sha256(crop).hexdigest(),
        }
        expected[name] = crop

    results = {name: {"found": False} for name in WINDOWS}
    previous = None
    decoded = 0
    with capture.open("rb") as source:
        for sequence, frame in enumerate(frames):
            image, _raw = jmd_capture.decode_frame(source, frame)
            decoded += 1
            if image is not None and image.size == (640, 400):
                for name, crop in expected.items():
                    if results[name]["found"]:
                        continue
                    if image.crop(WINDOWS[name]).tobytes() != crop:
                        continue
                    match = frame_record(frame, image, sequence)
                    match["crop_rgb_sha256"] = references[name]["crop_rgb_sha256"]
                    predecessor = None
                    if previous is not None:
                        previous_frame, previous_image, previous_sequence = previous
                        predecessor = frame_record(previous_frame, previous_image, previous_sequence)
                        predecessor["crop_matches_reference"] = bool(
                            previous_image is not None
                            and previous_image.size == (640, 400)
                            and previous_image.crop(WINDOWS[name]).tobytes() == crop
                        )
                        if predecessor["crop_matches_reference"]:
                            raise AssertionError("A preceding match was incorrectly skipped")
                    results[name] = {
                        "found": True, "match": match, "predecessor": predecessor,
                        "comparison": "Exact RGB bytes across the entire fixed modal, including its border",
                    }
                    retained[name] = (image, previous[1] if previous is not None else None)
            previous = (frame, image, sequence)
            if all(item["found"] for item in results.values()):
                break

    final_hash = jmd_capture.digest(capture)
    if capture.stat().st_size != initial_bytes or final_hash != initial_hash:
        raise ValueError("Capture changed during landmark scanning")
    for reference in references.values():
        if jmd_capture.digest(Path(reference["path"])) != reference["file_sha256"]:
            raise ValueError("A reference image changed during landmark scanning")

    output.mkdir(parents=True, exist_ok=False)
    for name, images in retained.items():
        for kind, image in zip(("match", "predecessor"), images):
            record = results[name][kind]
            if record is None:
                continue
            if image is None:
                record["png"] = None
                record["png_qualification"] = "Preceding native event has zero image area"
                continue
            path = output / f"{name}-{kind}.png"
            image.save(path)
            record["png"] = path.name
            record["png_sha256"] = jmd_capture.digest(path)

    report = {
        "format": "kq1-native-visible-landmarks-1",
        "capture": str(capture), "capture_sha256": initial_hash,
        "capture_bytes": initial_bytes, "capture_unchanged": True,
        "decoder": str(Path(jmd_capture.__file__).resolve()),
        "decoder_sha256": jmd_capture.digest(Path(jmd_capture.__file__)),
        "scanner_sha256": jmd_capture.digest(Path(__file__)),
        "selected_stream_name": index["selected_stream_name"],
        "indexed_native_frames": len(index["frames"]),
        "selected_stream_frames": len(frames),
        "decoded_frames_scanned": decoded,
        "stopped_after_both_first_matches": all(item["found"] for item in results.values()),
        "native_last_timestamp_ns": index["last_observed_timestamp_ns"],
        "references": references, "landmarks": results,
        "all_landmarks_found": all(item["found"] for item in results.values()),
        "host_scan_elapsed_ns": time.monotonic_ns() - started,
        "scope": "First complete captured windows on this selected native video stream. Every preceding frame was decoded and compared. Later payloads may only be indexed. No internal game completion, last-input timing, or gameplay start convention is inferred.",
        "visual_review_required": "Inspect each matching PNG and its immediate predecessor before reporting the visible endpoint. Exact matching does not independently authenticate the reference image's meaning.",
    }
    (output / "landmarks.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--endpoint-reference", type=Path, required=True)
    parser.add_argument("--credits-reference", type=Path, required=True)
    parser.add_argument("--stream-name")
    args = parser.parse_args()
    report = scan(args.capture, args.out, args.endpoint_reference,
                  args.credits_reference, args.stream_name)
    print(json.dumps({
        "report": str(args.out.resolve() / "landmarks.json"),
        "capture_unchanged": report["capture_unchanged"],
        "decoded_frames_scanned": report["decoded_frames_scanned"],
        "host_scan_seconds": report["host_scan_elapsed_ns"] / 1e9,
        "landmarks": {name: item.get("match") for name, item in report["landmarks"].items()},
    }))
    return 0 if report["all_landmarks_found"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
