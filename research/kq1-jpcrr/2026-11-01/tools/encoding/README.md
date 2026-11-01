# Native JPC-RR capture, decoded and presented at 1×

`jmd_capture.py` reads the standard JPC-RR `JPCRRMULTIDUMP` format directly. It preserves the capture clock as integer nanoseconds, validates every video payload, exports native RGB PNGs, and can produce a silent variable-frame-rate MP4. The MP4 uses the captured clock rather than the host time taken to emulate, collect, decode, or encode frames.

The native reference control in this directory reaches the final King's Quest credits. It is DrD2k9's reference movie with the explicitly declared original BIOS variant used by the parent experiment. It is not the newly authored Robb-route candidate. Its ordinary keyboard events include BOW; that technique is already present in this control.

## Run

Dependencies are Python 3, Pillow, `ffmpeg` with `libx264`, and `ffprobe`.

```bash
python3 jmd_capture.py /absolute/path/to/closed-capture.jmd \
  --out /absolute/path/to/new-output-directory \
  --video playback-1x.mp4 \
  --end-ns 22000000000 \
  --select-ns 13900000000
```

The output directory must be new or empty. The tool refuses to overwrite an existing MP4. Close the native dumper before reading its output; the input's size and SHA-256 must remain unchanged through decoding.

By default, every native video event is exported. `--export-every 10` exports every tenth event; `--export-every 0` exports only repeated `--select-ns` requests. Every payload is still validated. A selection chooses the closest captured timestamp, with the earlier frame breaking ties, and records the actual timestamp and difference. `--stream-name` is required if multiple named video streams exist.

`--start-ns` and `--end-ns` crop only the presentation video; the complete capture remains in `index.json`. The default start is the first captured video event. A crop carries the latest captured image at or before its start. Requesting a start before the first capture fails: the tool does not fabricate an unobserved video lead. `--end-ns` may hold the final image after the native data ends, but `encoding.json` labels that duration explicitly.

`--canvas WIDTHxHEIGHT` optionally chooses an even-sized MP4 canvas. Native PNGs retain their original size. The presentation uses nearest-neighbor resizing with aspect-preserving letterboxing; this does not affect timestamps.

## Files and timing contract

| File | What it establishes |
| --- | --- |
| `index.json` | Original file hash, stream chapters, packet counts, every video packet's byte offset, native timestamp and dimensions, decoded RGBx/RGB hashes, selected PNG hashes. |
| `frames/` | All or selected native RGB frames. The original nanoseconds are in the index. |
| `presentation.ffconcat` | Explicit per-image durations generated from native timestamps. |
| `encoding.json` | Exact presentation schedule, crop, resolution transforms, tail hold, quantization, synthetic endpoint, encoding command and verification result. |
| `ffprobe.json` | Independent FFmpeg measurements of all encoded frame timestamps and durations. |
| `reference-samples/landmarks.json` | Visually inspected reference landmarks and their immediate predecessors, plus independently parsed reference movie input times. |
| `reference-samples/landmarks-contact.png` | Unscaled native frames with external labels for independent visual review. |

The MP4 timebase is one microsecond. Each absolute native offset is rounded to the nearest microsecond before durations are calculated as differences; no repeated rounding of frame durations accumulates drift. Every encoded frame timestamp and duration must match `ffprobe` exactly at that timebase. The native timing uncertainty introduced by presentation is at most 500 nanoseconds per displayed frame. If two native states quantize to the same microsecond, the latest state is shown and the dropped presentation entry is listed; all native packets remain in the index.

A final duplicate image lasting one microsecond is explicitly marked **synthetic**. It exists to give the preceding real frame its requested duration in the MP4 container. It is not another native render or additional gameplay. Any hold after the last captured video frame and any extension beyond the final JMD timestamp are separately reported.

Audio packets are counted but are not decoded or rendered. The MP4 is explicitly silent. H.264 uses CRF 0, but YUV 4:2:0 color conversion means it is not a pixel-exact RGB archival image; the native PNGs are the RGB evidence.

