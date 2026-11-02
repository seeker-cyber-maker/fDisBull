## Purpose

Continue the Syndicate asset/missing-code investigation and hand implementers concrete tool improvements. This is a follow-up to #69, not a replacement for its diagnostic-recovery methodology. The inspected production base is `90e748c8bc6a4f068f9136f4d4ec989672421a03`; the private research runtime remained fDisBull0.26.0.

## New findings

- 176 original-code line/rectangle probes matched complete-buffer oracles, guards and preserved registers. Three previously blocked tail dispatches, plus a newly examined sibling, use a conditional **0..16** index after caller setup and a decreasing loop.
- Five local Z3 outcomes, including negative controls for lost lower bounds/order, and exhaustive enumeration of **202,880 endpoint pairs** support the arithmetic contract. Original helper/source binding checks remain separate from model proof.
- 86 sprite/animation probes matched: 64 authored cases, 16 uses of one real sprite, and six original higher-caller invocations. The latter use three frame IDs sharing **one** five-element chain, not three independent visuals.
- A vertical-reflection path has a one-row-shifted destination anchor even through the original caller. The comparison preserves it instead of silently substituting a conventional flip. Intended artistic anchoring and player-visible bug status remain unknown.
- Candidate decoding advanced **67,838 -> 68,186** instructions and **227,447 -> 228,882** unique bytes, without inflating the **630** function candidates. Exact original/mapped identities, all **897** restored selected asset identities and the TEST/STOSB overlap are retained.
- A source-free replay from the old checkpoint reproduced all 68,186 instruction rows. The 262 native calls exercised 2,525 distinct original starts and reaped every child. No full-game/DOS4GW execution or driver playback occurred.
- LX driver descriptor-return candidates enter interrupt-control code; they cannot be qualified by treating CLI/STI as host no-ops. Coincident preferred bases require module/load identities.

## Concrete recommendations

1. Public **candidate-only seeding**, separate from function hypotheses and resolved indirect edges. The reviewed `analyze(start=...)` inserts a user-seed function; the study needed the private `_queue_code` seam.
2. Conditional caller/loop range records retaining alias, bypass, table-mutation and callee-preservation obligations. A nearby signed upper bound is insufficient.
3. Qualified original-routine preparation/observation capsules, with explicit ABI, permissions, source/module identity, before-instruction sampling, finite budgets, expected writes, failure outcomes and independent child cleanup.
4. Resource-domain and shared-chain provenance, exact graphics footprint/anchor semantics, and environment-aware external-driver boundaries.
5. Immutable/versioned evidence paths with source-free summaries and separately private payloads.

Eight DG acceptance criteria are prospective product requirements. This PR implements none of those production features.

## Files and validation

Adds only:
- `docs/DIAGNOSTIC_GRAPHICS_FRICTION_2026-10-31.md`
- `docs/evidence/diagnostic-graphics-2026-10-31/check_contract_models.py`
- `docs/evidence/diagnostic-graphics-2026-10-31/model-checks.json`

The public authored checker requires no game files. With Z3 5.3.2 it reproduced all 202,880 pairs and all five expected solver outcomes. Its receipt binds the script digest. Missing optional Z3 is unavailable unless `--require-z3` requires failure; it is not a pass.

The original-code probes use an authored Linux x86-64 launcher in explicit 32-bit compatibility mode, not DOSBox, DOS/4GW, a hardware model or a general malicious-code sandbox. Inputs and globals are diagnostic preparations. These tests do not establish ordinary reachability, whole-game correctness, all source paths or native-driver behavior. The pixel oracle is independently written but source-informed, not blind rediscovery.

Local Python syntax, JSON/receipt identities, Markdown links/fences, privacy screening and a clean application of the patch were checked. No full repository suite, release, global installation, game-file upload or shared branch change was performed. Related #41/#53/#57 capabilities retain their separate tested scope.

The draft was prepared locally because the research session exposed GitHub read operations but no write action. Publication is a separate operator step; no GitHub CI result is claimed in this body.
