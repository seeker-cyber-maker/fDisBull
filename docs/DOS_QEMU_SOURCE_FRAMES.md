# Completed VGA source rasters

Native QEMU machine and DOS sessions expose a separate, explicit source-raster
stream for the admitted chain-4 320 × 200 VGA profile. Inspect
`video_frame_capture` before starting it and `video_frame_control` before
requesting its next accepted raster. Both require the prepared native extensions
and explicit virtual-clock and precise-retrace profiles.

The stream samples source rows on its declared native schedule and converts
six-bit DAC components using `(value << 2) | (value >> 4)`. A completed source
raster can contain changes made during its sampling interval. Completion does
not establish application drawing completion, input consumption, DOSBox sampling
phase equivalence or atomic correspondence with the current CPU state. Existing
renderer publications, legacy `frame_probe`, frame timelines and scene/pointer
contracts retain their separate capabilities.

## Select and inspect a completed source raster

Starting or stopping the stream does not execute the guest. The caller chooses
when to execute. A source-frame advance requires an already observing stream
and targets exactly the next accepted source raster, including a raster whose
earlier rows were sampled before the request.

```python
started = debug.video_frame_start()
advance = debug.video_frame_advance(timeout_ms=5000, stop_on_hook=True)
if advance['advance_completed']:
    seen = debug.video_frame_observe()
    identity = {'stream': seen['stream'], 'frame_id': seen['frame_id']}
    samples = debug.video_frame_probe([[0, 0], [319, 199], [0, 0]], **identity)
    rgba = debug.video_frame_rgba(**identity)
    image = debug.capture_video_frame('source.png', **identity)
    debug.video_frame_stop()
else:
    # Inspect this stop and its evidence before choosing further execution.
    interrupted = advance['native_result']
```

The optional `stream` and `frame_id` guards must be supplied together. They
select the currently retained raster; stale identities refuse before a native
pixel probe or file export. A query cannot create a missing completed raster.
Stopping the stream retains its last completed raster. Restarting or restoring
a machine requires a fresh stream identity.

`video_frame_probe` accepts a list of zero through 4096 source coordinates.
Each coordinate is an integer in the 320 × 200 source extent. Results preserve
caller order and duplicates in `samples`, with each item shaped as
`{'x': x, 'y': y, 'rgb': [r, g, b]}`. An empty list selects and validates a
completed raster and returns metadata with no native pixel calls.

An aggregate probe holds one machine lock and one absolute deadline, including
admission and all native replies. It makes at most sixteen calls of 256 points
each. Every source receipt has a 128 KiB QMP wire-message limit. All chunk
identities must agree exactly; duplicate coordinates must agree across the
entire aggregate and with retained sparse/full-image evidence. A contradictory,
late or incomplete aggregate publishes no successful prefix. Received chunks
remain in bounded failure evidence and the original uncertain owner is closed.
The persistent sparse cache retains at most 256 coordinates and the optional
full RGB cache retains one 192,000-byte raster.

## In-memory RGBA and saved PNG

`video_frame_rgba(*, stream=None, frame_id=None, timeout_ms=1000)` is a Python-only
operation returning `screenshot_codecs.RGBAFrame`. Its immutable `pixels` value
contains 256,000 row-major RGBA8 bytes, width 320, height 200, stride 1280 and
alpha 255. `pixel(x, y)` reads a four-component tuple. Metadata is a detached
copy containing the exact native frame/stream receipts and stopped clock bracket.
Mutating that metadata does not alter the retained native identity or pixels.

RGBA observation and PNG capture share the same native RGB export validation:
one non-following file descriptor, exact regular-file type and P6 byte count,
the native RGB hash, prior sparse-pixel consistency and a stopped owner/clock
check. The bounded temporary P6 file is removed after reading. RGBA observation
does not encode PNG, invoke screenshot hooks, publish a screenshot artifact or
write an observation event.

Hash meanings remain explicit:

| Value | Bytes hashed |
| --- | --- |
| Native `frame['pixel-sha256']` and host `pixel_sha256` | The 192,000 RGB source bytes |
| `RGBAFrame.sha256`, RGBA metadata `sha256` and `raw_sha256` | The 256,000 RGBA bytes |
| RGBA `transport['sha256']` | The exact temporary P6 header plus RGB bytes |
| PNG artifact metadata `sha256` | The stored PNG encoding |

