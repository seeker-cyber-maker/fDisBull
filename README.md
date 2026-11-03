# fDisBull

Give an agent a program to explore—and a place to keep what it learns.
**fDisBull** connects multi-architecture disassembly, headless native debugging,
scene-aware controls, spatial policies, a standalone text player and bounded
semantic reconstruction (`UDL` → `UIL` → `UDC`). Find the instruction behind a
changing value, rewind a native frame timeline, drive a qualified scene through
named actions, or retarget a verified interaction block to a new desktop,
browser or console shell. Come back next session with every discovery and piece
of evidence preserved in your SQLite project.

**Release status (0.31.0 candidate):** the local `release/0.31.0` line is a
packaging candidate, not a published tag. It carries the 0.30.0 release plus
lossless frame-timeline delta storage, the bounded typed-C to UIL frontend,
read-only Windows original-runtime preflight, CHIP-8 ISA/corpus pilots, and
UDC registry and fresh-agent swede examples. See the
[0.31.0 release notes](docs/RELEASE-0.31.0.md),
[release status](docs/RELEASE_STATUS.md) and
[feature history](docs/FEATURE_HISTORY.md) for qualification scope and open
gates. [`v0.30.0`](https://gitlab.com/brewster-jennings-group/fdisbull/-/tags/v0.30.0)
remains the latest published GitLab tag (`dc6d7e77`); the 0.31.0 candidate has
no tag or Release package yet.

> **This tool is not currently suitable for malware analysis or security work.**
>
> Must bring your own weapons. I have only done this once before. Safety not guaranteed.

**Game files stay private by default.** The user-approved
[Tic-tac-toe, Five Dice and Snake fixture collection](docs/FREEWARE_GAME_VERSIONS.md)
is a narrow repository exception (excluded from tool wheels and source packages).
All other original or modified binaries, ROMs, discs, assets, story images,
saves, emulator states and byte-containing databases stay outside Git and
published packages. New `.fdb` projects store external payload references by
size, SHA-256 and loader provenance in a private local store; binding a
divergent binary requires explicit user approval of the exact candidate receipt.
Semantic UIL/game representations are permitted pending sanitation, without
embedded originals. See [external targets and publication policy](docs/EXTERNAL_TARGETS.md).

## Choose a starting point

| I want to… | Start here |
| --- | --- |
| Check this copy's decoders, debuggers, diagnostics and UIL support without running a target | [Capabilities catalog](docs/CAPABILITIES.md) |
| Understand an x86, ARM64 or Cortex-M executable without running it | [Disassemble, type and search](#disassemble-type-and-search) |
| Unpack a local GOG DOS installer on macOS or Linux without Wine | [Native GOG unpacking](docs/GOG_UNPACKING.md) |
| Inventory a game collection, compare editions or inspect MZ/AGI/AVI media | [Collection intake](docs/TARGET_COLLECTION_INTAKE.md) · [TAS/AVI capture audit](docs/TAS_CAPTURE_AUDIT.md) |
| Identify NES, SNES or Sega cartridges, CUE/ISO discs, or disassemble Saturn SH-2 / SNES 65816 | [Console media](docs/CONSOLE_MEDIA_PARSING.md) · [Disc parsing](docs/CUE_ISO_PARSING.md) · [ROM-to-ASM](docs/ROM_ASM.md) |
| Share structural types or search edition-pinned C source and verified DOS byte maps | [Portable type catalogs](docs/TYPE_CATALOGS.md) · [Source & concept search](docs/SOURCE_CONCEPT_SEARCH.md) · [Verified CivD maps](docs/CIVD_VERIFIED_SOURCE_MAPS.md) |
| Debug an original DOS game or a Windows x86-64 program headlessly | [Debug the original program](#debug-the-original-program) |
| Investigate a macOS ARM64 binary or capture a reversible macOS status-menu session | [macOS ARM64 analysis](docs/MACOS_ARM64_ANALYSIS.md) · [Reversible native capture](docs/MACOS_REVERSIBLE_CAPTURE.md) |
| Rewind execution, branch frame inputs, test code layers or run partial-RNG delta experiments | [Layers, states, rewind and experiments](#layers-states-rewind-and-experiments) |
| Give an agent named controls, game-unit room maps and explicit spatial policies | [Scenes, maps and interaction policies](#scenes-maps-and-interaction-policies) |
| Play shared Z scenes, original-backed *DinoPark Tycoon*, or inspect *Civilization I* / *Zork I* worlds | [Text play and world projections](#text-play-and-world-projections) |
| Lift Sierra AGI v2 (*King's Quest I*) or Z-machine v3 (*Zork I*) directly in their guest languages | [Direct guest interpreters: AGI and Z-machine](#direct-guest-interpreters-agi-and-z-machine) |
| Compose typed indexed UIL and emit standalone Python/JS, linked native binaries or desktop windows | [Common UIL contract](docs/COMMON_UIL_CONTRACT.md) · [Native linking](docs/COMMON_UIL_NATIVE.md) · [Desktop shells](docs/COMMON_UIL_DESKTOP.md) |
| Verify source blocks with Z3 or retarget bounded-memory UIL across browser, macOS, Windows, Linux and Win16 | [Common UIL and the bounded UDC pipeline](#common-uil-and-the-bounded-udc-pipeline) |
| Compile shared UIL or source-bound *Miniplanets* / *Shadowrun* profiles to NES, Genesis or macOS ARM64 | [Console intake and synthesis](#console-intake-and-synthesis) |

Agents should start with [AGENTS.md](AGENTS.md), [CLAUDE.md](CLAUDE.md) and the
[agent quickstart](docs/AGENT_QUICKSTART.md). Two bundled skills ship inside the
installed package and work without opening a project:

- `fdisbull agent-skill --reference SKILL.md` (`fdisbull-investigate`): evidence-driven reverse engineering, probe selection, scene/UIL recovery and verification gates.
- `fdisbull agent-skill --skill write-gamefaqs-guide --reference SKILL.md` (`write-gamefaqs-guide`): turning recovered mechanics, routes, bugs, unused code and format specs into an attributed, human-readable guide.

Use `fdisbull agent-skill --list` and `--index` for selective discovery. Core
JSON replies stay compact (64 KiB inline by default) and archive larger results
behind private handles; see [bounded output](docs/OUTPUT_LIMITS.md) and the
[definitions and contract roadmap](docs/DEFINITIONS_AND_ROADMAP.md).

## Install and use

Python **3.12 or later** is required. From a source checkout:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install . ./player
fdisbull capabilities
fdisbull inspect /path/to/program
fdisbull import /path/to/program analysis.fdb
fdisbull analyze analysis.fdb --max-instructions 10000
fdisbull analysis-status analysis.fdb
fdisbull functions analysis.fdb
```

On Windows, activate `.venv\Scripts\Activate.ps1` in PowerShell. Pass `--image
com` when importing a DOS COM binary—filename suffixes alone are not format
evidence. Optional extras include `.[proof]` for bounded Z3 equivalence checks,
`.[managed]` for .NET metadata and CIL inspection, `.[udc]` for isolated x86-16
CPU block checks, and `.[source]` for C syntax indexing in source catalogs. The
standalone `fdisbull-player` package uses only the Python standard library and
can also be installed on its own. See the [user guide](docs/USER_GUIDE.md),
[API reference](docs/API.md) and [platform support](docs/PLATFORMS.md).

## Disassemble, type and search

Import x86 16/32/64, ARM64 or Armv7-M programs across supported containers and
profiles:

- **DOS & 16/32-bit Windows:** classic MZ, explicit COM, bounded 32-bit
  [DOS/4GW LE](docs/dos4gw-le.md) objects and fixups, 16-bit
  [Win16 NE](docs/NE_LOADING.md) segments with logical `ne:seg:offset` addresses
  and symbolic relocations, OMF library signature catalogs (`omf-catalog`), and
  [DOS audio drivers](docs/DOS_AUDIO_DRIVERS.md) (Miles AIL 2 `.ADV` exports
  via `--image ail`, plus named DIGPAK/MIDPAK `INT 66h` calls).
- **Modern desktops:** Windows PE32/PE64 (plus optional .NET CIL via `managed`),
  Linux ELF, and [macOS Mach-O ARM64](docs/MACOS_ARM64_ANALYSIS.md) with
  `LC_FUNCTION_STARTS`/unwind seeds, exact file-offset `code-backings`, and
  optional source-bound Headless Ghidra (`ghidra-arm64`) C/instruction
  diagnostics.
- **Embedded & console media:** static [Armv7-M Cortex-M](docs/CORTEX_M.md)
  flash images with Thumb/Thumb-2 vector-table traversal (exercised on 121GW
  2.05 meter firmware without hardware emulation), non-executing
  [cartridge](docs/CONSOLE_MEDIA_PARSING.md) (`rom-inspect`) and
  [CUE/ISO disc](docs/CUE_ISO_PARSING.md) (`disc-inspect`) headers, three-engine
  Saturn SH-2 [ROM disassembly](docs/ROM_ASM.md) (`rom-disasm` across Capstone,
  Ghidra and `saturn-recomp`), mode-explicit SNES 65C816 decoding, and
  reusable [media adapters](docs/AGENT_QUICKSTART.md#reuse-media-readers)
  (`media-modules`, `media-inspect`, `media-extract`).

Native decoders supply instruction facts (with two-engine Iced/Capstone checks
via `decoder-check` on x86); fDisBull owns bounded traversal and stores
instructions, control-flow graphs, cross-references, structural types, function
summaries and byte versions in SQLite. Unfinished worklist frontiers and
indirect transfers remain visible, inferred functions stay labeled as
candidates, and disassembly or CFG PNGs render directly from stored state
without launching a GUI. See [architecture](docs/ARCHITECTURE.md).

You can snapshot companion data or save files, bind structural layouts across
memory and file offsets, and share unbound structs across projects; see
[external files](docs/EXTERNAL_FILES.md) and [portable type catalogs](docs/TYPE_CATALOGS.md).
When period or reconstructed source exists, the private
[source and concept catalog](docs/SOURCE_CONCEPT_SEARCH.md) (`source-*`) indexes
edition-pinned snapshots for lexical and caller-embedded vector search, links
logical concepts, and verifies build-to-resident-byte mappings across releases—demonstrated
in [verified CivD source maps](docs/CIVD_VERIFIED_SOURCE_MAPS.md), the nine-way
[shared-food & strategy-Z study](docs/CIVD_SHARED_FOOD_AND_Z.md), and the
cross-platform [Colonization DOS/Win16 comparison](docs/COLONIZATION_FOOD_EQUIVALENCIES.md).

## Debug the original program

Python packages distribute neither emulators nor game files; native debugging
attaches to a separately prepared backend and your own inputs:

```bash
fdisbull debug analysis.fdb --executable /path/to/patched/dosbox-x --game-dir /path/to/game
```

- **DOS targets:** the patched [DOSBox-X debugger](docs/DOSBOX_DEBUGGER.md)
  supports execution breakpoints on verified mapped bytes, `after-access` data
  watchpoints, bounded fast-forward, short instruction traces, guest keyboard
  and mouse delivery, stored screenshots, and selected-PSP `guest_exit` versus
  `guest_tsr` termination tracking. Headless operation is the default;
  `--dot-mode` opens a watch-only window on compatible builds. A separate
  Linux/QEMU path supports DOS-in-QEMU and raw x86 boot contexts.
- **Windows x86-64 targets:** the [PE64 debugger](docs/WINE_DEBUGGER.md) drives
  analyzed Windows binaries through a prepared Linux/Wine/QEMU guest with
  address stops, watchpoints, guarded memory edits, traces and window input.
- **macOS observation & reversible UI capture:** `macos-observe` runs a
  source-bound ARM64 binary to one LLDB breakpoint, while
  [reversible native sessions](docs/MACOS_REVERSIBLE_CAPTURE.md)
  (`macos-snapshot`, `macos-session`, `macos-session-recover`) inspect
  CoreGraphics displays and accessibility trees and journal status-menu or
  `CFPreferences` trials for clean restoration. Experimental AppKit replication
  studies ([replication limits](docs/MACOS_APP_REPLICATION.md),
  [cpuinfo comparison](docs/CPUINFO_REPLICATION_COMPARISON.md),
  [Simple Menu updates](docs/MACOS_REPLICA_UPDATES.md)) stay outside normal
  packages.
- **Offline video & standing probes:** `capture-audit` hashes every decoded
  RGBA frame of finalized AVI segments and exports timestamped inspection pages
  before pixel analysis ([TAS capture audit](docs/TAS_CAPTURE_AUDIT.md)). For
  long-lived sessions, the skill and [standing probes RFC](docs/STANDING_PROBES_RFC.md)
  define selective execution and meaningful-field watch procedures for catching
  rarely activated code naturally.

Headless execution is not a security sandbox, and restoring an emulator state
never rolls back writes to mounted host directories.

## Layers, states, rewind and experiments

Explore runtime hypotheses without losing your baseline:

- **Code layers and saved experiments:** apply reversible RAM edits or DOS
  instruction-fetch overlays, capture runtime code alongside earlier byte
  versions, and compare baseline versus single-layer runs. See
  [code layers](docs/CODE_LAYERS.md), [saved experiments](docs/DEBUGGER_EXPERIMENTS.md),
  [debugger scripts](docs/DEBUGGER_SCRIPTS.md) and [runtime code](docs/RUNTIME_CODE.md).
- **Anchor Stones and next-fetch rewind:** full native saved states—called
  [Anchor Stones](docs/ANCHOR_STONES.md), a nod to TiGa's *Blob to General*—let
  sessions jump directly to a verified machine context, while bounded
  [debugger rewind](docs/DEBUGGER_REWIND.md) (`debug-rewind-*`) steps backward
  across recorded next-fetch intervals.
- **Automatic frame/input timeline:** on frame-capable DOS backends,
  [frame timelines](docs/FRAME_INPUT_TIMELINE.md) (`debug-timeline-*`) cache
  completed frames and full states with frame-scheduled physical keyboard
  make/break edges, supporting instant rewind, input branching and durable
  Anchor Stone pins.
- **CPU and RAM delta rewind:** [delta histories](docs/CPU_RAM_DELTAS.md)
  (`debug-delta-*`) record exposed register and declared RAM diffs anchored by a
  recovery stone on both DOSBox and [Wine/QEMU x86-64](docs/WINE_CPU_RAM_DELTAS.md).
  Default undo blocks execution until full native recovery; an explicit
  experimental policy can preserve selected current RAM (such as identified RNG
  state) to test alternative inputs from a documented mixed state.

## Scenes, maps and interaction policies

Scenes bind named UI controls, pixel masks, `visible`/`ready`/`enabled`
predicates, actions and expected outcomes to immutable revisions. Sparse native
pixel probes answer targeted state questions without transferring full PNGs on
every check, and [coordinate-domain audits](docs/SCENE_COORDINATE_DOMAINS.md)
keep world, room, viewport and collision bounds distinct. See
[scenes](docs/SCENE_FRAMEWORK.md), [progressive workflows](docs/PROGRESSIVE_SCENES.md)
and [bounded native scene controllers](docs/BOUNDED_NATIVE_SCENES.md).

[Spatial maps](docs/SPATIAL_MAPS.md) track known/safe regions in game units,
actor footprints, obstacles, hazards and interaction zones to propose and guard
bounded routes while keeping unexplored cells explicitly unknown. Every live
session selects its movement policy up front:

- **Physical:** ordinary guest input and engine movement only, guarded by qualified map checks.
- **Assisted:** permits explicitly qualified [assisted travel](docs/ASSISTED_TRAVEL.md) and records its use in receipts.
- **Story:** permits qualified temporary position-test overrides while ordinary game input still performs interactions.
- **Fair-play:** locks a `text-host` session to physical mode for the life of the run (a voluntary session contract, not an anti-cheat boundary).

## Text play and world projections

The zero-dependency [standalone text player](docs/TEXT_PLAYER.md) (`fdisbull-player`)
plays authored JSON slices, connects to `fdisbull text-host` over local
loopback, or drives shared-IL [Z scene services](docs/Z_SCENES.md) with
optional `--live` turn checkpoints ([live turns](docs/PLAYER_LIVE.md)) and
external story-agent drivers. Ordered routes use journaled
[recoverable Z batches](docs/Z_BATCH_RECOVERY.md) and
[oversized reply holds](docs/Z_REPLY_RECOVERY.md) so interrupted or
notice-paused actions reconcile cleanly without silently replaying side effects.

- **Original-backed *DinoPark Tycoon* in Z:** reconstructs your own qualified
  DOS game via UDC and drives the live native engine through loans, land and
  fencing, DinoMart supplies, Coelophysis and catalogue purchases, staff
  hiring, park opening, [month rollover and visitor gates](docs/VERIFICATION-DINOPARK-VISITORS-2026-11-01.md),
  [funded-park recovery](docs/DINOPARK_FUNDED_RECOVERY.md) and
  [named menu/quit actions](docs/DINOPARK_Z_TERMINAL_ACTIONS.md). See
  [DinoPark Z](docs/DINOPARK_Z.md) and the companion
  [static-analysis friction study](docs/DINOPARK_STATIC_ANALYSIS_FRICTION.md).
- **World snapshots and declarative maps:** read-only decoders lift a private
  DOS *Civilization I* `.SVE`/`.MAP` pair into an 80×50 JSON/ASCII/HTML/SVG
  [world snapshot](docs/CIV_WORLD_Z_SCENE_2026-10-31.md), lift historical *Zork I*
  rooms and exits into the strict [`(z-world ...)` graph language](docs/Z_WORLD_LANGUAGE.md),
  and project exact-coordinate [Syndicate spatial Z scenes](docs/SYNDICATE_SPATIAL_Z_SCENE_2026-10-31.md).

## Direct guest interpreters: AGI and Z-machine

[Direct decoder modules](docs/DECODER_MODULES.md) (`decoder-modules`,
`module-analyze`, `module-lift`) inspect interpreted game scripts in their own
languages without creating an x86 disassembly project:

- **Sierra AGI v2 (2.917):** combines the static [logic decoder](docs/AGI_LOGIC.md)
  (`agi-logic`), two-stage projectless [scene and resource census](docs/AGI_SCENE_CENSUS.md)
  (`agi-scenes`), compact `fdisbull-il-2` control-flow lifting, typed
  [object/resource effects](docs/AGI_EFFECTS.md) with resumable host requests,
  and the [original DOS host adapter](docs/AGI_DOS_HOST.md) comparing lifted
  routines against the live interpreter. Qualified *King's Quest I* artifacts
  span the [royal bow intent](docs/KQ1_BOW_INTENT.md) (`kq1-bow-*`),
  [natural goat](docs/AGI_NATURAL_GOAT.md) and [troll-bridge](docs/AGI_TROLL_BRIDGE.md)
  captures, [eastern](docs/AGI_BRIDGE_CLIP.md) and [bottom-row](docs/AGI_BRIDGE_BOTTOM.md)
  bridge clips, [mushroom island](docs/AGI_MUSHROOM_CROSSING.md),
  [leprechaun cave](docs/AGI_LEPRECHAUN_ROUTE.md),
  [gnome and giant's chest](docs/AGI_GNOME_GIANT_ROUTE.md),
  [dragon and magic mirror](docs/AGI_DRAGON_MIRROR_ROUTE.md) with
  [row-166/167 boundary exceptions](docs/AGI_BOUNDARY_EXCEPTIONS.md), and a
  frame-audited [9.89s TAS route study](docs/research/kq1-robb-9.89/ROUTE.md).
- **Z-machine v3 & *Zork I*:** inspects raw story bytecode through the
  [Z-machine processor](docs/ZMACHINE_PROCESSOR.md) (`story-info`,
  `zmachine-disasm`, `zmachine-analyze`) and optional [Jericho harness](docs/ZORK_HARNESS.md),
  lowers complete v3 stories to standalone word16 [executable IR](docs/ZORK_UIL.md)
  (`zork-uil`), and layers source-linked [mailbox game-intent rules](docs/ZORK_INTENTS.md)
  (`zork-intents`) plus 110-room / 352-exit [address-free scene rules](docs/ZORK_SCENES.md)
  (`zork-scenes`) while keeping unrecovered parser and handler bodies as
  explicit residual IR.

## Common UIL and the bounded UDC pipeline

fDisBull separates **UDL** (source-to-semantics mapping), **UIL** (typed
behavioral representation) and **UDC** (target realization and adapters),
qualifying `original → UIL` and `UIL → target` edges independently and checking
modeled register boundaries with [bounded Z3 proofs](docs/BOUNDED_PROOFS.md):

- **Common indexed UIL (`uil-*`):** the four-document
  [common UIL contract](docs/COMMON_UIL_CONTRACT.md) (`fdisbull-common-uil-1`,
  presentation, UDL-grouped semantic catalog and copy-in/copy-out orchestration)
  supports acyclic typed functions, lossless `uil-fold`/`uil-expand` grouping,
  immutable project storage, standalone Python and JavaScript code generation,
  deterministic [native linking and C/ASM component selection](docs/COMMON_UIL_NATIVE.md)
  (`macos-arm64`, `linux-x64`, `windows-x64`), and fixed-arena
  [native desktop window shells](docs/COMMON_UIL_DESKTOP.md) (`uil-desktop*` for
  AppKit, X11 and Win32/Win64). See [conformance examples](docs/COMMON_UIL_CONFORMANCE.md).
- **Original-backed DOS & selectable block layers:** reconstructs exact version-1
  MZ/COM binaries from immutable project backings ([DOS UDC](docs/UDC_DOS.md),
  [UDC testing](docs/UDC_TESTING.md)), captures overlapping multi-entry x86
  encodings ([code backings](docs/CODE_BACKINGS.md), [native UDL/UDC](docs/NATIVE_UDL_UDC.md)),
  and swaps pinned implementations across PE64, [Linux ELF64 and Clang C](docs/UDC_LINUX_AND_C.md),
  or guarded [Wasm/WebGPU browser shells](docs/UDC_BROWSER_SHELL.md)
  ([block layers](docs/UDL_BLOCK_LAYERS.md)).
- **Multi-target bounded-memory UDC:** retargets the same word-arena memory UIL,
  contiguous cuts and selectable RNG regions—demonstrated on the recovered Snake
  fixture—across [Wasm/WebGPU browsers](docs/UDC_MEMORY_BROWSER.md),
  [macOS ARM64 AppKit](docs/UDC_MEMORY_MACOS.md),
  [32/64-bit Windows GDI and Linux X11](docs/UDC_MEMORY_DESKTOP.md), and
  segmented 16-bit [Win16 NE executables](docs/UDC_MEMORY_WIN16.md).

## Console intake and synthesis

Beyond static cartridge and disc inspection, fDisBull compiles shared UIL and
reviewed source-bound console profiles into runnable hardware or native targets:

- **Shared NES & Genesis UDC (`console-udc`):** compiles an unsigned 8/16-bit UIL
  subset into native 6502 NES or 68000 Sega Genesis cartridges verified in real
  emulator cores ([console UDC](docs/CONSOLE_UDC.md)), packages compatible NROM
  titles behind a bank-switching menu while auditing commercial mappers
  ([NES multicarts](docs/NES_MULTICART.md)), and traces classic ROM bugs such as
  the [Mario minus-world warp](docs/MARIO_MINUS_WORLD.md).
- ***Miniplanets* Genesis & NES replay (`rom-game-lift`, `genesis-replay-*`):**
  lifts all 55 stages, hazards, globe projection, menus and soundtrack from the
  reviewed Genesis homebrew ROM into procedural UIL, compiling either to an
  experimental banked [full-game NES cartridge](docs/MINIPLANETS_FULL_GAME.md)
  ([first-level baseline](docs/MINIPLANETS_NES_LEVEL.md)) or back to a
  repeatable [native Genesis cartridge](docs/GENESIS_UIL_REPLAY.md) sustaining
  ~59.9 Hz display uploads in [Genesis performance checks](docs/GENESIS_PERFORMANCE.md).
- ***Shadowrun* Genesis & SNES studies (`shadowrun-*`):** exercises prepared-state
  Genesis slices from the [motel opening](docs/SHADOWRUN_UIL_OPENING.md) through
  [playable field targeting and damage](docs/SHADOWRUN_PLAYABLE_FIELD.md) and an
  [assisted hostile-actor arena](docs/SHADOWRUN_AI_EXPERIMENT.md). While bounded
  NES slices remain preserved as [research](docs/GENESIS_NES_RESEARCH_HANDOFF.md),
  the primary target compiles the same Genesis-bound UIL to a
  [native macOS ARM64 window](docs/SHADOWRUN_MACOS_ARM64.md)
  ([extended menus and courtyard](docs/SHADOWRUN_MACOS_EXTENDED.md)), alongside
  an independent [SNES 65816 morgue-movement recovery](docs/SHADOWRUN_SNES_MACOS.md)
  (`shadowrun-snes-build`) compiled to macOS ARM64. These are explicit
  source-bound slices, not general whole-ROM decompilers.

## Status, testing and history

Repository state is maintained in equal parity across local Git and GitLab
(`brewster-jennings-group/fdisbull`); GitHub is retired. Read
[CI coordination](docs/CI_COORDINATION.md) before inspecting hosted pipelines,
and consult [release status](docs/RELEASE_STATUS.md), the
[0.31.0 notes](docs/RELEASE-0.31.0.md), [0.30.0 notes](docs/RELEASE-0.30.0.md),
[0.29.0 notes](docs/RELEASE-0.29.0.md),
[PR backlog](docs/PR_BACKLOG.md), [offline dependencies](docs/OFFLINE_DEPENDENCIES.md)
and [system installation](docs/SYSTEM_INSTALLATION.md) for current qualification
receipts and platform limits.

For local development checks:

```bash
python -m pip install '.[test]' ./player build
python -m pytest -q
python -m build
python scripts/check_dist.py
python scripts/build_release.py
```

Ordinary test runs skip tests whose external emulators or toolchains are not
configured; required native acceptance uses real, separately prepared backends
([DOSBox acceptance](docs/DOSBOX_DEBUGGER.md#required-native-acceptance)) and
installed-wheel skill verification (`scripts/check_agent_skill.py`). Host checks
qualify only the tested platform and prefix. Repository examples and the
freeware review corpus are excluded from distributed tool wheels. Earlier
project history is preserved in [historical snapshots](docs/PROJECT_HISTORY.md).

No first-party distribution license has been selected. Public visibility does
not grant an open-source license. See [third-party provenance](docs/THIRD_PARTY.md).
