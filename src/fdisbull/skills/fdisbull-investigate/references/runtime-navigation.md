# Runtime navigation and observation reference

Use this reference when an investigation must move an actor through a running
program, repeatedly reach a state, or inspect scene pixels that the actor can
occlude. It describes a capability ladder, not a promise that every backend or
target supplies every rung. Check the selected backend, target adapter and live
session before choosing a method.

Keep player, authoring and diagnostic capabilities distinct. A diagnostic state
edit can test proximity or rendering without proving that a player traversed the
route. A visual projection can remove an actor from a frame without removing it
from program logic. Neither should silently become the ordinary player interface.

The investigation is deliberately cumulative. Once a target fact is qualified,
save it as a versioned semantic observation, scene object, named anchor, route,
projection or adapter when that will reduce later work. Link the reusable artifact
to the evidence that established it and retain invalidated revisions. This makes
fDisBull an increasingly capable game harness while analysis continues, without
collapsing a learned diagnostic shortcut into proof of ordinary play.

## Movement ladder

Choose the least invasive rung that settles the question.

1. **Authentic bounded input.** Send the program's ordinary directional input
   for an explicit guest-time budget. Verify how the target samples or latches
   the input; delivery acceptance does not prove movement. Record start/end
   semantic state and the stop reason.
2. **Conditional authentic movement.** Keep using ordinary input, but stop when
   an independently qualified coordinate/state predicate becomes true. Prefer
   ranges and crossing predicates to exact equality because one update may skip
   over an exact value. Bound guest time, watch hits and unchanged observations.
3. **Named route.** Compose qualified conditional segments such as vertical then
   horizontal movement. Bind the route to target/version, room or scene, adapter
   version and semantic anchors. A route is reusable only within those declared
   conditions.
4. **Diagnostic state placement.** Resolve the current authoritative runtime
   object and apply a guarded same-context placement to a named anchor. Use this
   for authoring, recovery or an explicitly declared text/Zork-style projection.
   Re-resolve after reload or restore; never retain a prior heap address as
   authority. Verify unchanged room/context and let the target's own interaction
   logic decide whether an action succeeds.

If a direction is latched, reaching the predicate is not yet a settled route.
Queue the target's ordinary stop/toggle input, continue until it is consumed,
and verify that direction is neutral, the coordinate remains in range, the
context did not change and no route input remains pending. Detect a blocked or
invalid route when the coordinate is unchanged for a bounded number of updates,
the target reports a no-movement condition, the context changes unexpectedly,
direction changes, or any guest-time/watch-hit budget expires.

Treat unchanged x/y over a declared completed-frame, semantic-sample or watched-
write window as an early `blocked` route failure when the destination predicate
is still false. Stop/neutralize input, retain the last-changing and final values,
and capture an immediate authentic diagnostic screenshot without preparation
that advances the guest. A capture error belongs in the same failure receipt;
it does not turn the blocked route into an unknown success. Constant position is
compatible with a wall/collision but needs a target collision flag or traced
branch before claiming that specific cause.

A diagnostic teleport to a qualified anchor can recover the authoring session
after the blocked receipt is frozen. Record it as a separate diagnostic branch,
re-resolve runtime objects and verify context. Never relabel the failed walked
route as completed because teleport bypassed the obstruction.

A useful conditional vocabulary is `eq`, `ne`, `lt`, `le`, `gt`, `ge`,
`in_range`, `changed`, `unchanged_for`, `crossed_up` and `crossed_down`. A result
should retain the semantic resolver and field, session-resolved address as
evidence rather than reusable authority, start/end values, predicate, watch
hits, measured guest time, context before/after, stop reason and settled input
state.

Example design shape, not a currently guaranteed fDisBull API:

```json
{
  "adapter": "target-actor-position-v1",
  "actor": "player",
  "field": "x",
  "predicate": {"in_range": [65, 69]},
  "scope": {"scene": "qualified-scene-id"},
  "limits": {"guest_ms": 3000, "watch_hits": 256, "unchanged_hits": 8}
}
```

