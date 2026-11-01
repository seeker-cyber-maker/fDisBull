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

## Linux offline dependencies

`scripts/offline_dependencies.py` builds a Linux x86-64 / Python 3.13 wheel
bundle for the core runtime plus the `proof` extra. See the
[offline dependency guide](OFFLINE_DEPENDENCIES.md) for build, diff and reuse
commands. It contains third-party wheels only: Capstone 5.0.9, iced-x86 1.21.0,
LIEF 1.0.0, Pillow 12.3.0 and Z3 5.3.2.0. The 0.29.0 bundle has fingerprint
`ea2a9ca41c8a06ffa2a0c3439b971c7952f1c5c0cd54df65159e732da6b588eb` and
SHA-256 `e45801015b0d8e0dc7a6396997e01bd2b5c7dc01bfec0cf18f692fa83ac48ce6`.

A fresh no-index install from the bundle passed the decoder imports and Z3
equivalence/counterexample check. Re-checking the same constraints reports
`status: reuse` and copies the archive byte-for-byte. A later release should use
`--previous` and `--require-reuse`; a changed constraint produces an explicit
`rebuild` diff instead of silently downloading a new compatible version. The
same archive was merged through `build_offline_kit.py --dependency-bundle` in a
kit smoke build, producing the seven-wheel set without duplication.

The full 0.29.0 native kit was rebuilt from upstream DOSBox-X baseline
`029bd65c` plus the current 33-file layers overlay. The heavy-debug backend has
SHA-256 `2db1c812d8af64bb5c71f5a1cc1466511ac6212a919cd3e70b82ef1b8c7b3471`;
the source companion has SHA-256
`f9560466383cbb4a8e1096434889d7009ae9fcca4b0d2511c25f4d61ea95d118`; the kit
has SHA-256
`b6f43aa6933c8e4e12b643f1dead105d96e5ac0a0bb6c9671032c31fffd97a3f`. Its
fresh Python 3.13.5 no-index install and installed-kit acceptance passed:
Z3 equivalence/counterexample, BIOS keyboard, memory readback, screenshot,
native restore, post-restore input, player resume and project restart. The
full native CI matrix and hosted runs remain separate gates.

## Qualification at this cut

- Focused world-model suite: 8 passed.
- Full macOS suite with `z3-solver` and the `managed` extras available:
  **2,596 passed, 127 skipped, 3 failed, 23 errors**. The three failures and 23
  errors reproduce unchanged on 0.28.0 and come from Linux ELF/GCC fixture
  builds and one case-sensitive media fixture on this macOS host. They are not
  release acceptance for those lanes.
- Full suite in a local Apple Linux container (`linux/amd64` under Rosetta,
  Debian 13, Python 3.13.18, Node 20.19.2, GCC 14.2.0):
  **2,600 passed, 156 skipped, 0 failed, 0 errors** in 251.48s. This is local
  container evidence, not hosted Linux CI.
- Distribution build: `fdisbull-0.29.0-py3-none-any.whl` and
  `fdisbull-0.29.0.tar.gz`; `check_dist.py` reports 196 and 712 tool-only
  entries respectively.
- Offline dependency bundle: five wheels, 49 MB, fingerprint and SHA-256 above;
  fresh venv install and byte-identical reuse passed.
- Full native offline kit: rebuilt backend and source companion, seven wheels,
  SHA-256 above; installed-kit acceptance passed on Python 3.13.5.
- Focused native backend suite on the rebuilt kit binary: **60 passed, 0
  failed** in 45.05s.
- Fresh shared macOS prefix: Python 3.13.18, core/player 0.29.0, genuine
  decoding, managed-analysis and Z3 dependencies; installed gate **818 passed,
  0 failed, 0 errors, 0 skipped**. The 3,221-entry payload verified before and
  after activation, the selector points at
  `releases/0.29.0-c03dc4f`, and all three installed doctors restored native
  state. The player passed a two-process save/resume smoke.
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
- Hosted CI and a published GitLab tag. The shared macOS installation is active
  locally; it makes no publication claim.
- The full hosted native CI matrix. The local backend rebuild and installed-kit
  acceptance passed, but the workflow matrix has not been rerun on hosted
  runners.
- The CPUInfo replica comparison, which is separate app work rather than a core
  fDisBull release item.

## Publication gates

1. Hosted Linux CI (ordinary and required-native) on the final source SHA; add
   GitLab CI or run the existing GitHub workflows once access returns. The
   local Apple container result above does not replace hosted CI.
2. Record the local Linux container result and re-run the full suite in hosted
   Linux CI; keep the environment-only macOS failures separate.
3. Build the wheel and source ZIP with `check_dist`; verify packaged skills,
   capability catalog and native resource files.
4. Reuse the offline dependency bundle and rerun the full native offline kit
   build and installed acceptance in hosted native CI; the local build passed.
5. Rebuild both native macOS backends and repeat installed-wheel acceptance;
   the active local prefix reuses the 0.28.0 backend by an APFS clone.
6. Decide the tag (`v0.29.0`) only after the above pass on the same commit.
