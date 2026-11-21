# Remaining native frame-control work

These are concrete implementation gaps after the retained-frame consumer and
source-step adapters. They do not change the parity definition or promote a
migration surface. The legacy renderer-source completion contract does not
require application drawing completion or atomic image/CPU equivalence.

## Keyboard repeat and native checkpoint phase

The native frame-key owner currently exposes `repeat-supported: false`.
`tests/test_qemu_frame_keys_native.py` explicitly excludes typematic behavior.
The existing DOSBox native case
`test_held_frame_keys_survive_native_anchor_restore_without_reinjection` in
`tests/test_frame_timeline_native.py` advances a held key for 48 frames, observes
repeated guest input, restores the held-key anchor, and reproduces the endpoint.

Implementing this behavior requires actual native keyboard repeat state and
timing, including continuity through the instrumented checkpoint path. Repeated
host make injection would bypass the held-key owner and would not preserve the
device's native repeat phase. The QEMU changes belong with the PS/2 device,
`system/fdisbull-frame-keys.c`, its QAPI receipt/checkpoint proof, and the native
frame-key patch; host `frame_inputs` remains the owner of explicit transitions.

## Useful stopped batch capacity

The existing QEMU helper `ps2_keyboard_frame_edge_capacity` reserves eight FIFO
bytes per edge and the supported quiescent profile advertises two edges.
Controller output, pending state, disabled scanning, command state, and throttle
state can reduce the capacity to zero. Its up-to-32-edge request grammar is not
a promise that a 32-edge batch is deliverable.

DOSBox's admitted key names reserve three bytes per edge from its actual FIFO.
The two implementations therefore have different useful chord capacity. A
future QEMU increment can compute an exact conservative reservation for the
admitted QCodes and translation/scancode state, validate the whole batch before
delivery, and preserve zero partial dispatch on refusal. Required witnesses
include a supported multi-modifier chord, extended keys, insufficient capacity,
and command/controller-state interference. Splitting a requested atomic batch
across guest execution would change its semantics.

The relevant existing sources are
`native/qemu-frame-keys/qemu-10.0.13-fdisbull-frame-keys-v1.patch`,
`src/fdisbull/qemu_frame_keys.py`, and the host/native frame-key suites.

## Source-raster checkpoint and timeline state

`native/qemu-video-frame` deliberately keeps its partial rows, completed source
raster, stream metadata and timer deadline outside native checkpoint state.
Save leaves the current live stream intact; load invalidates it, and a new
process starts idle. The current source fence is also never serialized.

Existing renderer timelines retain full process checkpoints and renderer PNGs.
They cannot supply an immediate restored source-raster receipt or restore the
source stream's future sampling phase. A source-backed timeline needs an
explicit native checkpoint design for this state, fresh-lifetime identity
binding, and host history admission/readback. Cached renderer pixels must not
be relabeled as a restored source stream.

Keep the retained artifact's historical identity separate from any new current
owner identity. A bounded acceptance increment should prove immediate restored
pixels, a partially sampled raster's future completion, and held-key ownership
without reinjection before connecting broader timeline operations.

## Sampling remains profile-specific

The recorded [Native07 paired result](DOS_QEMU_PAIRED_SOURCE_FRAME_PLAN.md)
matched all quiet authored rasters, then distinguished the fixed dynamic phase
families: DOSBox phase 1 and QEMU phase 0. Both counterphases and the final-palette
image were rejected. `backend_source_phase_equal=false` and
`exact_dynamic_image_equivalence_claim=false` remain explicit.

Source stepping controls the existing QEMU sampling profile. Resolving wider
mode, palette/origin, runtime-profile and cross-backend sampling obligations is
separate from exposing that working control through the legacy route.
