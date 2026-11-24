# CMPXCHG8B and split-store overlay candidate

Apply the patch after the exact [scalar CMPXCHG candidate](../qemu-cmpxchg-overlay/README.md).
The [manifest](source-manifest.json) records the predecessor executable, the
three source preimages and replacements, and the frozen x86_64 TCG build.

In a nonparallel translation block, a failed CMPXCHG8B comparison keeps its
eight-byte writeback cycle while suppressing execute-overlay notification
for that access. A matched comparison uses the ordinary observed store.
A match that writes the existing value also reports an overlap. Both locked
and unlocked instructions use the path. The failed-store helper carries the
full 64-bit value.

The paired fixture performs all three comparison outcomes and a DWORD store
crossing a 4 KiB physical subpage boundary in one guest startup. The split
store's execute overlay covers only its final byte on the second page.
Bochs supplies the independent registers, ZF, memory, translated addresses
and post-instruction PCs. Each engine repeats the sequence from its own
checkpoint in a fresh process. The receiving QEMU process starts with paging,
PAE and PSE disabled before restoring the active execute layer.

The native patch changes CMPXCHG8B notification. The existing two-page store
path supplies the split-store behavior. The cross-page buffer ends at LE
object offset `0x2000`, immediately before a relocation at `0x2001`.

Qualification covers the authored aligned CMPXCHG8B and split DWORD cases on
one TCG vCPU. Parallel execution, CMPXCHG16B, paging-fault retry, interactions
with later watchpoint faults, and TCG plugin callback parity remain separate
qualification work.
