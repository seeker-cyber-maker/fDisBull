# QEMU REP terminal-step: bounded native evidence

This report records a bounded comparison of the exact candidate QEMU and
DOSBox-X executables listed in `verification.json`. The authored paired COM
probe steps through a three-byte `REP MOVSB`: both engines finish at IP `010C`
with CX zero and destination `ABC`; QEMU's following fetch is also at `010C`.
The paired trace records still identify the REP address for each of the three
iterations. This establishes the observed terminal step boundary for this
probe, not general REP or trace parity.

QEMU-only probes passed for MOVSB counts zero, one and three, conditional
`REPE CMPSB` termination on the second comparison, and a cold restore from a
mid-REP checkpoint. Separate accepted receipts cover 41 native tests with no
skips, the one-case cold-restore run, and four history tests. Thirteen host
trial observations passed. Exact executable and patch identities, test
selectors, receipt hashes, and result scope are recorded in the JSON file.

The `trace-events` workgroup remains unqualified. This result does not qualify
overall QEMU/DOSBox parity. DOSBox remains the default backend; DotBox is
unchanged. Native VM tests ran locally; CI, release and installation did not.
Earlier divergence evidence remains preserved in its historical report.
