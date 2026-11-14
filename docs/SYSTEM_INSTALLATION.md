# System installation

## Current observation (2026-11-14)

Both `/Users/tiga/.local/bin/fdisbull` and `/usr/local/bin/fdisbull` route
through `/Users/Shared/fDisBull/current`. The selector currently points to
`releases/0.34.1-3aaac41`; its receipt records version `0.34.1`, source
`3aaac41b1f73220568fc07b9d53f5ccd4307a242` and status `local_candidate`.
This differs from immutable tag `v0.34.1` at
`011f1b8cb281edda208026aee9cdb238b800b2d7`. A version string alone does not
establish installed release identity. `check_local_install.py` correctly requires
`active_verified`; this current candidate does not meet that gate.

The intended next release is 0.35.0; source integration and exact-package install
acceptance remain open. Follow the [release process](RELEASE_PROCESS.md) and
[current release status](RELEASE_STATUS.md). No installation is performed by
updating these records.

## Historical: fDisBull 0.31.1 local shared Mac installation

The active selector `/Users/Shared/fDisBull/current` points to
`/Users/Shared/fDisBull/releases/0.31.1-27b388d`, source
`27b388d38cc14f04842a81b8ec1a113460900f53`. This is the 0.31.1 patch release
installed from CI-verified artifacts; `INSTALLATION.json` records
`active_verified`.

The local prefix contains the shipped Swift capture helper
`fdisbull/data/FdisbullMacCapture.swift` in both the core wheel and the tool
source ZIP. The installed package passed **97 tests** with no failures, errors or
skips (63 required-native debugger/layer/keyboard plus 34 macOS capture tests).
DOSBox, DOS-in-QEMU and Wine/QEMU doctors passed native-state restoration. The
installed player restored `hall`/`key` across two fresh processes and kept
private checkpoint permissions. `scripts/check_local_install.py --version
0.31.1 --commit 27b388d38cc14f04842a81b8ec1a113460900f53` passed.

The previous 0.31.0 prefix remains intact. Backup:
`/Users/Shared/fDisBull/backups/0.31.0-a12441b-to-0.31.1-27b388d`; the guarded
`current/share/rollback-to-0.31.0.py` reports the plan by default and requires
`--apply`. Existing projects and user checkpoints were not migrated.

Commands are `fdisbull`, `fdisbull-player`, `fdisbull-python`,
`fdisbull-dosbox`, `fdisbull-qemu` and `fdisbull-runtime`. `RUNTIME.json`
records backend paths. Verify the complete payload with:

```bash
fdisbull-python -B -I /Users/Shared/fDisBull/current/share/verify-system.py verify
```

After each release, confirm the local installation from the release source tree:

```bash
python scripts/check_local_install.py --version 0.31.1 \
  --commit 27b388d38cc14f04842a81b8ec1a113460900f53
```

The check requires `INSTALLATION.json` to be `active_verified`, the selector to
resolve under `releases/`, the installed version and source commit to match the
release, and the complete payload verifier to report `active_default: true`.

Discover both skills with `fdisbull agent-skill --list`; retrieve only the
needed reference. Keep games, story inputs, saved native states and project
databases outside the managed prefix. These checks qualify this host and
prefix, not arbitrary macOS hosts or complete game parity.

Historical 0.25.0 publication details remain in
[PUBLICATION-0.25.md](PUBLICATION-0.25.md) and [RELEASE_STATUS.md](RELEASE_STATUS.md).
