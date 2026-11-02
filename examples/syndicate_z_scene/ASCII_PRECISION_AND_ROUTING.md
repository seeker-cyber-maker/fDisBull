# Syndicate ASCII scene, exact coordinates, and candidate routing

Date: 31 October 2026. Local follow-up to the preserved mission-1 scene example.
This turn used its semantic snapshot and authored tests, not a new live guest.
GitLab was read; GitHub was not contacted and no remote content was changed.

## GitLab delivery check

Project `brewster-jennings-group/fdisbull` (88349936), main
`7a5caaa4258d826b63fc2546b107dc9fc432e667`, has two merge requests in the
complete all-states listing: !1 native ARM64 investigation and !2 capability
reporting. Neither is the Syndicate scene. The complete 93-branch listing lacks
`research/syndicate-spatial-z-20261031`. The pinned main `examples/` listing also
lacks `syndicate_z_scene`. The template project has no MRs or Syndicate-named
branch. This distinguishes branch-history copying from review-object migration.

Earlier sources *are* present as `pr/69/diagnostic-recovery-assets-20261030`
(`641b7e9`) and `pr/81/syndicate-graphics-diagnostic-friction-20261031`
(`7f37c43`). Their presence does not publish the later locally prepared scene.
The check is a snapshot, not continuing synchronization. Details are in
`evidence/ascii/gitlab-status.json`.

## Keep visual documentation; add an agent projection

The existing HTML, PNG, SVG, semantic terrain model and initial scene JSON are
preserved byte-for-byte. New `public/mission-ascii.txt` is a bounded district
view. `public/team-subtile-ascii.txt` shows the same scene at quarter-tile scale.
`mission-ascii.json` provides the matching coordinate and entity tables.
The old HTML retains its historical route display; it has not been changed to
consume the new planner. New route JSON is renderer-independent and can be
consumed by either presentation in a later integration.

The ASCII overlay uses a versioned origin, cell size, row/column labels, elevation
layer and positive-down Y convention. `r16c36`, for example, means an interval in
one named viewport, not an absolute game point. Resolving a cell returns a
half-open bounding box and **no default execution coordinate**. Stale overlay
identities and invalid cells reject. Zooming repeats existing tile evidence;
it does not manufacture sub-tile collision measurements.

Glyphs: `@` focused agent, `A` other agents, `c` civilians, `p` police, `g` guards,
`v` vehicles, `+` doors, `!` mission target, `t` trees, `w` window classes,
`i` loose items, `*` stacks, `:` conditional route. `.` means model-admitted
terrain and `?` means excluded/unresolved, not a proved wall. Selected/critical
glyphs have priority, but **every stacked entity remains in the keyed table**.
Owned weapons are retained in scene/inventory data rather than hiding their
owners behind weapon glyphs. The view is still global diagnostic information,
not a fair-play line-of-sight claim.

## Three separate coordinate concepts

1. Engine coordinates: exact integer X/Y in 1/256-tile units and Z in 1/128-level
   units. These drive state comparisons and destinations.
2. Terrain cells: coarse graph nodes used by the present conditional model.
3. Overlay cells: a display transform with a recorded origin, zoom and lifetime.

The actual saved scene places person-0 and person-1 in the same tile `(91,41)`:

| Entity | Raw XYZ | Exact world XYZ | XY offsets inside tile |
| --- | --- | --- | --- |
| person-0 | 23476,10668,256 | 91.703125,41.671875,2 | 180,172 |
| person-1 | 23420,10516,256 | 91.484375,41.078125,2 | 124,20 |

They must not be collapsed. One raw-unit move in a tile remains a distinct
position. The provider's new no-op branch only suppresses a teleport when the
actor **and its observed attachments** are already at the exact requested raw
point. Unsettled attachments request observation instead of replaying writes.
The helper also exposes an explicit pending-action decision. This control-flow
change was checked with authored controller fixtures, not a fresh native run.

## Plan over the world, not the ASCII characters or PNG

`plan_approach` generates a bounded four-neighbor candidate path to a neighboring
cell of a stable entity, rather than blindly aiming at the center of a car.
It retains the exact actor start, target position, final proposed approach point,
map/source identity, raw waypoint coordinates, excluded cells/edges, and gates.
The target position and approach position are different facts. Arrival at an
approach point is not boarding, range admission or successful interaction.

