# fDisBull

**Designed by a human, refined by agents, and operated by agents.**

**fDisBull** (`0.34.1` / `v0.34.1`) is an agent-first reverse-engineering,
headless native-debugging, scene-automation, and semantic-reconstruction
(`UDL` → `UIL` → `UDC`) pipeline. It is not a human GUI disassembler—with over
400 structured CLI/JSON methods, no human is meant to operate its low-level
surfaces by hand. Instead, **the tool owns the mechanical middle** of binary and
media inspection, live emulator control, memory/event narrowing, state-binding,
and Z3-checked code generation, leaving the agent only **a few bounded judgment
decisions** along an automated seven-stage pipeline while giving the human
clear milestone reports, visual evidence, and explicit approval gates.

## Built to minimize token usage and survive long investigations

Reverse-engineering fails in LLM context windows when tools dump megabytes of
disassembly, memory, or trace logs into the prompt. fDisBull keeps model context
small and durable across turns and subagents:

- **Hard 64 KiB inline output ceiling (`fdisbull-output-ref-1`):** every core
  CLI/JSON reply is capped at 65,536 bytes inline by default
  ([bounded output](docs/OUTPUT_LIMITS.md)). Larger reports, traces, or state
  dumps are automatically written to immutable private files (`out-<sha256>`)
  and queried surgically by JSON Pointer (`output-select`), byte-range slice
  (`output-read`), or metadata (`output-info`) without re-running the operation
  or flooding the prompt.
- **Persistent SQLite project (`.fdb`) & vectorized source/concept DB
  (`fdisbull-source-catalog-1`):** decoded instructions, CFGs, cross-references,
  structural types, watch hits, Anchor Stones, and Z scene revisions persist in
  SQLite across sessions. Companion source trees and recovered concepts live in a
  dedicated SQLite catalog ([source & concept search](docs/SOURCE_CONCEPT_SEARCH.md))
  indexed with **SQLite FTS5** (`card_fts` Porter/Unicode61 lexical search),
  **normalized embedding vectors** (`embeddings`), and explicit `concept_links`
  so agents pull only the exact function, struct, or concept card needed.
- **Selective `<2 KiB` skill routing (`fdisbull-skill-catalog-1`):** three
  self-contained skills ship inside the wheel (`fdisbull`,
  `fdisbull-investigate`, `write-gamefaqs-guide`). Agents query the compact
  catalog (`fdisbull agent-skill --list`) and guide index (`--index`), loading
  only the single reference file required for the active stage.
- **Zero-GUI headless execution & sparse visual probes:** debuggers run
  headlessly with no pop-up windows by default. Agents check `visible`/`ready`/
  `enabled` predicates via sparse pixel masks or in-memory `frame_rgba()`
  buffers, rendering disassembly/CFG/frame PNGs directly from stored state when
  human-facing evidence is needed.

## The 7-stage automated agent pipeline

fDisBull automates the mechanical work at every stage and isolates the exact
decision left to the agent ([methodology determinism review](docs/METHODOLOGY_DETERMINISM_AB_PLAN_2026-11-08.md)):

