# Bounded model checks

For first use and source-to-model acceptance, follow the
[repeatable reconstruction recipe](reconstruction.md).


Use the optional genuine `z3-solver` extra when a small explicit model can
disprove a decompiler hypothesis or test a recovered rule. Compare finite-width
arithmetic, readiness implications or guarded semantic transitions through
`proof-check` (Python `project.proof_check` or `session.proof_check`, saved
scripts `proof-check`). A proof is about the supplied model; this checker neither
parses C/C++, lifts arbitrary machine code nor implements a complete UIL runtime.

## Bind the subject and correspondence

Retain source executable/resource identities and byte version; model, mapping
and adapter revisions; and runtime/backend identity when runtime observations
are compared. Record the canonical model identity, numeric semantics, admitted
input domain, assumptions, clock/RNG or external-service exclusions, bounds,
timeout, solver version, result and exact claim ceiling.

The built-in receipt binds its documented fields. Put additional identities
and correspondence evidence in supported evidence records or companion notes;
do not invent fields in strict proof or shared-IL schemas. Authored source/node
provenance remains a claim until separately qualified. A valid formula and a
genuine solver do not establish the source-to-model mapping.

## Keep knowledge and check families separate

Distinguish known true, known false and unknown. Missing or conflicting samples
must not become false, absent, clear, ready or stalled. Encode knowledge flags
explicitly through supported expressions where needed and state their meaning;
do not constrain an unknown value as though it were observed. Preserve competing
models or reject a conflict rather than resolving it by insertion order.

Choose bit widths, wrapping, comparisons and signedness from the qualified
source contract. Modular bitvectors are not implicit C signed-overflow
semantics. Keep every relevant unmodeled effect visible: memory and aliasing,
flags, callers, intermediate commits, event order, time/RNG and persistence can
make equal register outputs insufficient.

World references, containment, geometry, movement policy, readiness and finite
event traces are different questions. Existing geometry/readiness checks answer
their narrow contracts. The expression checker and guarded-transition builder
do not provide complete world, containment or trace validators. Do not encode
an opaque unsupported claim and inherit validation from expression equivalence.
Use [semantic-contracts.md](semantic-contracts.md) for operation boundaries.

## Interpret the actual result

| Result | What it establishes |
| --- | --- |
| `equivalent_under_assumptions` | The admitted modeled outputs agree under satisfiable assumptions. |
| `counterexample` | A model input distinguishes the expressions; investigate it against the original. |
| `vacuous` | Assumptions are inconsistent; no behavioral equivalence is established. |
| `unknown` | Solver uncertainty or a limit prevents a conclusion. |
| `unavailable` | The required proof capability is unavailable. |

Invalid formats, types or unsupported expressions can be rejected before a
receipt exists. Preserve that validation error; do not invent a returned status
or call it a game defect. Recheck source/version and assumption dependencies
before reusing a proof. Test a discriminating bounded claim first, then continue
the remaining obligations needed by the requested conclusion.

For Zork-like templates, bind the exact story/source and semantic IR version,
canonical intent, pre-state, guard, expected state delta and ordered events.
Keep retail and source-built stories distinct. Check supported transitions
individually and retain unsupported rules. Prose resemblance, a finite transcript
and a local proof cannot certify a full game conversion.
