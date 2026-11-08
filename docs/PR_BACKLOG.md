# PR delivery and remaining work

> **Historical (GitHub-era) record.** This page documents the 0.25/0.26 GitHub-era intake pinned on 2026-10-30 UTC and the legacy PR #1–#29 dispositions. GitLab is the current review surface; the current consolidation and disposition record lives in [PR_BACKLOG_CONSOLIDATION.md](PR_BACKLOG_CONSOLIDATION.md).

The 0.25.0 requirements audit is retained with candidate updates called out
explicitly. The 0.26 development intake was pinned on 2026-10-30 UTC; it is not
a published release or a main-branch merge. A PR's lifecycle and
its technical requirements are separate: a closed documentation proposal may
be incorporated while some of its proposed capabilities remain future work.
Historical game reports establish what their authors observed, not a fresh
qualification of the current build.

The [definitions and contract roadmap](DEFINITIONS_AND_ROADMAP.md) links the
retained proposal texts and historical acceptance ledgers, including #29.
Those documents are proposals or scoped reports, not implementation evidence.

## 0.26 development intake

| Work | Candidate status | Remaining gate / scope |
| --- | --- | --- |
| #26 amendment, `17bc719` | Reviewed production changes and four later lifecycle tests are integrated locally. Confirmed food commits survive pending notice returns; a reachable stopped provider can remain available for explicit checkpoint recovery. | Fresh combined qualification and exact-commit Linux/native CI before promotion. Running/unreachable guests retain the fatal path; generic resurrection and original-intent completion certificates are not added. |
| #28, `bfcdfe8` | Reviewed bounded Z-machine v3 processor/analyzer integrated with current output and GOG methods. Static decoder, legacy IR and intent tests pass. | Separate source inspection only: no guest `.fdb` persistence, native/guest mapping, VM execution or additional game-intent recovery. |
| #15 F9 | A fresh authored native probe reproduced a partial REP with nonzero count while 0.25 reported completed. Candidate normalization reports `after-access` and unknown whole-instruction completion; partial and complete authored copies are tested. | Require both native Linux profiles on the final candidate. Raw stop records remain unchanged; callers qualify their own completion claims. |
| #29 via consolidated #30 | One definitions/roadmap reconciles language, interface, readiness and proof proposals and links feedback ledgers. | Documentation/design fixtures only. R01–R18 and other prospective cases are not implemented by inclusion. Original PRs remain intact. |

See [0.26 scope](RELEASE-0.26.0.md) and
[verification](VERIFICATION-0.26.md). The published/installed version remains
0.25.0. A candidate result is not a release or system update.

## Highest-value remaining seams

