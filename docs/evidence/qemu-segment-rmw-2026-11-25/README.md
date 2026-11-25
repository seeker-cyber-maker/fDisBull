# Protected-mode read-modify-write witness

An authored 32-bit COM fixture seeded `0x7fffffff` in RAM and executed the same
`INC dword` through read-only and writable DS descriptors. Before execution it
recorded general registers, EFLAGS and RAM. The read-only case also recorded
the first fault frame, the handler's observed state and the final retry result.

The exact QEMU candidate raised #GP before the read-only write, leaving RAM and
general registers unchanged. Its pushed EFLAGS matched the saved pre-state
apart from RF; after the handler loaded writable DS, the instruction retried
once and completed. Frozen DOSBox-X completed that read-only access without
entering the handler. This is a **reference divergence**, not a parity pass.

Both engines completed the writable control. The value became `0x80000000`;
carry remained set, overflow/sign/auxiliary-carry/parity became set, and zero
and interrupt flags remained clear. The [verification receipt](verification.json)
binds these observations to the exact native binaries and the final two-case
JUnit hash. The QEMU source patch and prior rights evidence remain at
`native/qemu-segment-rights/` and
`docs/evidence/qemu-segment-rights-2026-11-25/`.

This witness does not qualify other RMW instructions, implicit stack accesses,
guest TF/IRQ interactions, DOSBox checkpoint restore, trace retirement or the
full migration inventory. DOSBox-X remains the default; DotBox is unchanged.
No CI, release or installation was performed.
