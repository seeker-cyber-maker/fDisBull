# Audit a recorded TAS or analysis route

`capture-audit` verifies finalized AVI recordings without launching, attaching
to, or advancing an emulator. It decodes and hashes **every recorded frame**,
then optionally exports every Nth frame and a self-contained inspection page.
Agents can use the compact result as a gate before analyzing recorded pixels.

This implements the offline capture stage of the
[TAS analysis harness](TAS_ANALYSIS_HARNESS.md). It does not replay inputs,
certify game completion, or map video time to guest ticks. The separate native
snapshot correction still requires rebuilt-backend acceptance.

## Run it

The optional external readers `ffmpeg` and `ffprobe` must be installed and on
PATH, or supplied through their named options. Their paths and reported versions
are retained. No reader is downloaded or installed automatically.

Finalize and close the recording first. Use a **new output directory beneath
an existing private directory outside Git**, following the same output rules
as other source-retaining fDisBull exports. Recordings and exported images may
contain original game content and stay in that private workspace.

```sh
fdisbull capture-audit /private/run/mode-0.avi /private/run/mode-1.avi \
  --output /private/run/frame-audit --every 4 --html
```

`--every 1` exports all decoded frames. `--every 4` exports frames 0, 4, 8, …;
their original zero-based indices remain in every record. The default,
`--every 0`, hashes all frames and exports no PNGs. HTML requires a positive
sampling interval. Sampling changes exported inspection material; the complete
RGBA hash sequence is computed in every case. Duplicate frames remain in that
sequence and its frame count.

The inspection page shows exact recorded timestamp fractions, source frame
indices and hashes. Its 0.1×, 0.25×, 0.5× and 1× controls change browser playback
of the exported sample. They cannot affect the already finalized run.

## Agent API and failure handling

The same operation is available without a project through Python:

```python
from fdisbull.capture_audit import audit_capture

receipt = audit_capture(
    ["/private/run/mode-0.avi", "/private/run/mode-1.avi"],
    "/private/run/frame-audit",
    every=4,
    html=True,
)
if not receipt["ok"]:
    raise RuntimeError(f"Capture failed verification; inspect {receipt['summary']}")
# Only now use the verified segment records as pixel-analysis inputs.
```

Or through the existing JSON protocol:

```json
{
  "method": "capture-audit",
  "params": {
    "inputs": ["/private/run/mode-0.avi"],
    "output": "/private/run/frame-audit",
    "every": 4,
    "html": true
  }
}
```

Check **`result.ok`** in the JSON protocol. The outer `ok` means dispatch
completed and can still wrap a failed audit receipt. Direct `capture-audit`
CLI execution exits nonzero for a failed audit, including when the normal
output-budget mechanism returns a reference to the full result.

Validation errors such as a reused destination, invalid options or missing
reader fail before the audit starts. Once admitted, each segment receives an
explicit `verified` or `failed` result; ordinary missing/truncated/corrupt-input
failures retain diagnostics and allow the other supplied segments to be checked.
A late requested-export failure also makes the audit fail. Partial frame records
and images from a failed segment remain diagnostics, not accepted evidence.

The output path must be fresh. Existing evidence is never overwritten. Disk or
permission failures can prevent writing a final receipt; the API then raises an
error and the CLI reports failure. A directory's existence is not proof of success.

## Evidence layout

| File | Meaning |
| --- | --- |
| `summary.json` | Full result, input order, tool identity, module hash, budgets and each segment's status |
| `segment-NNN/result.json` | Segment outcome, input hash, stream metadata, decode counts and limitations |
| `segment-NNN/riff.json` | AVI container boundary checks and declared video headers |
| `segment-NNN/ffprobe.json` | Bounded reader metadata and frame records |
| `segment-NNN/frames.jsonl` | One record for every decoded frame, including its exact video time and RGBA hash |
| `segment-NNN/png/frame-NNNNNNNN.png` | Requested sample; filename retains the source frame index |
| `segment-NNN/inspection.html` | Optional self-contained page for slower sampled-frame review |
| `segment-NNN/ffprobe.stderr.txt`, `ffmpeg.stderr.txt` | Retained reader diagnostics |

