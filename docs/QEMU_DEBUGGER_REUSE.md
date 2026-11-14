# Shared QEMU debugger foundation: implemented reuse and remaining adapters

This account starts from the working DOS and CHIP-8 implementations at the G2
baseline `e0b323022a9e8ecdac602517628d8bfeb30b1732` and the first consolidation
at `8badfaa195823dc7d65fb3e6044de5fb9d7e0b55`. The dated prior candidate boundary
below is preserved separately from the current source integration. This account
answers what a new architecture can actually reuse. It is
not a promise that a third CPU needs only a small adapter, or that every separate
module is unnecessary. DOSBox-X remains default and retained. The current
LE binding and trace integration is host code and reuses the retained native
candidate; native qualification belongs to exact candidate receipts. No CI or
default switch is part of this integration.

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
| Stopped source-window search | `qemu_dos_le_match.masked_window_offsets`, used by the explicit QEMU LE matcher and legacy `runtime_source_matching` adapter | Source-backed ranges, loader fixup exclusions and each adapter's evidence/exception contract | One complete bounded masked-window search now owns within-object ambiguity refusal; there is no separate anchor heuristic to maintain. |
| Owned LE source traces | Existing DOS trace collector, predicates, GDB steps, clocks, artifacts and event searches | `qemu_dos_le_binding` owns current stopped relations; `qemu_dos_le_identity` rechecks protected CS/GDT, source anchors and complete instruction fixups | Ordinary runs qualify fresh endpoints; stepped captures qualify retained stopped boundaries, without retirement or OS lifetime claims. |
| Recorded runtime mappings | Project `runtime_mappings` registry, snapshot qualification and event/checkpoint queries | Original object identities, declared or observed task episodes, address-space/page evidence | Registry records remain separate from the strict stopped LE admission artifact and from native task-private controls. |
| Automatic stopped-state tracking | `runtime_tracking` callbacks integrated into the owned debugger/machine stop path | Provider source identity, source-byte matching and `runtime_desqview` containment/lifecycle observations | Provider-specific stop semantics remain adapters. Native evidence belongs to the exact combined candidate receipt. |

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

## 2026-11-13 prior Doom candidate boundary

The separate `Doom Intake` private candidate supplied useful protected-mode source
mapping and DESQview observations. Its Doom title/LE-object observations used
**DOSBox-X**; its DESQview machine observations used QEMU. Neither result is
silently promoted to !117 QEMU-DOS game qualification.

The reviewed five-file stream-recovery patch is identified by SHA-256
`bad7beed733238d93dcee436667bd0496ded359e2b9106df1a9211ccd0b78e2a`.
Its parser comes from an older transport baseline. Replacing !117's whole file
would lose existing operation deadlines, lock budgets, packet pagination,
injected channels, standard-error parsing and live-input callbacks. !117 already
retains partial packet/checksum state across receive timeouts.

At the first consolidation, only its independently reproduced **uncertain
ACK-write classification** was integrated: a failed packet acknowledgement closes the channel as an
uncertain write. It cannot authorize a receive-recovery interrupt or execution
replay. This is shared transport behavior used by both architectures.

At `8badfaa`, protected source-binding was a separate candidate integration.
`qemu_dos_process` required observed real-mode source admission and stopped
protected tracing at the transition. The candidate's `runtime_source_matching`,
`runtime_mappings`, `runtime_tracking` and `runtime_desqview` dependencies were
absent. The recorded next step was to pin those dependencies, verify stopped
CPU/GDT/source evidence through the QEMU-DOS public path, and preserve unknown
or ambiguous mappings. The candidate's DOSBox-X title observation was input
evidence for that work, rather than a QEMU-DOS result. This paragraph describes
that earlier boundary, not the current dependency inventory.

## Current protected-source and registry dependency boundary

