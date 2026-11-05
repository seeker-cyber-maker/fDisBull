# Deterministic pipeline orchestration: software vs agent responsibility audit

**Date:** 2026-11-03  
**Base examined:** fDisBull 0.30.0 main `2866c414bff33510ab58e3186f96960eddd0cb94`, plus draft [!57](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/57), [!58](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/58), [!60](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/60), [!61](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/61), [!62](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/62), [!63](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/63).  
**Kind:** Assessment and proposed architecture/acceptance criteria. **No new production scheduler, code implementation or native acceptance results are asserted here.**  
**Related:** [Maturity and gap analysis](RECONSTRUCTION_MATURITY_AUDIT_2026-11-03.md) · [Milestone gates](milestones/2026-11-03-generic-reconstruction-gates.md).

## Decision

The agent must **drive** a predeclared workflow, not carry artifacts across it by manually converting text to JSON, retyping source facts, writing one-off format adapters, repeating certified observations, patching test fixtures to get an output, or announcing success before the requested deliverable is complete. Routine transformation, scheduling, artifact transfer, proof execution, cache lookup, diagnostics and final delivery should be software-owned. An agent should receive compact *exception tickets* for genuinely unresolved meaning, missing specifications, ambiguous hypotheses, and strategic route changes. User approval remains authoritative for protected or externally effectful actions.

Three distinct qualities must not be conflated:

1. **Repeatable orchestration:** identical admitted inputs and recorded decisions produce the same stage calls and dependency ordering.
2. **Deterministic/qualified transformation:** a supported parser/lifter/compiler emits stable output under pinned toolchain and profile; a heuristic proposes candidates with fixed rules but still lacks proof.
3. **Correct interpretation:** the source meaning actually matches the UIL contract and target execution. Replaying a wrong lift consistently does not establish correctness.

Deterministic steps can be software-owned even when they end in an explicit **unknown/refused** result. The machine should detect uncertainty, not hide it.

## 1. Current ownership by stage

**Software-led:** implemented coded operations produce bounded results, though parameter choices or transitions may remain manual.  
**Mixed:** substantial implementation, but the agent must assemble experiments/adapters or move outputs between tools.  
**Agent-led:** repeated interpretation and workflow glue are instructions in skills/notes, without a generic automated implementation.

| Stage | Current | Deterministic machinery already available | Repeated agent load | Recommended change |
|---|---|---|---|---|
| Input discovery / collection | Mixed | Individual format inspection, source hashing, extractors, target storage/attachments | Group editions, choose members, build complete inventory manually; [collection intake](TARGET_COLLECTION_INTAKE.md) says universal importer not implemented | Batch content-addressed manifest + dependency closure, retain unknown members |
| Environment / capability selection | Mixed | `capabilities`, `methods`, doctor, installed skill inventory | Read tool/skill versions and select compatible backend and first route | Explicit capability solver chooses legal profile from goal and local inventory; refusals state missing component |
| Static decoding | Software-led | ISA parsers, CFG traversal, address mapping, source backings | Follow unknown successors, overlay or bank mapping, guess candidate entries | Fixed worklist, deterministic ambiguity inventory, resolved/unresolved provenance |
| Def-use / effect summaries | Agent-led | Low-level facts and selected semantic adapters | Trace last reaching value, flags, aliasing, helper footprint, control/effect closure | Generic bounded backwards slicer, typed summaries, known/unknown may-write sets; safe overapproximation |
| Runtime setup and control | Mixed | DOSBox/Wine-QEMU, save states, scripted bounded probes, trace/watchpoint APIs | Compose probes, select entry states, manage guest/host data and unexpected backend setup | Idempotent runtime-session recipe + snapshot closure + probe templates + bounded scheduler |
| Choosing semantic boundary | Agent-led | Explicit snippets and source mapping, bounded AGI/VM/6502 lifts | Locate meaningful unit, entry/exit, input/output and precondition | Generate candidates by data/effect cuts; agent only resolves unresolved competing interpretations |
| UDL lift | Mixed to agent-led | Narrow ASM/C, VM and 6502 adapters, snippet identity | Author binding/port map and fill gaps across unsupported code | Declarative lifter registry with algorithmic lowering, recorded unsupported residuals |
| UIL composition | Mixed | Typed common UIL validator/runtime, catalog and exact implementation IDs | Convert between profiles, interpret intent, author host-effect model | Conformance-checked adapters; core type/effect semantics fixed; unfamiliar intent stays a candidate |
| Source→UIL validation | Mixed | Z3 and bounded original-model checks | Select oracle and boundary vectors; write independent comparison harness | Original runner + UIL evaluator + normalized observation diff with generated edge/threshold/negative vectors |
| Provider discovery / sweding | Mixed; drafts | Catalog, component locks, [!57]/[!58] bounded registry/swedes | Search availability, invent missing provider, copy proof details | Capability graph resolves exact candidate; generate precise missing-provider ticket; admit only independently checked alternatives |
| UIL→UDC build | Software-led on admitted profile | Source generation, C/asm/JS/Python/Wasm/web/desktop/console profiles, deterministic linking | Work around unsupported services, ABIs or callback ownership | Preflight legalization and build graph; do not rewrite UIL to fit target by omission |
| Target execution/comparison | Mixed | Native runs, serializations, checked output manifests, test fixtures | Transfer input fixtures, compare state/events, decide qualification | One differential runner for original/model/output; attach precise first-divergence receipt |
| Optimization feedback | Prototype | Existing copy pruning; [!63] draft LLVM pure-u32 fusion/proof | Compose/route optimizer and interpret exceptions | Reversible measured candidate queue, proof/observation gating; never autonomous semantic promotion |
| Packaging, CI and user delivery | Mixed | `check_dist`, GitLab test/package CI, asset SHA; [handoff helper](AGENT_HANDOFF.md); bounded output references | Prepare reports, manually check final deliverable and relay links; native gates manual by policy | Delivery manifest + closure gate + verified accessible artifact/links + exact exclusions; preserve manual native policy |

