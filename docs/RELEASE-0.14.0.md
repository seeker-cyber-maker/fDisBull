# fDisBull 0.14.0

DOSBox and Windows debugging now share one owned Linux/QEMU machine lifecycle.
Projects expose explicit target and outer-machine contexts, with a raw x86 boot
profile that can stop before firmware execution. An optional IDA 9.4 adapter
and a matching DOSBox binary endpoint provide another common remote interface.
Original static bytes, earlier code versions and private runtime state remain
separate from observations saved with the project.

## Shared machine and DOS integration

- `backend="dosbox-qemu"` runs the patched Linux DOSBox inside an offline QEMU
  machine using the existing DOS project API. Breakpoints, read/write watches,
  RAM/fetch layers, bounded scripts, fast-forward, native DOS state save/restore,
  screenshots, 8px grids and click-frame remain available.
- `contexts()` and `context()` distinguish `dos-cpu`, Windows `process`, and the
  outer `machine`. Pausing the outer machine stops its Linux controller too;
  guest requests are rejected until it is resumed. The shared lock also rejects
  a request that was already queued when the pause completed.
- `project.machine(..., boot_image=...)` starts an original raw x86 image halted
  before boot. QEMU uses a private temporary disk overlay, preserving the source.
  Machine operations include guarded register/memory edits, physical or selected
  vCPU virtual memory, patchless execution breakpoints, `r`/`w`/`rw` watches,
  bounded run/step, completed-step traces and stored display captures.
- Guest asset uploads are explicit, relative and hash-bound. Symlinks,
  traversal, databases and saved-state launch assets are rejected. No host game
  directory is mounted into the VM, and the VM has no network interface.
- Owned startup processes are registered immediately. Disconnecting during a
  long boot reaps the pending VM. A valid native DOS rejection, such as an
  invalidated post-restore framebuffer, preserves the live session.

See [shared debugger usage and limits](UNIFIED_DEBUGGER.md). The real DinoPark
replay source is `examples/dinopark/verify_remote_endpoint.py`; its game inputs
and project database remain private. Selected screenshots, a marked click,
relocated breakpoint evidence, a 512-record fetch trace and the bank dialog are
retained under `experimental/remote-debugger/evidence/2026-10-25-unified/`.

## Optional IDA remote engine

`ida-wine-qemu` speaks the interface-31 binary debugger protocol to an explicitly
supplied IDA 9.4 `win64_remote.exe` inside Wine. It supports qualified patchless
execution stops, memory/register edits, RAM layers, screenshots/clicks and
bounded instruction traces. Trace batches execute within the Linux controller
with fresh code reads and register snapshots. The matching loopback DOSBox
endpoint uses native emulator hooks for stops without replacing guest bytes.

The vendor executable and license keys are not distributed. This adapter has
smaller qualified feature coverage than the existing custom Wine backend:
PE data watches, execution-only layers and native-state reconnection through
IDA are not qualified. See [remote endpoint usage](IDA_REMOTE.md), the
[initial verification](IDA_REMOTE_VERIFICATION.md), and the historical
[bounded trace measurements](IDA_TRACE_PERFORMANCE.md).

## Runtime compatibility and limits

Prepare the selected profile's runtime with the 0.14.0 package and explicitly
selected backend inputs. Guest source fingerprints reject stale prepared
images. DOS native states describe DOSBox CPU/device state and check guest
files separately; custom Wine native states capture the whole QEMU machine.
Neither format is a universal state for every context. Outer-machine code
layers and native states are explicitly unsupported in this release.

The initial machine context selects the first vCPU and stops all vCPUs. It does
not infer OS thread identity, discover typed NT objects, or translate between
DOSBox addresses and outer Linux memory. Real boot acceptance uses an authored
BIOS boot sector. Windows kernel boot, DTrace providers, register-read filters
and a universal execution-overlay engine are future work. The existing README
warning about malware/security suitability remains applicable.

DOS traces contain pre-execution fetch records; the final requested record is
pending execution. PE and machine traces confirm completed steps. Default QEMU
single stepping masks interrupts/timers, so machine instruction experiments do
not establish faithful elapsed-time behavior.

## Verification and release gates

The preserved local receipts establish real DOS/QEMU state/layer/input/restart
behavior, raw boot breakpoints and watches, original/child patch isolation,
offline image/trace exports and real Wine sessions. The final local correction
has its own receipt at
`experimental/remote-debugger/evidence/2026-10-25-unified-final/`.

Tagging requires both GitHub Linux workflows to succeed on the exact release
commit. Ordinary CI runs `python -m pytest -q`, builds the wheel/sdist/tool ZIP,
and audits exclusions. Native CI builds both pinned DOSBox profiles, tests the
binary DOS endpoint, verifies the source-built backend identity, prepares the
Linux DOS and Wine runtimes, and requires actual DOS-in-QEMU, boot-context and
custom Wine acceptance against the installed wheel. Missing required native
inputs fail rather than becoming skips. IDA's vendor-dependent native test
remains an explicit optional local gate.

All packages include host/controller sources and required guest resources.
Game files, saved states, databases, runtime images, vendor executables/keys and
compiled target fixtures are excluded. Existing 0.13.0 packages and deliveries
remain unchanged. Source/tag preparation does not publish a GitHub release or
deliver new backend bundles.
