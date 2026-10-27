# Persistent debugger scenes (0.17.0)

Version **0.18.0** adds [read deduplication, compact replies,
portable bundles, typed relative outcomes and numbered overlays](SCENE_IMPROVEMENTS.md).
The published 0.17.0 packages retain their original behavior.

For published packages, tag CI and copied qualification, see the
[0.17 delivery record](DELIVERY-0.17.md).

Scenes are now project database objects. A versioned manifest drives both the
headless overlay and named guest actions. Clean snapshots, object identities,
context, earlier revisions and failed observations survive project restart.
This implementation supports native DOSBox RGB probes; the Wine/QEMU and IDA
backends do not yet expose this scene runtime. No released 0.16.0 package is
silently upgraded by these source changes.

## Author a scene

Capture a real frame with `debug.screenshot()`, then save a definition:

```python
saved = project.debug_save_scene("office", definition, author="agent")
office = debug.scene(saved["id"])
office.assert_current()
office.click("office.bank")
```

Pin the returned revision ID in a saved route. A scene name resolves its current
revision when a handle is created. `debug_save_scene(..., parent=old_revision)`
creates a new immutable revision and rejects an outdated parent. Preserve an
object's returned ID when renaming it: the old name becomes an alias. Earlier
object definitions and snapshot evidence remain retrievable.

Definitions use `format: fdisbull-scene-1`, reference screenshot artifact ID,
native `width`/`height`, the reference frame's `mode_id`, context with a nonempty
`state` and `triggers`, a `match` predicate, and 1..64 objects. Each object has:

- `name`, persistent `id` (assigned on first save), optional aliases, and context
  containing the represented state, triggers and any confidence/source notes;
- `area`, an explicit interior `point`, and a separately preserved `original_area`;
- distinct `visible`, `ready` and `enabled` predicates;
- `action`, an explicit guest `click`, keyboard `press` or keyboard `type`;
- an `outcome` predicate and `guest_ms`/`timeout_ms` budgets;
- supporting `evidence` screenshot IDs, defaulting to the clean scene reference.

The reference `mode_id` is provenance, not a stable BIOS mode number. Runtime
matching checks the dimensions, source pixel format and double-width/height
signature, then re-evaluates the authored predicates. Each observation records
the current frame ID, mode generation and state revision. No availability result
is cached across actions, camera/modal changes, layer changes, sessions or state
restoration. Camera/state validity must be expressed in the authored predicates;
the debugger does not infer arbitrary game semantics from context labels.

## Shapes and cheap recognition

Action regions support:

```json
{"subtract":[{"rect":[119,60,220,177]},{"rect":[205,135,299,173]}]}
```

Rectangles are `[left,top,right,bottom]` with half-open bounds. `polygon` accepts
native integer points with included raster edges. `union`, `intersection` and
two-operand `subtract` compose those regions, including disconnected areas and
holes. A saved raster hash binds overlay rendering and point validation. The
framework rejects an empty mask or a point outside it. SVG paths, bitmap imports
and general equations are not implemented in this first version.

Action geometry and recognition masks are separate. Predicates support
`constant`, `pixels`, `memory`, `all`, `any` and `not`. For example:

```json
{"pixels":{"samples":[{"x":51,"y":26,"rgb":[20,30,40]}],"tolerance":0,"min_matches":1}}
```

These are schema examples, not calibrated DinoPark colors. Memory predicates
use a project-mapped `address`, `length`, expected `hex` and optional byte `mask`.
Samples are collected in one native `video.probe` call, with a maximum of 4096
coordinates. The response contains RGB triples and frame metadata: it does not
encode or transfer a PNG. A second metadata-only probe rejects an observation
that spans different frame/context revisions.

A pixel match establishes the authored visual condition. It does not, by itself,
prove control registration or enabled state. Use separate explicit conditions
and label a calibrated correlation honestly. The DinoPark acceptance uses an
observed dispatch-selector value as one readiness condition and independently
verifies the resulting input transitions; it does not claim to have recovered a
universal control-builder-ready flag.

