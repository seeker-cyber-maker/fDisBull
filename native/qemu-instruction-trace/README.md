# QEMU bounded instruction trace

Apply after the exact `qemu-cmpxchg16b-fault-retry` candidate in the source manifest. Verify every preimage hash before applying the patch. Build the x86 system target with TCG plugins enabled (`-Dplugins=true`); other builds reject `x-fdisbull-trace-start`.

QMP starts a bounded capture with an exact event limit, reads bounded cursor pages, and stops recording with a bounded page. The ring retains at most 65,536 records and each page is capped at 4,096. Events include sequence, vCPU, guest virtual PC, origin, and `before-execution` reason. `tcg-dispatch` is emitted by generated per-instruction TCG callbacks. `breakpoint-pre-dispatch` is emitted in QEMU's breakpoint check immediately before `EXCP_DEBUG` for a matched GDB or architectural breakpoint; it is not a TCG callback. Neither origin claims instruction completion or retirement.

The Nth TCG dispatch requests a GDB-visible stop with guest state restored to that instruction PC; resuming retries the Nth instruction with recording inactive. A matched breakpoint already stops at its boundary. Epoch changes clear observations on start, reset, instrumented checkpoint load, and checkpoint import. Wrong epochs, ahead cursors, and invalid page limits return QMP errors. The current schema omits translated instruction bytes and x86 mode/segment data, so the PC remains guest virtual.

The plugin-enabled local build passed. Paired QMP trace cases passed 2/2, including exact-count and GDB breakpoint ordering, and native regression passed 5/5 on the listed candidate. DOSBox remains the default backend.
