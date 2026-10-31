# 0.28.0 release candidate

Status: local release candidate on `release/0.28.0`. Not published, not tagged.
CI is not configured on the private GitLab copy; publication still requires the
Linux and native gates below.

## Scope

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
- **DinoPark Coelophysis recovery:** purchase reconciliation, selected catalogue
  motion, retained navigation, operation budgets and Z bridge changes backed by
  original-observation tests.
- **DOS/audio:** Miles AIL 2 driver libraries import as `ail` with named exports
  and a bounded descriptor candidate; DIGPAK/MIDPAK call descriptions and DOS
  audio-driver documentation are retained. AIL is static inspection; no runtime
  driver is installed.
- **Skill:** the investigation skill gains
  `references/binary-claim-verification.md` for settling stored-value, writer
  and behavior claims against a decoded original binary.

## Compatibility

- New image selector value: `ail` (inspect, import, analyze-module where
  supported). Existing PE/LE/NE/MZ/COM behavior is unchanged.
- New projectless operations: `capabilities`, `ghidra-arm64`, `macos-observe`.
- No project schema change is introduced by this candidate; existing projects
  remain readable.
- Original binaries, private object stores, ROMs, captures and full screenshots
  remain outside Git.

## Qualification at this cut

- Merged branches: CI coordination, PR #83 macOS ARM64, app-replication
  capabilities draft, and the Coelophysis recovery update.
- Focused suites: 104 passed / 1 skipped for CI + macOS ARM64; 143 passed / 1
  skipped for capabilities + distribution; 192 passed / 5 skipped for the
  Coelophysis, AIL, scene and distribution set.
- Full macOS suite with the worktree player on `PYTHONPATH=src:player`:
  **2581 passed, 127 skipped, 3 failed, 23 errors**. The three failures and 23
  errors reproduce unchanged on `integration` and come from Linux ELF/GCC
  fixture builds and one case-sensitive media fixture on this macOS host. They
  are not release acceptance for those lanes.
- `fdisbull --version` and `fdisbull capabilities` smoke tests pass.

## Not included

- The experimental full Miniplanets NES port (`pr-local/56-...`): 154 files and
  ~37k insertions, still based on the 0.27.0 baseline, with distribution and CLI
  conflicts. It needs an explicit rebase, private-ROM/toolchain qualification
  and its own full-suite pass; schedule it as a separate milestone (0.29 or an
  opt-in 0.28 feature branch).
- Hosted CI, a published GitLab tag, and a fresh shared macOS installation.

## Publication gates

1. Linux CI (ordinary and required-native) on the final source SHA; add GitLab
   CI or run the existing GitHub workflows once access returns.
2. Re-run the full suite on Linux and record the environment-only macOS
   failures separately.
3. Build the wheel and source ZIP with `check_dist`; verify packaged skills,
   capability catalog and native resource files.
4. Rebuild both native macOS backends and run installed-wheel acceptance.
5. Decide the tag (`v0.28.0`) only after the above pass on the same commit.
