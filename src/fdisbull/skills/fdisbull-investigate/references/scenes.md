# fDisBull scene investigation reference

Use this reference for authored native scene observations and actions. For recovering
UIL scene intent from game data and handlers, read [scene-recovery.md](scene-recovery.md).

For every target, retain full reference frames, poll sparse fingerprints, and
learn unknown states through the [shared refinement rule](#retain-references-and-refine-fingerprints).
Target-specific coordinates and labels are data, not a separate recognition policy.

## Contents

- [Observe and reuse scenes](#observe-and-reuse-scenes)
- [Build a bounded scene efficiently](#build-a-bounded-scene-efficiently)
- [Define objects and predicates](#define-objects-and-predicates)
- [Calibrate content and readiness](#calibrate-content-and-readiness)
- [Retain action and failure evidence](#retain-action-and-failure-evidence)
- [Investigate spatial predicate boundaries](#investigate-spatial-predicate-boundaries)
- [Keep world, viewport and collision domains separate](#keep-world-viewport-and-collision-domains-separate)
- [Retain references and refine fingerprints](#retain-references-and-refine-fingerprints)
- [Generalize discoveries into shared rules](#generalize-discoveries-into-shared-rules)
- [Adaptation provenance](#adaptation-provenance)

## Observe and reuse scenes

Version 0.18 supports `compact=True` on scene checks/actions/waits and
saved-script operations. Full evidence stays in the database; retrieve it with
`project.debug_scene_observation(result["observation"])`. Prefer compact replies
for expected routes and inspect retained evidence when results are surprising.
Never reuse historical success as proof of present readiness.

Repeated exact memory ranges share one capture inside an observation, including
segmented aliases; each subsequent observation reads fresh values. Keep related
conditions in one check instead of making repeated round trips.

Use `project.debug_scene_overlay(revision, labels="numbers")` for crowded scenes.
Its `legend_artifact` maps markers to stable object IDs, names and geometry.
Numbers follow that revision's object order; scripts should use names/IDs.

`project.debug_export_scenes([revision], output)` writes definitions and clean
PNGs only. `debug_import_scenes(bundle)` remaps local IDs and rejects incompatible
source/mapping or existing names. It imports historical evidence, not live
readiness. Recheck after starting/restoring the guest. States and databases do
not belong in a portable scene bundle.

Outcomes can use typed `compare` expressions with current memory, `before`
memory, integers and `add`/`sub`. Example: current `u16` counter equals
`{"add":[{"before":{"memory":{"address":"0x471ac","type":"u16"}}},1]}`.
Arithmetic does not implicitly wrap; use `wrap: {type, value}` when required.
The address is a schema example, not a qualified purchase route. Combine relative
state evidence with independent destination pixels. Every action captures its
own baseline; unavailable data remains incomplete even under `any`.

The packaged Python and JSON interfaces share the project database:

```python
saved = project.debug_save_scene("office", definition, author="agent")
scene = debug.scene(saved["id"])   # Pin this revision in saved scripts.
scene.assert_current()
scene.object("office.bank").exists()  # Visible only; not a readiness assertion.
scene.click("office.bank")        # All prerequisites + bounded postcondition.
```

## Build a bounded scene efficiently

Source checkouts containing `fdisbull.native_controller` and
`fdisbull.scene_receipts` provide shared controller/receipt helpers. Check their
availability before relying on newer guidance in an installed package. Keep
game-specific source predicates and pending transitions in an adapter. Use the
controller's admission hook for existing execution blocks, including before
keyboard delivery; a foreign debugger stop never becomes an ordinary pending
scene state. Receipt completion requires explicit forward observation endpoints.
Give a private full log and a portable summary distinct artifact roles/hashes.
The helpers cache one bounded artifact snapshot and do not authenticate a run.

Start with one intended interaction or short contiguous route, its policy and
the observation that would distinguish success from the nearest failure. Check
for existing qualified captures and source bindings first. For interpreted games,
use the actual interpreter and source resource where available; picture and
collision masks can propose a route or adjacent control, but do not establish
that either is physically reachable. Do not expand a partial scene into a
whole-game claim.

Use ordinary inputs for a gameplay claim. Record the delivered input and the
relevant before/after state in order, including enough identity and source
provenance to associate each edge with the stable run. Hash source, resources
and backend once per stable run or reusable qualified binding; recheck when the
identity, byte version, backend or restored context can have changed. This does
not replace any per-stop binding or freshness check required by the selected
native protocol.

Use bounded memory or sparse-pixel polls for routine progress and preserve the
actual guest time returned. Request a fresh stored frame when appearance or
frame timing is material; a last-completed frame is not automatically fresh or
atomic with a separate memory read. Stop on a foreign or unknown stop, uncertain
delivery, unsafe state or exhausted budget. Preserve the returned observations
and already observed effects before cleanup; an incomplete response is not
evidence that the action rolled back, and it does not authorize a replay.

Source checkouts with `control.align` can share one bounded ordinary-input axis
or unit-diagonal leg. Supply `x`/`y` scalars or inclusive ranges and adapter
callbacks for position, ordinary start/stop and boolean settlement. The adapter
owns source safety, coordinate units and room/domain context; unspecified axes
must remain unchanged. Use a range when every point in it satisfies the relevant
source/geometry contract. Local guest, poll and stall caps retain actual sampled
positions and also constrain callback/owned-stop execution through the same
controller. Overshoot, drift, changed context or unknown stops latch the attempt;
the helper never automatically reverses, retries, teleports or restores.

`control.capture_frame_state` shares a read-only stopped-status / state / stored
frame / state / stopped-status bracket. Its default does not execute the guest.
Use `require_fresh=True` only at a meaningful visual boundary; cheap status polls
can wait for a newer frame through the owner/controller, under its existing
execution admission and stop checks. A full `baseline_frame` carries session,
mode and frame ID; a bare `baseline_frame_id` is a caller-asserted ordinal in the
pinned session/mode. An already fresh frame needs no advance, and equality at
the global guest cap reached by an admitted freshness slice permits only its
final read-only bracket. Strict initial admission prevents a new operation on
an already exhausted controller. Do not resume a foreign stop or an unsafe
water/failure state for a picture.

Retain both state reads, identity checks and frame metadata. An optional
`state_projector` compares selected material fields without discarding the raw
observations. Missing or mismatched evidence remains incomplete. Stable
bracketing is not atomic frame/CPU equivalence or UI readiness:
`metadata.captured_ticks` is render time, while `metadata.state_revision` is the
capture RPC revision, never the render-CPU revision. A stale timeout returns its
last status without an automatic extra capture/advance; caller-owned diagnostic
capture can preserve the failure. Exceptions retain partial evidence and latch
the controller. The new bounded KQ1 candidate/control pair qualifies this
source slice, including 43 completed alignment legs and three required-fresh
captures. Other engines/routes remain separate. The SDK default brackets a
frame probe with two explicit paused-status reads; video metadata alone cannot
establish that execution is stopped. Keep prior-frame identities in their
owned live run and invalidate them on restoration or context replacement.

Describe expected transition stages as well as final invariants. A known west
border flag can precede a room change; the room number can change before the
original interpreter finishes drawing the actor. Admit such a stage only in
its qualified route context and bounded budget. Keep a foreign debugger stop
separate from an expected game-state transition. For intermediate waypoints,
use a source-supported range when an exact sample is immaterial. Preserve exact
coordinates where the pixel or predicate boundary is the discriminator.

Author a separate player projection from the supported source and observed
edges. Guard actions with their phase and relevant state so stale or repeated
actions cannot silently reuse an old result. Bind evidence for consequential
transitions to the source identity and observations that support them, and fail
closed when missing evidence would change the claim. Keep source candidates,
native witnesses and modeled scene effects separately labeled. Test the actual
player with the authored content, including a relevant refusal and checkpoint
restore if persistence is in scope; do not equate an in-memory checkpoint with
a durable one.

Choose verification in proportion to the change and claim: one meaningful
positive and a discriminating control may settle a bounded behavior. Reuse
unchanged source checks and completed results rather than repeating successful
runs, full suites or unrelated probes without a new risk or requirement. This
does not waive required safety gates, protocol checks or project-mandated checks.


## Define objects and predicates

Author `format: fdisbull-scene-1`, native `width`, `height`, `mode_id`, a clean
`reference` screenshot artifact, `context` with `state` and nonempty `triggers`,
the scene `match` predicate and `objects`. Each object has `name`, `context`,
`area`, `point`, separate `visible`/`ready`/`enabled` predicates, guest-input
`action`, an initially false `outcome`, and `guest_ms`/`timeout_ms` budgets.
Its snapshot evidence defaults to the scene reference. Source command IDs may
be retained in context; they never replace real guest input.

Action areas use `{"rect":[left,top,right,bottom]}` with half-open bounds,
`{"polygon":[[x,y],...]}` with included raster boundaries, or `union`,
`intersection`, and two-operand `subtract` over those regions. A point inside a
bounding box can still be outside the actual mask. SVG/expression evaluation is
not implemented. The stored raster hash binds the rendered and clickable area.

Predicates include `constant`, `pixels`, `memory`, `runtime_memory`, `compare`,
`all`, `any` and `not`. Runtime-memory observations require a qualified
session binding; they do not create persistent patch authority. Example:

```json
{"pixels":{"samples":[{"x":51,"y":26,"rgb":[20,30,40]}],"tolerance":0,"min_matches":1}}
```

Those values illustrate the schema, not DinoPark pixels. Calibrate against a
real clean frame. A memory predicate requires a project address, byte length,
expected hex and optional same-length mask. Keep a readiness hypothesis labeled
as such until its interpretation is verified. Absence of a known popup does not
prove absence of every possible popup.

Use `project.debug_scene_overlay(revision, artifact=frame_id)` for the same
regions/names drawn on a stored frame without operating a GUI. Pass `parent`
when saving a new revision. Preserve returned object IDs on rename; old names
become aliases. Reopen the project to retrieve definitions, observations and
snapshot/overlay artifacts. Another byte version does not implicitly inherit
the original scene's evidence.

Saved script operations are `frame-probe`, `scene-check`, `scene-assert`,
`scene-click` and `scene-wait`. A `SceneError` retains a structured result with
the diagnostic observation and available snapshot/overlay. Check operations do
not execute popup handlers. A click may use explicitly authored handlers only
when `handle_popups=true`; unknown or conflicting matches remain exceptions.

## Calibrate content and readiness

Keep screen-family recognition separate from the requested content, the
displayed variant and usable controls. Stable chrome can match while an old page
is still visible. An optional scene `content` object requires all three authored
predicates: `requested`, `displayed` and `ready`. All three, the scene match and
the selected object's availability must qualify before input. A selector or
rendered title alone cannot establish the other boundaries.

Calibrate sparse samples on legitimate animation phases and similar-looking
negative pages. Exclude cursors, changing counters and animated portraits from
a stable family detector when appropriate, while retaining variant-specific
recognition and semantic preflight. Recheck the selected object, identity,
quantity or price before a consequential action when those govern its meaning.
Broaden the evidence before relaxing a failing threshold; do not require
whole-frame stillness in an animated interface.

Include the relevant calibration cases: valid animation versus a near miss;
selector changing before display; display changing before controls; coherent
acceptance with observation identities; wrong/unknown/occluded content;
interrupted or exhausted waits; and restored or revised context. This is an
authoring checklist, not a claim that a new target has passed these cases.

Author destination evidence explicitly in the action's `outcome`. Current
content gates qualify admission in the starting scene; the outcome may describe
another scene and is evaluated independently of the old scene's match. The
optional `outcome_phase` value (`state`, `interface`, `persistence` or
`unspecified`) labels the intended boundary and adds no checks by itself.
A dependent action requires fresh qualification of its own context.

## Retain action and failure evidence

Name captures by their actual boundary: pre-input, post-dispatch, post-state,
post-interface or post-persistence. Take the final pre-input observation after
any preparation that advanced the guest, dismissed a popup or rematched context.
Keep an immediate post-state frame even when it still shows the old interface;
obtain a later interface observation through an explicit bounded readiness wait.
Screenshot hooks do not automatically establish these application phases.

Preserve debugger stops during waits. On failure, retain the actual frame when
available, individual failed predicates, input/stop status, before/after
observations, source/run/revision identities and any existing checkpoint
reference before changing the scene. Do not run repair hooks or repeat input to
produce a cleaner failure image. Record the order of memory/pixel reads and
coherence limits; separate captures are not automatically atomic. A failed
capture can coexist with a completed action.

Track an investigation decision alongside the object's context, for example:

```json
{
  "state":"office bank control",
  "triggers":["office controls built"],
  "evidence_status":"hypothesis",
  "confidence":"medium",
  "next_probe":{
    "question":"Does this control open the bank after readiness?",
    "cost":"one guarded click and a few pixel polls",
    "reward":"reuse the route and distinguish a bad hit area from a stale scene",
    "acceptance":"bank pixels and expected memory state both match within budget"
  }
}
```

Confidence is not a score to maximize by collecting more prose. Prefer the
smallest probe that can change the next decision; preserve counterexamples.

## Investigate spatial predicate boundaries

When an interaction looks physically implausible, inspect its actual source
predicate before inventing a distance rule. Record whether it uses an actor
origin, center, footprint or measured distance, its coordinate convention,
and the scalar/modal context. For paired AGI `posn` and negated `posn` guards,
`fdisbull.agi_spatial_predicates` can extract the narrow supported pattern;
`fdisbull.scene_boundaries.audit_rectangle_boundary` derives bounded thin
terminal complement bands using shared mask geometry.

A source witness is not a path. Check picture clearance and live obstacles,
then test adjacent positions through ordinary input in independent checkpoint
forks if the first action consumes inventory. Preserve exact launch poses,
NPC poses, original branch messages, writes, returns and failures. Keep unknown
reachability explicit and do not call a terminal band an isolated component.
Stop at the declared effect boundary; a score access does not prove a whole
room cycle or completed animation. The KQ1 dragon example confirms two row
166/167 branch outcomes while leaving the other 40 band origins unqualified.

## Keep world, viewport and collision domains separate

Use optional `coordinate_domains` metadata and the offline
`debug-scene-domain-audit` / `debug-spatial-domain-audit` methods to inspect
signed object extents before clipping. Declare the common space/unit, world,
room, collision coverage and viewport independently. Keep a baseline collision
footprint separate from rendered sprite bounds; leave missing transforms,
footprints and camera information unknown. The summary counts examined
comparisons, not qualified movement, and can be selected through output handles.

Expected off-screen data uses explicit scoped margin rules. Disable anomaly
flags per rule or with `alerts:false` while retaining layout notices. A platform
name does not establish a scrolling mechanism, and expected margins never
enlarge a safe mask or authorize teleportation. Imported metadata and screenshots
remain historical until fresh observations bind the context again.

Check both mixed and fully dry border baselines beside an inward hazard. KQ1's
recorded x154 water-walk touches the picture's right edge; it is not an object
past the viewport. A bounds-only containment result does not settle terrain
passability. Keep source seam candidates, native observations and inferred
mechanisms separate. A row inside a game picture is not automatically a row
outside the full screenshot.

World inventories can seed this work without inventing their missing rules.
Preserve exact coordinates, stacked identities and elevation layers. Distinguish
declared diagnostic anchors, static candidates, observed placements and
qualified interactions. A scene/camera glyph or world census does not supply
collision geometry or a safe teleport destination by itself.

## Retain references and refine fingerprints

This is a shared scene-authoring and reuse rule for every target, not a new
runtime API or an assertion that automatic learning is implemented. Use the
existing reference artifacts, predicates, scene revisions and observation store;
do not invent fields in the strict `fdisbull-scene-1` format to represent this
workflow. Keep any extra calibration evidence in linked project artifacts.

### Full evidence, sparse routine checks

Retain the original full, lossless reference frame for each admitted visual
state, and additional frames when legitimate variations matter. The scene owns
resolvable artifact references; image bytes can remain in the private external
store rather than being embedded in a manifest or model prompt. A hash alone is
not a replacement for recoverable pixels. Keep raw reference pixels unchanged;
annotated, cropped, normalized or masked images are separately identified
derivatives. Retain source, native geometry/mode, frame/run identity and relevant
palette/coordinate assumptions. References are historical examples, not live
readiness. Deduplicate identical stored frames and reuse existing identities.

Derive a small core fingerprint plus independent reserve points from those
frames and confusing alternatives. Select stable text strokes AND background
points when their distinction matters; a common popup border only identifies a
family. Variable words, dates, cursor pixels and animation may be excluded from
family recognition but remain separate content checks when the action needs them.
A retained example is sufficient for initial candidates, not a claim that every
animation or occlusion has been qualified.

Routine recognition uses the existing native sparse probe route when available,
with samples bound to a coherent current framebuffer. It requires no full-image
export, OCR or model interpretation. Read reserve discriminators only as needed,
or batch the small union if that avoids another RPC. Do not combine samples from
different frame identities. An unavailable sparse route is an explicit capability
gap; a declared full-frame fallback must not be reported as sparse sampling.
Exactly one qualified actionable candidate permits the next guarded action.
Zero matches means unknown; competing matches mean ambiguous. A known occlusion
may use a separately calibrated redundant signature; unexplained mismatches must
not be voted away by lowering a threshold. No finite fingerprint proves unique
recognition against every possible unseen image.

### Unknown or colliding observations

Preserve the unexpected observation before dismissing or replaying anything.
Acquire a full frame, or a bounded sequence when transition timing is relevant,
through an actually available capture interface. Reuse existing before/after or
timeline evidence rather than recapturing it. Record what each captured frame
represents; neither two screenshots nor a feature name proves atomic state or
complete intermediate coverage. Do not make a model call on every routine poll.

Compare the new frame with retained references. First decide whether it is a
new stable state, a legitimate variant of an existing state, an overlay, or an
unfinished transition. Do not make one new state per changed counter or movie
frame. A local vision model or analyst may propose a label and new correlation
points; that proposal is evidence for investigation, not automatic acceptance.
An unfamiliar stable state can be retained immediately as an unqualified
candidate even while its meaning remains unknown.

Before admitting a new or revised recognizer, compare it with ALL prior states
that could compete in its declared recognition context, including confusing
popup text, background-only views and relevant transitions. Context partitions
must be established independently, not inferred from the same disputed match.
Perform the comparisons in BOTH directions:

- the new predicate accepts its own examples and rejects other states' examples;
- existing predicates reject the new state's examples;
- every modified predicate still accepts its older legitimate examples and
  rejects the preserved negative examples, under its exact tolerance and threshold.

A new state can expose an old overly broad fingerprint. Refine the affected
existing predicates too, not just the newcomer. Add the smallest useful stable
points from the full references, preserve reserve discriminators, and keep the
colliding example as a regression case. Test newly selected points on an
additional observation when available; report a single-reference fit as such.
An online path need not evaluate the whole library every frame: the full
compatible-library comparison belongs to admission/refinement, with unchanged
comparison results reusable under unchanged dependencies.

If two relevant states are visually identical, more pixels cannot separate
them. Use a separately qualified memory/context/transition predicate or retain
ambiguity. A missing old reference blocks a collision-free promotion claim;
it does not prove that the state was absent or justify silently forgetting it.

Publish accepted changes as a new scene revision with parent/source links.
Preserve old reference frames and failure evidence; do not silently mutate a
revision already pinned by a script. Publish any mutually dependent fingerprint
changes as one coherent selected set, or suspend affected actions until the set
is consistent. Recognition alone does not add a dismissal handler, prove a
control ready/enabled, or establish Save/Load completion. Qualify those separately.
References and unfamiliar-frame evidence remain private under the target policy.

### Acceptance examples for shared implementations

Future shared runtime changes should exercise at least two unrelated authored
scene families rather than one game-only fixture. Required discriminators are:
new text inside an old popup border; an old predicate accepting the new state;
new points breaking an old valid variation; a moving cursor or permitted
occlusion; a half-drawn transition; stale/mismatched geometry; unavailable
reference pixels; and visually identical states that need nonvisual context.
Also check that known-state polling does not export images or call a model,
and that reopen/transfer retains references and revisions without declaring
historical observations currently ready. These are acceptance requirements,
not test results or new implemented runtime methods.

## Generalize discoveries into shared rules

When a user supplies an architectural correction, separate the shared rule from
the target evidence that motivated it. Put lifecycle, recognition, refinement
and refusal policy in the shared scene framework/skill; keep coordinates, text
signatures, edition bindings and action recipes in target adapters. Reuse the
existing schema, storage and probe APIs before creating a parallel helper.
A local fix is a regression example, not completion of a cross-target request.
Explicitly identify what is already implemented, what is documented in an
unmerged branch, what is available in the selected runtime, and what remains
an integration gap. A PR note alone does not activate a shared rule.

For a reusable contribution, make the rule discoverable from the shared skill,
name the implementation owner and affected consumers, retain a target-independent
regression contract, and link source changes to the relevant coordination MRs.
Do not claim propagation until the selected shared runtime/skill contains the
change and its consumers actually use it. Keep hypotheses, reference images and
recognition recipes portable through existing project artifacts; commercial
screenshots and payload-bearing stores do not belong in public source packages.

## Adaptation provenance

This skill paraphrases selected investigation principles from the user-provided
`debug-ready-ai`, `debug-decision-tree-ai`, `explain-button-ai`, `find-string-ai`,
`tell-story-ai` and `systematic-debugging` skills. Their OMP/macOS-specific attach,
re-signing, orchestration and output machinery is not imported. Cost/reward is
an explicit priority alongside evidence-backed confidence at the user's request.
