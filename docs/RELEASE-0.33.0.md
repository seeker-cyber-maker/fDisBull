# 0.33.0 local release candidate

Status: **local candidate, not tagged or published**. The source version is
`0.33.0`. This cut carries the unpublished 0.32.0 source line, the reviewed
`4a487e4` integration and the newer `7e43e32` integration stack. It does not
create a tag, GitLab Release or hosted-qualification claim. The candidate is
installed and active only in the local macOS shared prefix described below.

## Lineage

- Published base: `0.31.1` at
  `b2159367f3d4c2587c75acd077f30b39223da8dc`.
- Unpublished 0.32.0 candidate:
  `c80bff03e4cd2b946a93e7aecab61e5ff9281f81`.
- First 0.33 local candidate (`0.33.0rc1`):
  `337848e992d62dc530cd02f42f9f52c8f2088e90`, based on the `4a487e4`
  integration.
- New integration source:
  `7e43e32080eebb7a8cac5c5f1010db340fa39052`, merged as
  `05a4f5ce0dacb2f3992daa7115c661e0ed85bb39`.
- Final release-tree merge of `main`:
  `02669325f8c318901eeefe1d825eca21b3306c1b`.
- CHimpREC captured-PE writer PR `!67` merged as
  `b397a95d42b1747c2da713d10c2b63d2251e031c`; it adds the missing writer,
  reviewed plan-file path and focused PE32/PE32+ round-trip tests.
- Artifact/source build commit:
  `95b8520449a2ed388798a6b2cf10053e67c7d923`; it keeps single-pass GOG source
  and output hashes, adds read-only library identity matching, and places
  installer compatibility checks before the payload checksum sweep.
- Post-build bootstrap/status commit:
  `34e7278c05b419bc1cd660e631edcda2dee0d07d`; it adds the `--python`
  installer selector, repeats the native-library preflight in `bin/dosbox`,
  and changes completed intake records to outer `status: inspected`.

The 0.32.0 source line was never published. Its unpublished candidate remains
part of the lineage, not a missing tag.

## New in this integration pass

The newer `7e43e32` integration adds the reviewed 0.32/0.33 pull-request
stack, including:

- Library handoffs and dated handoff reconciliation (`!42`);
- Colonization paired production/difficulty examples (`!50`);
- Parallel research-workspace lifecycle and matched-methodology pilots
  (`!51`, `!52`);
- Syndicate tactical history, rewind and campaign/save studies
  (`!54`, `!55`);
- Portable UIL text, Z-harness and large-world reference studies (`!56`);
- PE32-first reversible UIL feedback fusion (`!63`);
- Maturity/deterministic-pipeline audits and reusable environment/ISA/target
  packages (`!64`, `!65`);
- Portable service-contract and common-UIL CI handoffs (`!66`, `!76`);
- NES C/Python-before-UIL and P00 DOS intake comparisons (`!70`, `!81`);
- Castles II Save/Load harness and page-cited manual OCR (`!84`, `!85`);
- Shared scene fingerprints/scanline rules and text-asset shell connectors
  (`!89`, `!90`);
- Z3-to-direct-Python block translation and Z-machine provider comparison
  (`!91`, `!92`);
- Native ScummVM GLK/Z-code bridge and owned launcher (`!94`).

This cut also carries the earlier 0.32 integration: Boat CI handoff, built-in
GOG Inno 5.6.2 intake, Westwood PAK/CPS/WSA and EMC2 modules, experimental
ScummVM Kyra/AGI pilots, the headless quit-dialog fix, signed-return
correction and package-completeness repairs. GOG extraction now retains its
single-pass source and output hashes while optionally comparing extracted
SHA-256 identities with a configured, read-only Game/Database Library registry.

Format intake now labels a completed file record `status: inspected`; format
recognition remains in nested `identification.status`, `recognized` and
`header_valid`. This prevents an unknown source such as an unrecognized SHI
file from appearing to be identified. The intake catalog still recognizes a
16-bit DOS MZ header and reports an unknown SHI without inventing a decoder.
SHI decoding and its discovery adapter remain in the separate `!97` follow-up,
which is outside this cut.

## Offline package Python boundary

The source declares `requires-python >=3.12`. The binary Linux offline kit is
built for CPython 3.13 (`cp313`) because its pinned dependency wheels include
compiled extensions. The previous installer required exactly `3.13.5`; this
cut accepts any CPython `3.13.x` and states the dependency boundary explicitly.
A Python 3.12 host must use an isolated 3.13 runtime for the binary kit; a
source install can use 3.12 subject to the separately declared dependency
environment.

