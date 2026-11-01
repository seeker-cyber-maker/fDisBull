# Shadowrun city and text projection

This is an investigator view of a prepared, source-bound scene, not a complete
city reconstruction or a fair-play visibility map. `machine_from_capture`
seeds the same `lift_play` GameIL used by the NES adapter. `ShadowrunRuntime`
owns that machine; `ShadowrunZBackend` provides the standard line-oriented
`observe` and `act` protocol through `text_projection.serve_stream`.

The captured terrain table has 64 columns and 44 rows; each 32-by-32 cell is in
source pixel coordinates. Player and camera positions are unsigned integers in
sixteenths of a source pixel. Bounds are half-open pixel intervals. Region IDs
identify 8-by-8-cell blocks; cell IDs identify one cell. Scene ID and runtime
revision accompany both views. The text view shows a coarse region index and a
local grid. Its symbols classify raw terrain codes only; they do not establish
walkability, visibility, dynamic collision, objects, or navigation routes.
Y increases downward. The captured graphics atlas and this terrain table are
separate coverage domains.

The representation follows the prior Civilization world snapshot's separation
of layered source facts and diagnostics (`examples/civ_z_world/README.md` in
the established integration checkout), and the Syndicate spatial example's
separation of engine coordinates, half-open coarse cells, explicit overlays,
unknown visibility, and diagnostic travel (`examples/syndicate_z_scene/ASCII_PRECISION_AND_ROUTING.md`).
A coarse cell itself has no default action coordinate. Assisted text targets
instead spell out exact fixed-point debug coordinates and are bound to the
current revision.

Ordinary directions advance one model frame. Assisted teleport is a diagnostic
intervention, available only under the explicitly selected assisted policy. It
checks the current revision, same scene, field bounds, current viewport and
source-derived terrain collision on a transactional candidate. By default placement preserves the current camera and scroll state. An explicit
`teleport-recenter` performs an authored diagnostic recenter, clamped to source
camera bounds, and updates model scroll and stream request fields. Unknown or nonzero
collision outcomes are refused. It neither executes a scene transition nor
proves original-game reachability or dynamic-object safety. Without recentering, placement outside the existing viewport is refused. The
recentered camera is a model adaptation. A bounded native NES debug run matched
the shared model's player and camera fields after one assisted placement and
subsequent movement; this does not establish original-game teleport parity or
graphics parity. No cross-scene loader is inferred.
The exact source ROM and capture stay private. The source-bound model, native
original, NES renderer and text interface are separate comparison boundaries.

`captured_entities(rom, snapshot_path)` separately reads the receipt-bound frame
5999 slots. The source scan at `$287a..$28a2` starts at `$ff0400`, advances in
`$100`-byte steps and tests bit 0 at offset `$10`; `$11dd6..$11e04` establishes
the party slot scan at `$ff0100` with an additional bit-1 condition. A reviewed
health consumer is at `$55a62..$55a9e`; the DTO labels the observed byte
`hp_byte_4c` rather than asserting every health dispatch has the same meaning.
The four captured bit-0 records are retained separately, including their raw
kind, flags and exact coordinates. Kind 11 remains uninterpreted. Captured slot
IDs describe this capture, not a persistent identity through scene changes.
The original captured position stays historical. Where a qualified dynamic
model reports status 1, the view separately uses its current coordinates;
unsupported or absent slots do not produce a current map marker. The local
view retains all known IDs in a cell, even when several stack.
`inside_camera_rectangle` is geometry only; visibility remains unknown.
The `actor_records` field names the mixed current/historical projection;
`captured_entities` is retained as a legacy alias and each record carries its
own provenance and current-position status. Local cell `entity_ids` follows
the same projection; `captured_entity_ids` is its legacy alias, not a claim
that a source-constructed actor appeared in the original capture.
The player's current model position and captured starting position are separate.

Debug placement is implemented by the authored `shadowrun_debug_place` GameIL
component shared with the NES target. A receipt showing matching model and NES
state for a given run does not imply original-game teleport parity or establish
dynamic-entity collision safety.

A protocol client can submit an exact destination directly with target
`teleport.<x>.<y>`, where both integers are fixed-point source coordinates,
and verb `teleport` or `teleport-recenter`. The request still needs the current
context token and the assisted policy; the shared placement checks may refuse
it. Preset region candidates are explicit debug coordinates, not a claim that
any coarse region resolves to a safe execution point.

The text protocol projects the current eight inventory slots from the shared
model. A zero item code is an empty slot; missing model fields are unknown.
Weapon slot and item, armor code, and ammunition are raw model values; the
ammunition unit is labeled where this bounded composition establishes it.
Inventory open and close, D-pad selection, the selected item's equip action,
target and fire advance `shadowrun_play_frame`. Each command advances one
model frame; the explicit release action separates repeated button presses.
Unsupported item and combat paths can refuse after that frame advances. These
controls do not extend the underlying NES composition's supported domain.

When the model exposes `shadowrun_play_actor_hp`, NPC records also carry a
separate current model HP value; the originally captured HP byte is retained as
historical evidence. Missing or unsupported current HP stays unknown. In the
separate assisted arena profile, player HP and the source-constructed kind-8
actor's current coordinates and HP come from the same shared model. The former
kind-11 occupant of slot `$ff0400` remains a historical captured record, not
the identity of the constructed actor. This does not establish natural
encounter reachability, general NPC AI or whole-game parity.
The `wait` controls advance 1, 10, 30 or 60 model frames with no buttons held,
and report the number actually executed. This lets a pending bounded action
progress without treating a long action as a single input press.
The current target slot, pending-shot flag and raw projectile state come from the
same model. They describe this bounded target adaptation, not NPC visibility or
an independently observed hit.
`hold-fire` advances 10, 30 or 60 frames with A held, subject to the same
prepared-field guards as the NES adapter. The shared model's current NPC HP and
ammunition are reported after each block; the captured starting HP remains a
separate observation. A separately tested prepared-state ordinary route reaches
and damages a captured NPC in both original and NES runs; the original NPC
moves while the NES record is frozen. Assisted placement and that bounded route
do not establish general encounter reachability or NPC AI parity.
