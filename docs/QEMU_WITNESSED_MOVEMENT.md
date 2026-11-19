# Witnessed held-key movement on QEMU DOS

`debug-move`, `QemuDOSProcessSession.move` and the `move` saved-script operation
retain the existing movement signature and `fdisbull-movement-result-1` result.
This first native scope supports held keyboard controls, explicit runtime RAM
scalar witnesses, predicate arrival/settling, and sample-based progress. It
requires one owned stopped CPU, the explicit virtual clock profile and native
input scheduling. Availability does not qualify the whole migration surface.

## Controls and observations

The start macro consists of `keyboard.key-down` steps and returns every acquired
lease exactly once. The stop macro consists of `keyboard.key-up` steps and
consumes exactly those leases through typed `$start.outputs.<name>` references.
The macro set, start/stop names and other control arguments must be literal.
Public macro cleanup remains unchanged. The private prospective check admits
only the future leases proven to be returned by that exact start; actual
ownership is checked again when the stop executes.

Each observation uses the existing `runtime_memory` scalar form with a binding,
type, optional byte offset and byte order. Binding admission, immutable witness
bytes, owner/process identities, restore epoch, RAM extent and address-context
checks remain those of the runtime RAM API. A runtime witness does not establish
an allocation, task or source-symbol lifetime. A full restore invalidates old
bindings; callers can establish a fresh independent witness afterward.

The first scope refuses timed press/type controls, source-address `memory`,
register/status/frame observations, scene/map geometry, coordinate targets and
frame-based progress before input. It does not infer a game variable from a
machine address or a completed guest frame from a display publication.

## Execution and stopping

One inherited host deadline and the unchanged owner lock cover admission,
physical controls, observation, cleanup and evidence publication. Known literal
script fields are validated independently before any earlier script effect.
Ordinary outer references may supply observation and budget values; the sole
local exception is the validated stop lease path inside `move.stop.args`, even
when an outer binding is also named `start`.

Newly queued makes and breaks are each armed once with the existing native
input schedule at a declared positive delay of **1 ns**. A bounded native clock
advance owns that attempt. This avoids racing a host QMP send against a fast
virtual cutoff. Arm and dispatch receipts remain evidence of native callbacks;
the declared guest RAM predicates supply the separate observation of progress
and settlement. The adapter neither rearms nor retries an interrupted batch.

`guest_ms` and `cleanup_guest_ms` denote milliseconds of `QEMU_CLOCK_VIRTUAL`.
The result also reports measured nanoseconds and whether native clock coverage
is complete. Polls are stopped observations bracketed by an unchanged native
clock and owner epoch. Poll/evidence/guest budgets remain finite.

Arrival becomes success only after the stop has released the owned leases, the
schedule and Python queue are empty, the declared settle predicate holds, and
the destination remains true. A caller's existing input causes an unchanged
rejection. The first breakpoint, hook, DOS return, uncertain native stop or
incomplete dispatch is retained; the adapter closes its owner without running
cleanup through that stop or fabricating releases. Uncertain failures preserve
their original receipt even if journal cleanup also fails.

## Evidence scope

The authored COM fixture owns IRQ1, records actual make/break bytes, and counts
BIOS timer ticks without video observations. Its position changes only while
the key is held; it reports settlement after two quiet ticks following release.
The paired goal compares those guest facts and neutral ownership on QEMU and
DOSBox, without requiring equal progress after different emulator intervals.
Separate witnesses cover an IRQ breakpoint before cleanup and an existing
caller hold. Tests establish only their executed, source-pinned cases; they do
not promote a campaign or change the default backend.

The local execution passed all four native/paired cases on QEMU ELF SHA-256
`71bef609647922544bfca23811caa0c08843a09d6b48c70293ab5ebd6cdb1a40` and DOSBox ELF
`d9236f1178855524a74516eb37cbb636431f9bdec599d9d675e6d69ea6309251`.
All owned processes were reaped. The affected host gate passed 186 cases; two
unselected legacy native tests were skipped. The first native attempt is retained
as failed evidence: it exposed host-QMP delivery racing the virtual cutoff,
which the one-shot native batch composition addresses without retrying input.
