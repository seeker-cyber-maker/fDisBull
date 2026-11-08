# DOSBox-X to native QEMU: capability inventory

This inventory records the migration boundary at
`089c1841c415eb2b5cdfa90d03b6291a07f73919`. It is a coverage ledger, not a
claim that the native QEMU replacements have passed. Each slice needs its own
native witnesses and DOSBox regression evidence before its status advances.

**Keep `dosbox` and `dosbox-qemu` selectable throughout and after the
migration.** Unsupported operations must fail before mutation. An uncertain
native result must not trigger an automatic retry on another backend. Changing
the default and retiring a backend are separate decisions; this migration does
not authorize deletion of the DOSBox fallback.

## What exists at the starting revision

[`QemuMachine` and `MachineContext`](../src/fdisbull/qemu_machine.py) already
own an offline QEMU machine and provide stopped register/RAM access, guarded
edits, execution breakpoints, data watchpoints, bounded run/step, stopped-boundary
traces and stored-display PNG capture. Native machine memory searches,
page-mapping observation and QEMM/DESQview report ingestion also exist. The
project-bound launcher accepts an original raw x86 boot image. It does not
launch a project COM/MZ at its DOS entry point.

The subsequent process slice now provides that path through
`QemuDOSProcessSession`: an original COM/MZ project, a separately identified
DOS boot disk, preserved startup/configuration, real EXEC loading, verified
PSP/MCB/source bytes and native entry. `debug-dos-process` reports lifecycle;
verified parent return distinguishes selected-process exit and TSR residency.
This is partial native availability, with real-mode entry and explicit machine
address controls. It does not promote driver/task/V86 or whole-game parity.
See the maintained [handoff log](DOS_QEMU_HANDOFF.md) for dated execution evidence.

The trace slice adds source-bound stopped observations and `trace-until` to
the original COM/MZ process adapter, plus persistent event-search integration.
Runtime bytes and canonical relocated source sites are kept distinct. Native
fault/REP witnesses corrected the earlier unconditional completion wording:
ordinary GDB stops do not prove instruction retirement. Initial-module and
epoch qualification is partial availability; live overlays, protected/V86
process mapping, queued input and whole-game timing remain unqualified.

[`dosbox-qemu`](../src/fdisbull/dos_qemu.py) is a different backend: it runs
DOSBox as a Linux process inside QEMU and forwards the DOSBox protocol. Its
`dos-cpu` context and outer `machine` context are different CPUs. Passing its
tests does not establish native DOS-on-QEMU compatibility.

The audited DOSBox surface comprises **35 backend RPC methods** and **83
public debugger route names** resolving on `DebugSession`. Two of those public
routes intentionally refuse direct DOS writes. Counting names alone is
insufficient: inherited methods can still reject the selected backend, and
apparently similar operations can have different timing, state or address
semantics.

## Dependency-ordered slices

| Slice | Transfer | Acceptance boundary |
| --- | --- | --- |
| Core | Owned process/transport, selection, capabilities, stop/run/step, CPU state, physical/virtual RAM, break/watchpoints | Bounded failure and cleanup; stopped observations; guarded mutation; unchanged source image; explicit capability refusals |
| DOS process | Actual DOS boot, COM/MZ launch, relocation/source binding, PSP/parent identity, drivers and task/page context | Original entry bytes and registers; child exit versus selected process exit; TSR versus normal exit; observed protected/v86 context |
| Trace and events | Instruction observations, register/event searches, predicate stops, code-region transitions | Declared fetch/completion semantics; IRQ, exception, REP and DOS callback cases; incomplete intervals remain unknown |
| Clock, media and input | Guest-time budgets, completed-frame capture, pixel probes, keyboard/mouse, physical frame inputs | Separate guest and host clocks; frame/mode/revision identity; consumed input and release evidence; no stale-frame substitution |
| Checkpoints | Native states, Anchor Stones, restore epochs and disk policy | Complete CPU/device/clock state; admitted disk/file identities; cold-session restore; pending-input policy; close on uncertain restoration |
| Layers and hooks | RAM/fetch views, priority/selection, live code, hooks and later block-service integration | Guarded transitions; separate data/fetch views; translation-cache coherence; self-modification; explicit effect ownership |
| Histories | Rewind, CPU/RAM deltas, frame timeline, baseline/layer experiments | Correct boundary identity; unrecorded-mutation invalidation; partial-state freeze and recovery; bounded storage and restored input ownership |
| Workflows | Scenes, macros, movement, spatial policy, text/player workflows and endpoint consumers | Their real frame/input/state dependencies qualify first; run source-bound scenarios and compare declared observables |
| Qualification | Driver/game matrix, Windows regressions, default selection and fallback rehearsal | Real OS and workload evidence in addition to authored snippets; retained selectable DOSBox; no unsupported parity claim |

