# fDisBull maturity, gap analysis, and cross-domain architecture audit

**Audit date:** 2026-11-03  
**Baseline:** GitLab `main` at `2866c414bff33510ab58e3186f96960eddd0cb94`; published `v0.30.0` is tagged at `dc6d7e7709802e743e79cf46e648a4e87b2a0a27`.  
**Status:** Architectural assessment and proposed roadmap. Documentation only; no newly executed native experiments or implementation change is claimed.  
**Companions:** [Capability milestones and acceptance gates](milestones/2026-11-03-generic-reconstruction-gates.md) · [Deterministic pipeline orchestration and agent responsibility audit](DETERMINISTIC_PIPELINE_ORCHESTRATION_AUDIT_2026-11-03.md).

## Executive conclusion

fDisBull is a **substantial, functioning investigation and evidence-retention platform**, with genuine bounded semantic reconstruction and code-generation capabilities. It is **not yet a general-purpose automatic program reconstruction engine**. Current strengths are source/byte identity, forensic state, static analysis, controlled original execution, reproducible experiments, cross-platform *bounded* output, and explicit qualification boundaries. Its dominant constraints are (1) automatic discovery of semantically meaningful blocks and their complete interfaces, (2) fragmented UIL profiles, (3) incomplete real-world state/effect/host semantics, (4) independent original-to-UIL qualification, and (5) production integration of provider discovery and verified optimization.

The development objective is not “add every game/ISA”. It is: **new source frontends, semantic domains, and target backends must vary independently**. An unfamiliar spreadsheet, text editor, strategy game, interpreter or firmware image should exercise the same recovery, contract, proof and composition machinery.

### Maturity rubric

These are **analyst estimates**, not instrumented KPIs or acceptance certificates: 0 absent; 1 exploratory; 2 bounded prototype; 3 functional on declared profiles; 4 substantial validated capability; 5 generalized with independent held-out qualification.

| Subsystem | Assessment / 5 | Principal qualification boundary |
|---|---:|---|
| Static RE, binary intake, retained evidence | 4.0 | Good on supported formats and analysis profiles; unknown indirect behavior persists |
| Original runtime investigation and rewind | 3.7 | Strong DOS/PE64 paths; incomplete Win16/PE32/device generality |
| UDL mapping and semantic lifting | 2.4 | Restricted and sometimes manually cut source-backed blocks |
| UIL typed common semantics | 3.0 | Executable typed core and catalog, not one universal behavior model |
| UDC generation and orchestration | 2.6 | Multiple working profiles; inconsistent host services and source completeness |
| Closed-loop optimization feedback | 0.9 | `!63` is draft, pure-scalar proof-of-concept |
| Blind cross-domain autonomous reconstruction | 1.4 | Strong guided/cold-agent studies do not establish general semantic recovery |
| Verification, provenance and test engineering | 3.7 | Significant gates; native/held-out coverage and evidence denominator still lacking |

Do not aggregate these estimates into a “percent complete”; they measure different obligations.

## 1. Evidence and release boundaries

