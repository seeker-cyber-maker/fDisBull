# PR delivery and remaining work

This is a requirements audit for the 0.25.0 integration, using current source
and the GitHub PR/comment snapshot taken on 2026-10-30 UTC. A PR's lifecycle and
its technical requirements are separate: a closed documentation proposal may
be incorporated while some of its proposed capabilities remain future work.
Historical game reports establish what their authors observed, not a fresh
qualification of the current build.

## Highest-value remaining seams

| Priority | Requirement | What exists | What remains |
| --- | --- | --- | --- |
| High | REP watchpoint completion, [#15](https://github.com/seeker-cyber-maker/fDisBull/pull/15) F9 | DOS watchpoints and raw register/stop records. | The generic normalization currently labels a watch as after-instruction/completed. A historical multiword REP report contradicts that blanket interpretation. Add authored partial/full-repeat native cases and conservative partial/unknown metadata. This audit corroborates the source mismatch; it is not a fresh native reproduction. |
| High | Persistent runtime-resource authority, [#6](https://github.com/seeker-cyber-maker/fDisBull/pull/6) | Runtime observations and the retained PQ1 finding. | Hash-bound resource transformations, resolver-backed identities, dependency invalidation and restoration across runs. A bounded memory read is not this resource layer. |
| High | Conditional semantic observation, [#8](https://github.com/seeker-cyber-maker/fDisBull/pull/8) | Bounded observations, conditions, navigation helpers and retained finding. | A reusable resolver-backed semantic watch and its native qualification. |
| High | Complete intent/projection acceptance, [#13](https://github.com/seeker-cyber-maker/fDisBull/pull/13), [#14](https://github.com/seeker-cyber-maker/fDisBull/pull/14), [#17](https://github.com/seeker-cyber-maker/fDisBull/pull/17) | Original-backed UDC, authored Z scenes, retained Zork IR and a bounded recovered intent. | General event/queue ordering, partial cancellation, persistence domains, resource closure, independent-consumer and matched graphics/text acceptance, revision requalification and general translators. |
| Medium | Linked interface schema, [#7](https://github.com/seeker-cyber-maker/fDisBull/pull/7) | Named scenes, targets, conditions and guidance. | Canonical linked event/control/context identities, intake and conformance rules for focus, readiness, modals and completion. |
| Medium | General proof adapters, [#11](https://github.com/seeker-cyber-maker/fDisBull/pull/11) | Narrow arithmetic, readiness and guarded-transition proof builders. | World/containment/geometry/movement/trace families and their proposed scenarios. Preserve unknown and bind every proof to its source, assumptions and observation boundary. |
| Medium | Scene recovery acceptance/cache, [#20](https://github.com/seeker-cyber-maker/fDisBull/pull/20) | Incorporated minimum-proof guidance, authored representation benchmark and safe aggregate receipts. | General resource adapters, source-effect slicing, helper summaries, dependency-qualified acceptance reuse and scene-streaming acceptance. The benchmark is not an automatic recovery engine. |
| Medium | KQ1 assisted travel qualification, [#16](https://github.com/seeker-cyber-maker/fDisBull/pull/16) | Geometry, physical/assisted/story policies and prior limited trials. | Edition-bound footprints, safe landings, separate memory/render/exit/range witnesses, neutral input, failed-attempt captures and a frozen paired benchmark. The historical small sample is not full acceptance. |

The first item is an interpretation risk when a watch stops during a repeated
instruction. Inspect the raw stop, registers and remaining repeat count; do not
infer that the whole repeated instruction completed from the normalized label.

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

## New work outside this intake

[Draft PR #28](https://github.com/seeker-cyber-maker/fDisBull/pull/28), head
`bfcdfe8eb5a030cb6f0e917067690fe2f7e4d03c`, appeared during integration. It is
stacked on #24 and proposes a bounded static Z-machine v3 processor/analyzer.
It is pending a separate review and combined qualification; it is not included
in 0.25. Its analyzer work must remain distinct from higher-level game-intent
recovery. Later amendments to the selected PRs also require fresh review rather
than silently changing a frozen verification target.

This document records technical disposition, not an instruction to close open
PRs or a claim that a future release has been published. Read the current GitHub
state when deciding lifecycle actions.
