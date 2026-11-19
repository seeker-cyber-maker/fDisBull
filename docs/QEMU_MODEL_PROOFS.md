# QEMU host model proof checks

The `qemu-dos` session supports `debug-proof-check` and the `proof-check`
saved-script operation through `proof_check(spec, timeout_ms=1000, author='agent',
evidence=None)`. Its capability is `bounded_model_proofs`.

This is the existing project proof engine associated with the selected debugger
run and immutable source/version identities. It compares caller-supplied
finite-width expressions. It does not lift guest instructions, read registers
or RAM, validate a source mapping, or establish that an authored model describes
the running program. Caller-supplied transition provenance retains the shared
`caller_asserted_not_independently_verified` status.

## Results and persistence

The shared result schema and meanings are preserved:

- `equivalent_under_assumptions`: the modeled expressions agree for every input
  satisfying the modeled assumptions.
- `counterexample`: the solver found modeled inputs where they differ.
- `vacuous`: the assumptions themselves are unsatisfiable.
- `unknown`: the solver did not establish a verdict within its supported budget.
- `unavailable`: the optional Z3 solver is not installed.

The proof record includes the exact selected version, source identities and a
leading `{'run': run_id}` evidence item. Its `proof-check` event identifies the
stored proof and status. Records remain accessible through the existing project
proof APIs after the database is reopened. A proof check does not acquire a
native lock, dispatch a native control, alter pending input, invalidate execution
history or release a selected CPU/RAM freeze.

## Budgets and saved scripts

The complete host request shares the incoming debugger/script deadline. The
solver receives at most the smaller of the requested timeout and the remaining
host allowance; the actual solver timeout appears in its existing result field.
A request with no remaining allowance refuses before the solver. If a completed
check returns after the host deadline, `TimeoutError.result` preserves the exact
stored proof; no guest cleanup, replay or execution follows from the proof
adapter. Saved scripts stop at that failure using their existing control flow.

Script admission validates every known literal in a partially referenced model,
including keys, expression limits, operation names/arities, widths, constants,
concrete operand types, author, timeout and evidence. It does not resolve a
result reference, invoke the solver or query the guest. Unknown reference values
for an operator still have to permit some supported operator family for the
known arity and operand types. Potentially valid unknown operands remain
admitted. Other unknown reference values
are deferred; the entire resolved model is validated by the concrete shared
grammar at dispatch. A whole-model reference therefore does not establish that
its unknown content is valid. Script calls without an explicit proof timeout
retain the method's 1000 ms default within the script's remaining allowance.

`tests/test_qemu_proofs.py` pairs the public QEMU adapter with the existing
DOSBox session's host proof method using the actual Z3 solver. Unknown and
unavailable result routing also has explicit boundary tests. This is host model
contract evidence, not native-code equivalence or a migration campaign pass.
