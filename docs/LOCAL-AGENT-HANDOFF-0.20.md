# Local agent handoff: 0.20 candidate

The working branch is `codex/v020-interpreter-analysis` (PR 12). Dot-mode is
already part of the branch. It opens a watch-only window for the agent-owned
session; guest keyboard and mouse input still comes from the agent. Use:

```sh
fdisbull debug PROJECT.fdb --executable /path/to/patched/dosbox-x --game-dir /path/to/game --dot-mode
```

`--window` is an alias. A compatible backend built from the current patch and
an accessible display are required. See [dot-mode requirements](DOSBOX_DEBUGGER.md#dot-mode)
and the pinned build and manifest checks in `.github/workflows/native-debugger.yml`.
The complete stable and layers patches are in `experimental/dosbox-x/`; select
the matching patch and verify its manifest. Historical Linux synthetic window
and native results are in [spectator verification](VERIFICATION-SPECTATOR-CLOUD.md).
macOS still needs native qualification. No private game assets are included.

The current cloud task has Python test dependencies installed and passed 29
processor, AGI and proof tests. Its native build is blocked: the configured
Debian package indexes returned proxy HTTP 403 and system APT lacked permissions.
These task-local results do not establish a working native backend on a new host.

For an existing local checkout, inspect `git status` and fetch the branch first.
Preserve the owner's changes by committing or stashing them as appropriate
before switching; do not reset or overwrite them. Inspect the fetched branch
and its dependencies before building. PR 13 and PR 14 contain separate design
proposals; they are not implemented runtime behavior or automatically mergeable.
Their heads observed during handoff were `351c6f3c4af6c92100a605cdbeb88b1b524ed94f`
and `128278b92be2c5b70bba1f2abea8479dda1a28b3` respectively; check their current
status before acting on them.
