# 0.33.0rc1 local release candidate

Status: **local candidate, not tagged or published**. The source version is
`0.33.0rc1`. The candidate exists to exercise the next source line on macOS and
to produce inspectable local artifacts; it does not promote the unpublished
0.32.0 candidate, create a shared installation or assert hosted qualification.

## Lineage

The candidate starts from the unpublished `0.32.0` candidate
`c80bff03e4cd2b946a93e7aecab61e5ff9281f81`, which is based on published
0.31.1 (`b2159367f3d4c2587c75acd077f30b39223da8dc`). It merges the selected
0.32 PR integration `4a487e45e679025af4d2c0aca2b6c8742383ef08`:

- `!93` Boat offline/native qualification handoff and finite runner;
- `!80` built-in GOG Inno 5.6.2 reader;
- `!79` phase contracts and audit guidance;
- `!83` Westwood PAK/CPS/WSA readers and EMC2 guest processor;
- `!86` experimental ScummVM Kyra/EMC2 controller;
- `!87` AGI-to-UIL native component pilot;
- `!88` Kyra debugger control scaffold;
- `!46`, `!47` and `!53` investigation-skill guidance changes.

The reviewed 0.32 `!73` ScummVM AGI/Gob substrate remains in the carried
lineage; it is not duplicated by this merge.

## Carried scope

The candidate carries the 0.32.0 source scope: captured Windows import
recovery, context-aware format/media intake, restricted SMK2 framing, original
Win32/experimental Win16 runtime controls, protected-mode DOS investigations,
exact frame transport and direct RGBA pixels, experimental ScummVM AGI/Gob
debugging, and the headless quit-dialog and signed-return fixes. It also carries
the 0.31.1 packaging and native-CI repairs.

## New in this candidate

- **Boat CI handoff:** finite local/hosted Linux phases, retained-runtime
  preparation, chat/offline inventory helpers and explicit phase receipts. The
  runner does not package or publish by itself.
- **Native GOG Inno intake:** bounded validation and multipart reconstruction
  without an external `innoextract` process. This remains a bounded GOG profile,
  not a general Inno reader or installer runner.
- **Westwood media modules:** PAK/CPS/WSA readers and an EMC2 guest processor
  with explicit duplicate-name, palette, delta-frame and syscall boundaries.
- **ScummVM Kyra and AGI pilots:** source-bound Kyra controller and control-core
  scaffolds, plus a bounded AGI-to-UIL native component path. These are not a
  runnable full Kyra backend, whole AGI compiler or original-game equivalence
  claim.
- **Investigation-skill guidance:** progressive console qualification,
  specialist/worker context selection, and deterministic execution requirements
  merged into the current skill references.

## Qualification at this cut

Local macOS verification is recorded in
[the candidate evidence](evidence/0.33.0-release/README.md). The full local
suite reported **10002 passed, 15 failed, 386 skipped, 23 errors and 2316
subtests passed**; the same 15 failures reproduce on the 0.32 candidate and are
inherited macOS Mach-O/GCC or packaged presentation/PSG fixture limits, not
0.33 regressions. Hosted Linux ordinary/native CI, installed-wheel PE/DOS/boot
acceptance and fresh-prefix installation are **not** part of this local cut. See
the evidence packet for exact commands, artifact checks and known failures.

## Exclusions and publication gates

- No tag, GitLab release, package upload, shared installation or system change
  is made by this candidate.
- No original game payload, save, emulator state or private FDB payload is
  included.
- `!42` and `!74` remain unmerged; unresolved research, the alternative `!67`
  captured-PE route and unselected pending stacks are outside this cut.
- Publication still requires frozen-source Linux ordinary/native qualification,
  required native cases executing rather than skipping, artifact inventory and
  private-input checks, isolated wheel/source installation, both bundled skills,
  and an explicit release decision on the exact source SHA.
