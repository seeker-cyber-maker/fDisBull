# fDisBull scene investigation reference

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

Predicates are `constant`, `pixels`, `memory`, `all`, `any` or `not`. Example:

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

## Proposed navigation geometry extension

The implemented `fdisbull-scene-1` areas above are native screen-pixel masks for
recognition and input. Do not reuse them implicitly as game movement geometry.
A future, separately versioned `navigation` extension should be able to retain:

- an explicit logical coordinate space, origin, units and actor anchor;
- the actor collision footprint when it is not a point;
- room bounds and a bounded walkable region;
- named static or conditional colliders;
- room-transition portals and their destination anchors; and
- qualified safe anchors for separately authorized diagnostic teleportation.

Derive this geometry from exact-version code, room tables, control maps or other
static game resources when available instead of learning it through repeated
collisions. Preserve source/resource hashes, project facts, extraction rule,
coordinate transform and `derived` versus `inferred` evidence status. Runtime
contradictions are evidence and must not be hidden by rewriting the definition.
Dynamic doors, actors and script-controlled barriers remain conditions requiring
fresh observation. A room bounding box alone does not prove its interior is
walkable, and a diagnostic teleport never proves that an ordinary route worked.

## Adaptation provenance

This skill paraphrases selected investigation principles from the user-provided
`debug-ready-ai`, `debug-decision-tree-ai`, `explain-button-ai`, `find-string-ai`,
`tell-story-ai` and `systematic-debugging` skills. Their OMP/macOS-specific attach,
re-signing, orchestration and output machinery is not imported. Cost/reward is
an explicit priority alongside evidence-backed confidence at the user's request.
