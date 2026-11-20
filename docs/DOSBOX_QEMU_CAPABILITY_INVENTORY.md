# DOSBox-X to native QEMU: capability inventory

This inventory preserves the migration boundary at
`089c1841c415eb2b5cdfa90d03b6291a07f73919` and reconciles source availability
against `1b3c11736fff947b5b34b6d7014cfe425bd6d074`, with the stereo and bounded
macro, runtime-memory, bounded host-proof, spatial-policy and movement integrations through
`ec3a6ec548a46b3dd2c4f5149446b823c6005891`.
It is a coverage ledger, not a runtime parity claim. Each surface
needs native acceptance, affected DOSBox regressions and a reviewed observable
comparison before its qualification advances.

**Keep `dosbox` and `dosbox-qemu` selectable while proving parity.** Unsupported
operations must fail before mutation. An uncertain native result must not trigger
an automatic retry on another backend. Changing the default and removing the
retained runtime are separate gates. The removal gate stays closed while any
required behavior is missing, unqualified, or has no recovery path.

## Current remaining work

The packaged [source inventory](../src/fdisbull/data/dos-migration.json) contains
**143 required surfaces: 37 backend RPCs, 83 public routes and 23 extra
surfaces**, plus **seven required compatibility campaigns**. Every qualification
remains open. The original nine extra surfaces have been joined by fourteen
explicit workspace/file-service surfaces; the old 127/134/141 totals are historical.

The machine-readable [remaining work plan](DOS_QEMU_PARITY_WORK.json) assigns
every identifier to exactly one of eighteen contract groups. It supplies
existing pytest argument lists, explicit runtime inputs, missing adapters and
primitives, and the minimum independent observations for each campaign. The
listed test sets are reusable selections; only separately linked execution
receipts establish results. A missing runtime, skipped native case or absent
primitive remains an open gate.

Source inspection finds all seventy public routes currently marked partial on
`QemuDOSProcessSession`; the thirteen routes marked pending are absent.
Method presence establishes availability only. In particular:

- Native checkpoint rewind, selected CPU/RAM undo, renderer timelines,
  comparative trials, RAM/fetch layers, hooks and fourteen workspace services
  already have bounded implementations and existing native tests. Their next
  work is contract composition and qualification, not a fresh port.
- Protected LE admission, stopped source binding, trace/event identity and
  separate LE checkpoint/capture histories exist. They do not recreate the old
  MZ allocation authority. The three [runtime RAM routes](QEMU_RUNTIME_MEMORY.md)
  now supply explicit ordinary physical or observed unpaged linear witnesses
  with their own owner/epoch and write guards.
- Retained renderer probes, physical timed mouse buttons and declared relative
  coordinate scaling are prerequisites for the missing completed-frame,
  absolute/INT33 click and coherent frame consumer contracts. Keep those
  distinctions visible through input routing, controls and recovery.
- The independently reviewed [bounded macro adapter](QEMU_MACROS.md) now
  composes admitted native input, run, wait and observation primitives while
  preserving held-key ownership and incomplete stops. The [host proof adapter](QEMU_MODEL_PROOFS.md) now checks caller-supplied
  finite-width models with run provenance and no guest effects. The
  [witnessed movement adapter](QEMU_WITNESSED_MOVEMENT.md) now composes held keys,
  explicit runtime RAM predicates and native virtual time. Richer movement,
  scene/workflow and screenshot-hook contracts remain pending. Macro route
  availability does not qualify their separate contracts. The
  [integrated native evidence](evidence/qemu-macros-runtime-memory-2026-11-18/README.md)
  covers two macro and two runtime-memory cases without native skips.
- The [host spatial policy](QEMU_SPATIAL_POLICY.md) now preserves the shared
  voluntary mode and irreversible fair-play latch through actual native owner
  replacement. It does not add the still-missing spatial action/scene routes.
- The [explicit stereo capture evidence](evidence/qemu-stereo-capture-2026-11-18/README.md)
  records nine native cases on macOS and nine on Linux, including paired
  asymmetric tones, hot/cold futures and malformed core4 refusal. General
  audio fidelity and real-game composition remain separate obligations.
- Original [Ultimate Doom](evidence/qemu-doom-stereo-2026-11-18/README.md),
  [TNT and Plutonia](evidence/qemu-final-doom-stereo-2026-11-18/README.md)
  now have paired installed-DOSBox/QEMU boot and firing observations, plus exact
  QEMU hot/cold 600 ms machine/audio futures. Their frozen producer still has
  the separately reproduced single-cycle stereo length bug. These bounded
  game receipts do not qualify audio fidelity or the full real-game campaign.
