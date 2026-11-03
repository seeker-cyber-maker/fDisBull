# 0.31.0 release candidate evidence

Status: **local release candidate, not tagged or published**.

- Source branch: `release/0.31.0`
- Code commit: `518572040eda679933cddec7eb66b3dbe9ffc527`
- Code tree: `dba4fa1c5dde5eaf363d71b614b2ef9f3c409515`
- Candidate commit used to build artifacts: `bda8107cf9f6c275e7db894e67217012fb49ecf2`
- Candidate tree: `e6f79878671ee57bc5610f85159edb59193fbc0f`
- Base `main`: `f861d17ed4837f753e000f53cc777a7d906fde82`
- Package version: `0.31.0` (core, player, sdist and tool ZIP)

## Scope

This candidate carries the 0.30.0 release plus:

- lossless frame-timeline delta storage (MR !41);
- bounded typed-C to UIL frontend (MR !48);
- read-only Windows original-runtime preflight (MR !60);
- CHIP-8 instruction-space/corpus pilot (MR !61);
- UDC registry and fresh-agent swede examples (MRs !57, !58);
- cold-agent benchmark and post-0.30 README/skill refresh (MRs !59, !44).

The large indexed-UIL/Civilization `z-work` candidate, records-validation
follow-up, and the still-Draft consolidated UDL/UIL/UDC, console-skill,
delegation and deterministic-guidance MRs are excluded. No native Windows
debugger, Wine guest image, historical CHIP-8 emulator qualification or general
swede compiler is claimed.

## Qualification

| Check | Result |
| --- | --- |
| Full suite | 8,992 passed, 335 skipped, 2,316 subtests; 3 failures + 23 errors are the known macOS ELF/GCC/media baseline |
| Focused feature suites | 67 passed, 13 skipped |
| Frame timeline / typed-C targeted | 148 + 26 tests passed |
| `check_dist.py` | core wheel 564 entries; player 19; tool ZIP 1,820; sdist 1,842 |
| Installed-wheel smoke | `fdisbull 0.31.0`; methods `0.31.0`; capabilities runtime/distribution `0.31.0` |
| Hosted GitLab `test-and-package` | success, pipeline `3020223207` at `bda8107`; 8,958 passed, 402 skipped; skill gates and package checks passed |
| Native debugger jobs | manual, not run |

The ordinary hosted CI gate passed. Native backend rebuilds, shared-prefix
qualification and publication remain separate gates. The installed smoke used a
throwaway venv with `--system-site-packages`; no system prefix was activated.

## Artifacts

Artifacts are outside Git under `dist/` on the packaging worktree. Their exact
SHA-256 values are in `artifact-sha256.txt`; the checked identities are:

- `fdisbull-0.31.0-py3-none-any.whl`
- `fdisbull_player-0.31.0-py3-none-any.whl`
- `fdisbull-0.31.0-tool.zip`
- `fdisbull-0.31.0.tar.gz`

## Logs

- `full-suite.log`
- `targeted.log`
- `check-dist.log`
- `installed-smoke.log`
- `artifact-sha256.txt`
