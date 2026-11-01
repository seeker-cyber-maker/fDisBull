# 0.29.0 release candidate

Status: local release candidate on `release/0.29.0`. Not published, not tagged.
CI is not configured on the private GitLab copy; publication still requires the
Linux and native gates below.

This candidate is `release/0.28.0` merged with the current `integration` line.
It therefore carries the unpublished 0.28.0 candidate scope and adds the two
post-0.28 world-model examples.

## Scope carried from 0.28.0

- **Analysis capabilities:** a projectless `capabilities` operation reports 19
  native analysis, debugger, C and UDL/UIL capabilities, their dependency
  discovery and whether runtime validation actually ran. It executes no tool,
  target or app and keeps the embedded source revision unknown.
- **macOS ARM64 investigation:** exact Mach-O ARM64 slices, source-backed
  `code-backings`, bounded `ghidra-arm64` instruction/C diagnostics and a
  `macos-observe` LLDB launch. App-level UIL export remains unimplemented; the
  replication case study records the claim ceiling and prioritized gaps.
- **CI coordination:** bounded agent status reads and duplicate-feature-CI
  avoidance, with scripts/tests and workflow updates. These are local-validated;
  hosted CI is not yet configured.
- **DinoPark Coelophysis recovery:** purchase reconciliation, selected and
  picked catalogue qualification (including the native pen record 10), retained
  navigation, operation budgets and Z bridge changes backed by
  original-observation tests.
- **DOS/audio:** Miles AIL 2 driver libraries import as `ail` with named exports
  and a bounded descriptor candidate; DIGPAK/MIDPAK call descriptions and DOS
  audio-driver documentation are retained. AIL is static inspection; no runtime
  driver is installed.
- **Syndicate spatial Z scenes:** exact-coordinate ASCII agent maps and bound
  scene/session tooling.
- **Skill:** the investigation skill gains
  `references/binary-claim-verification.md` for settling stored-value, writer
  and behavior claims against a decoded original binary.

## New in 0.29.0

- **Civilization I world snapshot.** A privately held Civilization DOS 47501
  `CIVIL0.SVE` + `CIVIL0.MAP` pair decodes to an 80 x 50 world with 41 active
  cities, 172 active units, 230 special-resource tiles and 181 human-explored
  tiles. The example emits JSON, ASCII, offline HTML and SVG views. It is a
  read-only observation: no guest process, input, memory write, world-generator
  or AI reconstruction is claimed. The unresolved Russian city/leader character
  mapping and one stacked/stale unit-owner tile stay explicit.
- **Z world language and Zork I map.** A strict `(z-world ...)` parser, writer
  and validator lifts the MIT-licensed historical Zork I `ROOM`/`OBJECT` forms
  into a source-addressable graph. Census: 110 rooms, 140 objects and 352 exit
  clauses; 105 rooms are statically reachable, five river rooms remain a
  dynamic boundary and seven `PER` exits are unresolved without runtime
  observation. Z is not a Z-machine IR and does not execute.

## Compatibility

- New image selector value from 0.28.0: `ail` (inspect, import, analyze-module
  where supported). Existing PE/LE/NE/MZ/COM behavior is unchanged.
- New projectless operations from 0.28.0: `capabilities`, `ghidra-arm64`,
  `macos-observe`.
- 0.29.0 adds examples and documentation only; it introduces no project schema
  change. Existing projects remain readable.
- Original binaries, private object stores, ROMs, captures, save pairs and full
  screenshots remain outside Git.

## Qualification at this cut

- Focused world-model suite: 8 passed.
- Full macOS suite with `z3-solver` and the `managed` extras available:
  **2,596 passed, 127 skipped, 3 failed, 23 errors**. The three failures and 23
  errors reproduce unchanged on 0.28.0 and come from Linux ELF/GCC fixture
  builds and one case-sensitive media fixture on this macOS host. They are not
  release acceptance for those lanes.
- Distribution build: `fdisbull-0.29.0-py3-none-any.whl` and
  `fdisbull-0.29.0.tar.gz`; `check_dist.py` reports 196 and 708 tool-only
  entries respectively.
- Installed-wheel smoke: `fdisbull --version` reports `0.29.0`; `capabilities`
  loads from the wheel.
- 0.28.0's focused and full-suite results are historical evidence for its own
  cut; they do not qualify the merged 0.29.0 source.
- Candidate receipt and logs: [0.29.0 release evidence](evidence/0.29.0-release/README.md).

## Not included

- The KQ1/AGI natural-goat, troll-bridge, goat-branch, bridge-clip and
  mushroom-crossing stack. It remains stacked draft work with in-memory
  checkpoints only and no durable IL-scene saves.
- Reversible macOS sessions and display-bound native capture.
- The experimental full Miniplanets NES port (PR #56): it remains based on the
  0.27.0 baseline and needs an explicit rebase, private-ROM/toolchain
  qualification and its own full-suite pass.
- Hosted CI and a published GitLab tag. A fresh shared macOS installation is
  prepared locally only; it makes no publication claim.
- The CPUInfo replica comparison, which is separate app work rather than a core
  fDisBull release item.

## Publication gates

1. Linux CI (ordinary and required-native) on the final source SHA; add GitLab
   CI or run the existing GitHub workflows once access returns.
2. Re-run the full suite on Linux and record environment-only macOS failures
   separately.
3. Build the wheel and source ZIP with `check_dist`; verify packaged skills,
   capability catalog and native resource files.
4. Rebuild both native macOS backends and run installed-wheel acceptance.
5. Decide the tag (`v0.29.0`) only after the above pass on the same commit.
