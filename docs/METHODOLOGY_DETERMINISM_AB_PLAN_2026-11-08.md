# Methodology determinism review and A/B testing plan

**Date:** 2026-11-08. Author: agent review pass over `release/0.34.0` at
`0203df4a`. Evidence: `src/fdisbull/methods.py` (400 methods), the bundled
`fdisbull-investigate` skill (23 references), `src/fdisbull/operation_goals.py`,
`z_queue.py`, `record_candidates.py`, `serializer_discovery.py`,
`preflight.py`, `docs/CONSOLE_RECOMPILER_INTEGRATION_PLAN.md`,
`docs/CONSOLE_SYNTHESIS_LOCAL_PILOT.md`, `src/fdisbull/console_synthesis/recover.py`.

## Part 1 — process graph and determinism audit

The investigation pipeline has seven stages. The tool already owns the
mechanical middle; the remaining agent-judgment islands are enumerated below
with the cheapest deterministic reduction for each.

### 1.1 Stages and their current determinism

| # | Stage | Deterministic surface (verified) | Judgment island |
| --- | --- | --- | --- |
| 0 | Setup & identity | `preflight --expectations`, `capabilities`, `doctor`, `--version-json` | none |
| 1 | Intake & triage | `identify`, `media-inspect`, `intake-inventory`, `capture-audit`, `gog-list`/`gog-unpack` | target/task framing (bounded by `task-framing.md`) |
| 2 | Static structure | `auto-analyze`, `function-patterns`, `xrefs`, `call-effects`, `define-type` → `apply-type` → `typed-data`, `code-regions` | which candidate to confirm first |
| 3 | Live observation | `memory-search-start/refine/results`, `execution-event-search`, `serializer-discovery` (emits `next_step`) | probe selection |
| 4 | State binding & harness | `serializer_candidates`, `debug-save-scene`, `z-controller`, `capture-action` → named verb | semantic labeling of a field |
| 5 | Work management | `operation-goal` (ready/blocked sets from facts), `work-queue`, `run-work`, `record-frontier` | question ranking |
| 6 | Claim qualification | `proof-check`, `udl-verify`, `memory-accesses`, watchpoints | sufficiency for exploration claims |
| 7 | Meaning & delivery | UIL/UDC generation, receipts, `bind-source` gates | meaning integration |

### 1.2 The four judgment islands and proposed reductions

**J1. Question ranking.** `analysis-approach.md:129` instructs agents to score
candidates "qualitatively, not with fake numeric precision". Every agent
re-derives the same six-criterion rubric (decision value, information gain,
confidence, risk, cost, scope) in free text.

*Proposed: `question-scorecard` schema* (`fdisbull-question-scorecard-1`).
Each candidate question becomes a record with required, validated fields:
`claim` (what settles), `unlocks` (blocked dependency ids), `separates`
(competing hypotheses), `risk` (none/guest/host/external), `reset` (valid
reset identity or none), `cost` (setup/guest/wall/compute), `prerequisites`.
The tool validates completeness and refuses vague entries; ranking stays
agent-side, but the rationale becomes a durable, auditable record instead of
prose. This converts a recurring freestyle step into a schema-checked one.

**J2. Probe selection.** The skill maps claim types to probe families in
tables, but agents re-read and re-apply the mapping each time.

*Proposed: `probe-selector` table method.* Input: claim kind (writer,
absence, trigger, persistence, equivalence) plus available primitives from
`capabilities`. Output: ordered candidate discriminators with cost notes and
their evidence ceilings (a screenshot shows a sprite but not the writer of
health). Pure table lookup over existing evidence; no execution, no new
analysis engine.

**J3. Concept-level frontier.** `record-frontier` diffs changed *files*
between passes; `operation-goal.coverage` tracks component slots. Nothing
seeds *which question to ask next* at the concept level.

*Proposed:* surface the existing `operation-goal` coverage gap as a
first-class listing: uncovered components, known blocks, and their declared
producers. This is a pure projection of data the tool already retains.

**J4. Sufficiency for exploration claims.** `proof-check`/`udl-verify` and the
reconstruction obligation ledger bound replacement claims; everyday
exploration claims ("this word is the timer") rely on agent judgment.

*Proposed:* extend the scorecard so each claim records its completion
condition up front (schema-enforced). "Done?" becomes a field check against
the recorded condition rather than a fresh re-litigation each pass.

**Scope note:** J3 (semantic labeling) and meaning integration remain
irreducibly agent work — that is the product, not the gap. The reductions
above do not remove judgment; they make every judgment deposit a
schema-validated record, which is what prevents "god of the gaps": each
decision point either returns tool-computed state or writes an auditable
justification.

### 1.3 Skill routing gap (pre-existing, unrelated to recent MRs)

The structure/code-pattern parser surfaces — `define-type`, `apply-type`,
`apply-file-type`, `typed-data`, `types`, `set-function-type`,
`function-patterns`, `code-regions`, `memory-accesses`, `add-signature`,
`capture-signature`, `signatures` — never appear in any of the 24 skill files.
`docs/API.md` documents them fully (function-patterns evidence at
`API.md:458-464`, the `apply-file-type` registry at `:117`); cross-project
type-catalog transfer gets one sentence at `workflows.md:229`. Proposed home:
`references/analysis-types.md` (or a `workflows.md` row plus a short section)
covering the typed-data registry, function-pattern evidence kinds, and the
`export-types`/`import-types` provenance rules.

Minor routing repairs, same MR:

- Scene CLI names (`debug-save-scene`, `debug-scene-overlay`,
  `debug-scenes`, …) are taught only as Python API calls in `scenes.md`.
- `memory-snapshot-info` is the one !112 command missing from
  `desqview-and-memory-search.md`.
- The router skill `fdisbull` advertises a "format/container handling" child
  skill that does not exist.

## Part 2 — A/B testing plan: Drag Race (Atari 2600) with sub-agents

### 2.2 What exists today (verified)

- **Console synthesis lane (how NES/SNES/Genesis worked in previous runs):**
  recovered game semantics become shared IL, then synthesized targets —
  `rom-game-lift`, `genesis-replay-*`, `nes-multicart-*`, `shadowrun-*` build
  commands, with `cc65` for NES targets (`AGENT_QUICKSTART.md:713-718`). These
  ROMs are *outputs* of recovery, not analysis subjects. The same lane fits an
  Atari target: synthesize a bounded Drag Race realization rather than
  emulate the original binary end-to-end.
- **6502 CPU recovery:** `console_synthesis/recover.py` already implements
  strict 6502 recovery with an explicit accepted-encoding table (56
  opcode/addressing combinations, bounded forward control flow, explicit
  carries and signed overflow, no permissive unknown-opcode path).
- **6507 = 6502 minus address pins A12–A15 and the PHI2-out/IRQ/NMI lines.**
  The instruction architecture is the same; Drag Race uses a 2K or 4K ROM
  where A12–A15 are effectively fixed, so the existing 6502 subset covers the
  CPU side directly.
- **Decoder modules** are guest-language front ends (AGI, MADS CNV, EMC2,
  Z-machine), not a general 6507 disassembler. `rom-disasm` covers Saturn
  SH-2; `rom-inspect` parses cartridge headers but does not decode 6507.
- **No TIA/Riot emulation backend exists.** The DOSBox-X debugger lane is
  DOS-specific; nothing drives an Atari emulator today.

### 2.3 What the A/B test needs

The user's framing — "cpu module, disassembler, decompiler and debugger for
it in an emulator" — decomposes into four bounded additions:

1. **CPU module (smallest):** extend `console_synthesis/recover.py`'s
   accepted-encoding table from 56 to the 6507-relevant full legal opcode set
   (documented 6502 opcodes; the 6507 sees only the same encodings). Each
   addition keeps the strict no-unknown-opcode rule. Acceptance: existing
   fixtures still pass; each new opcode has a decode + lift + compare case.
2. **Disassembler:** a bounded 6507 linear+sweep disassembler in the existing
   decoder-module style (`decode`, `static_successors` capabilities), driven
   from `rom-inspect`'s cartridge facts. Reads a `.bin` (2K/4K), emits
   address-annotated listings with explicit reset-vector anchor.
3. **Decompiler:** reuse the established route — recover to shared IL
   (`fdisbull-il-1`), not a new C decompiler. The existing recover → model →
   targets chain is the decompiler for this lane.
4. **Debugger/emulator:** two options, in preference order:
   - **Stella with its built-in debugger** as an external backend in the
     existing external-backend pattern (`doctor`'s
     `backend,executable,[...]` contract), giving watchpoints, tracing and
     RAM/TIA state. Requires a thin adapter process.
   - **No emulator at all:** run the *synthesized* C/JS realization headless
     and compare against recorded original sessions (the `compare.py`
     machinery). This is how the NES/Genesis lane qualified work, and it may
     be sufficient for an A/B test that measures *methodology*, not
     emulation fidelity.

### 2.4 A/B design

**Question:** do the determinism additions (Part 1) measurably reduce agent
legwork and improve evidence quality on the same target?

- **Target:** Atari 2600 *Dragster* (Activision, 1980). Small (2K), bounded state
  (position, speed, shift timing), deterministic physics loop,
  well-documented hardware, and famously short execution makes whole-session
  records cheap. Freeware/fixture rules apply: confirm the exact ROM's
  license/provenance before it enters the repository; the private delivery
  stays outside Git per the repo contract.
- **Arm A (baseline):** two antigravity-google/gemini-3.8-flash sub-agents
  work from the current skill + current tool, cold (no recovered answers),
  each with one bounded question at a time per the existing dossier rules.
  They document format facts, recover the bounded physics loop (speed,
  shift timing, acceleration tables, crash), and qualify it.
- **Arm B (treatment):** same sub-agents, same target and budget, plus the
  Part 1 additions: scorecard schema, probe-selector, coverage-seeded
  question frontier, and the `analysis-types.md` routing.
- **Measured:** wall time to first verified fact; number of redundant probes
  (same question asked twice); count of schema-validated decisions vs
  free-text justifications; evidence-recycle rate (facts reused across
  branches); budget stops vs completions. Both arms record receipts through
  `work-queue` so the comparison is data, not vibes.
- **Pass condition:** Arm B completes the bounded physics recovery with
  fewer distinct probes and at least equal claim quality (no unverified
  promotions). A null result is a valid outcome and still a finding.

### 2.5 Sequencing

1. This MR (doc + skill routing repair) — no tool changes.
2. `question-scorecard` + `probe-selector` schemas (pure additive).
3. 6507 opcode-set extension + bounded disassembler (decoder-module style).
4. Stella adapter (optional; only if live-original comparison is wanted
   beyond recorded sessions).
5. Run the A/B arms in parallel worktrees, one controller each, shared
   evidence store per the existing multi-worker rules.

Each step is independently reviewable and nothing blocks the A/B on the
emulator decision: arms can run against recorded sessions (option 2 in
§2.3.4) while the Stella adapter is prepared.
