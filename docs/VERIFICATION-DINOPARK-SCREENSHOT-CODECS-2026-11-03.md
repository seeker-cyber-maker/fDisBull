# Native lossless screenshot encodings — DinoPark, November 3, 2026

The native screenshot path now offers exact indexed PNG and optional raw RGBA8
with Zstandard level 1. Both are explicit selections; the original PNG remains
the default. Luna (`gpt-6-luna`) authored and ran the independent original-game
benchmark. The coordinating agent reviewed the source, built the private native
backend, ran regression checks, and independently inspected the resulting receipts.

## Implementation and identities

- Upstream DOSBox-X baseline: `029bd65c5dcc7cdc7f2e14e35278620d9707d969`.
- Qualified private macOS ARM64 layers backend SHA-256:
  `c88248913d582f95ddf1f4ca8aea1ef977f1029c5cb1bf6538cb8fbc4fdd7734`.
- Layers patch SHA-256:
  `78c6dde366d10194135360ef7a1b54e5c56b24f723244b1cb511870948fcb754`.
- Stable patch SHA-256:
  `e9f25b293d9c9368d2ad7d734fed1606b73a1d5e50eff3d86aa1545366a23691`.
- Original `DINOPARK.EXE`: 268,480 bytes; SHA-256
  `2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`.

Both complete patches replay cleanly onto their pinned baseline. All **37 stable
and 38 layers** resulting source-file hashes match their manifests; all 38
selected native build files also match the layers manifest. The layers backend
was built privately in 125.5 seconds using the existing host toolchain. The
stable profile has compiled encoder checks and exact source replay; it was not
separately built as a complete emulator in this experiment. No Linux or Windows
runtime qualification is claimed.

Indexed PNG builds a bounded, exact palette from the current completed RGBA
snapshot. It performs no quantization. A frame exceeding 256 colours, or with
nonopaque pixels, falls back to the existing RGBA PNG with a reason. Palette
contents are not reused across frames. The benchmark includes this actual
palette-construction cost; it does not assume a prepared index buffer.

