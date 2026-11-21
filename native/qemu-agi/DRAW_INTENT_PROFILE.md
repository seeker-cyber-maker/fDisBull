# Native cycle controls and deferred draw

`agi-2917-draw-intent-pilot-1` extends the explicit VIEW binding experiment
with cycling controls and a stopped, typed draw request. It executes cycle
flag changes. It does not complete drawing, rendering or presentation.

## Selection and compatibility

```text
-M agi-test,view-catalog=/absolute/path/views.fdbagiv1,draw-intent=on
```

Both properties are startup-only. `draw-intent=on` requires a valid catalog.
The selector defaults to false; catalog-only startup still selects the exact
`agi-2917-view-binding-pilot-1` contract. Without a catalog the scalar profile
is unchanged. Both old profiles continue rejecting opcodes 35, 70 and 71.

| Profile | State schema | Events schema |
| --- | --- | --- |
| `agi-2917-draw-intent-pilot-1` | `fdisbull-agi-intent-state-1` | `fdisbull-agi-intent-events-1` |

The [VIEW binding profile](VIEW_BINDING_PROFILE.md) defines the shared catalog,
reset state, actor fields, binding operations and faults. The new source
identity has the new profile name and the same exact catalog SHA-256 binding.
Existing consumers must opt into the new schemas. The old binding and scalar
consumers reject them.

## Committed cycle controls

| Opcode | Command | Effect |
| --- | --- | --- |
| 70 | `stop.cycling(actor)` | Set only the actor's `cycling` bit to false. |
| 71 | `start.cycling(actor)` | Set only that bit to true. |

Any valid actor slot is admitted, including an unanimated and unbound actor.
The commands retire normally. Redundant writes retire but produce no SCENE
actor transition. Neither command advances a cel, moves an actor, or changes
the cycle mode. First `animate.obj` sets cycling true; another `animate.obj`
on the already animated actor preserves its current cycling bit.

These operations follow the direct flag behavior in the pinned primary
[ScummVM command handlers](https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/op_cmd.cpp).
This is a nominal reference, not new original-interpreter parity evidence.

## Deferred draw boundary

Opcode 35 validates a valid actor and its loaded, bound VIEW/loop/cel. A
missing binding or invalid actor faults with the existing fault codes. A
successful request stops with guest status `effect`, PC still pointing at
`draw`, and no fault. No actor field changes; the instruction does not retire,
and no following instruction executes. Coordinates outside the picture remain
unchanged because position repair is part of the deferred work.

Only this profile adds `guest.pending_effect`. It is null at all non-effect
stops. At an effect stop it has exactly these fields:

```json
{
  "kind": "draw",
  "reason": "draw_requires_host",
  "pc": 11,
  "opcode": 35,
  "bytes": [35, 14],
  "actor": 14,
  "retired": false,
  "committed": false,
  "completion_available": false
}
```

The numbers above are illustrative. `source` and `catalog` in the same native
snapshot bind code and resource identity; `guest.actors[actor]` supplies the
complete committed pose. They remain immutable while the draw is pending.
The observation epoch describes the current journal, not the creation time of
the request. Clearing observations cannot create or erase an execution fact.

Direct continuation while pending leaves guest state, journal and run counters
unchanged. Observation configuration/clearing remains available and changes
only its normal control and diagnostic state. Restart clears the request,
actors and loads, retaining the immutable catalog and profile selection.
There is no draw-completion, state-import or actor-injection API.

### Why completion is deferred

The pinned `cmdDraw` includes position repair, previous-position and size
updates, sprite-list rebuilding, composition, and conditional presentation.
Position repair also depends on peer actors and the priority/control map; see
[checks.cpp](https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/checks.cpp)
and [sprite.cpp](https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/sprite.cpp).
VIEW dimensions alone cannot establish those effects. A native pending draw
is useful intent for a designer preview, but does not establish drawn sprite
membership, visibility or presentation.

The repository's existing AGI effect machinery similarly separates a pending
draw from host-observed completion. This native profile does not claim to use
that DOS host or expose its completion path. General `erase`, repeated draw
after a completed draw, picture operations and cycle ticks remain unsupported.

## Optional observations

DISASM and SCENE remain controlled by the existing two-bit mask. Cycle controls
use the ordinary retirement and atomic actor-change records. Pending draw
produces neither a retirement record nor a completed SCENE effect. Its typed
descriptor belongs to authoritative stopped state and survives a disabled,
cleared or saturated journal. No additional diagnostic event kind is added.

With observations disabled, translated cycle commands omit diagnostic calls
and before-state capture. The semantic draw helper remains necessary because
it establishes the stop. Full guest-state comparisons include pending_effect;
they must not drop that field to make observation-neutrality checks pass.

## Bounded development collector

`draw_intent_trial.py` uses exact contiguous source spans, explicit zero-reset
state and an executed authored VIEW-load prologue. It accepts two endpoints:
`authored_return` retires every copied action and the appended return;
`pending_draw` stops on the final copied draw without retiring it. The same
source preparation, catalog, decoded assets and journal validation mechanisms
are shared with the binding collector. Separate packet/profile identifiers
preserve the distinct acceptance contract.

The [detached packet contract](DRAW_INTENT_PACKET.md) states how to reconstruct
the committed pose, cycling state and requested diagnostic image while keeping
position repair, current visibility and presentation explicitly unresolved.
