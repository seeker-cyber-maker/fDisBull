# Shared QEMU debugger foundation: implemented reuse and remaining adapters

This account compares the working DOS and CHIP-8 implementations at the G2
baseline `e0b323022a9e8ecdac602517628d8bfeb30b1732` and the bounded consolidation
described below. It answers what a new architecture can actually reuse. It is
not a promise that a third CPU needs only a small adapter, or that every separate
module is unnecessary. DOSBox-X remains default and retained; no CI or native
rebuild is part of this source change.

## Feature account

| Feature | Shared implementation | Adapter or required CPU/device semantics | Remaining repeated orchestration |
| --- | --- | --- | --- |
| QMP | `qemu_control.QemuControl` | Native commands, capability models and receipt validation | Per-session command admission is appropriate. |
| GDB | `gdb_rpc.GDBRemote`, XML register layout, packet execution and memory transfers | Register names/widths, PC/fault interpretation, address spaces; DOS uses `QemuMachine`, CHIP-8 its `_Owner` | Launch/cleanup owners have different responsibilities; they are not unified here. |
| Project artifacts | Existing Project database and private CAS storage | Source/version identities and backend admission | No new storage engine per architecture. |
| Authored scripts/layers | `debug_script`, `code_layers.groups`, `debug_state.byte_string` | Accepted operations, address translation and source provenance | Native layer install/readback/rollback has similar structure but different protocols. |
| Full histories | `Chip8HistoryMixin` inherits `QemuDOSHistoryMixin`: DAG revisions/branches, pending journals, locks/deadlines and rewind orchestration | Identity, checkpoint capture/verification, formats and live epoch; DOS process/workspace/serial versus CHIP-8 machine state | Public mutation wrappers still differ around active frame/key rules. |
| Lossless checkpoint deltas | Same `frame_state_codec` encoder, validator and decoder | Frame formats, checkpoint metadata and CHIP-8 metadata hash checks | `qemu_frame_storage` and `chip8_frame_storage` repeat store/materialize chain and budget handling. This is a plausible later extraction, not changed now. |
| Frame histories | History DAG methods, `_history_operation` and shared codec | DOS renderer updates versus rational 60 Hz CHIP-8 device samples; different proof fields | Advance/capture/publication loops resemble each other but have different fence, input and recovery policies. |
| Input ownership | History operation serialization/deadlines | DOS keyboard controller/FIFO/scancodes/modifiers versus CHIP-8 sixteen-key held mask | Generation/adoption patterns resemble each other; receipts remain distinct. |
| Selected CPU/RAM undo | `_fingerprint`, `_runs`, policy validation; now `qemu_selected_state.replay` | x86 flags/aliases/segments/pages/task-private backing versus CHIP-8 V/I/PC widths, 4 KiB RAM and fetch rebasing | Record/inverse/recovery orchestration still differs in native write preparation, hooks and uncertainty receipts. |
| Comparative trials | `debug_script`, operation lock/deadline and artifact-capacity checks | DOS task-private controls versus CHIP-8 display/key/timer/RNG observations | Baseline/candidate/final restore loops are similar; deadline, report and failure behavior need a separate contract before extraction. |
| RAM/code layers | Common persistent layer definitions and patch grouping | DOS segmented/paged aliases and task identity versus flat CHIP-8 RAM and atomic native configuration | Similar stack-transition structure; address proofs and native commands justify distinct adapters. |
| Hooks | GDB breakpoints and persistent logical hook definitions | DOS task/runtime address binding and action types versus CHIP-8 fixed addresses/actions | Hit/displace/resume loops remain tied to backend live-control policies. |

The source anchors are `chip8_history.py:Chip8HistoryMixin`,
`qemu_dos_history.py:QemuDOSHistoryMixin`, `qemu_chip8.py:_Owner`,
`qemu_machine.py:QemuMachine`, `qemu_frame_storage.py`,
`chip8_frame_storage.py`, `qemu_experiments.py` and `chip8_experiments.py`.
The feature list is not an estimate of engineering completion from line counts.

## Concrete consolidation: selected-state chain replay

Previously, DOS and CHIP-8 independently reconstructed a selected CPU/RAM
history and checked the same chain invariants. They now call one
`qemu_selected_state.replay` implementation. It owns:

- parent/history/runtime-binding and range continuity;
- initial, current and selected projection reconstruction;
- register preimage checks and ordered RAM interval bounds/preimages;
- before/after fingerprints and per-entry deadline callbacks.

Backend document loaders retain artifact row/run/version/hash checks and their
metadata rules. In particular CHIP-8 still validates its exact metadata wrapper.
The shared function does no native execution, memory writes, address translation
or checkpoint recovery. Existing public artifact formats, selected-undo freeze
policy and full-recovery requirements are preserved. This is one maintenance
boundary extracted from two working implementations, not a new debugger framework.

## Deliberate Doom candidate boundary

The separate `Doom Intake` private candidate has useful protected-mode source
mapping and DESQview observations. Its Doom title/LE-object observations used
**DOSBox-X**; its DESQview machine observations used QEMU. Neither result is
silently promoted to !117 QEMU-DOS game qualification.

The reviewed five-file stream-recovery patch is identified by SHA-256
`bad7beed733238d93dcee436667bd0496ded359e2b9106df1a9211ccd0b78e2a`.
Its parser comes from an older transport baseline. Replacing !117's whole file
would lose existing operation deadlines, lock budgets, packet pagination,
injected channels, standard-error parsing and live-input callbacks. !117 already
retains partial packet/checksum state across receive timeouts.

Only its independently reproduced **uncertain ACK-write classification** is
integrated here: a failed packet acknowledgement closes the channel as an
uncertain write. It cannot authorize a receive-recovery interrupt or execution
replay. This is shared transport behavior used by both architectures.

Protected source-binding is a separate candidate integration. !117's
`qemu_dos_process` still requires observed real-mode source admission and stops
protected tracing at the transition. The candidate's `runtime_source_matching`
LE-object/GDT/placement/fixup matching, `runtime_mappings`, `runtime_tracking` and
`runtime_desqview` dependencies are absent here. The next protected-binding
slice must pin those dependencies, verify the stopped CPU/GDT/source mapping
through the QEMU-DOS public path, and preserve unknown or ambiguous mappings.
An observed DOSBox-X title screen is an oracle/input to that work, not its result.

## What a third architecture must provide

A third architecture can reuse transports, storage, script validation, the
history DAG, checkpoint delta codec and selected-state chain replay. It still
needs a real CPU/machine and exposed register description; a pinned capability
and checkpoint identity; source/address admission; native atomic layer/inverse
operations; device/input/time observation and ownership; and backend loaders and
recovery policy. Repeating whole history storage or chain validation is no
longer necessary. Sharing more orchestration should follow demonstrated common
contracts rather than an assumed universal CPU/device model.

The [component build boundary](QEMU_COMPONENT_BUILD_BOUNDARY.md) specifies which
changes need native work and which can reuse exact frozen artifacts. The
[maintained handoff](DOS_QEMU_HANDOFF.md) records actual behavior demonstrated
by this slice and the next DOS acceptance gap. Common UIL conversion gates
remain separate; G3-G8 are not advanced by this consolidation.