The slices describe dependencies rather than requiring every file in one slice
to land in a single commit. Display observation can begin before input, for
example, while full frame-timeline acceptance must wait for input and native
checkpoints. A working low-level operation does not automatically qualify its
compound consumers.

## Complete backend RPC ledger

The table covers the stable and layers patches. `layers.configure` requires
the layers profile. Names were cross-checked against the DOS session/helper
calls, patch dispatch conditions, and strings in the supplied DOSBox backend;
that last check is not runtime qualification.

| RPC methods | Slice | Existing native seam and remaining distinction |
| --- | --- | --- |
| `agent.capabilities` | Core | Machine capability metadata exists; advertise only implemented, admitted operations and distinguish availability from qualification |
| `session.start` | DOS process | Native COM/MZ adapter now uses actual DOS EXEC, verifies PSP/MCB, ordered relocations and exact loader writes, then stops at entry; protected/V86 and full DOSBox launch parity remain unqualified |
| `session.status`, `session.stop` | Core / DOS process | Machine status/cleanup exist; machine stop or process reaping is not selected DOS process termination |
| `execution.continue`, `execution.pause`, `execution.step`, `execution.wait` | Core | QMP/GDB control exists; bounded machine run is not the DOS asynchronous-operation schema or guest-time run contract |
| `execution.timing` | Clock, media and input | No native DOS guest-clock adapter at the baseline; host-time timeout is not emulated milliseconds |
| `state.get_registers`, `state.set_register` | Core | GDB register inspection/guarded writes exist; expose CPU mode, segment bases, widths and selected-vCPU identity, without inventing DOS source coordinates |
| `memory.read`, `memory.write` | Core / DOS process | Physical and selected-vCPU virtual memory plus guarded writes exist; DOS segmented/static addresses and task/allocation identity need separate admission |
| `breakpoints.create`, `breakpoints.delete`, `breakpoints.list` | Core / Trace and events | QEMU TCG execution/data controls exist; preserve byte-free breakpoints, access kind, length, bounded count and cause/resume semantics |
| `trace.start`, `trace.read`, `trace.stop` | Trace and events | Completed-step machine traces exist; no equivalent streaming before-fetch trace cursor or callback-safe DOS boundary adapter |
| `video.screenshot`, `video.probe` | Clock, media and input | QMP screendump provides a stored surface; it does not establish the DOSBox last-completed-frame, scanline, mode, guest-tick or revision contract |
| `input.keyboard.press`, `input.keyboard.type`, `input.keyboard.state` | Clock, media and input | Requires a real controller input adapter, bounded queue, US-layout admission and observed consumption; sending a host key event is insufficient |
| `input.keyboard.down`, `input.keyboard.up`, `input.keyboard.frame_edges` | Clock, media and input | Preserve owned held-key leases, exact make/break ordering, stale-lease invalidation and frame-bound input replay |
| `input.mouse.move`, `input.mouse.click`, `input.mouse.button`, `input.mouse.state` | Clock, media and input | DOSBox uses its built-in INT33 driver; QEMU needs an admitted guest driver/device path, pixel/range mapping, release timing and pending-input evidence |
| `frame.step` | Clock, media and input | Native frame boundary stop is required; instruction stepping or sleeping until a host refresh is not equivalent |
| `state.save`, `state.load` | Checkpoints | Raw `MachineContext` advertises `save_states=False`; DOSBox `.sav` data cannot be interpreted as a QEMU VM checkpoint |
| `layers.configure` | Layers and hooks | Raw `MachineContext` advertises `code_layers=False`; a RAM write or changed PC is not a fetch-only layer |

