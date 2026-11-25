# QEMU trace checkpoint epoch evidence

This packet records a bounded QEMU host checkpoint-cursor fix and its native
test. The trace workgroup remains unqualified; this result does not qualify
general trace parity, DOSBox-X behavior, or release readiness.
The earlier translated-byte witness and candidate details are retained in the
[QEMU instruction context packet](../qemu-instruction-context-2026-11-24/README.md).

## Observed result

On the exact QEMU v2 candidate identified in [verification.json](verification.json),
the selected local batch passed 25 tests with no failures or skips in 14.91 s.
The selection covered host trace behavior, native before-fetch tracing, and
native checkpoint epoch behavior. The saved trace remains available across a
save. A hot restore replaces the VM and invalidates the old host cursor; a new
trace observes the restored `INC` fetch with translated byte `40` and 16-bit
CS context. A fresh-session cold restore repeats this observation. The old
cursor does not alias the new capture. The checkpoint-epoch test is QEMU-only;
paired DOSBox-X three-COM cases are present in the broader batch but do not
qualify this checkpoint behavior on DOSBox-X.

The related process, LE checkpoint, and trace host regression selection also
passed 66 tests locally (`tests/test_qemu_dos_process.py`,
`tests/test_qemu_dos_le_checkpoint.py`, `tests/test_qemu_fetch_trace.py`).

The native producer audit found that reset, snapshot load, and import already
invalidate the native epoch. A successful load can increment it twice, which
still prevents an old cursor from matching the restored producer; no native
patch was needed for this fix.

## Limits

The private JUnit result stays outside Git; only its SHA-256 is recorded.
No broad suite, hosted CI, release, installation, or qualification promotion
was performed. DOSBox-X remains the default. Other event semantics and paired
workloads remain open as listed in the parity work record.
