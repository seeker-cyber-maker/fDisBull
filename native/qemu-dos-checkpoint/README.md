# Native DOS COM2 checkpoint status

This patch adds `x-fdisbull-dos-checkpoint-status` to the QEMU 10.0.13 source already carrying the fDisBull native physical RAM layers patch. `source-manifest.json` records both prerequisite and extension patch hashes.

The command requires stopped system-mode TCG with exactly one stopped vCPU. It searches realized ISA serial frontends and requires exactly one at I/O base `0x2f8`, then returns the frontend and UART QOM paths, device type, index, base and IRQ, raw LSR and FIFO enable/counts, RBR/THR/TSR byte values, TSR retry count, THRE/TEMT bits, and derived `tx-idle` and `rx-empty` flags.

The implementation reads QEMU's `SerialState` and `Fifo8` fields directly under the BQL. It does not read UART I/O ports, pop RX bytes, or clear LSR break/overrun bits. `tx-idle` proves the emulated UART has no pending transmitter/FIFO/retry state. It does not prove that bytes already accepted by the host chardev or Unix socket have been consumed; the owning host must drain and check its serial channel separately.

The x86_64 system target compiled and linked in the separate external `checkpoint-status-runtime` build. Local DOS process checkpoint witnesses exercised the query during save and fresh-process restore, including active layers and hooks.