| Stage | Automated by fDisBull (deterministic surfaces) | Only decision left to the agent |
| --- | --- | --- |
| **0. Setup & identity** | `preflight --expectations`, `capabilities`, `doctor`, `--version-json` | *None* (fully deterministic) |
| **1. Intake & triage** | `identify`, `media-inspect`, `media-extract` (native Inno 5.6.2 GOG, MADS, Westwood, ROM/ISO), `intake-inventory`, `capture-audit` | Target & deliverable framing (`references/task-framing.md`) |
| **2. Static structure** | `auto-analyze`, `function-patterns`, `xrefs`, `call-effects`, `define-type` → `apply-type` → `typed-data`, `code-regions`, `dos-sys-inspect`, `desqview-module-inspect`, `chimprec` | Which candidate function or record to confirm first |
| **3. Live observation** | `memory-search-start/refine/results` (guarded scalar narrowing), `execution-event-search` & `debug-trace-until` predicates, `serializer-discovery` (emits `next_step`) | Which discriminating probe to run next |
| **4. State binding & Z harness** | `serializer-candidates`, `debug-save-scene`, `z-controller`, `capture-action` → reusable named verbs, Anchor Stones & frame/CPU/RAM delta rewind | Semantic label of a verified field or control |
| **5. Dependency & goal queue** | `operation-goal` (computes ready vs. blocked recovery sets from facts), `work-queue`, `run-work`, `record-frontier` | Ordering ready questions across workers |
| **6. Claim qualification** | `proof-check` (bounded Z3 equivalence), `udl-verify`, `memory-accesses`, watchpoints | Sufficiency of evidence for exploratory claims |
| **7. Meaning & delivery** | Common indexed UIL (`uil-*`), multi-target UDC synthesis (DOS, PE, ELF, macOS ARM64, Wasm/WebGPU, NES, Genesis), human-readable guides & receipts | Meaning integration & user-approved `bind-source` gates |

## Core use cases (what humans ask for → what agents run)

Because fDisBull separates **deliverable depth** (`references/task-framing.md`)
from mechanical execution, a human can ask for anything from a single formula
explanation to a full cross-platform port, and the agent stops at the cheapest
stage that proves the answer:

1. **Explain an undocumented mechanic, formula, bug, or hidden branch (Reverse Engineering → Human Guide)**
   - **Human goal:** *"How does this DOS/Windows/console game actually compute combat odds, why does this dialog option soft-lock, or what hidden debug flags exist?"*
   - **Agent execution:** Unpacks the installer or disc natively (`media-extract`), imports the executable into `.fdb`, searches FTS5/vectorized source and concept cards (`source-search`, `concept-search`), narrows live memory or instruction triggers with guarded scalar/event searches (`memory-search-*`, `execution-event-search`, `debug-trace-until`), and compiles an attributed technical walkthrough or FAQ via `write-gamefaqs-guide`.
2. **Rapidly self-build an automation & AI-play harness through the `Z` representation (`Z` Controller)**
   - **Human goal:** *"Let agents jump straight into specific scenarios, run 100 balance/RNG experiments, or play a classic DOS/Win16 title over a structured text/JSON API without clicking through startup menus every time."*
   - **Agent execution:** The harness builds itself incrementally in the `Z` representation ([Z scenes](docs/Z_SCENES.md), [progressive scenes](docs/PROGRESSIVE_SCENES.md)) as the agent explores: each newly learned menu button, HUD control, room transition, or state field is immediately bound as a named `Z` verb (`capture-action`, `z-controller`) and composable route, while `serializer-discovery` and `debug-save-scene` unlock direct state loading—progressively replacing slow UI clicking with instant programmatic actions in either fair-play (`text-host --fair-play`) or assisted mode.
3. **Rapid QA on isolated code blocks with live debug-state rewind (Block-Targeted QA vs. Whole-Process Replay)**
   - **Human goal:** *"Test or fuzz a specific calculation, branch, or handler across dozens of edge-case inputs in seconds without restarting the process or replaying minutes of gameplay."*
   - **Agent execution:** Pins the live machine context right before the target routine with an [Anchor Stone](docs/ANCHOR_STONES.md), steps backward across recorded fetches ([`debug-rewind-*`](docs/DEBUGGER_REWIND.md)), or rewinds [CPU/RAM deltas](docs/CPU_RAM_DELTAS.md) (`debug-delta-*`) and [frame/input timelines](docs/FRAME_INPUT_TIMELINE.md) (`debug-timeline-*`, including partial-RNG preservation) to re-run only the target basic block or function in place. Agents can also lift that block into an isolated [UDL/UIL block layer](docs/UDL_BLOCK_LAYERS.md) (`udl-verify`, `proof-check`, CPU block checks) to test or prove inputs without running the surrounding process at all.
