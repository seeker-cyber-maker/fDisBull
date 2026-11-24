# Source-bound v2 room navigation

`navigation.py` inspects a verified room span and proposes a bounded route
through its stored SCUMM v2 routing table. It is a standard-library host module.
It performs no CPU operation, room transition, actor update or presentation.

Every proposal records `execution: "not_performed"` and
`live_applicability: "unverified"`. A route ending at the adjusted goal is a
candidate plan. It does not establish that the current guest can execute that
plan or that an actor has arrived there.

## Public API

```python
from navigation import (
    NavigationInputError,
    inspect_room,
    plan_movement,
    check_movement_plan,
)

geometry = inspect_room(
    room_bytes,
    room_id=room_id,
    source=packet["source"],
)

request = dict(
    room_id=room_id,
    start=(2, 5),
    goal=(15, 18),
    actor_id=1,
    player_ids=[1],
    flags={"policy": "room_initial"},
    max_hops=255,
)
proposal = plan_movement(packet, room_bytes, **request)
check = check_movement_plan(packet, room_bytes, proposal, **request)
```

`packet` is a complete, validated
`fdisbull-scumm-processor-scene-packet-1` from
[the stopped scene consumer](SCENE_CONSUMER.md). `room_bytes` is the entire
decoded room resource, including its four-byte old-bundle header. It is not
the complete containing LFL file and not a header-stripped payload. The
recorded source must select version 2 and `amiga-v2-isolated`.

All routines are pure. They neither open files nor access a VM. Returned
objects are detached from caller-owned input. Malformed source/request data
raises `NavigationInputError`. A checker mismatch returns `valid: false`;
it does not authorize execution or modify the proposal.

### Required caller choices

| Input | Contract |
| --- | --- |
| `room_id` | Explicit resource ID, 1..255, bound to the supplied room bytes |
| `start`, `goal` | Two signed 16-bit integers in SCUMM v2 actor coordinates |
| `actor_id` | Explicit actor ID, 1..31 |
| `player_ids` | Explicit unique actor IDs, each 1..31; an empty list declares no players |
| `flags` | Explicit initial-room or complete override policy described below |
| `max_hops` | Accepted box-transition budget, 0..255; default 255 |

Actor coordinates use eight pixels per horizontal unit and two pixels per
vertical unit. The packet records that space explicitly. Room width and height
are separately reported in pixels; the planner does not silently convert a
pixel request into actor coordinates.

The two admitted flag policies are:

```python
{"policy": "room_initial"}
{"policy": "override", "values": [flag_for_box_0, flag_for_box_1, ...]}
```

There is no implicit flag default. `room_initial` deliberately selects the
immutable room's initial bytes. `override` requires one byte for every box.
Both are caller declarations. Neither establishes the running game's current
box flags, which scripts can change. The proposal retains the policy and the
effective complete flag table.

Likewise, `player_ids` is explicit policy input. The reference v2 engine uses
the inclusive actor-ID interval in variables 42 and 43 for player restrictions;
the current scene packet does not establish that interval. The caller may
derive a list from a separately verified state, but this module does not infer
it from actor names, costumes, ego or selected room. Membership is recorded as
an assumption and remains unverified for live execution.

## Source and checkpoint binding

The plan carries the complete recorded code/profile/manifest/receipt/script
identity, the room ID/size/SHA-256 and a digest of the inspected geometry. The
packet's resource inventory must declare that exact room available with the
same size and SHA-256. Logical residency is not required for inspection.
Availability does not make that room current.

Admission also checks the current packet's internal snapshot evidence:

- `qualification.current_snapshot` must be true.
- The code digest in `evidence` must agree with the recorded source identity.
- Reconstructing the known native scene from `source`, `checkpoint`,
  `observation`, `actors`, `resources`, `control`, and `verbs` when present must
  reproduce `evidence.scene_sha256`.

This is a self-consistency check. It does not authenticate a publisher, establish
live VM ownership, verify unavailable kernel bytes, or independently repeat the
native bank's admission procedure. A future capture containing unknown scene
facts that cannot be reconstructed requires explicit consumer support.

