# QEMU retained-frame compatibility contract

The native QEMU backends provide `frame_probe` and `frame_rgba` over an explicitly
retained source raster. The selected profile admits standard 320 × 200 chain-4,
the Mode 13h timing models, unchained page-latched VGA, or 640 × 480 planar VGA
and banked VBE scanout.
Inspect `frame_contract` and `frame_contract_profile` before using these operations.
The producer must support the source-raster and virtual-clock extensions, the VM
must use the explicit virtual/precise profiles, and the cooperating owner must
have its bound protocol authority.

This adapter provides the existing pixel-consumer shapes. It preserves an
explicit QEMU source profile and clock. It does not promote
`completed_guest_frames`, change the default backend, or qualify additional
video modes, scene readiness, pointer mapping, sampling-phase equivalence, or atomic
frame/CPU state. Existing `screenshot()` / `capture_surface()` continue to observe
the stopped display surface; `capture_video_frame()` is the source-raster
artifact route.

## Using the frame consumers

The caller explicitly starts the source stream and chooses bounded execution
until a complete raster exists. The frame consumers never start, restart,
advance, repair, or fall back to another stream or backend.

A correlated native start refusal keeps the session available when readback
confirms the same native stream and stopped clock. The error carries
`verified_refusal: true` in its video-frame evidence. An uncertain start or
changed readback still closes the captured owner. This lets callers continue
with renderer capture or process checkpoints when the guest uses an
unsupported source layout.

```python
assert debug.capabilities['frame_contract']
debug.video_frame_start()
advance = debug.video_frame_advance(timeout_ms=5000, stop_on_hook=True)
if advance['advance_completed']:
    before = debug.status()
    samples = debug.frame_probe([[0, 0], [319, 199], [0, 0]])
    rgba = debug.frame_rgba(encoding='png-indexed')
    after = debug.status()
    assert before['state_revision'] == samples['state_revision']
    assert samples['state_revision'] == rgba.metadata['state_revision']
    assert rgba.metadata['state_revision'] == after['state_revision']
    image = debug.capture_video_frame('retained-source.png')
else:
    interrupted = advance['native_result']
```

`frame_probe(points, *, timeout_ms=1000)` accepts zero through 4096 integer
coordinates inside the source extent. It returns `format='rgb-samples'` and
ordered `{'x': x, 'y': y, 'rgb': [r, g, b]}` samples, preserving duplicates.
An empty probe returns identity metadata without a native pixel-probe call.
The native per-call limit remains 256 points, so a full public request makes
at most sixteen bounded native probes under one owner lock and host deadline.
One successful call publishes one `frame-probe` event. It creates no image
artifact and includes no encoded image payload.

`frame_rgba(*, encoding='rgba-zstd', timeout_ms=1000)` returns the existing
`RGBAFrame` object with RGBA8 pixels, opaque alpha and a packed stride of four
bytes per pixel. The artifact carries 256,000 bytes at 320 × 200 or 1,228,800
bytes at 640 × 480. It performs encoding and decoding through the selected
host codec. Direct reads invoke no screenshot hooks and publish no event or
artifact. The lower-level `video_frame_rgba()` continues to convert the native
RGB export directly without an intermediate PNG or Zstandard encoding.

The existing JSON `debug-frame-probe` and script `frame-probe` routes support
the QEMU contract. Script literals and capabilities validate before earlier
steps can take effect; resolved points validate again before dispatch. Use
`debug-capture-video-frame` / script `capture-video-frame` for an artifact.
The byte-containing `RGBAFrame` remains a Python interface.

A small local `call()` facade supports `session.status`, `video.probe`,
`video.screenshot`, and the separately gated `frame.step` below. The screenshot route returns the encoded payload expected
by the shared screenshot decoders. It does not forward arbitrary DOSBox RPCs
to QEMU. An optional supplied `session_id` must match the current owner.

### Retained-read admission

