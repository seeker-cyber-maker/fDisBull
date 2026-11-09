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
process mapping, input-to-source-trace causality and whole-game timing remain unqualified.

The clock/input slice now adds an explicit fixed-icount profile, machine-owned
keyboard and relative PS/2 mouse leases, a bounded Python queue dispatched once
during GDB continue, and stopped PNG/CPU/clock brackets. Independent DOS BIOS
and IRQ witnesses distinguish acceptance, consumption and later drawing.
The optional virtual-clock extension now has native timer budgets and retained
completed renderer publications. A separate explicit PC-speaker profile captures
bounded PCM output with callback timestamps. These operations have Python,
retained JSON and saved-script routes. A renderer ID is not a guest frame;
concatenated PCM duration is not elapsed guest time. Generic guest milliseconds,
completed guest frames, broader sound devices, coordinate clicks, guest text
consumption/layout and pixel/INT33 mouse semantics remain open. The separate opt-in
[host clock controller](DOS_QEMU_TIMING.md) now maps native virtual time to
host elapsed time at explicit cooperation points.

The optional retrace API 1 extension adds passive `retrace_observe()` under
`qemu_clock='virtual', qemu_retrace='precise'`. It pins the selected standard
PCI VGA model and reports its stopped virtual phase with a timing generation
that records guest-write changes, including unobserved A-to-B-to-A transitions.
Unsupported legacy timing or VBE returns an explicit reason without a phase.
The generation is not a full video-mode identity; vertical retrace is not the
whole vertical blank interval, a renderer publication or a completed guest frame.
The separate `retrace_wait()` composes this model with one native timer budget
and validates the exact next transition window. It refuses unsupported timing
and preserves timing changes, missed edges and earlier/coincident stops without
retry. No full-frame or frame-edge input parity is implied. The native profile
is opt-in; all default-promotion qualifications remain open.

`clock_sync_start/observe/step/stop` bind a fixed 1:1 mapping with persistent
host/native anchors. All host elapsed time since start counts; actual guest
progress and prior overshoot are subtracted. One explicit step chooses at most
one bounded native catch-up or host-only sleep. Excess drift or another observed
stop latches the mapping until explicit stop/start. JSON and saved scripts use
the same capability, parameter, transaction and deadline checks. There is no
background controller, automatic rebase, input replay or media resampling.
See the [timing contract](DOS_QEMU_TIMING.md) for receipt and state semantics.

The optional input API 1 extension now schedules one owned keyboard/relative
PS/2 batch on `QEMU_CLOCK_VIRTUAL`. Its patch applies after the current clock
and media patches. `input_schedule(delta_ns)` passively arms the pending batch;
`input_schedule_observe()` reads its retained receipt. One later explicit
bounded `run()` or `clock_advance()` owns the attempt. The first stop cancels an
unfired timer and requires explicit reschedule or `input_cancel_pending()`;
pending stops and reached/equal clock-budget deadlines win regardless of timer
insertion order. Dispatched holds still need an explicit release. No transition
is replayed after an uncertain result.

