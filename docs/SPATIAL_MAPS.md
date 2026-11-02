# Spatial maps and interaction policies

Version 0.22 stores room geometry in the game's own units.
The native DOS debugger, saved scripts and the text projection can share a
pinned map revision. Original keyboard/mouse input and the original interpreter
still perform the action. A map is an evidence-linked model of the qualified
context, not a certificate that every point is safe in every game state.

## Room layers

`fdisbull-spatial-map-1` has these fields:

| Field | Meaning |
| --- | --- |
| `source` | Selected project version SHA-256, pinned scene context revision, room identity and picture/resource identity |
| `space` | Named game coordinate system, width, height and unit |
| `actor` | Collision footprint width/height and anchor within that footprint |
| `known` | Cells classified by the map's stated evidence; the complement is unknown |
| `safe` | Candidate standing cells within known coverage, before subtracting active exclusions |
| `layers` | Separately named obstacles, hazards, object interaction zones and portals |
| `evidence` | Source spans, supporting screenshot artifacts, observations and qualification claims |
| `coordinate_domains` (optional) | Explicit world/room/collision/viewport extents and scoped expected off-screen margins; inspection only |

Use the [coordinate-domain audit](SCENE_COORDINATE_DOMAINS.md) to retain signed
object bounds and explain expected scrolling margins. Its unknowns and notices
do not enlarge these masks or confer movement authority. Existing composite
masks remain authoritative for their stated purpose; a bounding rectangle does
not reproduce a composite mask's holes or collision coverage.

A `source.sha256` is the **project version** hash, not a picture hash. Attach
resources to the project and bind their exact hashes and spans in `evidence`.
Screenshot references require an artifact ID and SHA-256, belong to the selected
version, and are checked on save and readback. These checks establish byte
identity. The author must establish what the bytes or screenshot mean.

Live use requires `source.context` to pin a real scene revision with fresh
picture/resource discriminators. The adapter checks its requested/displayed
identity on each operation, separately from action readiness. A same-room scene
mismatch is unknown. A descriptive label can be retained in an offline map, but
cannot qualify live movement. Scene predicates must discriminate relevant picture,
camera, control-plane and state changes; a room-number-only predicate does not
qualify those differences automatically.

Masks accept half-open rectangles, integer polygons, sorted row runs, and nested
`union`, `intersection` and `subtract` expressions. For example:

```json
{
  "intersection": [
    {"rect": [0, 90, 160, 156]},
    {"subtract": [
      {"row_runs": [[100, 90, 150], [101, 90, 150]]},
      {"rect": [133, 100, 142, 102]}
    ]}
  ]
}
```

An empty row-run list represents an empty mask. Object zones remain separate
from physical exclusions; an object zone does not automatically make its cells
walkable. Each zone can record qualified `interaction_points`. A layer's optional
`when` names a condition: false disables it, true enables it, and an omitted or
unknown condition leaves overlapping points unknown. Check the **whole actor
footprint**, including its anchor and map boundaries. A blocked part wins over
an unknown part, while an unknown part prevents a clear result.

The current AGI example uses a horizontal baseline footprint, not the visible
sprite rectangle. For its qualified view-zero cels, KQ1 has width six and PQ1
width seven. Their room plane is 160 × 168 game units; the observed 320 × 200
frames use doubled X and a picture offset of eight scanlines. These are edition
and scene facts, not a universal coordinate conversion.

## Persist, inspect and propose routes

```python
saved = project.debug_save_spatial_map("courtyard", document, version=1)
revision = saved["id"]
project.debug_spatial_check(revision, [125, 125])
project.debug_spatial_candidates(revision, zone="tree-approach",
                                 origin=[110, 100], clearance=1)
project.debug_spatial_route(revision, [110, 100], [125, 125], maxnodes=20000)
project.debug_spatial_overlay(revision, "courtyard-map.png")
```

Updates require the current parent revision; earlier revisions remain readable
after restart. Offline PNG export uses the stored map and verified stored
evidence. It never starts the game or operates a GUI. Candidate selection checks
footprints and clearance. Route planning uses cardinal steps and a bounded node
budget. A budget stop returns `budget_exhausted`, not a successful route.
Proposals do not run the guest or establish that the engine follows the path.

The corresponding JSON methods are `debug-save-spatial-map`,
`debug-spatial-map-info`, `debug-spatial-check`, `debug-spatial-candidates`,
`debug-spatial-route` and `debug-spatial-overlay`. Use them through `request` or
the existing JSON-lines service. The map and its artifact references normally
remain in the private project database.

## Map-aware ordinary movement

The existing bounded movement operation accepts:

```python
session.move(
    macro_set,
    start={"name": "right-start"}, stop={"name": "right-stop"},
    observations=observations, until=arrival, progress=progress, settle=neutral,
    spatial_map=revision, position={"x": "x", "y": "y"}, target=[146, 100],
    room_field="room", map_conditions={"door_closed": door_closed},
    target_tolerance=2,
    guest_ms=10000, timeout_ms=20000,
)
```

`map_conditions` values are predicates over fresh observations, rather than
cached booleans. A spatial map and an older scene navigation definition are
mutually exclusive for one movement call. The adapter checks the map's room
against fresh observations, authenticates its revision, checks the target before
input and checks the current footprint during movement and cleanup. Unknown or
hazardous targets are refused before the start macro. A stall near the selected
model's boundary can be classified `blocked_known_boundary`; that classification
alone is not independent proof of collision semantics.

