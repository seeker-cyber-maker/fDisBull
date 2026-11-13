# CHIP-8 end-to-end package-reuse and blind instruction-gap acceptance plan

**Status:** Proposed validation matrix, **not** a record of completed end-to-end reconstruction or CHIP-8 sweding.  
**Basis:** [Reusable package RFC](../REUSABLE_ANALYSIS_PACKAGES_RFC_2026-11-03.md), [package example](../examples/chip8-package-closure.example.json), pilot [!61](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/61), registry [!57](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/57) and separate swede composition trial [!58](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/58).

## Prior evidence: accurately scoped

From [!61 RESULTS.md](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/agent/chip8-sandsifter-pilot-20261102/examples/chip8_pilot/RESULTS.md):

| Observation | Result | Ceiling |
|---|---:|---|
| Classic non-legacy instruction families in six selected ROM observations | 26/34 (76.47%) | Bounded no-key/clock policy and authored VM; not population prevalence or original hardware proof |
| Natural executed adjacent family pairs / triplets | 132 / 244 | Trace-family novelty, not qualified composed UIL or whole-program correctness |
| Unseen classic families with authored gap probes | 8 / 8 passed | Synthetic one-word probes in the same VM, not natural family occurrence |
| Two classic/SCHIP/XO classifiers | 196,608 word/profile checks, 0 disagreements | Shared specification; no independent interpreter oracle |
| Distinct source-PC-word candidates and edges | 339 / 367 | Observational candidate registry, not verified behavior |
| Programs in selected public archive manifest | 6 classic, 2 SCHIP, 1 XO | Only six classic programs executed |

Historical family curve by successively adding the six classic titles: **11, 18, 23, 25, 25, 26**. Family pairs: **15, 44, 81, 91, 114, 132**. Triplets: **17, 57, 121, 137, 197, 244**. Order and sampling matter; do not extrapolate a universal 76% saturation plateau.

**Different experiment:** [!58](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/58) reported one, two and three **connected authored pure-scalar C blocks** sweded by fresh agents, first attempt passed for each worker mode, with finite independent arithmetic replay. These results are **not** a demonstration that one/two/three consecutive missing CHIP-8 instructions were blindly recovered or that host-device effects and UIL are already connected. The new experiment below extends that methodology.

## 2026-11-12 bounded G0 implementation note

The current source adds a pinned Git-corpus CHIP-8 intake and read-only
project identity verifier: [CHIP-8 conversion intake](../CHIP8_CONVERSION_INTAKE.md).
It validates the caller-pinned raw manifest, selected member size/SHA-256/Git
blob, original source mapping and declared classic profile before project
creation. Repository, edition and rights remain manifest-attributed claims;
source bytes are retained in the required private object store. This bounded
G0 slice does not implement the proposed G1 package closure or qualify any
G2–G8 conversion, independent execution or delivery gate. The matrix below
remains the proposed acceptance plan, not a completed gate report.

## 2026-11-13 bounded G1 implementation note

The [compatible package-closure resolver](../CHIP8_PACKAGE_CLOSURE.md) now
binds G0 to separately versioned, hash-pinned classic ISA and explicit native
v6 environment declarations. Cold inspection revalidates source and transitive
dependencies; another ROM reuses the same definitions with its own source and
target closure. Optional runtime declarations remain unverified, and optional
analysis pins hash only existing static records without decoding or proof.
This is a bounded G1 declaration-compatibility result. It does not qualify
instruction semantics, historical behavior, arbitrary ROM compatibility or
G2-G8 conversion. The wider resolver/campaign plan below remains prospective.

## A. End-to-end gates, in execution order

