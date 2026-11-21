# Reuse the recovered AITD movement and menu work

Reviewed 17 November 2026. The previous Alone in the Dark investigation contains
useful movement, object-manipulation and menu adapters. This continuation
recovered their actual source and verified the preserved artifact hashes.
It did not run AITD or qualify those adapters inside DotBox.

Use this work to connect the existing DotBox scene, navigation and recovery
contracts to a small original-game interaction. The current package does not
include an AITD adapter or its private game calibration.

## Recovered evidence

The retained archive is `fdisbull-thread-source-and-reports-20261117.zip`,
2,257,634 bytes, SHA-256
`a03860f21a790e59b573df1061ad82a7079c610dcfdd82acef0dd2f0003bff7f`.
All 69 entries in its `ARTIFACTS.json` matched their recorded sizes and hashes.
The ZIP has 71 members including that manifest and its preservation README.

| Material | Freshly established scope |
| --- | --- |
| `aitd-z-continued/deliverable/` | Eight preserved Python files, including `attic_z/planner.py`, `native.py`, `aitd_harness.py` and `aitd_objects.py`. This is a working-tree snapshot; completeness is not implied. |
| `fdisbull-aitd-original-harness-20261104.zip` | Adapter source, reference-calibration helper, authored tests and retained trial receipts. The private scene images and actor profile are separate prerequisites. |
| `fdisbull-aitd-objects-and-portals-20261104.zip` | Selected persistent-object, active-actor and inventory readers, original-input operations and a bounded portal investigation. |
| `fdisbull-menu-event-discovery-20261107.zip` | Generic selector leads, a read-only interaction classifier and an experimental one-input observation collector. |

The original harness's 4 November report records 27 authored test passes and
two original-game replays taking 28.449 and 26.739 seconds. Those are historical
results for a prepared route on fDisBull 0.31.1, using the selected GOG CD
edition, Emily and the initial attic. They are neither fresh DotBox results nor
cold-agent learning times. Source retrieval and hash verification do not renew
native qualification.

18 November follow-up: the exact standalone menu/event ZIP was recovered again
and verified independently, including all 24 checksum entries and nine source
manifest outputs. See [the corrected XCOM recovery scope](XCOM_REUSE.md).
That follow-up did not repeat this container's historical 69-entry check or
recover the separate private game profiles. A source archive's availability
does not establish its integration into a selected release or DotBox.

Keep original reference images, signatures, saves, RAM and other private game
evidence outside Git. The authored source and its reports identify those
dependencies without supplying them in the public package.

## Walking: reuse the controller boundary

The recovered `attic_z/native.py` supplies `plan_walk`, `_route`, `go_point`,
`turn_to` and `step`. `plan_walk` reads current solid-actor bounds and inflates
them for the player, then uses cardinal A* on a finite X/Z grid. It retains
endpoints and bends as waypoints rather than cutting diagonal shortcuts through
furniture. The original adapter uses a 200-unit pitch and a 310-unit margin;
these are target calibration values, not defaults for other games.

The executor turns and walks using ordinary keyboard input, then reads position
and heading. It bounds turns and waypoint attempts and detects repeated stalls,
movement away from the target, unexpected room changes and known hazards.
This provides a concrete starting point for feedback during a long movement leg.

Its geometry is a proposal from selected observed actors. Static walls and
other engine rules remain outside that projection. Its nearest-grid endpoint
also needs a connection from the actual actor position. Do not promote either
the remaining grid or that connecting segment to confirmed safe ground.

