# Native AGI runtime implementation

The implemented interface and explicit compatibility decisions are documented
in [RUNTIME.md](RUNTIME.md). This file records the reconstruction scope and
acceptance plan; candidate-specific verification belongs in its retained receipt.

This is the continuation of PR #102 (`a2bd8eb3ed9354067a995f066654bf399696aabc`).
The unpushed 19-file candidate recorded by the previous agent was unavailable in
its recorded recovery locations. This work is reconstructed from the published
source; its results are new results, not a repetition of that candidate's claims.

## Contract

The target is the explicit nominal AGI 2.917 opcode catalog, actions 0–173 and
predicates 0–18, plus IF/GOTO. The existing scalar, view-binding and draw-intent
pilots keep their admission rules. A separately selected runtime profile owns
variables, flags, strings, parser, inventory, controllers, LOGIC calls and scan
starts, resources, actors, deterministic ticks, text and picture state. External
interactive operations use identified, resumable requests. An unsupported or
failed operation never becomes a successful no-op.

The canonical C decoder remains the only instruction parser. The broader
runtime is portable native C, called by the QEMU target through one-instruction
TCG helpers. Its immutable LOGIC bank and actual LOGIC/PC identify instructions;
the QEMU trampoline contains no cached guest operands and cannot retain another
LOGIC's decoded instructions. Future direct TCG lowering can use the same
semantics without adding a host bytecode interpreter.

DISASM and SCENE controls affect observation only. With both disabled the
runtime does not append observation records. Native state snapshots, executed
scene output and static descriptions remain explicitly distinguishable.

## Work and acceptance

- Complete typed descriptors, preserving legacy profiles and contextual limits.
- Implement complete native action/predicate state transitions, short-circuit
  evaluation, bounded calls, exact pending/resume and deterministic input/ticks.
- Adapt the already approved GPL-2.0 Sarien mechanisms for actor motion,
  pictures, VIEW pixels and priority composition, recording provenance.
- Load bounded immutable resource packages and expose complete stopped state,
  execution observations, scene planes and effect completion through QOM.
- Exercise authored interaction programs and independent expected results,
  including malformed resources, failures, calls, ticks and all observation
  masks. Native QEMU results must bind the exact applied source and binary.
- Reuse recovered PQ1/KQ1 development inputs for scene reconstruction. Do not
  open SQ1/LSL1 held-outs. Do not put original game bytes in Git.
- Save source checkpoints to the authorized GitHub/GitLab branch and keep
  recovery checkpoints on the board. Hosted CI, releases and the separate
  QEMU/DOS parity work are outside this change.

Completion is not established by this plan, descriptor counts, compilation, or
tests skipped for a missing runtime. The final receipt must state actual tested
scope and remaining engine/device limitations.
