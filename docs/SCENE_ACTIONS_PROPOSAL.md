# Proposed saved scenes, button overlays and pixel assertions

Status: design specification. The first implementation is documented in
[SCENE_FRAMEWORK.md](SCENE_FRAMEWORK.md): persistent definitions/evidence, shared
overlays, composite rectangles/polygons, named actions and native DOS RGB probes.
That implementation ships in [0.17.0](DELIVERY-0.17.md). SVG/bitmap
imports, classifier integration and a graphical authoring editor remain future
work; the broader design below must not be read as an implementation claim.

The agent defines a virtual scene once on an authentic grid screenshot. Named
regions, click points, expected states and cheap assertions become its persistent
working model. Routine scripts act on that model. Unexpected observations pause
execution and capture a frame for the agent to inspect and update the model.

## Scene definition

One versioned scene manifest in the project database is the shared source for
the visible overlay, named actions, recognition rules and transition assertions.
An authored scene stores its reference artifact identity, native dimensions and
video mode, named control shapes and click points, and explicit observation
rules. The overlay and the Python/script interfaces resolve the same object
identity and manifest revision; they must not maintain separate coordinates.

Scene identity includes subpage, camera/viewport or anchor position, native
dimensions, video mode and any blocking modal. An office with a popup and the
same office after dismissal are different runtime contexts even when their
background pixels match.

## Persistent object context and evidence

Every object has a stable database identity, a readable name and immutable
definition revisions. Names can be renamed or aliased without replacing the
object identity. Each revision records:

- The scene and semantic state it represents, parent/subpage/camera context,
  and the triggers that cause it to appear, disappear or change state. Preserve
  whether a trigger is reported, an authored hypothesis or runtime verified.
- Its original geometry, any authored action-area refinement, anchor/coordinate
  transform, interior click point, recognition rules and separate availability
  predicates. Preserve source command IDs, table locations and dispatch order
  when known; unknown values remain unknown.
- Its real mouse/keyboard action, expected outcome and separate guest-time and
  wall-time bounds. A recovered command ID is diagnostic metadata, not a way to
  call the game's callback directly.
- Author, creation time, parent revision, change reason and supporting snapshot
  links. Recognition methods, masks, thresholds and classifier versions belong
  to the revision as well.

Snapshots use the project's existing authenticated artifact store. Save the
original clean frame with its hash, run/session, frame ID, guest ticks, dimensions,
mode and relevant runtime context. Grid, region outlines and mask previews are
derived views linked to that original; they do not replace it. One snapshot may
support several objects through separate region annotations.

Every actionable object revision requires supporting evidence. A draft with
missing evidence can be persisted but is not executable. Keep positive examples,
counterexamples, ambiguous matches and failed postconditions linked to the exact
object and recognizer revisions. Earlier definitions and evidence remain
available after editing. A missing or invalid referenced artifact makes the
dependent check unavailable; it must not silently become a successful match.

## Action shapes and recognition masks

Action geometry is not restricted to a rectangle. Start with rectangles combined
by **union, intersection and subtraction**. The same geometry contract can
support polygons, disconnected regions, holes, SVG paths or declarative region
expressions. An imported bitmap/alpha mask can also define an action area; save
the conversion threshold and source identity when deriving its binary mask.

Store the authored expression or path and its deterministic native-pixel
interpretation, including bounds, coordinate transform, fill/boundary convention
and mask identity. SVG input is geometry with an explicit viewBox/transform and
fill rule; a shape expression describes a bounded region. Neither is an
arbitrary script or external-resource loader. The overlay renderer and click
validator consume the same resulting region.

**Action masks** define where input may land. **Recognition masks** define which
pixels contribute to identifying an object or state. They are separately named
and versioned even when they share geometry. A detector's ignored text region
does not automatically become an invalid click region, or vice versa.

The click point must be inside the action region, outside holes and outside
conflicting active hit areas unless dispatch priority is verified. Do not choose
the center of a bounding box as a substitute for an interior point: it can lie
outside a concave shape or inside a hole. If no unambiguous interior point is
available, return an ambiguity exception with the relevant shapes and evidence.

For example, an authored ledger area could subtract the sale-card overlap from
the original ledger rectangle. Preserve the original rectangle as evidence;
the refined action mask is a separate authored revision.

The observation rules can use:

- A few pixels at known coordinates with expected RGB values and an explicit
  per-channel tolerance.
- A small reference patch plus a binary mask. Text, changing counters, animated
  decoration and cursor pixels can be excluded from the comparison.
- Optional guest-memory predicates when they are understood and verified.
- Known blocking-popup definitions with their own probes and explicit handlers.

The author specifies which rules distinguish two similar states. Availability
has three separate predicates: **visible**, **ready** and **enabled**. Each may
be matched, not matched or unavailable, with its own evidence. A scene name,
fresh frame or convenient background color does not prove that the game has
registered its controls. Readiness may instead use a verified control-builder
return, registration-table observation or other explicit condition. A named
action requires its authored prerequisites and a successful postcondition.

Persisted definitions survive restarts; cached runtime target observations do
not become valid merely because a definition exists. Invalidate those observations
after scene/subpage changes, camera movement, modal changes, dimension/mode changes,
new sessions, checkpoint restoration and relevant code/layer changes. Definition
or recognizer revisions also invalidate dependent cached results. Recheck the
current frame/context and all required availability predicates before input.

