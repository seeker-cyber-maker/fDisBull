# Keen Dreams: visible gameplay and measured representation costs

The November 20, 2026 checkpoint completed a short original-input route in the
supplied game: walk left, jump into a collectible, gain 100 points, and land with
three lives and neutral controls. The original 320 by 200 game image was visible
in the cloud browser. Enlarging that image changes presentation only; the route,
map, colliders and physics retain their native coordinates.

This extends the qualified [feedback loop](KEEN_REALTIME.md),
[input phase work](KEEN_INPUT_TIMING.md) and existing read-only browser presenter.
It adds an explicit optional frame sink and a reversible compact-state stream.
These are experimental source helpers, not an installed general Keen provider.
The installed runtime remains DotBox `0.1.0.dev9`. Exact identities and results
are in [the authored receipt](evidence/keen-gameplay-2026-11-20.json).
The subsequent [actor-model checkpoint](KEEN_ACTOR_MODEL.md) uses a fresh active
Carrot trace to compare source-informed walking rules with current RAM, with
screenshots disabled in its feedback loop.

## What the game actually did

One owner controlled every native call through the supported runtime API. Each
measured trial started in a separate private copy of the original game, followed
the known opening controls, and qualified its source, code, memory layout,
observation hook, ownership, player pose and local terrain. The controller used
ordinary left and Ctrl key edges. It did not write game memory or restore a
machine snapshot.

A standing-jump baseline rose 60.9375 game pixels and returned to the same
position. It completed 41 observed updates and 1,171 guest milliseconds, ending
with three neutral landed observations. The collection policy then used the
post-actor/pre-refresh hook and a freshly checked flat corridor. Its milestones
matched in both display-cadence runs:

| Observed milestone | Update | Native player position | Score |
| --- | ---: | --- | ---: |
| Initial standing pose | 0 | `(33280, 7695)` | 0 |
| Release left | 27 | `(31960, 7695)` | 0 |
| Start standing jump after settling | 31 | `(31936, 7695)` | 0 |
| Release jump | 35 | `(31936, 7375)` | 0 |
| Collect selected bonus | 39 | Recorded coherent airborne state | 100 |
| Three unchanged neutral standing transitions completed | 70 | `(31936, 7695)` | 100 |

The route moves 84 game pixels left in total. It uses a coarse 80-pixel release
threshold with a wide collectible-overlap allowance; it does not claim the
two-pixel stopping precision of the separate predictive waypoint policy.
The jump rises 55.9375 pixels. World coordinates remain 16 units per game pixel
and 256 units per tile, independent of browser size.

Collection was verified by both the 100-point increase and actor slot 31
changing from bonus to inert, followed by removal from the complete linked actor
list. Disappearance from the nearby projection alone was insufficient. The last
three updates preserve player position, standing state, floor contact and
neutral sampled controls. A leftover vertical-speed field of 51 does not mean
the grounded player is still moving; state, contact and observed displacement
establish the landing. Lives and inventory remain unchanged.

## Display work can run less often than control

`KeenLoop(..., frame_sink=None, frame_every=4)` leaves screenshots disabled by
default. A caller may provide a bounded synchronous
`frame_sink(png_bytes, metadata)`. The loop then captures the initial observation
and every selected Nth accepted update through its own RPC channel. The browser
server only reads the cached frame; it never operates the guest.

The sink receives validated original PNG bytes and copied frame metadata.
Native frame identity and state-observation identity remain separate:
`phase_synchronized=False` explicitly records that a completed framebuffer may
precede the post-actor RAM observation. Screenshot RPC, decoding and sink costs
are measured, included in completed-cycle host time, and subject to the existing
ownership and uncertain-operation rules. The callback receives no native session.
Synchronous callbacks are not preemptible, so this is not a hard callback deadline.

The paired collection runs used the same owner, policy, source, hook, initial
state and normal original clock. The only selected controller difference was
display cadence.

| Measurement | Every update | Every fourth update |
| --- | ---: | ---: |
| Coherent gameplay updates | 70 | 70 |
| State observations including initial | 71 | 71 |
| Display captures including initial | 71 | 18 |
| Screenshot RPC work | 137.743 ms | 32.972 ms |
| Total capture, decode and sink work | 163.116 ms | 39.357 ms |
| Controller host time | 1,993.005 ms | 1,993.614 ms |
| Accounted guest time | 1,999 ms | 1,999 ms |
| Complete cycle p50 | 28.419 ms | 28.424 ms |
| Complete cycle p95 | 31.321 ms | 31.951 ms |
| Slowest complete cycle | 44.948 ms | 46.520 ms |

All 71 complete compact states matched exactly, without normalizing clocks.
All key decisions, policy events, 70 hot-memory hashes, guest timestamps,
initial/final full object snapshots and 18 common presentation-frame hashes also
matched. Run and timeline identities remain distinct. Three bytes outside the
qualified hot-memory window differ in the full initial and final DS snapshots;
their meaning is unclassified. Whole-RAM equivalence is not claimed. Output
paths and the post-trial viewer lifetime also differ, outside the measured loop.

The sparse run used 74.65% fewer captures and 75.87% less measured display work.
It did not establish a throughput or tail-latency improvement: both runs advanced
at approximately normal speed and the sparse run's slowest cycle was slightly
longer. Normal guest pacing can absorb host work. This is one short paired
experiment, not a sustained performance guarantee, and does not claim an
improvement over the earlier display-disabled loop.

There is a visible tradeoff: at roughly 35 coherent updates per guest second,
every-update capture supplies about 35 frames per second and every-fourth-update
capture about 8.75. Lower capture frequency suits a compact agent view or reduced
recording; a watched game can retain the denser setting. Both settings keep the
same control cadence. The separate post-trial viewer polling interval is outside
this feedback comparison.

