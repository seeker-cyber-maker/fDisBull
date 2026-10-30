# fDisBull 0.24.0 — shared Mac installation

The active selector `/Users/Shared/fDisBull/current` points to
`/Users/Shared/fDisBull/releases/0.24.0-031b53e`, source
`031b53eb953bfdc1d0e23c0ed49441031bad6e06`, tag `v0.24.0`.
`INSTALLATION.json` records `active_verified`; all 2,968 managed entries passed
postflight. The fresh environment runs Python 3.13.17 on ARM64 and includes the
published core/player, real decoding libraries, managed-analysis dependencies
and Z3 5.3.2.

The selected installed-package gate passed **700 tests with no failures, errors
or skips**, with one source-only doctor CLI test deliberately deselected. Five
source build/distribution suites and the full Mac source suite are outside this
installed selection. The installed investigation-skill gate and blank backend
command check passed. Native ZIP CRC, synthetic UDC and QEMU boot/watchpoint
checks are included in the selected suite.

DOSBox, DOS-in-QEMU and Wine/QEMU doctors restored native state and checked
execution overlays, breakpoints/watchpoints, memory, screenshots, clicks, traces
and stored-evidence reopening using authored targets. Both freshly prepared
runtime images passed streamed path and resource-hash audits. Their preparation
removed 242 stale build/cache/profile entries while preserving the original 0.23
images. Mac binaries retain their original build provenance and were freshly
tested with 0.24; no Mac rebuild is claimed. The Linux ELF and SDL2_net match the
published kit. Other private Linux libraries retain their prior recorded origin.

Post-activation checked three global core aliases, three player aliases through
six fresh save/resume processes, the runtime profile, the global DOS restore
doctor and the complete payload. The public release has eight assets, all
redownloaded without authentication and matched to staged bytes and GitHub
digests. See [the publication record](PUBLICATION-0.24.md) for CI, hashes,
source-companion scope and retained setup failures.

The previous 0.23 prefix and all 14 wrappers remain intact. The guarded
`/Users/Shared/fDisBull/current/share/rollback-to-0.23.py` checks by default and
requires `--apply` to switch. Its preflight returned `rollback_ready`; no rollback
was applied. Existing projects and user checkpoint directories are not migrated.

Commands are `fdisbull`, `fdisbull-player`, `fdisbull-python`,
`fdisbull-dosbox`, `fdisbull-qemu` and `fdisbull-runtime`. `RUNTIME.json` records
backend profiles and documentation paths. Managed Python package directories are
read-only. Check the managed payload with:

```bash
fdisbull-python -B -I /Users/Shared/fDisBull/current/share/verify-system.py verify
```

Use `fdisbull agent-skill --index` for the compact workflow guide, then retrieve
a reference with `--reference FILE`. Keep games, story inputs, native checkpoints
and project databases outside the managed prefix.

Qualification covers this Mac and the tested paths. The initial installed test
attempt had a missing ZIP source fixture, unconfigured native QEMU checks and a
missing authored UDC helper; correcting that harness yielded the 700-test pass.
Earlier long-path DOSBox startup aborts remain unresolved. Interactive dot-mode
and the full Mac source suite are outside this qualification. The packaged
technical documents retain their tagged source-cut context; the local
`LOCAL-INSTALLATION.md` and installation metadata describe later delivery.
