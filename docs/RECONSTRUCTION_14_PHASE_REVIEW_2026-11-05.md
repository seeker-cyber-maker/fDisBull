# fDisBull: 14-stage UDL → UIL → UDC review worksheet

**Created:** 2026-11-05  
**Status:** Discussion worksheet, not an implementation, approved specification, release claim, or completed review.  
**Target:** Post-0.32 architectural prioritization. No change to the frozen 0.32 release candidate.  
**Source:** [Deterministic pipeline orchestration audit (November 3)](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/codex/integration-0.32-prs-20261104/docs/DETERMINISTIC_PIPELINE_ORCHESTRATION_AUDIT_2026-11-03.md) and [maturity audit](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/codex/integration-0.32-prs-20261104/docs/RECONSTRUCTION_MATURITY_AUDIT_2026-11-03.md). The source currently resides in the 0.32 integration branch; this worksheet does not assert those source documents have landed on main.

## Purpose

Review the **14 responsibility/stage rows** of the audit with TiGa, record design decisions, identify reusable software to replace agent glue, and turn approved decisions into independently testable acceptance criteria. These are not necessarily 14 strictly sequential runtime phases; feedback and qualification can loop or overlap.

For each phase, capture: (1) existing code/evidence, (2) intended software vs agent ownership, (3) supported/unsupported cases, (4) qualification gate and minimum usable deliverable, (5) dependencies/priority, and (6) decision and rationale. A draft note is not an accepted decision.

## Provisional phase alignment and Phase 0 intake specification (2026-11-05 discussion)

**User direction from voice review:** The source audit's 14 entries are engineering responsibilities, not necessarily the right user-facing phase boundaries or count. Separate **Phase 0: Intake** and **Phase 1: Goal setting / brainstorming**. Phase 0 inspects what was supplied and what this instance can do *before* asking the user to choose an analysis objective. Phase 1 should use a brainstorm skill or equivalent structured conversation, grounded in the actual intake findings, so the user and agent do not commit hours to an incorrect or infeasible interpretation of the request. Later sequencing and total phase count remain open for review; do not mechanically add one to all fourteen audit categories.

### Phase 0: Intake and feasibility dossier (provisional detailed design)

**Entry:** Any explicitly supplied file(s) or directory/collection, including an executable, installer, CD/disk/ROM image, resource-only package, archive, project manifest, or an opaque unknown file. A single binary is *sufficient to start*, but it is not sufficient to guarantee a runnable or reconstructable program.

**Mandatory read-only observations, at bounded cost:**

1. **Artifact identity and provenance:** original filename/path within selected collection, size, complete SHA-256 or explicitly partial fingerprint, read extent, opened-descriptor identity, source/carrier/member transformation chain, alternate identical revisions if locally established. Attribution, version labels, copyright/rights and provenance that cannot be proven from bytes remain *user-supplied/unverified/unknown*, not inferred facts.
2. **Container / related member inventory:** distinguish outer installer, compression/archive/filesystem, executable image, bytecode/VM program, resource/media and documentation; enumerate safely within explicit size/depth/read limits; keep internal relative paths and nested dependencies. Detect encryption/password need, missing members, unsupported formats and incomplete inspection; don't execute an installer just to extract files.
3. **Executable and platform facts:** recognized format and validation level (e.g. DOS MZ/COM when explicitly selected, PE, NE, LE, ELF, Mach-O, console ROM, Z-machine story); native/guest architecture, ISA, bits, byte order, CPU mode, OS/loader/ABI candidates, declared entry points, segments/sections, permissions, relocation/import/export/symbol tables, overlays and mapped/tail data. Do **not** infer a language, full runtime, correctness, or reachability solely from a file extension or magic bytes.
4. **Static dependency and execution prerequisites:** declared linked libraries, interpreters/VMs, DOS extenders, runtime engines, firmware/BIOS, DLLs, data/asset files, saves and configuration, expected environment and device/system calls where visible. Separate *declared*, *inferred*, *missing*, *observed*, and *not yet checked* dependencies. A dependency not declared in an import table may still exist.
5. **Useful accompanying evidence:** installation tree, game/application data, resource archives, manuals, documentation, version/patch notes, sample inputs and outputs, save files, captured traces, debug symbols, source code, SDK headers and legally supplied reference implementations or prior verified findings. These improve coverage but are not all mandatory. Never treat an archive README or unknown document as executable instructions.
6. **Visible interface and risks:** bounded strings, resource listings, exported API or protocol clues, command-line/help/known file types, packing/obfuscation/compression indicators, suspicious privileges or network/device requirements. These are *hints*, not proven behavior. No deep decompilation or reverse-engineering sweep in Phase 0.
7. **Local resource inventory:** selected fDisBull binary/source fingerprint and version; actual installed decoder/format readers, interpreters, debuggers, emulators, solvers, compiler, platform, architecture, memory/CPU/storage limits and missing dependencies. Keep source implementation, component availability, and **native runtime qualification** separate. Do not substitute a released version label or another worker's receipt for this runtime's capabilities.
8. **Unknowns, hazards, and safe next paths:** unresolved formats, damaged/truncated inputs, missing protected game files, anti-debug/DRM concerns, potentially unsafe execution, archive bombs or sandbox/rights restrictions, absent reference oracle. Keep evidence offsets and observed/assumed provenance, exact failure reasons, and missing-precondition tickets. Do not execute untrusted inputs, access network, write to source, patch binaries, or launch guests by default.