Movement still needs qualified controls, neutral input, measured guest time and
an explicit stop contract. A debugger breakpoint/hook is preserved. An unexpected
map or room disagreement is incomplete, with diagnostic evidence. Polling cannot
prevent every hazard between samples. Use protected checkpoint forks for risky
verification and retain the counterexample instead of relabeling it success.
`target_tolerance` defaults to zero. An explicit tolerance can admit small
overshoot while the stop input is delivered; the final point must still satisfy
the declared arrival predicate and pass its own fresh footprint check.

## Physical, assisted and story policies

Select a native DOS launch policy with `Project.debugger(...,
spatial_mode="physical")`, `fdisbull debug ... --spatial-mode physical`, or
`fdisbull text-host CONFIG --spatial-mode physical`. JSON host configuration
accepts `spatial_mode`. The default remains `assisted` for compatibility with
0.21 travel callers; select a policy explicitly for experiments and benchmarks.

| Policy | Spatial action behavior |
| --- | --- |
| `physical` | Enforce the original qualified proximity predicate; send ordinary input without actor placement or guard waivers |
| `assisted` | Select a clear named object-zone anchor, apply only its qualified actor-coordinate/refresh recipe, settle in the same room, then send ordinary input |
| `story` | Keep the actor in place while applying a qualified temporary spatial guard; send ordinary input and preserve nonspatial game conditions |

`session.spatial_policy("story")` changes an unlocked session. The policy appears
in text observations and token freshness. The text player shows a spatial-policy
marker without exposing source addresses, masks, guard bytes or investigator
context. Workflow/projection dispatch kind `spatial` binds the same named action
to `session.spatial_action(map_revision, definition, ...)`. The standalone player
remains independent of the debugger implementation.

`--fair-play`, or `Project.debugger(..., fair_play=True)`, selects and locks
physical policy. It refuses assisted travel and story waivers across state
restores. It cannot be unlocked within that session. This is a voluntary player
policy, not an anti-tamper boundary around the analysis APIs.

## Qualified position-free actions

A `fdisbull-spatial-action-1` definition pins an ID, project version and map
revision, observations, room/context and nonspatial pre/post predicates, an
outcome predicate, position field names, proximity predicate, original keyboard
inputs and separate guest/wall budgets. The room is checked on every action
observation even if the supplied context predicate omits it. Input operations
drain before the next operation; their execution consumes the shared budget.
An intermediate outcome never completes a route before its remaining inputs.

Story mode requires source-qualified `spatial_guards`. In this candidate the
action helper admits the AGI resource adapter's narrow reversible RAM edit:
widen one identified ego `posn`,
`obj.in.box`, `center.posn` or `right.posn` rectangle to the full room. It preserves
the condition opcode and object number. Its complete code-resource prefix must
match an immutable attached file in the live runtime binding before any edit.
The guard includes source/version/resource hashes, exact expected bytes and its
source offset. The bounded AGI 2.917 layout scanner verifies instruction and
condition boundaries and encoded branch targets, and rejects negated guards.
Unsupported or malformed layouts fail closed. Structural decoding does not prove
reachability or the action's meaning; retain separate source and runtime evidence.
Arbitrary native execution patches remain available through manual layer APIs
and are refused as story-action guards until a semantic qualification adapter exists.

The PQ1 profile qualifies a room-6 condition that computes radio proximity flag
227. The original GET RADIO handler retains inventory, character-state and
one-time score checks. The flag also serves the room's return interaction, so
the override is restricted to the bounded action. It does not make arbitrary
PQ1 interactions position-free. Add and verify another profile for another action.

Guard bytes and the original layer stack restore on success, failure and a
debugger stop, with checked readback. An uncertain restoration poisons and closes
the session; it never returns success. Checkpoints refuse an active or unrestored
temporary guard. Runtime bindings invalidate on state load and must be resolved
again. Host policy is not taken from the restored state.

Saved scripts expose `spatial-policy` and `spatial-action`; JSON service methods
are `debug-spatial-policy` and `debug-spatial-action`. Use
the checkout-only [AGI verification replay](https://github.com/seeker-cyber-maker/fDisBull/blob/v0.22.0/examples/agi/verify_spatial.py)
with its companion `spatial_trial.py`, licensed originals, the tested native
backend and a new private work directory to reproduce the bounded PQ/KQ checks.
Tool-only source archives exclude `examples/`; obtain these helpers from the
tagged repository checkout, rather than expecting them inside a package.

## AGI picture scope and verification

`agi_picture.extract_v2_resource` and `decode_picture` inspect a bounded AGI v2
picture stream and return separate 160 × 168 visual and priority planes. The
decoder targets the 2.915/2.917 behavioral profile, rejects malformed or unsupported
input and does not implement an AGI VM. Its command semantics are documented in
the [AGI picture specification](https://peterkelly.github.io/agi-re/spec/picture_resources.html).
The distinction between control pixels, water and trigger behavior is reflected
in [ScummVM's AGI checks](https://github.com/scummvm/scummvm/blob/master/engines/agi/checks.cpp).
Original-game probes remain the authority for the claimed PQ/KQ behavior.

A picture plane does not recover horizon, live block rectangles, moving objects,
actor water/land flags or scripted hazards. Keep unresolved context unknown or
conservatively excluded. The [verification record](VERIFICATION-SPATIAL-2026-10-29.md)
records an actual moat failure as well as the successful guarded refusal. No
whole-room equivalence, complete AGI interpretation or whole-game fair-play run
is claimed.
