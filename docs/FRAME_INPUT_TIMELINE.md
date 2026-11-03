# Automatic frame and input timeline

The native DOS frame timeline automatically records complete native saved states
and their completed-frame PNGs in a bounded live RAM cache. Native payloads are
retained in full by default; opt-in [lossless delta storage](FRAME_STATE_DELTAS.md)
retains keyframes and serialized-state differences. Both still perform a full
native capture at each point. An agent can return
through recent frames and try another input branch without naming a saved-state
artifact for every frame. A pinned point is an ordinary durable **Anchor Stone**.
This is separate from the selected CPU/RAM instruction deltas in
[delta rewind](CPU_RAM_DELTAS.md).

This first backend is real-mode DOSBox with the `frame_timeline` capability.
Windows/Wine, IDA, firmware and other native backends do not gain frame support
from this API. The experimental backend must be rebuilt separately; installing
the Python package does not rebuild or activate it.

## Execution modes

| Mode | Capture and navigation | Intended use |
| --- | --- | --- |
| Recording off | `advance_frames` and `frame_inputs`; no automatic full-state capture | Run a known input sequence with the smallest recording cost |
| Manual Anchor Stones | Explicit save/load at selected boundaries | Long-lived starting points and direct jumps |
| Automatic timeline | `timeline_start`, then `timeline_advance`; `timeline_rewind` selects recent frames | Short input searches and local retries |
| Combined | Pin a coarse Anchor Stone and retain a short automatic timeline near the interaction | Recovery outside the recent window plus inexpensive point selection inside it |

Recording and rewinding are separate costs. The timeline captures automatically
during `timeline_advance` even if no rewind follows. Full-state compression,
mounted-file checks and image capture still cost time. The live cache avoids
persisting every state/image in SQLite; pinning explicitly adds durable storage.

## Frame and input contract

A frame means one completed renderer frame followed by a safe stopped CPU
boundary. Its cadence depends on the guest video mode; it does not mean 1/60
second, one game logic update, or one CPU instruction. Native completion and the
stopped state are verified. An intervening breakpoint is not a completed frame.

Inputs are physical keyboard make/break edges delivered while stopped, before
the selected frame advances. They do not use the older guest-millisecond input
queue. A whole scheduled batch is validated against the current held-key set
before its first frame executes. Queue delivery still does not establish game
consumption or a successful game action.

Each batch contains at most 32 edges and must fit the hardware FIFO's reported
`frame_edge_capacity`. Capacity is checked while paused before input or cache
changes. A refused batch does not silently drop scan codes. PCjr machines refuse
the unsupported `f11`, `f12` and `kp5` keys; the ordinary VGA profile supports
physical keypad 5.

```python
debug.advance_frames(frames=1)  # Optional explicit alignment after a full load.
debug.timeline_start(max_frames=120, max_bytes=64 * 1024**2)
coarse = debug.timeline_pin('coarse-anchor.sav')  # Reuses the cached full state.
debug.timeline_advance(frames=8, inputs=[
    {'frame': 0, 'edges': [{'key': 'left', 'pressed': True}]},
    {'frame': 2, 'edges': [{'key': 'left', 'pressed': False}]},
])
debug.timeline_rewind(frames=4)
debug.timeline_advance(frames=4, inputs=[
    {'frame': 0, 'edges': [{'key': 'kp5', 'pressed': True}]},
    {'frame': 1, 'edges': [{'key': 'kp5', 'pressed': False}]},
])
image = debug.timeline_image('selected-frame.png')
```

`inputs[].frame` is a zero-based offset within that advance request, not an
absolute native renderer ID. Logical frame numbers follow the selected branch;
point and branch IDs distinguish different futures. Native renderer IDs remain
host-monotonic and are not used as rewind cursors.

`frame_inputs(edges)` also works independently. With recording active it journals
the edges and marks the current state dirty until the next completed-frame
capture. The cached point remains the state *before* these pending inputs.
`timeline_rewind(frames=0)` cancels such unadvanced inputs by restoring that point.
A dirty state cannot be pinned as if it were the cached full context. Its stored
image remains historical and is labeled accordingly.

