# Choose an investigation workflow

Use this reference to route a task to the smallest relevant fDisBull surface.
Every command uses caller-selected paths. The Python package does not include an
emulator, target executable, game files, saved states or project databases.

## Contents

- [Start from the user's outcome](#start-from-the-users-outcome)
- [Static analysis, media and source catalogs](#static-analysis-media-and-source-catalogs)
- [Native investigation, rewind and macOS capture](#native-investigation-rewind-and-macos-capture)
- [Scenes, maps and movement](#scenes-maps-and-movement)
- [Seed scene hypotheses from guides](#seed-scene-hypotheses-from-guides)
- [Player, Z scenes and direct guest interpreters](#player-z-scenes-and-direct-guest-interpreters)
- [Common UIL, multi-target UDC and console synthesis](#common-uil-multi-target-udc-and-console-synthesis)
- [Research-backed progression](#research-backed-progression)
- [Retain knowledge without overstating it](#retain-knowledge-without-overstating-it)
- [Retrieve bounded output](#retrieve-bounded-output)
- [Compare related programs](#compare-related-programs)

## Start from the user's outcome

| Need | Starting point | Evidence boundary |
| --- | --- | --- |
| Check local decoders, debuggers, C diagnostics and UIL scope | `capabilities`, `methods`, `doctor` | `capabilities` detects code and PATH/Python dependencies without running tools (`runtime_validation: not_run`); `doctor` runs separate runtime acceptance. |
| Unpack GOG installers, extract MZ/AGI members or audit AVI video | `media-modules`, `media-inspect`, `media-extract`, `gog-list`/`gog-unpack`, `capture-audit` | Non-executing structural extraction or full-frame RGBA hashing only; no guest clock mapping or execution proof. See [media-modules.md](media-modules.md). |
| Identify or analyze an x86, ARM64 or Cortex-M binary | `identify`, `inspect`, `import`, `analyze`, `auto-analyze`, `analysis-status`, `functions`, `disasm`, `xrefs`, `render` | Static decoder facts and stored SQLite analysis only; candidate functions, indirect transfers and budget frontiers stay labeled. |
| Prove or falsify a stored-value, writer or trigger claim in a binary | Decoded image offsets, xrefs and positive/negative writer controls | Scoped to pinned decoded editions and static scan windows; see [binary-claim-verification.md](binary-claim-verification.md). |
| Inspect console cartridges, CUE/ISO discs or Saturn SH-2 / SNES 65816 | `rom-inspect`, `disc-inspect`, `rom-disasm`, `fdisbull.snes_decode` | Header/track facts and mode-explicit instruction decoding; decoding never proves a region is reachable code. |
| Index edition-pinned source or verify period build-to-byte maps | `source-create`, `source-import`, `source-search`, `source-concept`, `source-build`, `source-map-native` | Separate from `.fdb` projects; lexical/vector ranks and symbol names require independent native qualification. See [source-and-concepts.md](source-and-concepts.md). |
| Observe actual DOS, Windows PE32/PE64/NE or macOS ARM64 behavior | `debug PROJECT ...`, `Project.debugger()`, `macos-observe`, `macos-snapshot`/`macos-session` | Requires a compatible external backend and authorized target; verify live source/version binding and real guest or UI effects. |
| Reuse visible controls, audit coordinate domains or map a route | Versioned scenes, `debug-scene-domain-audit`, spatial maps, `debug-spatial-domain-audit`, `session.move()` | Authored geometry or observed segments; unknown cells, scrolling overhangs and engine movement remain separate. |
| Run an authored slice, `text-host` projection or shared-IL Z service | `fdisbull-player` (`--package`, `--connect`, `--backend-command`), `fdisbull text-host` | Projections are bounded interfaces, not full game parsers; action freshness, batch journals and checkpoints have distinct contracts. |
| Inspect or lift Sierra AGI v2 or Z-machine v3 guest scripts directly | `decoder-modules`, `module-analyze`, `module-lift`, `agi-logic`, `agi-scenes`, `kq1-bow-*`, `story-info`, `zmachine-*`, `zork-uil`/`zork-intents`/`zork-scenes` | Guest-language front ends work without an x86 `.fdb`; unmodeled engine effects and residual IR remain explicit. |
| Compose typed indexed UIL into Python/JS, native links or desktop windows | `uil-check`, `uil-catalog`, `uil-run`, `uil-link`, `uil-components`, `uil-compile`, `uil-build`/`uil-seal`, `uil-desktop*`, `uil-fold`/`uil-expand`, `uil-store` | Emits standalone code or fixed-arena AppKit/X11/Win32 shells; build/seal is not runtime or source-equivalence qualification. See [common-uil.md](common-uil.md). |
| Reconstruct DOS blocks, retarget memory UIL or synthesize console ROMs | `udl-*`, `udc-*`, `code-backings`, `build-memory-*-shell`, `console-udc`, `rom-game-lift`, `genesis-replay-*`, `nes-multicart-*`, `shadowrun-*` | Scoped to declared spans, arenas or reviewed ROM profiles; qualify `original → UIL` and `UIL → target` edges separately. See [udl-uil-udc.md](udl-uil-udc.md). |

For concise command routes in a source checkout, read `docs/AGENT_QUICKSTART.md`.
Use `fdisbull methods` and `<subcommand> --help` rather than guessing flags.

## Static analysis, media and source catalogs

Inspect before importing so format, slice and image profile are explicit:

- **DOS & 16/32-bit x86:** pass `--image com` for DOS COM files (a `.com` suffix
  alone is not format evidence), `--image ne` (or auto-detection) for 16-bit
  Win16 NE logical `ne:seg:offset` segments, and `--image ail` for Miles AIL 2
  `.ADV` audio drivers (`dos-services` names DIGPAK/MIDPAK `INT 66h` calls;
  `omf-catalog` builds OMF library signature catalogs). Bounded 32-bit DOS/4GW
  LE objects and internal fixups load into the existing x86 analyzer.
- **Desktop & embedded:** import PE32/PE64 (plus optional `managed` .NET CIL),
  Linux ELF, Mach-O ARM64 (`--slice-arch arm64`, with `code-backings` and
  optional source-bound `ghidra-arm64` instruction/C diagnostics), or static
  Armv7-M Cortex-M flash profiles (Thumb/Thumb-2 vector-table traversal).
- **Console & recorded media:** inspect cartridge headers (`rom-inspect`),
  CUE/BIN + ISO 9660 tracks (`disc-inspect`), bounded Saturn SH-2 ranges
  (`rom-disasm` across Capstone, Ghidra and `saturn-recomp`), and mode-explicit
  SNES 65C816 spans (`fdisbull.snes_decode`). For finalized AVI recordings,
  `capture-audit` verifies every decoded RGBA frame hash before pixel review.

Start recursive analysis with an explicit instruction budget and check
`analysis-status` or `advanced-status` for pending work; a bounded stop never
establishes convergence. `render` and `render-cfg` export PNGs from stored
project state without launching a GUI or target. For container extraction,
collection intake, edition diffs and consumer-safe media reduction, read
[formats-and-media.md](formats-and-media.md). When screening for an embedded
bytecode VM or cross-file loader edge, read [methodology.md](methodology.md).

## Native investigation, rewind and macOS capture

Launch only with the user's actual executable, game directory, byte version and
compatible backend. DOS (`dosbox` or QEMU), PE32/PE64 (`wine-qemu`), NE (`wine-ne`) and macOS probes
have distinct capabilities; live JSON debugging requires a retained session
(`serve` or `debug`), never a one-shot `request`. Prefer ordinary guest input
with explicit guest-time and wall-time ceilings, and verify input consumption
before interpreting display or memory changes. Checkpoint restore never rolls
back mounted host files or external services.

- **Windows scenes and spectator:** original PE32 and NE use actual process
  widths and observed address bindings. Shared keyboard, native `frame-probe`
  and named scenes use host-time slices, not DOS guest ticks. `--dot-mode` or
  `dot_mode=True` exposes an owned read-only loopback viewer, refreshed at stops;
  it never hooks or forwards host input. Query `debug-spectator` for its URL.
  No-client-window capture is recoverable; an exception interrupts a scene and
  retains queued input rather than replaying it. NE logical segments require
  live source/selector verification, and native NE states/deltas/layers remain
  unavailable. See `docs/WINDOWS_ORIGINAL_RUNTIME_BRIDGE.md`.
- **Finite Windows route fuzzing:** `fdisbull fuzz` accepts a private bounded
  campaign of explicit keyboard, click or named scene-action choices. It runs
  each candidate in a fresh owned Wine NE/PE guest and records sanitized
  stage/fault feedback. Review the private-input, storage and qualification
  contract in `docs/WINDOWS_ORIGINAL_RUNTIME_BRIDGE.md` before a native run;
  an exception stop is only a crash candidate.
- **Anchor Stones:** full native saved states use `debug-save-anchor-stone`,
  `debug-load-anchor-stone` and offline `debug-anchor-stone-info` (legacy state
  method names remain compatible; see `docs/ANCHOR_STONES.md`).
- **Automatic DOS frame/input timeline (`frame_timeline` backends):**
  `debug-timeline-start`, `debug-timeline-advance`, `debug-timeline-rewind` and
  `debug-timeline-pin` maintain a live cache of completed frames and full states
  with physical keyboard make/break edges scheduled before selected frames.
  `storage_mode='delta'` optionally retains lossless native-payload deltas with
  bounded keyframes; full native capture still happens each frame
  (`docs/FRAME_INPUT_TIMELINE.md`, `docs/FRAME_STATE_DELTAS.md`). Unrecorded
  input or execution invalidates the cursor; frame cadence depends on the guest
  video mode rather than an assumed 60 Hz.
- **Bounded next-fetch DOS rewind:** `debug-rewind-start`, `debug-rewind-record`,
  `debug-rewind-status` and `debug-rewind` step across recorded next-fetch
  states without instruction-retirement claims (`docs/DEBUGGER_REWIND.md`).
- **CPU and RAM delta rewind (DOSBox & Wine/QEMU x86-64):** `debug-delta-*`
  records net exposed-register and declared writable RAM changes anchored to one
  full recovery stone (`docs/CPU_RAM_DELTAS.md`, `docs/WINE_CPU_RAM_DELTAS.md`).
  Default undo blocks execution, capture and snapshots until full native
  recovery. Passing an explicit `policy` (`name`, `preserve_registers`,
  `preserve_memory`, and `allow_partial_resume: true`, e.g., for caller-evidenced
  RNG bytes) ends the chain and permits experimental continuation with
  `partial_restored: true` and `resume_safe: false`—never report such a run as
  deterministic TAS replay or machine parity.
- **DOS watchpoints and guest exit:** normalized DOS data watches report
  `instruction_completed=null` and `registers_stage="after-access"` (check
  remaining `CX` on `REP` operations before claiming completion). Backends
  advertising `lifecycle.dos_guest_exit` distinguish selected-PSP `guest_exit`
  cleanup from resident `guest_tsr` or session shutdown.
- **macOS ARM64 & reversible UI capture:** `macos-observe` runs a source-bound
  ARM64 executable to a single LLDB breakpoint. On macOS 14+, `macos-snapshot`
  inspects displays and target accessibility without input; `macos-session`
  journals bounded captures (and, only with `--live`, declared status-menu or
  `CFPreferences` trials) using CoreGraphics global logical coordinates, while
  `macos-session-recover` restores owned pending changes (`docs/MACOS_REVERSIBLE_CAPTURE.md`).

## Scenes, maps and movement

Use scenes for versioned screen context, pixel masks, `visible`/`ready`/`enabled`
predicates and guarded actions, and spatial maps for game-unit safe regions,
actor footprints, obstacles, hazards and interaction zones. Audit off-screen
objects and scrolling margins with `debug-scene-domain-audit` or
`debug-spatial-domain-audit`. Read [scenes.md](scenes.md) for scene authoring
and [runtime-navigation.md](runtime-navigation.md) for spatial policies
(`physical`, `assisted`, `story`, and voluntary `--fair-play`), bounded route
proposals and sparse pixel/memory probes.

## Seed scene hypotheses from guides

Start with the current scene and a small likely frontier. External guide labels,
exits and prerequisites remain hypotheses until bound to the selected source and
observed at runtime where required. Visual claims need viewed frames rather than
text transcripts alone; keep future guide spoilers out of live player narration.

## Player, Z scenes and direct guest interpreters

- **Standalone `fdisbull-player` & `text-host`:** `--package` evaluates an
  authored JSON slice; `--connect HOST:PORT` attaches to `fdisbull text-host`
  over trusted local loopback; `--backend-command` runs a local Z scene service
  (such as `python -m fdisbull.il_scenes`, `fdisbull.strategy_z` or
  `fdisbull shadowrun-z`) without a shell and with `--backend-timeout`. `--live`
  checkpoints turns; `--batch-plan` and `--batch-journal` record ordered
  dispatches and pause partial or notice-interrupted steps for certified
  checkpoint reconciliation (`docs/Z_BATCH_RECOVERY.md`, `docs/Z_REPLY_RECOVERY.md`).
- **Original-backed DinoPark Z (`fdisbull.dinopark_z`):** verifies and launches
  the user's original game via DOS UDC in a new private work directory. Supports
  loans, land, fencing, supplies, Coelophysis/catalogue purchases, hiring, park
  opening, month rollover, `save park` disk persistence and named menu/quit
  actions (`docs/DINOPARK_Z.md`). When an error leaves a stopped reachable guest
  in `recovery_required`, new actions and checkpoints refuse until an explicit,
  previously qualified checkpoint restore re-verifies native fields and scene
  identity.
- **Direct AGI v2 & Z-machine v3 front ends:** `decoder-modules` and
  `module-analyze` inspect AGI v2 logic or checksum-qualified Z-machine v3
  stories (`story-info`, `zmachine-disasm`, `zmachine-analyze`) without a native
  `.fdb`. For AGI 2.917, run `agi-scenes --stage outline|resolve` (see
  [agi-scenes.md](agi-scenes.md)), lift bounded components with `module-lift`
  (including `--control-flow compact` and `--effect-profile agi-2.917`), compare
  leaf invocations against live DOS via `AGIDOSHostAdapter`, or evaluate the
  qualified KQ1 bow (`kq1-bow-intents` / `kq1-bow-evaluate`). For Zork I R88,
  `zork-uil` lowers word16 IR, `zork-intents` adds source-linked mailbox rules
  with fault receipts, and `zork-scenes` recovers 110 named rooms and 352 exits
  with live guards and explicit residual IR (see [scene-recovery.md](scene-recovery.md)).

## Common UIL, multi-target UDC and console synthesis

- **Indexed Common UIL (`uil-*`):** validate (`uil-check`), build UDL semantic
  catalogs (`uil-catalog`), evaluate copy-in/copy-out frames (`uil-run`), fold
  or expand hierarchies (`uil-fold`/`uil-expand`), persist immutable packages
  (`uil-store`/`uil-info`/`uil-list`), emit standalone Python/JavaScript or link
  and compile native `macos-arm64`, `linux-x64` and `windows-x64` realizations
  with C/ASM component selection (`uil-link`, `uil-components`, `uil-compile`,
  `uil-build`, `uil-seal`), and build fixed-arena AppKit/X11/Win32 desktop
  shells (`uil-desktop`, `uil-desktop-build`, `uil-desktop-seal`). Follow
  `common-uil.md` for schemas and qualification gates.
- **DOS, Web and Multi-Target Memory UDC:** capture byte-exact MZ/COM definitions
  (`udc-*`, `udc-native-*`), overlapping x86 `code-backings` / `code-layout`,
  and selectable block/memory layers (`store-*-contract`, `store-*-udl-layer`,
  `select-*-udl-layers`), retargeting pure or bounded-memory word arenas across
  Wasm/WebGPU (`build-web-*`, `build-memory-web-*`), macOS ARM64 AppKit
  (`build-memory-macos-shell`), 32/64-bit Windows GDI and Linux X11
  (`build-memory-desktop-shell`), and segmented 16-bit Win16 NE
  (`build-memory-win16-shell`).
- **Console synthesis (`console-udc`, Genesis, NES, SNES):** compile shared
  8/16-bit UIL to native NES or Sega Genesis ROMs (`console-udc`), package
  authored-compatible NROM pairs (`nes-multicart-*`), export repeatable
  *Miniplanets* procedural game/audio/display/PSG bundles to banked NES or
  native Genesis (`rom-game-lift`, `genesis-replay-*`), or build bounded
  prepared-state *Shadowrun* Genesis and SNES slices (`shadowrun-*`, with native
  `macos-arm64` recommended for desktop play and NES slices scoped as bounded
  research). Follow `udl-uil-udc.md` for every target's exact contract.

## Research-backed progression

For normal progression or source-assisted recovery, read
[recovery-research.md](recovery-research.md) to pin editions, build
source-attributed milestone checklists and test candidate transitions. Use
[semantic-contracts.md](semantic-contracts.md) to compare guards, effects,
timing and projection losses across representations while keeping unrecovered
behavior in working lower-level IR.

## Retain knowledge without overstating it

Promote verified facts into versioned scenes, spatial anchors, type/signature
catalogs, source links or UIL packages only when doing so lowers future probe
cost. Preserve provenance and revalidate whenever source bytes, resources,
rooms, layers or backends change. Keep target-specific addresses and private
paths in project evidence rather than in reusable skills.

## Retrieve bounded output

Core JSON replies default to 64 KiB inline. Oversized results return an
`fdisbull-output-ref-1` marker (`complete: false`, `status: artifact_required`)
while retaining the execution summary separately. Inspect or slice the archived
JSON with `output-info`, `output-select ARTIFACT POINTER --max-bytes N` (use
`/state` for raw `il-run` and `/result/state` for wrapped `request`),
`output-read ARTIFACT --offset N --length N`, or `output-export ARTIFACT
NEW_PRIVATE_PATH` outside Git. Retrieval never reruns the target.
`output_unavailable` means serialization or storage failed and no artifact
exists; it never implies rollback or permission to replay a side effect. Output
artifact IDs are distinct from `.fdb` debugger artifact IDs and live in
user-data `fdisbull/output-artifacts` (or `FDISBULL_OUTPUT_ARTIFACT_DIR`).

## Compare related programs

Use `export-types` / `import-types` and `export-signatures` / `import-signatures`
to transfer unbound structural layouts and closed function signatures after
verifying each target's own alignment, pointer width, endianness and ABI. Keep
byte signatures distinct from semantic correspondence (`link-snippets`), refuse
fixed segment transfers across models, and record accepted, rejected and
still-candidate links explicitly.
