# 0.31.0 release

Status: **release candidate, not tagged or published**. This line carries the
0.30.0 release plus the reviewed post-release code merges and the new bounded
research examples. Publication, a Git tag and a GitLab Release package remain
separate gates.

## New in 0.31.0

- **Lossless frame-timeline delta storage (MR !41):** `debug-timeline-*` now
  accepts `storage_mode='delta'` with bounded keyframes, verified XOR/zlib
  payload chains, hash-checked materialization and eviction that promotes a
  dependent successor before discarding its base. Full capture still occurs at
  every point; this is a live retained-payload optimization, not a faster
  recorder or a new portable save format
  (`docs/FRAME_STATE_DELTAS.md`).
- **Bounded typed-C to UIL frontend (MR !48):** `import_c` reads a selected
  function through a caller-provided local Clang AST and emits the existing
  `fdisbull-il-1` profile for admitted scalar, local-array, guard and
  fixed-buffer contracts. It refuses unsupported loops, calls, pointers,
  division and effects rather than widening the contract
  (`docs/BOUNDED_TYPED_C_FRONTEND.md`).
- **Windows original-runtime preflight (MR !60):** a read-only inventory for
  Win16 NE, Win32 PE32 and Win64 PE32+ work. It checks tool/file presence and
  versions only; it does not initialize a Wine prefix, start QEMU, execute a
  target or qualify a debugger (`docs/WINDOWS_ORIGINAL_RUNTIME_BRIDGE.md`).
- **CHIP-8 corpus and instruction-space pilot (MR !61):** two independently
  written decoders compare all 65,536 words under three declared profiles, and
  a bounded authored interpreter measures a nine-program CC0 corpus. The
  source package omits ROMs and SQLite files; corpus fetches are explicit and
  digest-checked (`examples/chip8_pilot/`).
- **UDC registry and fresh-agent swede examples (MRs !57, !58):** a local
  planning index over existing catalog/link validators, plus a reproducible
  one-, two- and three-block composition trial. Both are examples with
  `execution_authorized: false` and no production CLI or schema change; the
  swede compiler checks require Linux x86-64 and skip elsewhere
  (`examples/udc_registry/`, `examples/swede_trial/`).
- **Cold-agent benchmark and skill refresh (MRs !59, !44):** a four-stage
  cold-agent evaluation report and test, plus a post-0.30.0 README/skill refresh
  that restores explicit evidence cautions and preserves the console-reference
  anchor (`docs/COLD_AGENT_EGM_BENCHMARK.md`).

## Compatibility

- Project schema, `.fdb` databases, capabilities and existing UIL formats remain
  unchanged.
- The new CHIP-8, UDC-registry and swede material is example/research scope, not
  a new installed CLI method or a claim of general emulator/compiler support.
- Original game files, ROMs, saves, byte-containing databases and private
  payload stores remain outside Git and distribution packages.
- The typed-C frontend fixes an x86-64 Linux LP64/C11 source ABI for its own
  import; it does not establish the ABI or provenance of a recovered binary.

## Qualification

- Focused release-candidate tests: 67 passed / 13 skipped across the UDC
  registry, swede trial, CHIP-8, Windows preflight and cold-agent benchmark
  suites. The swede compiler checks skip off Linux x86-64.
- Targeted frame-timeline and typed-C suites passed on the merged commits
  (148 and 26 tests respectively, plus subtests).
- Full release-candidate suite: 8,992 passed, 335 skipped, 2,316 subtests
  passed, with the known macOS-only baseline of 3 failures and 23 errors
  (Linux ELF/GCC fixtures and one case-sensitive media fixture). No new failure
  is in the added feature suites.
- Candidate identities, artifact hashes and raw logs are in
  [`docs/evidence/0.31.0-release/`](evidence/0.31.0-release/README.md).

## Explicitly not included

- The large indexed-UIL/Civilization `z-work` candidate and its record-validation
  follow-up remain outside this candidate.
- The consolidated UDL/UIL/UDC reference, console-skill and cold-agent
  delegation documentation MRs remain Draft; corrected terminology and anchors
  are on their branches, not in this package.
- No native Windows Win16/PE32 debugger, Wine 11 guest image, CHIP-8 historical
  emulator qualification, or general swede compiler is claimed.
- No Git tag, GitLab Release, shared-prefix activation or publication is
  performed by this candidate.