Zstandard is optional at native configure time and advertised only when built.
The raw response includes encoded and decoded-pixel hashes, an exact RGBA8
layout and the existing frame/mode/tick identity. The optional Python decoder
checks frame bounds, content size, trailing data and both hashes. For existing
artifact consumers it then writes PNG, preserving native transport provenance
separately from the stored PNG's hash. See the
[API contract](DOSBOX_DEBUGGER.md#optional-lossless-native-screenshot-encodings).

## Original-game batch and detailed title result

The first finite original-game batch reached three distinct 320×200 frames by
bounded idle execution: a one-colour opening frame, a 26-colour logo frame and
the detailed 153-colour title menu. It sent no keys, mouse events, purchases,
saves, restores or action replays. It used **30 measured calls per encoding per
frame**, after three warmups, with shuffled encoding order. Five separate stored
artifact calls per encoding/frame measured the compatibility path.

Every decoded RGBA buffer matched the same paused frame byte for byte. Native
RGB probes independently matched the screenshot samples. Registers, frame ID,
mode ID and captured guest ticks remained identical through each same-frame
batch. All 45 canonical PNG artifacts had identical pixels, correct artifact
hashes and frame metadata; nine exports were reopened and verified. Both the
actual dummy audio driver and mixer/MIDI mute arguments were checked. The
private game-file inventory was unchanged, and the owned native process was
reaped with exit code zero.

A second fresh guest passed four distinct cases, including title captures at
15,000 and 60,000 requested cumulative guest milliseconds. Across both runs,
there are **630 measured native responses**, **105 stored screenshot calls**
and **21 reopened exports**. Each run independently verified sound-off settings,
unchanged files, pixel equality, paused-state neutrality and process shutdown.
The two initial blank frames are not counted as evidence of detailed-scene
compression performance.

The following medians are from the detailed title menu, rather than an aggregate
dominated by the blank opening frame:

| Encoding | Native payload bytes | Base64 characters | Native encoder ms | Screenshot RPC ms | Stored screenshot ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original RGBA PNG | 33,186 | 44,248 | 0.996 | 2.958 | 4.236 |
| Exact indexed PNG | 21,348 | 28,464 | 1.055 | 2.503 | 2.953 |
| Raw RGBA + Zstandard | 31,373 | 41,832 | 0.440 | 3.654 | 6.889 |

The title's indexed PNG is **35.7% smaller**, with a **15.4% lower RPC median**
and **30.3% lower stored-screenshot median** in this sample. Its encoder itself
is slightly slower because it constructs the palette. Zstandard's native
compression is faster, but its RPC is **23.5% slower** and its stored-screenshot
call **62.6% slower** here. The host-generated PNG after raw transport is
63,350 bytes, versus the native original PNG's 33,186 bytes.

Native `encode_us` excludes frame acquisition, hashes, base64, JSON and IPC.
RPC timing includes those native response costs; stored-screenshot timing also
includes validation, host conversion where needed, and database persistence.
Raw replies hash the complete RGBA buffer as well as the encoded bytes, and
the compatibility path additionally re-encodes PNG. Those are known extra
operations; this experiment does not isolate their individual latency shares.
The five artifact calls per case provide a bounded observation, not a general
throughput or latency guarantee.

The second guest's first detailed title frame repeated the direction of the
initial result: original/indexed payloads were **33,340 / 21,486 bytes**, RPC
medians **3.010 / 2.529 ms**, and stored-screenshot medians **3.960 / 2.899 ms**.
At the later 60,000-ms title sample, original/indexed payloads were
**32,528 / 20,950 bytes** and RPC medians **2.919 / 2.577 ms**. Its stored calls
were **3.844 / 3.997 ms**: indexed PNG was slightly slower for that small sample.
Raw Zstandard remained slower for RPC and stored calls on both detailed cases.
Thus the observed payload/RPC benefit is consistent on these title frames;
stored-artifact latency is variable. Persistence timing was collected in five
successive calls per codec, not a randomized storage experiment.

## Regression and reproduction

The new codec suite passes **21 tests** with the actual candidate backend.
The native integration test fails against the earlier installed backend at the
missing `png-indexed` capability, demonstrating that it distinguishes the new
path. Compiled checks use the actual encoder code from both complete patches,
with and without Zstandard enabled. They cover one colour, exactly 256 colours,
257-colour fallback, alpha preservation, palette refresh and invalid frame sizes.
Decoder checks cover malformed layout, dimensions, payload and pixel hashes,
unknown or wrong decompressed size, trailing data and absent optional support.
The real native test verifies all advertised codecs, invalid requests, preserved
registers and frame identity, stored artifacts, and export after project restart.

The final affected suite passes **409 tests in 31.01 seconds** with the native
backend: codecs, debugger, screenshot grid/hooks, compiled capture contracts,
scenes, timeline, native ZIP streams and all DinoPark tests. The first broader
run found one regression (407 passed, one failed): default PNG preflight
unnecessarily required an RPC capability object even when an adapter overrode
capture. The fix keeps capability negotiation exclusive to alternate encodings;
the entire affected suite was rerun successfully. Luna's final review also
identified invalid-encoding validation on an adapter without an RPC handle;
safe capability lookup and a public-adapter regression check close that edge.
The native backend and codec implementation used for Luna's measured frames
did not change.

The measured benchmark scripts are recorded separately from the final source:
run 2 used script SHA-256
`c5d9edb1ff8685a3234ffcf08dade36a8602e5c0ca2f50e13a381aa18f0aee42`;
the final script is
`6e744b7a51e5757986b96d52d18a60dad134590f62bd8b6e45cc3057c41e70de`.
After measurement, its pass gate was tightened to require the requested frame
count and a report key was renamed to clarify total requested guest time. The
two retained runs met their requested counts already; their original receipts
were not rewritten. Client preflight was adjusted as described above and then
checked in the final native regression suite. The original-game measurements
remain bound to their recorded client bundle, rather than a claim that the
complete final source was rerun against the original.

Luna's private report field `native_patch_sha256` identifies the **incremental
server delta**, not a complete backend patch. The complete patch identities
and all-source build verification at the start of this document are the native
reproduction authority.

```sh
FDISBULL_DOSBOX=/private/build/src/dosbox-x \
PYTHONPATH=src:player python -m pytest -q tests/test_screenshot_codecs.py

PYTHONPATH=src:player python scripts/benchmark_dos_screenshot_codecs.py \
  --executable /private/build/src/dosbox-x \
  --game-dir /private/original-game-copy \
  --output /private/new-codec-trial \
  --native-patch experimental/dosbox-x/layers/headless-agent.patch \
  --iterations 30 --guest-ms 15000 --frames 3
```

Select admitted private external paths and retain original game files outside
Git. The benchmark refuses an existing output directory and records its own
limits, exact inputs, comparisons and shutdown. The Python Zstandard module
must already be available. This work does not install dependencies or change
the active fDisBull installation.

## Findings for the next owner

- Exact indexed PNG is the useful opt-in for these original-game frames. Keep
  the default PNG and the exact fallback until broader modes and gameplay
  scenes are qualified. The lower wire payload/RPC cost does not guarantee a
  faster database-backed screenshot call.
- Raw Zstandard is a working lossless transport experiment, not a demonstrated
  end-to-end acceleration. A future raw-native consumer could avoid host PNG
  conversion; its benefit needs a separate measurement. Do not remove integrity
  checks to reproduce the isolated encoder speed.
- Report native compression, whole RPC and stored-artifact time separately.
  Include per-frame content and size: blank frames can make aggregate codec
  comparisons misleading. The prior offline codec timings did not include
  this native protocol or persistence path.
- The initial benchmark needed compatibility handling for PNG replies that
  omit an explicit `encoding`, distinct-content checks rather than only frame
  counters, independent native RGB probes, and shutdown evidence on failure.
  These are included in the retained source script. Requested frame counts
  must be satisfied explicitly; fewer distinct frames leave a failed trial.

Private receipts are under
`/Volumes/CACHE/fDisBull-native-screenshot-codecs-20261103/`: `BUILD-RESULT.json`,
`SOURCE-REPLAY.json`, `CODECS-NATIVE.log`, `REGRESSION-REVIEWED.log`, `PARENT-ORIGINAL-VERIFICATION.json`,
`luna-run-01/report.json` and `luna-run-02/report.json`.
The original frames, FDB, target objects and full file inventories stay private.
The source contribution contains authored code, tests and sanitized methodology.
No package, release, installation, hosted pipeline or merge was performed.
