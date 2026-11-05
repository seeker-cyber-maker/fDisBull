# fDisBull 0.33.0rc1 local candidate evidence

[intake.json](intake.json) records the source lineage and selected revisions.
This packet covers a **local macOS release-candidate cut**, not publication or
hosted qualification.

The candidate starts from the unpublished 0.32.0 candidate and merges the
selected 0.32 PR integration. It carries the 0.32.0 feature line and adds the
Boat CI handoff, built-in GOG Inno reader, Westwood media modules, experimental
ScummVM Kyra/AGI pilots and reviewed investigation-skill guidance.

No tag, GitLab release, package upload, shared installation or system change is
made here. Hosted Linux ordinary/native CI, installed-wheel PE/DOS/boot
acceptance and fresh-prefix installation remain separate gates. See
[the release notes](../../RELEASE-0.33.0.md#qualification-and-publication).

## Local macOS verification (2026-11-04)

Environment: macOS arm64, Python 3.13, optional `z3-solver==5.3.2.0`,
`dnfile==0.18.0` and `dncil==1.0.2` supplied from temporary targets. The host
site-packages contains a regular `tests` package that shadows the checkout's
test modules; the full-suite run used a temporary `tests` package shim pointing
at this worktree. That shim is an environment workaround, not repository code.

- Full suite: `10002 passed, 15 failed, 386 skipped, 23 errors, 2316 subtests passed`
  in 280.58 seconds.
- Base comparison: the same 15 failures reproduce on the 0.32 candidate
  `c80bff0`; they are inherited macOS Mach-O/GCC and packaged
  presentation/PSG fixture limits, not 0.33 regressions.
- Focused module set: `175 passed, 4 skipped`.
- Focused Boat/chat CI set: `190 passed`.
- Distribution test module: `916 passed`.
- `compileall` passed for `src/fdisbull`, `scripts` and `examples`.

The full-suite, base-failure and `check_dist` logs are retained in this packet.
The 23 errors are the inherited Linux ELF/GCC toolchain cases. No failing test
was edited or skipped for this candidate.

## Build and install

Built with `uv build` and `scripts/build_release.py`:

| Artifact | Entries | Check |
| --- | --- | --- |
| core wheel | 589 | `check_dist.py` OK |
| core sdist | 2020 | `check_dist.py` OK |
| player wheel | 19 | `check_dist.py` OK |
| tool ZIP | 2002 | `check_dist.py` OK |
| player sdist | — | built, auxiliary |

`check_package_payloads.py` compared the four checked artifacts against the
tracked source and passed. The isolated wheel smoke reported
`fdisbull 0.33.0rc1`, capabilities `ok=true` with 30 entries, and the standalone
player help. Artifact SHA-256 values are in `artifact-sha256.txt`; bytes remain
outside Git.