## Keep physical input separate from game-defined commands

Do not assume that `down`, `stop`, `press`, `release`, `interact` or another
player word has one universal physical meaning. In a latched-movement game, a
complete press may start movement and another complete press of the same key may
stop it. In a hold-to-move game, key-down starts movement and key-up stops it.

Prefer a versioned, explicitly selected user/cartridge macro set above stable
physical primitives. Macro names may be user-defined, including `down`, `stop`,
`press` and `release`, but calls should remain visibly namespaced and receipts
must retain the exact expansion. Do not redefine the core meaning of an atomic
keyboard press merely because one game interprets it as a toggle.

A reusable route should therefore record:

- the exact macro-set identity and target/static version;
- the semantic macro and bound arguments;
- expanded physical operations and their delivery receipts;
- any held-key lease created or consumed;
- the target-level condition used to establish success; and
- whether the macro is ordinary player input, authoring setup or a diagnostic
  shortcut.

Separate key-down and key-up require explicit input ownership and fail-closed
cleanup. If the current backend only supports an atomic press, retain that limit
instead of pretending a long press and a held-until-predicate movement are the
same operation. Macro expansion must remain bounded, declarative and free of
arbitrary host code.

## Observation ladder

Use one of these methods, with fallbacks in this order when practical:

1. **Persistent render-only actor projection.** Replace only the admitted
   rendering resource or equivalent presentation bytes with a reversible,
   same-length transparent form. Preserve dimensions, frame count, timing,
   mirror metadata and logical footprint. The actor stays present to collision,
   proximity and game logic. Bind the layer to immutable source identity and a
   session resolver, not a remembered runtime address.
2. **Guarded hide/capture/restore.** If a persistent projection is unavailable,
   pause, verify exact expected bytes/state, hide the actor, capture one frame,
   and restore with changed-byte refusal. A failed or unproven restoration makes
   the observation incomplete.
3. **Neutral observation anchor.** Move the actor through authentic input to a
   qualified location that does not overlap relevant objects. Record that route
   and confirm the anchor is still neutral for the current scene revision.
4. **Authentic actor-visible capture.** Keep the unmodified view for human
   review and questions involving the actor. If it occludes the recognition
   region, do not infer object absence.

A temporary presentation layer must be easy to disable and must preserve a
visually identical baseline after restoration. Captures before and after should
match at the declared boundary; a mismatch remains an unresolved intervention.
Do not patch collision or object tables merely to obtain a clean screenshot.

## Object-state classification

Define exact recognition masks or pixel fixtures from qualified positive and
negative frames. Keep action geometry separate from recognition geometry. For
each current capture return:

- **present** when the required context, render identity, dimensions and stable
  recognized pixels match;
- **absent** only when the same qualified observation boundary is available and
  the recognized object pixels are stably absent;
- **unknown** for a wrong scene/version, unavailable or unstable frame,
  unrecognized pixels, actor/overlay occlusion, incomplete hide/restore, or an
  exhausted observation budget.

Chain a pickup or other authentic action with a clean post-action observation
when useful, but do not let pixels become the sole authority for success. Use
the target's own parser response, inventory, score, object table or equivalent
semantic transition as corroboration. A clean pixel delta establishes a visual
state change within the tested frame; it does not by itself explain the cause.

## Checkpoints, replay and evidence

Save a qualified checkpoint before destructive authoring probes when the task
allows it. A rewind restores only the state covered by that checkpoint; mounted
files, external services, input queues and host-side clocks may require separate
controls. After restore, re-resolve runtime objects and resources and recheck
current scene applicability.

Preserve both the ordinary route and diagnostic shortcut when both were used.
Report which one established each claim. Keep target-specific addresses,
coordinates, anchors and object pixels in project evidence or cartridge data,
not in this reusable skill.