**Phase 0 output:** a compact, machine-readable and human-readable **Intake/Feasibility Dossier**. For each supplied artifact it records source and member identities, format/architecture and confidence, potential and known dependencies, preservation/limits, actual installed tooling, and explicit unknowns. For each *broad* type of later goal (static inspection, original runtime debugging, behavioral extraction, source→UDL/UIL, source-independent UDC, complete application reproduction), include one of **admitted on known profile / conditionally possible / blocked by known prerequisite / unknown until more evidence**, with the exact reason and *no unsupported promise*. A host-specific blocker is not proof a task is universally impossible.

**Efficiency and guardrails:** enumerate and recognize before analyzing; compute full hashes only when within allowed cost/budget (otherwise mark partial and postpone authoritative identity); cache by exact source, reader and environment identities; make one bounded deterministic preflight of the supplied collection; output small summaries with links to private evidence. A documented unknown is a successful intake outcome, not a silent pass or fabricated binary classification.

**Existing fDisBull machinery to reuse (integration branch, not necessarily the installed 0.31.1 kit):** `intake-inventory` and `TARGET_COLLECTION_INTAKE.md` for source/member enumeration and recovery queue; `file-identify`, `format-modules` and `FILE_FORMAT_REGISTRY.md` for bounded header/module knowledge; `identify` / `inspect` for selected image properties; `capabilities` for non-executing installed dependency/provider discovery. The **proposed new work is composing these into one first-class feasibility result**, not rewriting every parser.

**Suggested acceptance gate:** On an authored supported executable, a headerless COM case, an archive containing an executable plus resources, a partially missing resource set, and an unknown/unsupported binary, Phase 0 returns a reproducible provenance-bound dossier. All unsupported/unknown states remain explicit; no binaries run, source bytes mutate, or unapproved deep analysis starts. A fresh agent can use its output to ask relevant goal questions and identify when a requested goal needs files/backends not currently available.

### Phase 1: Goal setting and brainstorming (provisional)

**Input:** Phase 0 dossier, the user's stated task (if any), available brainstorm-style skills and applicable safety/authority rules. Brainstorming should surface plausible tasks based on the *actual* program and capability evidence, rather than presenting a generic menu of every fDisBull feature.

**Output:** a confirmed **GoalSpec** defining desired outcome (e.g., characterize, debug, extract mechanics, translate one block, port a bounded application slice), observable scope/fidelity, acceptable approximations, source/target editions, final reusable artifacts, independent original/model/output acceptance evidence, constraints/budgets, and allowed side effects. Explain infeasible or conditional routes and offer a narrower valid experiment before expensive execution. User consultation happens **here**, not during basic file inventory; retain decisions to avoid circular re-questioning. No consent or approval is inferred from an uploaded binary alone.

**Handoff:** Phase 0 says **what is present and could be attempted**; Phase 1 determines **what the user actually wants and what counts as done**; the subsequent route planner selects exact decoders, backends, proof oracles and execution stages. Do not start hours of generic analysis before those gates.

### Phase 2: Research-first reconnaissance and implementation-route selection (provisional)

**Candidate new gate, motivated by the Sherlock 1.50 case:** Once the user has chosen a goal in Phase 1, perform **targeted, bounded prior-art research before substantial binary recovery, custom engine development, UI recreation or deep emulator work**. The original fourteen rows omit this as a distinct control point, although the existing investigation skill already recommends research-first behavior. The failure mode is **not necessarily a missing instruction**; it is a checkpoint that agents can skip.