`scene_binding` includes the entire packet's canonical JSON digest, its trace
epoch and control generation through the checkpoint, the recorded actor
placement/room facts, and the full selected room resource entry. It also records
whether the requested start matches the recorded actor position and whether
the recorded actor room equals the requested room. These equalities do not
invent actor initialization, a current native walkbox or a completed transition.
Changes to other packet fields still change the complete packet digest.

The checker always rebuilds geometry and the full proposal from the exact room
bytes and the original request. It does not accept a cached geometry object as
authority. A changed checkpoint, room, flag policy, player list, endpoint,
budget or proposed waypoint produces a mismatch or an input rejection.

## Bounded v2 room inspection

The inspector requires a complete 28-byte fixed room header, a matching
little-endian resource-length word, and an in-range box-table offset outside
that fixed header. All offsets below refer to the whole decoded room span.
Its validation covers the fixed header fields used here and the box/matrix
spans. It does not validate the room's object tables, sound/script dependency
lists, entry/exit scripts, image data or every other subresource. A valid
navigation inspection is not full room admission or executable room entry.

| Field | Encoding |
| --- | --- |
| Resource extent | Little-endian length at offset 0; must equal supplied length |
| Room dimensions | Little-endian 16-bit width at offset 4 and height at offset 6 |
| Box-table offset | One byte at offset `0x15` |
| Box count | First byte at the box-table offset, 0..255 |
| Box records | Eight bytes each: `uy`, `ly`, `ulx`, `urx`, `llx`, `lrx`, `mask`, `flags` |
| Box-table extent | `1 + 8*N` bytes |
| Routing matrix | Immediately follows the box table; `N*(N+1)` bytes |

Each box has a horizontal upper edge and a horizontal lower edge. Inverted
vertical or horizontal bounds are rejected. Triangles, coincident edges and
zero-height records retain their encoded geometry; no guessed rectangle is
substituted. A zero-box room is a valid inspection with no routing geometry.

The matrix begins with `N` stored byte offsets to its rows, relative to the
end of the directory. The inspector honors these stored offsets, including
permuted, shared or nonaligned rows. It does not replace them with `row*N`.
The common reference address helper skips one initial `0xff` marker when
present; that interpretation is admitted only if every directory and row read
still fits the declared v2 matrix span.

Every selected cell is interpreted as a signed byte. All negative values mean
that the table supplies no next box for that lookup. Nonnegative values must
identify declared boxes. The same-box case requires no matrix lookup, so a
negative diagonal does not prevent a direct same-box proposal. An out-of-range
offset or nonnegative destination is malformed input, not an inferred route.

The output schema is `fdisbull-scumm-v2-room-navigation-1`. It contains source
and room identity, coordinate units, dimensions, exact table spans, decoded
box fields/corners, stored row offsets and signed next-hop rows. Its flags are
explicitly initial room bytes. It establishes no current room or live flags.

## Endpoint adjustment and route construction

Both requested endpoints remain in the output. The planner separately computes
their adjusted actor anchors and selected boxes. Adjusting the start is an
explicit host proposal; the current packet has no authoritative native
`walkbox` field to recover.

Destination-style adjustment examines boxes from highest ID to lowest. For
each eligible box, it clamps Y to the box and determines the horizontal bounds
using integer midpoint subdivision of the two sloped edges. It then clamps X
to that horizontal interval. This preserves v2's subdivision rounding instead
of substituting floating-point interpolation.

The selection distance uses horizontal displacement and vertical displacement
divided by four, with the smaller component contributing half its value.
The first zero-distance candidate wins; otherwise only a strictly smaller
distance replaces the current candidate. The initial distance ceiling is 255.
Consequently, ties favor the higher box ID, and a nearby Y adjustment can have
zero selection distance without preserving the requested coordinate exactly.

The restriction bits have distinct roles:

| Flag | Role in this policy |
| --- | --- |
| `0x80` | Excludes a box from endpoint selection |
| `0x40` | Stops a route at the current-box boundary before entering that next box |
| `0x20` | Exempts a caller-declared nonplayer actor from the above two restrictions |

