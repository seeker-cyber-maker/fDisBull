# Bounded model checks

Use the optional genuine `z3-solver` extra when a small explicit model can cheaply disprove a decompiler hypothesis or test a recovered rule. Compare finite-width arithmetic, readiness implications or guarded semantic transitions through `proof-check` (Python `project.proof_check` or `session.proof_check`, saved scripts `proof-check`). Persist scope, assumptions, source identity, modeled node and evidence alongside the result.

A counterexample supplies inputs to investigate in the original program. `equivalent_under_assumptions` applies only to the provided model and assumptions; first require satisfiable assumptions. `vacuous`, `unknown`, `unavailable` and unsupported operations never establish equivalence. Modular bitvectors are not implicit C signed-overflow semantics. This checker neither parses C/C++, lifts machine code automatically nor implements UIL. Explicit source/node provenance supplied to a model builder is caller asserted until separately qualified.

For Zork-like templates, bind the exact story/source and semantic IR version, canonical intent, pre-state, guard, expected state delta and ordered events. Keep retail and source-built stories distinct. Check supported transitions individually and retain unsupported rules. Prose resemblance, a finite transcript and a local proof cannot certify a full game conversion.
