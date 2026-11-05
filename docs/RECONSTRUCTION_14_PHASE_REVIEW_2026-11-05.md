# fDisBull: 14-stage UDL → UIL → UDC review worksheet

**Created:** 2026-11-05  
**Status:** Discussion worksheet, not an implementation, approved specification, release claim, or completed review.  
**Target:** Post-0.32 architectural prioritization. No change to the frozen 0.32 release candidate.  
**Source:** [Deterministic pipeline orchestration audit (November 3)](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/codex/integration-0.32-prs-20261104/docs/DETERMINISTIC_PIPELINE_ORCHESTRATION_AUDIT_2026-11-03.md) and [maturity audit](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/codex/integration-0.32-prs-20261104/docs/RECONSTRUCTION_MATURITY_AUDIT_2026-11-03.md). The source currently resides in the 0.32 integration branch; this worksheet does not assert those source documents have landed on main.

## Purpose

Review the **14 responsibility/stage rows** of the audit with TiGa, record design decisions, identify reusable software to replace agent glue, and turn approved decisions into independently testable acceptance criteria. These are not necessarily 14 strictly sequential runtime phases; feedback and qualification can loop or overlap.

For each phase, capture: (1) existing code/evidence, (2) intended software vs agent ownership, (3) supported/unsupported cases, (4) qualification gate and minimum usable deliverable, (5) dependencies/priority, and (6) decision and rationale. A draft note is not an accepted decision.

## Fourteen-phase map

| # | Phase (as described in audit) | Audit assessment | Main gap to review |
|---:|---|---|---|
| 1 | Input discovery / collection | Mixed | Batch content-addressed intake, edition/dependency closure and retained unknowns |
| 2 | Environment / capability selection | Mixed | Select legal backend/profile from actual installed capabilities, without agent guesswork |
| 3 | Static decoding | Software-led | Deterministic ambiguous-entry inventory, unknown indirect edges, and safe resume |
| 4 | Def-use / effect summaries | Agent-led | Generic backward slicing, typed live-in/out, memory aliases, flags, and may-write summaries |
| 5 | Runtime setup and control | Mixed | Idempotent session recipes, stable snapshots, probe templates, and exclusive ownership |
| 6 | Choosing semantic boundary | Agent-led | Algorithmic candidate cuts that identify a meaningful, testable operation |
| 7 | UDL lift | Mixed to agent-led | Declarative lifter registry and visible unsupported residuals, not custom one-off adapters |
| 8 | UIL composition | Mixed | Canonical type/effect semantics and loss/refusal checked bridges between UIL profiles |
| 9 | Source → UIL validation | Mixed | Differential original/model runner with independent oracles and negative cases |
| 10 | Provider discovery / sweding | Mixed; drafts | Qualified reusable block catalog, missing-provider tickets, cold worker synthesis |
| 11 | UIL → UDC build | Software-led on admitted profiles | Legalization, dependency/build graph, exact target support and explicit refusals |
| 12 | Target execution / comparison | Mixed | Repeatable original/model/output differential comparison and first-divergence receipts |
| 13 | Optimization feedback | Prototype | Reversible proof-checked, measured candidates; never promote changed semantics by intuition |
| 14 | Packaging, CI, and user delivery | Mixed | Verified closure manifest, source/artifact IDs, accessible deliverables, privacy and native gates |

## Discussion prompts and provisional exit tests

**1. Input discovery / collection**  
Decision pending. Should the default input be an executable, installer, disc image, folder or all of them? Proposed gate: one command inventories a supported collection, hashes sources, links resources/editions, and reports unknown files without fabricating relationships.  
**Notes:** _To discuss._

**2. Environment / capability selection**  
Decision pending. Where do host constraints, retained tools and runtime variants live? Proposed gate: a goal and environment inventory deterministically select an admitted route or give exact missing requirements, without running unapproved binaries.  
**Notes:** _To discuss._

**3. Static decoding**  
Decision pending. How much uncertain code-discovery work should be auto-queued? Proposed gate: repeatable worklists preserve overlapping interpretations and undecidable indirect edges; interruption/resume reproduces identities and frontier.  
**Notes:** _To discuss._