| Priority | Requirement | What exists | What remains |
| --- | --- | --- | --- |
| High gate | REP watchpoint completion, [#15](https://github.com/seeker-cyber-maker/fDisBull/pull/15) F9 | The 0.25 mismatch is freshly reproduced; the 0.26 candidate preserves unknown completion after an access, with partial/full native fixtures. | Final exact-commit Linux/native acceptance before promotion. The original 0.25 audit was static corroboration; the newer native reproduction and fix are separately recorded above. |
| High | Persistent runtime-resource authority, [#6](https://github.com/seeker-cyber-maker/fDisBull/pull/6) | Runtime observations and the retained PQ1 finding. | Hash-bound resource transformations, resolver-backed identities, dependency invalidation and restoration across runs. A bounded memory read is not this resource layer. |
| High | Conditional semantic observation, [#8](https://github.com/seeker-cyber-maker/fDisBull/pull/8) | Bounded observations, conditions, navigation helpers and retained finding. | A reusable resolver-backed semantic watch and its native qualification. |
| High | Complete intent/projection acceptance, [#13](https://github.com/seeker-cyber-maker/fDisBull/pull/13), [#14](https://github.com/seeker-cyber-maker/fDisBull/pull/14), [#17](https://github.com/seeker-cyber-maker/fDisBull/pull/17) | Original-backed UDC, authored Z scenes, retained Zork IR and a bounded recovered intent. | General event/queue ordering, partial cancellation, persistence domains, resource closure, independent-consumer and matched graphics/text acceptance, revision requalification and general translators. |
| Medium | Linked interface schema, [#7](https://github.com/seeker-cyber-maker/fDisBull/pull/7) | Named scenes, targets, conditions and guidance. | Canonical linked event/control/context identities, intake and conformance rules for focus, readiness, modals and completion. |
| Medium | General proof adapters, [#11](https://github.com/seeker-cyber-maker/fDisBull/pull/11) | Narrow arithmetic, readiness and guarded-transition proof builders. | World/containment/geometry/movement/trace families and their proposed scenarios. Preserve unknown and bind every proof to its source, assumptions and observation boundary. |
| Medium | Scene recovery acceptance/cache, [#20](https://github.com/seeker-cyber-maker/fDisBull/pull/20) | Incorporated minimum-proof guidance, authored representation benchmark and safe aggregate receipts. | General resource adapters, source-effect slicing, helper summaries, dependency-qualified acceptance reuse and scene-streaming acceptance. The benchmark is not an automatic recovery engine. |
| Medium | KQ1 assisted travel qualification, [#16](https://github.com/seeker-cyber-maker/fDisBull/pull/16) | Geometry, physical/assisted/story policies and prior limited trials. | Edition-bound footprints, safe landings, separate memory/render/exit/range witnesses, neutral input, failed-attempt captures and a frozen paired benchmark. The historical small sample is not full acceptance. |

The first item records an interpretation risk in older completion labels.
Inspect the raw stop, registers and remaining repeat count; do not infer that
the whole repeated instruction completed merely because an access occurred.

## Target-specific continuation requirements

[PR #15](https://github.com/seeker-cyber-maker/fDisBull/pull/15)'s F1–F20 feedback
contains reported corrections, research and future acceptance cases. PR #26
adds a useful bounded DinoPark continuation slice. It does not close the entire
list. Track these independently:

- Native save submission/collisions, separate persistence domains and lossless
  opaque save fields (F1/F4/F5).
- Composed navigation, revision compatibility and requested versus actual
  progress (F7/F8/F10).
- Direct Store exit, seasonal labels, scene-recognition variations, common
  receipts and month-boundary reservations (F15/F17/F18/F19/F20).
- The REP completion distinction above (F9), which is a backend semantic seam
  rather than a DinoPark-only rule.

Use the fresh [0.25 verification scope](VERIFICATION-0.25.md) for what was
actually exercised. A test-only reconciliation branch is not automatically a
native transaction observation. A known notice or a recognized park is not
proof of arbitrary popup handling or complete economic behavior.

## Legacy PR disposition

The closure comments for **#1–#6, #8, #13, #14 and #17** explicitly identify
incorporation through later commits. Their absence from merge ancestry is not
an unexplained loss. Do not reopen them simply to recreate merge history.

| PR | Submitted work / present source | Remaining capability or acceptance |
| --- | --- | --- |
| #1 | Keyboard restore tests incorporated and evolved. | Broad modal restore is not universally qualified by those tests. |
| #2 | Methodology skill and packaging incorporated and expanded. | Current skill has its own installed-package gate; historical testimony retains its original scope. |
| #3 | UIL producer boundary and RFC documents incorporated. | Linked-interface extension remains tracked under #7. |
| #4 | Timed keyboard sampling documentation/tests incorporated. | No universal game-independent timing guarantee. |
| #5 | UI capture-boundary document incorporated; hooks and readiness mechanisms exist. | Automatic readiness inference and every proposed capture-phase case remain unqualified. |
| #6 | PQ1 runtime-resource finding retained. | Persistent resource layer above. |
| #7 | Open interface proposal; related scene mechanisms exist. | Canonical linked grammar and conformance above. |
| #8 | Conditional-navigation finding and guidance incorporated. | Resolver-backed semantic watch above. |
| #9 | Requested/displayed/ready separation and unknown-preserving admission exist. | E43 document and all seven proposed target cases have not been independently qualified as a set. |
| #10 | Macros, movement and geometry have bounded implementations via #12. | Bidirectional semantic world IR and multiple projection-loss axes remain proposed. |
| #11 | Narrow proof foundations exist. | Broader adapters/scenarios above. |
| #12 | Merged movement, readiness, geometry and proof foundations. | Bounded foundations do not imply complete target recovery. |
| #13 | Intent-pipeline architecture incorporated. | General recovery/acceptance above. |
| #14 | Recovery, streaming and text-projection case tables incorporated. | Proposed case tables are not a passing acceptance suite. |
| #15 | Open original-backed game feedback; #19/#26 cover bounded portions. | Track individual findings, including native qualification, rather than closing the whole PR by association. |
| #16 | Open KQ1 assisted benchmark proposal; geometry mechanisms exist. | Paired target acceptance above. |
| #17 | Terminology, authored fixture checks and effect-isolation findings incorporated. | General source adapters, compiler learning and recovery completeness remain separate. |
| #18 | Merged Z scene service and separate player. | Its bounded envelope is not arbitrary scene streaming or recovered game semantics. |
| #19 | Merged original-backed DinoPark provider. | Broader continuation and persistence requirements remain target-specific. |

## 0.25 integration disposition

| PR | Incorporated deliverable | Claim ceiling / future work |
| --- | --- | --- |
| #20 | Recovery design, authored ASM/C benchmark, aggregate evidence. Reconciled with #27's single skill/reference structure. | No generic acceptance cache, automatic scene compiler or native speed claim. |
| #21 | NoCD music-boundary research and failure ledger. | Proposed duration/loop fixes are not implemented or freshly reproduced here. |
| #22 | Synthetic HUD and agent-context design. | Proposed HUD/profile/delta framework and its fourteen acceptance cases remain future work. |
| #23 | Native Inno Setup extraction command, API, safeguards and tests. | Requires `innoextract`; it is not an arbitrary GOG format reader or installer runner. |
| #24 | Qualified Zork IR, independent consumer, bounded semantic intent and explicit partial-effect fault reporting. | Parser, scheduler, autonomous actors and unhandled game actions remain retained IR. Other editions require new qualification. |
| #25 | Static LE object mapping and supported internal fixups. | LX, imports, unsupported fixups, protected-mode runtime selector translation and RTLink/NB02 recovery remain out of scope. |
| #26 | Bounded DinoPark continuation, scene/provenance improvements, journaled batches and shared action continuations. Integration rejects canonical action repeats and false completion of partial intents. | Current providers lack a bound original-intent completion certificate; partial batch steps remain paused. See fresh native scope and individual #15 requirements above. |
| #27 | Expanded, reconciled investigation skill, a separate guide-writing skill, selective routing and installed-package gates. | Guidance about a capability does not implement that capability. External guide descriptions remain attributed where direct retrieval is unavailable. |

## Historical 0.25 intake boundary

[Draft PR #28](https://github.com/seeker-cyber-maker/fDisBull/pull/28), head
`bfcdfe8eb5a030cb6f0e917067690fe2f7e4d03c`, appeared during 0.25 integration. It was
stacked on #24 and proposes a bounded static Z-machine v3 processor/analyzer.
It was not included in 0.25 and is now reviewed for the local 0.26 candidate
above. Its analyzer work remains distinct from higher-level game-intent
recovery. Later amendments to the selected PRs also require fresh review rather
than silently changing a frozen verification target.

[PR #29](https://github.com/seeker-cyber-maker/fDisBull/pull/29) contributes
its draft executable Rosetta contract and sanitized authored-prototype receipts
in the documentation consolidation. Its **R01–R18** cases remain prospective;
neither that evidence nor this documentation implements a generic compiler,
polyglot runtime or visual editor. See the [roadmap](DEFINITIONS_AND_ROADMAP.md)
for the proposed 0.26 sequencing and retained evidence boundaries.

This document records technical disposition, not an instruction to close open
PRs or a claim that a future release has been published. Read the current GitHub
state when deciding lifecycle actions.
