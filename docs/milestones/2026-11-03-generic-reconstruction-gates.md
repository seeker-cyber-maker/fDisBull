# Generic UDL → UIL → UDC roadmap: milestone and qualification gates

**Proposed:** 2026-11-03; **baseline:** `main` `2866c414bff33510ab58e3186f96960eddd0cb94` / published `v0.30.0`.  
**Decision records:** [Maturity and gap analysis](../RECONSTRUCTION_MATURITY_AUDIT_2026-11-03.md) · [Deterministic pipeline orchestration audit](../DETERMINISTIC_PIPELINE_ORCHESTRATION_AUDIT_2026-11-03.md).  
**Status:** Proposed development milestones, **not** pre-existing GitLab milestone records or a promise of release dates.

## Core outcome

An unknown program can be mapped from source evidence through an independently verifiable semantic contract and into a selected target realization **without introducing special-case application logic into the common recovery, UIL, UDC or proof engines**. Unsupported behavior remains explicit and executable authority is never inferred from a catalog declaration.

## Claim ladder

| Gate | Qualification | Evidence |
|---|---|---|
| G0 recognized | Format, edition and source hash known | Loader/media receipt |
| G1 recovered | Exact source-backed instruction/data spans and boundaries | Decode/source-map receipt |
| G2 modeled | Typed UDL/UIL behavior, including unknowns and contract domain | Validated semantic model |
| G3 source-qualified | Original execution or independent spec compared with model | First-difference, corpus and proof receipt |
| G4 composed | Connected blocks preserve state, effects and continuations | Composed independent test |
| G5 realized | Generated/selected UDC output actually runs and matches | Build/runtime observation |
| G6 optimized | Alternative proved safe, measured better, reversible | Proof, cost, selection and rollback |
| G7 generalized | Held-out source family and target reuse the mechanism | Reuse/exception report |

The scope of “done” is explicitly declared: a static tool can qualify at G1/G3; a UDC milestone requires G5; an optimizer requires G6; “generic” requires G7.

## Milestones, dependencies and exit criteria

### M0: Trusted baseline and inventory (P0)

**Depends on:** none.  
**Deliver:** automated version/source/provider report; release/tag/build/install status; per-feature evidence claims and CI matrix.

- [ ] Check status of all main and candidate docs against released source, not historical proposals.
- [ ] Qualify source/build/installed backend fingerprints separately.
- [ ] CI report distinguishes passed, failed, skipped, unrun-native and environment-dependent gates.
- [ ] All advertised capabilities link to implementation and a repeatable corresponding gate.
- [ ] Existing issues/MRs grouped by milestone with one evidence owner per feature.

**Exit:** a reviewer can select any advertised feature and identify source revision, exact tested domain, what ran, what was skipped and what is unqualified without asking the author.

### M1: Canonical semantic core and inter-profile bridges (P0)

**Depends on:** M0.  
**Deliver:** versioned core UIL meaning/effects/unknowns and adapter contract for common indexed, legacy, memory, records, VM and Z-world profiles.

- [ ] At least **30** redistributable conformance fixtures across numeric, control, arrays/records, ownership, time, effects and rejection.
- [ ] A loss/refusal descriptor for every profile adapter; no silent deletion of unsupported constructs.
- [ ] Typed integer/wrap/refusal rules and platform float/decimal profiles where required; no unintended widening.
- [ ] Stable semantic IDs separate from source, presentation and ABI selection.
- [ ] Signed-off schema migration/round-trip compatibility for retained fixtures.

**Exit:** two independent consumers agree on all admitted core fixtures, and unsupported cross-profile cases produce reproducible refusals.

### M2: Generic source-backed recovery (P0)

**Depends on:** M1 and M0.  
**Deliver:** reusable block discovery and semantic-port inference across host and guest ISAs, including calls, memory, flags and explicit unknown effects.

- [ ] Recover at least **one effectful operation each** from three different execution models: a conventional native binary, a bytecode/VM target, and a non-game executable.
- [ ] Recovered inputs/outputs, live flags, aliases and external effects bounded by an evidence report.
- [ ] Demonstrate changed-source invalidation and a wrong-boundary counterexample.
- [ ] Hold out specific targets from recognition-rule construction. Count refused and unknown operations.

**Exit:** generic source→UDL/UIL candidate path operates with no named-game conditional in the core; each promoted contract reaches G3 for its declared domain.

### M3: Host effects, state, and clock adapters (P0)

**Depends on:** M1 and M2.  
**Deliver:** explicit file, keyboard/pointer/focus, display, timed-event, callback and persistence contracts.

- [ ] Typed ordered effect requests and acknowledgments, including deferred or partially completed actions.
- [ ] Explicit snapshot, guest time, host time and external-world rollback boundaries.
- [ ] Two host adapters produce identical ordered selected observations for one stateful application operation.
- [ ] Negative tests for focus changes, reordered callbacks, failed save, illegal address and incomplete host service.

**Exit:** no reported successful operation relies on suppressing or guessing a required external effect; source-to-model-to-target event logs agree on tested cases.

### M4: Production reusable block catalog and guided sweding (P1)

