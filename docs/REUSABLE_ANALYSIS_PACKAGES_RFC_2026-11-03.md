# RFC: Reusable environment, architecture and software-target evidence packages

**Status:** Proposed architecture, not a production implementation.  
**Date:** 2026-11-03. Baseline: `main` `2866c414bff33510ab58e3186f96960eddd0cb94` / v0.30.0.  
**Pilot:** [CHIP-8 study MR !61](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/61) (draft, not merged).  
**Companions:** [CHIP-8 end-to-end and blind-gap acceptance](milestones/2026-11-03-chip8-package-end-to-end-acceptance.md) · [illustrative package closure](examples/chip8-package-closure.example.json) · [deterministic coordinator analysis](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/docs/maturity-generalization-20261103/docs/DETERMINISTIC_PIPELINE_ORCHESTRATION_AUDIT_2026-11-03.md).

## Decision proposed

The 2026-11-13 source contains bounded CHIP-8 implementations of
[G0 pinned intake](CHIP8_CONVERSION_INTAKE.md) and
[G1 declared ISA/environment closure](CHIP8_PACKAGE_CLOSURE.md). They do not
implement this full cross-platform resolver proposal or independently qualify
semantic packages. G1 keeps package-definition identities, exact target binding,
optional unverified runtime declarations and existing-analysis fingerprints
distinct; G2-G8 conversion remains separate work.

Establish **three mandatory reusable package classes**, one optional runtime/family class, and a separately versioned session:

| Package | Responsibility | Reuse |
|---|---|---|
| **OS / environment** | Loader/memory layout, clock, input, display/audio devices, filesystem/syscalls/BIOS, host capabilities, interpreter execution contract, quirk-specific services | Across compatible projects, once qualified |
| **CPU / architecture / virtual ISA** | Opcode decoding and semantics, registers, flags, control flow, stack, addressing, exceptions, profile versions and quirks | Across programs with the same admitted architecture/profile |
| **Target / exact software edition** | Immutable source/resource hashes, version and lineage, recovered source spans, UDL bindings, qualified UIL rules, known variant deltas, evidence and unresolved gaps | Across *sessions* involving the same program/edition |
| Optional **engine / runtime family** | AGI, Z-machine, CRT, application framework or shared VM implementation | Across family-compatible programs |
| **Investigation session** (not a reusable knowledge package) | Live checkpoints, input schedule, working hypotheses, temporary patches, agent tasks, private run artifacts and partial progress | Resumable but not automatically transferable as truth |

The architecture and environment packages are **orthogonal dependencies**, not a strict tree. Loader/ABI/runtime profile binds them. An x86-16 DOS program and an x86-16 Win16 program may share instruction semantics without sharing OS calls. Likewise CHIP-8 is a **virtual ISA with no conventional OS**; its emulator host's keypad, clocks, display and input/timing policy belong to the environment binding, not a made-up DOS-like syscall layer.

**Invariant:** Target *facts* persist across sessions, while mutable execution/checkpoint state remains session-scoped. A source's hash does not establish semantic equivalence. An agent does not automatically get to declare missing semantics proven because two generated versions agree.

## CHIP-8 reduced-architecture example

- ISA package: classic fixed 16-bit words, V0–VF, I, PC, stack, instruction families, legal forms and decoding/width/flag rules. Keep SCHIP, XO and legacy `0NNN` capability contracts distinct; XO `F000` is a declared longer instruction.
- Environment package: selected ROM load address, memory bounds, original/host interpreter profile, 64×32 framebuffer, keypad, deterministic RNG, delay/sound timer clocks and explicit selected quirks. The CPU package alone cannot certify these effects.
- Target package: byte-pinned Snek, Ghost Escape or another specific ROM; source/PC/word identities, entry and observed paths, source-mapped candidate UDL/UIL, variant relationships and unresolved effects. Its privately stored ROM bytes are **not** copied into public documentation.
- Session: one specific input/clock/seed policy, emulator state, toolchain identities, probes and run receipts. A new session reuses qualified descriptions but obtains new runtime evidence.