`virtual_input_schedule` is advertised only for the admitted virtual profile
and discovered native commands. `timed_input`, `guest_time_control` and
`completed_guest_frames` remain false. A dispatch timestamp proves PS/2 handler
callbacks and their final sync, while FIFO acceptance, guest consumption and
frame recognition remain unknown. This new seam does not qualify the legacy
`guest_ms`, timed press/type, frame-edge or pixel/INT33 contracts. Native bounds
are 256 events per batch, one edge per ordinary mouse button, relative values
-32767..32767, delay 1..60,000,000,000 ns and 4096 successful tokens per process.
Reset/profile loss invalidates the scheduler; migration stays blocked after
the first successful arm. See the [workflow guide](DOS_QEMU_MIGRATION.md#schedule-one-physical-input-batch-on-virtual-time)
and [native patch contract](../native/qemu-input/README.md).

The optional fifth [retrace-input patch](../native/qemu-input-retrace/README.md)
adds `retrace_input_schedule` and `input_schedule_retrace(edge='enter'|'exit')`.
It arms the same pending batch for the strictly next modeled transition and
checks the pinned timing generation/window in the native callback. Timing
changes, including unseen ABA writes, or a missed window cancel before delivery
and require explicit resolution. Stops and equal clock deadlines retain
precedence. The immutable callback snapshot qualifies native PS/2 callback
phase only; guest consumption, full VBlank, completed frames and legacy
frame-edge parity remain open. The ordinary delta scheduler and older native
patch chains retain their existing capability boundary.

The optional sixth [keyboard-press patch](../native/qemu-keyboard-press/README.md)
adds `virtual_keyboard_press` through the existing press API, JSON and script
routes. One passive chord has 2..8 edges, 2 ms modifier spacing and a main hold
of 1..1000 ms. Every next native deadline derives from the preceding actual
callback. First-stop cancellation retains the proven prefix and any held leases;
explicit suffix cancellation and explicit release are required before recovery.
No partial replay or conversion to ordinary/retrace batch scheduling is admitted.
The general `timed_input` flag stays false; coordinate clicks remain open.

The optional seventh [keyboard-type patch](../native/qemu-keyboard-type/README.md)
adds `virtual_keyboard_type` through the existing text API, JSON and script
routes. One passive plan accepts 1..64 printable US-layout ASCII characters,
CR, LF and Tab. Each character gets its own key/Shift lifetimes. The first
edge of every later character waits `gap_ms + 2 ms` from the preceding final
release; there is no trailing gap timer. Future lease reservations stay outside
the active held-key ledger, so the 256-edge and 64-active-lease bounds remain.
The same per-edge stop precedence, delivered-prefix evidence and explicit
suffix cancellation/release policy apply. Guest layout, lock state and generic
text consumption remain unqualified.

The optional eighth [mouse-click patch](../native/qemu-mouse-click/README.md)
adds `virtual_mouse_click` and the QEMU-only
`mouse_button_click(button='left', *, hold_ms=80)`, JSON
`debug-mouse-button-click` and script `mouse.button-click`. The capability
requires explicit virtual clock plus the native clock/input commands,
`input-send-event` and `x-fdisbull-arm-mouse-click`; precise retrace is
unnecessary. Older seven-patch builds keep their physical/keyboard capabilities
and refuse the new helper.

One stopped empty-queue/no-held-lease arm prepares two separate button batches
and syncs: down after 2 ms, release 1..1000 ms after the actual down callback.
The caller chooses bounded execution or one explicit clock-sync step. Stop or
equal-budget precedence can cancel the suffix and retain an owned hold, which
requires explicit suffix cancellation and release. No movement is requested;
prior accumulators, external button state, disabled/remote mode and FIFO
capacity remain unnormalized. Callback/sync evidence does not establish device
acceptance, guest consumption or cursor position. This narrowly extends the
physical `input.mouse.button` route; pixel `input.mouse.click`, `debug-click`
and `debug-click-frame` remain open. General `timed_input`, `absolute_mouse`,
`guest_time_control` and `completed_guest_frames` remain false.

Virtual-profile COM/MZ source traces now retain stable stopped clock brackets
under `source_trace_clock`. A `virtual-time-range` predicate binds the exact run,
host epoch and native epoch with half-open nanosecond bounds. Retrospective
query rows, final endpoint clocks and search witnesses preserve that evidence
across project reopening; candidate source-site identities remain independent
of time. Live and saved-script requests refuse foreign or unsupported clocks
before execution. This joins source observations to input/media timestamps;
input causation, natural stepped-instruction latency, legacy guest milliseconds
and completed guest frames remain unqualified. No default-promotion row is
qualified by this narrower clock evidence.

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

Together with the nine non-method surfaces, **all 127 default-switch
qualification rows remain open**. The new QEMU-only routes below do not change
that frozen DOSBox inventory or promote a compatibility campaign. DOSBox remains
the default and both DOSBox selectors remain available.

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
| `execution.timing` | Clock, media and input | `clock_observe` separates machine icount, host time and opt-in API1 native virtual nanoseconds. `clock_advance` retains requested/fired/stopped times and earlier native stops; opt-in `clock_sync_*` preserves a fixed 1:1 host mapping and `retrace_wait` verifies one modeled transition. Legacy guest_ms and exact-cutoff parity remain unqualified |
| `state.get_registers`, `state.set_register` | Core | GDB register inspection/guarded writes exist; expose CPU mode, segment bases, widths and selected-vCPU identity, without inventing DOS source coordinates |
| `memory.read`, `memory.write` | Core / DOS process | Physical and selected-vCPU virtual memory plus guarded writes exist; DOS segmented/static addresses and task/allocation identity need separate admission |
| `breakpoints.create`, `breakpoints.delete`, `breakpoints.list` | Core / Trace and events | QEMU TCG execution/data controls exist; preserve byte-free breakpoints, access kind, length, bounded count and cause/resume semantics |
| `trace.start`, `trace.read`, `trace.stop` | Trace and events | Stopped-boundary machine/source traces exist; ordinary debug stops do not prove retirement, and no equivalent streaming before-fetch trace cursor is supplied |
| `video.screenshot`, `video.probe` | Clock, media and input | Stopped QMP surface/CPU/clock bracket and PNG exist; they do not establish the DOSBox last-completed-frame, scanline, mode, guest-tick or revision contract |
| `input.keyboard.press`, `input.keyboard.type`, `input.keyboard.state` | Clock, media and input | State reports owned queue/leases and immediate or scheduled receipts. Optional virtual keyboard extensions arm one timed chord or 1..64 US-layout characters, retaining a delivered prefix and held leases on cancellation. Native BIOS/IRQ witnesses separately inspect selected consumption cases |
| `input.keyboard.down`, `input.keyboard.up`, `input.keyboard.frame_edges` | Clock, media and input | Machine-owned make/break leases support immediate, explicit virtual-delay or generation-checked modeled-retrace scheduling; stale leases invalidate on close. A modeled callback phase does not qualify guest-frame edges, consumption or replay parity |
| `input.mouse.move`, `input.mouse.click`, `input.mouse.button`, `input.mouse.state` | Clock, media and input | Relative PS/2 movement/button leases support immediate or scheduled dispatch. The button route also has an opt-in passive timed pair with separate syncs and explicit held-lease recovery. DOSBox INT33, pixel/range mapping, coordinate clicks and guest cursor state remain unqualified; IRQ12 packet evidence is a separate witness |
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
| Trace and predicates | `debug-trace`, `debug-trace-until` | Raw stopped-boundary traces; verified COM/MZ source traces, register/PC/region predicates and saved event searches. Virtual profile adds stopped clock brackets and run/epoch-bound time ranges. Initial real-mode module only; no queued input or overlay rebinding |
| Waits and input | `debug-wait`, `debug-keyboard-press`, `debug-keyboard-type`, `debug-keyboard-state`, `debug-keyboard-down`, `debug-keyboard-up`, `debug-click`, `debug-click-frame` | Owned make/break/state routes and opt-in native timed chords/text have partial support; legacy waits, coordinate clicks, guest layout and frame contracts remain open |
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

The QEMU-only scheduling routes are `debug-input-schedule` and
`debug-input-schedule-observe`; cancellation/resolution uses
`debug-input-cancel-pending`. Their Python names are `input_schedule(delta_ns)`,
`input_schedule_observe()` and `input_cancel_pending()`. Saved scripts use
`input-schedule`, `input-schedule-observe` and `input-cancel-pending`, with the
same capability admission and one shared host deadline. They are additional
native surfaces, not new names in the 83-route legacy DOSBox qualification set.

`debug-mouse-button-click` is also QEMU-only. It routes directly to
`mouse_button_click`, with script operation `mouse.button-click`; it adds no
`GuestMouse` facade or legacy `DebugSession` stub. It does not replace the
coordinate/frame behavior of `debug-click` or `debug-click-frame`, and it adds
no row to the frozen 127-surface promotion inventory.

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
| Native one-shot virtual input, ownership and callback receipts | `tests/test_qemu_input_schedule.py`, `tests/test_qemu_input_schedule_native.py` |
| Layers and code views | `tests/test_code_layers.py`, `tests/test_code_overlap_native.py`, `tests/test_runtime_code.py`, `tests/test_screenshot_hooks.py` |
| Checkpoints and histories | `tests/test_anchor_stone_cli.py`, `tests/test_rewind_native.py`, `tests/test_cpu_deltas_native.py`, `tests/test_delta_policies.py`, `tests/test_debug_timeline_deltas.py`, `tests/test_frame_timeline_native.py`, `tests/test_debug_experiments.py` |
| Scenes and workflow consumers | `tests/test_scene_domain_integration.py`, `tests/test_scene_readiness.py`, `tests/test_input_macros.py`, `tests/test_movement.py`, `tests/test_spatial_native.py`, `tests/test_progressive_scenes.py`, `tests/test_player_live.py` |
| Backend fallback, wrappers and Windows | `tests/test_dos_qemu.py`, `tests/test_ida_dosbox.py`, `tests/test_doctor.py`, `tests/test_dosbox_window.py`, `tests/test_windows_native.py`, `tests/test_win16_native.py` |

The scheduling host witnesses target hostile receipts, token/batch ownership,
terminal freeze, UTF-8 reason bounds, owned clock-budget cutoffs, early-stop
resolution and deadline/cleanup failures. Native witnesses use independent
IRQ1/IRQ12 state, an otherwise halted guest, retained renderer output, actual
DOS exit/TSR and retained JSON/scripts. They distinguish callback dispatch from
guest consumption and test source isolation and historical receipt reopening.
These file references do not assert a passing run; exact results and remaining
scope belong in the [handoff log](DOS_QEMU_HANDOFF.md).

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
