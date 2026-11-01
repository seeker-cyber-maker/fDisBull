# Scene edges, object extents and expected off-screen data

The coordinate-domain audit keeps **world, room, collision coverage and viewport**
bounds separate. It measures an object's rendered and collision extents in one
explicitly named coordinate system, preserving the original signed bounds before
computing a clipped display copy. An origin inside a viewport does not imply
that the whole sprite is inside it. A baseline collision footprint does not
stand in for a sprite rectangle.

This is an offline layout inspection. Its reports and expected-margin policies
do not change movement masks, qualify teleport destinations, bypass physical
proximity or relax fair-play mode. A source seam, an extent overhang and a native
crossing are different findings.

## Describe the coordinate domains

The pure API is:

```python
from fdisbull.scene_domains import audit_coordinate_domains
report = audit_coordinate_domains(descriptor, max_checks=4096)
```

A `fdisbull-coordinate-domains-1` descriptor contains:

| Field | Meaning |
| --- | --- |
| `space` | Explicit `name` and `unit`, common to every supplied rectangle and pose |
| `bounds` | Separate nullable `world`, `room`, `collision` and `viewport` rectangles |
| `objects` | Stable `id`, `role`, nullable `pose`, and independent local `render`/`collision` rectangles |
| `expectations` | Scoped expected mechanisms with maximum overflow margins and an evidence-status label |
| `alerts` | Whether unexplained extent relations raise anomaly flags |
| `provenance` | Declared source/context/evidence notes; not an authentication mechanism |

All rectangles are nonempty, half-open integer bounds `[left,top,right,bottom)`.
Local object rectangles are relative to their pose. Signed off-screen positions
are retained; they are not rejected by the on-screen action-mask rasterizer.
Unknown bounds, camera conversions or footprints use `null`. The audit does not
infer a screen transform from a world position, tile count or screenshot size.
Wrapping and elevation conversions also require explicit qualified adapters.

Each object-part/domain relation reports raw local and absolute bounds,
overflow on each side, clipped bounds, disposition, missing facts, the matched
expectation and any suppressed flag. Contained geometry does not mean safe
terrain. Unknown geometry remains unknown when alerts are disabled.

`complete` means all requested comparisons were performed. Read the separate
unknown counts before drawing a conclusion. Budget exhaustion preserves partial
results with `complete:false`; the summary then counts examined relations only.
The implementation does not allocate world-sized images. Input JSON, object and
rule counts, coordinates and comparisons are bounded.

## Expected mechanisms remain visible

Here is an **authored illustration**, not a claim of a verified NES adapter:

```json
{
  "format": "fdisbull-coordinate-domains-1",
  "space": {"name": "scrolling-example", "unit": "pixel"},
  "bounds": {
    "world": [0, 0, 512, 240], "room": null,
    "collision": null, "viewport": [0, 0, 256, 240]
  },
  "objects": [{
    "id": "next-column", "role": "prefetch", "pose": [256, 0],
    "render": [0, 0, 8, 240], "collision": null
  }],
  "expectations": [{
    "id": "scroll-buffer", "mechanism": "scroll-prefetch",
    "roles": ["prefetch"], "domains": ["viewport"], "parts": ["render"],
    "max_margins": {"left": 0, "top": 0, "right": 8, "bottom": 0},
    "reason": "Declared next-column staging; verify against this target.",
    "evidence_status": "declared"
  }],
  "alerts": true,
  "provenance": {"scope": "Authored example; no native execution."}
}
```

The viewport overflow remains a layout notice, with disposition `expected`
and no anomaly flag. A different role, another domain, or a larger margin does
not inherit this exception. Set `alerts:false` to suppress flags globally while
retaining geometry and notices. Platform names never create an automatic
exception.

