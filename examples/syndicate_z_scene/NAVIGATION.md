# Bounded original navigation (D004)

This opt-in research profile connects candidate approach plans to original
Syndicate movement order 3. It is not unrestricted autonomous walking or a
replacement pathfinder. The diagnostic adapter prepares native selection,
mouse-latch and world-hit-test input; the original game moves the actor.
It does not patch actor position/state, path buffers or instruction bytes.

## Enable explicitly in a newly owned, paused mission

Use the existing private controller and verified MAIN source. Never reuse an
old process/socket/binding merely because its addresses look familiar.

```sh
python tools/bind_scene.py \
  --controller-root /absolute/new-private-session \
  --main /absolute/private/SYNDICAT/MAIN.EXE \
  --code-base 0x1c4030 \
  --enable-original-navigation \
  --output /absolute/new-private-session/scene-binding.json
```

`0x1c4030` is the observed candidate in this investigation, not a universal
address. The binder checks every relevant relocation and code byte before it
accepts the nomination. The flag also enables the original vehicle profile.
Start the ordinary Z player with that configuration and private decoded map data
as in README.md. No protected-mode checkpoint certificate is fabricated.

```text
examine route to car
walk route to car
board car
exit car
```

The `walk` verb is absent in snapshot mode or without the explicit profile.
Approach plans are recalculated from the fresh scene. A plan's exact run,
revision, actor/target position, source-state hash and terrain identity must
match. Gate crossings remain refused, even when the door looks open. The named
mission-target route therefore remains an informative pre-input refusal where
it crosses the unresolved door condition.

## Result and failure semantics

Every waypoint is requested once. Progress uses exact integer XYZ and the
source-qualified input-loop boundary. Success requires stopped state, exact
position, coherent spatial/occupant graphs and settled attachments.
A repeated completed approach is a no-op with no input writes or guest-time
advance. This is not tile-based deduplication.

Health/state changes, target motion, stalled or oscillating movement, prolonged
movement without waypoint improvement, wrong stops and budgets produce a held
partial result. No automatic replan-and-replay or teleport fallback is provided.
Use the owning debugger to inspect, then explicitly restore a verified native
checkpoint or establish a new admitted context. Default live replay-safe Z
save/recovery is not implemented by this example.

The source-only watchdog's labels distinguish `stalled_replan` from
`moving_without_progress_hold`; neither declares a target unreachable. The
original actor can move away while entering a detour-like state. Also, a connected
terrain route can expose the actor to changing health. The current planning cost
does not account for combat or establish hazard safety.

The profile is bounded to map 1, stopped on-foot team slots 0/1, a fixed qualified
terrain identity, same-level candidate waypoints and no unresolved gate crossing.
Dynamic topology/clearance, driving, all actors/cars and normal mouse picking
remain unqualified. Per-transport timeouts can extend a route's between-operation
wall check; it is not a hard real-time deadline.

## Evidence and tests

Recorded D004 native acceptance includes two independently restored four-segment walks
on the same car approach, original board/exit for each actor, duplicate no-ops,
a held long route after a health change, and stale/gate/held-action controls.
The separate second-door traversal and excluded-cell diagnostic are not executed
by removing the generic route's gate guards.

Run `python -m unittest discover -s tests -v` for the current cumulative suite.
D004 historically reported **140 authored tests** at its cut; cumulative F002
has 240. These tests do not reproduce the original game. Native receipts and limits are in
the D004 research report and its sanitized evidence packet. Original resources,
raw logs/memory, screenshots and checkpoints are private inputs, not repository
fixtures. Graphical map documentation remains unchanged.
