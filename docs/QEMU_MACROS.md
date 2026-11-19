# Named input macros on native QEMU DOS

`QemuDOSProcessSession.macro`, the `debug-macro` JSON method, and the `macro`
saved-script operation share the existing immutable `fdisbull-macro-set-1`
definitions. Definitions remain bound to their exact project byte version and
source identity. Native DOS sessions advertise `input_macros`.

This adapter expands a bounded route over already available QEMU primitives:
keyboard down/up/state, timed keyboard press/type, run, virtual observation wait,
registers, machine memory, status, screenshots and assertions. Nested macros
retain the shared depth, step, authority and typed-argument limits. Scene and
completed-frame operations require their separate QEMU contracts.

## Native ownership and time

A QEMU held-key lease is the native `session_id:token` string. A macro can accept
it as an `input-lease` argument or pass an earlier key-down's `.lease` through a
nested macro output. It is checked against the live VM's physical input ledger.
It is never translated into a DOSBox lease or shared between unrelated VMs.
Lease arguments are supplied for the current live owner; saved defaults retain
the existing portable macro declaration grammar.

The entire macro holds the machine lock and one host deadline, intersected with
any caller, session, VM and channel deadlines. Native operations retain their
own guest-clock semantics. In particular, native `run` has no DOSBox `guest_ms`
or fast-forward option. Use the existing QEMU `wait` operation for a bounded
predicate wait in the explicit virtual clock profile.

`keyboard.press` and `keyboard.type` passively arm their existing native plans.
Include an explicit run or wait to resolve the plan. The macro does not insert
a run, finish a cancelled suffix, retry an input edge, or resume after an
unexpected stop. A matching wait predicate alone cannot override unresolved
input ownership. A known timed plan followed by a wait must fit, with one poll
tail, within that wait's declared virtual budget.

## Admission and cleanup

The full expanded syntax, literal parameters, available primitives and
capabilities, result references, and prospective key ownership transitions are
checked before route artifacts or input effects. Rejected admission preserves
the caller's existing leases. Typed macro arguments are expanded before this
check. Result references are supported in assertions, outputs and typed
key-up bindings; other primitive parameters must be literal after expansion.
An outer saved script cannot supply an unresolved future lease to macro
preflight; pass a currently owned token or express the key-down in the macro's
own nested definition.

The existing primitive adapters still validate their current native state at
dispatch. Execution stops at the first failed assertion, incomplete wait,
unexpected run outcome, or unresolved input boundary. The original execution
receipt remains in the macro's script report. `stop_on_hook` stays enabled.

Successful macros may retain newly acquired active leases only through explicit
outputs. An unreturned new lease or a newly armed unresolved timed plan closes
the owned session. Failure after input effects uses the same terminal cleanup.
Closing invalidates ownership without injecting a release or running through
a breakpoint. Pre-existing leases remain the caller's responsibility when a
successful observation-only macro leaves them unchanged.

## Evidence and scope

Results use `fdisbull-macro-result-1` with `backend: qemu-dos`. They retain the
expanded route, lineage, script receipt, outputs, physical input before/after,
cleanup, and persisted macro artifact. QEMU result references use their own
guaranteed fields; DOSBox-only revision, keyboard queue, or frame identifiers
are rejected. The default DOSBox expansion and execution contracts are unchanged.

`tests/test_qemu_macros.py` exercises public routing, actual project persistence,
the production QMP envelope, physical ownership, timed input receipt handling,
and deadlines against bounded wire/CPU peers. Those tests do not establish guest
consumption. `tests/test_qemu_macros_native.py` provides a separate opt-in witness
using the existing hash-pinned ATTT fixture and prepared native DOS runtime. It
checks preflight preservation, two observed moves through public and saved-script
macros, released input, and cold reopening of persisted macro evidence.

Macro success establishes completion of the declared primitive route. Guest
consumption and target action completion require their own observations;
completed guest frames are not inferred from QEMU display updates.