Each retained probe, RGBA read, local screenshot call and source-frame artifact
capture retains its original owner before its existing initial stopped-clock
context. When the original pipe monitor advertises
`x-fdisbull-take-pending-events`, one bounded matching-response event batch is
taken after that context succeeds. Its original events are fully validated and
delivered through the existing event handler before one explicit admission
freezes the cooperative revision. Admission itself adds no native request.
Missing-command and other transport paths add no speculative cut query.
An event or cooperating effect delivered before that boundary can become part
of the new baseline only while the original owner, resources, configuration and
session lifetime remain unchanged. Every covered effect after admission still
invalidates the read, including unknown or same-valued events and same-byte
bound memory writes. The reader never filters events, drains after the matching
reply, retries or repairs the stream. Later bytes remain buffered for their
proper next operation. Delivery time does not establish when a device generated
an event. The batch does not establish an event-free stream, complete history or
device-cause order. See [QEMU_PENDING_EVENTS.md](QEMU_PENDING_EVENTS.md) for its
bounds and status sequencing. Durable frame keys, including an attached
controller with no held keys, do not alone make the native cut ineligible; the
cut never queries, releases, detaches, or mutates those keys.

The returned revision and mode projection use the captured original authority.
The scope retains its original cleanup resources through the outer operation's
deadline restoration and lock release. A late timeout or replacement refuses
success, preserves arrived evidence and closes only the captured resources;
later cleanup does not adopt a replacement authority or channel. Missing-raster
and unsupported-codec refusals with an otherwise healthy owner remain reusable.
The conservative `ObservationAuthority` keeps its separate strict lease rules.

An earlier caller's status remains separate evidence. A newly admitted frame
can succeed at a later revision while `capture_frame_state` correctly refuses
the caller's earlier bracket. No prior status is rewritten to match the read.
The source-step helper retains its existing owner and execution contract.

Missing, invalidated, or stale source rasters fail without implicit execution.
Stopping a healthy source stream retains its last complete raster. A change in
display layout invalidates the stream and requires explicit restart and execution.
The unchained latch profile retains the active raster across programmed page
starts and CPU plane selection. Completed or cancelled input schedules do not
prevent frame reads. The adapter does not call the separate selected-state
observer and does not require initial neutral keyboard/scheduler state.

## Advance the existing source stream

Inspect `capabilities['frame_step']` before using source-backed legacy frame
controls. It requires the retained-frame contract and the native source-frame
fence. It does not require a checkpoint tool or renderer timeline. The source
stream must be explicitly started and still observing; its first complete
raster need not exist yet.

```python
assert debug.capabilities['frame_step']
debug.video_frame_start()
step = debug.call('frame.step', {'timeout_ms': 5000})
if step['completed']:
    assert step['stop_reason']['kind'] == 'frame'
    assert debug.frame_probe([])['frame_identity'] == step['frame_identity']
else:
    actual_stop = step['native_advance']['native_result']

batch = debug.advance_frames(frames=2, timeout_ms=10000)
if batch['outcome'] != 'completed':
    actual_stop = batch['stop']
    completed_prefix = batch['frames']
```

`frame_step(*, timeout_ms=5000)` invokes the existing `video_frame_advance`
controller once, with stop-on-hook enabled. A successful result has
`format='fdisbull-qemu-frame-step-1'`, `completed=True`, a stopped state, and a
frame stop reason. `native_advance` retains the complete original controller
result, including its actual debugger result, arm, observed and released fence,
row witnesses, source identities, and clock brackets. The adapter adds no
second event or image artifact to the controller's existing intent/result
events.

Raster acceptance and stop attribution remain separate. A competing breakpoint
can leave an accepted raster while `completed=False`; that breakpoint's actual
stop reason remains visible. If the attempt accepted no raster, its projected
`frame_id`, `mode_id`, and `frame_identity` are `None`, even when an older image
remains cached in the full source evidence. A proven exit of the original,
reaped owner has no fabricated post-exit frame, clock, or protocol query.

Successful step identity agrees with subsequent passive probe/RGBA reads. Its
session revision is sampled after the effectful execution. `captured_ticks`
remains the accepted raster time; `guest_ticks` is the actual stopped virtual
time in milliseconds, with `guest_ticks_clock='QEMU_CLOCK_VIRTUAL_milliseconds'`.
Neither is relabeled as DOSBox PIC ticks.

