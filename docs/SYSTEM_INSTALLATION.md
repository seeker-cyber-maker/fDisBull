# fDisBull 0.29.0 — local shared Mac installation

The active selector `/Users/Shared/fDisBull/current` points to
`/Users/Shared/fDisBull/releases/0.29.0-c03dc4f`, source
`c03dc4f9d4b5b9d0b374f6423e21962bfb0b07c9`. This is a local candidate:
`INSTALLATION.json` records `active_verified`, but no tag or publication exists.
Core and player 0.29.0 run in Python 3.13.18 ARM64 with genuine decoding,
managed-analysis and Z3 dependencies. The installed payload has 3,221 entries
and its backend was inherited from the 0.28.0 prefix by an APFS clone.

The installed-package gate passed **818 tests with no failures, errors or
skips**. DOSBox, DOS-in-QEMU and Wine/QEMU doctors passed native-state
restoration on authored targets. The installed player restored `hall`/`key`
state across two fresh processes and kept private checkpoint permissions.
Global core/player aliases and the global DOSBox doctor passed after activation.

The previous 0.28.0 prefix remains intact. Its backup is
`/Users/Shared/fDisBull/backups/0.28.0-d06bffb-to-0.29.0-c03dc4f`; the guarded
`current/share/rollback-to-0.28.0.py` reports the rollback plan by default and
requires `--apply` to switch. Preflight reported `ready`; no rollback was
applied. Existing projects and user checkpoints were not migrated.

Commands are `fdisbull`, `fdisbull-player`, `fdisbull-python`,
`fdisbull-dosbox`, `fdisbull-qemu` and `fdisbull-runtime`. `RUNTIME.json`
records backend paths. Verify the complete payload with:

```bash
fdisbull-python -B -I /Users/Shared/fDisBull/current/share/verify-system.py verify
```

Discover both skills with `fdisbull agent-skill --list`; retrieve only the
needed reference. Keep games, story inputs, saved native states and project
databases outside the managed prefix. The macOS backend was not rebuilt for
0.29.0; it was requalified from the 0.28.0 prefix. Hosted Linux CI, the hosted
native matrix, a Git tag and publication remain pending. These checks qualify
this host and prefix, not arbitrary macOS hosts or complete game parity.

Historical 0.25.0 publication details remain in
[PUBLICATION-0.25.md](PUBLICATION-0.25.md) and [RELEASE_STATUS.md](RELEASE_STATUS.md).