DotBox should retain the [current planner's](NAVIGATION.md) explicit known/safe
areas, full collision footprint, portal exclusion, source/scene bindings and
bounded search. It also retains heading in search state to minimize turns among
equal-length routes. The recovered AITD walking helper does not supply that
turn preference. Adapt its observation and control seams around the existing
planner; recheck current hazards and input ownership throughout execution.

## Moving furniture: plan the actor's approach too

The preserved `attic_z/planner.py` has SHA-256
`240221b28d06d6aa68997738df9c843bde1dc6bd05924345c32665c3f4bbb6e3`.
Its `PushPlanner` searches actor position plus rectangular-object positions.
Each edge includes a reachable contact stance, a walk to that stance and one
cardinal object translation. Every legal stance is retained because the stance
can affect the actor's reachable region afterward. Pulling is explicit opt-in.

The abstract planner distinguishes a solved route, a budget stop and exhaustion
of its declared grid. The native continuation admits only wardrobe-to-window
and chest-to-trapdoor manipulation. It checks proposed directions, approaches
using ordinary movement and measures the original object's actual progress.
The abstract plan alone does not qualify another object, direction or pull.

Before extracting a general manipulation planner, bound flood-fill work,
generated states, objects and footprints as well as outer A* expansions.
The recovered deadline is checked around the outer search loop; that is not a
complete bound on each reachability expansion. Keep this as a separate future
slice after ordinary walking is qualified.

## Menus: small observed states and guarded actions

`calibrate_scenes.py` uses the existing `fdisbull-scene-bundle-1` format and
production `pixels` / `all` predicate evaluator. It compares every declared
predicate against every retained 320-by-200 reference frame and a black
negative. Each reference must match only its own state. Full retained frames
support refining ambiguous predicates; ordinary recognition uses sparse probes.
This is finite reference verification, not universal recognition or proof that
input is ready.

The recovered adapter provides several useful rules:

- `open_menu()` recognizes an already open menu before using Escape. A toggle
  is not an unconditional opener.
- Named actions use a current scene assertion and destination checks. Pending
  or held input and an unexpected debugger stop prevent another action.
- `select_action()` traverses observed highlighted menu states and returns to
  play. Selecting Open or Push changes the active action; performing it is a
  separate, guarded input and observed result.
- A save-derived actor signature is resolved again after loading. An earlier
  live address is not authority for a new runtime context.

The DotBox adapter must also exclude blocking foreground menus and prompts
when admitting background-room actions. Room pixels visible behind a modal do
not grant movement. Unknown or competing foreground matches need a fresh
observation before input; a background match must not win by list order.

Memory adoption, a completed rendered frame, current menu selection and input
readiness remain separate observations. This matters after both ordinary menu
transitions and [memory-only revert](RECOVERY_AND_SAVES.md). A restored position
or flag cannot establish that the old screenshot or selected menu item is still
current. Rebuild runtime bindings and obtain a fresh input lease and scene
observation before another action.

### Exclude the research save-slot replacement policy

The recovered continuation's `native.py.save()` deletes its previously owned
`SAVE0.ITD` before creating another original-game save. Its `load()` copies an
older retained save back over `SAVE0.ITD` before driving the game's Load menu.
Those are explicit host-file mutations. They do not satisfy the user's
memory-only revert requirement and must not be imported into DotBox recovery.

Reuse the movement and menu observations while keeping that research save-slot
policy outside the integration. DotBox revert restores a compatible native
machine checkpoint, leaves current disk files in place and establishes fresh
runtime bindings and observations. A separate user-selected original-game Load
action has its own semantics; it is not an implementation shortcut for revert.

## Learn menu effects without repeating uncertain input

The generic menu work is published in [fDisBull draft MR !119](
https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/119), inspected
at `c16f3fc9a11fac715f52b2cf254c4ea5f5e8463a`. Its
[method](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/c16f3fc9a11fac715f52b2cf254c4ea5f5e8463a/docs/MENU_EVENT_DISCOVERY.md)
and [classifier](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/c16f3fc9a11fac715f52b2cf254c4ea5f5e8463a/src/fdisbull/structure_events.py)
keep context changes independent from selected state changes. A control can do
both. A sampled return to its starting context remains a roundtrip, and missing
fields remain unknown. Pending work needs explicit evidence rather than a
guess based on elapsed time.

The experimental collector records intent and receipt separately, submits one
input and retains a bounded observation burst. It never retries possibly
accepted input. The classifier is read-only and grants no execution authority.
Its observations must share source, run and restoration identity and have
increasing logical times. A preceding idle interval exposes varying fields;
it does not by itself prove which effects the input caused.

This method fits DotBox's [state and outcome separation](STATEFUL_SCENES.md).
The old collector and AITD runner use fast-forward in parts of their experiment
flow; visible gameplay needs the current DotBox normal-speed and ownership
contract. The earlier shared scene guidance is preserved in [MR !89](
https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/89) at
`5935e7d41ded41d0f39b9c47292e8620fd5d4785`; its inspected status was closed,
not merged. Neither draft reference establishes package integration.

## Next bounded integration

Qualify one ordinary long walking leg and one menu selection in an isolated
original-game session. Use an already compatible source/profile, current
coordinate and collision observations, a foreground scene guard and the single
input owner's current generation. Measure actual movement and interruptions;
do not add delays to cover preparation work.

Capture a qualified memory checkpoint before the interaction. After a test
revert, show that the earlier lease, coordinate binding, menu observation and
route are stale. Acquire fresh observations and ownership before repeating the
selected action. Verify that selection and execution have their own receipts,
that a blocking menu prevents background walking, and that the newly completed
frame agrees with the admitted input context. Disk files remain outside the
revert operation. Broader room coverage and furniture manipulation can follow
once that complete boundary works.
