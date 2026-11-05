# D004 navigation follow-up

The D003 findings below remain their original evidence scope. See
[NAVIGATION.md](NAVIGATION.md) for the later original walking-to-car integration
and the separately recorded second-door corridor. No generic gate approval or
vehicle driving behavior is inferred.

---

# Doors and original vehicle interactions, 1 November 2026

Current qualification: installed fDisBull/Player 0.29.0 and the supplied native
DOSBox-X backend, selected MAIN SHA-256
`bfbed760ab2def1fbe9f73588dc5a24747826c9b7660d615b02a8847d92bf078`.
The guest has been closed. Do not reuse a vanished session or stale binding.

## What changed

Object subtypes 12, 13, 14 and 15 stay category `door`, respectively closed,
opening, open and closing. A changing animation must not erase a portal from
counts, nearest-entity queries or route conditions. `open` is a recovered object
state, not a universal collision or reachability certificate.

Vehicle occupant chains are separate from spatial cell chains. Vehicle +0x1C
points to its first person. Person +0x22 is the next occupant; +0x24 is its
predecessor, either the vehicle root or another person. Person +0x2C is a retained
order-target field, not authoritative current membership. The old `vehicle_refs`
pair remains available with a correction to its meaning. Invalid cycles, dangling
references and inconsistent predecessors produce unknown membership, not an empty
car or an invented direct vehicle reference. Boarded actors remain in the scene.

## Enable the bounded live profile

Create a new owned original-game session and reach mission 1 as in README.md.
Record an explicit private native checkpoint before experiments. Nominate an
observed MAIN code base, then run:

```sh
python tools/bind_scene.py --controller-root /absolute/new-private-session \
  --main /absolute/SYNDICAT/MAIN.EXE --code-base 0x1c4030 \
  --output /absolute/new-private-session/scene-binding.json \
  --enable-original-vehicle-actions
```

The number is an example, not a constant. Whole-object/source validation is
mandatory. The option adds private original-source and trial-directory fields.
At provider startup, the actual source is relocated under the verified object
mapping and every selected interaction window is compared to live code.
Without this opt-in profile, the additional action verbs are not exposed.

Use the ordinary Player with `--backend-command`, not replay-safe `--live`
checkpoint promises. Representative commands:

```text
teleport car approach
board car
examine car
examine team
focus team agent 2
teleport car approach
board car
examine car
focus team agent 1
exit car
focus team agent 2
leave car
```

The profile currently admits team slots 0 and 1, mission 1, and its selected
subtype-13 car. The actor must already be within one XY tile and at the same
height for a boarding request; that is a bounded research preparation, not the
original final boarding threshold. The original code performs the final approach.
A source-derived final distance gate uses max(abs(dx),abs(dy)) <128 raw units
and abs(dz) <=128. Other state/vehicle checks remain original-code decisions.

The action is **diagnostic/assisted**. It prepares the source-bound native
selected-agent field and mouse input latches, pauses at the actual request
producer, verifies its chosen actor, then supplies the selected vehicle's
hit-test reference. It observes the original emitted command and original actor
updates. It never writes actor position, actor state, occupant links, instructions
or CPU registers as part of board/exit. A separate requested teleport does write
linked spatial state and is labelled separately.

Completion requires coherent spatial and occupant graphs, the intended membership
transition, preservation of other occupants and attachment settlement. Repeating
`board car` when already aboard is a no-op without writes or guest-time advance.
An uncertain request holds the provider. It is not retried automatically; inspect
or restore an explicitly qualified checkpoint and create a fresh provider.

## Observe at the original input-loop boundary

Elapsed-time stops can land inside timer contexts with different selectors.
The opt-in profile waits at original input-loop entry 0x2D610, with checked source,
load/session identity and expected CS/DS. No selector is forced. Teleport settlement
and `advance world` also use this boundary when this profile is active. Passive
reads never wait, run or patch the guest. A frame/input boundary is not a calibrated
wall-time or fixed-refresh-rate claim. A fired one-shot watch's documented
`BREAKPOINT_NOT_FOUND` on cleanup is expected; unrelated cleanup errors propagate.

## Qualified door corridor, not complete pathfinding

After an initial assisted placement, the original actor walked from raw
`(16512,8576,256)` to `(16512,8064,256)` and back. The request's world-coordinate
hit test was prepared; no position writes occurred after either movement request.
Both legs took 32 observed 16-unit movements and one stopped-state observation.
Door 3 opened/closed through original code; health stayed 16 and spatial lists
remained coherent. This witnesses that actor/corridor/context, not every doorway,
footprint, moving obstacle, floor connection or planner output.

A single-unit boundary counterexample also remains: door 3 admits x=16639 but
its fixed three-column root lookup misses x=16640, despite the latter passing
its fine geometric test. Keep full coordinates and original search semantics.

## Verification and remaining work

At the D003 stage, 103 authored checks passed. Its recorded installed-Player native sequence passed 15
commands, including two occupants, head removal, last removal, a repeated-board
no-op and a distant pre-input refusal. Five additional open-door/map/car/team
reads were passive. Earlier aborted selector/preflight/cleanup preparations stay
recorded separately; they are not silently counted as successful target trials.

The graphic maps are preserved. `public/car-occupancy-ascii.txt` and the new
semantic `public/two-occupants-observation.json` are local documentation inputs,
not required original game payloads. The latter can be read offline without
`--map-model` (the old model binds the old snapshot and should correctly reject
this different snapshot). Native tests need privately supplied game files and
are not reproduced by source-free unit tests.

D003 did not claim a generic walking executor, driving, mission completion,
capacity analysis, other vehicle types, fair-play visibility, or universal
passability. D004's later bounded walking profile is described in [NAVIGATION.md](NAVIGATION.md).
The D003 native investigation made no GitLab read/write, release or
shared-installation change. It used a fresh private 0.29.0 runtime from the
unchanged supplied offline kit.
