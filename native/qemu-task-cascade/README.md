# Native QEMU cascaded PIC task preemption

This package contains a small source patch on top of the sealed N18
`native/qemu-task-preemption` patch. It extends the opt-in native x86 TCG task
scheduler to track actual slave-8259 interrupts, cascaded dual-controller EOIs,
and nested real hardware interrupt frames. It does not replace the default
DOSBox backend or claim compatibility with QEMM, DESQview, or arbitrary DOS
schedulers.

## Source and build identity

The base is QEMU 10.0.13 plus the exact N18 task-preemption patch whose path and
SHA-256 appear in `source-manifest.json`. The authored delta changes only the
QAPI scheduler schema and `target/i386/fdisbull-task-private.c`. The patch is
`qemu-10.0.13-fdisbull-task-cascade-v2.patch`; its file hash and every changed
file's before/after hashes are in the manifest. A read-only `patch --dry-run`
against the sealed N18 source applied both files cleanly.

The root-owned candidate was built for `x86_64-softmmu` with TCG. Its executable
path and SHA-256 are recorded in the manifest. To reproduce the build in the
retained external study workspace:

```sh
cd /Volumes/CODEX/Codex_Projects/active/fDisBull-local-studies/QEMU-DOSBox-Parity-20261110/native-runtime/native-cascade-runtime
mkdir -p build tmp
cd build
TMPDIR=/Volumes/CODEX/Codex_Projects/active/fDisBull-local-studies/QEMU-DOSBox-Parity-20261110/native-runtime/native-cascade-runtime/tmp ../qemu-10.0.13/configure \
  --target-list=x86_64-softmmu --without-default-features --enable-system \
  --enable-tcg --enable-pixman --disable-user --disable-tools --disable-docs \
  --disable-guest-agent --disable-containers --disable-download \
  --disable-install-blobs --disable-debug-info --disable-qom-cast-debug \
  --audio-drv-list= --firmwarepath=../qemu-10.0.13/pc-bios \
  --prefix=/Volumes/CODEX/Codex_Projects/active/fDisBull-local-studies/QEMU-DOSBox-Parity-20261110/native-runtime/native-cascade-runtime/build/install \
  --ninja=/Users/tiga/miniconda/bin/ninja \
  --python=/Users/tiga/miniconda/bin/python3
TMPDIR=/Volumes/CODEX/Codex_Projects/active/fDisBull-local-studies/QEMU-DOSBox-Parity-20261110/native-runtime/native-cascade-runtime/tmp \
  /Users/tiga/miniconda/bin/ninja -C . -j2 qemu-system-x86_64
```

The configure arguments and exact external command are recorded in
`native-cascade-configure-command.json` in the study workspace. The initial
build completed 1587 steps. After the nested pending-handoff boundary fix, an
incremental four-step build compiled the updated task-private object and
relinked the frozen binary. Both build receipts and their hashes are recorded
in `source-manifest.json`. No CI was run.

## PIC ownership and switch rules

The existing `x-fdisbull-task-preemption-configure` command accepts a configured
global 8259 IRQ from 0 through 15, except cascade line 2. The quantum remains 1
through 65535. A real accepted PIC acknowledgement creates exactly one native
hardware-frame receipt. While the policy is enabled, all accepted real PIC IRQs
are tracked, including nested non-policy interrupts.

A slave IRQ records one global IRQ/vector and both controller lines: master
cascade line 2 and the actual slave input line. The guest must EOI the slave
controller first, then the master cascade line. Direct master IRQs require one
master EOI. EOIs bind to the newest outstanding native interrupt frame; the
stack therefore represents nested delivery in order. Duplicate in-service
line claims, spurious/unacknowledged input, APIC delivery, auto-EOI, PIC poll
mode, PIC reinitialization, unsupported PIC modes, mismatched or out-of-order
EOIs, and IRET before all required EOIs fail closed.

The scheduler switches only after the configured IRQ has completed the needed
EOIs and no other real PIC frame still has an outstanding EOI. A fully EOI'd
frame can remain in its task's native frame stack while that task is dormant;
its IRET ownership remains attached to that task. A target handoff may be
pending while an outer or nested non-policy IRQ remains active. In that case
QEMU returns to the native scheduler after the final outstanding EOI and
switches before the interrupted task executes its IRET.

Pending handoff is a single boolean request. If more configured-IRQ quantum
thresholds complete before the outstanding stack drains, those thresholds
coalesce into one switch at the next eligible boundary. Later completions
continue advancing `quantum-progress`; the implementation does not queue
multiple catch-up switches.

There is no injected timer interrupt and no fabricated EOI. QEMU's real x86 IF,
PIC masking, STI shadow, and MOV-SS shadow behavior governs whether an IRQ is
accepted. PIC/PIT state stays machine-global. Support remains bounded to one
TCG vCPU, existing native task slots, the preceding private page allocation
and CPU-mode limits, and the existing device/DMA limitations. The source delta
does not add a timer source. It retains only the prior bounded authored real
IRQ0 witness; general IRQ timing remains unqualified, and this cascade change
does not broaden that qualification.

## API and checkpoint format

The scheduler status model is `qemu-pc-task-scheduler-v1`, API version 3. The
preemption record is `qemu-pc-pic-preemption-v2`. It retains the earlier
master/slave PIC mask, IRR, ISR, and vector-base fields and adds ordered
`outstanding-frames` entries. Each entry identifies the task lifetime,
acknowledgement sequence, native frame sequence, global IRQ/vector, both PIC
lines, and required/seen EOI masks. Mask bit 0 means master EOI; bit 1 means
slave EOI. For a cascade frame, the required mask is 3, and the valid partial
state after slave EOI is seen mask 2. The legacy `inflight` fields project the
newest outstanding entry. `ack-count - eoi-count` equals `outstanding-count`;
ack-count covers every tracked IRQ, while eoi-count advances once after each
IRQ's full required EOI set.

Native `fdisbull/task-private` VMState advances to version 5. The nested
interrupt-frame VMState layout stays unchanged; version 5 stores additional
PIC line and EOI-mask fields in parallel arrays. The loader reconstructs N18
version-4 direct-master ownership and validates task identity, frame/ack
sequence, PIC modes, and exact PIC ISR-to-outstanding-frame correspondence.
Consistent nested and partially EOI-complete cascade checkpoints are
supported. A pending target handoff is checkpointable only while another
outstanding frame remains; the short pending-with-empty-stack interval is
refused. The host's exact-binary checkpoint fence means cross-binary VMState
interchange is not qualified.

The complete typed QMP schema is in `qapi/fdisbull-task-scheduler.json` inside
the patch. No private DOS targets, guest images, or emulator state files are
part of this package.

## Native evidence

Root-owned native receipt `native-cascade-04.xml` reports 19 passed, zero
failed, and zero skipped in 71.708 seconds. It covers:

- Real RTC IRQ8 cascade delivery and matching slave/master EOIs.
- Nested i8042 IRQ1 ownership over IRQ8, with cold-process checkpoint
  continuation.
- Policy preemption configured for IRQ8 and for nested IRQ1, with the IRQ1
  handoff held until the outer cascade is fully EOI'd.
- Refusal of IRET before required EOIs and refusal of master cascade EOI before
  slave EOI.
- The preceding direct IRQ0/IRQ1, IF/mask/shadow, quantum, native frame,
  private task state, and instrumented checkpoint checks.

These are bounded native fixture results. They do not establish behavior for
other PIC programming modes, general IRQ timing, a proprietary task manager,
or arbitrary DOS software.