Native saved states preserve keyboard FIFO, controller, repeat and modifier
state. Dedicated frame-held key names are retained as checkpoint metadata and
restored as ownership bookkeeping after loading the native hardware state;
loading must not synthesize new make events. Legacy timed events/leases,
held mouse buttons and pending mouse releases remain incompatible with timeline
capture. Native state files do not retain agent ownership of mouse buttons, so
manual capture also requires released buttons; loading an older held-button state
closes the session rather than exposing a button that cannot be released.
Keyboard reset in progress is also refused.

## Restoring or preserving RNG

An ordinary rewind loads the complete selected native point. For a declared
mixed-state experiment, an agent can preserve current conventional RAM ranges:

```python
debug.timeline_rewind(frames=3, policy={
    'name': 'preserve-observed-rng',
    'preserve_memory': [{'address': '0x0001A607', 'length': 2}],
    'allow_partial_resume': True,
})
```

That address is illustrative. The caller must identify the real runtime writer
and field; a policy name does not discover RNG. Full-state restoration covers
dynamically loaded DOS memory, so these explicit runtime ranges are not confined
to the original file-backed launcher mapping. Policies allow at most 64 disjoint
ranges totaling 64 KiB within conventional RAM below `0xA0000`.

Current values are read before loading the historical point, reapplied with
expected-byte hashes and read back. The result remains `resume_safe:false` and
records its policy, base point and preserved-byte hashes. Explicit
`allow_partial_resume:true` permits the experiment to continue; otherwise the
mixed state is frozen until a complete point or Anchor Stone is restored.
Provenance follows subsequent events, captures and derived Anchor Stones. A
fresh completed frame is required before pinning a newly mixed current state.

## Limits and recovery

The defaults retain 120 past frames, use a 64 MiB logical cache budget and allow
4,096 cumulative captures. Limits include checkpoint/image metadata and retained
input records. State/image reservations precede input and frame execution;
preflight capacity refusals preserve the last verified state and history. The maximum
advance request is 128 frames. A history permits at most 4,096 input edges.

Eviction removes only this live cache's oldest owned points. It does not delete
manual Anchor Stones or project artifacts. Logical byte counts do not include
Python allocator overhead, native emulator memory, temporary serialization or
decoded image working memory. State capture and operation deadlines have their
own limits; a timed-out or uncertain mutation closes the owned session.

Unrecorded execution, ordinary queued input, external restoration and other
unowned runtime changes invalidate the timeline before mutation. Active hooks,
layers, temporary spatial guards and unsupported CPU modes are refused. Mounted
files are hash-checked; full states do not roll back host files or external I/O.

The cache lasts only as long as its owning live session. `timeline_stop` releases
it. Project restart preserves pinned Anchor Stones and exported stored PNGs,
not a live emulator or its RAM history. A full load invalidates the native
framebuffer; `timeline_image` can still export a retained historical point's PNG
without advancing the guest or operating a GUI.

The same methods are available as `debug-timeline-*`, `debug-frame-advance` and
`debug-frame-inputs` JSON methods and their unprefixed declarative script names.
Malformed literal plans are rejected before earlier script steps execute.
If a route fails after delivering frame inputs or restoring newly held keys,
the owned session closes so those inputs cannot continue unexpectedly. Keys
already held on route entry retain their existing ownership. An uncertain
ownership readback after an attempted restoration also closes the session.

## Local comparison

`scripts/benchmark_frame_timeline.py` uses an authored DOS program, shared starting
states, equal frame/input plans and independent BIOS-input/RAM oracles. It
separately reports execution without recording, manual dense capture, automatic
capture, combined pinning, restores, native dispatches, caller operations and
retained payloads. Its raw project/state/image output belongs in a private
workspace outside Git. Perform the user-required storage admission before a run.
Original KQ1 rat experiments remain private, with sanitized results in the MR;
an authored benchmark alone does not qualify a real-game handoff or RNG policy.
