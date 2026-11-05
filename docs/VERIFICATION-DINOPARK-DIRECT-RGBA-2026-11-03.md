# Direct RGBA consumption — original DinoPark, November 3, 2026

The Python debugger now provides `frame_rgba(encoding="rgba-zstd")`, returning
an in-memory `RGBAFrame` without PNG conversion or artifact persistence. This
closes the conversion boundary identified in the
[earlier native codec experiment](VERIFICATION-DINOPARK-SCREENSHOT-CODECS-2026-11-03.md).
The existing `screenshot()` API still produces persistent PNG artifacts.

## Direct consumer contract

The default request uses native raw RGBA8 plus Zstandard. The consumer validates
the compressed-payload hash, dimensions, stride, declared decompressed size,
Zstandard frame bounds, trailing data and decoded-pixel hash. Its immutable
`pixels` bytes can be consumed through `memoryview` or `pixel(x, y)`; no image
encoder or decoder is involved on the Zstandard path. Frame/mode/tick metadata
is retained, and compressed-payload provenance remains separate from the raw
pixel identity.

```python
frame = debug.frame_rgba()
assert frame.metadata["pixel_format"] == "RGBA8"
rgba = frame.pixel(160, 100)
buffer = memoryview(frame.pixels)
width, height, stride = frame.width, frame.height, frame.stride
```

`frame.sha256` and `frame.metadata["sha256"]` identify the decoded RGBA bytes.
`frame.metadata["transport"]["sha256"]` identifies the native compressed payload.
The call does not run screenshot hooks, store events/artifacts, pause or advance
the guest, or bypass the normal debugger RPC guards. Comparing one completed
frame across calls requires an owned, paused guest.

