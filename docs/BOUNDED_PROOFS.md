# Bounded expression checks

The required `z3-solver` runtime dependency checks a supplied model, not the correctness
of its relationship to instructions, recovered C/C++, runtime observations, a
game, or a future UIL export. No C parser, decompiler, or UIL engine is implied.
The caller supplies the correspondence and supporting evidence. See the
[Z3 bit-vector guide](https://microsoft.github.io/z3guide/docs/theories/Bitvectors/)
for signed and unsigned bit-vector operations and the
[Z3 Python guide](https://microsoft.github.io/z3guide/programming/Z3%20Python/Introduction/)
for solver outcomes.

`check_equivalence(spec, timeout_ms=1000)` accepts JSON-compatible data:

```json
{"format":"fdisbull-proof-1","scope":"authored 8-bit example",
 "variables":{"x":8},"assumptions":[],
 "left":{"op":"add","args":[{"var":"x"},{"const":1,"width":8}]},
 "right":{"op":"add","args":[{"const":1,"width":8},{"var":"x"}]}}
```

Leaves are `{"var":"name"}`, `{"const":unsigned_integer,"width":bits}`,
and `{"bool":true}`. Variables and constants have widths 1 through 256.
Operations are binary `add`, `sub`, `mul`, `band`, `bor`, `bxor`, `eq`,
`ult`, `ule`, `slt`, `sle`, `and`, `or`; unary `bnot`, `not`; and ternary
`ite` (Boolean condition, equal-typed alternatives). Operand types and widths
must agree. Arithmetic is modular; signedness is explicit in comparisons.
Division, shifts, memory, pointers and C-specific signed arithmetic are not
implemented. To investigate C semantics, the caller must encode appropriate
definedness preconditions within this vocabulary and document the mapping;
unsupported behavior must remain unknown rather than silently wrap.

Assumptions are checked for satisfiability before comparison. The statuses are
`vacuous` for inconsistent assumptions, `counterexample` with input bits,
`equivalent_under_assumptions`, `unknown` on solver uncertainty or timeout, and
`unavailable` only when a source checkout is missing the required Z3
dependency. The time budget is shared by both checks.
Equivalent means only equality of the supplied expressions over their declared
finite-width inputs under the supplied assumptions. The API bounds expression
size, depth, node count, width and solver time; unsupported input is rejected.

`project.proof_check(spec, version=..., author=..., evidence=[...])` stores an
immutable, hash-checked record including selected byte-version and source
digests, specification, solver version, assumptions and result.
`project.proofs(version=...)` and `project.proof_info(id, version=...)` select
the exact version and verify record integrity. A child patch does not inherit
the parent's result. Evidence is caller-supplied context, not independently
verified provenance; hashes detect changes, not truth or authenticity.

## Reusable model adapters

The Python builders below return the same JSON specification accepted by
`check_equivalence` and `project.proof_check`. They reject invalid expressions
before solving or storing anything. `scope` must describe the exact modeled
claim. The builders do not recover expressions from binaries or execute them.

```python
from fdisbull.proofs import arithmetic_model, readiness_model, guarded_transition_model

x = {"var": "x"}
one = {"const": 1, "width": 8}
zero = {"const": 0, "width": 8}
inc = {"op": "add", "args": [x, one]}

# Explicitly modular arithmetic, including unsigned wrap at 255.
arithmetic = arithmetic_model({"x": 8}, inc, zero,
    scope="8-bit increment compared with zero")

# A readiness condition implies a requirement only for inputs where it holds.
ready = {"op": "ult", "args": [x, {"const": 10, "width": 8}]}
requirement = {"op": "ult", "args": [x, {"const": 20, "width": 8}]}
readiness = readiness_model({"x": 8}, ready, requirement,
    scope="example readiness implies the requirement")

# A candidate adventure rule, not a UIL parser or a game engine.
guard = {"op": "eq", "args": [x, zero]}
transition = guarded_transition_model({"x": 8}, guard, inc, one,
    scope="candidate door transition when the state is zero",
    source={"kind": "candidate-rule", "sha256": "a" * 64,
            "node": "room/door/open"})
```

The arithmetic adapter accepts only `semantics="bitvector_modular"`. It does
not model C/C++ integer promotions, signed overflow, division by zero, invalid
shifts, pointers or other undefined behavior. A caller must establish and
encode the relevant language semantics and definedness separately; asking the
adapter for another semantics is rejected rather than treated as proof.

Readiness and transition adapters place the readiness condition or guard in
the assumptions. An unreachable condition yields `vacuous`, never a successful
implication. Explicit `assumptions` may add path constraints. Transition source
provenance consists of a `kind`, a lowercase 64-character SHA-256, and a node
identity. It is stored in the specification and result as a **caller assertion**;
the checker does not retrieve or verify the source, verify that the node exists,
or prove that its model faithfully represents that node. A proof for one
guarded expression does not establish an entire story, game or UIL export.
