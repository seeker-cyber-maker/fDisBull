# fDisBull 0.23.0 — shared Mac installation

The active selector `/Users/Shared/fDisBull/current` points to
`/Users/Shared/fDisBull/releases/0.23.0-ed89abc`, source
`ed89abca061964385b176537bc9fd275dd02afa5`, tag `v0.23.0`.
`INSTALLATION.json` records `active_verified` and all 2,464 managed entries
passed the postflight payload check.

The installed package passed 709 required-native tests with no failures or
skips. DOSBox, DOS-in-QEMU and Wine/QEMU doctors restored native state; both
runtime-image audits passed. Post-activation checked three global core aliases,
three player aliases with six fresh save/resume processes, and the global DOS
restore doctor. Z3 5.3.2 is present. The shipped UDC reconstructs original-backed
DOS bytes and qualifies only its declared small register-block profile.

The [public release](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.23.0)
contains eight assets, all downloaded and matched against staged bytes and
GitHub digests. See [the publication record](PUBLICATION-0.23.md) for exact
identities, source-companion scope and retained test failures.

The previous 0.22.0 prefix and all 14 wrappers remain intact. The guarded
`/Users/Shared/fDisBull/current/share/rollback-to-0.22.py` checks by default and
requires `--apply` to switch. Its preflight returned `rollback_ready`; no rollback
was applied. Existing projects and user checkpoint directories are not migrated.

Commands are `fdisbull`, `fdisbull-player`, `fdisbull-python`,
`fdisbull-dosbox`, `fdisbull-qemu` and `fdisbull-runtime`. `RUNTIME.json`
records the backend profiles. Managed Python package directories are read-only.
Run `fdisbull-python -I /Users/Shared/fDisBull/current/share/verify-system.py`
for the payload check. Keep game data, checkpoints and projects outside the
managed prefix.

Qualification covers this Mac and tested paths. Two initial DOSBox startup
aborts occurred in a long-path harness run; the outside-Git shorter-path rerun
passed, but their cause remains unresolved. Interactive dot-mode is unqualified.
General `il-run` output amplification also remains; see the measured known limit
in the publication record. The local `agent-skill --index` follow-up is not
installed; 0.23.0 supports selective `agent-skill --reference FILE` retrieval.
