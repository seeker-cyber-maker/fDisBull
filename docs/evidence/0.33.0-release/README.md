# fDisBull 0.33.0 release evidence

This packet covers the **tagged local 0.33.0 release**, not a GitLab publication
or hosted CI claim. The source version is `0.33.0`; tag `v0.33.0` points at
`bdd096f963f2c125e70e7f52ae944b662dd89f6f`. The final tag is installed in the
local shared prefix. The earlier `0.33.0-c18afda` candidate evidence below is
retained as history and is not a result for the tagged source.

## Source lineage

- Published base: `0.31.1` at
  `b2159367f3d4c2587c75acd077f30b39223da8dc`.
- Unpublished 0.32.0 candidate:
  `c80bff03e4cd2b946a93e7aecab61e5ff9281f81`.
- Prior local `0.33.0rc1`:
  `337848e992d62dc530cd02f42f9f52c8f2088e90`; its evidence remains at
  `docs/evidence/0.33.0rc1-release/`.
- Reviewed integration merged into this cut:
  `7e43e32080eebb7a8cac5c5f1010db340fa39052`, merge commit
  `05a4f5ce0dacb2f3992daa7115c661e0ed85bb39`.
- Candidate functional source commit:
  `1004bda484b0405e35247432447deb0e9c7d12de`.
- Final release-tree merge of `main`:
  `02669325f8c318901eeefe1d825eca21b3306c1b`.
- CHimpREC captured-PE writer PR `!67` merged as
  `b397a95d42b1747c2da713d10c2b63d2251e031c`.
- Library/preflight follow-up commit:
  `95b8520449a2ed388798a6b2cf10053e67c7d923`; it keeps the single-pass GOG
  identity hashes, adds read-only Game/Database Library matching, and orders
  installer preflight before payload checksums. App artifacts and source
  archives were rebuilt from this commit. The native DOSBox backend and its
  source companion retain their functional-source receipt at
  `1004bda484b0405e35247432447deb0e9c7d12de`.
- Tagged source:
  `bdd096f963f2c125e70e7f52ae944b662dd89f6f`.

## Earlier local macOS verification for `0.33.0-c18afda` (2026-11-05)

Environment: macOS arm64, CPython 3.13.18 from the freshly installed local
prefix, optional `z3-solver==5.3.2.0`, `dnfile==0.18.0` and `dncil==1.0.2`.
The full-suite command imported the candidate source through `PYTHONPATH` so
the installed interpreter could exercise it.

- Full suite: **10,248 passed, 2 failed, 359 skipped, 23 errors, 2,322
  subtests passed** in 291.74 seconds.
- The two failures and the 23 errors reproduce on the 0.32 candidate
  `c80bff0`; they are inherited macOS Mach-O/ELF and GCC Linux-ELF toolchain
  limits. See `base-failure-reproduction.log`.
- Focused packaging/distribution set: **932 passed**.
- `compileall` passed for `src/fdisbull`, `player/fdisbull_player`, `scripts`
  and `examples`.

## Earlier artifacts for `0.33.0-c18afda`

These are the historical candidate artifacts, not the tagged source artifacts.
Built with `uv build` and `scripts/build_release.py` from that candidate:

| Artifact | Entries | Check |
| --- | --- | --- |
| core wheel | 598 | `check_dist.py` OK |
| core sdist | 2,063 | `check_dist.py` OK |
| player wheel | 19 | `check_dist.py` OK |
| tool ZIP | 2,045 | `check_dist.py` OK |
| player sdist | — | built, auxiliary |

`check_package_payloads.py` passed for the four checked artifacts; see
`payload.json`. The isolated wheel smoke reported `fdisbull 0.33.0`,
`result.ok=true` with 30 capability records, and the standalone player help.
Hashes are in `artifact-sha256.txt`; bytes remain outside Git.

## Offline package Python boundary

The source declares `requires-python >=3.12`. The binary Linux offline kit uses
CPython 3.13 because its pinned wheels are `cp313`. The previous installer
required exactly `3.13.5`; this cut accepts any CPython `3.13.x` and states the
dependency boundary. A host defaulting to 3.12 must use an isolated 3.13
runtime for the binary kit; this is recorded in `intake.json`.

The native backend was built on Boat Linux x86-64. The offline kit was assembled
from that verified backend and the final wheelhouse, then installed and verified
in a fresh Boat x86-64 sandbox with CPython **3.13.14** (any 3.13.x is accepted). Its installer checks Python 3.13, Linux x86-64, `sha256sum` and missing
backend libraries before the payload checksum sweep; it discovers
`python3.13` or accepts `FDISBULL_PYTHON`, and applies the bundled library path
to the `ldd` check. It does not bundle a CPython interpreter or the system
native-library environment. Its offline kit SHA-256 is
`2a279eb865cafc29d8a75432d75a340163ed17fd55878f01468aa90d2e7803ac`;
the backend is `0548d21a5072cc13957b4771af9d31fcc04a50d36159f53066b0d84b572e8212`.
The installed-kit acceptance passed equivalence/counterexample, keyboard,
memory, native restore, player live resume and project restart; both bundled
skill text retrievals passed; this is not a methodology-following test. See `offline-acceptance.json`, `offline-kit-manifest.json`,
`backend-receipt.json` and `offline-build.log`. No full required-native CI or
GitLab release qualification is claimed.

## Final tagged source and core qualification

`bdd096f963f2c125e70e7f52ae944b662dd89f6f` passed the exact-source Boat Linux
core gate. Ordinary JUnit: 12,970 cases, 0 failures/errors, 410 skipped; 26
required contracts also passed. Stable native: 2,355 cases with no failures,
errors or skips. Layers native: 2,673 cases with no failures, errors or skips.
Unified PE/DOS: 188 + 17 cases with no failures, errors or skips.
`check_ci_qualification.py --legacy-dos-only` produced
`boat-core-qualification.json` in this directory.

The tagged source artifacts are:

| Artifact | SHA-256 |
| --- | --- |
| core wheel | `89ff609d9186f34950ae1ce0854381930ebfbb8ed247704f54606b4945cb70e2` |
| sdist | `f4e9bddbba63f01e39f87f9cbc027d63afebad02b4ca232b77d10a0dfae1f097` |
| player wheel | `a09a48dea4442a8888bd1be9436d2c68e0cdaf53693459e24883339df376c460` |
| tool ZIP | `250a686383c166d92110cef17d9271699499bef1253d47547ce2c98d0036134d` |

The optional chat offline consumer was not qualified. Its preparation rejects
the retained QEMU installer bitmap `qemu-nsis.bmp` under the kit's
private-payload rule; the core gate does not depend on that consumer.

## Local shared-prefix installation

The tagged source is active at
`/Users/Shared/fDisBull/releases/0.33.0-bdd096f` (selector
`releases/0.33.0-bdd096f`) with source identity
`bdd096f963f2c125e70e7f52ae944b662dd89f6f`. The payload verifier passed with
`active_default: true` and 4,563 entries. `check_local_install.py` reported
PASSED. The installed-prefix smoke included `pip check`, version, both bundled
skill text retrievals, player help and a passing DOSBox doctor. The guarded
rollback plan targets `releases/0.33.0-c18afda`.

## Limits

- `v0.33.0` is tagged; no GitLab Release, package upload or hosted CI claim.
- Local shared-prefix installation and activation are performed for the tag.
- The optional chat offline consumer remains unqualified.
- No original game payload, save, emulator state or private FDB payload.
- Open follow-up MRs `!96`, `!97`, `!98` and `!99` are outside this cut.
