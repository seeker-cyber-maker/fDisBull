# fDisBull scene investigation reference

## Contents

- [Observe and reuse scenes](#observe-and-reuse-scenes)
- [Define objects and predicates](#define-objects-and-predicates)
- [Calibrate content and readiness](#calibrate-content-and-readiness)
- [Retain action and failure evidence](#retain-action-and-failure-evidence)
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

## Adaptation provenance

This skill paraphrases selected investigation principles from the user-provided
`debug-ready-ai`, `debug-decision-tree-ai`, `explain-button-ai`, `find-string-ai`,
`tell-story-ai` and `systematic-debugging` skills. Their OMP/macOS-specific attach,
re-signing, orchestration and output machinery is not imported. Cost/reward is
an explicit priority alongside evidence-backed confidence at the user's request.