| Gate | Primary owner | Required software-owned acceptance | Common false positive to reject |
|---|---|---|---|
| G0: intake and exact identity | Deterministic source/package resolver | Exact ROM hash/member/edition, corpus provenance and program profile, no hidden source file copies; detect mismatches | Filename match means same software |
| G1: compatible package closure | Resolver | Pin CPU/ISA, environment/device/clock/quirk capabilities, optional runtime and target analysis; reproduce closure cold | Host CPU or same “chip8” label means all dialects compatible |
| G2: original source mapping and UDL | Decoder, target index, bounded exception worker | Real PC/word/span, call/control context, typed live-ins/outs/effects, unknown byte paths identified; source identity retained | Entire 65,536-word scan is source semantic coverage |
| G3: candidate UIL semantics | Common UIL with admitted adapters + independent worker review | All required executed operations mapped, or explicit residual/refusal; bit widths, registers, stack, I, VF, memory/clock/output effects represented | Candidate semantic label is a verified rule |
| G4: original→UIL qualification | Independent oracle runner, Terra review | Compare same selected initial states and input/timer/RNG schedules against a trusted separate implementation or independently accepted specification fixtures; first divergence retained | Same authored VM replay, or two shared-spec classifiers |
| G5: UIL→UDC selection and build | Catalog and target builder | Qualified provider or explicit missing-provider ticket; target ABI/effects/quirks and build identity pinned, no unsupported services dropped | A generated source file proves a runnable port |
| G6: composed target execution | Deterministic differential harness | Run independent original/UIL/target on same named route; compare PC/continuation where relevant, V regs, I, stack, memory, frame, timer/sound/key effects, stop/refusal and errors | One arithmetic value or screenshot agrees |
| G7: source/target variant reuse | Resolver and independent verifier | Second held-out ROM reuses G1 and qualified operation contracts, rechecks source binding, investigates only novel effects | Similar titles or matching mnemonics certify equivalence |
| G8: end-user delivery | Packaging/doctor/receipt | Fresh executable run, machine-readable manifest, checked dependencies and archive hashes, accessible artifact and explicit limitations; no unfinished delivery obligations | Tests passed, branch committed, or binary emitted |

**Minimum “completely tested” scope:** one selected, source-pinned CHIP-8 program or finite complete interaction route under declared original/emulator dialect and input/clock policy, from import to emitted program and independent executable behavioral comparison. A game need not have a natural exit; the accepted route must define a reproducible stop, timeout/frontier and covered state/effects. All unseen input paths remain explicitly *outside the claim*, not silently complete.

## B. Package reuse and variant test protocol

1. Freeze architecture package version and dialect, environment package versions (display, keypad, timers, RNG, RAM, quirks), source ROM SHA and parser/solver/UDC versions.
2. Process ROM A. Persist exact static source identities, decoded facts, independently qualified semantic operations, native observation receipts and emitted source/target closure.
3. Open a new cold session on **the same ROM**. Package resolver must find exact still-valid facts and avoid any agent research/web call, repeated decoding or replayed proof unless current runtime evidence is explicitly requested.
4. Process ROM B with compatible profiles; reuse CPU/env knowledge and qualified semantic definitions, retain B's own source bindings and different unknown code.
5. Process a controlled variant of ROM B: exact unchanged blocks can reuse valid source facts; changed control/data, quirk profile or environment invalidates affected descendants. Cross-variant semantic equality needs its own proof.
6. Run incompatible dialect, clock, VM or legacy-instruction negative control and require preflight refusal, not a guessed fallback.

Measure per case: model tokens/tool calls, deterministic stage time, cache hits, invalidation count, first new opcode/idiom, first divergence and false promotions. No “saved tokens” percentages until the paired baseline is run.

## C. Complementary coverage recovery

| Route | Generate or observe | Must do | Must *not* do |
|---|---|---|---|
| **Natural corpus** | Load byte-pinned real archive ROMs into qualified host; record PCs, executed words, family usage and pairs/triples | Report exact input/clock profile and reachable coverage | Claim any unexecuted/unknown byte belongs to executed code |
| **Synthetic compile/assemble then shred** | Author minimal CHIP-8 program for absent legal family, family pair/triple or behavioral interaction; compile/assemble with pinned independent source tool | Run the **ordinary intake→decode→UDL→UIL→UDC path**, compare independent spec/oracle, keep synthetic provenance | Increment natural-use counters, inject a direct “verified” registry entry |
| **Blind implementation sweding** | Retain qualified UIL contract while hiding reference implementation and golden tests | Agent authors target provider; independent verifier tests entire effect and continuation contract | Conflate solution with source semantic discovery or substitute final-only equality |
| **Blind semantic recovery** | Hide source's reference semantic contract but permit original bytes/trace/oracle under fixed policy | Agent recovers contract and mappings; compare against independent source/oracle | Claim successful sweding merely because a label was generated |
| **Adversarial** | Faulty decoder, illegal encoding, quirk conflict, bad memory/stack, unexpected wait/partial effect | Preserve minimum first-divergence and refusal receipts | Treat syntactic validity as original runtime correctness |

