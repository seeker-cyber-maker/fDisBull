# Runtime navigation and observation reference

## Contents

- [Spatial masks and policies](#spatial-masks-and-policies)
- [Movement ladder](#movement-ladder)
- [Build the smallest useful Z harness](#build-the-smallest-useful-z-harness)
- [Settle a route when required](#settle-a-route-when-required)
- [Observation ladder](#observation-ladder)
- [Object-state classification](#object-state-classification)
- [Checkpoints, replay and evidence](#checkpoints-replay-and-evidence)
- [Bounded controller](#bounded-controller)

## Spatial masks and policies

Persist a source/version-bound room map in game units with known and safe masks,
an actor footprint, obstacle and hazard exclusions, separate object zones, and
references to supporting native snapshots. Rectangles, polygons, row runs and
their union/intersection/subtraction compose the same map. Unknown cells remain
unknown. A source control plane is evidence of encoded geometry; horizon,
dynamic objects, runtime blocks and scripted hazards require separate checks.
Use `debug_spatial_candidates` and bounded `debug_spatial_route` to propose
anchors/routes. Resolve doubts with ordinary walking from a protected checkpoint
when the expected information reward justifies the cost and hazard exposure.

`move(..., spatial_map=revision, position={'x':'x','y':'y'}, target=[x,y])`
checks the destination before input and refreshes room/condition checks while
moving. It preserves debugger stops and reports a geometry disagreement rather
than declaring an unobserved route successful. Polling cannot prevent every
hazard between samples. KQ1 demonstrates that movement into water can succeed
and still be fatal; keep hazards separate from physical obstacles.

Choose `physical`, `assisted` or `story` explicitly at native DOS launch or with
`spatial_policy`. Physical actions enforce proximity. Assisted actions qualify
an object-zone anchor and a limited actor placement recipe before original
input. Story actions keep the actor in place and temporarily waive a specific
source-identified spatial condition; room, inventory, modal and puzzle conditions
remain guest-owned. A general position-free adapter is not inferred from the
word "story." Define and verify each guard profile. An AGI byte sequence that
resembles a condition is insufficient without instruction/control-flow evidence.

Fair play locks physical policy across state restores. Policy is voluntary and
does not turn the analysis API into an anti-tamper environment. Text projections
keep source addresses and guard definitions private and expose the policy marker.
The full API and qualified PQ/KQ scope are in the source-checkout documentation
`docs/SPATIAL_MAPS.md`.
The 0.23 AGI proximity-waiver profile is limited to a source-identified,
byte-bound spatial condition with checked control-flow boundaries. It preserves
the opcode and object identity and leaves nonspatial tests guest-owned. It is
not a general position-free interaction adapter, teleport, or permission to
waive any condition that resembles a proximity check.

Progressive workflows support a small qualified action subset while
unrelated scene research remains incomplete. Pin a progressive workflow and
resource inventory, then expose only grounded public objects through a text
projection. The separate `fdisbull-player` consumes that projection; it does not
need disassembly or investigator-only state. Use cheap observations for routine
checks and retain diagnostic frames on a mismatch.

Travel assistance is an explicit control policy. `assisted_travel` can place a
qualified actor inside a room or at an observed portal followed by original
transition input. It must not write the declared room field. Require destination
position and readiness, not just a changed room byte. Report skipped traversal,
different guest time and possible changed hazard exposure. Prioritize a reusable
action when its expected benefit justifies qualification cost and confidence;
do not recover every room before the first useful action. See source-checkout
`docs/PROGRESSIVE_SCENES.md`, `docs/TEXT_PROJECTION.md` and
`docs/ASSISTED_TRAVEL.md`.

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

Choose the cheapest compatible capability already available for the question.
The ladder accumulates capabilities; it does not require replaying earlier rungs.
Honor the user's selected assistance/fair-play policy.

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
5. **Named scene start.** Reuse a checkpoint or the original initialization path
   with its required resources, flags and entry state. Retain the entry predicate
   and one observable ready outcome. A room/scene-ID write alone is insufficient;
   `assisted_travel` does not write the room field. Missing initialization blocks
   this shortcut, while the existing route remains available.
6. **Semantic action.** Keep the same public text verb while replacing its input
   macro with a supported programmatic operation when its preconditions and
   effect are known. Keep the input-backed implementation as a fallback. This
   is a target-specific adapter, not a generic native handler-call capability.

## Build the smallest useful Z harness

Start with `look`/`inspect`, one observed action and a way back to the starting
state. A resource reader can expose map bounds or object names before a guest is
running; label it as a static view. A live harness adds current scene/state,
named actions and observed outcomes. Grow it during investigation instead of
finishing all recovery and building the harness afterward. Recovering source
semantics into UIL is shared with reconstruction, but this goal needs no output
past UIL and can keep driving the original runtime.

Use existing surfaces selectively:

| Reusable result | Existing surface |
| --- | --- |
| Named input sequence or bounded route | `debug-script`, `debug-move` |
| Scene object and ready/outcome predicates | Scene definitions and named scene actions |
| Several numeric/pixel observations in one visit | Named observations, `debug-wait`, scene probes and scripts |
| Restore a baseline and compare a declared change | `debug-save-experiment`, `debug-restore-experiment`, `debug-compare-experiment` |
| Multiple distinguishable guarded RAM edits | Non-overlapping patches in `debug-layer`; explicit field-to-sentinel mapping |
| Partial action set with local research gaps | `debug-save-workflow`, `debug-workflow-observe`, `debug-workflow-act` |
| Public text interface over known actions | `debug-save-text-projection`, `text-host`, `fdisbull-player` |

These are available building blocks, not an automatic whole-game harness or
research scheduler. Consult the selected method's schema for the backend in use.

For a HUD such as `Health: 234`, collect the label, displayed number and scene
once. Search relevant live strings/format strings and numeric memory candidates;
the displayed text might be a render buffer rather than stored game state.
Batch candidates for health, money and other visible fields. Narrow by natural
changes or set distinct valid sentinels from one saved baseline, then observe all
fields together. If 456 and 789 appear in their assigned places, retain those
display dependencies and use them. Split a coupled result; trace a writer or
authoritative gameplay value only when a downstream action needs that meaning.

Turn a reusable record layout, string/value collector or script into a bounded
deterministic helper rather than asking another agent to transcribe it again.
Before interpreting a parsed value operationally, check the small schema detail
that matters (for example MAP header height/width order). Do not confuse this
with proving every possible reader or exhaustively exploring the game.

Before any screen visit, collect compatible pending questions and prepare their
observations. Save/restore once per compatible batch. Preserve the mapping from
field to intervention and capture the joint outcome; run separate trials only
for ambiguous or interfering changes. Once route/scene-start/action shortcuts
work, use them for subsequent batches instead of repeated manual traversal.

## Settle a route when required

If a direction is latched, reaching the predicate is not yet a settled route.
Queue the target's ordinary stop/toggle input, continue until it is consumed,
and verify that direction is neutral, the coordinate remains in range, the
context did not change and no route input remains pending. Detect a blocked or
invalid route when the coordinate is unchanged for a bounded number of updates,
the target reports a no-movement condition, the context changes unexpectedly,
direction changes, or any guest-time/watch-hit budget expires.

Qualify memory arrival, rendered arrival, interaction range, original exit
effects and stopped input separately when the task depends on them. Animation
can continue after arrival; use the relevant stable predicates rather than
whole-frame equality. A positioned cursor and released controls may still
precede the target's own readiness to consume the next input.

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

## Observation ladder

Imported-image layers, session-bound runtime reads and runtime-resource
transformations have different authority. A witnessed `runtime_memory` binding
allows supported observations in its session; it does not turn a heap range
into an imported region or grant persistent layer support.

Before either transformation below, require a supported resolver bound to the
current resource/source/adapter identity, expected live bytes, a qualified
guarded transition, and changed-byte refusal on restoration. Re-resolve after
restore, restart or relocation. Keep imported-image layer guards intact.
If the selected backend cannot provide this authority, use a qualified neutral
anchor or the authentic actor-visible view. A direct backend experiment or
remembered heap address does not establish a reusable transformation.

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

For native persistence, distinguish disk slot, internal save title, public
backup name and artifact identity; qualify collision and replacement behavior
before saving. Preserve unknown native bytes and compare defined fields under
their own contract. A changed whole-file hash can coexist with equal decoded
fields. Validate a selected save through the target's fresh loader; equal fields
alone do not establish equal queues, RNG, timing or future behavior.

Preserve both the ordinary route and diagnostic shortcut when both were used.
Report which one established each claim. Keep target-specific addresses,
coordinates, anchors and object pixels in project evidence or cartridge data,
not in this reusable skill.

## Bounded controller

Select an exact `debug_define_macros` ID for every `macro` or `move` operation. Latched games require a second full same-direction press; held games require a returned owned lease and its key-up. `move` requires explicit observations, destination, progress window and stopped-state predicate. A blocked receipt is failure, even if a separate diagnostic intervention later recovers the session. Capture its immediate authentic frame without screenshot hooks. Re-resolve runtime bindings after checkpoint restore. Navigation masks use a declared game coordinate space and actor footprint; keep their source facts, inferred/derived status, conditional colliders and contradictions. Requested content, displayed content and control readiness are separate conditions. Use [bounded proofs](proofs.md) to test an explicit model without promoting its fidelity to fact.
