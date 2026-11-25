# QEMU divide-fault and partial-REP trace evidence

This packet records a bounded local paired DOSBox-X/QEMU selection for two
new authored-COM trace witnesses. It extends the preceding
[QEMU trace checkpoint packet](../qemu-trace-checkpoint-2026-11-24/README.md),
which contains the prior QEMU-only checkpoint-epoch evidence. The trace
debugging workgroup remains unqualified.

## Observed result

The combined local selection passed 30 tests with no failures or skips in
21.76 seconds on the exact QEMU and DOSBox-X executables identified in
[verification.json](verification.json). It included host trace coverage, three
prior paired COM trace tests, the QEMU-only checkpoint-epoch test, QEMU fault
and REP step semantics, and the new paired fault-frame and partial-REP boundary
tests.

The authored divide-by-zero COM witness installs INT 0 and then executes
`DIV BL` with BL zero. Both engines report the DIV fetch at offset 010D and the
handler fetch at 0111. AX remains 1234, SP decreases by six, and the CPU-created
frame stores saved IP 010D and the code segment.

The authored REP MOVSB witness copies ABC with CX initially three. Both
engines report the first two single-step progress states at REP offset 010A,
with CX values two then one and matching destination bytes. On the third step,
both have CX zero and destination ABC. QEMU's stopped IP still reports 010A,
while DOSBox-X reports 010C. The next QEMU step fetches 010A before reaching
010C; the next DOSBox-X step fetches 010C. This is an observed stop-boundary
difference, not a parity pass. Before-fetch trace records do not establish
instruction completion or retirement.

## Limits

The private JUnit result is excluded; only its SHA-256 is recorded. The
workgroup remains unqualified, DOSBox-X remains the default backend, and this
packet does not change DotBox. No hosted CI, release, or installation was run.
Private JUnit data, guest media, and runtime payloads are excluded.
