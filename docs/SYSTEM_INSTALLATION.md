# fDisBull 0.25.0 — shared Mac installation

The active selector `/Users/Shared/fDisBull/current` points to `/Users/Shared/fDisBull/releases/0.25.0-70eb4e3`, source `70eb4e38bf4bf8d47e52e38b8fab6a6cd718f15e`, tag `v0.25.0`. `INSTALLATION.json` records `active_verified`; all 3,040 managed entries passed postflight. Core/player 0.25.0 run in Python 3.13.17 ARM64 with genuine decoding and managed-analysis dependencies and Z3 5.3.2.

The selected installed-package gate passed **1,107 tests with no failures, errors or skips**. Two checks were explicitly deselected because they require a source-only no-decoder launch or Linux display behavior. Source/build archive suites and the full Mac source suite are outside this selection. Both installed skills, blank-command rejection and native ZIP/UDC/boot checks passed. The [publication record](PUBLICATION-0.25.md) retains the initial fixture failures and corrected rerun.

Direct DOSBox, DOS-in-QEMU and Wine/QEMU doctors passed native restore, layers, breakpoints/watchpoints, memory, screenshots, clicks and traces on authored targets. Both new runtime images passed streamed exclusion/resource audits. Mac executables retain their original build provenance and were freshly requalified, not rebuilt. The Linux ELF matches the published kit. Historical backend receipts are labelled separately.

Global core/player aliases, automatic turn save/resume through six processes, a further global DOS doctor and the runtime profile passed. The global source-linked Zork CLI also passed first/repeated mailbox result and checkpoint comparisons against the prior qualified path. No complete native-game replay or arbitrary-host portability is claimed.

The previous 0.24 prefix and all 14 wrappers remain intact. The guarded `current/share/rollback-to-0.24.py` checks by default and requires `--apply` to switch; preflight returned `rollback_ready`. Existing projects and user checkpoints were not migrated.

Commands are `fdisbull`, `fdisbull-player`, `fdisbull-python`, `fdisbull-dosbox`, `fdisbull-qemu` and `fdisbull-runtime`. `RUNTIME.json` records backend paths. Managed package files are read-only. Verify the sealed payload with:

```bash
fdisbull-python -B -I /Users/Shared/fDisBull/current/share/verify-system.py verify
```

Discover both skills with `fdisbull agent-skill --list`; retrieve only the needed reference. Optional GOG extraction uses the separately available genuine host `innoextract`; its version was checked, but no original installer extraction was qualified in this publication turn. Keep games, story inputs, saved native states and project databases outside the managed prefix. Earlier long-path DOSBox startup aborts remain unresolved. Interactive dot-mode and the full Mac source suite remain outside this qualification.