4. **Patch analysis, live behavioral diffing, and multi-language pre/post-patch export**
   - **Human goal:** *"Compare two game versions, an official patch, or an experimental hotfix—show me not just which bytes changed, but how the runtime behavior changed, and export the pre/post-patch logic in Python, JS, C, or assembly for review."*
   - **Agent execution:** Captures each binary version or non-destructive [code layer](docs/CODE_LAYERS.md) in `.fdb`, replays identical inputs from a shared Anchor Stone in [saved debugger experiments](docs/DEBUGGER_EXPERIMENTS.md), and diffs the **live behavioral outcomes** (register trajectories, memory writes, RNG branches, and rendered frames)—not just static instructions. It then lifts both the pre-patch and post-patch blocks into [common UIL](docs/COMMON_UIL_CONTRACT.md) (`uil-*`) to export side-by-side behavioral diffs in any supported language (**Python**, **JavaScript**, **Clang C**, **x86/ARM64/6502/68000 assembly**, or **Z3 equivalence counterexamples**).
5. **Unpack, audit, and compare legacy installers, packed Windows PEs, and multi-edition collections**
   - **Human goal:** *"Inventory this folder of GOG installers, floppy/CD images, ROMs, and TAS captures on macOS/Linux without Wine, rebuild imports from a captured packed PE, and show how editions differ."*
   - **Agent execution:** Runs `intake-inventory`, `capture-audit`, and `media-inspect`/`media-extract` (built-in Inno Setup 5.6.2 GOG reader, MADS `.HAG`/`.MAD`, Westwood `.PAK`, CUE/ISO, NES/SNES/Genesis/Saturn headers), or recovers an import table from a caller-supplied process dump via `chimprec`, recording every hash, edition diff, and asset map in `.fdb`.
6. **Lift verified subsystems into portable `UIL` and recompile across platforms (`UDC` Porting & Modernization)**
   - **Human goal:** *"Extract the rules engine, serializer, or full playable loop of a 16/32-bit x86, ARM64, AGI, Z-machine, or MADS title and build a verified native macOS ARM64, Linux, Windows, WebAssembly/WebGPU, or NES/Genesis target."*
   - **Agent execution:** Lifts native blocks or guest bytecode into `UDL` → typed indexed `UIL` (`uil-*`), proves mathematical block equivalence with Z3 (`proof-check`, `udl-verify`), tracks unresolved serializer/UI children in `operation-goal` and `work-queue`, and emits a signed native or browser build through `UDC`.
7. **Inspect and repack adventure scripts, dialog trees, and cinematic resources in place**
   - **Human goal:** *"Map every conversation branch and room script in a MADS, Sierra AGI, or Z-machine adventure, or generate a compact playable cutscene variant."*
   - **Agent execution:** Decodes guest conversation bytecode, vocabulary tables, and scene scripts (`mads-inspect`, `mads-compile`, `mads-compact`, `agi-*`, `zmachine-*`) directly into structured JSON and UIL while keeping commercial originals isolated in the private local object store.
8. **Run multi-agent parallel reverse engineering overnight without context-window blowup**
   - **Human goal:** *"Have a coordinator and worker subagents map out an entire binary's subsystems in parallel without duplicating probes or burning millions of tokens on raw dumps."*
   - **Agent execution:** A single controller owns the live headless guest while parallel workers pull bounded, non-overlapping questions from the persistent dependency queue (`work-queue`, `run-work`), inspect shared `.fdb` facts and 64 KiB-capped `out-<sha256>` slices (`output-select`), and commit verified types, xrefs, and concepts back to SQLite.

