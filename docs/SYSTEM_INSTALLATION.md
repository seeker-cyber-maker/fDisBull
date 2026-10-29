# fDisBull 0.22.0 — versioned shared Mac installation

The selector `/Users/Shared/fDisBull/current` points to
`/Users/Shared/fDisBull/releases/0.22.0-75bbd7e`, source commit
`75bbd7ee65118c0186844f73ef6c79245854eba0` and tag `v0.22.0`. Postflight
verified all three global core aliases and all three player aliases. Six fresh
player processes covered save and resume; the global DOS doctor passed with
native-state restoration. The complete active payload verification passed for 2,459 entries, and
`INSTALLATION.json` records `active_verified`.

Before activation, the installed candidate passed 672 tests with zero failures,
errors or skips. DOSBox, DOS-in-QEMU and Wine/QEMU doctors each passed
native-state restoration, and the standalone player passed a two-process
save/resume check. The installed Zork CLI passed a bounded mailbox autosave and
fresh-process resume using a separately selected existing Jericho 3.3.1 worker.
That check does not requalify whole-game behavior or DOS parity. These results
qualify the tested Mac and prefix, not portability to other macOS machines.
Interactive dot-mode remains unqualified.

The source includes native-unit spatial maps and physical, assisted and story
policies. Fair play locks physical mode for a session. Story guards are
source-qualified and narrowly scoped; map coverage and behavior can remain
unknown. The Z-machine harness requires a user-provided story and external worker
environment. Keep private checkpoints and projects outside the installation.

The public [0.22.0 release](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.22.0)
contains eight assets, all downloaded and matched against GitHub digests and
staged bytes. Package release notes and verification documents are fixed
source-finalization snapshots; the publication record distinguishes later
verification and activation from tagged package contents.

The previous 0.21 prefix remains preserved. The guarded
`/Users/Shared/fDisBull/current/share/rollback-to-0.21.py` helper reported
`rollback_ready` with 14 wrappers preserved. It checks preconditions by default
and requires `--apply` to change the selector; no rollback has been performed.
Existing projects, running sessions and user checkpoint directories are not
migrated. Global command wrappers were not changed by the selector update.

Release packages do not supply licensed games, user saves or project databases.
User state remains outside the managed prefix. The historical full Mac source
suite was not green: 1,429 passed, 104 skipped, 2 failed and 23 setup errors
involving Linux ELF fixtures on the Apple toolchain.

The shared commands are `fdisbull`, `fdisbull-player`, `fdisbull-python`,
`fdisbull-dosbox`, `fdisbull-qemu` and `fdisbull-runtime`. `RUNTIME.json` records
the DOSBox, DOS/QEMU, Wine/QEMU and boot-machine profiles, plus the optional
external story-worker identity. Managed Python package directories are read-only.
Run `fdisbull-python -I /Users/Shared/fDisBull/current/share/verify-system.py`
for the full payload check. The prefix keeps its tagged documentation snapshot
and a separate `share/docs/LOCAL-INSTALLATION.md` record.
