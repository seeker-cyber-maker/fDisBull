# Named fDisBull pipeline stages: contracts, gates and per-stage optimization

**Status:** Architecture/acceptance proposal, **not** a new runtime schema, command, completed compiler or implementation claim.  
**Audit date:** 2026-11-04; GitLab main `3dc5c50d35f310a3ba39b1cf0cf82a20b8df69f7`, published `v0.31.1` (`e94bae0`); proposed `v0.32.0` remains an unqualified Draft [!78](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/78).  
**Source-of-truth:** [consolidated UDL/UIL/UDC](UDL_UIL_UDC_CONSOLIDATED.md) [!45], [14-stage deterministic audit !64](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/64), [reusable package RFC !65](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/65), [portable service RFC !66](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/66). See [complete MR board snapshot](agent-handoffs/GITLAB_MR_BOARD_2026-11-04.md).

This RFC **names** the 14 existing inventory stages rather than inventing a second pipeline, adds explicit handoff and optimization contracts, and assigns existing MR research owners. Names `P00`–`P13` are provisional planning labels. Existing `fdisbull-*` profile identifiers, formats, parser fields, APIs and installed behavior remain unchanged.

## Goal and irreducible semantic separation

`original bytes / live source → UDL (User-Defined Language) mappings → UIL (Universal Interaction Language) behavior → UDC (User-Defined Compiler) realization → independently tested result`.

- **Source / UDL:** factual byte/address/edition ownership, code effects and candidate interpretation. The same physical byte can participate in overlapping instruction interpretations; duplicate bytes in self-enclosed UDL blocks if necessary, preserve overlapping physical layout at selected UDC realization; never leak overlap mechanics into UIL meaning.
- **UIL:** **what happens and when**, typed state/transitions, preconditions and requested effects. It does not prescribe CPU flags, OS APIs, host registers or renderer wiring. Canonical common indexed UIL is `fdisbull-common-uil-1` only where its actual validator admits the semantics; other established profiles require explicit adapters, not renaming.
- **UDC:** **how** a selected target enacts the contract (compiled code, retained native island, emulator-backed residual, generated connector, presentation/service provider). Provider admission must satisfy ABI, state, clocks, effects and refusal semantics. A candidate may remain mixed original-backed.
- **Qualification:** source→UIL evidence and UIL→target evidence are **independent**; identical generated copies or same-VM replay do not prove original semantics. Native restore is bounded and does not rewind external host state automatically.
- **Packages:** resolve reusable **environment/OS**, **CPU/ISA** and **exact target/edition** packages, optional **engine/runtime**, plus a mutable **session** envelope. CHIP-8 environment is display/keypad/timer/RNG/quirks, **not** an invented operating system.

## Named phase map and exact handoff obligations

Each row's named I/O is a **proposed logical artifact category**, not a registered parser schema. A row must emit a qualified, refused, blocked or unknown receipt: never manufacture an empty successful result. `P04 Observe` and `P08 Qualify` can feed earlier candidate phases through **new immutable revisions**. This is a DAG with bounded feedback, not an irreversible linear script.