## Named actions, stops and ambiguity

`office.object("office.bank").exists()` checks scene/object visibility and raises
on unavailable or ambiguous evidence. It is not an assertion of readiness.
`office.click(...)` and `office.act(...)` require all three availability conditions
and a postcondition that is initially false. They send real guest input, bound
mouse clicks to the newly checked frame/mode and poll the outcome. Already-true
postconditions are rejected before input, rather than being counted as proof
that a new action succeeded.

Use `scene.wait(...)` for an explicit bounded readiness wait. It returns without
guest execution if the condition is already true. Guest progress and wall time
are separate budgets; measured guest time may overshoot a requested slice by
the backend's scheduling granularity. A breakpoint, watchpoint, hook, guest error,
missing capture, ambiguity or exhausted budget is an explicit stop/exception.
The framework does not continue through debugger stops. Diagnostics and artifact
export are separate from the guest-driving timeout.

Scenes in the same `exclusive_group` (default `main`) cannot both match. Objects
can declare an `exclusive_group` for mutually exclusive visible variants.
Conflicting active hit areas at the chosen point are also rejected. An ambiguity
retains candidate revision/object IDs, observed values, source frame metadata,
a diagnostic clean snapshot and overlays for the conflicting definitions.

Optional named popup handlers contain `when`, real input `action`, an explicit
point for mouse input, and their own `outcome`. They execute only when an action
opts in with `handle_popups=True`. Multiple matching handlers are ambiguous.
The sequence checks the handler's postcondition, rechecks the target, and uses
the action's shared wall/guest budget. Unknown popups remain dependent on the
authored scene/readiness checks; the tool does not promise to discover every
possible modal automatically.

`SceneError.result` retains the persisted observation and available diagnostic
artifacts. A failed saved-script step preserves that structured result.

## Persistence, overlays and interfaces

`project.debug_scene_info(revision)` and `debug_scene_observations(...)` inspect
definitions and results offline. `debug_scene_overlay(revision, artifact=frame)`
renders the same masks, points and names on a stored clean screenshot, with an
optional grid, without launching or operating a GUI. The source image remains
unchanged. Evidence is tied to the selected disassembly byte version; a patched
child does not silently inherit the original version's scenes.

The Python APIs are also exposed through JSON methods `debug-save-scene`,
`debug-scenes`, `debug-scene-info`, `debug-scene-overlay`,
`debug-scene-observations`, `debug-frame-probe`, `debug-scene-check`,
`debug-scene-assert`, `debug-scene-click`, `debug-scene-act` and `debug-scene-wait`.
Saved scripts use `frame-probe`, `scene-check`, `scene-assert`, `scene-click`,
`scene-act` and `scene-wait`. For example:

```json
{"format":"fdisbull-script-1","steps":[
  {"op":"scene-click","scene":"REVISION_ID","object":"office.ledger"},
  {"op":"scene-click","scene":"LEDGER_REVISION_ID","object":"ledger.back"}
]}
```

The CLI can save a manifest from a JSON file:

```bash
fdisbull debug-save-scene project.fdb office manifest.json
fdisbull debug-scene-info project.fdb REVISION_ID
fdisbull debug-scene-overlay project.fdb REVISION_ID
fdisbull agent-skill
```

`agent-skill` returns the bundled [fdisbull-investigate skill](../src/fdisbull/skills/fdisbull-investigate/SKILL.md),
its scene reference and its behavioral-investigation methodology reference. It
prioritizes expected decision value per cost along with evidence-backed
confidence. It is included in wheels, source distributions and tool ZIPs; it
does not depend on the author's local skill directory.

The [DinoPark acceptance driver](../examples/dinopark/verify_scenes.py) uses a
private NEW GAME copy and exports only authored evidence. Native state bytes,
game files and the byte-retaining project database stay outside Git.
See [the installed-wheel verification](VERIFICATION-SCENES.md) for the original
game, restart, stop-preservation, pixel-cost and regression evidence.
