# Witnessed held-key movement

The public and saved-script routes retain the existing movement signature and result format. The [verification receipt](verification.json) pins the implementation, runtime and bounded evidence.

Four native/paired cases pass: the same authored COM records an IRQ1 make, at least three BIOS ticks of held-key progress, the break, and two quiet ticks after release on QEMU and DOSBox-X. Separate QEMU cases preserve the first IRQ breakpoint without cleanup execution and preserve a caller-owned hold when movement is rejected. All owned processes were reaped.

The final independent host gate passes 33 cases, including two-key reverse-order release, ambiguous arm outcome, capture-epoch change, late result publication and known-invalid references before an earlier real RAM write. The native source predates only the pure duplicate-reference preflight correction; this distinction is recorded rather than claiming an unexecuted final-source native rerun.

The initial native failure exposed host-QMP dispatch racing a short virtual cutoff. The adapter now arms each exact owned edge batch once at a declared positive native delay. No retry, host-time-to-guest-time conversion or release through an earlier stop is introduced.

This is a bounded physical movement route over caller-witnessed RAM. Scene geometry, frame-based progress, collision inference, assisted travel and whole-game parity remain separate obligations.
