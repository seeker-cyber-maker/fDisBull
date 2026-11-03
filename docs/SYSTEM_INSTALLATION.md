# fDisBull 0.31.0 — local shared Mac installation

The active selector `/Users/Shared/fDisBull/current` points to
`/Users/Shared/fDisBull/releases/0.31.0-a12441b`, source
`a12441b3a6ba9d6816721d59a3d94727bea1eb3b`. This is a local candidate built from
the `release/0.31.0` branch; `INSTALLATION.json` records `active_verified`. The
published `v0.31.0` tag remains at `10d0106`; these post-tag packaging and CI
repairs are not inside it.

The local prefix contains the shipped Swift capture helper
`fdisbull/data/FdisbullMacCapture.swift` in both the core wheel and the tool
source ZIP. The installed package passed **97 tests** with no failures, errors or
skips (63 required-native debugger/layer/keyboard plus 34 macOS capture tests).
DOSBox, DOS-in-QEMU and Wine/QEMU doctors passed native-state restoration. The
installed player restored `hall`/`key` across two fresh processes and kept
private checkpoint permissions. `scripts/check_local_install.py --version
0.31.0 --commit a12441b3a6ba9d6816721d59a3d94727bea1eb3b` passed.

The previous 0.30.0 prefix remains intact. Backup:
`/Users/Shared/fDisBull/backups/0.30.0-2866c41-to-0.31.0-a12441b`; the guarded
`current/share/rollback-to-0.30.0.py` reports the plan by default and requires
`--apply`. Existing projects and user checkpoints were not migrated. The DOS
QEMU runtime was regenerated from the trusted 0.30 runtime base to match this
package's broker/RPC resources; the Wine runtime hashes already matched.

Commands are `fdisbull`, `fdisbull-player`, `fdisbull-python`,
`fdisbull-dosbox`, `fdisbull-qemu` and `fdisbull-runtime`. `RUNTIME.json`
records backend paths. Verify the complete payload with:

```bash
fdisbull-python -B -I /Users/Shared/fDisBull/current/share/verify-system.py verify
```

After each release, confirm the local installation from the release source tree:

```bash
python scripts/check_local_install.py --version 0.31.0 \
  --commit a12441b3a6ba9d6816721d59a3d94727bea1eb3b
```

The check requires `INSTALLATION.json` to be `active_verified`, the selector to
resolve under `releases/`, the installed version and source commit to match the
release, and the complete payload verifier to report `active_default: true`.

Discover both skills with `fdisbull agent-skill --list`; retrieve only the
needed reference. Keep games, story inputs, saved native states and project
databases outside the managed prefix. The macOS backend was not rebuilt for
0.29.0; it was requalified from the 0.28.0 prefix. Hosted Linux CI, the hosted
native matrix, a Git tag and publication remain pending. These checks qualify
this host and prefix, not arbitrary macOS hosts or complete game parity.

Historical 0.25.0 publication details remain in
[PUBLICATION-0.25.md](PUBLICATION-0.25.md) and [RELEASE_STATUS.md](RELEASE_STATUS.md).
