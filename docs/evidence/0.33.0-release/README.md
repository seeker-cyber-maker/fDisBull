# fDisBull 0.33.0 local candidate evidence

This packet covers a **local macOS release-candidate cut**, not publication or
hosted qualification. The source version is `0.33.0`; the candidate has not
been tagged, uploaded or installed.

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
- Candidate source commit:
  `1004bda484b0405e35247432447deb0e9c7d12de`.

## Local macOS verification (2026-11-05)

Environment: macOS arm64, Python 3.13.14, optional `z3-solver==5.3.2.0`,
`dnfile==0.18.0` and `dncil==1.0.2` from the host environment. The full-suite
run used a temporary `tests` package shim because a host `tests` package
shadowed the checkout. The shim is an environment workaround, not repository
code.

- Full suite: **10,187 passed, 2 failed, 419 skipped, 23 errors, 2,322
  subtests passed** in 282.03 seconds.
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
| core wheel | 592 | `check_dist.py` OK |
| core sdist | 2,053 | `check_dist.py` OK |
| player wheel | 19 | `check_dist.py` OK |
| tool ZIP | 2,035 | `check_dist.py` OK |
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

The native Linux offline kit was built on Boat Linux x86-64 from the candidate
source and verified with CPython **3.13.14** (any 3.13.x is accepted). Its
offline kit SHA-256 is
`9b5a1e4310a8ad955555910cb50d7eafdfbeb03094eb17fbe9c34fa1c11c2909`;
the backend is `0548d21a5072cc13957b4771af9d31fcc04a50d36159f53066b0d84b572e8212`.
The installed-kit acceptance passed equivalence/counterexample, keyboard,
memory, native restore, player live resume and project restart; both bundled
skills passed. See `offline-acceptance.json`, `offline-kit-manifest.json`,
`backend-receipt.json` and `offline-build.log`. No full required-native CI or
GitLab release qualification is claimed.

## Limits

- No tag, GitLab release, package upload, shared installation or system change.
- No original game payload, save, emulator state or private FDB payload.
- Open follow-up MRs `!96`, `!97`, `!98` and `!99` are outside this cut.
- Hosted Linux ordinary/native CI, installed-wheel PE/DOS/boot acceptance and
  fresh-prefix installation remain pending.