**Sherlock evidence:** [draft !97](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/97) reports that the team used fDisBull 0.31.1 for authentic DOS execution/captures and some independently checked semantic witnesses. However, it also wrote a custom unpacker, Unicorn harness, C puzzle engine and AppKit host without first looking for relevant prior reconstruction/ports. The user later supplied [Watson](https://github.com/koro-xx/Watson/releases); review of its pinned source revealed puzzle-relation logic, hint/board code and a Mac build approach that would have been useful to evaluate **before** building. Watson was **not built or executed** in that work, and its edition, numbered-puzzle behavior, license (GPLv3) and assets require separate qualification. No evidence here supports claiming automatic fDisBull porting or exact Watson equivalence.

**Phase 2 inputs:** P0 intake/feasibility dossier, P1 approved GoalSpec, exact title/edition/source IDs, current known algorithms/languages/engines, and allowed external research sources. If Phase 1 changes the goal, invalidate or rescope the research receipt rather than relying on a generic search performed for a different objective.

**Bounded sequence:**

1. **Search existing evidence:** Repository/code/project catalog, locally retained work and verified prior MRs/lessons; manuals and documentation; reference implementations, open-source ports/reimplementations, format specs, interoperability projects, prior RE papers and community investigations. Search by signatures, engine/format and algorithms as well as by app/game title. Do not assume one public title uniquely identifies the user's edition.
2. **Evaluate actual applicability:** Record URL/repo, pinned version/commit, scope, algorithms/interfaces, runtime/host support, input edition, completeness and whether it was merely located, read, built, executed or independently compared with the user's artifact. Matching a feature or rule is not whole-program equivalence.
3. **Check reuse obligations:** License/attribution/asset ownership, availability, compatibility, safety, provenance, dependency risks and whether public code may be linked, used as an oracle, or only studied as inspiration. Avoid copying private game payloads into public work.
4. **Produce alternatives, not an open-ended rabbit hole:** Choose the smallest qualified route for the accepted goal: reuse or wrap an existing implementation, extend a compatible module/engine, extract only required data, construct a bounded independent model, perform targeted original-binary investigation, or explicitly report the missing capability. Record expected costs, confidence, evidence gaps and the minimum discriminating test for each plausible route.
5. **Exit the checkpoint:** Produce a **Research/Reuse Decision Receipt** that says `searched and matched`, `searched and no suitable match`, `research unavailable/partial` or `requires verification`; cites concrete sources and semantic comparisons; identifies the selected route and independent acceptance obligations; and passes a minimal, goal-specific work plan to the next engineering stage. A failed internet search or brief source skim is not evidence that no prior work exists.

**Cost/ownership:** Automated search and capability catalog lookups may help, but human/agent judgment is needed for semantic fit and legal reuse. Budget search in proportion to expected reimplementation cost. One small bounded reconnaissance pass should precede expensive work, with permission to reopen it when a new discovery materially changes the route. Do not demand an exhaustive web survey for a trivial or completely offline task. A small amount of original-byte identification can be part of Phase 0 to enable the search; substantial decompilation belongs after this checkpoint.

**Proposed acceptance/regression case:** Re-run the Sherlock scenario from a cold agent with the same intake and user goal but without supplying the Watson URL. Before writing a generator/GUI, its research receipt should discover and evaluate Watson or a comparably relevant existing project, and distinguish matching clue logic from unproven version-specific parity. Preserve what fDisBull already provided: source-bound observations, constrained probes, provenance and independent original/model/output comparisons. A second held-out non-game case should check that this is not a named-game hardcoded search rule.

**Open questions:** exact search sources and offline fallback; who signs off on chosen route; whether Phase 2 is a fully independent phase or a gated substage of planning; and how to measure redundant work avoided without requiring perfect external discovery. This **does not yet define the final number or order of all subsequent phases**.

### Disposition and remaining design questions

- **Captured user preference:** Separate Phase 0 intake from Phase 1 goal discussion, with a brainstorm skill informed by first inspecting inputs. Preserve this as a user-originated direction.
- **Proposal, awaiting review:** exact dossier schema, capture budgets, feasibility categories, which missing items block a particular goal, and whether Phase 0 inventory runs tool-only or with a bounded agent explanation pass.
- **Not claimed:** existing fDisBull already emits this unified dossier, has a generic goal parser, or automatically routes every file/host combination.
- **Additional skills:** The user referenced uploaded skills with names ending in “AI”; their exact names, source files and applicability have not yet been verified. Do not declare them integrated until located and reviewed.

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
| Phase 0 / Phase 1 | User direction: separate read-only input/capability intake from subsequent brainstorm-based goal setting. | Avoid choosing an unsupported or wrong objective before analysis; detailed acceptance remains under review. | User + review agent | Proposed dossier and brainstorming contract in this document; no implemented or tested feature claimed. | **Direction captured; specification provisional** |\n| Phase 2 | Candidate: targeted existing-solution research and route-selection checkpoint after agreed goal. | Sherlock !97 documents a missed pre-implementation prior-art search; Watson source was only evaluated afterward. | Review agent + user | Sherlock cold-agent reuse-discovery regression; pinned source/licensing and qualification receipt proposed, not executed. | **Provisional; awaiting discussion** |\n| Original 14 audit categories | Mapping, numbering and phase count pending review. | Original audit rows are responsibility areas, not a proven sequence. | Pending | Pending | **Unreviewed** |

## Change and release boundaries

This documentation-only worksheet contains **no software implementation** and claims **no new runtime qualification**. Keep it as a draft MR while discussing. Do not automatically merge into the frozen 0.32 release branch. Changes to the fourteen phase descriptions, notes, accepted decisions and acceptance tests should be made on this worksheet branch with a clear commit history.

Source and context: [0.32 integration MR !95](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/95), [0.32 release MR !78](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/78), [14-stage audit](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/codex/integration-0.32-prs-20261104/docs/DETERMINISTIC_PIPELINE_ORCHESTRATION_AUDIT_2026-11-03.md).
