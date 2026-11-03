# 0.31.0 release evidence

Status: **published** as `v0.31.0`; shared prefix not activated.

- Source branch: `release/0.31.0`
- Code commit: `518572040eda679933cddec7eb66b3dbe9ffc527`
- Candidate commit: `bda8107cf9f6c275e7db894e67217012fb49ecf2`
- Final source / tag commit: `10d01062092a47bdc984ee59cd817b8ab57b6f1b`
- Final source tree: `9956d54a16ad49c80bacf8cef58af776cabd706f`
- Annotated tag object: `5f061f700a71021db57abf1a30da1fcaf1f2ee61`
- GitLab Release: <https://gitlab.com/brewster-jennings-group/fdisbull/-/releases/v0.31.0>
- Base `main`: `f861d17ed4837f753e000f53cc777a7d906fde82`
- Package version: `0.31.0`

## Scope

This release carries the 0.30.0 release plus:

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
| `check_dist.py` | core wheel 564 entries; player 19; tool ZIP 1,819; sdist 1,841 |
| Installed-wheel smoke | `fdisbull 0.31.0`; methods `0.31.0`; capabilities runtime/distribution `0.31.0` |
| Hosted GitLab `test-and-package` | success, pipeline `3022313149` at `10d0106`; 8,958 passed, 402 skipped |
| Tag pipeline `3022469643` | success on `v0.31.0`; 8,958 passed, 402 skipped |
| macOS native stable | 86 passed |
| macOS native layers | 148 passed |
| Linux native CI jobs | compiled, then failed at emulator startup in the SDL2/headless environment; not claimed |

The installed smoke used a throwaway venv; no system prefix was activated.

## Artifacts

Published as generic package `fdisbull-tool-packages` version
`0.31.0-20261103` (package ID `75116571`). The uploaded files were downloaded
again and all SHA-256 values matched.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `fdisbull-0.31.0-py3-none-any.whl` | 1,895,363 | `a676c98e2d9c5c24f901d66ea03742d7e1f92351eb25c92530db861c5a1bf025` |
| `fdisbull_player-0.31.0-py3-none-any.whl` | 86,673 | `d80e27589174ca119b33bf7ca4d3f08f7cc5f930f5b934362028472d6205d8fc` |
| `fdisbull-0.31.0-tool.zip` | 6,376,596 | `0f7371880eca1a462182fc90bcc181d80951c2db505e3573256df383f121dada` |
| `fdisbull-0.31.0.tar.gz` | 5,258,070 | `e2f93e875cb3ed624525e10f7669810ee17da06de398f3f114cc1c63787ddb9a` |

`SHA256SUMS` and `BUILD.json` are published alongside the artifacts. The
evidence packet itself is omitted from those packages so the external artifact
hashes remain authoritative rather than self-referential.

## Logs

- `full-suite.log`
- `targeted.log`
- `check-dist.log`
- `installed-smoke.log`
- `artifact-sha256.txt`
- `native-macos-stable.log`
- `native-macos-layers.log`
- `tag-ci.log`