**Current release (`0.34.1` / `v0.34.1`):** unifies deterministic capability
preflight and build identity (`--version-json`, `preflight`), the top-level
`fdisbull` skill router, the
[7-stage methodology determinism review and Dragster A/B plan](docs/METHODOLOGY_DETERMINISM_AB_PLAN_2026-11-08.md),
built-in Inno Setup 5.6.2 GOG archive reading without external `innoextract`,
independent [MADS media and conversation modules](docs/MADS_MEDIA_RUNTIME.md)
([conversation processor](docs/MADS_PROCESSOR.md)), Westwood/format media
intake, captured Windows PE import recovery ([CHimpREC](docs/CHIMPREC.md)),
[DOS device-driver and QEMM guest analysis](docs/DOS_DRIVERS_AND_QEMM.md),
[DESQview module inspection and persistent guarded memory searches](docs/DESQVIEW_AND_MEMORY_SEARCH.md),
[execution-event searches with trace predicates](docs/EXECUTION_EVENT_SEARCH.md),
Win32 and protected-mode DOS debugging, exact lossless frame codecs and
`frame_rgba()`, headless DOSBox-X no-pop-up defaults, experimental ScummVM
AGI/Gob/Kyra/GLK backends, and signed UDC contracts. See
[release records](docs/RELEASE_STATUS.md),
[feature history](docs/FEATURE_HISTORY.md), and the
[GitLab release inventory](https://gitlab.com/brewster-jennings-group/fdisbull/-/releases)
for exact published source identities, qualification receipts and package hashes.

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
| Verify this copy's version, build identity, decoders, debuggers and preflight expectations without running a target | [Capabilities catalog](docs/CAPABILITIES.md) · [Methodology determinism & preflight](docs/METHODOLOGY_DETERMINISM_AB_PLAN_2026-11-08.md) |
| Understand an x86, ARM64 or Cortex-M executable without running it | [Disassemble, type and search](#disassemble-type-and-search) |
| Unpack a local GOG DOS installer (including Inno 5.6.2 natively) on macOS or Linux without Wine | [Native GOG unpacking](docs/GOG_UNPACKING.md) |
| Rebuild a caller-captured packed Windows PE or GOG Galaxy UPX wrapper | [CHimpREC captured-image recovery](docs/CHIMPREC.md) · [GOG Galaxy workflow](docs/GOG_UNPACKING.md#galaxy-upx-wrappers) |
| Identify an unfamiliar executable or media file, inspect MADS resources/dialogs, or prepare a compact cinematic variant | [Format modules and header catalog](docs/FILE_FORMAT_REGISTRY.md) · [MADS media & conversation model](docs/MADS_MEDIA_RUNTIME.md) |
| Inventory one game or a collection, compare editions or inspect resource/media formats | [Collection intake](docs/TARGET_COLLECTION_INTAKE.md) · [TAS/AVI capture audit](docs/TAS_CAPTURE_AUDIT.md) |
| Identify NES, SNES or Sega cartridges, CUE/ISO discs, or disassemble Saturn SH-2 / SNES 65816 | [Console media](docs/CONSOLE_MEDIA_PARSING.md) · [Disc parsing](docs/CUE_ISO_PARSING.md) · [ROM-to-ASM](docs/ROM_ASM.md) |
| Share structural types or search edition-pinned C source and verified DOS byte maps | [Portable type catalogs](docs/TYPE_CATALOGS.md) · [Source & concept search](docs/SOURCE_CONCEPT_SEARCH.md) · [Verified CivD maps](docs/CIVD_VERIFIED_SOURCE_MAPS.md) |
| Debug an original DOS or Windows program headlessly | [Debug the original program](#debug-the-original-program) |
| Inspect DOS `.SYS` drivers, QEMM/v86 mappings, DESQview modules, or narrow changing memory values | [DOS drivers & QEMM](docs/DOS_DRIVERS_AND_QEMM.md) · [DESQview and memory searching](docs/DESQVIEW_AND_MEMORY_SEARCH.md) |
| Find code or register values associated with an action, or stop at an instruction predicate | [Execution event searching](docs/EXECUTION_EVENT_SEARCH.md) |
| Investigate a macOS ARM64 binary or capture a reversible macOS status-menu session | [macOS ARM64 analysis](docs/MACOS_ARM64_ANALYSIS.md) · [Reversible native capture](docs/MACOS_REVERSIBLE_CAPTURE.md) |
| Rewind execution, branch frame inputs, test code layers or run partial-RNG delta experiments | [Layers, states, rewind and experiments](#layers-states-rewind-and-experiments) |
| Give an agent named controls, game-unit room maps and explicit spatial policies | [Scenes, maps and interaction policies](#scenes-maps-and-interaction-policies) |
| Play shared Z scenes, original-backed *DinoPark Tycoon*, or inspect *Civilization I* / *Zork I* worlds | [Text play and world projections](#text-play-and-world-projections) |
| Lift Sierra AGI v2 (*King's Quest I*), Z-machine v3 (*Zork I*) or MADS conversations in their guest languages | [Direct guest interpreters: AGI, Z-machine and MADS](#direct-guest-interpreters-agi-z-machine-and-mads) |
| Compose typed indexed UIL and emit standalone Python/JS, linked native binaries or desktop windows | [Common UIL contract](docs/COMMON_UIL_CONTRACT.md) · [Native linking](docs/COMMON_UIL_NATIVE.md) · [Desktop shells](docs/COMMON_UIL_DESKTOP.md) |
| Verify source blocks with Z3 or retarget bounded-memory UIL across browser, macOS, Windows, Linux and Win16 | [Common UIL and the bounded UDC pipeline](#common-uil-and-the-bounded-udc-pipeline) |
| Compile shared UIL or source-bound *Miniplanets* / *Shadowrun* profiles to NES, Genesis or macOS ARM64 | [Console intake and synthesis](#console-intake-and-synthesis) |

Agents should start with [AGENTS.md](AGENTS.md), [CLAUDE.md](CLAUDE.md), the
[agent quickstart](docs/AGENT_QUICKSTART.md) and the
[skill integration guide](docs/SKILL_INTEGRATION.md). Three bundled skills ship
inside the installed package and work without opening a project:

- `fdisbull agent-skill --skill fdisbull --reference SKILL.md` (`fdisbull`): top-level router skill for choosing between investigation (`fdisbull-investigate`) and human-readable guide authoring (`write-gamefaqs-guide`).
- `fdisbull agent-skill --reference SKILL.md` (`fdisbull-investigate`): evidence-driven reverse engineering, task-framing (`references/task-framing.md`), probe selection, scene/UIL recovery, source-concept mapping and verification gates.
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
fdisbull --version-json
fdisbull capabilities
fdisbull preflight
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

- **DOS & 16/32-bit Windows:** classic MZ, explicit COM,
  [DOS `.SYS` device drivers](docs/DOS_DRIVERS_AND_QEMM.md) (`dos-sys-inspect`),
  [DESQview `.DVR` modules](docs/DESQVIEW_AND_MEMORY_SEARCH.md) (`desqview-module-inspect`),
  bounded 32-bit [DOS/4GW LE](docs/dos4gw-le.md) objects and fixups, 16-bit
  [Win16 NE](docs/NE_LOADING.md) segments with logical `ne:seg:offset` addresses
  and symbolic relocations, OMF library signature catalogs (`omf-catalog`), and
  [DOS audio drivers](docs/DOS_AUDIO_DRIVERS.md) (Miles AIL 2 `.ADV` exports
  via `--image ail`, plus named DIGPAK/MIDPAK `INT 66h` calls).
- **Modern desktops:** Windows PE32/PE64 (plus optional .NET CIL via `managed`),
  Linux ELF, and [macOS Mach-O ARM64](docs/MACOS_ARM64_ANALYSIS.md) with
  `LC_FUNCTION_STARTS`/unwind seeds, exact file-offset `code-backings`, and
  optional source-bound Headless Ghidra (`ghidra-arm64`) C/instruction
  diagnostics.
- **Captured packed Windows PEs:** source-bound CHimpREC recovery accepts caller-owned
  PE32/PE32+ mapped-module captures and loaded-export maps, recovers named and
  ordinal imports, requires explicit decisions for ambiguous or junk thunks,
  and rebuilds analysis images with original IAT addresses, new
  OriginalFirstThunk tables, a qualified OEP and verified checksum. A bounded
  GOG Galaxy profile covers captured UPX0/UPX1 wrappers. This is structural,
  fixed-base analysis reconstruction; Windows loader execution needs separate
  qualification. It does not download, launch, attach to or bypass protections
  in Galaxy.
- **Embedded & console media:** static [Armv7-M Cortex-M](docs/CORTEX_M.md)
  flash images with Thumb/Thumb-2 vector-table traversal (exercised on 121GW
  2.05 meter firmware without hardware emulation), non-executing
  [cartridge](docs/CONSOLE_MEDIA_PARSING.md) (`rom-inspect`) and
  [CUE/ISO disc](docs/CUE_ISO_PARSING.md) (`disc-inspect`) headers, three-engine
  Saturn SH-2 [ROM disassembly](docs/ROM_ASM.md) (`rom-disasm` across Capstone,
  Ghidra and `saturn-recomp`), mode-explicit SNES 65C816 decoding, and
  reusable [media adapters](docs/AGENT_QUICKSTART.md#reuse-media-readers)
  (`media-modules`, `media-inspect`, `media-extract`), built-in Inno Setup 5.6.2
  [GOG archive reading](docs/GOG_UNPACKING.md) without external `innoextract`,
  and independent [MADS media and compression codecs](docs/MADS_MEDIA_RUNTIME.md)
  (`fab`, `madspack`, `pkware-dcl`, `mads-*` for HAG containers, sprites, tiles,
  depth/walk masks, fonts, audio and animations).

The [format catalog](docs/FILE_FORMAT_REGISTRY.md) distinguishes a recognized
header from an implemented decoder. Collection intake retains edition and
consumer context instead of guessing from a suffix. Restricted `smk-frame`
variants retain opening/ending images and complete embedded audio with native
hold frames between; independent decoding and original-game playback remain
separate checks. See [media coverage](docs/INTAKE_MEDIA_COVERAGE.md). The audited
cinematic experiment changes media in a separate variant while preserving the
original executable.

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

An experimental [ScummVM AGI backend](docs/SCUMMVM_BACKEND.md) provides a
headless replacement-engine investigation path with script state, breakpoints,
input and stored frames. Its evidence identifies ScummVM separately from the
original DOS interpreter. See the [matched scene experiment](docs/SCUMMVM_DOS_SCENE_COMPARISON.md)
for the tested scope and measured results.

The separate experimental [Gob backend](docs/SCUMMVM_GOB_BACKEND.md) supports
Lost in Time investigation through a patched ScummVM 2026.4.0 runtime. It adds
typed script state, source-bound execution control, hotspot receipts and stored
frames. Native game checkpoints and script patching remain unsupported; the
stock ScummVM application alone does not provide this debugger protocol.
The [Lost in Time comparison](docs/SCUMMVM_LOSTTIME_COMPARISON.md) records the
original-DOS checks, nail visibility regression and fresh Z authoring results.

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
  [Protected-mode DOS](docs/DOS_PROTECTED_RUNTIME.md) adds checked runtime RAM
  bindings, guarded live edits and native whole-machine checkpoints, while
  retaining explicit CPU-mode and address-space limits.
  [QEMM and DESQview profiles](docs/DOS_DRIVERS_AND_QEMM.md) observe v86/page-frame
  mappings and cooperative API calls, [persistent scalar memory searches](docs/DESQVIEW_AND_MEMORY_SEARCH.md)
  narrow changing values across stopped snapshots with guarded conditional edit
  rules, and [execution-event searches](docs/EXECUTION_EVENT_SEARCH.md)
  (`debug-event-search-*`, `debug-trace-until`) isolate shared or differential
  instructions and register values across actions. Agent headless launches
  disable the quit confirmation and mute audio; visible launch preferences
  remain separate.
- **Windows targets:** the [Windows debugger](docs/WINDOWS_ORIGINAL_RUNTIME_BRIDGE.md)
  adds a Win32 PE32 route and experimental Win16 support alongside PE64.
  A prepared offline Wine/QEMU guest provides actual program stops, scoped
  watches, memory, traces and shared keyboard/frame/scene actions. Windows
  `--dot-mode` supplies a read-only spectator without capturing host input.
  PE32 uses its actual 32-bit CPU context. Win16 requires observed selector
  mappings and restricts register edits; its native checkpoints, code layers
  and delta rewind remain unavailable.
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

For repeated frame inspection, optional exact indexed PNG and raw RGBA8 with
Zstandard retain frame identity and pixel hashes. Indexed PNG falls back to
RGBA PNG when an exact palette is unavailable. `frame_rgba()` gives Python
callers a checked in-memory buffer without writing an artifact; `screenshot()`
continues to save PNG evidence. Raw Zstandard requires a matching backend and
the `screenshot` extra. The [DinoPark codec study](docs/VERIFICATION-DINOPARK-SCREENSHOT-CODECS-2026-11-03.md)
and [direct-consumer study](docs/VERIFICATION-DINOPARK-DIRECT-RGBA-2026-11-03.md)
measure specific paused scenes, rather than promising a universal speedup.

## Layers, states, rewind and experiments

Explore runtime hypotheses without losing your baseline:

- **Code layers, patch analysis and live behavioral diffing:** apply reversible
  RAM edits or DOS instruction-fetch overlays, capture runtime code alongside
  earlier byte versions, compare baseline versus patched or single-layer runs
  from a shared Anchor Stone, and lift pre/post-patch blocks through `UDL` →
  `UIL` to export behavioral (not just byte/instruction) differences into
  Python, JavaScript, C, assembly or Z3 proofs. See
  [code layers](docs/CODE_LAYERS.md), [saved experiments](docs/DEBUGGER_EXPERIMENTS.md),
  [debugger scripts](docs/DEBUGGER_SCRIPTS.md), [block layers](docs/UDL_BLOCK_LAYERS.md)
  and [runtime code](docs/RUNTIME_CODE.md).
- **Anchor Stones and next-fetch rewind:** full native saved states—called
  [Anchor Stones](docs/ANCHOR_STONES.md), a nod to TiGa's *Blob to General*—let
  sessions jump directly to a verified machine context, while bounded
  [debugger rewind](docs/DEBUGGER_REWIND.md) (`debug-rewind-*`) steps backward
  across recorded next-fetch intervals.
- **Automatic frame/input timeline:** on frame-capable DOS backends,
  [frame timelines](docs/FRAME_INPUT_TIMELINE.md) (`debug-timeline-*`) cache
  completed frames and full states with frame-scheduled physical keyboard
  make/break edges, supporting instant rewind, input branching and durable
  Anchor Stone pins. Optional [frame-state delta storage](docs/FRAME_STATE_DELTAS.md)
  reduces retained payloads through verified keyframes and XOR chains; it still
  captures a full state at every point and does not promise faster recording.
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

## Direct guest interpreters: AGI, Z-machine and MADS

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
- **MicroProse MADS conversations (`fdisbull.mads.conversation`):** decodes
  CNV/CND conversation bytecode from HAG and MADSPACK 2.0 containers through the
  registered [MADS conversation processor](docs/MADS_PROCESSOR.md) and executes
  bounded transactional dialog turns with explicit variable imports and
  deterministic replay ([MADS media and conversation model](docs/MADS_MEDIA_RUNTIME.md)).
  Native DOS scene binaries and RTLink overlays remain separate x86 targets.

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

GitLab (`brewster-jennings-group/fdisbull`) and the local Git hub are the
release and CI authority; GitHub (`seeker-cyber-maker/fDisBull`) is an active
public peer mirror. Read
[CI coordination](docs/CI_COORDINATION.md) before inspecting hosted pipelines,
and consult [release status](docs/RELEASE_STATUS.md), the
[methodology determinism review](docs/METHODOLOGY_DETERMINISM_AB_PLAN_2026-11-08.md),
[0.33.0 notes](docs/RELEASE-0.33.0.md), [0.32.0 notes](docs/RELEASE-0.32.0.md),
[0.31.1 notes](docs/RELEASE-0.31.1.md),
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