The [NES PPU programmer reference](https://www.nesdev.org/wiki/PPU_programmer_reference)
describes scroll-controlled views of nametable data and edge masking. Such
rendering arrangements motivate separate viewport and staging declarations;
they do not establish a game's collision coverage or an automatic safe margin.

## Persist and inspect the same definition

Store the descriptor as optional `coordinate_domains` in a scene definition:

```python
definition["coordinate_domains"] = descriptor
saved = project.debug_save_scene("river", definition)
result = project.debug_scene_domain_audit(saved["id"])
```

It is hashed with the immutable scene revision and travels in the existing
portable scene bundle. Supporting images still use the scene reference and
object evidence mechanisms; domain provenance does not introduce additional
executable files or automatically resolved artifact pointers. Imported snapshots
remain historical. A stored pose is not a fresh live pose after a camera change,
checkpoint restoration or another model turn.

Spatial-map documents can carry the same optional field. Their descriptor must
use the map's named space/unit, and a known room rectangle must match its
dimensions. The original `known`, `safe`, `layers` and actor masks are preserved.

```python
project.debug_spatial_domain_audit(map_revision, max_checks=4096)
```

Both methods are available offline in Python, JSON requests and the CLI:

```sh
fdisbull debug-scene-domain-audit private.fdb river --max-checks 4096
fdisbull debug-spatial-domain-audit private.fdb MAP_REVISION
```

Large reports use the existing core output-artifact handles. Select
`/audit/summary` for inexpensive inspection, then retrieve the relevant relations.
The stored wrappers explicitly return `historical_only:true`,
`live_state_verified:false` and `navigation_authority:"none"`. A legacy definition
without this field returns `not_defined`, rather than an all-clear conclusion.

## KQ1: what the river evidence actually shows

The recovered recreation archives identify an eastern-edge **room 41 → 40**
water-walk. The selected restored request moves through `(152,90)`, precisely
aligns to `(154,90)`, then sends ordinary Down and reaches room 40 at `(154,47)`.
It is checkpointed continuation evidence, with earlier exploration retained;
it is not an uninterrupted fresh/TAS-equivalent run.

The retained local native witness independently supplies adjacent fresh-game
samples at the same `y=109`:

| Origin | Six-unit baseline | Source priority values | Observed water flag |
| --- | --- | --- | --- |
| `(154,109)` | `[154,160)` | `3,3,3,3,3,15` | false |
| `(153,109)` | `[153,159)` | `3,3,3,3,3,3` | true |

Both rectangles are contained in the picture's `[0,160) × [0,168)` domain.
The first touches its right edge with **zero overhang**. Thus an extent-only
audit correctly reports containment; the source edge-seam scan exposes the
passability contrast. The original collision routine was not instruction-traced,
so the decoded-priority explanation remains separate from the observed outcome.
See the [earlier native river record](AGI_GOAT_BRANCHES.md) and this follow-up's
[sanitized receipt](evidence/scene-coordinate-domains-2026-11-01/receipt.json).

The user's recreation did not retain a room-39 observation in its exported
request histories. The separately qualified [room-39 corner clip](AGI_BRIDGE_CLIP.md)
is another case, at `(72,88)`. Its new export automatically includes layout
provenance and a source edge notice, while preserving all three action programs.

The scanner previously required a *mixed-water* outer baseline. That missed a
fully dry border beside water. It now includes both forms. PIC39 yields 82
bottom-row candidates at `y=167`, `x=5..86`, against an all-water inward row166.
Those bottom-row walking routes remain unqualified by the recovered records;
the prepared exploratory controller was never launched.

AGI's 168-row picture and the whole 200-row screenshot are separate domains.
In the inspected stored mode, picture row167 maps to display row175. It must
not be described as a row below the full screenshot. Source/local coordinates,
sprite extents and viewport mapping need their own evidence.

## Reuse world inventories without inventing geometry

The reviewed [Syndicate/Civilization examples in MR !24](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/24)
at `121ce8274ebdb731349d0577f850959f8affb412` are custom world representations.
A camera movement does not create a new world room. New pure example adapters
in `examples/scene_domains/world_adapters.py` preserve their distinctions:

- `syndicate_domains` preserves raw XY at 256 units/tile, Z at 128 units/layer
  and stacked identities. A matching map-model is needed for world bounds.
  Isometric viewport transforms and object footprints remain unknown.
- `civilization_domains` inventories the 80×50 tile world, cities, `(civ,slot)`
  units and resource points. The inspected saved world has 443 such objects.
  Its 3,544 extent relationships stay unknown because footprints are absent.
- `syndicate_destination_inventory` retains declared diagnostic anchors and
  source candidate-route statuses. It preserves elevation and exact units;
  safety and execution remain unknown. It dispatches no movement or teleport.

Use the existing known/safe spatial masks, qualified footprints and conditional
connectors for path candidates. Keep a named diagnostic anchor, a static
candidate, an observed placement and a qualified interaction as separate facts.
Successful placement does not by itself establish a walkable route or an
interaction. Cross-elevation connectors and Civilization movement rules need
their own qualification.

Original game/story files, archives, states, databases, full world documents,
raw captures and generated scene content remain private. This follow-up changes
engine source and authored examples; it does not release or install a version.