**Gap-filling policy:** Query qualified catalog first. An absent *source observation* can be filled with generated authored source; an absent *UDC provider* can be sweded; an unknown *semantics* requires original/independent source recovery. Multiple routes can produce complementary evidence for the same contract. The producer tag and oracle ancestry are never collapsed.

To measure corpus saturation, grow by held-out title/author batches and report marginal **new qualified semantics**, **new pairs/triples**, and **new compositions**, not just opcode count. Do not force a synthetic 100%-natural-use result. Reaching a rare opcode in an admitted runtime route still obligates handling it correctly or narrowing the claim.

## D. Blind gaps of 1, 2, and 3 *consecutive source instructions*

### What the mask means

**Primary benchmark:** select a qualified source window of 1, 2 or 3 adjacent fixed-size classic CHIP-8 instruction words at successive source PCs that also appear consecutively in an observed trace. Keep a hidden reference implementation, exact source, PC/word hashes and test results in an isolated verification store. Workers receive only the disclosure authorized by their context arm. Source windows containing branch skip, taken jump or wait should also appear in an explicitly labelled *dynamic-consecutive, non-address-adjacent* secondary benchmark.

Mask **a real contiguous gap in the program representation**, not just replace a string of mnemonics in prose. Test individual instruction intermediate state and complete composition: V0–VF/VF alias, I, PC/return stack, memory, frame pixels/collision, key consumption, time/sound/RNG and refusal. A final matching scalar does not establish correct composition.

### Separate missing-knowledge classes

- **S: Unknown semantics.** The worker sees a source gap plus a permitted independent source-execution oracle and must infer original→UIL behavior. No prewritten reference semantic contract is visible.
- **I: Known semantics, unavailable implementation.** Worker sees a *source-qualified* complete UIL contract and target ABI/host requirements, but cannot see the golden target implementation. It must swede a UDC implementation.
- **B: Both missing.** Recover semantic contract first, independently qualify, then swede a target provider. Report separate evidence gates and errors; this is strictly harder and must not be counted as an I success.
- A purported *blind* C0 task with no behavior spec **and no oracle access** is underdetermined; correct behavior is refusal, not invention.

### Context-availability ablation (two distinct task types)

| Level | Semantic-recovery arm S/B receives | Implementation-only arm I receives |
|---|---|---|
| C0 black-box | Typed ports, pre/post observations and bounded queryable independent oracle; **no ISA dossier or golden semantics** | Exact qualified behavioral contract, typed ports, target ABI and test runner only |
| C1 ISA package | C0 plus pinned CPU/ISA spec, opcode widths, register/flag/memory/stack rules | C0 plus reusable architecture/compiler instructions and qualified ISA helper catalog |
| C2 + environment package | C1 plus device/clock/quirks, input and state/persistence requirements | C1 plus validated target host/runtime service adapters and execution profile |
| C3 + Elephant dossier | C2 plus source-attributed edition/candidate addresses, permitted neighboring qualified blocks, known variants, explicitly *unqualified* external hypotheses | C2 plus relevant previously validated implementations/composition patterns, excluding hidden answer |

Make source availability and oracle-query budget explicit independently of context level. Do not compare task arms whose fundamental question differs. A worker with known source bytes and the full decoder has more information than a black-box worker; label the disclosure.

### Design, isolation and measurement