- The existing paired Tic-Tac-Toe file now covers full rounds, recovery/replay,
  reset and guest exit. Original Five Dice and Snake add source-assisted
  complete-game/RNG and keyboard/growth/clock/exit witnesses. Actual
  QEMM/DESQview, protected real-game media/input,
  Windows and clean installed fallback campaigns still require their declared
  evidence. Authored task schedulers and parser tests cannot substitute for
  vendor execution.

Run the affected existing test groups first, implement each blocked primitive
with an independent guest oracle, then run its compound consumers and the seven
campaigns. Reuse a fresh receipt across surfaces only when its assertions cover
each contract. Do not promote a row from a method count, a historical receipt or
an aggregate passing-test total.

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

The checkpoint slice now has an explicit raw-machine QCOW2 profile. It saves
the stopped machine and private guest disk and restores them in a fresh QEMU
process. The authored witnesses compare CPU, RAM and guest-written sectors,
reopen the project, and check stale memory plan/rule refusal. Source-bound DOS
process restore, instrumented profiles, state forks and history consumers
remain unqualified; the checkpoint rows are partial.

The separate native-only [owned-machine recovery contract](DOS_OWNED_MACHINE_CHECKPOINTS.md)
now has [bounded original-Doom hot/cross-host/exit evidence](evidence/qemu-owned-machine-recovery-2026-11-14/README.md).
It deliberately retires source authority and does not advance the stronger
source-bound checkpoint/history rows or the default/removal gates.
The opt-in `rebind_protected_source=True` load option performs a fresh stopped
LE admission after machine recovery. It never restores the old handle or MZ
allocation authority. The separate
[LE checkpoint and stopped-capture history](DOS_LE_SOURCE_CHECKPOINTS.md) now
persists and revalidates that LE relation. Ordinary MZ histories, trials/undo and
the default/removal gates retain their distinct qualification requirements.

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

The audited DOSBox surface comprises **37 backend RPC methods** and **83
public debugger route names** resolving on `DebugSession`. Two of those public
routes intentionally refuse direct DOS writes. Counting names alone is
insufficient: inherited methods can still reject the selected backend, and
apparently similar operations can have different timing, state or address
semantics.

Together with the twenty-three extra surfaces, **all 143 default-switch
qualification rows remain open**. New native prerequisites do not promote
their legacy consumers or a compatibility campaign. DOSBox remains the default
and both DOSBox selectors remain available.

The ninth optional native extension adds `renderer_probe` through
`display_probe(points, *, window=None, update_id=None, timeout_ms=1000)`, JSON
`debug-display-probe` and script `display-probe`. It samples zero through 256
ordered RGB coordinates from the existing private retained renderer publication,
with exact optional window/update guards and unchanged stopped clock brackets.
It creates no screenshot artifact, refresh, guest execution or input. Both
expected identity fields are required together because update IDs restart per
window. Strict arguments validate before admission; script literals validate
before earlier effects and resolved values validate again. One intersected host
deadline covers I/O and persistence. Invalid native evidence or failed/late
persistence closes with available evidence and no retry.

This adds a sparse renderer observation prerequisite. `video.probe` and
`debug-frame-probe` remain pending: their legacy mode/frame/state identities are
not supplied by a renderer update. Coordinate clicks, INT33 mapping, application
readiness and completed guest frames remain separate. Full pixel hashes still
come from `capture_display()`. All 143 promotion qualifications remain open.