## Inexpensive normal path

A native `frame.probe` operation should return selected RGB samples or masked
match results directly from the last completed framebuffer. It must not encode
or transfer a full screenshot for a few pixel checks. Include frame ID, captured
guest ticks, dimensions, mode and freshness/validity, including invalidation after
state restoration. All coordinates refer to native screenshot pixels.

Pattern matching is deterministic: declare the pixels or patch, mask, color
tolerance and required match count. An unavailable or invalid frame is distinct
from a pattern mismatch. A fresh frame does not by itself prove a control exists.

Proposed usage, not an existing API:

`scene.click("office.ledger")` and the object-style form below resolve the same
database object and manifest revision used to draw the overlay. Neither call
duplicates the target's geometry or availability rules in the script.

```python
scene.assert_current("diner")
diner.small_feeders.more.click(times=20)
diner.ok_button.click()
scene.assert_current("street", guest_budget_ms=5000, wall_timeout_ms=3000)
```

`diner.ok_button.exists()` evaluates its authored presence rule. A named click
first checks the containing scene, the control's conditions and known blockers,
then queues guest input and checks the expected effect. Repeated clicks can
assert the quantity after each action or after a declared batch.

## Desynchronization and recovery

Waits keep logical guest-time and wall-clock limits separate. An unexpected
scene, unknown popup, missing capture, invalid frame or exhausted budget returns
an incomplete/failed route with the last observations. It must not silently click
coordinates from the previous scene or claim success from accepted input alone.

Save the clean frame, an optional grid/named-region overlay, the expected and
actual probe values, last action and stop reason. Known popup handlers may run
only when their own pattern matches, and must verify dismissal afterward.
Breakpoints, watchpoints, hooks and guest errors remain explicit stops; scene
waiting must not resume through them automatically.

The agent can inspect the diagnostic snapshot, correct or add a scene definition,
and resume explicitly. The normal route stays cheap, while the saved definition
remains a readable and reviewable mental model of the game's controls.

## Ordered if / else / exception rules

A scene can formalize its alternatives as an ordered decision tree: if a known
popup matches, run and verify its handler; else if the expected scene and control
match, execute and verify the action; else raise a scene exception. Each branch
has an explicit condition, action, postcondition and bounded execution budget.
The saved run records which branch matched and why.

Distinguish legitimate parent/modal combinations from mutually exclusive scene
or object matches. Conflicting matches produce an ambiguity exception before
ordinary first-match rule selection; they must not be hidden by list order.
Evaluate compared features against the same completed frame and context epoch.

Persist a collision record linking the candidate objects and definition revisions,
feature scores/values, thresholds, active shapes, context and original snapshot.
The agent can reopen that frame with both overlays, inspect positive and negative
examples, refine the geometry or detector, and create a new revision. Retain the
collision as a regression example for the revised definition. Geometry overlap
and recognition-feature collision are different kinds of ambiguity and should
be recorded separately.

Recognition is a replaceable part of that contract. Exact pixel samples, masked
patches and optional future lightweight classifiers return the same matched,
not-matched or unavailable states. Classifier observations additionally record
model/version, region, confidence and the configured threshold. Scene names,
controls, actions and exception handling remain stable as recognizers improve.
Whether a classifier may select a branch or only suggest a diagnosis is an
explicit property of the authored rule. A missing observation never selects a
successful branch.

## Reported DinoPark office starting examples

The user supplied a researcher report saying the original office table contains
11 rectangles and command IDs. These are the three provided examples, preserved
as reported source data rather than a fresh extraction:

| Name | Reported native bounds | Suggested interior point |
| --- | --- | --- |
| `office.bank` | `(0,0)` to `(102,53)` | `(51,26)` |
| `office.ledger` | `(119,60)` to `(220,177)` | `(169,118)` |
| `office.sell_park` | `(205,135)` to `(298,172)` | `(251,153)` |

The ledger and sale-card bounds intersect between x=205..220 and y=135..172.
The two suggested points are strictly inside their respective bounds and outside
the other listed object's bounds. That is a geometric check, not a new runtime
hit-test verification. The source's upper-edge convention, dispatch priority,
actual command ID values and remaining eight objects were not supplied here;
preserve them as unknown until the original table and runtime behavior are
verified. Supporting captures and source locations must be attached before
these reported definitions become actionable database objects.

## Acceptance checks for the future implementation

- Restart the project and recover the same object identities, contexts, trigger
  provenance, revisions and supporting snapshots; pin a saved script to its
  exact manifest revision.
- Edit a target once and show that overlay geometry and named action resolution
  agree, while earlier revisions and their evidence remain retrievable.
- Exercise composite rectangles, concave regions, disconnected regions and holes;
  reject clicks outside the actual mask even when inside its bounding box.
- Present a visible scene whose controls are not ready, and a ready but disabled
  control; neither should receive input until its separate prerequisites match.
- Change camera, modal, checkpoint, session or manifest revision and demonstrate
  invalidation followed by fresh checks rather than reuse of stale target data.
- Make incompatible detectors match one frame; capture an ambiguity with both
  candidates and snapshots, then revisit and refine the definition without losing
  the original collision evidence.
- Verify the expected transaction or transition after actual guest input. Missing
  captures, unknown popups, unexpected debugger stops and exhausted budgets remain
  explicit incomplete/exception results.
