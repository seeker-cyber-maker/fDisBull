# Native QEMU cooperative task scheduler

This QEMU 10.0.13 source patch builds on `native/qemu-task-private` and adds bounded native x86 CPU contexts, cooperative slot switching, and native ownership checks for guest interrupt frames.

## Cooperative scheduling

A cooperating monitor registers CPU slots and invokes `INT 0x60` to yield or `INT 0x62` to block/finish the current slot. QEMU captures the outgoing architectural context, chooses the next runnable slot, writes the FDBTASK1 anchor itself, and restores the incoming context before guest execution resumes. Tasks do not select each other by writing monitor records. Scheduling is cooperative: this patch does not claim timer or IRQ preemption, QEMM/DESQview compatibility, or a general DOS scheduler.

`x-fdisbull-task-slot-fork` inherits the selected parent’s current context and overrides only EIP, the 16 GPRs, and EFLAGS. The register order is `RAX, RCX, RDX, RBX, RSP, RBP, RSI, RDI, R8..R15`. It preserves virtual-8086 and I/O privilege mode flags.

## Interrupt-frame ownership

When native scheduling is enabled, supported interrupt frames are preflighted against the selected task’s private stack pages before the guest frame is pushed. The saved frame is bound to its SS selector/base, stack mask, interrupt gate width, byte size, and ordered physical backing pages. IRET checks those properties before reading the frame. A mismatch revokes scheduler ownership and stops the CPU. Task-gate switches are refused while native task slots are active.

A single-stepped yield relies on QEMU’s normal debug exception to stop at the selected incoming context; it does not queue a second debug stop. When no task is runnable, QEMU retains the last selected CPU/private view and stops idle so the owner can inspect or disable the scheduler before cleanup.

## CPU state and limits

The native contexts preserve the supported real, V86 and non-PAE protected-mode registers, DR0–DR3/DR6/DR7, segments, controls, x87 and SSE state. AVX-family, MPX, AMX, PAE, long mode, SMM, nested guest mode and PKRU/PKS state are rejected. GDB software breakpoints remain debugger-owned and separate from guest DR state. Device and DMA/IOMMU access stays on shared base memory; task-private data/fetch views use the explicit task QMP APIs.

The task-private RAM limit remains 16 task slots with up to 16 direct 4 KiB pages each. This patch does not provide asynchronous preemption, vendor task identity, private device DMA, or multi-vCPU scheduling.

## QMP commands

| Command | Purpose |
| --- | --- |
| `x-fdisbull-task-scheduler-init` | Prepare a checkpoint destination or initialize from a stable monitor anchor. |
| `x-fdisbull-task-slot-capture` | Bind the stopped selected CPU as the first native slot. |
| `x-fdisbull-task-slot-fork` | Fork a child from the selected parent context with bounded register overrides. |
| `x-fdisbull-task-slot-runnable` | Mark a slot runnable or blocked while stopped. |
| `x-fdisbull-task-scheduler-observe` | Read native selection, slot/context hashes, and frame status. |
| `x-fdisbull-task-context-read` | Read one stopped task’s architectural context and interrupt frames. |
| `x-fdisbull-task-scheduler-disable` | Disable scheduling at a quiescent stopped state before cleanup. |

The exact typed signatures and fields are in `source-manifest.json` and the QAPI patch.

## Build and qualification

The isolated `x86_64-softmmu` TCG target compiled with the retained N16 study configuration using `TMPDIR=<external native-scheduler-runtime/tmp> ninja -C <external native-scheduler-runtime/build> -j8 qemu-system-x86_64`. The source manifest records the exact binary hash. Root-owned native receipt `native-scheduler-10.xml` passed all seven scheduler and guard checks with zero skips: V86 interrupt-frame cold restore, per-task x87 context and rounding restore, instrumented checkpoint profile, same-DR7/different-address guest watchpoint isolation, IRET-width refusal, V86 GP error-code frame, and unowned ring-0 stack refusal. The instrumented profile recorded zero audio frames, so its audio evidence covers observer state/token continuity only; it does not establish PCM or audio-output continuation. No CI was run by the patch author.
