# 0.33.0 local release candidate

Status: **local candidate, not tagged or published**. The source version is
`0.33.0`. This cut carries the unpublished 0.32.0 source line, the reviewed
`4a487e4` integration and the newer `7e43e32` integration stack. It does not
create a tag, GitLab Release, shared installation or hosted-qualification
claim.

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
3.13.14. Its installer now checks Python 3.13, Linux x86-64, `sha256sum` and
missing backend libraries before the payload checksum sweep, discovers
`python3.13` or accepts `FDISBULL_PYTHON`, and still requires the documented
system native libraries; no CPython or native-library environment layer is
bundled. Its installed-kit acceptance passed Z3 equivalence/counterexample,
keyboard, memory, native restore, player live resume and project restart; both
bundled skill text retrievals passed; this does not establish that an agent
followed either methodology. The kit SHA-256 is
`3e5b4b0cd2720475bcd415374393e6cdee31a21a2cedb36f30d132f3e0b1ac8e`;
the backend SHA-256 is
`0548d21a5072cc13957b4771af9d31fcc04a50d36159f53066b0d84b572e8212`.
This is local Linux verification, not the required-native CI matrix or a
published artifact.

## Qualification at this cut

Local macOS verification is recorded in
[the candidate evidence](evidence/0.33.0-release/README.md). The full suite
reported **10,191 passed, 2 failed, 419 skipped, 23 errors and 2,322 subtests
passed**. The same failure classes reproduce on the 0.32 candidate
`c80bff0`; they are the inherited macOS Mach-O/GCC fixture limits. Focused
packaging/distribution tests passed **932**. Hosted Linux ordinary/native CI,
installed-wheel PE/DOS/boot acceptance and fresh-prefix installation are
**not** part of this local cut.

## Exclusions and publication gates

- No tag, GitLab release, package upload, shared installation or system change
  is made by this candidate.
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
  installation, both bundled skill retrievals, and an explicit release decision on the
  exact source SHA.