**4. Def-use / effect summaries**  
Decision pending. This is one likely high-value bottleneck. Proposed gate: a general analysis recovers admitted live-ins, live-outs, flags, alias sets, and conservative external effects on held-out examples; unsupported effects stay unknown.  
**Notes:** _To discuss._

**5. Runtime setup and control**  
Decision pending. Proposed gate: pinned source/backend/host identities, clean launch, controlled input, checkpoint and restart with explicit differences between guest and external host state. Exclusive session lease prevents multiple controllers interfering.  
**Notes:** _To discuss._

**6. Choosing semantic boundary**  
Decision pending. How do we define a useful operation without naming the game? Proposed gate: candidate boundaries from data/effect cuts on an unfamiliar target; wrong boundaries produce measurable counterexamples, not silent acceptance.  
**Notes:** _To discuss._

**7. UDL lift**  
Decision pending. Proposed gate: a reusable source-backed lift emits typed ports, state/effects and unsupported residuals; a second unrelated source can reuse the same registry and gate.  
**Notes:** _To discuss._

**8. UIL composition**  
Decision pending. Proposed gate: core semantics plus explicit bridges for legacy/common/memory/record/Z profiles, with order, ownership, width and unknown/refusal rules retained. Two independent consumers pass shared conformance cases.  
**Notes:** _To discuss._

**9. Source → UIL validation**  
Decision pending. Proposed gate: compare original observation with independently interpreted UIL, report the first divergence, and include boundary, reset, negative and refusal probes. Agreement between two authored models alone is insufficient.  
**Notes:** _To discuss._

**10. Provider discovery / sweding**  
Decision pending. Proposed gate: discover and reuse a source-independent block when available; when absent, issue a bounded synthesis ticket for a fresh agent and independently qualify any produced provider. Exercise 1-, 2- and 3-block graphs with a stateful effect.  
**Notes:** _To discuss._

**11. UIL → UDC build**  
Decision pending. Proposed gate: a target-capability preflight either emits a complete admitted realization with pinned dependency graph or refuses with missing constructs. No hidden deletion of callbacks, effects, or state.  
**Notes:** _To discuss._

**12. Target execution / comparison**  
Decision pending. Proposed gate: run original, UIL and target realization against matched inputs, compare ordered observations and persistence separately, and retain first-difference evidence.  
**Notes:** _To discuss._

**13. Optimization feedback**  
Decision pending. Proposed gate: source-qualified baseline, proven or independently checked candidate meaning, measured cost on target, provenance, bounded loop and opt-in reversible selection.  
**Notes:** _To discuss._

**14. Packaging, CI, and user delivery**  
Decision pending. Proposed gate: one delivery receipt identifies tested source, built artifacts, exclusions, privacy checks, actual binary download/install/run and blocked native tests. An upload is not a completed delivery.  
**Notes:** _To discuss._

## Cross-cutting questions

- Should the workflow coordinator be a small local-first SQLite-backed DAG/state machine, with agent involvement only for ambiguous meaning and genuine exceptions? This is the audit's recommendation, **not yet an approved architectural decision**.
- Which two unrelated held-out programs will prove reuse without game-specific core conditionals?
- Which receipts can be cached under transitive source/semantic/provider/host dependencies?
- Do we set a stop rule against adding more decoders or engines until one bounded source→UIL→UDC operation achieves independent G5 acceptance?
- How do we count unknown/refused and untested operations as denominators, rather than citing only passing tests?

## Decisions ledger

| Phase | Decision | Rationale | Owner | Acceptance evidence | Status |
|---|---|---|---|---|---|
| 1–14 | No choices reviewed with user yet. | Worksheet opened for collaborative review. | Pending | Pending | **Unreviewed** |

## Change and release boundaries

This documentation-only worksheet contains **no software implementation** and claims **no new runtime qualification**. Keep it as a draft MR while discussing. Do not automatically merge into the frozen 0.32 release branch. Changes to the fourteen phase descriptions, notes, accepted decisions and acceptance tests should be made on this worksheet branch with a clear commit history.

Source and context: [0.32 integration MR !95](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/95), [0.32 release MR !78](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/78), [14-stage audit](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/codex/integration-0.32-prs-20261104/docs/DETERMINISTIC_PIPELINE_ORCHESTRATION_AUDIT_2026-11-03.md).