The raw transport remains an owned, bounded channel. Its failure policy—close
on uncertain dispatched I/O rather than replay—must survive the migration.
See [`dosbox_rpc.py`](../src/fdisbull/dosbox_rpc.py) and
[`qemu_machine.py`](../src/fdisbull/qemu_machine.py).

The process adapter preserves this policy across memory-search/report mixins
and persistence failures. A shared startup deadline covers staging and native
control; process identity is invalidated when a machine fails closed. Process
exit does not itself terminate the emulator. DOS's resident category is kept
separate from an inferred exit opcode, and retained source ranges come from
the observed allocation-chain intersection.

## Complete public debugger route ledger

The following groups enumerate the 83 routes found by resolving the
[`DebugWorkspace` router](../src/fdisbull/debugger.py) against `DebugSession`
and all its mixins. Engine-only and machine-only routes are not counted as
existing DOSBox capabilities. Backend selection, live ownership and
`debug-stop` also require explicit integration checks even though launch/stop
dispatch are outside this router dictionary.

| Group | Public routes | Native transfer status at the baseline |
| --- | --- | --- |
| Core control and inspection | `debug-status`, `debug-registers`, `debug-breakpoint`, `debug-delete-breakpoint`, `debug-memory`, `debug-run`, `debug-contexts`, `debug-script` | Machine equivalents exist with different scope/signatures; the full legacy DOS script grammar and source mapping are pending |
| Explicit direct-write refusals | `debug-write-memory`, `debug-write-registers` | Legacy DOS deliberately refuses these routes; preserve that contract while native machine writes remain explicitly guarded |
| Memory investigations and driver context | `debug-memory-snapshot`, `debug-memory-apply`, `debug-memory-rule-tick`, `debug-desqview-observe`, `debug-bind-runtime-memory`, `debug-runtime-memory`, `debug-write-runtime-memory` | Snapshot, one-shot edit/rule and report code has machine paths; live runtime bindings and source/task identity need qualification |
| Periodic memory rules | `debug-memory-rule-run` | Inherited on `MachineContext` but explicitly refuses QEMU; requires qualified guest-time slices |
| Trace and predicates | `debug-trace`, `debug-trace-until` | Raw stopped-boundary traces; verified COM/MZ source traces, register/PC/region predicates and saved event searches. Initial real-mode module only; no queued input or overlay rebinding |
| Waits and input | `debug-wait`, `debug-keyboard-press`, `debug-keyboard-type`, `debug-keyboard-state`, `debug-keyboard-down`, `debug-keyboard-up`, `debug-click`, `debug-click-frame` | Pending guest-clock, device and ownership contracts |
| Frames | `debug-screenshot`, `debug-frame-probe`, `debug-frame-advance`, `debug-frame-inputs` | Stored-surface screenshot exists; coherent probes, boundaries and physical frame input are pending |
| Checkpoints and Anchor Stones | `debug-save-state`, `debug-load-state`, `debug-save-anchor-stone`, `debug-load-anchor-stone` | Pending native serializer, identity, disk and epoch contracts |
| Layers, code and controls | `debug-layer-stack`, `debug-layer-enable`, `debug-layer-patch`, `debug-code`, `debug-capture-code`, `debug-branch`, `debug-cave`, `debug-hook`, `debug-hooks`, `debug-delete-hook`, `debug-controls`, `debug-screenshot-hooks` | Pending fetch-view and hook adapter; screenshots with preparation hooks also depend on this slice |
| Reproducible trials | `debug-save-experiment`, `debug-restore-experiment`, `debug-compare-experiment` | Pending native state/control qualification; incomplete or misaligned observations cannot prove equality |
| Checkpoint rewind | `debug-rewind-start`, `debug-rewind-status`, `debug-rewind-record`, `debug-rewind` | Explicitly DOSBox-only at the baseline |
| CPU/RAM deltas | `debug-delta-start`, `debug-delta-status`, `debug-delta-record`, `debug-delta-rewind`, `debug-delta-recover` | Pending native adapter; selected-state undo must retain its partial-restoration/frozen-state distinction |
| Frame history | `debug-timeline-start`, `debug-timeline-status`, `debug-timeline-advance`, `debug-timeline-rewind`, `debug-timeline-stop`, `debug-timeline-pin`, `debug-timeline-image` | Pending full checkpoint/frame/input composition and restored key ownership |
| Scenes | `debug-scene-check`, `debug-scene-assert`, `debug-scene-click`, `debug-scene-act`, `debug-scene-wait`, `debug-scene-navigation` | Reusable host algorithms, pending native frame/input dependencies |
| Macros, movement and proofs | `debug-macro`, `debug-move`, `debug-proof-check` | Reusable host algorithms, pending source/control/budget adapter and observed native effects |
| Higher workflows and policy | `debug-workflow-observe`, `debug-workflow-act`, `debug-text-observe`, `debug-text-act`, `debug-assisted-travel`, `debug-spatial-policy`, `debug-spatial-action` | Pending coherent lower-level composition; preserve physical/assisted/story/fair-play distinctions |

