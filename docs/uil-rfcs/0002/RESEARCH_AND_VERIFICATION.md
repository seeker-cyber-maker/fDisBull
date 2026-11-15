# Dependency evidence and hierarchical verification for executable UIL

**REVISION IN PROGRESS. Discussion draft, 30 October 2026.**

Companion to [RFC 0002](../0002-executable-rosetta-contracts.md) and the
[agent-first topology](AGENT_FIRST_TOPOLOGY.md). These are research-informed
requirements, not an integrated verifier or new empirical results.

## 1. Where the supplied ideas fit

| Material | Contribution to the proposed pipeline | Does not establish |
| --- | --- | --- |
| Static definitions, uses and slices | Candidate block boundaries, dependencies, state mappings and patch impact | Runtime reachability, complete alias/call semantics, or game-intent names |
| Context-qualified execution history | Concrete writers, readers, dispatch and path witnesses | All-input behavior or unobserved paths |
| H-Houdini | A method to investigate dependency-directed invariant learning and reuse | A drop-in native/software loop-equivalence verifier |
| Human-LLM teaming study | A reason to measure useful accepted findings and correction work | That every model, expert or multi-agent workflow gains the reported benefits |

Keep this machinery beside the source-backed UDL / UIL contract / UDC
implementation correspondence. Do not insert another mandatory language or
replace executable UDL with learned predicates.

## 2. H-Houdini: applicable architecture, not a ready software adapter

H-Houdini is an ASPLOS 2025 paper. It structures invariant learning around
smaller dependency-directed SMT obligations, including memoization and parallel
work, and combines the results under stated soundness conditions. VeloCT is its
hardware relational-invariant application. BOOM needs expert annotations;
Large/MegaBOOM results use 160 cores. Its headline speedups are not estimates for
fDisBull. [V1, sections 3, 5 and 6]

Proposed application: derive source- and target-state relationships at admitted
block/loop boundaries, then use a hierarchical learner to propose and discharge
supporting predicates. Candidate generation, symbolic checking, source-model
fidelity and composition are separate responsibilities. Start locally with a
small software transition system; only adopt distributed infrastructure after
measuring which obligations justify it. No VeloCT execution or integration was
performed for this revision. [V2]

### Example obligation, authored for this proposal

Compare a source loop walking a stable byte buffer with a target loop indexing a
collection. At aligned loop boundaries a candidate relation is:

```
source_count = target_index
source_pointer = source_base + target_index
source_accumulator = target_sum
0 <= target_index <= length
source_memory[source_base + j] = target_values[j] for 0 <= j < length
```

Admit only valid storage and nonoverflowing index/pointer arithmetic; specify
accumulator arithmetic separately, for example modulo 256. The relevant checks
are:

```
Init(source, target) implies R(source, target)
R and aligned_transition imply R_after
R and matched_exit imply contract_agreement
```

The entry domain must be satisfiable. Positive observations can propose/filter
predicates but cannot replace coverage of all admitted initial states. Specify
what constitutes aligned progress: one abstract step can correspond to several
native steps, and an optimized loop can require a different coupling relation.

An invariant alone is not a termination argument. For a finite loop, a valid
well-founded measure such as length-index can supply a separate obligation.
For perpetual event loops, state the allowed event traces, responsiveness and
scheduler assumptions instead. Conditional termination, refinement and full
trace equivalence must remain distinct results.

Cyclic proof dependencies need a checked joint inductive closure, not acceptance
because worker A assumed B and worker B assumed A. Require initiation, relevant
step closure and the promised observation relation. Solver timeout, unavailable,
unknown, invalid model and vacuous domain are never success. Preserve
counterexamples and the exact model assumptions.

## 3. Raw dataflow facts: separate questions and levels

Binary Ninja exposes SSA variable definition/use queries and possible-value
queries. A definition explains where a value comes from; a possible-value set
constrains what it might be. A version-zero input or merged definition must not
be replaced by an invented single writer. The adapter also needs the instruction
position and whether the query is before or after it. [V3]

Ghidra supplies raw p-code and analyzed p-code. Its simple backward-slice
implementation follows definitions but stops at CALL/CALLIND. Analysis-introduced
MULTIEQUAL and INDIRECT nodes encode merge/indirect effects rather than original
instructions. IDA/Hex-Rays exposes microcode use/definition lists with explicit
may/must distinctions. Preserve these scopes when combining results. [V4, V5]

A proposed common query surface should return data, control, memory and call
relationships with source identities and unresolved dependencies. For example,
a write of the constant true under `if has_key` depends on that guard even if a
value-only slice reaches only the literal. An unknown callee is not a pure
operation, and a possible-value result is not a reaching-definition certificate.

The correspondence graph can hold multiple provider claims. Admission depends
on evidence and the requested contract; not on two providers choosing similar
variable names or agreeing because they share one decoder. Provider frontends
remain optional. No universal SSA-to-UIL adapter is implemented here.

## 4. First/last execution maps with retained causal intervals

The supplied discussion proposes persisting first/last memory touches and
instruction predecessors together with process/base context. Treat that as an
investigation proposal, not an independently benchmarked tool result.

For fDisBull, an event identity should bind source/byte-view revision, run,
restore epoch, sequence, native PC, relevant address space, access kind/width,
value boundary and current resource/object instance. Guest VM identity and
script PC are essential when one native interpreter handler serves many scripts.

