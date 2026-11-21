# Fewer turns, longer useful movement

Decision: 17 November 2026. Prefer long straight movement legs over repeated
stops and direction changes when the route remains useful and traversable.
Movement advances the player's selected intent and provides natural time for
scene preparation. Do not introduce detours or slow the game to manufacture
that time.

Version `0.1.0.dev5` adds an offline, bounded walking-route planner. It reuses
`fdisbull-spatial-map-1` geometry and checks the supplied actor footprint against
known/safe areas, obstacles and hazards. It does not observe or move a live
actor, emit keyboard events, write coordinates or qualify a car-driving model.

## Grow movement and scene-entry capabilities

Use the cheapest already qualified route that answers the current question.
The following stages add reusable capabilities; they do not require repeating
earlier experiments or completing every stage before ordinary play. The
[behavior and entry-point guide](BEHAVIOR_AND_ENTRY_POINTS.md) describes how
several invocation routes can serve the same semantic operation.

1. **Locate position candidates.** Compare bounded observations at rest and
   during a short movement. Keep world coordinates, sprite/render coordinates,
   camera offsets and unrelated counters distinct until evidence identifies
   their roles. Record the source, object identity, units and candidate mapping.
2. **Verify ordinary motion.** Use the game's normal controls and compare the
   candidate fields with observed direction, displacement and stopping. Include
   an idle contrast where useful. Qualify only the axes, ranges and contexts
   actually established; input acceptance alone does not establish movement.
3. **Try a reversible same-room perturbation.** In an isolated research guest,
   change a small qualified field range with expected-old-value guards and a
   bounded observation. Retain the before values and a qualified restoration
   path. Restore and verify the declared scope; a coordinate correction is not
   full-machine rewind. Record partial effects and stop if recovery is unresolved.
4. **Establish coherent placement.** Recover the smallest relevant set of
   position, movement, collision, camera or script dependencies needed for a
   useful anchor. Let the engine adopt the placement, then check context,
   interaction readiness and the requested outcome. A changed coordinate and
   matching screenshot alone do not establish every dependent state.
5. **Observe a normal crossing.** Approach and cross a selected portal through
   ordinary controls. Retain the event and relevant before/during/after evidence:
   location, actor/resource bindings, entry setup, flags, timers and continuation
   as needed. Separate transition effects from concurrent autonomous changes;
   one large memory diff is not a reusable entry recipe.
6. **Reuse original room entry.** Recover the applicable setup or initialization
   operation, its prerequisites and arguments, and its continuation to a usable
   destination. A supported shortcut may place the actor at a known portal and
   use its original input, or invoke a separately qualified original setup path.
   Writing a scene ID or copying an entire observed delta is insufficient.
7. **Construct a useful research state.** Helpers may combine recovered entry
   and state-setting operations to investigate a location beyond normal story
   progression. Establish the runtime coherence needed by the experiment and
   record every imposed prerequisite, retained effect and unresolved dependency.
   Such a state does not prove that the player can reach it through ordinary play.

Keep these experiments in the helper's own guest and mutable files. Preserve
their branch identity and distinguish imposed state from observed consequences;
their results can inform the model without advancing the player's progress.
Missing initialization limits the shortcut's claims and leaves the working
ordinary route available. Visible play continues through the selected original
movement/input route under current ownership; helper shortcuts do not authorize
teleporting the player or skipping graphical traversal.

