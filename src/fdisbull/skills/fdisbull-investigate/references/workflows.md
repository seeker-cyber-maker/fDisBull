# Choose an investigation workflow

Use this reference to route a task to the smallest relevant fDisBull surface.
Every command uses caller-selected paths. The Python package does not include an
emulator, target executable, game files, saved states or project databases.

Contents: [Outcome](#start-from-the-users-outcome),
[static](#static-analysis), [native](#native-investigation),
[scenes](#scenes-maps-and-movement),
[guide checklist](#seed-scene-hypotheses-from-guides),
[text](#player-and-live-text-workflows),
[retained knowledge](#retain-knowledge-without-overstating-it).

## Start from the user's outcome

| Need | Starting point | Evidence boundary |
| --- | --- | --- |
| Identify or analyze an executable | `identify`, `inspect`, `import`, `analyze`, `analysis-status`, `status`, `functions`, `disasm`, `xrefs` | Static decoder facts and stored analysis only; candidates and budget limits stay labeled. |
| Observe actual program behavior | `debug PROJECT ...` plus the appropriate `Project.debugger()` or JSON methods | Requires a compatible external backend and an authorized target. Verify live source/version binding and real guest effects. |
| Reuse visible controls or map a route | Versioned scenes, spatial maps and `session.move()` | Authored geometry or observed segments; unknown coverage and target behavior remain separate. |
| Expose a small text interface | `fdisbull text-host CONFIG` with a qualified local projection | The projection is not a game parser or full-game reconstruction; action freshness and completion are backend-owned. |
| Run an authored text slice | `python -m fdisbull_player --package FILE` | The independent player evaluates the declared slice; this does not emulate or recover the source game. |
| Qualify a supported code-to-semantics block | UDL/UIL/UDC commands and APIs | Only the exact supported source span and declared effect boundary; see [udl-uil-udc.md](udl-uil-udc.md). |
| Inspect AGI 2.917 logic bytes | `agi-logic LOGDIR VOLUME_DIRECTORY LOGIC --profile 2.917` | Bounded, read-only partial decoding; it does not establish that the logic was loaded or executed. |

For concise command routes, read `docs/AGENT_QUICKSTART.md` in a source checkout.
The command `fdisbull methods` lists the JSON interface. For detailed static
behavior, live debugger setup or target-specific contracts, use the relevant
source documentation rather than guessing flags.

## Static analysis

For an executable file, inspect before importing so you can confirm format and
architecture. COM images require explicit `--image com`; a filename suffix is
not format evidence. Start recursive analysis with a reasonable instruction
budget and inspect `analysis-status` or `status` for remaining work. A bounded
run does not establish convergence. Use `render` only for stored project state;
it does not operate a GUI or launch a target.

Static call-flow can screen for a script interpreter, asset reader or dispatch
table. A data file that resembles code is still not proof of a load or execution
edge. Read the interpreter section of
[methodology.md](methodology.md) when the task needs that distinction.

## Native investigation

Launch only with the user's actual executable, game directory, byte version and
compatible backend. DOS, PE/Wine and machine-level backends have different
capabilities; check the selected run before using optional features. Live JSON
operations require a retained server session (`serve` alone or `debug`), not a
one-shot `request` call. See `docs/DOSBOX_DEBUGGER.md` and the relevant backend
guide. A debugger capability does not imply target or game support.

Prefer ordinary input with explicit guest-time and wall-time bounds. Check
parser/readiness and input consumption before interpreting a response. Native
screenshots and traces are stored in the project and can be exported later;
exporting an existing artifact is different from claiming a fresh capture.
Checkpoint restore does not roll back mounted host files or external services.

## Scenes, maps and movement

Use scenes for versioned screen context, recognition masks, readiness and
guarded input actions. Use spatial maps for game-unit known/safe regions, actor
footprints, obstacles, hazards and interaction zones. These models answer
different questions. See [scenes.md](scenes.md) for scene authoring and
[runtime-navigation.md](runtime-navigation.md) for spatial policies, movement
and observation choices.

The default route is ordinary movement. Assisted placement and story-mode guard
waivers are explicit interventions with narrower contracts, not equivalent
forms of physical traversal. Unknown map cells are not safe; map proposals do
not guarantee engine movement or survival. A state edit can test a mechanism
without showing that a player can reach it.

## Seed scene hypotheses from guides

Use an available guide, walkthrough, manual, map or video when it can reduce the
next discovery cost. Start with the current scene and a small likely frontier;
do not require a whole-game guide before offering a useful action. Respect any
task restriction on spoilers or outside information. Record the source URL or
document/section, video timestamp when relevant, edition/platform/language and
accessed material. A transcript or summary is not evidence of frames not viewed.

Compile your own concise investigation guide as a scene graph and checklist.
Extract likely views, objects, exits, actions, inventory dependencies, expected
effects and transitions. Split compressed instructions into candidate steps:
"oil the mechanism" may involve selecting an item, opening a closeup, applying
it to a different target and dismissing a response. Separate what the guide
actually states from your inferred implementation. Route order alone does not
establish a necessary prerequisite. An earlier authored adaptation is also a
hypothesis source, not independent confirmation of its source guides.

Keep one row per useful hypothesis in private project evidence; a Markdown
table or existing notes suffice. This is not a new runtime scene schema.

| Context/view | Predicted object/action and guard/effect | Origin/version | Source binding/evidence | Runtime evidence, if required | Disposition and next question |
| --- | --- | --- | --- | --- | --- |
| Current view or candidate closeup | Preserve the external claim and mark extra inferred steps | Guide section, prior note or video timestamp | Unknown until resource, handler, predicates and relevant effects are bound | Unknown unless observed under a recorded context | Expected, located, contradicted, or conditional claim accepted; retain the unresolved question |

Use this checklist to choose probes:

1. Locate likely labels, objects, views and exits in text/resources and dispatch
   structures. Guide or video coordinates are candidate cues, not native target
   geometry. Bind geometry and live transforms separately for harness clicks.
2. Match the claimed prerequisite and outcome to relevant source conditions,
   typed state changes and helper dependencies. Reuse accepted primitives and
   summaries instead of repeating settled verification.
3. Inspect adjacent source branches for wrong-item, repeat, refusal, optional
   and alternate-route behavior relevant to the selected claim. Add discoveries
   absent from the guide; absence from a walkthrough does not mean absence in
   the game. Do not expand this into exhaustive whole-game testing by default.
4. Preserve contradictions and version differences. A copied claim in several
   guides is not several independent witnesses. Do not reshape source evidence
   to fit a plausible story or silently promote inferred object names.
5. Mark what is usable and the next cheapest unresolved question. Track
   conditional code acceptance, ordinary reachability, current readiness and
   persistence separately. Finishing guide steps establishes only coverage of
   those steps, not complete scene or game recovery.

Keep the guide hypotheses and their evidence history when writing a corrected
walkthrough. Player narration may use only appropriate current observations;
private solutions, future objects and guessed effects must not leak into it.
Measure guide reading, outline construction and analyst effort separately from
decoder/runtime time, and stop preparation when it no longer improves the next
decision. Compare time to the first accepted useful action at equal claim scope
before claiming this workflow is faster.

## Player and live text workflows

`fdisbull-player` is a separate, standard-library package. Its `--package` mode
runs an authored JSON slice; `--connect HOST:PORT` connects to a line-oriented
backend. `--live` restores and checkpoints turns, but cannot verify a remote
backend's durability. Optional external agents are trusted processes, not
sandboxed programs. Read `docs/TEXT_PLAYER.md` and `docs/PLAYER_LIVE.md` before
choosing this surface.

The debugger-backed `text-host` exposes a deliberately qualified public
projection over a live session. It needs a private configuration, project,
backend, game directory, resource root and explicit runtime witnesses. It is
single-client loopback transport without authentication or encryption; use it
only in a trusted local environment. The projection is not a secrecy or process
isolation boundary. `--fair-play` locks the host to physical movement. Otherwise
choose `--spatial-mode physical|assisted|story` explicitly for a controlled
experiment. Read `docs/TEXT_PROJECTION.md` and `docs/SPATIAL_MAPS.md`.

## Retain knowledge without overstating it

Promote verified reusable facts into versioned scene objects, named anchors,
route segments, source mappings or interaction definitions only when doing so
reduces later probe cost. Preserve the evidence and authority behind the
shortcut. Revalidate after a source/version, resource, room, backend or runtime
context change. Keep target-specific addresses, masks and paths in project
evidence rather than this reusable skill.
