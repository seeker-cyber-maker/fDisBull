# CMPXCHG16B and fault-retry overlay batch

Apply this source patch after the exact atomic overlay batch described by
the linked manifest. Verify each preimage hash and `git apply --check` first.
It preserves the full-width failed CMPXCHG16B write cycle without marking
an execute-overlay write in nonparallel translation. It also checks both
pages for watchpoints before dirty callbacks on cross-page accesses.
Translation of both pages already precedes dirty callbacks.

The local paired fixture boots a DOS MZ program into four-level long mode,
then makes its aligned 16-byte operand read-only before each compare. Its
page-fault handler records the fault and retries after making the page
writable. Unlocked and LOCK-prefixed cases were compared with Bochs before
and after independent unprimed cold restore, while a QEMU owned-machine
checkpoint carried an active physical execute layer. Both matched Bochs
for the failed, changed-value and same-value outcomes and three guest
write faults. The old native image conflicts on the failed comparison.

A second trial put a GDB write watchpoint on the last byte of a high-backed
cross-page DWORD store. The new image preserved the complete store and
post-instruction overlay stop in both sessions. The predecessor was
observationally identical for that trial because x86 GDB watchpoints stop
after access. Stop-before-access watchpoint behavior is therefore still
source-level only.

The checked long-mode checkpoint path is limited to canonical four-level
mapping and physical RAM below 4 GiB. Parallel TCG, high-backed 16-byte
operands, and arbitrary later MMIO/device failures are outside this
qualification. The dirty callback still precedes the actual store.
DOSBox-X remains the default.