Arming preserves partial source rows and their original deadlines.
`baseline_rows_sampled` reports the pre-arm count; a next accepted raster may
contain rows sampled before an input edge or step request. An owned safe stop
does not establish application drawing completion or atomic image/CPU state.
The paired Native07 evidence still distinguishes DOSBox phase 1 from the
default QEMU phase 0 for its authored dynamic raster. The opt-in
`dosbox-mode13` model retains its first/steady phase from observed guest
programming and uses format 5 for checkpoint restore. Its scope is the
qualified standard BIOS programming and exact mode geometry. Native paired
measurements cover the authored text-to-Mode 13h transition and two steady
palette pulses. See the [paired timing diagnostics](DOS_QEMU_VGA_STEADY_PHASE_DIAGNOSTIC.md)
and the [native mode timing profile](../native/qemu-video-mode13-phase/README.md).

The explicit `dosbox-mode13-overlap` profile adds the same-mode BIOS reapply
sequence. The older stream retires at reapply. Start the new source stream
before the next raster boundary to capture the overlapping callbacks. Format 7
preserves both pending deadlines and the partial raster through restore.
[Paired Mode 13h overlap evidence](DOS_QEMU_VGA_STEADY_PHASE_DIAGNOSTIC.md#paired-mode-13h-reapply-and-format-7-restore)

The explicit `vga-640x480` source profile samples one physical row at a time
in standard planar Mode 12h and banked VBE 101h. Select it with
`qemu_video_source_profile="vga-640x480"` for native DOS debug launch or
`video_source_profile="vga-640x480"` on the machine API. Both routes require
the virtual clock, precise VGA instrumentation and a matching native QEMU.
The source reports its `scanout-layout` as `vga-mode12` or `vbe-banked-101`.
Format 8 preserves the last complete 640 × 480 RGB raster, the partial next
raster, and its deadline independently. Banked VBE source capture uses its
own timing model while the legacy VGA retrace observer reports `vbe-enabled`.
A source stream belongs to one layout. Start a new stream after a mode change.

Select `vga-640x480-sync` to also model the guest’s port 03DAh status in the
admitted banked VBE 101h layout. Bit 0 follows display blanking and bit 3 marks
vertical sync. Retrace observation, waits and retrace-scheduled input use that
same sync interval. The native receipt includes `vbe101-timing` alongside
the inherited VGA timing registers. This profile uses format 9 checkpoints.

Select `vga-640x480-flip` with an explicit QEMU firmware directory containing
`fdisbull-vgabios-vbe101-flip.bin` to enable retrace-synchronized display
starts for banked VBE 101h. The runtime loads a verified private copy of that
ROM. The retrace receipt reports the programmed and active byte origins in
`vbe101-display-start`. A scheduled change also reports its next retrace
deadline. Format 10 checkpoints preserve the device's display start and
deadline even with source capture idle. Each completed banked raster reports
its own sampled origin, which can precede the currently active page.

Select `vga-640x480-pan` to add horizontal panning in banked VBE 101h. This
profile uses the same VGA ROM and supports byte pitches from 640 through 8184
in increments of eight. The coarse origin latches at line 490 and the fine
horizontal offset at line 492. Format 11 checkpoints preserve both pending
deadlines and the active viewport, including a stop between the two latches.
Each completed banked raster retains the sampled pitch, coarse byte origin
and fine offset. A pitch change retires the source stream.

Select `vga-640x480-xy` with `fdisbull-vgabios-vbe101-xy.bin` in the explicit
firmware directory to submit X and Y together through VBE function `4F07h`.
This profile checks the whole pair before either coordinate is programmed.
A rejected pair leaves the active viewport and any previously queued change
intact. The accepted pair keeps the separate coarse and fine latch times.
Format 12 checkpoints preserve both latches with the same raster metadata
used by the panning profile.

Select `vga-640x480-palette` with `fdisbull-vgabios-vbe101-palette.bin`
to add banked VBE stride queries and setters, six- and eight-bit DAC
selection, and immediate and retrace-timed palette transfers. Format 13
restores BIOS execution while a palette transfer waits for a fresh
retrace edge. It also restores the DAC width, stored palette and partial
raster after the transfer. A stride or DAC-width change invalidates the
current stream. Palette data writes leave both the sampled prefix and
the previous complete frame intact.

To save a script with literal coordinates outside the standard 320 × 200
source, give the script an explicit `qemu-machine` or `qemu-dos` backend and
the selected `video_source_profile`. The script must match the owner's launch
profile when it runs. A running session also checks each resolved probe against
the selected source extent.

`advance_frames(frames=1, timeout_ms=10000)` on a machine context accepts 1..128
frames under one outer deadline and original VM/channel lifetime. DOS process
sessions retain their existing 60000 ms default; an explicit `timeout_ms`
always intersects tighter session, script, machine, and channel deadlines.
Each completed entry contains the full single-step result. The first earlier
stop returns `outcome='interrupted'`, the successful `completed_frames` prefix,
the actual `stop`, and `interrupted_frame`; it never continues to make up the
requested count. Failure evidence retains the successful prefix and any nested
controller evidence, without replay. An owner replacement is not executed or
closed as though it were the original machine.

JSON `debug-frame-advance` and script `frame-advance` select this source unit
when `frame_step` is advertised. Literal and capability preflight occurs before
earlier script effects; resolved parameters validate before timeout clamping.
An interrupted script retains the result and stops before the next step. An
absent, stopped, or invalidated source stream does not trigger renderer fallback,
stream repair, or implicit restart.

The separately exposed `timeline_*` APIs keep their renderer-publication and
checkpoint-storage semantics. Older QEMU DOS profiles without `frame_step`
retain their existing renderer `advance_frames` behavior when that capability
is available. Source frame advancement does not add source-raster checkpoint
serialization, typematic repeat, or the raw legacy frame-edge RPC; existing
`frame_inputs` and its JSON/script routes retain their owned native semantics.
See [remaining native frame-control work](QEMU_FRAME_CONTROL_GAPS.md).

## Identity, generation, and clocks

The DOSBox `last_completed_guest_frame` contract represents an accepted complete
renderer source-cache raster. It does not prove that an application completed
its drawing. The QEMU producer similarly supplies a complete retained source
raster, sampled on its declared row schedule. Its different producer identity
and timing remain visible.

| Field | QEMU meaning |
| --- | --- |
| `source` | `qemu_completed_source_raster` |
| `frame_profile` | The selected native model, including `qemu-vga-chain4-scanline-v1`, `qemu-vga-chain4-dosbox-mode13-v1`, `qemu-vga-chain4-dosbox-mode13-overlap-v1`, `qemu-vga-unchained-320x200-latch-v1`, `qemu-vga-640x480-scanline-v1`, `qemu-vga-640x480-sync-v1`, `qemu-vga-640x480-flip-v1`, `qemu-vga-640x480-pan-v1`, `qemu-vga-640x480-xy-v1`, and `qemu-vga-640x480-palette-v1` |
| `scanout_layout` | `vga-mode12` or `vbe-banked-101` for the 640 × 480 source model |
| `vbe101_origin_bytes` | The coarse byte origin sampled in a completed banked VBE 101h raster under the flip, panning and X/Y profiles |
| `vbe101_pitch_bytes`, `vbe101_pel` | The backing row pitch and fine horizontal offset sampled under the panning and X/Y profiles. The first pixel uses the coarse origin plus the fine offset |
| `source_bpp` | **24**, the native producer's RGB888 source bytes |
| `double_width`, `double_height` | Both false. Coordinates use the retained source extent |
| `frame_id` | Native accepted raster ordinal, including identical consecutive pixels |
| `mode_id` | Monotonic session-local projection of the complete source-generation key |
| `captured_ns` | Native `completed-ns`, on `QEMU_CLOCK_VIRTUAL` |
| `captured_ticks` | `captured_ns // 1_000_000` |
| `captured_ticks_clock` | `QEMU_CLOCK_VIRTUAL_milliseconds`; never DOSBox PIC ticks |
| `session_id` | Fresh identity for the current owned VM lifetime |
| `state_revision` | Current cooperating session-control revision at observation time |

The full `frame_identity` retains the owner lifetime, native epoch, host clock
epoch, stream token, stream generation, configuration generation, timing
generation, native frame ordinal, runtime epoch, and checkpoint epoch. A mode
ID is neither a BIOS video-mode number nor a hash of the pixels. A stream
restart changes its generation even if the next raster has identical pixels.
A new VM, including a cold checkpoint replacement, has a new session identity;
the surrounding project run may remain the same.

`state_revision_scope='cooperative-session-control-v1'` distinguishes the public
counter from the strict observer's conservative `control_generation`. The latter
continues to invalidate on every admitted public operation, including reads.
The public counter stays stable for passive status, source probe, and codec
reads, and for bounded successful GDB register/memory reads. It advances before
effectful public controls and bound QMP/GDB dispatches, including same-byte RAM
or register writes, execution, queued input, source-stream controls, and layer
changes. Transport replacement/closure and observed QMP events also invalidate
the prior public revision. Known read commands are recognized by concrete
schemas and bounded selectors; unknown commands are treated conservatively.

Host-only changes also participate: hook configuration, spatial policy,
history-control admissions, and reconciliation of a newly dispatched native
input prefix. Refreshing an unchanged schedule receipt stays passive. A bounded
GDB memory read temporarily selecting and restoring `PhyMemMode` stays passive;
failure to restore closes the bound channel and advances the revision.

The counter records admissions and control changes, not a count of modified
bytes. One composed operation can advance it more than once. A rejected or
uncertain effect can invalidate a prior receipt. Raw file descriptors,
independent controllers, native device changes, and unobserved guest execution
are outside this cooperative contract. Both `native_state_revision` and
`whole_machine_state_revision` remain `None`.

A retained raster can precede a later control change. Reading it after a RAM
write returns the current session revision with the same retained raster
identity. This does not claim that its pixels depict the current CPU/RAM state.

## Codec negotiation and hashes

The nested `capabilities['video']` on the session and its RPC owner identifies
`codec_origin='host-adapter'`, the source profile, and available
`screenshot_encodings`. PNG and exact indexed PNG are available for the admitted
profile. `rgba-zstd` is advertised only when the optional host `zstandard`
dependency imports successfully. A missing or unadvertised requested codec
fails before native I/O.

| Requested encoding | Actual encoded payload |
| --- | --- |
| `png` | RGBA PNG |
| `png-indexed` | Exact palette PNG for at most 256 RGB colors; RGBA PNG with `fallback_reason='more_than_256_colors'` otherwise |
| `rgba-zstd` | Zstandard-compressed RGBA8 with declared content size, exact stride, and raw-pixel hash |

Indexed PNG never quantizes or merges colors. `requested_encoding` records the
request; `encoding` records what was actually produced. The shared screenshot
decoder validates payload hashes, layout, encoded dimensions, Zstandard bounds,
and canonical pixel identity.

The direct RGBA object's `sha256` hashes the packed RGBA bytes of the selected extent.
`transport` describes the selected host codec and its encoded-byte hash;
`native_transport` preserves the underlying P6/RGB888 export identity. The
native `pixel_sha256` still hashes the 192,000 RGB source bytes. Stored PNG
artifacts hash the stored encoding. These values are not interchangeable.

## Generic frame/state brackets

`capture_frame_state(controller, debug.capture_video_frame)` can use the local
status/probe facade. It requires stopped status with matching session/revision,
the explicit QEMU source/profile/layout/clock, and identical full source
identity across the probe/capture brackets. A custom status reader must retain
those QEMU fields as well. A freshness wait cannot cross source generations
even if a caller supplies a misleading unchanged integer mode ID.

The resulting receipt remains `atomic=False` with
`frame_state_equivalence=None`. The bracket verifies the supplied observations
and their control identity; it does not establish native authenticity or
application readiness. DOSBox continues to use its existing raw
`session.status` RPC when available, its original source label, and its existing
validation behavior.

## Qualification boundary

The admission scope reconstructed after the interrupted workspace is new
source. Historical qualification of unavailable earlier files does not qualify
this reconstruction; it requires fresh host results and a separate native
witness on the exact resulting source and producer.

The focused host tests exercise the public facade through real QMP/GDB client
framing against deterministic protocol peers, actual Pillow/Zstandard codecs,
real project events/artifacts, scheduler reconciliation, and generic coherence.
Those tests do not execute a guest or prove a native renderer phase. The new
native acceptance witness must be run separately with a frozen host source,
exact producer/runtime pins, an authored raster fixture, and a bounded fresh
owner/output plan. A paired DOSBox/QEMU receipt is still required for any
cross-backend pixel/codec acceptance claim.

This implementation adds a working scoped adapter. It does not close the
broader migration promotion ledger. Wider mode capture, automatic capture
lifecycle across mode/reset/load transitions, existing scene signatures with
different source depths, and downstream pointer/action/history requirements
retain their own implementation and native acceptance gates.
