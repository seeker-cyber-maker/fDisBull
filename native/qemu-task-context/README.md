# Native x86 task-context observation

This patch adds a read-only stopped-state QMP observation for one x86 TCG
vCPU. It reports architectural context and a transition generation, with an
optional caller-selected 56-byte guest physical RAM anchor. The generation
advances when CR3 changes, the hidden TR or LDTR cache changes, a hardware TSS
task switch completes, or the CPU resets. A CPU reset advances both epoch and
generation so a retained monitor anchor cannot keep the same owner identity
across reset. A small VMState record preserves the generation and native epoch
across local snapshots and advances both on load. It does not add a migration
blocker.

The native API is `x-fdisbull-query-task-context`. Its model is
`qemu-i386-architectural-task-context-v1`. The response includes the CPU mode,
CPL, EIP, ESP, CS and SS selectors, CR0/CR3/CR4/EFER, GDTR/IDTR, and visible
and hidden TR/LDTR state. The optional `anchor-address` argument must refer to
exactly 56 contiguous bytes in direct RAM. QEMU returns those bytes as
`anchor-hex`; it rejects I/O, ROM, ROMD, RAM-device, discard-managed and
cross-region ranges. The query does not read guest ports or write guest RAM.

This is architectural context evidence, not a software task identifier.
QEMM or DESQview-style schedulers may switch tasks without changing CR3, TR or
LDTR. The native generation cannot distinguish those tasks by itself. A
cooperating monitor can expose a stable anchor containing its own UUID, task
cookie, incarnation and sequence; the host validates that record and combines
it with the architectural context. QEMU does not parse the anchor or infer a
vendor task identity. Without an observed anchor or other explicit task
binding, tasks that share architectural context remain indistinguishable.

The host's cooperating-monitor protocol uses this little-endian layout:

| Offset | Size | Value |
| --- | --- | --- |
| 0 | 8 | ASCII `FDBTASK1` |
| 8 | 16 | Expected monitor UUID bytes |
| 24 | 8 | Scheduler sequence, even while stable |
| 32 | 8 | Nonzero task cookie |
| 40 | 8 | Nonzero task incarnation, never reused for a new lifetime |
| 48 | 4 | State `1` for an active task |
| 52 | 4 | Reserved, must be zero |

The monitor makes the sequence odd before changing task state and publishes a
greater even value after the selected task is stable. The host rejects a
regressing sequence or a changed lifetime without a sequence transition.
Bind before activating layers or adding hooks. Source views and source tracing
require the selected bound task; raw machine observations remain available.
The stable host task key includes the anchor address, UUID, cookie, incarnation
and DOS helper nonce. That nonce distinguishes independently booted DOS
processes; it is retained across a verified checkpoint restore.

The host must call the query before saving or loading a snapshot so the
blocker-free task-context VMState record is registered in that QEMU process.
After load, the record advances epoch and generation beyond both the saved
values and the destination process's prior highwater marks. The guest RAM
snapshot preserves the monitor anchor itself; this native record preserves
only epoch and generation.

The isolated `x86_64-softmmu` TCG target compiled and linked. The root-owned
native witness passed remapped A→B→A task context and a cold Python subprocess
restore, including the physical RAM layer, fetch overlay, scoped hooks, epoch
and generation checks. This is a bounded witness; it does not qualify
vendor software task recognition, QEMM/DESQview compatibility or general
protected/V86 task-switch coverage. This is an x86-specific patch and
currently does not provide a non-x86 QMP handler stub for multi-target QEMU
builds.

Apply this patch after the exact
[instrumented-checkpoint base](../qemu-instrumented-checkpoint/README.md).
The manifest pins the prerequisite, all changed source files and the locally
built binary. Runtime states and caller-owned DOS media stay outside Git.
