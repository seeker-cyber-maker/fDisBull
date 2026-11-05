# fDisBull 0.33.0 local candidate evidence

This packet covers a **local macOS release-candidate cut**, not publication or
hosted qualification. The source version is `0.33.0`; the candidate has not
been tagged or uploaded. It was installed into a local shared prefix for
verification and the active local selector currently resolves to that prefix.

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

## Local macOS verification (2026-11-05)

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

## Artifacts

Built with `uv build` and `scripts/build_release.py` from the candidate source:

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

## Local shared-prefix installation

The candidate is active at
`/Users/Shared/fDisBull/releases/0.33.0-c18afda` (selector
`releases/0.33.0-c18afda`) with source identity
`95b8520449a2ed388798a6b2cf10053e67c7d923`. The payload verifier passed with
`active_default: true` and 4,561 entries. The installed-prefix smoke included
`pip check`, version, authored MZ create/reopen, both bundled skill text
retrievals, player help and a passing DOSBox doctor. `check_local_install.py`
reported PASSED. The guarded rollback plan targets
`releases/0.32.0-c80bff0-prototype`; applying it remains a caller action.

## Limits

- No tag, GitLab release, package upload or public release.
- Local shared-prefix installation and activation are performed; the
  candidate remains a local release candidate.
- No original game payload, save, emulator state or private FDB payload.
- Open follow-up MRs `!96`, `!97`, `!98` and `!99` are outside this cut.
- Hosted Linux ordinary/native CI and installed-wheel PE/DOS/boot acceptance
  remain pending.