**Important qualification:** Skills such as [reconstruction](../src/fdisbull/skills/fdisbull-investigate/references/reconstruction.md) and [scene recovery](../src/fdisbull/skills/fdisbull-investigate/references/scene-recovery.md) specify good behavior, but instructions are not implementations. They currently direct the agent to pin evidence, choose probes, author UIL, qualify two edges and hand off. Replacing an instruction with an executable service is the objective.

Existing [debugger scripts](DEBUGGER_SCRIPTS.md) *already* validate and stop on unexpected outcomes, retain partial effects, and avoid guessing click coordinates; retain these semantics in the coordinator. Existing [bounded output](OUTPUT_LIMITS.md) correctly provides immutable references instead of huge replies; the coordinator should consume typed summaries and artifact handles rather than dumping JSON into an LLM.

## 2. The minimal deterministic coordinator

Build **a small local-first, database-backed DAG/state machine** around existing CLI/Python capabilities. Do not start by replacing all implementations or introducing a new game scripting language. An existing SQLite storage foundation is suitable for an initial local coordinator; an external durable workflow service should be optional, not prerequisite.

Suggested new components are **proposed names, not existing APIs**:

- `GoalSpec`: exact source identity, requested semantic/UDC outcome, fidelity/observation scope, target profile, authorized side effects, required final artifacts, test requirements, resource/time/token budgets.
- `StageSpec`: deterministic operation and version, prerequisites, declared input/output schemas, read/write/resource effects, admission and refusal rules.
- `StageReceipt`: source/model/provider/host hashes, executed tool and status, observed outputs, coverage, proof/validation references, budget frontier, unknowns, cache identity, next eligible stages.
- `ExceptionTicket`: single minimal blocker, exact source span/boundary, competing hypotheses, already tried probes, small reproduced counterexample, proposed next tests, permitted agent actions and retry ceiling.
- `DeliveryReceipt`: all requested outputs available and checked, independent required runtime gates, exact links or paths, missing work and explicit truthful partial completion.

Proposed lifecycle:
 
`queued → ready → running → {qualified, partially_qualified, refused, blocked, failed} → downstream readiness → {delivered, partial_delivery, blocked_delivery}`

The *claim qualification* of a node and its *workflow completion* are separate axes. A solver's `unknown` is not `qualified`; an artifact being emitted is not `delivered`. An entire run can finish its analysis pass with unresolved findings while the requested reconstruction remains incomplete.

A coordinator should:

1. Freeze the source, supported profile, original oracle and obligations; build the dependency DAG and required delivery checklist **before** executing probes.
2. Find a still-valid cached receipt for each ready stage using **all transitive dependencies**, not just source SHA.
3. Run admitted deterministic tasks with stable ordering, bounded budgets and explicit resource leases (one owner per mutable guest, repository branch or state).
4. On expected success, pass structured outputs to the next stage **without agent interpretation**.
5. On a known refusal, stop that branch and expose the exact unavailable capability; continue independent supported branches.
6. On an ambiguous result, create one compact exception ticket; route to agent only if a decision can unblock the run.
7. Validate any agent-proposed binding, probe or source patch against the same strict gates. Generative text is never granted execution/proof authority by itself.
8. Resume from the last valid stage, not from intake. Do not rerun a partially effectful activity without explicit idempotence/compensation evidence.
9. Produce complete, verifiable output artifacts and a delivery receipt only when the original requested closure is satisfied.

External precedent: [Temporal deterministic workflow execution](https://docs.temporal.io/workflow-definition) keeps non-deterministic I/O/LLM actions outside its replay path, recording outcomes as activities. Apply the principle without requiring Temporal infrastructure. [MLIR dialect conversion](https://mlir.llvm.org/docs/DialectConversion/) exposes analysis/partial/full conversion and legality checks, useful for explicit UIL→UDC admission.

## 3. What the agent should do

Agent involvement is appropriate for **new hypotheses**, **discriminating uncertain meaning**, **unrecognized interpreter conventions**, **novel host-effect models**, **missing semantic definitions** and **choosing a route around a genuine blockade**. It should not be used for deterministic file-manifesting, known decoder loops, copy/paste JSON adapters, source/result hashing, solver runs, baseline comparisons, status polling or artifact upload.

Require an exception packet that answers four questions: **What exact fact remains unknown? What has already been proven? Which small observation would distinguish the alternatives? What changes if we choose a candidate?** Never ask the agent to reconstruct the entire analysis transcript from scratch.

The agent should respond with a structured proposal: `choose_probe`, `bind_candidate`, `implement_missing_provider`, `narrow_claim`, `request_user_approval`, or `declare_blocked`. If the agent authors new code, it is an isolated candidate with tests and provenance, not silent modification of production rules. Every answer passes software validation and remains reversible.

A conservative attempt policy: deterministic fixes/retries for known transient failures; one or two bounded discriminating probes for an ambiguity; escalate or park after a finite ceiling. An unknown static edge must not trigger an unbounded sampling or hallucination loop. Parsing and computation should be performed once and reused at equal scope.

## 4. Cache three different kinds of information

The current [scene recovery guide](../src/fdisbull/skills/fdisbull-investigate/references/scene-recovery.md) already distinguishes these, but they should become core services:

1. **Definition cache:** parsed resources, decoded instructions, file/ROM/VM address relations. Keys include exact source, decoder, profile and resource dependencies.
2. **Semantic qualification cache:** recovered block contracts, pure helper summaries, proof receipts and assumptions. Keys include typed ports, effect boundary, solver/runtime versions and the complete transitive dependency graph.
3. **Observation cache:** specific original execution states, inputs, clocks, device/file snapshots and outcomes. Keys include exact original/backend/source, checkpoint and observation scope. Historical observation is never live readiness.

Changing a display color should not invalidate a proven arithmetic kernel. Changing the calling ABI, backing bytes or aliasing model must invalidate its dependent semantics and realizations. Replaying a qualified action in a different native guest still requires an appropriate current runtime receipt.

## 5. The last-mile/delivery gate

Define the **end-user deliverable first**. “Analyzed successfully”, “compiler returned zero”, “tests passed” and “provided a branch” are possible intermediate achievements, not automatically completion.

A run requesting a usable transformed program must prove, at its declared scope:

- complete source/model/output identity and required generated files;
- exact source→UIL qualification and selected UIL→target comparison;
- required runtime bootstrap/input/output/side-effect route tested, or explicitly blocked;
- artifacts reopen and execute in a fresh permitted environment, without hidden local interpreter/source files unless declared;
- build/readback/hashes and a valid delivery path or download URL; report missing native or user-side installation gates honestly;
- a concise final result saying **delivered**, **partial but useful**, or **blocked**, with the outstanding obligations and evidence IDs.

Never mark a task done because the last invoked tool exited cleanly. **Acceptance belongs to the requested goal, not the last stage.** A successful source study that leaves no usable output is still a partial user request.

The [agent handoff script](AGENT_HANDOFF.md) is already a specialized implementation of verified MR handoff; generalize its *receipt* concept, not its GitLab coupling, to exports, emulator bundles, native binaries, test logs and release packages.

## 6. Prioritized implementation work

| Order | Implementable project deliverable | Acceptance proving agent work disappeared |
|---|---|---|
| P0-A | Run/goal ledger and deterministic stage DAG | One declared goal executes intake→known recovery→validation→existing UDC build→delivery with no intermediate agent prompt; interruption resumes from last accepted stage |
| P0-B | Typed stage adapters over **existing APIs** | No agent copies source facts, receipts, typed values or output artifacts between the selected core stages; mismatched schemas produce a bounded adapter error |
| P0-C | Qualification closure + differential runner | Original→UIL, UIL→UDC and composed state/effects produce independent same-input receipts; wrong guard, width, alias and missing effect are caught |
| P0-D | Exception routing / bounded agent tickets | Unsupported opcode, ambiguous branch or missing provider yields minimal source-bound ticket; cold agent never needs to reread entire repo/history to proceed |
| P0-E | Last-mile delivery manager | Emitted-but-unrun, failed runtime, inaccessible artifact, missing package, or unverified install never reports delivered; a fresh-user smoke passes on an accepted output |
| P1-A | Generic backwards data/effect slicing with helper cache | Automatically propose ports and effect closures for three held-out source families with recorded unknowns rather than manual tracing |
| P1-B | Registry and swede orchestration using !57/!58 | Exact reuse before synthesis; new candidates independently qualified, persisted and selected through the same resolver |
| P1-C | Auto-generated original/model/target probes | Boundary, branch, overflow/refusal and negative controls generated from contracts; oracle remains independently original-backed |
| P2 | Optimization feedback and measured provider selection | Pure → branch → memory/effect profiles admitted incrementally; original semantics remain immutable and every improvement reversible |

Start **P0-A through P0-E** before increasing ISA support. The cheap path is wrapping existing working capabilities in a reliable coordinator, not spending months building a novel compiler.

## 7. Required regression scenarios

| Scenario | Software behavior | Agent behavior |
|---|---|---|
| Supported authored DOS/CHIP-8 test with known contracts | Entire selected run, including independent tests and requested artifact, reaches declared closure with no intermediate agent prompts | None beyond initial goal |
| Unknown opcode or indirect branch | Emit one exact unknown frontier and affected claims; continue independent work; no guessed no-op | Decide next focused test or leave bounded residual |
| Wrong recovered guard, signedness or omitted write | Differential/proof mismatch blocks qualification and retains counterexample | Inspect smallest divergence, propose repair |
| Unknown effect after partial mutation | Do **not** rerun original action automatically; preserve committed state/effects | Approve recovery experiment or request user policy |
| Compiler supports scalar but not required file effect | Preflight refuses full target and identifies service/version gap | Decide target change or implement service, never erase required effect |
| Existing qualified result unchanged | Reuse receipt and provider; no source reparse/retest outside changed dependencies | None |
| End-to-end output built but not executable in intended host | `partial_delivery` with missing native runtime gate, not `delivered` | Plan qualification or request environment access |
| Lotus 1-2-3 workflow | Repeatable original-backed edit/formula/recalculation/save/load tests against independently emitted target | Only investigate edition-specific unknown numeric/command behavior |

## 8. Measure token savings without pretending to have a baseline

No credible current “X% deterministic” or “Y% token saving” can be derived from code count or test count. **Instrument first.** Capture per-run:

- agent invocations and **tokens in/out by stage**; deterministic stage CPU/wall time and I/O;
- count of transitions handled without a model; manual data-conversion or script-writing actions; repeated probes;
- exact cache hits/revalidations and their transitive evidence IDs;
- error classification, counterexamples, agent interventions, user rescues and false “done” reports;
- time and cost to **requested deliverable**, not merely first working slice;
- unresolved/unsupported denominator alongside qualified coverage.

Suggested *design target*, not current observed result: **at least 90% of ordinary handoffs should require zero LLM calls**, with agents disproportionately focused on **new unknown semantics**. Set quantitative token/cost reduction targets after a paired baseline-versus-coordinator benchmark at equal source, output scope and verification quality.

**Operational principle:** A useful agent is a skilled driver with a map, not a person forced to unload the truck at every junction and carry its cargo by hand. Software owns the road, cargo handling, proof/checkpoints and delivery dock.
