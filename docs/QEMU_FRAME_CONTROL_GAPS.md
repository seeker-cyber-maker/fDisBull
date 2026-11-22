# Remaining native frame-control work

These are concrete implementation and qualification gaps after the retained-frame
consumer and source-step adapters, updated for the 2026-11-22 continuation.
They do not change the parity definition or promote a
migration surface. The legacy renderer-source completion contract does not
require application drawing completion or atomic image/CPU equivalence.

## Keyboard repeat and native checkpoint phase

The [native key repeat extension](DOS_QEMU_MIGRATION.md#native-key-repeat)
uses the PS/2 rate parameter and QEMU virtual time for eligible frame-owned
keys. Instrumented format 4 captures the exact deadline while retaining the
source-raster and device ownership state. The base frame-key producer still
reports `repeat-supported: false`.

The DOSBox native case
`test_held_frame_keys_survive_native_anchor_restore_without_reinjection`
continues to provide a comparison target for broader guest-visible repeat
qualification, including game-level behavior and input during device congestion.

## Useful stopped batch capacity

The original QEMU helper `ps2_keyboard_frame_edge_capacity` reserves eight FIFO
bytes per edge and its supported quiescent profile advertises two edges.
Controller output, pending state, disabled scanning, command state, and throttle
state can reduce the capacity to zero. Its up-to-32-edge request grammar is not
a promise that a 32-edge batch is deliverable.

The reconstructed [frame-key batch extension](QEMU_FRAME_KEY_BATCH_GATE.md)
adds exact native planning for the admitted QCodes and current translation and
scan-code state. It validates the complete request before delivery and reports
the actual post-enqueue proof. Its native witness accepted Ctrl/Alt/A/Up in one
five-byte batch, preserved that queue through a fresh-owner checkpoint restore,
and reproduced the independently checked IRQ stream. A separate capacity case
accepted Shift/A/B and retained stale/foreign-owner refusal checks.

These results close that bounded implementation increment. Broader scan-code
profiles, Print/Pause/right modifiers and controller-state combinations still
need their own native evidence. DOSBox's capacity and repeat semantics remain
separate comparisons. Splitting a requested atomic batch across guest execution
would change its semantics.

The relevant existing sources are
`native/qemu-frame-keys/qemu-10.0.13-fdisbull-frame-keys-v1.patch`,
`src/fdisbull/qemu_frame_keys.py`, and the host/native frame-key suites.

## Source-raster checkpoint and timeline state

The original `native/qemu-video-frame` layer leaves its partial rows, completed
source raster, stream metadata and timer deadline outside native checkpoint
state. The reconstructed [source checkpoint extension](../native/qemu-video-frame-checkpoint/README.md)
adds these fields to instrumented format 3, including separate completed and
partial pixels and the actual armed expiry. It restores logical state with a
fresh source token and epoch. The current source fence is still never serialized.

The [source-raster timeline](DOS_QEMU_MIGRATION.md#source-raster-timeline-replay)
adds explicit host admission, PNG provenance, rewind readback and branching.
The ordinary renderer profile and its artifacts remain available. The source
profile requires a retained completed raster and stores its checkpoint with the
partial next raster and timer phase. A rewind verifies the source pixels and
logical phase under fresh stream ownership before admitting the cursor. Held
frame keys use checkpoint restore without reinjection.

The paired dynamic-phase campaign, wider input profiles and game-level
timeline qualification remain open.

## Sampling remains profile-specific

The recorded [Native07 paired result](DOS_QEMU_PAIRED_SOURCE_FRAME_PLAN.md)
matched all quiet authored rasters, then distinguished the fixed dynamic phase
families: DOSBox phase 1 and QEMU phase 0. Both counterphases and the final-palette
image were rejected. `backend_source_phase_equal=false` and
`exact_dynamic_image_equivalence_claim=false` remain explicit.

Source stepping controls the existing QEMU sampling profile. Resolving wider
mode, palette/origin, runtime-profile and cross-backend sampling obligations is
separate from exposing that working control through the legacy route.