**Depends on:** M1-M3.  
**Deliver:** persistent catalog, exact version resolution, missing-provider detection, safe synthesis task intake and measured candidate verification. Integrate lessons from [!57](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/57) and [!58](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/58).

- [ ] Cold workers discover existing block alternatives before generating a new one.
- [ ] Demonstrate **1-, 2- and 3-block** graphs with at least one stateful/effectful fixture, not pure arithmetic alone.
- [ ] Store and reopen exact contract/provider/proof identities; changed backing invalidates dependent selection.
- [ ] Untrusted declarations remain `execution_authorized: false` until independent admission.
- [ ] Separate intentional behavioral variants from observationally equivalent implementations.

**Exit:** no manually assembled registry JSON is needed for these controlled fixtures, and the system refuses unproven candidates.

### M5: General target realization and qualified composition (P1)

**Depends on:** M3, M4.  
**Deliver:** UDC provider obligations, link locks, native/portable host implementations and executable output verification.

- [ ] Realize the same **source-independent** UIL program on **two distinct target families**.
- [ ] Include calls, nontrivial state/array ownership, control flow, host effects and error paths.
- [ ] No target-specific operation name or source-game knowledge appears in the shared core.
- [ ] Report every unavailable target capability before build; host acknowledgments proven by execution rather than source inspection.

**Exit:** G5 on all supported operations of the chosen program, with per-target exact build/runtime receipts and no hidden interpreter or source-backed shortcut unless explicitly selected.

### M6: Verified feedback/superoptimization (P1→P2)

**Depends on:** M2 and M5.  
**Deliver:** production candidate loop based on [!63](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/63): compose → lower → optimize/synthesize → reabstract → prove → measure → optionally select.

- [ ] Preserve original source, UIL child DAG, original default selection and all counterexamples.
- [ ] Pure scalar profile must pass fixed-point/cycle termination and complete bit-vector checks.
- [ ] Add separately admitted flags, branches, memory aliases and ordered effects; refusals remain explicit.
- [ ] Independently compare original source and UIL before trusting optimized candidate, not only a UIL↔UDC round trip.
- [ ] Require measured gains in selected target metrics; node-count reductions alone are insufficient.

**Exit:** at least three distinct optimization classes pass G6 with no unproved automatic promotions; baseline remains recoverable.

### M7: Office application and spreadsheet held-out proof (P1, parallel after M3)

**Depends on:** M2/M3; complete G5 requires M5.  
**Deliver:** a pinned, lawfully supplied DOS Lotus 1-2-3 edition plus a second non-game office-like program (e.g., text editor). No assumption that different Lotus versions are semantically identical.

- [ ] Observe formulas `A1=3; B1=A1*2; C1=B1+5`, then change A1=4; verify C1 transitions from 11 to 13 against **the selected original**.
- [ ] Recover copy/fill relative and absolute reference rules, error/rounding behavior and selected recalc semantics.
- [ ] Reconstruct tested command/focus and save/reload operations, including failure path.
- [ ] Emit and execute at least two non-DOS target realizations of the admitted semantic slice.
- [ ] Report unknown original semantics and edition differences. Gnumeric WK1/WKS import is only a secondary file-format check.

**Exit:** G5 on an observable spreadsheet workflow; the generic engine changed only through reusable declared type/effect capability additions, not application-name switches.

### M8: Blind multi-domain generalization and promotion (P2)

**Depends on:** M5-M7.  
**Deliver:** formal held-out corpus across game/VM/firmware/CLI/spreadsheet/editor, with reusable test runners and an openly reviewable metric protocol.

- [ ] Corpus owners and title/version/format held out from initial semantic-rule design.
- [ ] Three cold starts per selected held-out target; report interventions and local script/agent context.
- [ ] Measure recovered semantic operations / observed operations, target realizability, independently qualified effects, first divergence and unsupported-case denominator.
- [ ] Classify every failure as discovery, semantics, provider, environment, test oracle or evidence gap.
- [ ] Repeat on release artifacts, not only source checkouts; preserve regression and rollback.

**Exit:** reviewers can compare generalization against the prior release and reproduce the claimed supported subset without task-specific hidden context.

## Existing work to route rather than duplicate

- **Merged at latest main:** [!44](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/44), [!45](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/45), [!59](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/59).
- **M0/M1:** [!43](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/43) plus [!49](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/49); [!53](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/53).
- **M2/M3:** [!60](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/60) is Windows preflight, not working PE32/NE original debugger; [!61](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/61) is a corpus/VM pilot, not production semantic lifting.
- **M4:** [!57](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/57)/[!58](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/58) remain registry/sweding drafts.
- **M6:** [!63](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/63) is bounded scalar fusion, not a general optimizing UDC.
- **Release candidate:** [!62](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/62) does not confer shipped status on unmerged source.

## Suggested governance

Each epic/milestone has: owner, exact input sources, required original oracle, target profile, deliverable, cross-domain fixture, admission gate, artifact/evidence identity, and blocker list. Prefer a small issue per milestone gate, separate from implementation MRs. Do not measure progress by number of games or decoders alone.

**This is a proposed plan, not implementation, a new format version, or an executed acceptance result.**