The current source integrates `runtime_mappings`, `runtime_tracking`,
`runtime_desqview` and the legacy `runtime_source_matching` adapter as reviewed
dependencies. The Project registry retains original object identities and
snapshot-qualified relationships; session-owned tracking closes intervals
before execution or unmonitored mutation and observes a new stopped boundary.
The tracker refuses original-source enrichment under execution-only overlays.
The DESQview provider's source/containment evidence remains distinct from a
native task identity inferred merely from a PSP, CR3 or selector. See the
[registry and tracking contract](runtime-mappings.md) for the integrated module
provenance, supported source views and remaining combined qualification gates.

The separate public `dos_source_admit` / `debug-dos-source-admit` operation now
uses an explicit embedded-LE runtime view of the complete original carrier. It
requires an owned stopped unpaged protected32 CPU, A20, consistent CS/GDT
evidence, physical/linear RAM comparison and final readback. It records source
and producer pins, bounded original-file spans, explicit loader-fixup
exclusions, an initialized-data relocation witness and, when found, a symbolic
16-bit bridge witness. It leaves the initial MZ EXEC source binding unchanged.
See [protected QEMU-DOS source admission](QEMU_DOS_PROTECTED_SOURCE.md).

The QEMU matcher and legacy adapter share a complete bounded masked-window
search. It checks every eligible window rather than accepting the first unique
16-byte anchor. Alternative placements within one object refuse even when the
second placement has no unique anchor. The stricter QEMU route filters
source-backed extents before uniqueness; zero-filled or wholly excluded bytes
do not qualify a source relationship. Existing byte-free reply and private
artifact boundaries remain in place.

These consumers retain separate authority. A stopped LE admission always has
`lifetime_qualified: false` and `live_mapping_installed: false`; it does not create
a runtime task episode, install registry bindings, authorize LE source-addressed
hooks/layers, or itself extend tracing. The legacy tracker and registry retain
their own source/span and lifetime contracts.

The explicit `dos_source_bind` operation adds a separate owned recipe. It makes
a fresh stopped admission, records immutable carrier/version/run/epoch and
placement evidence, and revalidates source bytes after owned execution. A
normal run has an unobserved interval and qualifies only its new stopped
endpoint. A source trace reuses `session.step()` and validates each retained
boundary. The protected qualifier checks the current CS/GDT and physical/linear
readback, then compares the whole decoded instruction, including any supported
internal offset32 relocation with a proved target placement. Masked discovery
bytes do not become instruction proof. Symbolic, straddling or unproved fixups
and unrelated/changed instructions stop qualification.

The collector selects an installed LE handle by default; `source_view` can
explicitly request `embedded-le` or retain `initial-dos`. There is no implicit
bind or fallback after an LE failure. LE locations and historical search sites
carry an application hash, object ID/index and object offset in a distinct
namespace; no LE preferred address is presented as an ordinary MZ project PC.
Cold consumers reconstruct recipe and instruction claims from original source
and linked receipts. The initial MZ mapping and classic trace format remain
unchanged.

Source authority is withdrawn before execution and is not usable while running.
Mutation, unmonitored resume, owner/source/epoch drift and restore/rewind paths
retire the handle. Existing checkpoints do not restore it. Fresh source checks
share a bounded run/step's remaining allowance; an already exhausted allowance
defers optional revalidation without discarding a known native stop. Actual
source transport uncertainty retains the stop/error and follows existing owner
cleanup. LE source observation still refuses active layers and task-private
views and does not authorize LE hooks, layers, redirects or checkpoint bindings.
No OS task/allocation lifetime follows from this source recipe.

The earlier local QEMU-DOS probe reached the original Ultimate Doom title and
recorded bounded protected-source extents without seeded runtime placement.
That result is separate from the private candidate's older DOSBox observations.
The continuous source-revalidation and LE trace/search slice has a separate
exact-candidate native qualification gate. Host checks and earlier artifacts support
their named contracts; they do not qualify OS/task lifetime, bridge execution,
general gameplay or the broader DOS compatibility campaigns.

## What a third architecture must provide

A third architecture can reuse transports, storage, script validation, the
history DAG, checkpoint delta codec, selected-state chain replay, recorded
mapping registry and bounded source-window search. It still
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