### Native empty events

The real stock capture begins with zero-area video events. The stock stream tools also handle these as empty/blank video. A zero-area native event has no legal PNG dimensions, so its exported file is an explicitly labeled **1×1 black placeholder**, with `empty_native_video_event` and `png_qualification` in the index. The presentation uses a blank canvas for the event. No dimensions or pixels are attributed to an original image that did not exist.

## Reference control results

The complete native source was 9,785,709 bytes with SHA-256 `3cce89f97ad0177b4411d1a9bb5e6f3b5212bda26affa4ec262e9097af7ef62f`. It contains 1,539 video events. The stock replay receipt records 38.437206116 seconds of host time for process launch through exit, including JVM, emulation, capture and teardown. That host duration is a separate measurement from the game's clock and from the MP4's playback duration.

The first captured event is at 0.015 seconds, the last video event is at 21.992631500 seconds, and the final native timestamp is 22 seconds. The reference MP4 therefore presents 0.015–22.000 seconds at 1×, lasting **21.985001 seconds** including its labeled one-microsecond endpoint duplicate. It holds the last image for 7.3685 milliseconds through the requested stop, and does not extend beyond the last native JMD timestamp. All 1,540 encoded sample timestamps/durations passed `ffprobe` comparison. Maximum native-to-MP4 timestamp quantization error is 500 nanoseconds.

| Reference landmark | Zero-based native frame | Native time | Immediately preceding frame |
| --- | ---: | ---: | --- |
| First complete scene 1: castle, score 0, Graham, parser prompt | 205 | 2.973223357 s | 204 at 2.958955233 s is still the partial title card. |
| First complete “You move aside” modal | 977 | 13.988214419 s | 976 at 13.973946296 s still shows the BOW acknowledgement. |
| Last movie keyboard event | — | 14.294723718 s | Independently summed relative JRSR event deltas; keyboard scan code 28. |
| First complete final credits modal | 1004 | 14.373453744 s | 1003 at 14.359185621 s contains only the partially drawn beginning of the message. |

The complete final credits are visible 78.730026 milliseconds after the last keyboard event. The interval from the first complete scene-1 image to the complete final credits image is 11.400230387 seconds. This is a **display-to-display interval**, not a declaration of a speedrun timing convention. The first directional input was already scheduled at 2.901904314 seconds, before the first complete scene-1 capture; display capture alone cannot establish the exact earlier control-ready instant. No timing for our authored candidate is inferred from this control.

## Format provenance and verification

This is an independent Python implementation based on the bundled stock JPC-RR source contracts:

- `src/streamtools/new-jpcrr-dumpformat`: chapter/stream layout, big-endian fields, shared relative nanosecond timestamps, variable payload lengths and video subtypes.
- `src/streamtools/newpacket.cpp`: chapter continuity and time-skip behavior.
- `src/org/jpc/output/OutputFrameImage.java`: zlib RGBx byte layout and native dimensions.
- `src/streamtools/packet-processor.cpp`: handling of empty video frames.

`provenance.json` records the source paths and hashes, decoder/test hashes, native source and replay receipt hashes, generated evidence hashes, and local Python/Pillow/FFmpeg versions. It does not copy a guest binary or save state into the deliverable.

Run the focused checks with:

```bash
python3 test_jmd_capture.py
```

The six tests cover raw and compressed RGBx (including ignored x bytes), zero-area events, chapter continuity, audio advancing the shared clock, the specified two-byte variable-length example, time skips, ambiguous streams, invalid/truncated container data, bounded malformed zlib payloads, crop/quantization edge cases, and a real FFmpeg/ffprobe VFR round trip with resolution changes. The tests reject unsupported video subtypes and excessive allocation sizes. This is not a general-purpose fuzzer or a certification of every possible JMD producer.

`reference-format-check/index.json` is an additional decode of the real reference after the final parser changes, without PNG exports. Its complete native frame sequence and decoded RGB hashes were compared with the initial reference output. The final checks are recorded in `validation.txt` and `provenance.json`.