### Surfaces a method count does not cover

- The Python-only `frame_rgba()`/`RGBAFrame` consumer needs decoded-pixel hash,
  size, stride, codec and frame-identity checks. Stored PNG export is a different
  path.
- COM/MZ source hashing, launch aliases, relocation validation, private target
  storage, explicit asset allowlists and disk mutation policy remain part of
  launch correctness. Keeping the original executable unchanged is mandatory.
- DOS process completion is observed **after cleanup of the selected PSP**.
  Child exit, returning TSR, reaching an exit interrupt, debugger shutdown and
  emulator death are separate events. Test remapped exit interrupts as a
  negative control.
- Protected/v86 execution needs observed mode and segment/page context.
  Selectors must not become DOS paragraphs by arithmetic. CR3 alone does not
  establish allocation or task lifetime.
- Native controlled dot-mode, the IDA endpoint, `serve`/`debug`, runtime doctor,
  capability discovery, packaged agent references and offline runtime setup
  are consumers of backend selection, not optional documentation polish.
- Static disassembly, binary diff, driver/module readers, code versions and
  persisted evidence remain host features. They do not need an emulator rewrite,
  but source identity, restart and artifact-isolation regressions still matter.
- BIOS, disks, graphics, sound, interrupts, EMS/XMS/A20/paging, QEMM and DESQview
  are compatibility obligations beyond the JSON protocol. A bare-metal fixture
  does not prove an actual DOS driver, scheduler or game works.
- UDL/UIL region selection, pending Python services, selective joins and
  original/replacement effect ownership are planned additions. The separate
  hostcall/layer experiments do not qualify a production backend. Their own
  completion, cancellation, duplicate-notification and restore-epoch contracts
  need independent witnesses.

## Regression witnesses and promotion gates

These are existing candidate tests, not a report that this inventory ran them.
Use the narrow affected tests as each slice lands; run a wider composition only
to settle a remaining risk. Preserve local receipt identities and do not
automatically start hosted CI.