The remaining bits and the mask byte are preserved as source facts. Facing
remapping, costume presentation and animation timing are outside this planner.
The planner does not treat invisible and locked flags as interchangeable walls.

For each accepted transition, the stored table selects the next box. The
planner projects the current anchor to the next box's boundary, then projects
that point back to the current box's boundary. This produces the boundary
waypoint used by the v2 routing rule. Boundary projection examines top, right,
bottom and left edges in that order; equal-distance ties retain the earlier
edge. Scalar divisions in sloped projections truncate toward zero.

These operations project to edges even when boxes overlap. They are not a
generic nearest-point-in-filled-polygon operation. The proposal preserves
per-transition `legs`, including the intermediate next-box projection and any
locked boundary. Repeated coordinates are omitted from the compact
`waypoints` list while `box_path` preserves accepted box transitions.

The room matrix remains the selected routing authority. A missing route,
locked next box or cycle does not trigger A*, BFS or another inferred route.
The planner bounds transitions, detects repeated boxes and distinguishes a
budget stop from a demonstrated lack of route.

## Proposal and checker results

The plan schema is `fdisbull-scumm-v2-movement-plan-1`.

| Status | Meaning |
| --- | --- |
| `planned` | The candidate reaches the adjusted goal in the selected policy |
| `no_walkboxes` | The room declares zero boxes |
| `no_eligible_box` | Start or goal could not select an eligible box within the v2 distance ceiling |
| `no_route` | The stored lookup returned a negative next-box value |
| `locked` | The next box is restricted for the declared actor; its boundary is recorded |
| `routing_cycle` | The stored route repeats a box |
| `budget_exhausted` | More box transitions would be needed than the caller allowed |

`hops` counts accepted transitions. A blocked next box is not added to
`box_path`. Same-box plans need zero transitions and may succeed with a zero
hop budget. A finite partial route remains explicitly partial.

The checker returns `fdisbull-scumm-v2-movement-check-1`, with `valid`, `reason`,
the recomputed status and proposal digests. `valid: true` means that exact
replanning matched the supplied proposal. It establishes no live execution.

This version does not qualify continuous containment within walkboxes, avoidance
of other actors, exact original-engine equivalence, native movement ticks,
turning, animation or presentation. The original room table can direct actors
across gaps or through overlapping geometry. A consumer must not relabel these
candidate polylines as collision-free physical paths.

## Relationship to AGI and future native walking