`encoding="png"` and `encoding="png-indexed"` provide the same direct RGBA result
after decoding their native PNG, without re-encoding or database persistence.
The PNG option supports older backends; the default Zstandard option requires
its advertised codec and the existing optional Python decoder. The direct API
is a Python buffer consumer, not a JSON reply embedding all pixel bytes.
See the [usage contract](DOSBOX_DEBUGGER.md#direct-rgba-consumer-without-png-conversion).

## Original-game verification by Luna

Luna (`gpt-6-luna`) extended the retained benchmark and ran one fresh original
DinoPark guest through four paused-frame cases: opening black, logo, detailed
title menu, and a later title animation after 60,000 requested guest ms. Each
case used three warmups and **30 measured calls per encoding**, with shuffled
codec order. This produced **360 timed direct-consumer calls**, another **360
timed wire-only calls**, and **60 stored screenshot calls** for comparison.
No keyboard or mouse input, purchases, saves, restores or action replays were
sent. The old research guests were not resumed.

All direct outputs matched the paused original-game PNG reference in every
RGBA byte. Native RGB probes independently agreed. Registers, frame ID, mode
and captured guest ticks remained identical during each same-frame comparison.
Guards around the direct phase observed:

- Zero image-save calls for all three encodings.
- Zero image-open calls for raw RGBA + Zstandard; PNG paths opened their native
  PNG once per call as expected.
- Zero screenshot-hook, event or artifact calls.
- Zero SQLite write attempts, with unchanged event/artifact counts and
  `total_changes` before and after each direct phase.

The actual native spawn had SDL dummy audio, `mixer nosound=true` and
`midi mididevice=none`. The original private game-file inventory was unchanged,
and the owned backend was cleanly reaped with exit code zero. This is debugger
shutdown evidence, not a natural game-completion claim.

## Measured speed and remaining limit

The detailed title cases avoid an aggregate dominated by the blank opening
frame. All numbers below are full-call wall times in milliseconds, median
(p95), on this Mac. Direct calls include native RPC, integrity validation and
pixel decode; stored calls additionally include the PNG compatibility/artifact
path. Each direct cell has 30 measured calls; each stored cell has five.

| Consumer | Title at 15,000 requested guest ms | Title at 60,000 requested guest ms |
| --- | ---: | ---: |
| Direct RGBA from native PNG | 3.681 (3.864) | 3.742 (4.008) |
| Direct RGBA from indexed PNG | 3.400 (3.633) | 3.126 (3.551) |
| Direct RGBA from Zstandard | 3.865 (4.260) | 4.039 (4.279) |
| Zstandard through stored PNG | 5.970 (6.831) | 6.327 (7.632) |

The direct Zstandard consumer lowers the measured median by about **35–36%**
against the existing Zstandard-to-stored-PNG API on these title frames. This
comparison removes both PNG conversion and persistence; it does not isolate
the encoding cost alone. Storage calls were measured in successive groups,
whereas direct codec order was randomized. These are bounded observations,
not a general throughput guarantee. Direct timings include the narrow guard
instrumentation; its small host overhead was not subtracted.

Direct indexed PNG remained faster than direct Zstandard in both detailed
cases. Native Zstandard encoding was faster, but the complete protocol still
has frame acquisition, full-buffer hashing, base64/JSON transfer and host
validation/decompression costs. This experiment does not isolate their
individual latency shares or show that raw transport is the fastest choice.
No integrity check was removed to improve the timings.

## Source identity and regression checks

No backend rebuild was needed. Before the run, the coordinating agent rehashed
the private native backend, and Luna recorded the same identity:

- Native macOS ARM64 backend SHA-256:
  `c88248913d582f95ddf1f4ca8aea1ef977f1029c5cb1bf6538cb8fbc4fdd7734`.
- Complete layers patch SHA-256:
  `78c6dde366d10194135360ef7a1b54e5c56b24f723244b1cb511870948fcb754`.
- Original `DINOPARK.EXE` SHA-256:
  `2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`.
- Measured benchmark script SHA-256:
  `34b7dc8670eb3df68c1c5d89939606ffd80c8dff2dd2fcedb78c6ec7b1ad0707`.
- Measured client-source bundle SHA-256:
  `612e582a69b5e9883d57a8326f8f238df6cf45d80121ade3695d8f08755b0465`.
- Private report SHA-256:
  `25d8faed99e4218b2238b720a706561c3def94635eba17f3212cbe9fc336fb33`.

All 375 recorded Python source hashes were unchanged across the original-game
run and independently matched the coordinating agent's final readback. The
production decoder/API was frozen before the run; it is the same code covered
by the final regression checks, not a later unmeasured compatibility fix.

The focused suite passes **38 codec checks** with the actual native backend.
The affected suite passes **426 tests in 28.37 seconds**, covering debugger,
screenshot grids/hooks, capture contracts, scenes, timeline, native ZIP streams
and all DinoPark tests. Tests forbid PNG loading/saving and persistence on the
raw direct path, check real native frame identity and zero database changes,
and apply malformed layout/hash/Zstandard cases to both consumer paths. RGB,
RGBA and indexed PNG inputs are also decoded without re-encoding. Pixel access
checks reject invalid coordinates.

```sh
FDISBULL_DOSBOX=/private/build/src/dosbox-x \
PYTHONPATH=src:player python -m pytest -q tests/test_screenshot_codecs.py

PYTHONPATH=src:player python scripts/benchmark_dos_screenshot_codecs.py \
  --executable /private/build/src/dosbox-x \
  --game-dir /private/original-game-copy \
  --output /private/new-direct-rgba-trial \
  --native-patch experimental/dosbox-x/layers/headless-agent.patch \
  --iterations 30 --guest-ms 60000 --frames 4
```

## Handoff and scope

The direct API is suitable for callers that consume pixel buffers and do not
need an automatic persistent PNG. Callers needing durable screenshots continue
to use `screenshot()`. Direct consumer, raw RPC, codec-only timing and persisted
artifact timing must remain separate when comparing performance.

The original-game run covers sampled 320×200 startup/title frames on this
macOS ARM64 backend. Other gameplay scenes, resolutions, targets and platforms
are not qualified by this measurement. The remaining DinoPark 97-entry and
13-asset research inventory is unchanged. The earlier codec source replay and
fallback-fixture evidence retain their separate scope.

Private evidence is under `/Volumes/CACHE/fDisBull-direct-rgba-20261103/`:
`luna-run-01/report.json`, `PARENT-VERIFICATION.json`, `SOURCE-FROZEN.json`,
`NATIVE.log` and `REGRESSION.log`. Frames, target objects, FDB and full inventories
stay private. Only authored code, checks and sanitized methodology are included
in the source contribution. No package, release or installation was made.
