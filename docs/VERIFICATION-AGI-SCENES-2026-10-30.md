# AGI scene census: KQ1 and PQ1 verification

Date: 2026-10-30 (America/New_York). Base:
`f94a5cd74b153b58f56c9fdb6c653d2e295f5ee6`.

**Result:** a requirements-first pass can inventory the supplied original DOS
AGI games quickly and deterministically before deeper code investigation. All
90 present KQ1 LOGICs and 118 present PQ1 LOGICs were structurally decoded. The
pass collects scene ingredients, typed references and explicit source obligations.
It does not establish that every scene, progression path or game intent has been
recovered. Accepted executable UIL interactions remain **zero**.

The [workflow and API guide](AGI_SCENE_CENSUS.md) describes the method. The
[machine-readable receipt](evidence/agi-scenes-2026-10-30/verification.json)
contains the complete selected source identities, implementation hashes, scan
counts, timing samples and source-correspondence results. No original resource,
game message, vocabulary spelling, inventory name or byte-retaining project is
included in this evidence directory.

## Qualification and denominator

| Input | Resource identity | Declared decoder profile |
| --- | --- | --- |
| KQ1 DOS 2.0F, 1987-05-05 | LOGDIR MD5 `10ad66e2ecbd66951534a50aedcd0128` | AGI 2.917 |
| PQ1 EGA/DOS 2.0G, 1987-12-03 | LOGDIR MD5 `d194e5d88363095f55d5096b8e32fbbb` | AGI 2.917 |

These match the DOS entries in the pinned
[ScummVM detection table](https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/detection_tables.h).
Both supplied `AGIDATA.OVL` files contain `Version 2.917` at offset 2756 and have
SHA-256 `f7ca256c1c0ab12509d695baabdd44a3c5e72a570b08118d3ead995a47f4c383`.
The directory identity, DOS input context and overlay qualify this resource
profile together. A matching directory hash alone does not identify a platform
uniquely, authenticate a release or qualify its native interpreter.

The two supplied `AGI` files differ. In particular, the KQ1 file is not an MZ
executable. This pass did not execute either native interpreter, and does not
reuse a historical native benchmark as fresh runtime evidence. SCI remakes,
early GAL/booter KQ1, AGI3 and alternate platform layouts are outside this
frontend's claimed scope.

The census denominator is **present LOGDIR entries**. A LOGIC may implement a
room, helper, common command, modal activity or other behavior. A room number,
LOGIC number and picture number are distinct typed identities even when their
numeric values happen to agree.

## Observed coverage

| Measure | KQ1 | PQ1 |
| --- | ---: | ---: |
| Present / decoded LOGICs | 90 / 90 | 118 / 118 |
| Main-stream instructions | 11,452 | 26,105 |
| Code bytes | 54,772 | 128,087 |
| Condition predicates | 5,083 | 10,446 |
| `said` command patterns | 1,478 | 3,147 |
| Present messages / message slots | 1,442 / 1,526 | 3,592 / 3,678 |
| Vocabulary groups / entries | 260 / 496 | 358 / 1,126 |
| Inventory objects | 27 | 25 |
| Picture directory entries | 82 | 71 |
| View directory entries | 118 | 220 |
| Sound directory entries | 26 | 36 |
| Background-producing LOGICs | 81 | 55 |
| Static room-target candidates | 81 | 42 |
| LOGIC 0 `call.v(v0)` dispatch candidates | 1 | 3 |
| Typed references | 3,161 | 5,114 |
| Variable-selected references | 265 | 358 |
| Variable references resolved to finite sets | 5 | 21 |
| Variable references still unresolved | 260 | 337 |
| Worklist updates in resolve stage | 11,703 | 28,958 |
| Layout failures / budget stops | 0 / 0 | 0 / 0 |
| Accepted UIL interactions | 0 | 0 |
| Scene discovery complete | false | false |

Background-producing scripts and room-target candidates are separate sets with
different admission rules. Neither count is the number of fully recovered scenes.
Literal references can occur in unreachable code; finite value sets are
conservative local analysis results, not proofs that a path is feasible. A
`call.v(v0)` site records an operand relationship; it does not prove complete
room dispatch or a room-to-LOGIC mapping.

Both games reached the value analyzer's fixed point within its budget. That means
the implemented conservative analysis finished; it does not mean all variable
references became known. Calls, persistent state, unknown values at saved scan
entries, volatile variables and unmodeled effects remain barriers. The analyzer
does not perform interprocedural closure or evaluate condition feasibility.

### Retained resource errors

The supplied KQ1 `VOL.2` is 90,891 bytes long. Four present sound entries point
beyond it and remain explicit errors:

| Sound | Volume | Directory offset |
| --- | ---: | ---: |
| 34 | 2 | 134,703 |
| 35 | 2 | 134,799 |
| 36 | 2 | 134,893 |
| 37 | 2 | 135,787 |

Consequently KQ1 has complete directory enumeration but incomplete resource
integrity. All its LOGICs, message tables, vocabulary and inventory decoded.
PQ1 had no resource integrity errors. The receipt's `resource_errors` counter
is the LOGIC decode frontier; the separate `resource_issues` list and
`resource_integrity_complete` field include non-LOGIC failures. No original file
was repaired or replaced.