The inspected fDisBull [assisted-travel implementation](https://github.com/seeker-cyber-maker/fDisBull/blob/ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd/src/fdisbull/assisted_travel.py)
already supplies guarded same-room placement and placement at a known portal
followed by original transition input. It requires current scene/runtime
bindings, rejects writes to the declared room field, advances the guest after
writes and observes the destination. It does not discover those bindings or
initialize arbitrary rooms, and failures retain actual partial effects without
implying rollback. This is reusable source, not a new DotBox control or a passed
teleportation test. See [recovery](RECOVERY_AND_SAVES.md) for state restoration
and qualified original Save/Load entry.

## Planning policy

The initial policy minimizes distance first, then turns among routes of the
same distance. Heading is part of search state; reaching a cell from different
directions can change the cost of the remaining route. Search is bounded and
returns distinct results for an unclear endpoint, exhausted budget, no route
and a found route.

Collinear steps are compressed into long geometric legs. A clear straight
crossing can therefore be represented by one leg instead of dozens of separate
point commands. Only cardinal directions are supported in this slice. Do not
smooth a route into arbitrary slopes that the actual control harness cannot
execute. Unit diagonals can be added after their movement and corner-clearance
rules are qualified.

This initial preference needs no invented timing constant. A later measured
turn/stop penalty can justify a small detour when it actually improves travel.
Report that policy explicitly; shortest distance and minimum execution time
are different objectives. Keep the player's goal and hazards ahead of cosmetic
smoothness.

## What a clear map does and does not establish

| Input | Required interpretation |
| --- | --- |
| Source, room and coordinate space | Match the selected game and scene; game x/y, rendered pixels and host-window coordinates are distinct. |
| Actor footprint and anchor | Model actual collision geometry, not a guessed point or an unqualified sprite rectangle. |
| Known and safe areas | Unknown stays unavailable. Known geometry alone does not establish safety. |
| Obstacle/hazard conditions | Use current observed values; missing or unknown conditions remain unavailable. |
| Objects | Visual presence does not establish blocking behavior. Include collision in an obstacle layer when qualified. |
| Portals | The planner blocks them by default. Plan to an approach point, then handle the intended crossing as a separate transition. |
| Evidence | Supplied observations support the map; hashes preserve identity without proving its interpretation or live freshness. |

Unselected exits cannot become convenient shortcuts through another room. A
portal can trigger before the actor's anchor enters its region, so check the
whole supplied footprint. After a room transition, discard/rebind the old room
route. Static AGI picture/priority information can help propose geometry, but
dynamic objects, script blocks, horizon and water/hazard rules still need the
selected runtime's interpretation.

## Bind the plan to the observed timeline

`plan_movement` requires a stateful scene packet. It checks game-source and room
agreement and retains the exact map digest, original map context, conditions,
scene digest/observation and provider session/branch/revision. The map's context
remains its own provenance; it is not silently relabeled as a new observation.
The caller is responsible for establishing that the map applies to that scene.

`check_movement_plan` repeats bounded deterministic planning against the supplied
current inputs and verifies the resulting proposal. Changed maps, conditions,
scene packets or rewind branches invalidate an old plan. Editing the path or
its legs does not preserve its validity. This is an offline consistency check;
the executor must still refresh the live provider and ownership before input.

The result is a proposal with `execution=not_performed`. It is not arrival,
interaction success, a movement lease or a promise that the game will follow
the planned path. A valid stored scene can be old in the live game.

After exporting the kit into a new private directory, the authored example can
be used without a game or live controller:

```sh
dotbox kit-export --directory /tmp/dotbox-route-example
dotbox route plan /tmp/dotbox-route-example/examples/navigation_room.json --scene /tmp/dotbox-route-example/examples/scene_window_closed.json --start 1 3 --goal 10 3 > /tmp/dotbox-route-example/plan.json
dotbox route check /tmp/dotbox-route-example/plan.json --map /tmp/dotbox-route-example/examples/navigation_room.json --scene /tmp/dotbox-route-example/examples/scene_window_closed.json
```

Use a new export destination if it exists. `--conditions FILE` supplies a
bounded JSON object of current boolean/unknown condition assertions;
`--max-nodes` bounds search. The check command accepts the exact successful
CLI envelope or a raw plan. All files in this example are authored fixtures;
their coordinates and route references are not controls for a commercial game.

## Connect long legs to the existing TAS/control machinery

The existing fDisBull `BoundedNativeController.align` is a useful one-leg
reference: issue ordinary input, observe debugger x/y read-only, and check
progress, target ranges, drift, overshoot and settled state. Its frame timeline
also supplies scheduled key edges and bounded advancement. These remain
integration references; they have not been imported as a second live input
owner into DotBox.

The [recovered AITD source](AITD_REUSE.md) supplies another concrete adapter:
cardinal walking plans around observed actor bounds, waypoints at bends, and
ordinary keyboard movement checked against current position and heading.
Its rectangle push planner additionally includes the actor's approach to a
contact stance. Retain DotBox's stronger footprint, known/safe-area, portal and
timeline admission, plus its distance-then-turn cost. The AITD actor projection
does not recover static walls, and its coarse manipulation plan only advises
two separately qualified original-game routes.

A long geometric leg must remain interruptible. The future executor should
retain its direction while observing at bounded intervals where supported,
without visibly stopping at every observation. Do not turn the leg into one
uninterruptible queued hold. Current DotBox fixed controls remain bounded to
their existing input contract. Frame-edge/native helpers must carry the current
control generation and use the qualified ownership path.

Distinguish held-key controls from latched direction. Repeating a direction in
a latched game may stop the actor; an automatic stop at a room boundary can make
another toggle restart movement. Observe settled state before cleanup. On a
stall, unexpected coordinate jump, overshoot, source/context change or takeover,
stop admitting the old route and reconcile what happened. Do not automatically
replay an uncertain input.

Coordinate arrival, rendered arrival, interaction range, input readiness and
successful room transition are separate observations. Target ranges/crossings
are usually more useful than exact equality when an update can skip a pixel.
An applicable known fallback should remain available while a better route or
interaction slice is prepared.

The user's exact earlier x/y TAS script is still unidentified. The AITD source
recovery establishes the preserved walking and manipulation adapters; it does
not establish that either is that script. The installed fDisBull
controller/timeline interfaces were also inspected. Its broad `move` helper
hardcodes fast-forward and can close unresolved sessions, so that lifecycle
policy must be adapted before it can support ordinary visible play.
Coordinate-writing assisted placement remains a separate explicit operation.

## Recovery and vehicle movement

The user's selected first live controls trial is [Police Quest's locker-to-shower
route](POLICE_QUEST_ACCEPTANCE.md): perform the ordinary clothing change, close
the locker and reach the usable shower approach with fresh position and frame
evidence. The EGA shower is within the locker-room overview; a referenced helper
LOGIC is not a room transition. Arrival is the requested endpoint; activating
the shower is a separate optional interaction. One ordinary-input functional
run passed on the cloud Linux computer on 17 November 2026, including shower
activation and turn-off afterward. It did not qualify a live coordinate binding
or repeatable route/timing harness. Those qualifications, assisted placement
and the missed-briefing memory-rewind trial remain open.

A walking grid does not model vehicle speed, heading, braking distance, turn
radius or moving obstacles. Car driving needs an appropriate controller and
state model; a geometrically clear path alone does not qualify it. Rewind can
retain a failed attempt and recover before the collision once the full restore
path is qualified. Every memory restore invalidates queued movement and creates
a fresh scene branch, even when the room looks unchanged. Reobserve coordinates,
collision state, foreground menus and readiness under the new input lease before
admitting another route. Disk files are outside the revert operation.

See [recovery and saved-game evidence](RECOVERY_AND_SAVES.md) for the restore
transaction and file scope, and [continuous play](../skills/dotbox-play/references/continuous-play.md)
for movement priorities, worker deadlines and late-result handling.
