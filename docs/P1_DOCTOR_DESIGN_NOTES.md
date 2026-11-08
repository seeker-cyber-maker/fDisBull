# P1 doctor/version design notes (working)

## Durable-writer classification (issue acceptance: "durable analysis artifacts carry only the primary tool version")

Audit of every `fdisbull_version` writer:

- `project.py` target_sources.loader.version: durable analysis provenance -> patched to primary version (done).
- `debugger.py`, `scummvm_debugger.py`, `scummvm_gob.py`: runtime-debugger session
  metadata stored in the project DB (`runs`/`artifacts` metadata). These records are
  observations about the runtime that produced them, not exported analysis
  artifacts. Keeping the full runtime identity there is correct: they are "tool
  diagnostic context", which the issue says may retain the full identity. Resume
  compatibility checks do not compare `fdisbull_version` (verified: no reader
  compares it; resume gates use source/version SHA and schema).
- `dinopark_scenes.py` (2 sites): evidence receipts over observations
  (`dinopark-text-scene-1`, save-library bundle). These are sanitized evidence
  receipts about a run, not durable analysis exports; the issue's durable
  artifact list (FDBs, UDL/UIL/UDC exports, analysis reports, handoffs,
  knowledge packs) does not include these receipts, and the full identity aids
  regression attribution, which the issue preserves in tool diagnostic context.

Decision: only the FDB provenance field (project.py) is a durable analysis
artifact among the writers; it now records the primary version line.

Second audit pass (2026-11-08): `target_sources.py` writes the same
`target_sources.loader` provenance record for approved external source layers,
so it belongs to the same durable class and received the same primary-version
treatment. Remaining `__version__` users are third-party binding identities
(capstone) or tool-diagnostic contexts (debugger/ScummVM/DinoPark receipts),
which the issue keeps at full identity.

## Pre-existing defect fixed on this branch

`tests/test_distribution.py` carried committed conflict markers
(`<<<<<<< HEAD` / `=======` at lines 1244/1471) from upstream commit
`d3419c85`: the incoming fragment was truncated (no `>>>>>>>` marker) and the
distribution suite could not even be collected. Resolution kept the HEAD-side
body (the release-lineage test text) and removed the malformed fragment; the
source-concepts gate itself is enforced at `scripts/check_dist.py:897`, so no
coverage was lost. Verified: file parses, and the full module passes 916 tests.

## Environment findings from full-suite verification (not repo defects)

1. The miniconda environment contains an installed regular package named
   `tests` (shipped inside site-packages; dist-info `color_matcher-0.6.0`
   RECORD lists `tests/__init__`). A regular package beats the repo's
   namespace `tests/` directory regardless of sys.path order, so the eleven
   `from tests.X import ...` test files could not resolve. They were
   converted to the suite's dominant module-import style
   (`from test_x import ...`, used by 129 files), matching e.g.
   `tests/test_agi_dos.py`.
2. `tests/test_code_overlap_proof.py` requires optional `z3-solver`
   (pyproject extra `proof`/`test`), which is not installed in this
   environment; its collection error is pre-existing (verified identical on
   the unmodified baseline).
3. `tests/test_distribution.py` carried committed conflict markers
   (see above); resolved on this branch.

## Base and integration

