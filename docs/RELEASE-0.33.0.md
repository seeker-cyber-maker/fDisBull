# 0.33.0 release

Status: **tagged `v0.33.0` and active in the local macOS shared prefix; no
GitLab Release or package upload**. The tag points at
`bdd096f963f2c125e70e7f52ae944b662dd89f6f`. The source version is `0.33.0`.
This cut carries the unpublished 0.32.0 source line, the reviewed `4a487e4`
integration and the newer `7e43e32` integration stack. The exact-source core
Boat Linux gate passed; the optional chat offline consumer remains unqualified.

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

The earlier `0.33.0-c18afda` offline kit was assembled locally from the
verified Boat-built backend and installed/tested on Boat Linux x86-64 with
CPython 3.13.14. Its installer checks Python 3.13, Linux x86-64, `sha256sum`, `ldd` and
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

The final source is `bdd096f963f2c125e70e7f52ae944b662dd89f6f`. Its active
local prefix is `/Users/Shared/fDisBull/releases/0.33.0-bdd096f` (selector
`releases/0.33.0-bdd096f`); `check_local_install.py` reports PASSED with 4,563
payload entries. The payload verifier, `pip check`, version, both bundled
skill retrievals, player help, DOSBox doctor and the local prefix smokes
passed. The guarded rollback targets `releases/0.33.0-c18afda`.

The exact-source Boat Linux core gate passed:

- ordinary: 12,970 JUnit cases (410 skipped) and 26 required contracts, no
  failures/errors;
- stable native: 2,355 cases, no failures/errors/skips;
- layers native: 2,673 cases, no failures/errors/skips;
- unified PE/DOS: 188 + 17 cases, no failures/errors/skips.

`check_ci_qualification.py --legacy-dos-only` produced
`docs/evidence/0.33.0-release/boat-core-qualification.json` for this source.
The optional chat offline consumer was **not qualified**: chat preparation
rejects the retained QEMU installer bitmap `qemu-nsis.bmp` under the kit's
private-payload rule. The earlier macOS candidate results remain historical
evidence for `0.33.0-c18afda` and `95b8520`, not results for this final source.

### Artifact bytes

| Artifact | SHA-256 |
| --- | --- |
| core wheel | `89ff609d9186f34950ae1ce0854381930ebfbb8ed247704f54606b4945cb70e2` |
| sdist | `f4e9bddbba63f01e39f87f9cbc027d63afebad02b4ca232b77d10a0dfae1f097` |
| player wheel | `a09a48dea4442a8888bd1be9436d2c68e0cdaf53693459e24883339df376c460` |
| tool ZIP | `250a686383c166d92110cef17d9271699499bef1253d47547ce2c98d0036134d` |

The earlier `0.33.0-c18afda` offline kit and outer kit were not rebuilt from
this final source; their prior acceptance is not a result for `bdd096f`.

## Exclusions and publication gates

- `v0.33.0` is tagged at `bdd096f` and active in the local shared prefix. No
  GitLab Release, package upload or hosted CI claim is made; the offline chat
  consumer is explicitly unqualified.
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
