# QEMU breakpoint and paired COM cold-input evidence

This directory records one bounded slice of QEMU DOS debugging
and paired authored-COM checkpoint behavior on 2026-11-25. The evidence is
limited to the listed test selections and native attempts. It does not qualify
broad DOSBox-X/QEMU parity, migration, or a default-backend change.

## Host and adjacent test selections

The host-selection run of `tests/test_qemu_dos_breakpoints_host.py`,
`tests/test_paired_com_checkpoint_input_native.py`, and
`tests/test_execution_trace.py` completed with 40 passed and 1 opt-in skip.

An adjacent selection of `tests/test_qemu_dos_process.py`,
`tests/test_qemu_machine.py`, `tests/test_debug_timeline.py`,
`tests/test_debug_rewind.py`, and `tests/test_qemu_session_revision.py`
completed with 140 passed and 5 skipped before the final address-shape fix.
After that fix, a selection of `tests/test_qemu_dos_breakpoints_host.py`,
`tests/test_execution_trace.py`, `tests/test_qemu_dos_process_lifecycle.py`,
`tests/test_qemu_checkpoint.py`, `tests/test_debug_rewind.py`, and
`tests/test_qemu_session_revision.py` completed with 125 passed and 6 skipped.
These are separate runs; they are not a single combined-suite total.
The final combined local host selection, including migration inventory and
history/selected-undo checks with both opt-in native nodes in their skipped
state, completed with 268 passed and 13 skipped on this candidate source.

## Native paired authored-COM observations

The final attempt-04 native checkpoint gate passed (1 passed, 9.68 seconds) using
identical authored `CHECK.COM` inputs on DOSBox-X and QEMU. Hot restore on both
engines consumed `k`, observed marker `A5`, and exited with code 37. A fresh
process cold restore on both consumed `k`, observed the marker, and reached
pre-exit `AX=4C25`; QEMU also reported exit code 37. The DOSBox-X cold guest
exit was deliberately not exercised: the native bridge loses selected-PSP
tracking across an unrecognized owner restore. A post-`INT 21h` DOSBox-X
timeout at BIOS does not establish guest exit. Earlier attempt-01 failed on a
harness-flags key and attempt-02 failed because it required DOSBox-X cold
`guest_exit`; a diagnostic QEMU cold run passed. Those attempts remain part of
the history and are not represented as passing gates.

The final paired core-control native attempt-03 passed (1 passed, 6.14 seconds).
QEMU's new `breakpoints.list` and DOSBox-X's list each included the owned
execution breakpoint and source-relative stop. Watchpoint and operation
control surfaces still use distinct schemas. Host review found that the first
adapter candidate treated listing as a mutation in shared history and session
revision guards; the final candidate marks it read-only and verifies that
live history, selected CPU/RAM undo and cooperative revision are preserved.
A poisoned QMP status channel now closes the owner. The QEMU adapter host tests
passed 18 tests. Earlier native attempts-01 and -02 passed before the final
guard and transport cleanup corrections and remain separate observations.

## Identity, private artifacts, and claim limits

The hashes, selected test snapshots, runtime identities, and native
observations are recorded in [verification.json](verification.json). Raw
receipts and inputs remain outside this repository. The private manifest is
identified as `private-attempt-manifest-verified.json`
(`ef277303d746eca63e985b5697ef2d3a37ac60520a0f73e7f90c3484962349ce`); no
private artifact paths or bytes are included here.

This is a bounded local evidence slice. It does not establish general debugger
or DOS parity, identical breakpoint/watchpoint/operation-control schemas,
DOSBox-X cold guest-exit parity, migration qualification, CI qualification, or
a default-backend switch. No private binaries, boot media, FDBs, or emulator
states are included.
