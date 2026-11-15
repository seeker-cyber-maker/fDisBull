# Native QEMU cooperative task-private RAM views

This QEMU 10.0.13 patch adds bounded CPU-private RAM pages and instruction
fetch overlays for an explicitly cooperating x86 guest monitor. It is built
on the task-context patch. It does not identify proprietary tasks or implement
a QEMM/DESQview scheduler.

## Task selection protocol

The monitor publishes a 56-byte `FDBTASK1` record in guest RAM:

| Offset | Size | Field |
| --- | --- | --- |
| 0 | 8 | ASCII `FDBTASK1` |
| 8 | 16 | Monitor UUID bytes |
| 24 | 8 | Scheduler sequence, little endian; even when stable |
| 32 | 8 | Nonzero task cookie |
| 40 | 8 | Nonzero task incarnation |
| 48 | 4 | State; `1` means active |
| 52 | 4 | Reserved; zero |

The monitor marks the sequence odd while changing task state, publishes a
greater stable even sequence, then issues `OUTW 0xF1DB, 0x4446`. QEMU checks
the anchor at that doorbell and commits the view at a TCG block boundary
before the next guest block executes. The first registered stable task can
become the initial view. Later registrations cannot silently change the
selected task. An invalid, odd, stale, or unregistered commit revokes the
active private view and stops the CPU before code from the next task runs.

QEMU treats the UUID, cookie and incarnation as opaque cooperative identity.
The native architectural context generation from the prerequisite remains a
separate ABA signal; neither one is claimed to be a vendor task ID. The
monitor owns task scheduling and lifetime publication.

## Native QMP surface

All setup, registration, configuration, read, observe and retirement commands
require a stopped single-vCPU x86 TCG machine. The guest doorbell is the only
running-guest switch operation.

| Command | Purpose |
| --- | --- |
| `x-fdisbull-task-monitor-init` | Register the fixed private RAM arena and VMState record. Use `prepare-only: true` on a fresh checkpoint destination so guest switching stays disabled until restore. |
| `x-fdisbull-task-register` | Register or extend a task lifetime and clone its requested direct RAM pages into private backing. |
| `x-fdisbull-task-layer-configure` | Apply guarded task-private RAM writes and a complete task fetch overlay with an expected generation. |
| `x-fdisbull-task-layer-read` | Read the explicit `ram`, effective `execute`, or shared `base` view. Reads are limited to 4096 bytes. |
| `x-fdisbull-task-layer-observe` | Read selection, registry, native epoch/generation, per-page hashes and fetch-overlay hashes without changing task state. |
| `x-fdisbull-task-retire` | Tombstone a lifetime and revoke it if currently selected. A retired cookie/incarnation pair cannot be reused. |

RAM configuration is guarded against the current private bytes before any
write. Execution configuration records the expected private backing bytes;
stale backing or guest self-modification revokes the overlay and stops before
stale instructions execute. Generation exhaustion fails closed.

## CPU memory and migration behavior

The native manager reserves a 1 MiB RAMBlock containing up to 16 task views,
with at most 16 4 KiB pages per task. Each task gets its own backing slot for
the requested physical RAM backing identity. The CPU TLB points data accesses,
read/modify/write accesses, and instruction fetches at that task's private
slot. A task's aliases to the same RAM backing share its page slot. Switching
tasks flushes TLB and translated blocks; adding pages to the selected task
also flushes them.

The RAMBlock bytes, task/page registry, selected task, guarded fetch overlays,
and manager epoch/generation are saved in VMState version 1. A fresh
destination must issue `x-fdisbull-task-monitor-init` in prepare-only mode
before snapshot load so the RAMBlock and VMState record exist. After load,
the native epoch/generation advance for the new owner. The host checkpoint
controller and its sidecar are a separate versioned layer.

## Scope and limits

- Only x86 system-mode TCG is implemented. No non-x86 QMP handler stubs are
  included for multi-target builds.
- The implementation requires one vCPU. It does not implement or emulate a
  DOS task scheduler; task switches are cooperative monitor doorbells.
- The arena supports 16 task lifetimes and 16 pages per task. A task's
  private pages must resolve to direct writable RAM. I/O, ROM/ROMD,
  discard-managed memory and cross-region spans are rejected.
- Task-private paging structures are not supported. Pages aliasing the active
  page directory or present legacy page tables are rejected. PAE paging is
  rejected while private pages are active.
- Device and DMA/IOMMU accesses remain on shared base RAM. GDB physical
  accesses are not task-private. Use the explicit QMP `task-layer-read` views
  to inspect task RAM or effective fetch bytes.
- No claim is made for multiple vCPUs, non-TCG accelerators, DMA-private
  semantics, arbitrary guest schedulers, QEMM/DESQview compatibility, or
  broad protected/V86 task-switch coverage.

## Verification

The isolated `x86_64-softmmu` TCG source compiled and linked. Against the
current binary, 899 broader local checks passed with zero failures or skips.
They include same-page A/B private data and fetch views across five task
visits, separate-Python-process cold restore with shared hook hit counts,
standard and virtual/precise-retrace profiles, dormant generation-zero
protected/V86 restores, retirement, invalid commits, atomic memory admission,
single-step commit, selected-B restore, and reset revocation. These are specific authored witnesses;
they do not establish general DOS scheduler or commercial task manager
compatibility.

The patch applies after the pinned task-context patch. Its unified diff was
dry-run against the pristine task-context source tree. Runtime images and
guest data remain outside the repository.
