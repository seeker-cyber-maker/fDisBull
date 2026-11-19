# Native macros and witnessed RAM

At exact source `86733c87d21340d5391da73990a2ef48527b81e2`, the combined
Linux native selection passed **four cases with zero failures, errors or
skips**. Source, native binary and boot inputs remained unchanged. No process
using the qualified native executable remained in the execution namespace.
The [verification record](verification.json) retains exact source/native
identities, test nodes and private receipt hashes.

## Macros

Two actual ATTT witnesses cover the public `debug-macro` route, saved-script
macros, typed native input ownership, two observed board moves and cold
reopening of the persisted result. A large response is retrieved through
`output-select` and `output-export`; those reads do not replay input. An
observation-only inner macro followed by an outer assertion failure preserves
the caller's pre-existing key lease and does not run the suffix.

The interrupted-input witness stops at the original game's board-write
watchpoint between key make and break. It retains the first native GDB reply,
records one dispatched make and one cancelled break, never arms the later
chord, and closes/reaps the owner without injecting another input edge.

The earlier native test incorrectly indexed an output-reference envelope as
the macro body. That failure is retained. The correction changes tests only
and adds a host spill regression plus the real interrupted-chord case.

## Runtime memory

Two authored native witnesses exercise actual flat protected LE and paged V86
contexts. Explicit physical and observed unpaged linear bindings read the
expected data, reject incorrect write preimages, verify a live edit, retire
source authority through the existing writer, and consume a changed witness.
A full owned-machine restore replaces the process and epoch: old names and
IDs fail, while a fresh physical witness can observe the restored bytes without
claiming that the original DOS source mapping was restored. Paged linear
bindings refuse; an explicit physical witness remains available.

Independent review reproduced and corrected three host defects before native
acceptance: incomplete literal preflight in scripts, missing closure after a
direct admission transport failure, and loss of the primary timeout receipt
when cleanup itself failed. All 69 independent host cases passed after the
fixes. Broader host selections overlap and include explicitly optional native
skips; their counts are not added to the four executed native cases.

See [macro semantics](../../QEMU_MACROS.md) and the
[runtime RAM contract](../../QEMU_RUNTIME_MEMORY.md). The RAM adapter does not
infer source, selector, task or allocation ownership from an address. Movement,
scene, completed-frame, paged-linear and task-private contracts remain
separate. These results do not change the default backend or migration gates.
