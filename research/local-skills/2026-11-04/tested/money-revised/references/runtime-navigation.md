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

## Contents

- [Build the smallest useful Z harness](#build-the-smallest-useful-z-harness)
- [Establish one input and outcome](#establish-one-input-and-outcome)
- [Batch a HUD experiment](#batch-a-hud-experiment)
- [Movement ladder](#movement-ladder)
- [Settle a route when required](#settle-a-route-when-required)
- [Checkpoints, replay and evidence](#checkpoints-replay-and-evidence)
- [Spatial masks and policies](#spatial-masks-and-policies)
- [Observation ladder](#observation-ladder)
- [Object-state classification](#object-state-classification)
- [Bounded controller](#bounded-controller)

## Build the smallest useful Z harness

Start with `look`/`inspect`, one observed action and a way back to the starting
state. A resource reader can expose map bounds or object names before a guest is
running; label it as a static view. A live harness adds current scene/state,
named actions and observed outcomes. Grow it during investigation instead of
finishing all recovery and building the harness afterward. Recovering source
semantics into UIL is shared with reconstruction, but this goal needs no output
past UIL and can keep driving the original runtime.

Include the main menu and global controls in the Z representation immediately.
For example, expose menu selection, difficulty, globe centering/zoom and base
placement as separate actions, with their current state and entry conditions.
Initially a named action can execute the learned input recipe; replace its
implementation with a supported programmatic operation when that becomes known.
Compose full routes from the same handlers instead of burying useful controls
inside one long startup macro. A failed coastal-view predicate blocks placement,
while centering and zoom remain available. Return that partial state and its
available actions so discovery continues through the harness.

For repeated actions, use one `z-controller` and its owned live session:

```sh
fdisbull z-controller /private/work/game.fdb --executable /path/to/backend \
  --game-dir /private/work/game --actions /private/work/actions.py \
  --root /private/work --spatial-mode assisted
```

The selected file is trusted authored Python, not recovered target content.
It exports handlers and small descriptive contracts:

```python
def look(ctx):
    return ctx.frame()

ACTIONS = {"look": {"handler": look, "entry": "live guest",
                    "next_state": "observed frame"}}
```

Send `{"verb":"list"}` or `{"verb":"look"}` as JSON lines to the same process.
Each action/list request recompiles the selected file; `ctx.state` and the guest
persist. Compose named actions with `ctx.invoke("verb", **params)`. The handler
checks actual entry state; its metadata alone is not a readiness predicate.
Add a newly discovered menu or globe action to this module and use it immediately.
Imported sibling modules have normal Python caching; explicitly reload an edited
helper or keep evolving handlers in the selected file. A bad module or handler
returns an error without falling back to stale actions or discarding the guest.
Partial effects remain available for inspection; no automatic retry or rollback.

Use `ctx.run(guest_ms=..., timeout_ms=...)`, `ctx.frame(output=...)` and
`ctx.call(method, params)` for supported native operations. The reserved JSON
verbs `run`, `frame` and `call` expose the same operations. `ctx.dos_click` reuses
the qualified bounded INT33 recipe in `fdisbull.z_dos`; that module also provides
complete `read_linear` and `write_linear_guarded` helpers for supported backends.
The helper delivers input; the target action observes the resulting scene.
`close`, EOF or transport failure closes the owned guest/project. Do not end the
stream merely to edit a handler. A saved run record cannot reconnect a dead guest.

Save/load controls are especially useful discovery seeds. Follow the main-menu
load dispatch through slot/path selection to file reads, destination buffers and
the successful continuation. Serialization identifies candidate persistent state
and can prioritize field, writer and reader branches before the whole format is
understood. Use original routines once their call/initialization contract is known;
do not leave repeated Save/Load menu navigation behind a supposedly semantic verb.
Core serialization, state adoption and scene redraw can be separate routines.
Observe file bytes, live state and the completed frame at the boundary needed by
the next consumer. Loading values does not by itself prove initialized scene entry.

Use existing surfaces selectively:

| Reusable result | Existing surface |
| --- | --- |
| Named input sequence or bounded route | `debug-script`, `debug-move` |
| Scene object and ready/outcome predicates | Scene definitions and named scene actions |
| Several numeric/pixel observations in one visit | Named observations, `debug-wait`, scene probes and scripts |
| Native checkpoint experiments on supported backends | `debug-save-experiment`, `debug-restore-experiment`, `debug-compare-experiment` |
| Multiple distinguishable guarded RAM edits in mapped DOS regions | Non-overlapping patches in `debug-layer`; explicit field-to-sentinel mapping |
| Partial action set with local research gaps | `debug-save-workflow`, `debug-workflow-observe`, `debug-workflow-act` |
| Public text interface over known actions | `debug-save-text-projection`, `text-host`, `fdisbull-player` |

These are available building blocks, not an automatic whole-game harness or
research scheduler. Consult the selected method's schema for the backend in use.

Turn a reusable record layout, string/value collector or script into a bounded
deterministic helper rather than asking another agent to transcribe it again.
Run collectors beside the owned session so they consume complete bounded reads
and return useful candidate locations and witnesses. Retain raw data once when
another consumer needs it; do not require dumps of every scanned range merely
to report a candidate. A truncated preview is insufficient if the collector has
not yet consumed the bytes, so provide that collector or retained-data path first.
Before interpreting a parsed value operationally, check the small schema detail
that matters (for example MAP header height/width order). Do not confuse this
with proving every possible reader or exhaustively exploring the game.

## Establish one input and outcome

Start with the owned live session, a recognizable entry state, one ordinary
input and the requested visible or semantic effect. Keep the same session while
learning its press/release cadence. An accepted input, a drained queue and a
visible effect are different results; stop checking once the next task has the
result it needs.

Use existing operations: Python `d.keyboard.press(...)`,
`d.keyboard.key_down(...)` / `d.keyboard.key_up(lease)`, `d.click(...)` and
`d.run(guest_ms=..., timeout_ms=...)`, or their JSON `debug-*` methods.
`d.keyboard.state()` reports queued events and owned keys. Mouse state is
available through `d.call('input.mouse.state')` on the native DOS backend.
`guest_ms` bounds emulated work; `timeout_ms` is the host-side deadline. Omitting
`guest_ms` can run until that deadline, so a 30-second timeout is not a short settle.
A short `hold_ms` remains short even when followed by a long run. Match click
coordinates to the captured frame dimensions, not a scaled preview.

If an input is rejected, retain the unmet condition and try a supported ready
boundary within a bounded run. For example, native absolute DOS mouse input can
be admitted during the original driver's real/v8086 service even when a DOS
extender normally runs in protected mode. Preserve the driver/mode guards; this
is a conditional route, not general protected-mode mouse support. Do not turn
that one rejection into a permanent target blocker.

If input is accepted without the effect, check the effect before another attempt,
then try one discriminating cadence or safe same-session press/release cycle.
A recognized transition calls for a bounded settle without input, followed by
reassessment of the next entry/ready state. Repeating the previous click can
activate a different control on the arriving screen.
A screen can be visible before its controls are ready. Do not repeatedly restart
and send the same first input. If the diagnostic itself changes behavior, compare
ordinary execution at the next boundary: single-stepping a DOSBox native callback
can differ from normal callback dispatch. Keep observer failure separate from
guest failure. Use `analysis-approach.md` for other capability mismatches.

Once a sequence works, retain its entry predicate, input/timing/release sequence,
effect predicate and stop budget as a named action. Use `debug-script` or a
target-local helper over those supported operations; no universal retry helper
is supplied. A helper can return **effect observed**, **input not admitted**, or
**effect unobserved**, with the existing observation reference and next usable
state. These are suggested recipe results, not tool schema fields.

Give a dependent worker that action recipe, its question, relevant guide claim
or field candidates, required output and next consumer. Publish the action as
soon as it works; the worker need not read the failed probes or wait for the
underlying input mechanism to be fully recovered.

## Batch a HUD experiment

Before entering a screen, gather compatible questions. The minimum inputs are
the current scene, displayed fields, candidate addresses/encodings, a supported
guarded edit, a display-refresh action and a recovery path. Collect the frame
and relevant memory snapshot once. Search for all displayed values and useful
strings together; a rendered label need not exist as contiguous text in RAM.

Retain a baseline appropriate to the effect: original bytes with guarded
restoration for a bounded reversible edit, an original game save plus its working
load route, or a supported native checkpoint. Restoring bytes does not undo
effects already propagated elsewhere; use the save/route when those matter.
Reject restoration over unexpected changed bytes. Native checkpoints are not
a universal gate. High-level runtime bindings, DOS layers and native memory RPC
have different ranges and mode support; choose the supported surface explicitly
without treating a raw read/write as a persistent binding or layer.

Choose the smallest useful batch:

| Batch | Shared work | Intervention and output |
| --- | --- | --- |
| Observe together | One visit, frame and memory census for four HUD fields | Candidate set per field; each can unlock its own probe immediately. |
| Test sequentially in one visit | Same scene and recovery recipe | Edit one candidate, refresh, record its field response, restore as needed, then test the next; no repeated navigation. |
| Test compatible edits together | One baseline and refresh | Assign distinct in-range sentinels to non-overlapping candidates; record all field responses and known coupling, then split only when attribution remains ambiguous. |

For a HUD showing `Health: 234`, assign its candidate 456 and a money candidate 789, then
return a compact table of field, candidate/encoding, original value, sentinel,
observed display and observation reference. If each assigned field follows its
edit, publish those scoped display dependencies immediately. A partial result
can unlock a writer task, gameplay-reader task or guide-rule check while another
field remains unresolved. Distinct values help attribution but do not establish
independence when edits are coupled. Recover authoritative gameplay meaning only
when a downstream task needs it. Reuse the acquired scene-entry and action recipes
for the next batch.

Reuse an existing baseline comparison when it already settles restoration. For
a stable view, an identical retained frame can resolve ambiguous small HUD text
without another live operation. Use the relevant fields or predicates when other
parts of the screen legitimately change; whole-frame equality is not mandatory.
Recognize the scene through stable elements rather than the values being edited;
a baseline-only frame gate would reject the intended changed HUD and block restore.

Several displayed numbers can alias one stored field or derive from several
fields. Record the resulting field-to-output relation; useful coupling is a
result, not a reason to search for a separately writable variable behind every
number. Split an experiment only if the next decision still needs attribution.

For a paused owned native DOS session whose backend supports guarded linear
memory writes, the existing lower-level Python path is:

```python
import base64
address = {"space": "linear", "offset": f"0x{candidate_address:08X}"}
before = d.call("memory.read", {
    "address": address, "length": len(replacement), "view": "ram"})
changed = d.call("memory.write", {
    "address": address,
    "data_base64": base64.b64encode(replacement).decode("ascii"),
    "expected_sha256": before["sha256"]})
```

Retain `before["data_base64"]` for restoration, guarded against the then-current
bytes. The backend checks mapping and the expected old bytes; keep those guards.
Reads/writes are bounded to 65,536 bytes per call. This surface can operate on
protected-mode linear memory even when higher-level DOS bindings, layers or
checkpoints cannot. A successful write still needs the requested consumer's
outcome, such as one refreshed HUD batch. It does not create a persistent binding.

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

## Bounded controller

Select an exact `debug_define_macros` ID for every `macro` or `move` operation. Latched games require a second full same-direction press; held games require a returned owned lease and its key-up. `move` requires explicit observations, destination, progress window and stopped-state predicate. A blocked receipt is failure, even if a separate diagnostic intervention later recovers the session. Capture its immediate authentic frame without screenshot hooks. Re-resolve runtime bindings after checkpoint restore. Navigation masks use a declared game coordinate space and actor footprint; keep their source facts, inferred/derived status, conditional colliders and contradictions. Requested content, displayed content and control readiness are separate conditions. Use [bounded proofs](proofs.md) to test an explicit model without promoting its fidelity to fact.