- [Release status](RELEASE_STATUS.md), [v0.30 notes](RELEASE-0.30.0.md), [architecture reference](UDL_UIL_UDC_CONSOLIDATED.md) and [README](../README.md) describe the now-published 0.30 line. `v0.30.0` GitLab Release was published on 2026-11-03; avoid carrying earlier “0.29 unpublished” conclusions forward.
- The 0.30 package is versioned but a tag commit, an integration baseline, a package-build source and active installed prefix can be distinct identities. A source tag does not itself certify all runtime tests.
- Previously observed hosted `test-and-package` passed at main pipeline [3019557970](https://gitlab.com/brewster-jennings-group/fdisbull/-/pipelines/3019557970) on `f861d17`. At this audit snapshot the latest main pipeline [3022298012](https://gitlab.com/brewster-jennings-group/fdisbull/-/pipelines/3022298012) at `2866c41` is **skipped**. Never describe that latter pipeline as a pass. Native-debugger jobs in the previously passing pipeline were manual/unrun.
- The published 0.30 Release states source and package hash verification, but it does not substitute for a complete hosted native matrix or every original game's end-to-end verification.
- [MR !62](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/62) remains a **draft 0.31 release candidate** with reported local test results, not a 0.31 release. [MR !63](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/63) remains a draft optimization experiment.
- Merged [!44](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/44) (README/skill refresh), [!45](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/45) (consolidation), and [!59](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/59) (cold-agent benchmark) are already on this newer `main`, so they are not counted as outstanding integration work.

A report/test fixture needs four separately pinned facts: **source identity**, **semantic claim and admitted input domain**, **target build/runtime identity**, and **actual observation/proof receipt**. Stored agreement between two authored models is not independent original-program fidelity.

## 2. Pipeline architecture and where it breaks

`Original artifacts → loader/decoder/analyzer + original runtime → UDL source backings and behavioral boundaries → source-independent UIL → UDC providers and host orchestration → executed candidate → comparison/optimization feedback.`

This is a feed-forward **discovery direction**, not necessarily a one-way linear implementation. Each semantic operation can have many source correspondences and implementation variants. Its realization is a typed graph of selectable components with state/effect dependencies. Feedback is allowed to **suggest** a better UIL expression or backing, but must not silently redefine already qualified semantics.

| Stage | Implemented capability | Unsolved generalization issue | Best next proof |
|---|---|---|---|
| Intake/inspection | MZ/COM, PE, ELF, Mach-O, NE/LE subsets, raw, ROM/disc and resources; external source hashes | Unsupported loader/relocation/bank/OS semantics; edition-aware relationships are not general behavior links | Independent format/loader differential fixtures plus unsupported-case accounting |
| Static RE | x86, ARM64, Thumb, console/VM subsets; CFG, xrefs, image views, type/source linkage | Indirect edges, polymorphism, effects and recovered data ownership remain incomplete | Unknown-entry, alias, multi-address-space and overlapping-code held-outs |
| Dynamic evidence | DOSBox and Wine/QEMU original-probed paths, traces, watches, source layers, saved states, scenes | Full Win16 and PE32 processes, external effects, devices, speed/timing and lifecycle differences | Cold start → controlled action → checkpoint → restored comparison on multiple hosts |
| UDL | Exact source snippets/backings, separate symbolic contracts, direct AGI/Z-machine/6502 bounded adapters, Clang-backed typed C subset | Generic extraction of *meaningful* interfaces across registers, flags, memory, ABI, callbacks and I/O | Automatically infer one effectful block in three unrelated execution models |
| UIL | `fdisbull-common-uil-1`, memory/legacy/record/Z/scene profiles, catalogs, typed values, bounded control/calls | One coherent canonical meaning/effects model is not yet shared by all profiles; missing dynamic structures, float/decimal, file and host effects | Inter-profile adapter with explicit loss/refusal and source-preserving equivalence fixtures |
| UDC | Original-byte pass-through, selected splices; C/native Python/JS/Wasm/WebGPU and desktop/console output | Realization breadth exceeds auto-recovery breadth; effects/callbacks/runtime/device contracts are nonuniform | Same recovered model runs on two unrelated hosts with exact ordered effects |
| Feedback | Native value numbering/copy pruning; draft `!63` Clang/LLVM expression fusion with Z3 | No production memory/flags/branch/effects-aware source-independent optimization | Stable candidate, independent source observation, proof, cost measurement, reversible opt-in |

### Preserved strengths

1. **Evidence first:** Immutable byte versions, source mappings, exact content identities, alternate overlapping interpretations, unknown frontiers and per-edge counterexamples are structural assets ([code backings](CODE_BACKINGS.md), [UDL layers](UDL_BLOCK_LAYERS.md)).
2. **Runtime control:** DOSBox-X and Wine/QEMU debugging, source-identity-bound frame timelines, checkpoints and reversible code layers support independent experiments ([debugger rewind](DEBUGGER_REWIND.md), [frame-state deltas](FRAME_STATE_DELTAS.md)).
3. **Real abstraction tests:** [Common UIL conformance](COMMON_UIL_CONFORMANCE.md) and [native composition](COMMON_UIL_NATIVE.md) compare actual typed computations, selected C/assembly implementations and independent results. [Colonization UDL pilot](UDL_LAYER_PILOT.md) maps distinct DOS/Windows kernels to one contract; its original-instruction and output tests have declared limits.
4. **Multiple execution models:** [Processor modules](PROCESSOR_MODULES.md) and [decoder modules](DECODER_MODULES.md) distinguish interpreter bytecode from its DOS host. Console routes and [console synthesis](CONSOLE_SYNTHESIS_LOCAL_PILOT.md) demonstrate native target work, not universal source recovery.
5. **Agent repeatability:** [Cold-agent study](COLD_AGENT_EGM_BENCHMARK.md) is useful evidence for task isolation and contextualized research. Its named-source benchmark is not a blind population estimate of universal automated success.

### Architectural debt

- **Schema fragmentation:** legacy `fdisbull-il-1`, common indexed UIL, memory UIL, Z-world and indexed records can coexist, but cannot be treated as interchangeable without tested semantic adapters. Source/representation changes require explicit versioned legality; prefer a conservative core and capability extensions over flattening specialized domains.
- **Semantic discovery:** no routine generic process infers every live-in/out, hidden flag, memory alias, side effect and callback. Decoder breadth is not synonymous with meaning recovery.
- **Effects and time:** host requests marked `pending_host` are not completed I/O; timestamps, event ordering, file systems, focus, async completion, audio/device events and partial commit need a versioned effect protocol. A restored guest state is not necessarily a restored external world.
- **Types and state:** add admitted typed records/arrays/strings, reference identity, arbitrary-but-bounded collections, floating/decimal semantics, serialization and explicit state ownership; protect numeric overflow and release-specific quirks.
- **Address abstraction:** segmented, banked, native, virtual, device and source-file addresses require separate spaces, stable identities and explicitly qualified mappings.
- **Provider and block catalog:** persistent declarations already exist, but automatic discovery, untrusted submission, synthesis, validation, ranking and compatibility with production UDCs are not one completed service.
- **Incremental invalidation:** content hashes identify provenance, but a semantic or host-contract change should invalidate dependent proof and build receipts by a dependency DAG, not simply by whole-project rebuild or unchanged source bytes.
- **Demonstrated coverage denominator:** count unknown/refused and untested operations, not only passed test vectors and emitted programs.

## 3. Cross-tool comparison and reusable mechanisms

| Tool and primary source | Mature capability | fDisBull complement / action, not a replacement claim |
|---|---|---|
| [Ghidra](https://ghidra-sre.org/) | Mature disassembly, decompilation and P-code analysis | Import verified instruction/IR/dataflow facts; spend effort on semantic operation recognition, provenance and runtime equivalence |
| [angr](https://docs.angr.io/en/stable/core-concepts/pathgroups.html) | Symbolic state exploration, branching, constraints and reachability | Use as optional path/oracle provider to infer ports, input domains and counterexamples |
| [rev.ng](https://docs.rev.ng/what-is-revng/) | QEMU-assisted lifting, LLVM pipeline, inferred data layouts, dependency invalidation | Model its incremental recomputation and native source/data shape recovery; keep semantic identity independent of readable C |
| [QEMU TCG](https://www.qemu.org/docs/master/devel/tcg.html) | Dynamic translation with CPU state-dependent translation blocks | Explicit CPU/memory/device state contracts and invalidation when mapping or execution context changes |
| [ScummVM](https://docs.scummvm.org/en/v2026.4.0/index.html) | Reusable engine family replacements for shipped game executables | Engine/VM family adapters are useful, but target-general UIL cannot depend on bespoke game-engine interpretations |
| [MLIR dialect conversion](https://mlir.llvm.org/docs/DialectConversion/) | Versioned legality, partial/full conversion, rewrite patterns, types and rollback | Specify exactly which UIL features each UDC supports; refuse unsupported effects instead of quietly removing them |
| [Alive2](https://github.com/AliveToolkit/alive2) | LLVM refinement/optimization translation validation on its admitted scope | Reuse LLVM-level validation where applicable; it does **not** establish original binary ↔ recovered UIL fidelity |
| [Souper](https://github.com/google/souper) | SMT-assisted search for cheaper scalar LLVM expressions | Candidate-generating optimizer, with independently verified semantics and measured target cost |
| [Gnumeric format support](https://gnome.pages.gitlab.gnome.org/gnumeric/manual/sect-file-open.html) | Lotus WK1/WKS import | Auxiliary file-format comparator; never an oracle for historical Lotus UI, calculation scheduling or process side effects |

Prefer trusted external analysis providers and constrained IR transformations. Do not assume converting to C proves intended behavior, and do not call an external decompiler a replacement for source/runtime qualification.

## 4. Optimization feedback: precise proposed contract

[!63](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/63) composes two pure `u32` constant-operand blocks, emits C11, runs Clang -O2/LLVM, imports a *restricted* optimized expression, uses Z3 over all admitted `u32` values, and preserves original children/defaults. Its reported illustrative reductions: `(x xor 0x5A) xor 0xA5 → x xor 0xFF` and `(x + 17) - 17 → x`. This draft is **not** arbitrary optimized-PE32 decompilation, CRC-table synthesis, effectful fusion or production auto-selection.

“Backpropagation” here is an informal term. The mechanism is closer to **superoptimization / counterexample-guided synthesis / translation validation**, not neural gradient descent.

Promotion must require:
1. A *complete declared boundary*: inputs, outputs, flags, memory aliases, ordered effects, callbacks, time, environment and refusal behavior.
2. A source-qualified semantic baseline independent from the optimizer: `Original ≈ UIL` under an explicit observation domain.
3. Recovered candidate proof: `UIL ≈ optimized candidate`, including definedness, overflow and observable effects; preserve any counterexample.
4. Fixed-point or bounded cycle detection for iterative reabstraction; nontermination and unsupported LLVM must refuse.
5. Measured performance on the actual target and workload. Fewer source-level nodes are **not** necessarily less code, lower latency or lower energy.
6. An immutable original/child DAG and reversible, opt-in selected implementation; semantic changes require new contract revision.

**Hard stop:** If original behavior is incompletely observed, two mutually agreeing UIL implementations cannot certify that original meaning has been preserved.

## 5. Cross-domain acceptance: Lotus 1-2-3 and office software

A historical spreadsheet is a critical held-out class, not a skin or merely a DOS game. Pin an exact, lawfully supplied DOS Lotus 1-2-3 edition and its executable, format and environment; do not transfer findings between Release 1/1A and 2.x without evidence.

A first authored fixture: `A1=3; B1=A1*2; C1=B1+5` (expected C1=11), update A1 to 4 (C1=13), then save/reload and compare the declared snapshot. This is a **test definition**, not evidence of an executed Lotus experiment.

| Feature | Portable UIL requirement | Independent original-observation gate |
|---|---|---|
| Edit/clear/copy/fill cells | Typed state mutation and reference-translation policy | Actual original transitions for relative/absolute references |
| Formula parsing and evaluation | Expression/dataflow graph; numeric and error profile | Roundoff, overflow, coercion, invalid references and evaluation order |
| Recalculation | Dirty dependencies, calculation modes, scheduling, error propagation | Matched changed cells and intermediate observables, not just final total |
| Commands/macros | Context, focus, modal state, event execution and completion | Original command dispatch and macro-visible state/effects |
| Save/load | Versioned resource encoding, file effects and persistence lifecycle | Byte- or semantic-level file round trip with source/edition pinning |
| Presentation/printing | Independent text/graphics/print host services | Declared fidelity level; no assumption of pixel identity |
| Recovery and failure | Atomicity boundaries, partial commits, invalid input and refusal | Repeated edit/save/restart and failure-path observations |

For broader generalization also hold out a DOS word processor or small text editor and one non-UI firmware/CLI tool. A game, a spreadsheet and an editor should share the same state/effect/proof primitives without shipping game- or application-specific logic in the core.

## 6. Priority decisions

**P0 before new domain features**
- Establish uniform capability and proof/receipt levels: recognized, recovered, modeled, original-qualified, composed, realized, optimized, generalized. Record evidence domain and uncertainty at every edge.
- Stabilize the canonical UIL semantic contract and adapters; no new core opcode without a witnessed non-expressible case, semantics, refusal behavior and conformance fixture.
- Introduce generic effect/state contracts and automated boundary discovery on a held-out target, including memory aliases and caller-visible flags.
- Make final-cut native qualification and known skipped gates explicit, and reconcile release/tag/installed-provider identities.

**P1 next**
- Productionize the block catalog and fresh-agent sweding [!57](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/57)/[!58](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/58) beyond bounded authored arithmetic; preserve unqualified declarations as non-executable.
- Resolve indexed record validation before integration ([!43](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/43), [!49](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/49)).
- Use CHIP-8 corpus/adversarial decoding [!61](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/61) to measure semantic/idiom saturation; independent reference interpreter needed beyond self-repeatability.
- Qualify Win16/PE32 original runtime after the preflight-only [!60](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/60).
- Add source/semantic/implementation/environment dependency invalidation and cost receipts.

**P2 after qualification**
- Extend optimization [!63](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/63) beyond pure expressions by progressively admitting memory, branching and effects, with independent native observations and rollback.
- Run Lotus and editor blind recoveries before declaring generic application support.
- Define an offline non-commercial/publication policy for sanitized semantic contributions; original proprietary payloads and private FDBs never move into source artifacts by default.

## 7. Definition of done and metrics

Use the [companion roadmap](milestones/2026-11-03-generic-reconstruction-gates.md) for milestone dependency and exit gates. Instrument:
- **Recovery ratio:** original-backed, source-qualified semantic operations / all observed and discovered candidate operations; report unknown/refused separately.
- **UDC coverage:** admitted UIL constructs and effects fully realized / all constructs used by the tested program, by target.
- **Proof coverage:** independently checked original→model, model→target and composed-operation contracts, with solver/guest/profile identities.
- **Held-out generalization:** target-family-specific code changes, new providers and human interventions per unfamiliar program; no claims from fixture-only self-agreement.
- **Effect fidelity:** first differing ordered state/effect event, not just matching final scalar values.
- **Optimization:** runtime, memory, code size, compile cost and retained proof obligations; regressions tracked separately.
- **Agent research:** cold-start attempts, false promotions, counterexamples found, tool effort, reproducibility under context isolation.

**Decision rule:** More source files, decoders, game reproductions or passing test counts are useful only insofar as they improve the qualified throughput of new source→UIL→UDC programs. The principal next milestone is the semantic middle, not an ever-growing list of game-specific adapters.

## Key project references

- [Consolidated UDL/UIL/UDC reference](UDL_UIL_UDC_CONSOLIDATED.md)
- [Common indexed UIL contract](COMMON_UIL_CONTRACT.md) and [conformance](COMMON_UIL_CONFORMANCE.md)
- [Native realization and linking](COMMON_UIL_NATIVE.md), [desktop shells](COMMON_UIL_DESKTOP.md), [UDC tests](UDC_TESTING.md)
- [Source/byte backings](CODE_BACKINGS.md), [UDL selections](UDL_BLOCK_LAYERS.md), [cross-edition pilot](UDL_LAYER_PILOT.md)
- [Interpreter modules](DECODER_MODULES.md), [processor seam](PROCESSOR_MODULES.md), [console acceptance](CONSOLE_RECOMPILER_ACCEPTANCE.md)
- [UIL export boundary](UIL_BOUNDARY.md), [reconstruction qualification gates](RECONSTRUCTION_WORKFLOW_GATES.md)
- [0.30 release](RELEASE-0.30.0.md), [status](RELEASE_STATUS.md), [cold-agent evaluation](COLD_AGENT_EGM_BENCHMARK.md)

_No original binaries, game data, device images, project databases, native state, or private source snapshots are included in this document._