Base: gitlab/release/0.34.0 tip `4932cf4cf32e87b3d618e33d99361da87bc0dd18`
(the `v0.34.1` tag commit). Branch `codex/p1-doctor-version-identity-20261108`.
The implementation MR targets the release line per issue !1 ("use the current
release/0.33.0 line as the integration baseline/target"), where the live
release line now continues at release/0.34.0; !100 remains the 0.33→main
vehicle. The reviewed source `c9bd78f60c2a7fa4d3f4eecc310db73fb9c64154` is an
ancestor of the base, so the reviewed analysis is contained in the baseline.

## Full-suite baseline comparison (2026-11-08, branch tree)

Unmodified baseline (`git stash` run) and patched tree both fail identically in
the environment-limited set: 34 failed / 48 errors — Linux-only compiler
fixtures (`-Wl,-e` + ibtplt on macOS gcc), missing optional `z3-solver`,
`tests/` namespace shadow, and other recorded macOS environment limits from the
existing suite baselines (compare docs: "3F/23E macOS environment failures" era
summaries). The patched tree adds **zero** new failures: all doctor/version
affected modules (test_preflight_identity, test_capabilities, test_doctor,
test_output_cli, test_distribution, test_text_distribution,
test_platform_review, test_agent_discovery) pass; 11,174 tests pass overall.

## Skill-gate repair (found during installed-artifact verification)

Merge `6d71c27e` (!113) added table rows to
`src/fdisbull/skills/fdisbull-investigate/SKILL.md` whose link label repeated
the reference path (e.g. `[references/scenes.md](references/scenes.md)`),
duplicating targets that the gate (`scripts/check_agent_skill.py:199`) forbids.
Removed the redundant rows/links (13 lines); all targets remain linked exactly
once. `tests/test_agent_skill_gate.py` now passes (27 passed).

Final affected-suite receipt on the amended commit: 1034 passed, 2 skipped
(test_preflight_identity, test_capabilities, test_doctor, test_output_cli,
test_distribution, test_text_distribution, test_platform_review,
test_agent_discovery, test_agent_skill_gate, test_source_catalog).

## Baseline-vs-patched full-suite failure comparison (executed twice, 2026-11-08)

Run A (patched tree, pre-repair of the two gate failures): 33 FAILED lines.
Run B (unmodified baseline via git stash): 31 FAILED lines. The only deltas:
- baseline additionally fails `test_agent_skill_gate[fdisbull-investigate]`
  (duplicate skill-index links) and `test_capabilities` size bound — both are
  REPAIRED by this branch, not caused by it;
- `test_loading` gcc temp-path differs between runs only (same environment
  failure). Failure-set identity otherwise holds: 31 of 33 patched failures
  match the baseline exactly; zero new failures introduced.

## Final head identity

Branch `codex/p1-doctor-version-identity-20261108`; base
`4932cf4cf32e87b3d618e33d99361da87bc0dd18` (gitlab/release/0.34.0, tag
v0.34.1). The branch head records the executed 31-vs-33 baseline comparison
above (only deltas: the two pre-existing failures this branch repairs, plus a
temp-path-only difference in test_loading). MR !116 targets release/0.34.0.

## Skill review finding (2026-11-08): z-controller CLI wiring lost in a merge

The bundled `fdisbull-investigate` skill and `docs/AGENT_QUICKSTART.md` direct
agents to `fdisbull z-controller PROJECT --executable ... --game-dir ...`,
and `tests/test_z_controller_cli.py` exercises it. Commit `98e94697` added
the parser/dispatch wiring; the merge `c9922f85` ("Integrate skill fast-path
and native Inno reader into 0.34", parents `23fd9747` = 0.34 side without the
wiring, `5ca2d5f4` = skill-fast-path side with it) resolved `cli.py` to the
parent WITHOUT the two `z-controller` hunks while KEEPING `z_controller.py`,
the skill text, the quickstart text and the test file. Result on
`release/0.34.0` (and `main`, 0.33, 0.31): `fdisbull: error: invalid choice:
'z-controller'`, and `tests/test_z_controller_cli.py` fails 4/4 on the
unmodified baseline (pre-existing, not caused by this branch). This branch
restores the two lost hunks verbatim (parser registration and `_dispatch`
branch), so `fdisbull z-controller` registers again and all four
`test_z_controller_cli.py` tests pass here. The release lines still need the
same restore.

## Skill review finding (2026-11-08, part 2): test_scenes skill-file list is stale

`tests/test_scenes.py:341-360` pins the bundled skill file list to 19 entries.
Four later guides never updated it, so
`test_bundled_investigation_skill_is_readable_without_project` fails on the
pristine `release/0.34.0` tip (3aaac41b) exactly as on this branch:
`desqview-and-memory-search.md` + `dos-drivers-and-qemm.md` (MR !112 lane,
f5b4158a/7f89f185), `execution-event-search.md` (MR !113 lane, 089c1841), and
`references/task-framing.md` (skill-fast-path lane, 04ce7880). The stricter
skill gate (`tests/test_agent_skill_gate.py`, 27 tests) passes on all 23
reference files, and every guide is indexed and reachable. Not repaired on
this branch to keep the P1 diff scoped; same release-line defect class as the
z-controller wiring loss above.

## Final suite receipt (2026-11-08, head eb275aea)

Full suite with all optional extras installed (unicorn, z3-solver, dnfile,
dncil, pycparser 3.12): `11181 passed, 496 skipped, 2379 subtests passed`.
Remaining failures are host-environment, reproduced on the pristine release
tip: Apple clang cannot emit Linux ELF for `test_platform_calls`,
`test_elf_metadata`, `test_loading` (gcc IS found so the check raises before
the lief.ELF skip), plus the `mads-pack` vs `madspack` identifier collision
(codec_profiles.probe from MR !110/!111 runs first in `_media`, test still
expects the legacy `madspack`) and the stale skill-file list above.

## Release-line consistency fixes folded into this branch (2026-11-08, part 3)

Two same-tree conflicts on `release/0.34.0` are fixed here instead of only
being logged, because both are one-line test-contract repairs:

- `tests/test_format_media.py`: the strong-header row expected the legacy
  `madspack` identifier from `format_media.probe`. MR !110/!111 added
  `codec_profiles.probe` ahead of it in `_media()` with the richer validated
  `mads-pack` identity (176-byte header, section table, `mads-pack` decoder
  module link). `tests/test_mads_integration_audit.py` already asserts
  `mads-pack` for the same bytes, so the strong-header row now feeds a full
  176-byte pack header and expects `mads-pack`; `full_decode` and
  `native_runtime_tested` stay false. The empty legacy `madspack` catalog row
  remains defined but unreachable through `identify_file`.
- `tests/test_scenes.py`: the bundled-skill file list now includes the four
  later guides (`desqview-and-memory-search`, `dos-drivers-and-qemm`,
  `execution-event-search`, `task-framing`), 23 entries total; the selective
  read loop and invalid-path cases are unchanged.

## Final suite receipt (2026-11-08, head 1a18aa64)

Full suite with all optional extras installed (unicorn, z3-solver, dnfile,
dncil, pycparser 3.12): `11368 passed, 370 skipped, 2379 subtests passed`.
Every branch-scoped failure is fixed on this head; the only remaining
failures are the macOS-host ELF environment class (Apple clang cannot emit
Linux ELF for `test_inspection`/`test_loading`/`test_elf_metadata`/
`test_platform_calls`), reproduced identically on the pristine release tip.
The previously documented `mads-pack` and skill-list failures no longer
appear: both are repaired in this branch.