The repository contains two useful but different navigation seams. DotBox's
host [navigation.py](../../apps/dotbox/src/dotbox/navigation.py) and
[spatial_map.py](../../apps/dotbox/src/dotbox/spatial_map.py) create and check
bounded cardinal plans over a spatial map, using heading-aware A*;
[fDisBull's older spatial-map planner](../../src/fdisbull/spatial_map.py) uses
BFS. Their source/checkpoint-bound proposal pattern is useful here.
Their rectangular footprint and unknown/hazard/portal policies do not define
SCUMM v2 walkbox behavior.

Native AGI's [runtime_actor.c](../qemu-agi/overlay/target/agi/runtime_actor.c)
instead advances eight-direction motion against
its priority/control plane and loaded VIEW geometry, with local collision and
position repair. Those are native motion semantics, not SCUMM room-table
routing. The present SCUMM module adds a host proposal layer only.

Native v2 walking would additionally need a declared current room, actor room
membership and current walkbox, destination/leg state, direction and fractional
step accumulators, and an explicit movement-cycle owner. The reference advances
actors during the engine loop; a walk instruction requests motion rather than
finishing the whole path as one retired instruction. `waitForActor` also depends
on scheduler behavior.

Future motion ticks need their own observation contract. The current SCUMM
instruction journal counts eligible events against retired instructions and
requires nonempty encoded instruction extents. Host ticks must not manufacture
script retirements or be inserted silently as zero-byte records in that schema.

## Pinned references and independence

The behavioral reference is ScummVM `v2.9.0`, commit
`38af1883a2eb7a622c31bfc3708888bbcc47db48`. Reference source was inspected outside
the production checkout. This module independently expresses the format,
scalar geometry and bounded traversal rules; it does not include or link a
copied ScummVM implementation.

| Reference | Facts used | SHA-256 |
| --- | --- | --- |
| [room.cpp](https://github.com/scummvm/scummvm/blob/38af1883a2eb7a622c31bfc3708888bbcc47db48/engines/scumm/room.cpp#L642-L868) | Whole-room offsets, v2 dimensions, box and matrix extents | `d38cc1bf0bfe4e7f1feb5fac28837691511cc937cbc0984ca8fa14856a587e0a` |
| [boxes.cpp](https://github.com/scummvm/scummvm/blob/38af1883a2eb7a622c31bfc3708888bbcc47db48/engines/scumm/boxes.cpp#L36-L810) | Box fields, signed matrix lookup, integer edge projection and edge order | `c011ef23fca0797a8b64e81ddc7971a13313cfa06e3a8fcb1f364b9c71ccee58` |
| [boxes.h](https://github.com/scummvm/scummvm/blob/38af1883a2eb7a622c31bfc3708888bbcc47db48/engines/scumm/boxes.h#L29-L49) | Record sizes and box flags | `b8b80587bcb7d228ae329d5c4f9bed6d3321400f07181149bca25c6d7f78f431` |
| [actor.cpp](https://github.com/scummvm/scummvm/blob/38af1883a2eb7a622c31bfc3708888bbcc47db48/engines/scumm/actor.cpp#L1249-L1297) | v2 next-box and locked-boundary routing | `316395ecad531b653525cd370734e9a370aecc0adee8298bcefea725ebd95606` |
| [actor.cpp adjustment](https://github.com/scummvm/scummvm/blob/38af1883a2eb7a622c31bfc3708888bbcc47db48/engines/scumm/actor.cpp#L1802-L1977) | Integer subdivision, distance metric and descending box preference | Same actor.cpp digest |
| [actor.cpp player policy](https://github.com/scummvm/scummvm/blob/38af1883a2eb7a622c31bfc3708888bbcc47db48/engines/scumm/actor.cpp#L3868-L3880) | v2 player interval and v1 Maniac exception | Same actor.cpp digest |
| [actor.h](https://github.com/scummvm/scummvm/blob/38af1883a2eb7a622c31bfc3708888bbcc47db48/engines/scumm/actor.h#L38-L51) | Actor coordinate multipliers and movement flags | `bd9b27dd2d45113954084760d1c95f76d5d8ae6a80df75a1bfeb5e0aebecce04` |
| [script_v2.cpp](https://github.com/scummvm/scummvm/blob/38af1883a2eb7a622c31bfc3708888bbcc47db48/engines/scumm/script_v2.cpp#L1083-L1103) | Walk instruction requests a destination | `41f59ce1631eedd41704ce07b370ead262447abb1c05e50b7506033974c41432` |
| [script_v3.cpp](https://github.com/scummvm/scummvm/blob/38af1883a2eb7a622c31bfc3708888bbcc47db48/engines/scumm/script_v3.cpp#L43-L49) | Box flags can be changed by the opcode reused by v2 | `3d5a690c3de0e4bab868401f2fb739f539a49e984e5efd06fd6ddd646ce10d0a` |

Version 0 has a different five-byte box format and movement algorithm. Version
3 uses a different box format and gate-based routing. v1 has platform and player
classification exceptions. This API admits the explicit v2 resource profile;
it does not infer equivalent behavior for those other variants.

## Authored verification

Independent tests are in `test_navigation.py` and require only the Python
standard library. They use authored room bytes and processor packets, with no
original game data, network service or native guest:

```sh
python3 native/qemu-scumm/test_navigation.py -v
```

Coverage includes zero-box and malformed spans, stored row offsets, all signed
negative next-hop values, initial-marker bounds, same-box diagonal behavior,
midpoint and edge ties, sloped projections, bends, locks/invisibility/player
exceptions, cycles and budgets, unavailable or changed resources, contradictory
capture evidence, genuinely changed checkpoints, verb-bearing snapshots,
proposal tampering, detached data and absence of I/O.
