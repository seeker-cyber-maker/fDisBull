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

The owned checkpoint's RIP/RSP fence uses canonical four-level mapping and
physical RAM below 4 GiB. Parallel TCG and arbitrary later MMIO/device
failures are outside this qualification. The dirty callback still precedes
the actual store. DOSBox-X remains the default.

The later host adapter qualifies this same frozen native image with an
operand backed at physical `0x100802000`, selected through a low linear
address in four-level long mode. Its opt-in layer walk permits 40-bit
physical leaf addresses while the owned checkpoint's RIP/RSP fence remains
low-physical by default. The plain and LOCK high-backed cases matched
Bochs live and after unprimed cold restore with the active layer. This
qualification requires the local host wheel SHA-256
`84ee5c22f73521074bfb0f671cd0e730b9229596cc97a59ba2460614148149d3`.
The high-backed runtime test uses a 4 KiB leaf; wider leaf sizes have
offline walk coverage only.