[MR !61 README](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/agent/chip8-sandsifter-pilot-20261102/examples/chip8_pilot/README.md) reports an authored two-decoder/classic-VM pilot and a private candidate registry. The candidate labels are not accepted common-UIL contracts, its interpreter is not a historically independent oracle, and its registry is not production [!57](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/57). This RFC does not claim they are.

## Deterministic first-pass resolver

Before dispatching a Goldfish worker, software should:

1. Record exact source/member hashes, edition and source rights claims, source-to-loaded mappings, resource identities and compatible execution profile.
2. Resolve environment and ISA packages by *declared capabilities* and exact version/quirk constraints. Do not select the host CPU merely because it runs the emulator.
3. Look up exact source-derived facts and already qualified contract/provider receipts by complete transitive dependency identities.
4. Search previously analyzed editions and variants for relocated code, identical source spans, corresponding CFG/data structures and independently qualified equivalent semantic contracts.
5. Classify each candidate: `exact_reuse`, `verified_remap`, `proven_semantic_reuse`, `candidate_only`, `contradicted`, or `unknown`.
6. Produce a deterministic work DAG of outstanding obligations. Schedule parsers, reference lookups, proofs and qualified builds automatically; send only irreducible ambiguities/missing providers to agents.
7. Validate any proposed promotion to shared environment/ISA/engine package against a separate source/spec/oracle check. Recompute dependent receipts when identities, timing, quirks, effects or assumptions change.

Existing [collection intake](TARGET_COLLECTION_INTAKE.md), [source concept search](SOURCE_CONCEPT_SEARCH.md), [type catalogs](TYPE_CATALOGS.md), [source/backings](CODE_BACKINGS.md), [UDL layers](UDL_BLOCK_LAYERS.md), and [native link selection](COMMON_UIL_NATIVE.md) supply real components. Their existence does not constitute this proposed unified package resolver.

### Reuse ladder

| Relationship | Legal reuse |
|---|---|
| Identical source and compatible decoder/profile/version | Static facts and any still-valid evidence; not automatically fresh runtime readiness |
| Verified relocation/format repacking | Source mapping with independently checked address remap and dependent qualifiers |
| Independently proved equal behavior on an admitted domain | Shared semantic contract; distinct original UDL backings, ABI and run receipts |
| Related edition, same engine, matching names or similar machine code | Attributed lead and a suggested distinguishing probe, never automatic equality |
| Changed quirk, unknown host effect, conflicting proof | Refuse or invalidate affected downstream claims; preserve historical identities |

**Caching:** definition cache, semantic qualification cache, and path/state-specific observation cache are separate. A new ROM should not cause repeated ISA discovery; an ISA semantic fix should invalidate its affected target proofs. Unchanged source identity alone is an insufficient cache key.

## CHIP-8 coverage as a prioritization signal, not a universal assertion

The [!61 results](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/agent/chip8-sandsifter-pilot-20261102/examples/chip8_pilot/RESULTS.md) are more precise than a universal 76% claim:

- Six deliberately selected classic CHIP-8 ROMs under a bounded no-key, timed authored-VM policy observed **26 of 34 (76.47%) non-legacy instruction families**. Nine source-pinned archive programs were present; two SCHIP and one XO were classification-only.
- The same runs observed **132 distinct adjacent executed family pairs** and **244 family triplets**, even as new-family discovery slowed.
- Eight missing families were separately covered by **authored one-instruction probes**, which passed against the pilot's own VM. These are not natural-use observations, historical oracle proofs or sweded UDC implementations.
- Two independently authored classifiers that share a specification agreed across **65,536 word encodings × 3 dialect profiles**, which establishes agreement, not independent hardware semantics. Same-VM replay establishes repeatability, not correctness.

The six-title convenience sample does **not** establish that 76% of opcode families occurs in the vast majority of programs. Future held-out titles/authors, quirk profiles and independent emulator comparisons must test that extrapolation. The count is **family-level observed coverage**, not fraction of all syntactically possible 16-bit encodings or every execution path.

### Avoid chasing an artificial 100% natural-usage target

Maintain two different requirements:

**Complete ISA inventory:** every legal encoding/family in each supported dialect is classified with semantics, explicit unresolved/opaque, or refused. A small finite ISA is cheap to enumerate, but not every syntax acceptance is a runtime/semantic proof.