| Boundary | Existing witness files |
| --- | --- |
| Machine control, memory, capture, restart and source isolation | `tests/test_qemu_machine.py`, `tests/test_debugger.py`, `tests/test_debug_semantics.py` |
| DOS entry and process lifecycle | `tests/test_dos_com.py`, `tests/test_dos_launch.py`, `tests/test_dos_guest_exit.py` |
| Mode, mapping, QEMM/DESQview and searched RAM | `tests/test_dos_memory.py`, `tests/test_qemm_runtime.py`, `tests/test_desqview_runtime.py`, `tests/test_desqview_memory_native.py`, `tests/test_memory_search_runtime.py`, `tests/test_memory_rules.py` |
| Traces and event predicates | `tests/test_execution_trace.py`, `tests/test_execution_event_native.py`, `tests/test_protected_mode_trace.py` |
| Guest time, completed frames and input | `tests/test_debug_wait.py`, `tests/test_keyboard.py`, `tests/test_frame_capture_native.py`, `tests/test_frame_coherence.py`, `tests/test_screenshot_codecs.py`, `tests/test_protected_runtime_native.py` |
| Layers and code views | `tests/test_code_layers.py`, `tests/test_code_overlap_native.py`, `tests/test_runtime_code.py`, `tests/test_screenshot_hooks.py` |
| Checkpoints and histories | `tests/test_anchor_stone_cli.py`, `tests/test_rewind_native.py`, `tests/test_cpu_deltas_native.py`, `tests/test_delta_policies.py`, `tests/test_debug_timeline_deltas.py`, `tests/test_frame_timeline_native.py`, `tests/test_debug_experiments.py` |
| Scenes and workflow consumers | `tests/test_scene_domain_integration.py`, `tests/test_scene_readiness.py`, `tests/test_input_macros.py`, `tests/test_movement.py`, `tests/test_spatial_native.py`, `tests/test_progressive_scenes.py`, `tests/test_player_live.py` |
| Backend fallback, wrappers and Windows | `tests/test_dos_qemu.py`, `tests/test_ida_dosbox.py`, `tests/test_doctor.py`, `tests/test_dosbox_window.py`, `tests/test_windows_native.py`, `tests/test_win16_native.py` |

Native tests have explicit environment inputs and may otherwise skip. For
example, existing raw-machine acceptance uses `FDISBULL_MACHINE_QEMU` with
`FDISBULL_REQUIRE_MACHINE=1`; DOSBox acceptance uses `FDISBULL_DOSBOX`; the
frame-timeline gate uses `FDISBULL_FRAME_DOSBOX` and
`FDISBULL_REQUIRE_FRAME_NATIVE=1`. The DOSBox-inside-QEMU gate additionally
requires its kernel and prepared initramfs. Record skips as missing evidence,
not successful native parity. Driver profile parsers and an absence-report
helper do not establish loaded QEMM or DESQview scheduling.

Before a future default switch, every required ledger row needs a declared
disposition and matching native evidence. Qualify a fresh launch, source
isolation, cold checkpoint restore, real DOS/driver/game cases and the actual
fallback-selection path. DOSBox and QEMU checkpoints remain backend-specific;
fallback means launching the same authorized target with the selected backend,
not replaying an uncertain mutation or loading an incompatible checkpoint.

## Preventing inventory drift

The coverage check should derive public routes from the router and
`DebugSession` inheritance, including methods that explicitly refuse. Derive
raw RPC names from literal `.call(...)` first arguments in the session/mixin
and helper modules; expand literal `_keyboard_call(...)` operations; add
`method == "..."` dispatch names from added/context lines of the stable and
layers patches. Ignore deleted lines, trailing-dot dispatch prefixes and
filenames such as `agent.env`.

At this baseline that extraction produces exactly the 35 RPC names above and
83 public routes. Require set equality with the ledger, unique entries,
recognized slices/statuses and existing test paths. New or removed surfaces
must update the inventory deliberately. Keep implementation status separate
from qualification receipts: a referenced test path, advertised capability or
importable method is not evidence that the native replacement passed.
