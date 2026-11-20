# Opt-in native source-row video stream

This increment samples an admitted standard VGA chain-4 320 × 200 source
raster row by row using the existing native precise timing model. It owns
completed source RGB pixels independently of the synchronous QEMU renderer.
The existing display, renderer fence, and raster-proof APIs retain their prior
meaning and color conversion. No frame control or DOSBox equivalence is claimed.

## Frozen QMP v1 interface

- `x-fdisbull-start-video-frame {token}`
- `x-fdisbull-query-video-frame {}`
- `x-fdisbull-stop-video-frame {token}`
- `x-fdisbull-export-video-frame {token, frame-id, filename}`
- `x-fdisbull-probe-video-frame {token, frame-id, points:[{x,y}]}`

Start itself is the opt-in; there is no new launch property. The existing
explicit virtual clock and precise retrace profile, exactly one realized
primary VGA, and owned synchronous headless console zero/head zero are required.
Every public command requires the supported stopped clock, with no armed/fired
clock budget or checkpoint transaction. Start schedules future sampling and
never advances the guest. Query never renders, hashes, samples, creates a file,
changes a timer, or repairs an empty/invalidated stream. Probe reads at most 256
ordered points from one exact retained frame; duplicate and empty points work.
Export creates a new private P6 RGB file with `O_EXCL`; existing paths are refused.

All commands except probe return `FdisbullVideoFrameInfo`. Probe returns
`{info: FdisbullVideoFrameInfo, pixels:[{x,y,r,g,b}]}`.

| Info field | Meaning |
| --- | --- |
| `api-version`, `model` | `1`, `qemu-vga-chain4-scanline-v1` |
| `state` | `idle`, `observing`, `stopped`, or `invalidated` |
| `epoch`, `virtual-ns` | Current stopped native clock identity/time |
| `stream-generation` | Process-local start generation, initially zero |
| `frame-sequence` | Process-local accepted complete-raster count; never reset by start/stop/load |
| `aborted-frames` | Number of discarded partial rasters that had sampled at least one row |
| `in-progress`, `rows-sampled` | Whether a partial raster has rows, and its 0..199 row count |
| `token`, `device` | Present after start; caller token and canonical device path |
| `start-ns` | Present after start; its actual stopped native time |
| `stop-ns` | Present only when state is `stopped` |
| `next-deadline-ns` | Next intended row deadline, only while observing |
| `reason` | Present on invalidation; no retained frame survives invalidation |
| `frame` | Present only when a complete owned source raster is retained |

The frozen frame contains `frame-id`, `stream-generation`, producing `epoch`,
`configuration-generation`, `timing-generation`, `width=320`, `height=200`,
`stride=960`, `pixel-format=RGB888`, `dac-conversion=replicate-6-to-8-v1`,
`dac-8bit`, `frame-start-ns`, `period-ns`, `line-period-ns`, `first-sample-ns`,
`last-sample-ns`, `completed-ns`, `pixel-sha256`, and exactly 200
`rows:[{row,intended-ns,actual-ns}]`. First/last sample times are actual times;
completion occurs immediately after sampling row 199. Accepted identical rasters
still advance `frame-sequence` and get a new `frame-id`.

## Sampling and colors

For the existing precise model let `H = ticks_per_char * htotal` and
`P = ticks_per_char * total_chars`. Start chooses the first phase-zero boundary
`B = (start_ns // P + 1) * P`, strictly after the start time. Source row `r`
samples at intended time `B + floor(H/4) + 2*r*H`, for `r=0..199`. Future
rasters use `B + k*P`. The model must have at least 400 physical lines. These
are native model periods, not a wall-clock or physical VGA timing claim.

Each callback copies that source row from the current admitted VRAM and expands
it using the then-current raw DAC. Six-bit channels explicitly use
`(v << 2) | (v >> 4)` after masking to six bits; eight-bit channels are unchanged.
Thus DAC 1/21/42 becomes RGB 4/85/170. This adapter follows the pinned DOSBox
source convention and intentionally differs from the existing QEMU renderer's
`c6_to_8` values 7/87/168. It never changes QEMU's palette, renderer cache, or
existing raster proof. A later palette write cannot recolor an earlier sampled
row in this stream. A full render at the end of a period is not used.