The saved scene's new candidate car approach is `(61.5,35.5,2)`, raw
`[15744,9088,256]`, reached in 36 grid steps. The target approach is
`(64.5,31.5,2)`, raw `[16512,8064,256]`, reached in37 steps with door object-3
as an unresolved condition. These counts differ from the earlier37/38 because
that earlier model routed to the entity's cell; these proposals stop adjacent.
The numbers are not measured travel times or demonstrated traversals.

Known entity-center cells are excluded as a planning preference, not a full
collision-footprint model. Heights are not flattened and missing connectors
return an explicit unresolved result. Unknown door state is not silently
converted to open. Blocking a failed directed edge produces another candidate
route without discarding the previous failure. Dynamic blockers, actor clearance,
turning, exact gate thresholds, slopes and sub-tile steering remain incomplete.

Walking and assisted travel should share the destination/route contract while
using separate executors. Teleportation can skip intermediate positions but
cannot certify walked edges. The present provider still exposes only its earlier
named assisted waypoints; **route proposals do not automatically execute through
that provider, and native walking is not implemented**.

## Bounded feedback rather than repeated movement spam

The decision-only `ProgressWatch` consumes fresh revisioned positions and an
explicit next waypoint. It preserves progress within the same tile, detects
stagnation after a configured bound and A-B-A-B oscillation, and holds for target
movement, a regressed route or an unqualified gate. It checks an intermediate
waypoint rather than distance to the final target, so a necessary detour does
not automatically look like failure. Exact approach arrival is distinct from
attachment settlement and later interaction success.

The watchdog never issues input or retries a teleport. Once halted it requires
a new plan, rather than resetting itself into another endless retry. A future
executor must bind it to the live session/plan, qualify gate and attachment
readiness, cap total replans, retain failed-edge reasons and refresh moving
obstacles. It must stop/report when no supported alternative exists. Successful
unit tests do not establish that the original game's pathfinder no longer sticks.

## Working commands

With the existing player installed, from the separate local analysis-delivery root:

```sh
python -m fdisbull_player --backend-command "python tools/z_provider.py --snapshot public/mission-1-observation.json --map-model public/map-model.json"
```

Use `examine map`, `examine route to car`, or `examine path to mission target`.
These are passive snapshot operations. `--map-model` refuses live-config mode;
live display still uses the previously source-bound decoded terrain path.
For an ASCII dump without any player dependency:

```sh
python tools/agent_map.py --snapshot public/mission-1-observation.json --map-model public/map-model.json --target vehicle-0 --origin 14080 6400 --width 42 --height 22
python tools/agent_map.py --snapshot public/mission-1-observation.json --map-model public/map-model.json --subdivisions 4 --width 25 --height 13
```

## Verification

63 authored checks passed: the preserved27 plus36 new checks. The first run
caught an out-of-bounds renderer request on a small authored map (five failures
sharing that cause); explicit display-boundary handling corrected it. Final
checks cover exact no-ops versus same-cell movement, stacked identities,
viewport lifetimes, elevation, route/gate conditions, failed-edge exclusion,
stall/oscillation detection and the actual player's passive resolver.

Five real player commands were also replayed against the saved semantic scene.
This is fresh **offline player** acceptance, not original-game execution.
The installed player0.26.0 was extracted privately from the supplied wheel;
no shared installation was changed. No current GitLab source suite or CI was
run. The earlier native report remains historical and its tests are not claimed
for this code revision.

## Pending implementation acceptance

- ASCII and graphical consumers use the same map, IDs, layer and route identity.
- Preserve full raw precision even when a glyph cell contains multiple entities.
- Reject stale overlay/route references; cell selection alone is not a destination.
- Exact no-op and pending-effect reconciliation never repeat committed writes.
- Physical movement uses bounded steering and observed progress, then qualified
  replanning or an explicit blocked result; never indefinite identical commands.
- Interaction approaches include clearance, current gate/occupancy state and
  the original interaction preconditions before claiming boarding or completion.
- Visibility and assist policy remain explicit; a diagnostic map is not fair play.

No new GitLab MR was created. The updated local draft and add-only patch are
provided for review and future publication, with older artifacts retained.