The 0.33 offline kit was assembled locally from the verified Boat-built backend
and installed/tested on Boat Linux x86-64 with CPython
3.13.14. Its installer checks Python 3.13, Linux x86-64, `sha256sum`, `ldd` and
all missing backend libraries before the payload checksum sweep. It accepts
`--python /absolute/path/to/python3.13` (which takes precedence over
`FDISBULL_PYTHON`) and discovers `python3.13`/a 3.13 `python3` otherwise. The
generated `bin/dosbox` wrapper repeats the complete `ldd` preflight before
starting the debugger, so missing host sonames such as `libncurses.so.6` and
`libtinfo.so.6` are reported together before any native process starts. No
CPython or native-library environment layer is bundled; a host must supply the
interpreter and documented libraries. Its installed-kit acceptance passed Z3 equivalence/counterexample,
keyboard, memory, native restore, player live resume and project restart; both
bundled skill text retrievals passed; this does not establish that an agent
followed either methodology. The kit SHA-256 is
`f15257d75245f0698948d5e54999f283b841572636f1ff0a531637902decb179`;
the backend SHA-256 is
`0548d21a5072cc13957b4771af9d31fcc04a50d36159f53066b0d84b572e8212`.
This is local Linux verification, not the required-native CI matrix or a
published artifact.

## Qualification at this cut

Local macOS verification is recorded in
[the candidate evidence](evidence/0.33.0-release/README.md). The installed
prefix full suite reported **10,248 passed, 2 failed, 359 skipped, 23 errors and
2,322 subtests passed** in 291.74 seconds. The same failure classes reproduce
on the 0.32 candidate `c80bff0`; they are the inherited macOS Mach-O/GCC fixture
limits. Focused packaging/distribution tests passed **932**; the GOG contract
suite now has **26** cases. The candidate is active at
`/Users/Shared/fDisBull/releases/0.33.0-c18afda` with source identity
`95b8520`; `check_local_install.py` passed and rollback to
`0.32.0-c80bff0-prototype` is planned but not applied. Hosted Linux
ordinary/native CI and installed-wheel PE/DOS/boot acceptance are **not** part
of this local cut.

### Artifact bytes

| Artifact | SHA-256 |
| --- | --- |
| core wheel | `80b4a873a1d17f1c6613cc9ba83cf2761a993e774570ef6eb268325cad617ee9` |
| sdist | `8db547c639f293b4dfde52f1506f3e7b5d4bf1c5d67dcf49332f99bb536b6f0b` |
| player wheel | `d52b7ae86d87bc6a6775762c7418f1e68bc9891a00d9ff71ce6fa525f0a70240` |
| tool ZIP | `ef251fb003146d8dd7166283d47825c72ac17d97a375fd04251394b453d22225` |
| offline kit | `f15257d75245f0698948d5e54999f283b841572636f1ff0a531637902decb179` |
| outer kit ZIP | `f809e36b09a0cc55f6d9e2c99e6343d80f74f9aaabf7f13844c12c186b48b4be` |

The outer wrapper is packaging-only. Its inner kit was rebuilt after the prior
acceptance, so the new outer kit has **no new Linux acceptance result**; its
`evidence/offline-acceptance.json` explicitly records `not_run` and the prior
tested kit hash. The prior acceptance claim refers only to kit
`2a279eb865cafc29d8a75432d75a340163ed17fd55878f01468aa90d2e7803ac`.

## Exclusions and publication gates

- No tag, GitLab release or package upload is made by this candidate. A local
  shared-prefix installation is performed; it is not a publication or a system
  qualification claim.
- No original game payload, save, emulator state or private FDB payload is
  included.
- Open follow-up MRs `!96`, `!97`, `!98` and `!99` are outside this cut.
  `!43`, `!49`, `!60`, `!69`, `!72`, `!75`, `!77` and `!82` remain blocked by
  their recorded prerequisites. `!67` is not blocked: its captured-PE writer
  is merged as `b397a95d42b1747c2da713d10c2b63d2251e031c`. The separate `!96`
  GOG/Inno provider follow-up remains outside this cut.
- Publication still requires frozen-source Linux ordinary/native
  qualification, required native cases executing rather than skipping,
  artifact inventory and private-input checks, isolated wheel/source
  installation, both bundled skill retrievals, and an explicit release decision
  on the exact source SHA.