`capture_video_frame` keeps its existing artifact dictionary and accepts
`max_bytes` for the encoded PNG. Exceeding that image budget refuses before
artifact publication. It does not change the meaning of the native RGB hash.

## JSON and saved-script routes

These routes require the `qemu-machine` or `qemu-dos` backend. Their result
dictionaries use the same source envelopes as Python. Normal tool output
limits still apply: a large successful probe or failure receipt may be
delivered through `fdisbull-output-ref-1`. Read the retained output instead of
repeating the operation.

| Python method | JSON method | Script operation | Result |
| --- | --- | --- | --- |
| `video_frame_start` | `debug-video-frame-start` | `video-frame-start` | `fdisbull-video-frame-stream-1` dictionary |
| `video_frame_observe` | `debug-video-frame-observe` | `video-frame-observe` | `fdisbull-video-frame-stream-1` dictionary |
| `video_frame_stop` | `debug-video-frame-stop` | `video-frame-stop` | `fdisbull-video-frame-stream-1` dictionary |
| `video_frame_probe` | `debug-video-frame-probe` | `video-frame-probe` | `fdisbull-video-frame-probe-1` dictionary |
| `capture_video_frame` | `debug-capture-video-frame` | `capture-video-frame` | Screenshot artifact dictionary |
| `video_frame_advance` | `debug-video-frame-advance` | `video-frame-advance` | `fdisbull-video-frame-advance-1` dictionary |

JSON methods require the usual `project` and `run` selection. The first five
operations default to a 1000 ms host deadline; advance defaults to 5000 ms.
Script steps retain the result dictionary in `steps[index]['result']` and
intersect each operation's deadline with the route's remaining allowance.
All visible literals, signatures, capabilities and transaction restrictions
are validated across the whole route before an earlier step can mutate the
machine. Result references are validated again after resolution and before
timeout clamping or native dispatch.

A script stops if `video-frame-advance` returns `advance_completed=False`,
retaining the actual native stop and accepted-raster evidence. A raster may
have completed while an earlier user breakpoint owns the stop; that does not
permit the next script step to run. The public Python/JSON advance result
retains this distinction for the caller to inspect.

`video_frame_rgba` has no JSON method or script operation. Its byte-containing
Python object is not implicitly serialized or stored as an artifact. The
typed CPU/image observation authority and a legacy frame-coherence bridge
remain separate work; these methods do not invent PIC ticks or a guest-state
mutation revision.

## Qualification checkpoint

At clean host `59fa4b4e5fcc29d222330103064fc214f38545de`, the focused host
selection completed with **284 passed, one skipped, zero failures or errors**
in 5.33 seconds (5.797 seconds including the owned worker). All 5,671 tracked
file hashes stayed unchanged and the worker group/leader were reaped without
adopted children. The skip is the existing legacy direct RGBA codec witness
requiring the absent optional `zstandard` dependency; it is not a source-RGBA
pass. Every new consumer/public-route case executed and passed.

The selection comprises the source consumer, source public routes, source
frame, source control, renderer public probe and QEMU I/O deadline modules,
plus two explicitly named direct RGBA/PNG codec nodes. It excludes that codec
module's compiled and native fixtures. Exact receipt SHA-256:
`4099c7681e19e8072e4aa3dd8e5a8c1a20f325c1c3d9698ddb5c45d7b4169cba`.

Earlier attempts are preserved. One bootstrap failed before creating a test
worker. The first execution stopped at 30 passed/one failed because an oracle
compared separate passive clock observation sequences; the corrected test
compares each route with its actual delegated Python result and independently
checks stable guest clocks. The next stopped at 63 passed/one failed because
an oracle required exactly 50 ms despite conservative integer-millisecond
script clamping; it now checks the inherited 49..50 ms ceiling and consumed
30 ms prefix. A third execution reached the controller's 128 MiB aggregate
output cap before JUnit completion; its private per-test database fixtures
were retained. A separately admitted unchanged selection completed within a
256 MiB cap, using 154,685,387 bytes. No earlier incomplete prefix is counted
as a completed test run.

The underlying [native capture](QEMU_VIDEO_FRAME_GATE.md) and
[native frame-control](QEMU_VIDEO_FRAME_FENCE_GATE.md) gates passed separately.
The broadened 4,096-point/RGBA/JSON/script consumers still require their own
finite native witness on that producer. Host transport tests do not establish
guest scanout cadence, legacy phase identity, or whole-debugger parity.