Use first/last maps as indexes into bounded ordered events or reproducible
replay intervals. If A writes X, B reads X, C overwrites X, and D reads X, a
first/last summary alone cannot reconstruct both read-from relationships.
Record context generations to distinguish reused addresses, resource reloads,
self-modification and restores. A first/last predecessor summary is likewise
not a complete control-flow trace. Sampling and capture gaps stay explicit.

Observed read-from edges support a particular execution. They do not establish
that unobserved aliasing is impossible. Native and static facts should supplement
one another without exchanging their quantifiers.

## 5. Patch-local qualification and safe reuse

The patch identifies changed backings. Definitions/uses and control effects
identify candidate dependent claims. Native witnesses and symbolic checks then
establish which relationships remain valid. Retain unaffected code and evidence;
recheck unchanged callers when their callees' behavior changes.

A persistent qualification cache needs more than a source hash or predicate
string. Bind the source/resource closure, byte view, backing and adapter
identities, UIL contract, state relation, admitted domain, observable effects,
helper summaries, analysis/model/checker versions and solver policy. Cache hits
are reused qualification, not a new proof run. Changed assumptions invalidate
connected results. Evidence validation policy must itself remain explicit.

The known two-handler/three-handler fixture motivates the first loop extension:
unrelated prefix -> byte-accumulation loop -> version-specific decision ->
unrelated suffix. Compare source, UIL and UDC within each version. Do not try to
prove the intentionally different pre/post programs equivalent to each other.
Compare direct recovery from patched source with incremental backing/contract
updates, preserving any shared-model limitations.

## 6. Human-LLM evidence and held-out evaluation

The NDSS 2026 study surveyed 153 practitioners and observed 48 participants on
two CTF-style binaries. It reports benefits, especially for novices/familiar
algorithms, as well as harmful or unhelpful assistance; its study restricted
participants to static analysis. It does not measure our executable-backings,
trace-assisted, multi-provider architecture. [V6]

Our proposed evaluation should count accepted behavior/dependencies, correction
cost and useful next actions rather than number of renamed symbols. Freeze
starting knowledge and tools; counterbalance provider/agent allocation; include
scaffold preparation, cold startup, tokens, waiting, coordination and rejected
hypotheses. Evaluate ordinary-information and assisted-HUD play separately.
One worker owns mutations to each live guest. Parallel tasks should be
independent questions with explicit missing dependencies, not continuous polling.

## 7. Prospective acceptance cases

These are requirements, not executed tests. Existing RFC 0002 R01-R18 remain
unchanged; this companion uses Q01-Q12.

| ID | Trial | Acceptance boundary |
| --- | --- | --- |
| Q01 | Two branches reach one value use | Keep alternatives and control predicates; no fabricated unique definition. |
| Q02 | Backward slice reaches an unknown call | Retain unresolved effects rather than treating call outputs as independent. |
| Q03 | Providers disagree on signedness or a code boundary | Preserve both claims and request discriminating evidence; no majority-vote proof. |
| Q04 | Recorded address is reused after restore/resource reload | Epoch/object identity prevents merging unrelated memory histories. |
| Q05 | Middle write determines a later read | Detailed interval recovers it; first/last index alone reports insufficient coverage. |
| Q06 | Source pointer loop versus target indexed loop | Check nonvacuous initialization, aligned step preservation, exit and progress scope. |
| Q07 | Two predicates support each other | Validate joint induction; reject circular assumption-only acceptance. |
| Q08 | Patch changes a helper but not caller bytes | Invalidate dependent behavior while retaining compatible bytes and unrelated receipts. |
| Q09 | Same source under different domain/observation profile | Cache identity differs; no inappropriate qualification reuse. |
| Q10 | Semantic width stays u8 but storage carrier changes | Preserve admitted values/arithmetic; physical size choice does not change meaning. |
| Q11 | Tensor/parallel lowering changes event order or early exit | Reject unless the observation contract explicitly permits that transformation. |
| Q12 | New operation unsupported by a consumer | Preserve as data/residual where admitted, or reject required execution; no successful no-op. |

## References and review method

- V1: Dinesh, Zhu and Fletcher, [H-Houdini: Scalable Invariant Learning](https://sushant94.me/publications/25asplos-hhoudini.pdf), ASPLOS 2025. Abstract, algorithm/soundness section and evaluation qualifications inspected; PDF page images inspected, including printed pages 1, 5 and 10.
- V2: [VeloCT author repository](https://github.com/FPSG-UIUC/veloct). Its hardware frontend is not asserted to support arbitrary software inputs.
- V3: [Binary Ninja MLIL SSA documentation](https://dev-api.binary.ninja/binaryninja.mediumlevelil-module.html) and [C++ API](https://api.binary.ninja/cpp/group__mediumlevelil.html). Development/current web documentation; no installed-runtime execution.
- V4: [Ghidra p-code reference](https://ghidra.re/ghidra_docs/languages/html/pcoderef.html) and [DecompilerUtils implementation](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Decompiler/src/main/java/ghidra/app/decompiler/component/DecompilerUtils.java), inspected 30 October 2026; source pin required for an executed comparison.
- V5: [Hex-Rays microcode may/must lists](https://python.docs.hex-rays.com/classida__hexrays_1_1mblock__t.html).
- V6: Basque et al., [Decompiling the Synergy](https://www.zionbasque.com/files/papers/dec-synergy-study.pdf), NDSS 2026. Abstract and study/limitation sections inspected; first-page image inspected.

No new native run, provider comparison, H-Houdini deployment, formal software
proof or full repository test suite was performed for this documentation
increment. Source links establish what the cited systems expose; the proposed
integration and acceptance cases remain under discussion.