**Complete declared workload:** every instruction and effect reached within the selected program and input/clock/quirk envelope is supported, legitimately residual/original-backed, or explicitly excluded with a narrowed claim. A rare opcode becomes mandatory as soon as the accepted workload reaches it.

Artificially increasing corpus “natural use” to 100% using newly authored programs would corrupt the metric. A useful cutoff is based on measured marginal new-family/idiom/contract discovery with explicit holdouts, not a guessed universal saturation percentage.

## Complementary gap-filling sources

**Do all of them, preserve provenance separately:**

| Route | Meaning | Source-of-truth boundary |
|---|---|---|
| Real corpus observations | Naturally executed original ROM code with exact source/PC/input identities | Natural usage statistics; original-runtime qualification still required |
| Authored/compiled source programs, then reimported and shredded | Construct legal missing instructions, pairs and triplets; pass through the ordinary loader→decode→UDL→UIL path | Synthetic coverage; compare with independently specified/original reference semantics |
| Sweded implementations | Generate alternate UDC providers for an already qualified semantic contract | Candidate until compared against independent original/model/target checks; not natural usage |
| Blind semantic recovery | Infer a hidden source meaning using permitted original bytes/traces and oracle observations | Candidate until original→UIL verified, not equivalent to provider sweding |
| Mutated/invalid/quirk programs | Force failures, refusal, ambiguous fronts and first-divergence reduction | Negative/adversarial coverage, not executed-family use |

Generated programs and swedes can reinforce each other: use an assembler/compiler to make a new target containing a rare instruction, recover and compare its contract, then let a blind worker swede a separate target realization under a withheld reference implementation. Or swede first from an independently qualified contract and later meet the operation in a held-out real ROM. Preserve **both evidence ancestries**, never overwrite one with the other.

The [sweding guide](../src/fdisbull/skills/fdisbull-investigate/references/sweding.md) already requires effect/timing/source/model/target comparison. The planned catalog workflow [!57](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/57) and connected-block trial [!58](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/58) are draft precedents, not a completed production schema.

## EGM ownership and agent packets

- **Sol lead (Astra exceptional architecture reviewer):** one-time external specs, archive/corpus research, dialect/quirk comparisons, versioned permanent OS/ISA/engine dossiers, held-out challenge design, strategic routing. External reconstructions are labelled hypotheses until source verified.
- **Luna implementation worker:** only assigned missing source slices or target implementations, with pinned source/profile/ABI/contract/acceptance, no history rediscovery.
- **Terra independent verifier:** separate original source and oracle checks, adversarial mutation/counterexamples, refusal tests. Do not leak implementation source or hidden expected answers.
- **fDisBull coordinator:** package resolver, task packet construction, cache/handoff, deterministic test execution, qualification-gated promotion and end-user deliverable closure.
- **User:** approvals for source mutation, external side effects, license-sensitive payloads and release/merge.

The [Cold-Agent EGM benchmark](COLD_AGENT_EGM_BENCHMARK.md) reported a 39.2% wall-time reduction and 46.9% fewer tool calls in its controlled dossier-assisted vs skill-only comparison. This is evidence for the prepared-context mechanism in that benchmark, not a universal model ranking or guaranteed reduction on CHIP-8.

## Minimal acceptance to add to the pipeline roadmap

The companion [CHIP-8 test matrix](milestones/2026-11-03-chip8-package-end-to-end-acceptance.md) specifies:

1. Two cold sessions resolve the same compatible environment/ISA/target package closure without rerunning known analysis.
2. Different ROMs retrieve shared machine/env knowledge, while only target-specific differences reopen; incompatible quirks fail closed.
3. A generated legal-opcode program reenters through the ordinary analysis path and only increments **synthetic**, not natural, coverage.
4. Separate blind **semantic recovery** and **implementation sweding** trials test **one, two and three consecutive missing instructions** with controlled available context and a hidden independent oracle.
5. One bounded full program runs original→UDL→UIL→UDC→independent target execution→verified packaged deliverable, including input/display/timer/memory/continuation effects and original runtime limitations.

No original ROM payload, private FDB, emulator state, machine-readable proven schema, generated code or runtime change is shipped by this RFC. All source license claims are attributed to their publisher rather than adjudicated.
