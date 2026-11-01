# Choose an investigation workflow

Use this reference to route a task to the smallest relevant fDisBull surface.
Every command uses caller-selected paths. The Python package does not include an
emulator, target executable, game files, saved states or project databases.

## Contents

- [Start from the user's outcome](#start-from-the-users-outcome)
- [Static analysis](#static-analysis)
- [Native investigation](#native-investigation)
- [Scenes, maps and movement](#scenes-maps-and-movement)
- [Seed scene hypotheses from guides](#seed-scene-hypotheses-from-guides)
- [Player and live text workflows](#player-and-live-text-workflows)
- [Research-backed progression](#research-backed-progression)
- [Retain knowledge](#retain-knowledge-without-overstating-it)
- [Retrieve bounded output](#retrieve-bounded-output)

## Start from the user's outcome

| Need | Starting point | Evidence boundary |
| --- | --- | --- |
| Unpack an owned local GOG Inno Setup installer | `gog-list`, then `gog-unpack INSTALLER NEW_PRIVATE_DIRECTORY` | Native external innoextract reads payloads without Wine or running the installer; listing and hash manifests do not prove game execution or loader support. See `docs/GOG_UNPACKING.md`. |
| Identify or analyze an executable | `identify`, `inspect`, `import`, `analyze`, `analysis-status`, `status`, `functions`, `disasm`, `xrefs` | Static decoder facts and stored analysis only; candidates and budget limits stay labeled. |
| Inspect a qualified raw Z-machine v3 story | `zmachine-disasm STORY`, `zmachine-analyze STORY` | Bounded source instruction facts, separate from the generic Z scene interface. Retain unresolved calls, overlaps and worklist frontiers; a drained graph is not whole-game coverage. No native-to-guest mapping or guest project persistence is implied. |
| Observe actual program behavior | `debug PROJECT ...` plus the appropriate `Project.debugger()` or JSON methods | Requires a compatible external backend and an authorized target. Verify live source/version binding and real guest effects. |
| Reuse visible controls or map a route | Versioned scenes, spatial maps and `session.move()` | Authored geometry or observed segments; unknown coverage and target behavior remain separate. |
| Expose a small text interface | `fdisbull text-host CONFIG` with a qualified local projection | The projection is not a game parser or full-game reconstruction; action freshness and completion are backend-owned. |
| Run an authored text slice | `python -m fdisbull_player --package FILE` | The independent player evaluates the declared slice; this does not emulate or recover the source game. |
| Preserve supported Z-machine v3 behavior in an independent player | `zork-uil STORY --output PRIVATE_IR`, then `fdisbull-player --uil PRIVATE_IR` | Executable word16 IR preserves low-level operations; semantic recovery is a separate claim. Derived story content stays private. |
| Exercise the qualified Zork mailbox intent layer | `zork-intents STORY --output PRIVATE_PACKAGE`, then `fdisbull-player --intents PRIVATE_PACKAGE` | A source-bound partial semantic layer with explicit retained IR; inspect fault receipts and restore the last successful checkpoint before resuming. |
| Recover named Zork scene rules | `zork-scenes STORY --intents PRIVATE_INTENTS --output PRIVATE_PACKAGE`, then `fdisbull-player --scenes PRIVATE_PACKAGE` | Qualified Zork I R88 only: named exit and dispatch rules with live guards and explicit residual bodies. Exit selection, movement and arrival have separate boundaries. Use [scene-recovery.md](scene-recovery.md) for the investigation procedure. |
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

For installer extraction, nested images, overlays, edition comparison or media
reduction, use [formats-and-media.md](formats-and-media.md). Select optional
commands from the installed method inventory; an open proposal or a successful
container listing does not provide a missing loader or processor.

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

For a short native DOS debugging history, use `debug-rewind-start`, advance with
`debug-rewind-record`, inspect `debug-rewind-status`, then `debug-rewind` a
declared count. This records bounded next-fetch intervals with native states;
instruction retirement remains unknown. Unrecorded mutations invalidate the
cursor, and capture/byte budgets include discarded branches. It restores existing
states rather than replaying instructions; use ordinary `debug-load-state` when
the checkpoint is already known. See `docs/DEBUGGER_REWIND.md` for limits and the
local comparison procedure. Other execution backends are outside this first scope.

A DOS data watch confirms the observed access boundary, not whole-instruction
completion. Starting with 0.26, normalized DOS watch stops report
`instruction_completed=null` and `registers_stage="after-access"`. A REP copy
can yield with the same PC and a nonzero remaining count; inspect raw registers
and memory before claiming completion of the copy or the enclosing transaction.
Do not use older unconditional completion labels as that evidence.

For a rebuilt DOS backend advertising `lifecycle.dos_guest_exit`, a
`guest_exit` run result retains the selected PSP's completed DOS cleanup in
`session.stop_reason.guest_exit`; `guest_tsr` separately reports remaining
resident. Record target registers before exit because DOS has restored the
parent context at this boundary. A legacy `program_exit` on debugger closure,
a pause outside the image, or an exit interrupt alone is not this evidence.

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

Start with the current scene and a small likely frontier. A guide's labels,
objects, exits and prerequisites are hypotheses until bound to the selected
source and, where required, observed at runtime. A transcript supports its text;
visual claims need viewed frames or other direct evidence. Retain inferred
intermediate steps and discrepancies in the private scene ledger described in
[Research-backed progression](#research-backed-progression). Keep future
discoveries out of player narration and include research preparation in cost.

## Player and live text workflows

`fdisbull-player` is a separate, standard-library package. Its `--package` mode
runs an authored JSON slice; `--connect HOST:PORT` connects to a line-oriented
backend. `--live` restores and checkpoints turns, but cannot verify a remote
backend's durability. Optional external agents are trusted processes, not
sandboxed programs. Read `docs/TEXT_PLAYER.md` and `docs/PLAYER_LIVE.md` before
choosing this surface.

Z scene consumption is available through
`--backend-command`: select a trusted local content service and a finite
`--backend-timeout`. `python -m fdisbull.il_scenes /private/scene.json` consumes
shared IL without starting a debugger. The player supports public object verbs,
compass aliases, partial observations and opaque freshness tokens. A failed
exchange stops the connection; inspect unknown effects before any retry.
`--quiet` keeps external-driver transcripts private. Checkout examples are not
installed runtime resources; provide your own authored or qualified scene input.
Read `docs/Z_SCENES.md` for the envelope and exact limits.

For an ordered route, `--batch-plan` and `--batch-journal` journal each dispatch
before it crosses the provider boundary. A continuation needs both the plan's
permission and the original provider response's matching context/command.
Canonical action identity blocks aliases from resending the original action.
An acknowledged notice or successful `look` cannot complete an original
partial effect. Current providers supply no bound original-intent completion
certificate, so such steps remain paused. Inspect the original result and use
only a certified checkpoint rewind when its live-session/resource contract
holds. See `docs/Z_BATCH_RECOVERY.md`; do not combine this protocol with the
separate Word16/intent command loop.

For the original-backed DinoPark provider, run
`python -m fdisbull.dinopark_z` as the selected service with explicit original
game, compatible backend and a new private work directory. It uses the v0.23
DOS UDC before launching the original engine. Verify native receipts, keep
unfinished or interrupted sessions distinct from successful cleanup, and never
repeat an action solely because its follow-up view failed. `save park` uses the
original disk writer and a fresh loader; a live snapshot is a separate facility.
The qualified scene surface is partial. See `docs/DINOPARK_Z.md`.

Starting with 0.26, an action error can leave that provider available only when
the same native guest is still reachable and freshly confirmed stopped.
`recovery_required` is not success: new actions and new checkpoints are refused;
only an explicitly requested, previously qualified checkpoint restore can clear
the gate after native fields match and the saved scene qualifies again. Preserve
confirmed effects separately from unknown effects, including when EOF closes the
session. A running, unreachable or terminated guest is not recoverable through
this path. Checkpoint rewind does not undo mounted-file writes.

The debugger-backed `text-host` exposes a deliberately qualified public
projection over a live session. It needs a private configuration, project,
backend, game directory, resource root and explicit runtime witnesses. It is
single-client loopback transport without authentication or encryption; use it
only in a trusted local environment. The projection is not a secrecy or process
isolation boundary. `--fair-play` locks the host to physical movement. Otherwise
choose `--spatial-mode physical|assisted|story` explicitly for a controlled
experiment. Read `docs/TEXT_PROJECTION.md` and `docs/SPATIAL_MAPS.md`.

## Research-backed progression

When the goal is normal progression or recovery, read
[recovery-research.md](recovery-research.md) for version-qualified prior work,
a source-attributed milestone checklist and tests of candidate scene transitions.
Do not confuse a guide-derived route with a route observed on this target.

For the meaning of an interaction across code, a text view and a proposed
reconstruction, use [semantic-contracts.md](semantic-contracts.md). Retain the
working lower-level representation and explicit unknowns as individual intent
contracts are qualified.

## Retain knowledge without overstating it

Promote verified reusable facts into versioned scene objects, named anchors,
route segments, source mappings or interaction definitions only when doing so
reduces later probe cost. Preserve the evidence and authority behind the
shortcut. Revalidate after a source/version, resource, room, backend or runtime
context change. Keep target-specific addresses, masks and paths in project
evidence rather than this reusable skill.

## Retrieve bounded output

The core defaults to 64 KiB inline. An `fdisbull-output-ref-1` marker with
`complete: false` and `status: artifact_required` replaces an oversized reply;
the separate execution summary keeps the original status/completeness, including
unknown values. The marker is in a successful wrapped `request` result, in `output` for a
wrapped error, or is the raw `il-run` response. It is not a failure, a rollback or proof of equality.
`output-info ARTIFACT` inspects the private archived JSON; `output-select
ARTIFACT JSON_POINTER --max-bytes N` returns a selected value only if complete,
`output-read ARTIFACT --offset N --length N` reads bounded base64 byte ranges,
and `output-export ARTIFACT NEW_FILE` exports to a new private path outside Git.
For example, use `/state` for a raw `il-run` artifact and `/result/state` for a
wrapped `request`. Do not repeat a side effect to obtain its response. Retrieval
does not run the target or refresh state. `output_unavailable` means full output could not be retained, including
a storage or serialization failure, with no artifact; it does not undo execution or authorize a retry. These
output references differ from project debug artifact IDs. The default private
store is user-data `fdisbull/output-artifacts`; `FDISBULL_OUTPUT_ARTIFACT_DIR`
may select a location outside Git. Artifacts have no automatic deletion.

## Compare related programs

Use explicit `export-types` / `import-types` to share unbound structural
interpretations after checking each target's own layout evidence. Keep byte
identity signatures separate from semantic correspondences: equivalent arithmetic
can have different code, pointer widths and calling conventions. Catalog origin
is a declared source claim, not native evidence. Apply a received type only at a
locally qualified memory/file location; fixed pointer segments cannot be
transferred. Record accepted, rejected and still-candidate correspondences.
