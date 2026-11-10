# Blast-radius influence pilot: path-specific atomic state slots

This adds fdisbull.influence_pilot.analyze_linear_influence for a bounded, declared, closed **linear path**. Each instruction-like event names normalized atomic reads/writes and explicit per-output dependencies. It emits entry liveness, required per-step outputs, discardable-written *candidates*, versioned sparse def-use edges and backwards reachable influence from the specified observer/sink values.

Closed semantics and closed observers MUST be affirmed by the caller. Unknown indirect writes, interrupts, PUSHF, traps, memory aliases, loops and device effects cannot be hidden under a don't-care label. This module does not decode original instructions, prove unknown code or generalize to unsampled CFG paths. The graph/projection is a candidate proof input, not a proof.

Focused tests cover CMP -> JZ (only ZF required), CMP -> INC -> JC (carry survives INC), overwrite kills, reject unknown observers, measured projected equality. Follow-up slices: true x86 flag decoder, partial register aliasing, CFG/loop fixed points, side-effect modeling, saved proof masks, SMT equivalence + rewind/taint negative tests.

Separate MR to avoid coupling QEMU/LLVM core and Harness² QA routing to correctness-sensitive semantics.