| ID and phase name | Required input | Typed output / handoff | Mandatory admission / refusal | Primary independent metric | Coordinating MRs |
|---|---|---|---|---|---|
| **P00 Intake** | Authorized source member(s), container/path/rights claim | `source_inventory`: exact hashes, edition, locale, members, offsets, retained originals and unresolved formats | Never equate filenames or visually similar editions; isolate private bytes | Files/s, bytes parsed, ambiguity and exact reuse rate | !77 !43 !52 |
| **P01 Lock** | `source_inventory`, capabilities, requested fidelity and host policy | `profile_lock`: environment/ISA/target(/engine) IDs, compatibility, selected runtime/quirks and missing capabilities | Refuse unsatisfied platform, clock, ABI or backend constraints; host CPU is not guest ISA | Cold resolution time, valid cache hits, wrong-compatibility negatives | !65 !64 !60 !61 |
| **P02 Decode** | Exact mapped/loaded source and ISA lock, entry candidates | `decode_facts`: instruction spans, context, alternatives, edges, confidence, unclassified frontier | Decode is a fact, not an executed semantic proof; preserve overlaps and unknown flow | Relevant decode coverage/s, disagreement rate, frontier growth | !61 !11 !68 !77 |
| **P03 Slice** | `decode_facts`, alias/register/stack models | `effect_summary`: def-use, live-in/out, flags, may/must writes, calls, host effects, unknowns | Unknown alias/effect stays conservative; no guessed pure function | Slices/s, eliminated unknowns, false-pure rejection rate | !64 !63 !70 |
| **P04 Observe** | Pinned source, owned backend, exact checkpoint, input/clock/RNG plan and budget | `original_witness`: run/session/epoch, trace, physical I/O, state deltas, first/last observations | Separate observed versus remembered; partial effects and partial restore never treated as fresh proof | Traces/s, witness bytes, oracle/setup cost, reproducibility | !30 !41 !71 !72 !73 |
| **P05 Carve** | `effect_summary` and optional `original_witness` | `boundary_candidates`: entry/exit, typed ports, guards, effects, alternatives and minimal counterprobes | Agent may select uncertain intent, not silently upgrade a hypothesis | Boundaries proposed vs qualified, agent interventions per boundary | !64 !70 !47 |
| **P06 Map** | Candidates, exact source/flow identity and declared contracts | `udl_projection`: immutable source-to-semantic links, overlapping backings, residual/unsupported operations | Every mapping retains provenance; missing op does not become NOP | Automatic source mapping %, unknown residuals, mapping time | !45 !65 !61 !69 |
| **P07 Compose** | `udl_projection`, selected supported UIL profile, resources | `uil_candidate`: typed behavior module, state/effect plan, explicit residuals, profile adapters | Validate widths, signedness, alias/array types, guards, resource identity; never insert general Python as mandatory IL | Type/check failures caught, module reuse, token/manual edit cost | !24 !43 !48 !49 !50 !66 !70 |
| **P08 Qualify** | Exact original independent witness/oracle, `uil_candidate`, matched vectors/schedules | `source_uil_receipt`: passing domain, proof assumptions, differential observations, counterexamples, unknown | Reject same-VM-only replay as independent equivalence; include negative controls and effects | First-divergence latency, qualified path %, false passes | !59 !63 !65 !69 |
| **P09 Bind** | Qualified UIL/effect contracts, target capability and provider catalog | `provider_lock`: exact implementation/backing IDs, typed service adapters, swede tickets for gaps | Existing qualified provider first; swede = candidate until independently qualified | Cache hit %, swede count, time per newly admitted contract | !57 !58 !66 !65 |
| **P10 Build** | Qualified UIL + provider lock + ABI/startup/storage/service constraints | `udc_artifacts`: code/assets/shell, exact build/toolchain hashes, declared retained dependencies | Refuse unsupported services; never erase semantics to make target compile | Compile time, bytes output, ABI violations caught, build determinism | !24 !28 !63 !66 |
| **P11 Compare** | Original, UIL and produced target with matched initialization and effect policy | `target_receipt`: separate original↔UIL, UIL↔target and composed runs, state/effect/timing/first difference | A runnable binary is not parity; compare observable effects, partial mutation and wrong-provider negatives | Accepted traces/s, mismatch rate, time to first divergence | !24 !61 !70 !75 |
| **P12 Tune** | Pinned qualified baseline and equivalence boundary; candidate UDC variants | `optimization_trial`: candidate hash, before/after cost, proof and replay, rollback link | Only reversible, qualified transformations; do not optimize away timing or externally visible effects | Median/p95 runtime, size, RSS, energy/trace, proof overhead | !63 !41 !64 |
| **P13 Deliver** | Qualified stage closure and requested output formats + native/release policies | `delivery_receipt`: complete artifact list/hash, offline dependencies, fresh install/run tests, accessible download, limitations | A tag, successful tests, or produced ZIP alone ≠ delivered; no falsely advertised offline kit | End-user cold-install success, size, verification time, missing files | !71 !78 !27 !42 |

**Milestones:** the P00–P13 map is per-stage granularity. The proposed [M0–M8 / G0–G7](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/docs/maturity-generalization-20261103/docs/milestones/2026-11-03-generic-reconstruction-gates.md) in !64 and [CHIP-8 G0–G7](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/65) remain **end-to-end qualification gates**, not aliases for these stage IDs.

## Stage I/O envelope: common minimum (proposed only)

Each stage records an **immutable invocation** and a **readback-verifiable output**. The following is an illustrative receipt shape, not a live command or `fdisbull-*` schema:

```json
{
  "phase": "P07 Compose",
  "operation_version": "declared-tool-revision",
  "input_artifact_ids": ["exact-content-id"],
  "profile_lock_ids": {"environment": "...", "isa": "...", "target": "...", "engine": null},
  "source_version_id": "exact-original-source-and-mapping",
  "session_context_id": null,
  "status": "candidate",
  "outputs": [{"kind": "uil_candidate", "sha256": "..."}],
  "qualification": {"level": "unverified-candidate", "domain": "...", "assumptions": []},
  "unknowns": [],
  "dependencies": ["toolchain", "contracts", "quirks", "reference-oracle"],
  "metrics": {"wall_ms": null, "cpu_ms": null, "peak_rss_bytes": null, "agent_tokens": 0},
  "next_stage_eligible": false
}
```

Rules:

1. `status` is workflow outcome; `qualification.level` is claim status; they must not be collapsed. A tool exit 0 is not semantic proof. The fields above are **illustrative**, not a proposed production status enum.
2. Always carry exact source/member/mapped IDs and source-relative address domains; distinguish physical source bytes from selected loaded/mapped bytes.
3. Separate pure definition caches, semantic qualification caches, and state-specific original observation caches. A modified source, ABI, effect contract, runtime/quirk, oracle or provider invalidates **only descendants whose dependency closure changed**.
4. Cache key must include full transitive input artifact IDs, tool/code revision, target ABI, profile quirks, semantic scope, and relevant observation epoch/seeds. Never use a source hash alone to reuse a runtime readiness receipt.
5. Every refusal preserves first unsupported boundary and actionable minimal ticket. A cold agent gets one unresolved source-bound question, available alternatives, evidence, bounded attempts and a measurable proposed test.
6. An effect provider must report resource identity, ownership, sequence, clock, confirmation/partial completion and chosen implementation, not just a generated API call. The existing `pending_host` plan is not an executed host effect.
7. Privacy/license gate: do not put purchased/proprietary original binaries, private FDBs, emulator states, screenshots or ROM-derived payload bundles in Git or generic public packages.

## Individual optimization method

**One phase, one controlled change, one frozen workload.** Optimize only after the current stage's output contract and negative/refusal tests pass.

- **Baseline:** record source/profile, implementation SHA, normalized output hash, test domain, wall/CPU/p95, peak RSS, bytes read/written, cache hit/miss, external calls, manual operations and agent tokens. `P04` also records guest-time and clocks; `P11` compares full effects; `P13` checks cold user installation.
- **Change:** vary exactly one parse strategy, worklist scheduling policy, proof vector, slicing policy, cache configuration, provider or build optimization. Reject any changed semantics/effect order not explicitly authorized as a versioned variant.
- **Acceptance:** identical canonical facts for deterministic transforms; equivalent qualified behavior for semantic stages; independent original and target witnesses on an admitted domain; and improved relevant cost distribution without increasing unknowns or false positives.
- **Regression:** unchanged source/profile uses cache; change one source byte, host quirk, signedness, ABI, provider, resource, timing policy and independent-oracle version and verify the intended downstream invalidation set. Inject missing offline wheel, corrupt archive hash and inaccessible download URL.
- **Output:** retain trial receipt and original reference so optimization is reversible. Promote nothing automatically when the proof times out, an effect is unknown or native acceptance is unavailable.

**Practical priority from !64:** P00/P01/P13 provenance and package closure, deterministic typed adapters across P02–P11, P08/P11 independent differential checks, and narrow P05/P09 agent exception tickets before sophisticated P12 superoptimization. Avoid spending agent tokens moving JSON between operations that deterministic software can connect.

## CHIP-8 first end-to-end experiment

Use !61's six **deliberately selected**, bounded classic ROMs only as the initial corpus: 26 of 34 naturally observed non-legacy instruction **families** under the authored VM, not 76% of programs in the wild. Preserve separately its 132 adjacent family pairs, 244 triplets and eight synthetic gap probes. Two decoders agreeing under a shared specification is not historical interpreter proof.

- Freeze one ROM/edition, dialect, 64×32 display, keypad, clocks, RNG and quirky shift/load semantics under P00/P01. Collect exact P02/P04 source-PC-word traces, not all syntactically possible encodings as executed coverage.
- Produce one real source-bound P06 UDL mapping and P07 UIL **for the complete admitted trace**, including memory, stack, VF, timers and display effects or explicit residuals. P08 must compare with an **independent** CHIP-8 oracle or trusted specification vectors before promotion.
- Use !69's **20 manually authored Python family emitters** only as candidate P09/P10 providers. Its 54,198 same-pilot-VM matched steps (45,584 specialized, 8,614 fallback) show a hybrid implementation, not a completed universal UDL→UIL→UDC path.
- Run separately (A) authored/assembled rare-instruction programs, reimport/shred/lift and (B) swede providers against independently known semantics, and (C) **blind** 1/2/3 consecutive source-instruction semantic gaps. Do not confuse these with !58's 1/2/3 connected scalar C-block swede experiment.
- Finish P11/P13 with a **fresh-user offline install and execution**, then a held-out ROM/author/quirk profile demonstrating the environment and ISA packages are reusable without re-research.

## Integration and publication policy

Use the [MR board](agent-handoffs/GITLAB_MR_BOARD_2026-11-04.md) as an **index**, not as permission to merge. Existing MRs own implementations. This document adds no duplicate engine, new schema or command; comments and review corrections outrank stale MR titles. !59 has a substantive original-binary correction note; !43/!49 document source-bound validator issues; !67 and !68 overlap a PE writer; !69 is an explicit **paused** handoff; !71/!78 still own exact-source native CI and release policy. Never represent !78 as a released v0.32.0 until its required gates pass.

**Completion criterion for this proposal:** adopt/revise names and receipt contracts via review, then implement the smallest tested coordinator around **existing APIs**. No user-facing file is deemed downloaded unless its local bytes and hash were verified.