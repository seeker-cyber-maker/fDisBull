# DOSBox-X cold selected-PSP candidate — 2026-11-25

This evidence records a bounded DOSBox-X selected-PSP identity candidate in
the separate experimental backend. The complete source patch SHA-256 is
`b009952403f86c52bfe404ef16d0bb2b567c8df8a3f2078d6e35ed932aa5cd15`; the
rebuilt arm64 executable SHA-256 is
`b9c1e0510b413032cab5e034573c3845dbe1e6ed6ba66001dc49bb15b998fa36`.

## Build and candidate checks

Build history is retained as separate outcomes. A guarded four-worker build was
denied before compiler launch by the memory guard. A separate single-worker
build attempt 01 reached `agent_server.cpp` and failed because
`Session::state_changed` was not a member. After a one-line source/regen
correction, single-worker incremental build attempt 02 produced the arm64
candidate above.

Candidate native tests had an initial attempt 01 harness failure comparing an
integer PSP value with its hexadecimal representation; that is a harness
comparison failure, not evidence of a DOSBox behavior failure. Candidate test
attempt 02 passed 3 tests in 2.79 s. A full-file run at attempt 03 passed 16
tests in 5.49 s. Two native legacy checks also passed against the old installed
binary; they do not establish that the rebuilt candidate is installed.

The direct native failure gate at attempt 05 passed in 0.78 s. It supplied a
missing absolute state-file path through the direct `state.load` RPC while the
session was stopped. The session became `Failed`, could not resume, emitted no
`guest_exit`, and its owner was reaped. Full `tests/test_dos_guest_exit.py`
attempt 06 then passed 17 tests in 5.80 s. Attempt 03's 16-test result remains
a separate earlier run.

This failure gate covers a missing-file error before loading starts. It does
not demonstrate behavior after partial or mid-load state corruption.

## Paired authored COM observations

Strict candidate paired attempt 02 passed in 9.95 s. Both DOSBox-X and QEMU
passed hot and separate-process cold authored-COM continuations. In the cold
owners each recorded key byte 107 (`k`), marker 165, selected guest exit code
37, and emulator owner return code 0. The engines retained their own native
checkpoint formats.

A separate legacy paired attempt 03 passed in 9.62 s using the old DOSBox-X
binary. The hot paths reported guest exit 37 in both engines. After cold
restore, QEMU reported exit 37; DOSBox-X reached the guest exit boundary at the
pre-exit point but did not observe a guest exit code. This legacy result is not
the strict candidate result and remains a limitation of the old binary.

## Limits

The candidate covers this authored COM route only. A selected parent PSP with a
child PSP current at cold restore remains unsupported; the candidate fails
closed when the selected PSP differs from the current child PSP. Identity
metadata is trusted only inside a compatible fDisBull project artifact and is
not cryptographically authenticated. These checks do not establish arbitrary
child-process handling, broad DOS compatibility, or DOSBox/QEMU parity. No
default backend change, CI, release, or installation activation is claimed.

The sanitized details are in [verification.json](verification.json). Private
receipt evidence is preserved outside the repository; its manifest is
identified by basename and hash in that record. No private target, emulator
state, JUnit report, or raw receipt is included here.
