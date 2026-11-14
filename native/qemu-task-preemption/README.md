# Native QEMU PIC task preemption

This patch adds an opt-in, bounded native task switch driven by actual legacy
8259 interrupt acknowledgements and guest EOIs. It layers on the sealed
`native/qemu-task-scheduler` source patch. It does not replace the default
DOSBox backend or claim QEMM/DESQview compatibility or a general DOS scheduler.

## Interrupt and switch contract

The caller enables `x-fdisbull-task-preemption-configure` while the stopped
native task scheduler is active. The selected input is one direct master PIC
IRQ from 0 through 7, excluding cascade IRQ2. The optional quantum is 1 through
65535 matching guest acknowledgement/EOI pairs. The disabled policy remains
visible in API version 2 scheduler status.

When QEMU accepts a supported PIC interrupt, the extension binds that real PIC
acknowledgement and vector to the native hardware frame just created for the
selected task. It waits for the guest to clear that same master PIC ISR bit
with a real EOI. After the configured quantum, QEMU schedules at the native
execution-loop boundary following the guest I/O instruction and before the
next guest translation block. The source task retains its actual interrupted
CPU state and interrupt frame; the next runnable task receives the machine's
normal global PIC/PIT state. Guest code does not choose tasks or synthesize
EOIs.

The implementation relies on QEMU's normal x86 interrupt rules for IF,
masking, and interrupt shadows. A task switch can preserve a task inside its
real hardware interrupt handler after EOI; the task later resumes and executes
its own IRET. Machine-level pending lines remain global.

## QMP and checkpoint state

The scheduler receipt remains `qemu-pc-task-scheduler-v1` with API version 2.
It adds a `qemu-pc-pic-preemption-v1` record containing the enabled policy,
quantum phase, monotone acknowledgement/EOI/switch counters, current PIC
mask/IRR/ISR snapshots, last transition keys, and any in-flight task/frame
binding. Each interrupt frame includes PIC validity, controller, IRQ, vector,
acknowledgement sequence, and EOI-seen fields.

Native VMState `fdisbull/task-private` advances from version 3 to version 4.
The existing nested interrupt-frame VMState record keeps its prior layout;
version 4 stores PIC frame ownership in parallel arrays. A checkpoint can
retain a real IRQ before its EOI only when the saved PIC ISR, selected task,
full task lifetime, acknowledgement sequence, and native frame sequence agree.
The short post-EOI handoff-pending interval is refused for save. Version 1–3
streams load with PIC preemption disabled and zero PIC metadata on old frames.

The complete typed signatures are in the QAPI source included in the patch.

## Supported behavior and limits

- One stopped/running x86 TCG vCPU with the existing native task slots and
  private RAM/fetch views.
- Direct master PIC IRQs 0, 1, and 3–7. Slave/cascade, IRQ2, spurious, APIC,
  auto-EOI, PIC polling, PIC reinitialization, and unsupported PIC modes fail
  closed while preemption is enabled.
- Actual interrupt delivery and guest EOI are required. No timer is injected,
  no EOI is fabricated, and no preemption is claimed for blocked/masked
  interrupts before the CPU accepts them.
- Up to 16 native task slots; page, CPU-mode, interrupt-frame, DMA/IOMMU, and
  device limitations remain those documented by
  [`qemu-task-scheduler`](../qemu-task-scheduler/README.md).
- The test evidence covers authored FreeDOS fixtures and named input paths;
  it does not establish compatibility with proprietary task managers or
  arbitrary DOS software.

## Reproduction and evidence

The source was based on QEMU 10.0.13 plus the preceding task-scheduler patch
whose SHA-256 is recorded in `source-manifest.json`. Configure the external N18
source using the retained study profile, then build the x86 system target:

```sh
cd /Volumes/CODEX/Codex_Projects/active/fDisBull-local-studies/QEMU-DOSBox-Parity-20261110/native-runtime/native-preemption-runtime
mkdir -p build tmp
cd build
TMPDIR=/Volumes/CODEX/Codex_Projects/active/fDisBull-local-studies/QEMU-DOSBox-Parity-20261110/native-runtime/native-preemption-runtime/tmp ../qemu-10.0.13/configure \
  --target-list=x86_64-softmmu --without-default-features --enable-system \
  --enable-tcg --enable-pixman --disable-user --disable-tools --disable-docs \
  --disable-guest-agent --disable-containers --disable-download \
  --disable-install-blobs --disable-debug-info --disable-qom-cast-debug \
  --audio-drv-list= --firmwarepath=../qemu-10.0.13/pc-bios \
  --prefix=/Volumes/CODEX/Codex_Projects/active/fDisBull-local-studies/QEMU-DOSBox-Parity-20261110/native-runtime/native-preemption-runtime/build/install \
  --ninja=/Users/tiga/miniconda/bin/ninja --python=/Users/tiga/miniconda/bin/python3
TMPDIR=/Volumes/CODEX/Codex_Projects/active/fDisBull-local-studies/QEMU-DOSBox-Parity-20261110/native-runtime/native-preemption-runtime/tmp \
  /Users/tiga/miniconda/bin/ninja -C . -j2 qemu-system-x86_64
```

The frozen binary is recorded in `source-manifest.json` by exact path and hash.
Root-owned native qualification passed all 15 focused checks across two
receipts. `native-preemption-03.xml` reports 14 passed, zero skipped, in
57.459 seconds: standard and virtual/x87 IRQ0 preemption, IF/mask/chained-shadow
deferral, real keyboard IRQ1, quantum-three phase across cold restore,
frame/IRET guards, and the preceding native scheduler checks.
`native-preemption-04.xml` adds one instrumented-profile IRQ cold-restore check
with zero skips and pre/post-EOI cross-process checkpoint checks. These are
local native results; no CI was run for this patch.

The dedicated isolated MOV-SS pending-IRQ probe remains unqualified because
the stopped-input surface cannot establish a pending PIC interrupt before the
following instruction. The chained-shadow fixture passed, but it does not
support a separate MOV-SS-specific claim.
