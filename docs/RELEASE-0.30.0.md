# 0.30.0 release

Status: published as GitLab tag `v0.30.0` and local-hub release candidate on
2026-11-02. This release merges the unified `integration` line into `main`,
unifying the post-GitHub migration consolidation with the full slate of
common indexed UIL contracts, console synthesis, AGI/KQ1 native alignment,
debugger rewind history, standing probes, and verified trial-safe GitLab CI.

## Scope carried from 0.29.0

- **Civilization I world snapshot:** DOS 47501 `CIVIL0.SVE` + `CIVIL0.MAP`
  decoding to an 80 x 50 world with 41 cities, 172 units, 230 special resource
  tiles, and offline JSON/ASCII/HTML/SVG views.
- **Z world language and Zork I map:** Strict `(z-world ...)` parser, writer,
  and validator lifting 110 rooms, 140 objects, and 352 exits into a
  source-addressable graph.
- **Packaging and offline dependencies:** Reusable Linux x86-64 / Python 3.13
  dependency bundle (`ea2a9ca4...`), 33-file DOSBox-X heavy-debug backend
  companion, and post-publication verification helpers.

## New in 0.30.0

- **Common indexed UIL contract (MR !24):** Formalizes the four-document UIL
  representation (`fdisbull-common-uil-1`, `fdisbull-uil-presentation-1`,
  `fdisbull-uil-orchestration-1`, and `fdisbull-uil-catalog-1`) with indexed
  variable/constant tables, acyclic call graphs, eager `select` evaluation,
  copy-in/copy-out array ownership, and selectable semantic realization catalogs.
  Connects common UIL to native desktop windows, frame events, and input
  plumbing (`docs/COMMON_UIL_CONTRACT.md`, `docs/COMMON_UIL_DESKTOP.md`).
- **Console intake & synthesis (PR #56):** Replayable Genesis UIL, full
  Miniplanets NES port with multicart packaging, Shadowrun SNES/Genesis
  dialogue and playable combat projections, Capstone 5.0.9-backed SH2/65816
  disassembly, and native macOS ARM64 compilation (`docs/MINIPLANETS_FULL_GAME.md`,
  `docs/SHADOWRUN_SNES_MACOS.md`, `src/fdisbull/snes_decode.py`).
- **AGI & KQ1 native alignment:** Completes the King's Quest I royal greeting
  intent recovery, natural goat scene, bridge clip, boundary exceptions, and
  shared native controller alignment (`docs/AGI_BOUNDARY_EXCEPTIONS.md`,
  `docs/AGI_NATURAL_GOAT.md`, `docs/AGI_TROLL_BRIDGE.md`,
  `docs/VERIFICATION-KQ1-BOW-2026-10-30.md`).
- **Debugger rewind & frame input timeline:** Bounded native debugger rewind
  history, Wine/x86 CPU & RAM delta undo/redo, and frame-accurate input
  timeline scrubbing (`docs/DEBUGGER_REWIND.md`, `docs/FRAME_INPUT_TIMELINE.md`,
  `docs/CPU_RAM_DELTAS.md`).
- **Standing probes RFC & DinoPark full-loop recovery:** Standing probes for
  month rollover and visitor gates, plus DinoPark land, fence, employment,
  visitor, and park return source recovery with native Borland C receipts
  (`docs/STANDING_PROBES_RFC.md`, `docs/DINOPARK_STATIC_ANALYSIS_FRICTION.md`,
  `docs/VERIFICATION-DINOPARK-VISITORS-2026-11-01.md`).
- **Multi-target memory UDC shells & Cortex-M Thumb:** Segmented Win16,
  Win32, native Win64/Linux, and macOS ARM64 memory shells with selectable RNG
  Snake, plus Cortex-M Thumb decoder (`docs/UDC_MEMORY_WIN16.md`,
  `docs/UDC_MEMORY_MACOS.md`, `docs/CORTEX_M.md`).
- **Trial-safe GitLab CI & dual mirror parity:** Validated `when: always`
  workflow rules in `.gitlab-ci.yml`, automated container toolchain build
  dependencies (`git`, `build-essential`, `nodejs`, `libx11-dev`), skill receipt
  isolation in `$RUNNER_TEMP`, and two-way mirror synchronization tooling
  (`scripts/sync_mirrors.py`, `scripts/ci_status.py`).

## Compatibility

- Project format and capabilities remain backward-compatible; existing
  `.fdb` databases and 0.29.0 analysis snapshots remain readable.
- `scripts/check_dist.py` verifies both core wheel, player wheel, and source
  ZIP packages, enforcing all required knowledge and terminal JSON assets.
- Original game ROMs, binaries, private databases, and saves remain outside Git.

## Qualification

- Hosted GitLab CI `test-and-package` passed on the `integration` baseline
  (Pipeline `#3016197597` at commit `d39390ef`, completing 3 jobs across 2
  stages).
- Local verification on macOS ARM64 passes all distribution checks, package
  skill gates, and mirror synchronization checks.
