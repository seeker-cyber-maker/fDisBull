# CMPXCHG execute-overlay candidate

Apply the patch after the exact [dirty-page candidate](../qemu-dirty-overlay/README.md).
The [manifest](source-manifest.json) identifies the predecessor executable,
source preimages, and frozen macOS arm64 build of x86_64 TCG.

For scalar x86 memory CMPXCHG in a nonparallel translation block, the failed
compare follows the existing store path for its writeback cycle, including
memory access checks, QEMU dirty bookkeeping, and the task-private write
observer. Only the execute-overlay notification is suppressed for that
access. The matching compare uses the usual observed store. A match that
writes the current value still reports an overlap and stops before the next
guest instruction. This applies to the nonparallel lowering of both locked
and unlocked instructions.

The [Bochs reference checks](../bochs-pae-reference/README.md#compare-cmpxchg-outcomes-on-dirty-pages)
cover a failed comparison, a changed-value match and a same-value match on 4
KiB PAE, 2 MiB PAE and 4 MiB PSE-36 backing above 4 GiB. Wider atomic
instructions, parallel translation blocks, page-table A/D writes and plugin
callback parity have separate qualification boundaries.