## Repeated scan cost

Python 3.12.14; five consecutive scans per stage and game in the same already
imported process, with a warm filesystem cache:

| Game / stage | Median | Minimum | Maximum |
| --- | ---: | ---: | ---: |
| KQ1 outline | 201.880 ms | 163.160 ms | 214.023 ms |
| KQ1 resolve | 252.279 ms | 195.173 ms | 262.261 ms |
| PQ1 outline | 455.451 ms | 372.863 ms | 532.872 ms |
| PQ1 resolve | 684.178 ms | 522.797 ms | 704.150 ms |

Each measured scan includes fresh file reads, hashing, parsing, the selected
stage's analysis and canonical result digests. Each reads nine input files once:
four directories, three volumes, `WORDS.TOK` and `OBJECT`. Reads are snapshots
per file; they are not an atomic filesystem transaction.

Process startup, input preparation, research, report serialization and the
following source-correspondence checks are outside the timing interval. These
numbers measure the implemented census on these inputs and this environment.
There is no matched prior-method baseline, cold-run claim or claimed speedup in
analyst recovery time.

## Backing the outline with source

The verifier expands the retained structural IR after measuring the compact
outline and resolve stages. It checks:

- Every decoded instruction's opcode and operands re-encode the complete original
  bytecode, with no gap or overlap: **37,557 instructions / 182,859 bytes** across
  both games.
- Structural IR identities agree between outline, resolve and expanded output.
  Expanding IR does not change the resolved references.
- Repeated results have identical canonical hashes, and the hashes recompute
  from the returned JSON data.
- All selected source file identities are unchanged before and after verification.
- Source bytes and widths agree with the preserved partial inspector where it
  supports the operation: **4,009 KQ1** and **4,232 PQ1** instructions. Its
  unsupported frontier contains 801 and 724 records respectively; those were
  not used as an oracle or silently counted as agreements.

The byte re-encoding check proves source retention, not the correctness of
recovered semantics. The partial inspector comparison shares some format
knowledge and is not an independent execution reference. No higher-level AGI
representation was executed against an original game in this pass.

Reproduce with qualified private inputs:

```sh
PYTHONPATH=src python scripts/verify_agi_scene_census.py \
  --game kq1=/private/kq1 --game pq1=/private/pq1 \
  --runs 5 --output /private/agi-census-verification.json
```

## Regression and package checks

The change adds authored tests for directory and resource bounds, messages,
vocabulary and inventory, typed references, control-flow joins, indirect writes,
scan entries, volatile variables, budgets, strict options and public JSON hash
preservation. Authored fixtures contain no original game content.

Independent review found four issues that are covered by regressions: the valid
zero-operand false condition, hash-changing native-address normalization,
context-dependent `trace.on` layout, and condition operands escaping an
action-count-only budget. `trace.on` now preserves the whole affected LOGIC as
opaque, and a global code-byte budget bounds expansion including conditions.
Neither supplied game contains `trace.on`.

- Full repository suite: **2,240 passed, 119 skipped** in 145.61 seconds, using
  `PYTHONPATH=src:player python -m pytest -q`. The initial run exposed the exact
  bundled-skill inventory assertion; its expected set now includes the new guide.
  No existing test was removed or weakened.
- Focused AGI/resource/scene/CLI suite: **150 passed** under independent review.
- Core and standalone-player wheels, sdist and tool ZIP build and pass archive
  content policy. The new source modules, tests, guide, report and selected JSON
  evidence are checked against the final source archives.
- Both installed bundled-skill gates pass. An isolated installed core wheel runs
  both census stages on an authored fixture and preserves document/IR hashes.
  The installed standalone player imports and displays help without the core
  package visible.

These are host, source-correspondence and packaging checks. They do not substitute
for the 119 skipped checks or qualify original-game execution. GitHub CI status
belongs to the PR's exact head and is reported there separately.

## Integration and next recovery boundary

The repository's main branch and metadata for all 53 PRs available during this
pass were checked. Code review was selective: AGI support, scene recovery,
edition guidance, Zork work and overlapping current changes. This does not claim
a full code review of every PR. The implementation is independent of unmerged
source-intake and media-adapter work. The shared CLI, bundled-skill inventory and
documentation edits in PRs #51–#53 need ordinary reconciliation if merged first.

The existing `agi-logic` partial inspector, Zork converter, Zork tests and player
are preserved. This branch adds a projectless census, a requirements-first skill
reference and reusable verification; it adds no project schema, native backend,
game asset, AGI UIL executor or generated native program.

The next promotion should cover **one whole interaction**. KQ1's bow-to-king
action is a candidate informed by the
[earlier benchmark](KQ1_ASSISTED_TRAVEL_BENCHMARK.md); PQ1 also has candidates in
the [conditional-navigation report](PQ1_CONDITIONAL_NAVIGATION_FINDING.md).
Bind the exact source and entry phase; include admission, refusal and repeat
branches; name state from writers and consumers; preserve ordered output,
modal work and cycle effects; define the UDL correspondence; then execute the
higher-level candidate against qualified reference checks. Until that boundary
passes, all scene ingredients and unknown behavior remain explicitly low-level
source structure.
