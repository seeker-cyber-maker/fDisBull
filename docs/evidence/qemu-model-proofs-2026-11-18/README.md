# QEMU bounded host proof checks

The public `debug-proof-check` route and saved-script `proof-check` operation now
use the existing project model engine with exact project, source, version and
debugger-run provenance. See the [contract](../../QEMU_MODEL_PROOFS.md) and
[pinned verification](verification.json). This is host model checking; no
assertion that the model describes the guest follows from associating a run.

An independent 61-case run passed, including four actual earlier-write
regressions found during review. Partially referenced operators now have to
permit at least one supported operator family for their known arity and operand
types. Seven valid partial cases remain admitted. Fully resolved models retain
the existing grammar: a deterministic 10,000-model comparison found identical
acceptance, exception class and canonical encoding (600 accepted, 9,400 refused).

The public QEMU and DOSBox host adapters agree on actual Z3 equivalent,
counterexample and vacuous results. Unknown and unavailable result routing has
explicit solver-boundary tests. Proof and debug-event persistence, reopening,
solver budget admission and late-result retention are covered. An adjacent
selection passed 164 cases with 20 intentionally skipped native cases; these
counts overlap with the focused selection. No emulator was launched for this
host-only slice, and no migration qualification changed.