- Factorial study: **gap length 1/2/3 × context C0–C3 × gap class S/I/B**, on equal-difficulty seeded cases. Start with controlled smoke cases, then repeat across held-out titles/authors and multiple workers/seeds before claiming trends.
- The Sol/Astra lead performs source literature research **once**, creates persistent source-attributed dossiers, and withholds the golden original/target solution. Luna/Terra perform isolated implementation/falsification. Use separate read permissions/mounts for masked workers, golden tests and reference source; prompt-only isolation does not establish blindness.
- The deterministic coordinator generates packets with exact source/profile/ports/effects, allowable references, test budgets, historical qualification and a smallest-next-experiment field. It does not copy large lead chats or give withheld answers to the workers.
- Independent verifier tests behavior and preservation of unaffected state, original→model, model→target, composed state/effects, refusal and negative mutation. Preserve all counterexamples; do not auto-promote a self-tested candidate.
- Record **accuracy and correct refusal** first; then tokens in/out, tool calls, wall time, probe count, agent interventions, CPU time, hit rate, retries and final deliverable closure. Do not score an early incomplete worker as faster success.

### Positive/negative controls

1. Trivial sequential constant assignments and reversible cancellation for basic packet/ABI checks.
2. Carry/borrow, VF aliasing, register/memory overlap and bounds.
3. Skip-branch behavior with nonexecuted word, PC step-size/continuation, call/return stack.
4. Draw collision/frame reset, key wait, timer ticks, RNG policy and partial external effect.
5. Wrong reference semantics, intentionally inverted guard, missing state write, forbidden quirk, and unqualified reused provider. Each must fail or refuse.

## E. Staged pilot implementation tickets

| Priority | Ticket | Completion test |
|---|---|---|
| P0 | Define/validate package closure manifest for OS-env, CPU/ISA and target edition | Same input resolves identical compatible closure; incompatible dialect fails closed |
| P0 | Wire existing CHIP-8 source/observation index to package registry and evidence cache | Two cold sessions and second ROM reuse qualified data without re-documenting ISA; unknowns preserved |
| P0 | Separate natural, synthetic, swede, adversarial evidence classes | Eight authored gap probes **do not** raise 26/34 natural count; all are visible in independent counters |
| P0 | Run an independently qualified interpreter/quirk oracle | Same-spec classifiers and same-VM replay are no longer the only tests; first divergences retained |
| P1 | Generate rare-instruction programs and reimport/shred | At least one missing family and a two/three-instruction idiom pass ordinary UDL/UIL path with synthetic provenance |
| P1 | Deterministic 1/2/3 gap packet + hidden oracle runner | Workers cannot retrieve golden implementation; cases maintain exact source and immutable test IDs |
| P1 | Integrate [!57](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/57)/[!58](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/58) registry/selectors and qualified swedes | Existing provider reused before generation; proposed swede has independent executable proof and opt-in selection |
| P1 | Complete source→UDL→UIL→UDC→host runner | Same bounded program reaches independently compared state, effect and continuation, not merely an emitted C/ROM |
| P1 | Artifact/last-mile delivery closure | Fresh target run, packaged verified files and exact completed/partial status; no manual end-user repair |
| P2 | Held-out variant generalization and cost benchmark | Source/package reuse saves measurable analysis work on a second program without correctness regression |

## F. No false-completeness claims

Do not describe any of the following as proven by existing !61/!58:

- 76% as a population-level statistic, synthetic probes as natural observations or full-code coverage.
- All classic/SCHIP/XO executions as historically qualified, or same-VM replay as independent correctness.
- Candidate UDL/UIL family label as an admitted common UIL contract.
- Connected scalar 1/2/3 blocks as proof of blind *consecutive-instruction* recovery.
- A generated source file as a completely delivered playable port.
- All 34 families as required naturally observed by the chosen ROM corpus.

**Ultimate acceptance:** a narrowly specified CHIP-8 program runs through **source → UDL → UIL → selected UDC → independent target execution → verifiable delivered artifact**, with package reuse on a second held-out source and no agent manually transporting artifacts between supported stages. This plan is the gate; **execution evidence still has to be produced**.