The bounded [public DESQview raw-checkpoint witness](DOS_QEMU_HANDOFF.md#public-desqview-checkpoints-and-fresh-physical-qualification-2026-11-14) now composes an attached automatic observer with standard raw save/load. Save suspends only its verified native control while paused; restore replaces the owner/epoch and requires fresh snapshot/certificate authority. Two original-guest endpoint pairs and eleven preservation cases passed locally. User/hook breakpoints, active raw layers, pending lifecycle stops and unreleased input still refuse. The original selected RAM window was unchanged before restore, so this is saved-window preservation; changed-RAM recovery has separate authored witnesses. Broader parity and default-switch gates remain open.

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

The table covers the complete pinned stable and layers server sources.
`layers.configure` requires the layers profile. The offline source census
reconstructs both servers, validates their hashes and reconciles known-method
declarations with exact dispatch and explicitly reviewed prefix fallbacks.
Host consumer calls are checked separately. Neither census is runtime
qualification.

| RPC methods | Slice | Existing native seam and remaining distinction |
| --- | --- | --- |
| `agent.capabilities` | Core | Machine capability metadata exists; advertise only implemented, admitted operations and distinguish availability from qualification |
| `debug.output.read` | Core | Cursor-paged diagnostic output has no equivalent public QEMU cursor; owner logs and event artifacts need an explicit consumer/retention disposition |
| `debugger.execute_command` | Core | Stopped `HELP`/`CPU`/`PIC` only. The protected source matcher has a bounded QEMU CPU/GDT alternative; raw/parsed replies, HELP/PIC and rejection semantics remain unqualified |
| `session.start` | DOS process | Native COM/MZ adapter now uses actual DOS EXEC, verifies PSP/MCB, ordered relocations and exact loader writes, then stops at entry; protected/V86 and full DOSBox launch parity remain unqualified |
| `session.status`, `session.stop` | Core / DOS process | Machine status/cleanup exist; machine stop or process reaping is not selected DOS process termination |
| `execution.continue`, `execution.pause`, `execution.step`, `execution.wait` | Core | QMP/GDB control exists. Optional counted steps retain native stop observations under one deadline; DOSBox step-over/reply parity stays open. Bounded machine run is not the DOS asynchronous-operation schema or guest-time run contract |
| `execution.timing` | Clock, media and input | `clock_observe` separates machine icount, host time and opt-in API1 native virtual nanoseconds. `clock_advance` retains requested/fired/stopped times and earlier native stops; opt-in `clock_sync_*` preserves a fixed 1:1 host mapping and `retrace_wait` verifies one modeled transition. Legacy guest_ms and exact-cutoff parity remain unqualified |
| `state.get_registers`, `state.set_register` | Core | GDB register inspection/guarded writes exist; expose CPU mode, segment bases, widths and selected-vCPU identity, without inventing DOS source coordinates |
| `memory.read`, `memory.write` | Core / DOS process | Physical and selected-vCPU virtual memory plus guarded writes exist; DOS segmented/static addresses and task/allocation identity need separate admission |
| `breakpoints.create`, `breakpoints.delete`, `breakpoints.list` | Core / Trace and events | QEMU TCG execution/data controls exist; preserve byte-free breakpoints, access kind, length, bounded count and cause/resume semantics |
| `trace.start`, `trace.read`, `trace.stop` | Trace and events | Stopped-boundary machine/source traces exist; ordinary debug stops do not prove retirement, and no equivalent streaming before-fetch trace cursor is supplied |
| `video.screenshot`, `video.probe` | Clock, media and input | Stopped QMP surface/CPU/clock bracket and PNG exist; they do not establish the DOSBox last-completed-frame, scanline, mode, guest-tick or revision contract |
| `input.keyboard.press`, `input.keyboard.type`, `input.keyboard.state` | Clock, media and input | State reports owned queue/leases and immediate or scheduled receipts. Optional virtual keyboard extensions arm one timed chord or 1..64 US-layout characters, retaining a delivered prefix and held leases on cancellation. Native BIOS/IRQ witnesses separately inspect selected consumption cases |
| `input.keyboard.down`, `input.keyboard.up`, `input.keyboard.frame_edges` | Clock, media and input | Machine-owned make/break leases support immediate, explicit virtual-delay or generation-checked modeled-retrace scheduling; stale leases invalidate on close. A modeled callback phase does not qualify guest-frame edges, consumption or replay parity |
| `input.mouse.move`, `input.mouse.click`, `input.mouse.button`, `input.mouse.state` | Clock, media and input | Relative PS/2 movement/button leases support immediate or scheduled dispatch. The button route also has an opt-in passive timed pair with separate syncs and explicit held-lease recovery. DOSBox INT33, pixel/range mapping, coordinate clicks and guest cursor state remain unqualified; IRQ12 packet evidence is a separate witness |
| `frame.step` | Clock, media and input | `advance_frames` stops at native renderer publications; the completed-guest-frame step contract remains open |
| `state.save`, `state.load` | Checkpoints | Restricted raw, source-bound COM/MZ, owned-machine and explicit LE checkpoint contracts exist, including fresh-process restoration. Their authority and disk policies differ; DOSBox `.sav` data cannot be interpreted as QEMU state |
| `layers.configure` | Layers and hooks | Optional native guarded RAM/fetch layers and source/task-bound host adapters exist; qualification must preserve visibility, precedence, preimages, translation invalidation and cold control identity |

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

| Group | Public routes | Inspected native availability; qualification remains open |
| --- | --- | --- |
| Core control and inspection | `debug-status`, `debug-registers`, `debug-breakpoint`, `debug-delete-breakpoint`, `debug-memory`, `debug-run`, `debug-contexts`, `debug-script` | Machine equivalents exist with different scope/signatures; the full legacy DOS script grammar and source mapping are pending |
| Explicit direct-write refusals | `debug-write-memory`, `debug-write-registers` | Legacy DOS deliberately refuses these routes; preserve that contract while native machine writes remain explicitly guarded |
| Memory investigations and driver context | `debug-memory-snapshot`, `debug-memory-apply`, `debug-memory-rule-tick`, `debug-desqview-observe`, `debug-bind-runtime-memory`, `debug-runtime-memory`, `debug-write-runtime-memory` | Snapshot, one-shot edit/rule and report code has machine paths; live runtime bindings and source/task identity need qualification |
| Periodic memory rules | `debug-memory-rule-run` | Partial explicit QEMU virtual-clock route with guarded native RAM views, owned overlays and hook-aware stops; ten bounded authored native cases and a 1,159-test bounded regression passed; broader parity remains unqualified |
| Trace and predicates | `debug-trace`, `debug-trace-until` | Raw stopped-boundary traces; verified COM/MZ or explicitly bound embedded-LE source, register/PC/region predicates and saved event searches. Virtual profile adds stopped clock brackets and run/epoch-bound time ranges. LE code relation supplies no allocation/task authority; streaming and general action causality remain open |
| Waits and input | `debug-wait`, `debug-keyboard-press`, `debug-keyboard-type`, `debug-keyboard-state`, `debug-keyboard-down`, `debug-keyboard-up`, `debug-click`, `debug-click-frame` | Owned make/break/state routes and opt-in native timed chords/text have partial support; legacy waits, coordinate clicks, guest layout and frame contracts remain open |
| Frames | `debug-screenshot`, `debug-frame-probe`, `debug-frame-advance`, `debug-frame-inputs` | Stored surfaces, renderer publication advancement and owned frame-key edges exist. Legacy frame-probe/raw RGBA and completed-guest-frame equivalence remain open |
| Checkpoints and Anchor Stones | `debug-save-state`, `debug-load-state`, `debug-save-anchor-stone`, `debug-load-anchor-stone` | Native serializers, admitted source/disk/control identity and fresh-process restore exist. Raw, COM/MZ, owned-machine and LE authority remain separate; broader device/workload qualification is open |
| Layers, code and controls | `debug-layer-stack`, `debug-layer-enable`, `debug-layer-patch`, `debug-code`, `debug-capture-code`, `debug-branch`, `debug-cave`, `debug-hook`, `debug-hooks`, `debug-delete-hook`, `debug-controls`, `debug-screenshot-hooks` | Bounded RAM/fetch/source layers, code views, hooks and experiment control receipts exist. The screenshot-hooks adapter remains absent; source/task/mapping and preparation/capture composition need qualification |
| Reproducible trials | `debug-save-experiment`, `debug-restore-experiment`, `debug-compare-experiment` | Bounded full-checkpoint baseline/candidate trials and final recovery exist. Incomplete/misaligned observations cannot prove equality; file/media/workload composition remains open |
| Checkpoint rewind | `debug-rewind-start`, `debug-rewind-status`, `debug-rewind-record`, `debug-rewind` | Native bounded checkpoint histories, branches and cold restore exist; separate stopped LE capture history does not broaden ordinary MZ authority |
| CPU/RAM deltas | `debug-delta-start`, `debug-delta-status`, `debug-delta-record`, `debug-delta-rewind`, `debug-delta-recover` | Native selected projections, guarded inverse, frozen partial-state boundary and full recovery exist. Hidden CPU/device rollback and continued execution from a partial inverse are not claimed |
| Frame history | `debug-timeline-start`, `debug-timeline-status`, `debug-timeline-advance`, `debug-timeline-rewind`, `debug-timeline-stop`, `debug-timeline-pin`, `debug-timeline-image` | Bounded checkpoint/PNG renderer DAGs, full or lossless delta retention, branches, pin reconstruction and fresh held-key ownership exist. Completed guest frames and broader file-aware composition remain open |
| Scenes | `debug-scene-check`, `debug-scene-assert`, `debug-scene-click`, `debug-scene-act`, `debug-scene-wait`, `debug-scene-navigation` | Reusable host algorithms, pending native frame/input dependencies |
| Macros, movement and proofs | `debug-macro`, `debug-move`, `debug-proof-check` | Bounded macro route is implemented with native ownership and one total deadline. Bounded model proofs and witnessed held-key movement are implemented; richer postconditions remain pending |
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
no row to the legacy RPC/public-route set. The complete current inventory has
143 required surfaces, including its explicit workspace additions.

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

The tenth optional extension adds `vga_configuration` and the stopped
`vga_configuration_observe` / `debug-vga-configuration` / `vga-configuration`
routes. It requires the explicit virtual/precise profiles and the native
clock/display/retrace/configuration command set. A conservative raw vector and
write-time lifetime generation distinguish current configuration from the
configuration observed at a retained renderer publication. A-to-B-to-A,
same-size origin/pitch/panning and byte-order changes can invalidate identity
without changing dimensions. DAC palette and VRAM contents remain outside the
configuration vector. See the [configuration contract](DOS_QEMU_MIGRATION.md#observe-current-and-published-vga-configuration).

This separate QEMU observation adds no row to the frozen DOSBox promotion
inventory. A publication stamp does not prove raster coherence, guest frame
completion, BIOS mode identity, INT33 mapping or scene readiness. Native reset,
overflow and restore invalidation do not supply checkpoint parity. All 143
promotion qualifications remain open and DOSBox remains the default.

The eleventh optional [display-motion extension](../native/qemu-display-motion/README.md)
adds `mapped_mouse_motion`: `mouse_move_mapped`, JSON
`debug-mouse-move-mapped` and script `mouse.move-mapped`. Caller-declared rational
axis scales convert a bounded image displacement to exact QEMU REL event units.
The passive 2 ms attempt requires an empty owned queue and an explicitly stopped
nonempty publication whose current/published VGA generations agree. Native arm
and callback both check publication/configuration identity. A valid change
cancels before any motion event; the protected pending plan requires explicit
cancellation before a fresh request. Existing explicit run, clock advance and
clock auto-sync remain the execution routes.

This narrowly extends relative movement without supplying an absolute pointer
or verified driver calibration. Count values fit −127..127, with no rounding or
splitting; packet acceptance still remains unknown. An authored guest separates
packet receipt, application pointer commit and drawing, including a deliberately
wrong scale. Actual pixel travel, pointer position, raster freshness and arbitrary
INT33 behavior remain unqualified. This adds no promotion row; all 143 remain open.
See the [mapped motion contract](DOS_QEMU_MIGRATION.md#move-with-a-declared-image-to-relative-scale).

## Regression witnesses and promotion gates

These are existing candidate tests, not a report that this inventory ran them.
Use the narrow affected tests as each slice lands; run a wider composition only
to settle a remaining risk. Preserve local receipt identities and do not
automatically start hosted CI.

| Boundary | Existing witness files |
| --- | --- |
| Machine control, memory, capture, restart and source isolation | `tests/test_qemu_machine.py`, `tests/test_debugger.py`, `tests/test_debug_semantics.py` |
| DOS entry and process lifecycle | `tests/test_dos_com.py`, `tests/test_dos_launch.py`, `tests/test_dos_guest_exit.py` |
| Paired original game witnesses | `tests/test_qemu_dos_game_parity_native.py` (Tic-Tac-Toe full round/recovery/replay/reset/exit), `tests/test_qemu_dos_workloads_native.py` (source-assisted original Five Dice and Snake); these assetless fixtures do not qualify mouse, protected-game or full-raster behavior |
| Mode, mapping, QEMM/DESQview and searched RAM | `tests/test_dos_memory.py`, `tests/test_qemm_runtime.py`, `tests/test_desqview_runtime.py`, `tests/test_desqview_memory_native.py`, `tests/test_memory_search_runtime.py`, `tests/test_memory_rules.py` |
| Traces and event predicates | `tests/test_execution_trace.py`, `tests/test_execution_event_native.py`, `tests/test_protected_mode_trace.py` |
| Guest time, completed frames and input | `tests/test_debug_wait.py`, `tests/test_keyboard.py`, `tests/test_frame_capture_native.py`, `tests/test_frame_coherence.py`, `tests/test_screenshot_codecs.py`, `tests/test_protected_runtime_native.py` |
| Native one-shot virtual input, ownership and callback receipts | `tests/test_qemu_input_schedule.py`, `tests/test_qemu_input_schedule_native.py` |
| Sparse retained renderer pixels and exact publication identity | `tests/test_qemu_display_probe.py`, `tests/test_qemu_display_probe_public.py`, `tests/test_qemu_display_probe_native.py` |
| Current VGA configuration and configuration observed at publication | `tests/test_qemu_vga_configuration.py`, `tests/test_qemu_vga_configuration_public.py`, `tests/test_qemu_vga_configuration_native.py` |
| Declared image displacement and publication/configuration-bound relative callbacks | `tests/test_qemu_mapped_mouse.py`, `tests/test_qemu_mapped_mouse_public.py`, `tests/test_qemu_mapped_mouse_native.py` |
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

The coverage check derives public routes from the router and `DebugSession`
inheritance, including methods that explicitly refuse. Raw native names come
from the **complete reconstructed server**, not patch hunks:

```sh
python scripts/dosbox_rpc_census.py
```

The [160 KB pinned upstream member](../experimental/dosbox-x/census/README.md)
makes exact in-memory stable/layers reconstruction possible in ordinary offline
tests. Baseline/member, patch and resulting-source identities must all match.
The helper reconciles the complete known-method filter with every dispatch
use, rejects unknown syntax and requires explicit statement evidence for the
existing `input.mouse.state` prefix fallback. It accepts no new method merely
because its namespace resembles an old one.

The host literal scan covers session/mixin helpers and
`runtime_source_matching`, expands literal `_keyboard_call` operations and
accepts all syntactically valid RPC namespaces. In particular,
`runtime_source_matching._descriptors` calls `debugger.execute_command` with
`CPU`; its QEMU monitor-read alternative is a partial consumer implementation,
not full public diagnostic compatibility.

There are 36 stable / 37 layer-profile RPC names and 83 legacy public routes.
The earlier 35-row RPC ledger missed unchanged upstream `debug.output.read`
and `debugger.execute_command` because neither name occurs in a supplied patch
hunk. Both are now explicit unqualified obligations, bringing the current gate
to **143 surfaces plus seven campaigns**. The diagnostics are read-only and
restricted; no arbitrary monitor-command passthrough is added.

Tests require exact ledger equality, unique entries, complete work-plan
partitioning, recognized slices and existing witnesses. They also reject
missing/extra declarations or dispatch, missing fallback code and source/hash
drift. A native patch/manifest update is checked automatically against the
same pinned baseline, without rewriting a generated census list. New or
removed surfaces require deliberate inventory changes. Referenced tests,
advertised capabilities and importable methods never qualify native parity.

### 2026-11-16: scoped digital SB16 audio

The optional [SB16 extension](../native/qemu-sb16-checkpoint/README.md) adds
U8 mono/stereo guest voices with retained 32 kHz mono U8 PCM and passive
DSP/DMA/IRQ/timer/mixer checkpoint restoration. The
[dated receipt](evidence/qemu-sb16-checkpoint-2026-11-16/README.md) gives the
authored, application and preservation gates separately. This is an explicit
profile and exact native-build contract. OPL/FM/music, ideal amplitude and
paired DOSBox-X audio remain unqualified. The backend default and retirement
gates do not change.

### 2026-11-16: corrected bounded history-root CPU continuation

The [timing fix](evidence/qemu-history-cpu-timing-2026-11-16/README.md) pins the
virtual profile's RTC to VM time and moves selected SB16 DMA service off the
host idle loop. The actual Doom explicit/root continuations now match full
exposed CPU as well as PCM/chunks, device, image and clock/count across hot and
separate-process recovery. This resolves the observed endpoint discrepancy
for the qualified tuple. It does not enable general deterministic replay,
complete a whole migration milestone or change the default/removal gates.

## 2026-11-16 OPL2 qualification update

The distinct `sb16-opl` profile provides bounded combined FM music and digital
effects persistence on its exact native/tool tuple. It retains OPL operator,
envelope/LFO/noise/register and wrapper state plus two named audio voices and
callback order. Original Doom passes six hot/cold selections and all four full
CPU/media continuations through explicit and history-root checkpoints.
[Detailed gates](evidence/qemu-opl-checkpoint-2026-11-16/README.md) keep signal,
persistence, native preservation and broader compatibility evidence separate.

FM/OPL2 is no longer wholly untested, but this does not close general device
parity: OPL3, MIDI, hardware-timed AdLib timers, analog waveform fidelity, paired
DOSBox-X comparison, broad mixed-device stress and portable delivery remain
unqualified. Existing trials, histories, layers, hooks and IRQ contracts retain
their prior scope. DOSBox-X remains the default and is retained. No CI.