The selected phase is explicit. DOSBox's carried `render_step` phase, blanking,
and timing arithmetic can differ; per-line paired evidence remains required
before claiming legacy frame equivalence. Stable-source equality does not close
that sampling qualification.

## Invalidation and recovery

Every effective selected VGA configuration change, including timing/configuration
A→B→A, invalidates both partial and current completed pixels. Unsupported source
geometry, device/clock ownership loss, reset, load, deadline overflow, and a row
callback at least one physical line late do the same. A callback never catches
up missing rows with present-day VRAM. A callback pending behind a real stop is
deferred by one native nanosecond; the same lateness bound still applies on resume.

Stopping discards a partial raster and retains the last completed one, which
can still be probed/exported with its token and ID. An invalidated query returns
its token/reason with no frame as long as the underlying stopped clock remains
valid. A native reset that invalidates the base clock is refused by that clock
guard. Start can replace a stopped or invalidated stream once source admission
holds again; it needs a token different from the preceding stream and increments
`stream-generation`. It clears old completed pixels. Sequence counters do not
wrap; overflow refuses/invalidate rather than manufacturing an identity.

Stream buffers and metadata are process-local and not checkpoint state. Native
load invalidates them; a replacement process starts idle. Saved renderer pixels
or update counters cannot resurrect this stream. Generic migration is blocked by
the existing precise retrace owner admitted explicitly at stream start. The
instrumented checkpoint route retains that owner's existing behavior but does
not serialize this stream's in-progress or completed raster. An instrumented
save preserves the current process's live stream and intended timer deadline;
loading that save still invalidates the stream rather than restoring it.

## Scope and verification

The finite eight-case native source-row gate passed at integrated host commit
`eb0e8753dc3df0aac8bdef929a9cc69884186bcd`, using QEMU SHA-256
`253830eeedb2608da7b09a9527692332266488bd4abfef37a239c011e59dd592`.
See [the recorded native gate](../../docs/QEMU_VIDEO_FRAME_GATE.md) for the
independent oracles, preserved initial setup failure, exact producer/input
identities, process ownership and remaining limitations. This does not qualify
later producers, source-frame control or legacy sampling equivalence.

The stream admits the same bounded chain-4 address interpretation as the earlier
source proof: origin/bank zero, pitch 320, exact 320 × 200 source, no panning or
visible split, legacy graphics and VBE disabled. Admission reads freshly derived
parameters, never a stale `s->params` renderer cache. Per-row configuration/timing
identity is checked before any row can contribute to a completed raster.

Storage is bounded to two 192,000-byte RGB buffers plus fixed 200-row timing
arrays and one bounded frozen receipt. Probe output is bounded to 256 points;
export is exactly the P6 header plus one 192,000-byte RGB raster. No new timer
exists until explicit start. Source-only helper tests exercise exact extracted
code; native integration, host consumers and paired legacy evidence are separate
gates. The recorded eight-case gate establishes the declared native source-row
behavior on its pinned profile; later consumers and legacy equivalence remain
separate acceptance work.

The initial source-only checks passed 39 tests from
`tests/test_qemu_video_frame_source.py`. They compile the exact hash-checked
pure header extracted from the patch with `-Wall -Wextra -Werror`, and check
declared arithmetic vectors, refusal bounds, DAC conversion, and complete owned
row bytes. The full combined QAPI schema also passed the pinned QEMU parser
with `doc-required: true`. The manifest records the tested helper hash and each
check's patch identity; subsequent documentation changes did not alter that
helper. These checks do not compile the complete native module.

Sampling overhead is unmeasured. The initial implementation validates each row
through the existing configuration/retrace snapshots, including their bounded
QAPI allocations. The authored native cases met the declared row deadlines;
they are not a performance benchmark or a completed-guest-frame qualification.
