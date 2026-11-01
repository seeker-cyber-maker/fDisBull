# fDisBull

See the [feature history](docs/FEATURE_HISTORY.md) for what shipped in each
version and what remains in review. The latest published package is
[0.27.0](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.27.0).
This development branch adds direct AGI lifting and original-DOS qualification
to the earlier source line; those additions are in the open PR stack described
in the feature map. Check the installed capabilities when choosing a workflow.

Give an agent a program to explore—and a place to keep what it learns.
fDisBull connects disassembly, headless debugging, scene-aware controls and
persistent evidence. Find the instruction behind a changing value, name a
control and reuse its verified route, or compare a temporary patch against a
baseline. Come back next session with the discoveries still in your project.

Use it to investigate DOS and Windows programs, inspect game interpreters,
build reusable automation or test small recovered interaction models. Watch
an agent work in dot-mode, drive a qualified scene through named actions, or
play an authored text projection without opening the debugger yourself.

> **This tool is not currently suitable for malware analysis or security work.**
>
> Must bring your own weapons. I have only done this once before. Safety not guaranteed.

## Choose a starting point

| I want to… | Start here |
| --- | --- |
| Extract a GOG DOS installer on macOS or Linux without Wine | [Native GOG unpacking](docs/GOG_UNPACKING.md) |
| Understand an executable without running it | [Disassembly and analysis](#disassemble-and-analyze) |
| Observe a DOS game or a Windows PE64 program | [Debug the original program](#debug-the-original-program) |
| Compare a hypothesis, a checkpoint or a temporary patch | [Layers, states and experiments](#layers-states-and-experiments) |
| Give an agent reliable scene context and navigation | [Scenes, maps and interaction policies](#scenes-maps-and-interaction-policies) |
| Play a supported projection or a user-supplied Zork story | [Text play and interpreter inspection](#text-play-and-interpreter-inspection) |
| Convert Zork I to executable IR and recover bounded game-intent UIL | [Executable IR](docs/ZORK_UIL.md) · [Game-intent UIL](docs/ZORK_INTENTS.md) |
| Disassemble Zork's v3 bytecode and follow static calls and branches | [Z-machine processor](docs/ZMACHINE_PROCESSOR.md) |
| Try shared interaction scenes through Z | [Z scene play](docs/Z_SCENES.md) |
| Run a qualified DinoPark park through the original game | [DinoPark in Z](docs/DINOPARK_Z.md) |
| Test a small recovered block against its original DOS backing | [The bounded UDC pipeline](#the-bounded-udc-pipeline) |

Agents can start with [AGENTS.md](AGENTS.md), [CLAUDE.md](CLAUDE.md) and the
[agent quickstart](docs/AGENT_QUICKSTART.md). The bundled investigation skill is
also available through `fdisbull agent-skill --reference SKILL.md`. These guides describe the tools
and their boundaries; they do not turn an inferred result into observed fact.

The [definitions and contract roadmap](docs/DEFINITIONS_AND_ROADMAP.md) brings
the language, interface, scene and proof proposals together and shows which
parts are working, partial or still proposed.

The 0.25.0 source lets you preserve a qualified Zork story as executable IR,
recover a small action as game-level rules, and keep playing through the
unrecovered parts. DinoPark's original-backed provider adds bounded
continuation through catalogue, notice and save boundaries. Effects already
performed remain visible when a later step fails; the tool does not quietly
repeat the action to make a reply look successful.

Routine replies stay small, with larger evidence retained through private
handles. The unified investigation skill helps agents choose a useful probe,
research an edition and turn walkthrough clues into testable scene leads.
See the [0.25 notes](docs/RELEASE-0.25.0.md),
[bounded output](docs/OUTPUT_LIMITS.md) and
[agent workflow](docs/AGENT_QUICKSTART.md).

Turn the findings into something people can play from: a separate guide-writing
skill helps assemble verified routes, maps, secrets and mechanics into a
walkthrough, with sources and unresolved gaps kept visible.

## Install and use

Python **3.12 or later** is required. From a source checkout:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install .
fdisbull inspect /path/to/program
fdisbull import /path/to/program analysis.fdb
fdisbull analyze analysis.fdb --max-instructions 10000
fdisbull analysis-status analysis.fdb
fdisbull functions analysis.fdb
```

On Windows, activate `.venv\Scripts\Activate.ps1` in PowerShell. Use `--image
com` when importing a DOS COM file: the filename extension alone is not format
evidence. Install `.[managed]` for optional .NET metadata and CIL inspection.
See the [user guide](docs/USER_GUIDE.md), [API](docs/API.md) and
[platform support](docs/PLATFORMS.md) for more options.

## Disassemble and analyze

Import x86 16/32/64 or ARM64 programs in supported DOS MZ, COM, PE, ELF,
Mach-O or explicit raw-image profiles. Native decoders supply instruction
facts; fDisBull traverses reachable code and stores instructions, control flow,
references, annotations and versions in SQLite. Analysis is bounded: unfinished
work and unresolved targets remain visible. Inferred functions are candidates,
not proof of execution or complete code coverage.

Original bytes and previous versions are preserved. You can attach supporting
files, record types and links, and export disassembly and control-flow images
from stored state without operating a GUI. See [architecture](docs/ARCHITECTURE.md)
and [external files](docs/EXTERNAL_FILES.md).

The [DOS/4GW LE module](docs/dos4gw-le.md) adds bounded loading of
supported 32-bit LE objects and internal fixups for the existing x86 analyzer.

## Debug the original program

The DOS debugger uses a separately built, compatible patched DOSBox backend.
For example, after importing your own program:

```bash
fdisbull debug analysis.fdb --executable /path/to/patched/dosbox-x --game-dir /path/to/game
```

Catch a memory access with a watchpoint, stop at a verified disassembly address,
skip an intro with bounded fast-forward, then inspect a short trace or a saved
frame. Guest keyboard and mouse input let the program perform its own actions.
Traces and screenshots remain available from the project after restart.
Headless mode is the default; `--dot-mode` opens a watch-only window on the same
session when a display and compatible backend are available. See the
[DOSBox guide](docs/DOSBOX_DEBUGGER.md).

For x86-64 Windows executables, the [PE64 debugger](docs/WINE_DEBUGGER.md)
uses a separately prepared Linux/Wine runtime and QEMU. Its watches, layers
and machine states have their own implementation and limits. Python packages
include neither emulator nor game files. Headless execution is not a security
sandbox; restoring a machine checkpoint does not roll back mounted host files.

## Layers, states and experiments

Save checkpoints and bounded experiments, compare observations, and explore
reversible runtime changes while retaining original versions. The DOS layers
backend supports RAM changes and instruction-fetch overlays; the PE64 backend
uses different mechanisms. Runtime code observations retain captured bytes
alongside earlier views, but a capture does not by itself prove those bytes ran.
See [code layers](docs/CODE_LAYERS.md), [saved experiments](docs/DEBUGGER_EXPERIMENTS.md),
[debugger scripts](docs/DEBUGGER_SCRIPTS.md) and [runtime code](docs/RUNTIME_CODE.md).

## Scenes, maps and interaction policies

Scenes connect named controls, masks, predicates and supporting screenshots to
persistent revisions. Sparse native pixel probes can answer qualified questions
without transferring a full PNG each time. Stored screenshots and map overlays
can be exported later. Scene identity, readiness and actual action outcomes
remain distinct; an incomplete observation is not a successful action.
See [scenes](docs/SCENE_FRAMEWORK.md) and [progressive workflows](docs/PROGRESSIVE_SCENES.md).

Room maps describe known and safe areas in game coordinates, actor footprints,
obstacles, hazards and object interaction zones. A map can suggest candidates
or a bounded route; it does not itself move the game or prove that every cell
is safe. Unknown conditions remain unknown. Live use requires a pinned,
freshly qualified scene context. See [spatial maps](docs/SPATIAL_MAPS.md).

Choose a policy for the session:

- **Physical** uses the original game's movement and input, with qualified map checks.
- **Assisted** can use explicitly qualified travel assistance and reports its use.
- **Story** can use qualified temporary position-test overrides while original game input still performs actions.
- **Fair-play** locks a text-host session to physical mode and disables the assisted and story shortcuts. It is a voluntary session policy, not a tamper-proof anti-cheat boundary.

The exact conditions and evidence for these choices are in the
[spatial guide](docs/SPATIAL_MAPS.md) and [assisted travel guide](docs/ASSISTED_TRAVEL.md).

## Text play and interpreter inspection

Z gives agents a small text interface for exercising shared interaction scenes:
look around, pick up an object, try a guarded action and observe the result.
The same player consumes a local scene service while the shared IL supplies the
state and effects. See [Z scene play](docs/Z_SCENES.md) for a working authored
example, model-driver support and current limits. This integration is available
in the published 0.24.0 packages.

The [DinoPark Z provider](docs/DINOPARK_Z.md) lets an agent borrow and repay,
buy supplies, prepare a pen, hire a guide, open the park and save its progress
through a bounded text interface. The original-backed compiler reconstructs
your own qualified game files before play, and the original engine performs
the actions. Bring the game and a compatible native backend. See the
[native verification and coverage limits](docs/VERIFICATION-DINOPARK-Z-RELIABILITY-2026-10-29.md)
and [v0.23 merge-readiness checks](docs/VERIFICATION-Z-V023-MERGE-READINESS.md).

[Recoverable Z batches](docs/Z_BATCH_RECOVERY.md) retain per-step effects,
resume explicitly declared notice continuations and rewind only after a
certified live checkpoint restore. DinoPark restores recheck native values and
the original scene before more input. Live checkpoints require the surviving
guest and unchanged mounted files; native park saves provide durable resumption.
An acknowledgement can advance a partial action, but current providers do not
certify that the original intent is complete. Such batch steps remain paused
for reconciliation, and aliases cannot be used to resend the original action.
If a result read fails, read-only reconciliation can verify a saved reply in the
same guest before the batch continues.

The [funded26k recovery path](docs/DINOPARK_FUNDED_RECOVERY.md) preserves a confirmed
food purchase across its quarter notice and keeps a paused provider available
for explicit checkpoint recovery after a failed action.

The separately installable [text player](docs/TEXT_PLAYER.md) can consume an
authored projection or connect to a compatible local backend. Its live mode
can checkpoint after each model turn and resume, subject to successful save and
identity checks. It is a bounded player and declarative runtime, not an AGI
interpreter or evidence of whole-game equivalence. Its local protocol has no
authentication or encryption; use a trusted endpoint. See [live turns](docs/PLAYER_LIVE.md).

An external story agent can choose commands, narrate its choices and continue
within turn/time limits, with a transcript of the observed results. Voice input
and output are planned future work; the player currently supplies the text and
state interface.

The [AGI inspector](docs/AGI_LOGIC.md) reads a limited version-2 logic subset;
unsupported operations remain unresolved. The [Z-machine harness](docs/ZORK_HARNESS.md)
can run a user-supplied version-3 story using a separately selected Python and
Jericho environment. Story inspection and the recovered mailbox slice are
bounded evidence, not recovery of the parser, turn loop or complete game.
No original game or story files are distributed.

[Direct decoder modules](docs/DECODER_MODULES.md) make AGI logic and Z-machine
stories inputs in their own languages. Inspect them without creating an x86
analysis project. Follow scalar AGI decisions, branches and direct logic calls
into UDL/UIL with source evidence and explicit state. The guest-language front
end can grow independently of the DOS interpreter's assembly; supported source
components and their boundaries stay explicit. Compact control flow keeps shared
paths once, making larger routines easier to inspect. Unmodeled engine actions
stay visible and block execution until their effects are implemented.
An explicit [object/resource effect profile](docs/AGI_EFFECTS.md) now models
AGI positions, views, queries and controller changes. Drawing and message
windows use resumable host requests, so an agent can inspect a routine without
silently treating a requested external action as completed.
The [original DOS host adapter](docs/AGI_DOS_HOST.md) can now check selected
KQ1 routines against the running original: follow the same decisions, observe
real handler returns, and compare the declared state at the routine boundary.
Interrupted work keeps its evidence and stops for inspection.
The [eastern bridge case study](docs/AGI_BRIDGE_CLIP.md) follows a speedrunner's
description to a reproduced KQ1 corner clip, a neighboring failure control,
and a reusable partial scene in the separate player.
The [mushroom-island follow-up](docs/AGI_MUSHROOM_CROSSING.md) carries that
workflow through a river crossing and a real inventory pickup, then offers the
recorded journey through the separate text player.
The [clover-and-diamonds cave route](docs/AGI_LEPRECHAUN_ROUTE.md) follows
ordinary game input through a moving rat, the shield pickup and the small
opening, then turns the recorded journey into seven guarded text actions.
The [gnome/key and giant's chest follow-up](docs/AGI_GNOME_GIANT_ROUTE.md)
continues from a verified native checkpoint through the original game's
riddle, tree and clouds. Its eight guarded text actions retain the recorded
inventory, score and source evidence in the separate player.
The [dragon and magic mirror route](docs/AGI_DRAGON_MIRROR_ROUTE.md) starts a
fresh game, uses water to clear the dragon, takes the mirror and returns to the
surface. Original inventory writes and short traces support eight guarded
text actions, with the preparation, failures and final evidence kept inspectable.
Its [boundary analysis](docs/AGI_BOUNDARY_EXCEPTIONS.md) also exposes the dragon
rule's last-row exception, with adjacent outcomes checked in the original game.
The [coordinate-domain audit](docs/SCENE_COORDINATE_DOMAINS.md) keeps world,
viewport and collision bounds distinct, flags object overhangs and retains
designer notes for expected scrolling margins.
The [bottom-row bridge route](docs/AGI_BRIDGE_BOTTOM.md) now has a fresh-game
witness, an adjacent water control and a two-action scene for the separate
player, with the original game files unchanged.
Agents can now reuse [bounded native control and scene receipts](docs/BOUNDED_NATIVE_SCENES.md)
for their own routes, carrying partial results and evidence forward without
rewriting the same transport and capture bookkeeping.
A separate [reconstruction of Robb's short TAS](docs/research/kq1-robb-9.89/ROUTE.md)
preserves the visible route and its unresolved inputs for another investigator.

The [Z-machine processor](docs/ZMACHINE_PROCESSOR.md) adds direct v3 bytecode
inspection through fDisBull's processor interface. It reports operands, calls,
branches and source identity, and can follow a bounded graph from a selected
entry. Dynamic targets and incomplete analysis remain explicit. This is the
instruction layer; it does not assign gameplay meanings to those operations.

The [standalone Zork converter](docs/ZORK_UIL.md) lowers a complete v3 story into
executable word16 **IR**: arithmetic, memory, control and object operations. Its
legacy `zork-uil` command and wire format remain compatible, but that layer does
not recover game intent. Its independent player runs without an original
interpreter.

The separate [game-intent UIL](docs/ZORK_INTENTS.md) recovers a bounded mailbox
interaction: opening conditions, state change, ordered narration, pronoun
reference and action counting. UDL definitions connect each primitive to the
original operations. The consumer executes those domain rules and retains the
parser, background callbacks, uncertain flag effects and unsupported cases as
explicit low-level IR. Recovery is partial; the verification report distinguishes
successful play from evidence that the higher-level rules actually executed.

## The bounded UDC pipeline

The 0.23 source introduces an original-backed DOS compiler definition (UDC):
explicitly mapped ASM blocks can be lifted to shared UDL/UIL primitives and
checked with Z3 at a declared register boundary. A limited C statement view
can be lifted and compared as well; it shares the ASM decoder and is not an
independent general-purpose decompilation. Unknown, unavailable or failing
proofs do not qualify a semantic block.

The first target reconstructs original MZ/COM bytes from immutable stored
backings, including opaque regions and explicitly attached resources. It does
not generate arbitrary DOS code or claim whole-game semantic recovery. The
authored COM demonstration and the bounded real-game observations are described
in [UDC usage](docs/UDC_DOS.md), [testing methodology](docs/UDC_TESTING.md)
and [verification](docs/VERIFICATION-0.23.md).

## Status, testing and history

The **0.25.0 source integration** is described in the
[release notes](docs/RELEASE-0.25.0.md) and
[verification record](docs/VERIFICATION-0.25.md). The
[PR backlog](docs/PR_BACKLOG.md) distinguishes incorporated contributions from
requirements that remain partial or proposed. A source integration does not
change the published release or system installation.

[Version 0.24.0 is published](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.24.0) with eight download-verified assets and the updated Linux offline kit. The [publication record](docs/PUBLICATION-0.24.md) documents exact-tag CI, public asset readback, known limits and the verified [shared Mac installation](docs/SYSTEM_INSTALLATION.md).

The **0.24.0 release** adds bounded replies and private output handles,
shared Z scenes, the original-backed DinoPark provider and research-led agent
guidance. See the [0.24 notes](docs/RELEASE-0.24.0.md) and
[verification record](docs/VERIFICATION-0.24.md). Ordinary and required-native Linux
CI passed on the exact release commit before tagging, and both tag workflows
passed before publication. The system installation passed 700 selected tests
and native save/restore through DOSBox, DOS-in-QEMU and Wine/QEMU. Check
[Actions](https://github.com/seeker-cyber-maker/fDisBull/actions) for current runs.
The earlier [0.23 notes](docs/RELEASE-0.23.0.md) and
[verification record](docs/VERIFICATION-0.23.md) describe the UDC baseline.

For development checks:

```bash
python -m pip install '.[test]' build
python -m pytest -q
python -m build
python scripts/check_dist.py
python scripts/build_release.py
```

Ordinary tests can skip native tests. Required native acceptance uses real,
separately prepared backends; see the [DOSBox acceptance guide](docs/DOSBOX_DEBUGGER.md#required-native-acceptance).
Consult the verification record for platform-specific results and test limits.
Repository examples are excluded from tool packages. The previous detailed
landing page is preserved as a [historical snapshot](docs/PROJECT_HISTORY.md),
with original release and delivery links.

No first-party distribution license has been selected. Public visibility does
not grant an open-source license. See [third-party provenance](docs/THIRD_PARTY.md).
