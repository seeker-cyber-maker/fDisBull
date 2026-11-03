# 0.31.1 release

Status: **release candidate** built from `release/0.31.1`, based on the
published `v0.31.0` tag (`10d0106`) plus post-tag repair commits.

## Scope

0.31.1 is a patch release. It carries no new analysis or runtime features. It
packages the fixes that were validated after `v0.31.0`:

- Native CI builds DOSBox-X with `--enable-dosbox_agent`, so `--agent-config`
  is recognized and the backend does not fall back to X11.
- Keyboard acceptance tolerates the backend's `frame_edge_capacity` and
  `frame_keys` fields while still checking idle/pending/owned state.
- The BIOS-callback checkpoint disarms, settles a pending VGA mode, re-arms the
  same callback, and only then saves.
- The tool source ZIP includes
  `src/fdisbull/data/FdisbullMacCapture.swift`; `check_dist.py` requires the
  macOS Swift capture helper in both the core wheel and source ZIP.
- Regression tests cover the tool-ZIP allowlist and missing-helper rejection.

## Compatibility

- Core and player package versions are `0.31.1`.
- No project, save, checkpoint or database format changes.
- The published `v0.31.0` tag and its assets remain unchanged.

## Qualification

See [0.31.1 evidence](evidence/0.31.1-release/README.md) for exact counts,
pipeline IDs, artifact hashes and the local prefix receipt.

## Explicitly not included

- No new UIL, UDC, debugger, console, Windows-runtime or game-analysis feature.
- No migration of existing projects or user checkpoints.
- No new native backend rebuild beyond the DOS QEMU runtime resource refresh
  needed for the 0.31.x package contract.