## Lossless world representation

The new `scripts/experiments/keen_world.py` encodes compact observations as a
bounded ordered JSON stream. It factors repeated context and state definitions
by complete content, then reconstructs the original state mapping exactly.
The controller continues to consume its unchanged mapping. Encoding was measured
after gameplay and adds no unmeasured work to this controller comparison.

The first representation factored phase/map context and player definitions,
saving 4.81% on each richer collection trace. Nearby actor arrays made up 80.63%
of that trace's state bytes. Factoring repeated actor `state_name` and
`state_record` by content improved the collection reduction to 23.36%:

| Fresh trace | Observations | Original state array | Context/player factoring | Final actor-aware stream |
| --- | ---: | ---: | ---: | ---: |
| Standing jump | 42 | 178,002 bytes | 163,044 bytes | 136,708 bytes |
| Dense collection | 71 | 521,547 bytes | 496,455 bytes | 399,730 bytes |
| Sparse collection | 71 | 521,547 bytes | 496,455 bytes | 399,730 bytes |
| Total | 184 | 1,221,096 bytes | 1,155,954 bytes | 936,168 bytes |

Every one of the 184 states reconstructed exactly. The final aggregate reduction
is 23.33%, compared with 5.33% before actor-definition factoring. Counts include
all headers, context/definition/state records, references, commas and brackets
in independently framed canonical JSON arrays. Controller envelopes, memory
transport, screenshots and RPC receipts are outside this comparison. This is a
byte-size result, not a measured serialization-speed or frame-rate improvement.

Earlier, smaller retained schemas still save 24.30--26.59%; their nearby objects
lacked these repeated definition fields, so the actor extension does not change
those measurements. They are not the basis for the fresh result above.

The public stream uses `dotbox-keen-world-stream-2`. A changing definition gets a
new content reference even when its game pointer is unchanged. All other actor
fields, including current position, collider, activity, state pointer, counters,
scratch fields and list order remain per observation. Missing fields and unknown
finite JSON are retained. Only nearby lists of at most 100 objects are factored;
other JSON shapes pass through unchanged. Format 1 requires its original decoder
and is refused explicitly by the new decoder.

The implementation bounds reconstructed states to 16,384 canonical bytes,
streams to 10,000 observations, and context/definition tables to 1,024 references
each. It validates content hashes, reference ordering, duplicate factored fields
and reconstruction limits. Hashes establish exact reported content, not actor
lifetime, terrain freshness or authority to issue input.

```python
records = encode_states(states)
restored = decode_records(records)
assert restored == states
```

## Keep definitions, terrain, live state and presentation separate

| Layer | Appropriate contents | Freshness and identity |
| --- | --- | --- |
| Game definitions | Tile attributes, directional collision meanings, state definitions | Exact source/resource identity and complete content hashes |
| Terrain baseline and changes | Tile planes, map dimensions, capture provenance, later changed cells or refreshed regions | Point-in-time baseline; pointers alone do not prove unchanged content |
| Current control state | Player and actors, colliders, movement, state/timers/scratch fields, input, clocks, physics, camera | Coherent live observation with source/session/timeline fences |
| Planner and scene view | Relevant local geometry, current actor facts, observed events and qualified next actions | Derived bounded projection referencing its observations |
| Display | Original framebuffer, scale and viewport | Separate visual frame identity; no effect on world coordinates |

The level has 136 by 37 tiles: each 16-bit plane is 10,064 bytes. The owner
captures foreground and event planes plus tile attributes at admission and
completion. Their matching endpoint hashes in these trials establish endpoint
equality, not continuous immutability. Released source `RFL_AnimateTiles` writes
animated cells in place; `PatchWorldMap` also changes map cells. General terrain
reuse needs changed-cell reporting or bounded revalidation.

The private live decoder now retains nearby inactive and inert actors and their
state/timer/scratch fields. General hazards still require phase-aware reasoning:
a temporarily flowered creature is inert now and can later restore. Slots and
pointers can be reused and are not permanent entity identities. A scene omission
means the fact was not projected; it does not prove an actor was destroyed.
The broader persistent model and automatic scene integration described in
[WORLD_MODEL.md](WORLD_MODEL.md) remain separate development work.

## Verification, preparation and limits

The first new owner attempt stopped during a legitimate 720 by 400 startup
text-mode capture because it applied the 320 by 200 gameplay guard too early.
That failed run and its clean process closure were retained. Bootstrap now
accepts validated native modes while preserving pinned prompt checks; admitted
gameplay, the frame sink and final display still require 320 by 200.

This was warm reuse of existing controls and research. The retained preparation
clock reached first verified useful play after 797.421 seconds, exceeding its
600-second budget. Earlier preparation before that clock is unknown. Desktop
command submission and the startup-size correction contributed to the delay;
the clock was not reset and the result is not presented as cold-start acceptance.

The final targeted suite passed 199 tests: 58 loop, 99 unchanged waypoint and
42 world-stream tests. It covers the optional sink, uncertain receipts, callback
failures, exact reconstruction, actor-definition references and the nesting
boundary between a state and its record wrapper. `git diff --check` passed.
Exact file hashes and the command are retained in the receipt. The visible browser
showed score 100 and three lives after the final collection run. Browser input,
audio, platform takeover, general enemy avoidance, arbitrary jumps, terrain
mutation tracking and full-level completion remain unqualified by this slice.

The previous viewer, failed startup, baseline and dense trial closed with reaped
native processes and return code zero. The sparse trial completed its controls
and hook cleanup, then continued ordinary execution for a bounded read-only
viewer interval. Its final shutdown must be established separately; a successful
trial is not a claim that the lingering process has already exited. Commercial
game files, raw memory and native image payloads remain outside Git.