The compact return value identifies `summary.json` by path and SHA-256. It also
contains per-segment outcomes/counts, the RGBA sequence hash and failure reasons,
without returning images or thousands of frame records inline.

The sequence hash is SHA-256 over the concatenation of the 32-byte SHA-256 digest
of every decoded RGBA frame in order. It therefore retains duplicates and frame
ordering. It is distinct from the compressed AVI file hash and sampled PNG hashes.

## What the audit checks

The reader first validates RIFF/LIST boundaries, rejects unfinalized/truncated
chunks, and requires one video-stream header. `ffprobe` reads frame metadata;
a separate strict `ffmpeg` decode must produce exactly the reported number of
complete RGBA frames. Reported frame counts, fixed segment dimensions, positive
timebase and strictly increasing timestamps must agree. Decoder error output
causes failure even if a tool could salvage part of the recording.
The audit covers the selected video stream. Audio streams are not decoded or
validated by this operation.

The input's size, modification time and SHA-256 are compared before and after
inspection. Concurrently changing recordings are unsupported. This check detects
observed input changes; it is not an atomic snapshot or a filesystem lock.

Every timestamp record identifies whether it came from `pts` or a decoder
`best_effort_timestamp`. A fallback does not manufacture a source PTS:
`source_pts` is null for that case, and `source_timestamp_field` identifies it.
Fractions preserve the recorded timebase without rounding everything to a
borrowed game/movie frame rate.

## Limits and timing claims

Defaults are intended for short analysis routes:

| Budget | Default | Scope |
| --- | ---: | --- |
| Input segments | At most 16 | One operation |
| Input bytes | 512 MiB | Per segment |
| Decoded frames | 10,000 | Per segment |
| RGBA frame bytes | 16 MiB | Per frame |
| Reader metadata | 32 MiB | Per probe result |
| Audit output | 512 MiB | All segments, including requested exports |
| Reader time | 120 host seconds | Per external-reader process |
| Self-contained viewer estimate | 64 MiB maximum | Per HTML page; also fits the remaining output budget |

The Python API accepts explicit budgets; the CLI exposes matching options.
`--audit-output-bytes` governs retained files, separately from the global
`--max-output-bytes` JSON-reply limit. One MiB of the audit file budget is reserved
for failure/final receipts. Decoder stderr is capped at 64 KiB. These are reader
and artifact budgets, not an operating-system sandbox or a hard aggregate RSS cap
for the external codec. Tool availability and supported codec variants depend on
the recorded external reader versions.

Each input retains its own dimensions, starting timestamp and timebase. Input
argument order is not an inferred continuous timeline. Checkpoint restores and
mode changes require separate provenance. The audit leaves **guest ticks and
input-to-frame alignment unknown**.

A successful audit establishes consistency of the finalized recorded stream.
It does not establish that the emulator recorded every guest scanout, that an
input was delivered at a particular guest time, that a scene condition held,
or that a whole-game TAS finished. Those claims need their corresponding native
observations and completion checks.

## Use it in a harness

After the route's owner finalizes recording, call `capture-audit` and retain its
compact receipt alongside the route's checkpoint, input script and state/effect
receipts. Reject failed segments before vision or scene analysis. Analysis
workers may inspect the completed files in parallel without controlling the
guest. A semantic checker can then compare qualified state/output observations
against retained IR and named UIL/UDL interactions; pixels alone do not replace
those semantic conditions.

Authored regression tests use six exact solid-color ZMBV frames, including two
duplicate pairs. They check all-frame hashes under different sampling intervals,
independent mode/timebase segments, real corrupt/truncated inputs, byte/time
budgets, late export/source-change failures, and CLI/JSON result handling.
