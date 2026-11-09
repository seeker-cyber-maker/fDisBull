# Native QEMU DOS migration

Use `dos-migration` to inspect the current slices, capability gaps and default
promotion gate. The ledger covers all current DOSBox RPC methods and public
debugger routes plus non-method surfaces. Test references are requirements,
not a claim those tests ran. DOSBox stays the default and remains selectable
after the migration; an uncertain operation never triggers an implicit fallback.

## Choose the backend explicitly

| Selector | Execution environment |
| --- | --- |
| `dosbox` | Retained patched DOSBox-X; existing COM/MZ project route |
| `dosbox-qemu` | DOSBox-X inside a prepared Linux/QEMU guest |
| `qemu-dos` | Native QEMU PC; original raw disk or original COM/MZ plus a separate DOS boot disk |
| `qemu-machine` | Existing generic raw machine and QEMM/DESQview contexts |

Native QEMU currently supplies machine controls, physical/virtual memory,
guarded edits, break/watchpoints, stopped-boundary trace artifacts, stored PNGs
when the QEMU build supports them, and stopped memory snapshot/search/edit/rule
operations. The process slice adds real DOS EXEC loading, verified PSP/source
entry and selected-process exit/TSR observations. Source-bound trace predicates
and persistent event searches cover the initial verified real-mode module.
Owned keyboard and relative PS/2 mouse input, optional native virtual-time batch
scheduling, explicit instruction-count observation and stopped surface/CPU/clock
captures are now available.
Frame-timed input, native checkpoints, fetch layers and scene parity remain later
slices. Periodic memory rules still need their native clock integration and
qualification; explicit stopped rule ticks are available.

## Check an installation without a game

```sh
fdisbull dos-migration
fdisbull dos-migration --surface debug-save-state
fdisbull doctor --backend qemu-dos --executable /path/to/qemu-system-x86_64 \
  --qemu-firmware /path/to/qemu/share/qemu --qemu-transport pipe \
  --output /private/qemu-core-check
```

Doctor executes authored boot code. Inspect its scope and individual checks:
it does not boot DOS or qualify drivers, checkpoints, games or timing parity.
The core doctor requires QEMU 9.1+ and no custom patch. A minimal QEMU build
may lack stored-display capture; that capability is observed at startup.

`pipe` uses private POSIX process streams/FIFOs without a network listener.
The default `unix` transport remains available for existing environments.
Dispatched control failures are terminal when their outcome is uncertain.

## Launch a caller-owned DOS disk

Keep source disks, project databases and runtime artifacts outside Git. A
native DOS disk has complete 512-byte sectors, a boot signature and at most
64 MiB. Standard floppy sizes use A:; other sizes use the IDE disk. The basic
profile uses one 486, 32 MiB and no network. Configuration is not boot proof.

```sh
fdisbull dos-profile /private/DOS.img
fdisbull import /private/DOS.img /private/dos-native.fdb \
  --arch x86 --bits 32 --base 0 --entry 0
fdisbull debug /private/dos-native.fdb --backend qemu-dos \
  --executable /path/to/qemu-system-x86_64 --game-dir /private \
  --qemu-firmware /path/to/qemu/share/qemu --qemu-transport pipe
```

The 32-bit raw file-address view allows a whole floppy in the project; actual
instruction width comes from observed CPU state. Raw disk offsets are not a
loaded program's source addresses. The machine starts paused at reset. In the
same retained JSON server, use the returned run ID with `debug-breakpoint` at
`0x7c00`, `debug-run`, `debug-registers`, and explicitly physical/virtual
`debug-memory`. `debug-step` is one instruction boundary, without the DOSBox
count option. A data watch uses `debug-breakpoint` with `access` and `length`.

Prepared `dos-profile --cpu max --memory-mib 64` output can be supplied as the
`guest_profile` object to JSON `debug-launch`. For installed QEMM or DESQview,
select its existing pinned profile with `--guest-profile qemm` or `desqview`;
report ingestion and actual kernel compatibility remain separate evidence.

Project identity, admitted profile and private runtime copy must agree. QEMU
runs with a disposable disk snapshot over that copy, preserving the source
disk. Closing discards runtime disk changes. An explicit firmware directory is
recorded by file hashes at admission; the default firmware path is unpinned.

Use scripts with `backend: "qemu-dos"` for the supported native operations.
Unknown or unsupported operations must refuse before execution. Stored trace
completion and display-surface capture do not acquire DOSBox fetch/frame
semantics just because their method names resemble each other.

## Keep the fallback testable

Launch an original COM/MZ project explicitly with `--backend dosbox` when a
migration gap or late regression requires comparison. Retain the old executable,
its preparation recipe and native regression tests. A raw disk project and a
COM/MZ project have different address mappings; never silently convert them or
restore one emulator's checkpoint into the other.

Transfer slices in dependency order: core; DOS process/drivers; traces/events;
clock/media/input; checkpoints; layers/hooks/block services; histories;
workflows; compatibility and fallback campaigns. QEMM, DESQview, Windows and
real games each require actual runtime evidence beyond the authored snippets.
Custom hostcalls, asynchronous providers and UDL/UIL joins remain a later slice;
the native launcher does not activate the earlier experiment's opcode hooks.

## Launch an original DOS process

For an original COM/MZ project, select `qemu-dos` with a separate
`dos_boot_image`, `dos_mcopy`, `dos_startup_batch` (default `FDAUTO.BAT`) and
`dos_arguments` (literal CP437 command tail, at most 126 bytes).

```sh
fdisbull import /private/game/TARGET.COM /private/target.fdb --image com
fdisbull debug /private/target.fdb --backend qemu-dos \
  --executable /path/to/qemu-system-x86_64 --game-dir /private/game \
  --dos-boot-image /private/DOS.img --dos-mcopy /path/to/mcopy \
  --dos-startup-batch FDAUTO.BAT --dos-arguments ' ALPHA.TXT /Q' \
  --qemu-firmware /path/to/qemu/share/qemu --qemu-transport pipe
```

The startup batch must already exist and return. Staging preserves its original
bytes and CONFIG files, appends an authored loader invocation, and uses private
disk copies. Required drivers/assets must already be on the FAT12/FAT16 boot
image; no host directory is mounted. COM2 is reserved for the loader protocol.
Conflicting names, changed source/disk, patched project versions, secondary
executable formats and inconsistent observations are refused.

`debug-dos-process` returns the real PSP/parent, MCB allocation, entry registers,
initial source map, environment segment, tail/FCBs, driver-chain observations
and process lifecycle. Read `source_mapping.runtime_base` and `delta` before
placing native breakpoints: machine controls do not translate static addresses.
The entire file-backed module is verified after ordered MZ relocations and
the exact DOS startup stack writes recorded in `loader_writes`. Initial load
verification is not continuous proof after self-modification or overlay loads.

The internal parent-return breakpoint yields `guest_exit` or `guest_tsr` only
after a matching helper report and DOS return category. Nested child completion
does not complete the selected process. Resident results retain observed
allocations and vector changes, without inferring which TSR instruction ran or
claiming vector-change causation. Exit/residency changes the capture epoch;
machine close invalidates live ranges. A failed observation is not a DOS exit.
The machine remains stopped and owned after a verified return.

Entry requires observed real mode. QEMM, DESQview, DPMI and V86 combinations
remain separate qualification campaigns. A registered device header or the
authored SYS initialization test does not establish arbitrary device I/O.
Source tests require real QEMU/FreeDOS and independent authored COM/MZ/TSR
witnesses; production uses the packaged helper without requiring NASM.

## Capture register and execution events

On a live COM/MZ process, `debug-trace` preserves the existing bounded-count
artifact route. `debug-trace-until` accepts the shared register, PC-range,
mnemonic, region-change and nonsequential predicates. For example:

```json
{"method":"debug-trace-until","params":{"run":"RETURNED_RUN","until":{"kind":"register","register":"ax","equals":7},"max_steps":100,"timeout_ms":10000,"name":"ax-seven.json"}}
```

Budgets count stopped QEMU debugger intervals. A stop can follow a fault or
partial REP progress; it does not certify instruction retirement. Artifacts
retain actual IRQ/timer stepping policy, full register observations, linear
and segmented PCs, verified source sites and the initial capture epoch.
Source-site hashes account for DOS relocation separately from observed byte
hashes, so independent launches can be compared at the same project site.

Use the returned `trace_artifact` with `event-trace-query`, `event-search-start`
and `event-search-refine`. Ordered entry/artifact receipts and source bytes are
rechecked after session close or project reopening. Only a closed qualified
window can narrow candidates. Self-modification, source/module departure,
allocation/epoch or mode changes stop the source binding; unbound boundaries
never acquire a source site. Inspect `source_window_closed`, `outcome` and
`error`, even if an explicit runtime predicate matched the final boundary.

Queued `action` input inside `trace-until` is refused before mutation. Dispatch
physical input with a bounded natural run, then start a separate trace at an
explicit breakpoint; the prior run is an unobserved interval, not contiguous
source-trace evidence or proof of input causation.
Raw-disk machine tracing remains separate and supplies no process source map.

### Relate source boundaries to virtual time

An initial COM/MZ process launched with `qemu_clock='virtual'` advertises
`source_trace_clock`. Its source trace events automatically retain a
`fdisbull-source-clock-1` clock with `domain='QEMU_CLOCK_VIRTUAL'`, the owned
`run`, host `epoch`, native `native_epoch`, `virtual_ns`, separate `icount`,
and compact `before`/`after` samples. The complete ownership, register and
instruction read must be bracketed by unchanged native time/counter/epoch.
The sequences share `clock_observe()`'s epoch; sampling does not add a separate
clock journal event for each side. Standard/instruction-profile source traces
and raw machine traces remain clockless.

Use a predicate with exact fields:

```python
observed = debug.clock_observe()
interval = {
    'kind': 'virtual-time-range', 'run': observed['run'],
    'epoch': observed['epoch'],
    'native_epoch': observed['virtual_clock']['native']['epoch'],
    'start_ns': observed['virtual_ns'],
    'end_ns': observed['virtual_ns'] + 1,
}
captured = debug.trace_until(interval, max_steps=0, timeout_ms=3000)
rows = project.event_trace_query(captured['trace_artifact'], predicate=interval)
```

This example observes the current stopped boundary without executing it. Bounds
are integer nanoseconds, `0 <= start_ns < end_ns <= 2**63`, with an excluded
end. A future live range is tested at each debugger stop, so it can be skipped;
it does not install a clock timer. Always bound steps and host time.

Query rows and search witness samples retain clocks after project reopen.
An optional query `endpoint_clock` preserves the final count endpoint from
`collector.current_stop.clock`, without adding an N+1 event to `trace(count=N)`.
Candidate site identities remain independent of time. Missing clocks or
foreign identities are unknown offline; malformed brackets are rejected even
when the query concerns only a register. Historical clockless records remain
supported.

A time predicate may match the observed final boundary after leaving the
source binding. Its source site stays unknown and its open source window
cannot narrow an event search.

Live and saved-script predicates must match the current run and both epochs.
Every nested clock leaf is checked before execution, including before earlier
script writes. Saved trace-until parameters remain literal: use identity from
an earlier request, not `$` interpolation from a step in the same script.
An unstable native clock closes ownership while preserving any already known
stop in the result.

Compare these timestamps with input `dispatch_ns`, renderer `published_ns` or
audio callback timestamps only within the same run and both epochs. Ordering
does not prove input consumption or causation, completed guest frames or
natural instruction latency. Equal timestamps do not establish callback order.
The actual GDB IRQ/timer step policy still applies, and instruction count is
never converted into elapsed virtual time. Host auto-sync is a separate,
explicit mapping; it does not reinterpret source-event timestamps.

One host deadline now includes trace lock admission, observations, stepping
and persistence, intersecting script/session/native-channel bounds. If it
expires before publication, `ExecutionTraceError.result` can contain the
partial stop with no artifact. A slow synchronous write may already have
committed an artifact or journal; its post-check still reports failure and
preserves any available IDs. Inspect the result instead of replaying the trace.

## Queue input and observe clocks/surfaces

While stopped, queue `keyboard_key_down(key)` and use its returned `lease` with
`keyboard_key_up(lease)`. The shared `keyboard.key_down/key_up` namespace works
too. `mouse_move_relative(dx,dy)` queues relative controller deltas;
`mouse_button_down(button)` and `mouse_button_up(lease)` own the matching
physical button. These are machine devices, including after a DOS child exits.
Relative motion does not identify pixels or supply a DOS INT33 mouse driver.

By default, `run(timeout_ms=...)` sends one GDB continue and at most one QMP input
batch, then reads the same native stop. Inspect `input_delivery.delivery`: either
`qmp_accepted` or `not_dispatched`. An early breakpoint can retain pending
input or follow acceptance before any guest consumption. `guest_consumed`
stays `None`; establish consumption with independent guest RAM/register/driver
evidence. Unknown delivery closes the VM without replay. Pending input blocks
step/trace/unbounded resume before execution.

`input_state()` reports the owned queue and leases. `input_cancel_pending()`
discards only unsent transitions; accepted holds still require explicit
release. Closing invalidates leases without pretending release code ran.
Limits: 256 pending edges, 64 leases and relative deltas -32767..32767.
Timed press/type, pixel clicks and frame-edge timing remain unsupported.
Make and break in one batch specify order, not a hold duration.

JSON routes are `debug-keyboard-down/up/state`, `debug-mouse-move-relative`,
`debug-mouse-button-down/up`, `debug-input-state`, `debug-input-cancel-pending`,
`debug-clock-observe` and `debug-capture-surface`. Script operations are
`keyboard.key-down/up/state`, `mouse.move-relative`, `mouse.button-down/up`,
`input-state`, `input-cancel-pending`, `clock-observe` and `capture-surface`.
Alias a down result and use `$alias.lease` for its release. Failed scripts
that touched physical input close the owned VM. Native input/capture/clock
operations refuse caller-owned database transactions during full preflight.
Their native I/O inherits the saved script's one host-time deadline; prior
channel bounds are restored afterward. Windows whole-machine snapshots refuse
pending or held machine input because their current sidecar cannot restore
these physical leases. Release/cancel explicitly before requesting a snapshot.

Select `qemu_clock='instruction'` in Python/JSON launch or
`--qemu-clock instruction` on the CLI for one TCG CPU with
`-icount shift=7,align=off,sleep=off`. `Project.machine` uses
`clock_profile='instruction'`. Default `standard` leaves the launch unchanged.
`clock_observe()` records `query-replay.icount` only for the explicit profile,
with a machine epoch, sequence and a separately labelled host timestamp.
Without that profile the counter is explicitly unsupported. `guest_ms` and
`virtual_ns` are `None` in the stock profiles: idle timer warps mean `count * 128` is not all
elapsed guest time. This is neither cycle accuracy nor exact live count/time
stopping. The instruction profile changes timing and must be chosen explicitly.

The optional `qemu_clock='virtual'` profile requires the fDisBull API1 clock
extension on QEMU10.0.13; stock QEMU is rejected before guest execution. It
uses the same single-CPU fixed-icount settings, observes
`QEMU_CLOCK_VIRTUAL` directly as `virtual_ns`, and keeps `guest_ms=None`.
Use `clock_advance(delta_ns, timeout_ms=1000)`, JSON `debug-clock-advance`,
or script `clock-advance`. Integer durations are 1..60,000,000,000 ns.

Each budget arms one virtual timer and issues one GDB continue, retaining
earlier break/watchpoints, DOS exit/TSR and physical-input delivery evidence.
Inspect the original `outcome` and `clock_budget` together. The latter records
the token, requested duration, start/deadline/fired/stopped times, elapsed time
and overshoot. `deadline_reached` says the timer fired; an early stop has no
firing time. Do not infer consumption, a completed frame, cycle accuracy or
an exact arbitrary-nanosecond cutoff. The extension's own pause is SIGINT;
real debugger traps stay SIGTRAP. A timer at a matching PC cannot fabricate
an execution breakpoint or a DOS parent-return event.

The host budget covers lock admission through final readback, cleanup and
persistence, intersecting existing script/channel limits. Unknown arm/cleanup
or expired post-execution observation closes the VM without replay. Cleanup
must prove both the timer and deferred stop request are gone. Reset/restore
invalidate the native epoch; migration after budget use is blocked. The
source repository's `native/qemu-clock/` contains the pinned patch and build
contract; the Python wheel alone does not provide a patched emulator.

Host startup budgets also differ from guest boot delays. The I/O witnesses
explicitly use FreeDOS `SWITCHES=/F` to omit its F5/F8 delay for both profiles;
the ordinary baseline exceeded 15 host seconds while still inside that guest
wait. Production preserves caller CONFIG files and never skips prompts or
extends a deadline automatically. This is post-boot I/O evidence on a declared
test configuration, not arbitrary boot-time qualification.

`capture_surface(name)` stores PNG bytes, unique capture ID, run/dimensions/hash,
selected CPU state and a stopped before/after clock bracket. `screenshot()`
uses the same path. Metadata is `source='qemu_display_surface'` with
`completed_guest_frame=None` and `guest_frame_id=None`. It can contain a
half-drawn screen; a capture ID proves no new frame or UI readiness. Standard
clock stability remains `not_observable`; instruction-profile stability is only
the observed counter. The virtual profile checks its direct clock as well.
A changed stopped bracket closes the VM and refuses it.

The independent native witness checks BIOS AX, IRQ1 make/break bytes, IRQ12
mouse packets, separate consumption/draw points and PNG pixels under QEMU
10.0.13/FreeDOS1.4. This does not qualify real games, QEMM/DESQview, Windows,
broader sound devices, a completed guest-frame fence or legacy guest-time
scheduling parity. Keep those gates distinct from the native observations below.

## Schedule one physical-input batch

Use the pinned QEMU 10.0.13 build with the current clock, media and input patches,
in that order; source/build instructions are in `native/qemu-input/`. Select
`qemu_clock='virtual'` (`clock_profile='virtual'` for `Project.machine`) and
require `capabilities['virtual_input_schedule']`. This optional native API 1
does not change the stock/default immediate-input path. `timed_input=False`,
`guest_time_control=False` and `completed_guest_frames=False` remain explicit.

Queue physical edges while stopped, then call `input_schedule(delta_ns)`.
Arming copies one owned batch and emits no input or guest execution.
`input_schedule_observe()` is passive too. The next explicit bounded `run()`
or `clock_advance()` owns one attempt; do not loop or resume to force delivery.

```python
lease = debug.keyboard.key_down('a')['lease']
armed = debug.input_schedule(5_000_000)
result = debug.clock_advance(20_000_000, timeout_ms=3000)
delivery = result['input_delivery']
print(result['outcome'], delivery['state'], delivery['dispatch_ns'])
```

The `fdisbull-qemu-scheduled-input-1` receipt binds token, run/session/epoch,
edge sequence/count, requested start/deadline and actual terminal/dispatch
times. `lateness_ns` is actual dispatch time minus its requested deadline.
`dispatched` means the selected PS/2 handler callbacks and final sync returned;
`device_queue_accepted` and `guest_consumed` stay `None`. Disabled/full devices
can ignore events. Validate consumption, release and later drawing with
independent guest evidence. A callback timestamp is not a frame boundary or an
exact CPU-cycle guarantee. Terminal native fields freeze across later reads.

The first actual stop cancels an unfired timer, preserving the original
break/watchpoint or DOS exit/TSR result. Pending stops and equal/already-expired
owned clock-budget deadlines win independently of timer insertion order. Choose
an earlier input deadline when combining it with `clock_advance()`. A cancelled
receipt has `dispatch_ns=None` and `requires_resolution=True`; its Python edges
remain pending. Before another run or queue edit, explicitly reschedule them
with `input_schedule(new_delta_ns)` from the current stop, or discard them with
`input_cancel_pending()`. Cancellation proves disarm before forgetting edges.

A dispatched hold still needs `keyboard.key_up(lease)` or
`mouse_button_up(lease)` and another explicit dispatch, optionally scheduled.
Cancelling its queued release retains the hold; cancellation never emits a
release. While a batch is bound, new edges and step/trace/unbounded resume are
refused. `input_state()['schedule']` reports the retained receipt and resolution
requirement alongside the existing queue and leases.

The retained JSON methods are `debug-input-schedule` with `run` and `delta_ns`,
`debug-input-schedule-observe` with `run`, and `debug-input-cancel-pending` for
resolution. Saved scripts use `input-schedule`, `input-schedule-observe` and
`input-cancel-pending`. Their full preflight and native I/O share the script's
host deadline, including post-stop reconciliation. A failed script that armed
a batch closes the VM even if its pending edges came from an earlier call.
Reopened receipt artifacts are historical evidence, not a live timer owner.

Bounds are 1..256 events, delay 1..60,000,000,000 ns, relative X/Y values
-32767..32767, and at most one edge for each left/middle/right mouse button in
a batch. Do not schedule both mouse down and up at one timestamp: one sync
would collapse them into the final button state. The existing 64-lease bound
remains. Native token history allows 4096 successful arms per process; a fresh
VM is required afterward. Reset, epoch/profile loss and unsupported runstates
invalidate the scheduler. Migration stays blocked after the first successful
arm. Uncertain
mutation, callback, deadline or evidence results close the VM without replay.

The new host/native witnesses are `tests/test_qemu_input_schedule.py` and
`tests/test_qemu_input_schedule_native.py`; test paths are not passing receipts.
All 127 default-switch qualifications remain open and DOSBox stays the default.
Legacy `guest_ms`, timed press/type, frame presses, pixel/INT33 semantics and
whole-game timing remain unqualified. The separate host clock-sync controller
preserves input's first-stop semantics and never re-arms a cancelled batch.

## Schedule input at a modeled retrace edge

For input tied to this model, apply the optional fifth patch in
`native/qemu-input-retrace/` after the unchanged clock/media/input/retrace
chain. Require `retrace_input_schedule`, queue physical edges while stopped,
then call `input_schedule_retrace(edge='enter'|'exit', timeout_ms=1000)`.
JSON uses `debug-input-schedule-retrace`; scripts use `input-schedule-retrace`.
Arming is passive and selects the strictly next absolute occurrence. The
caller must choose a bounded execution beyond the target: a coincident clock
deadline, including a `retrace_wait` to the same edge, cancels before delivery.

Immediately before the existing PS/2 batch callbacks, the native timer checks
the pinned VGA identity, timing generation and original target window. A
timing change, including hidden ABA writes, cancels as
`retrace-timing-changed`; arrival at or beyond the exclusive window end
cancels as `retrace-missed-window`. These cancellations do not add a VM stop,
and pending edges remain bound for explicit rescheduling or cancellation.
An undelivered release keeps its prior dispatched hold. No automatic re-arm
or synthetic release is allowed.

The normal scheduled-input receipt gains `retrace` with format
`fdisbull-retrace-input-1`, original observation, target/window and historical
native arm/check snapshots. Inspect `dispatch_phase_verified` as well as
`state`; success requires callback, dispatch and terminal timestamps to join
inside the original window. Later observations must not relabel that evidence.
Failed scripts close an armed owner even for batches queued before the script.
Older four-patch builds lack this capability and retain ordinary delta
scheduling. This boundary does not qualify arbitrary guest consumption, full
VBlank, completed frames or legacy frame-edge helpers.

## Observe the explicit VGA retrace model

Select `qemu_clock='virtual', qemu_retrace='precise'` (CLI `--qemu-clock virtual
--qemu-retrace precise`); the raw machine factory uses `clock_profile` and
`retrace_profile`. The default retrace profile is `standard`. The precise
profile requires the exact native clock/media/input/retrace patch chain, one
TCG CPU, a fresh paused PC and standard PCI VGA. Inspect `retrace_observation`
before planning `retrace_observe(timeout_ms=1000)`, retained JSON
`debug-retrace-observe`, or saved-script `retrace-observe`.

The receipt shares the run and host/native clock epochs with other observations
and adds model, exact device/console/head and `timing_generation`. It retains
raw timing inputs, cached integer timing and stable before/after clock samples.
The native query is passive: it neither reads the VGA status port nor resets the
attribute flip-flop, advances execution, refreshes pixels or waits for an edge.
Admission pins the device and blocks migration. Reset invalidates ownership.

Always check `phase_supported`. An uninitialized cache, enabled VBE, or timing
outside the declared initialized legacy, nonwrapped model subset returns
`False` with `unsupported_reason` and no phase. This is normal evidence, not a
reason to retry execution. Malformed or contradictory receipts close the owner.
When supported, `phase['vertical-retrace']` and the synthesized status bits
describe QEMU's selected integer model only. They do not qualify the full
vertical blank interval, visible scanout, hardware timing or completed frames.

The opt-in model fixes write-time cache updates for CR10 and VBE/effective
sequencer transitions. Generation changes at guest-write boundaries, so A-to-B
and B-to-A changes cannot hide behind equal final registers. Compare timing
only within the same device, run, both clock epochs and generation. This is not
a complete palette/address/pixel-format mode identity. A current phase cannot
be retrospectively attached to older retained renderer pixels.

One absolute timeout covers lock admission through evidence persistence;
scripts reject an unsupported profile or invalid literal timeout before earlier
writes. A journal can commit before a late timeout is detected, so inspect
`error.result` for retained observation evidence. Do not infer rollback or
replay. Use the separate explicit operations below for bounded edge waiting
or host auto-sync. All 127 default-switch gates remain open.

## Synchronize at an explicit cooperation point

Check `host_clock_sync` on the explicit virtual profile. Use
`clock_sync_start(tolerance_ns=1_000_000, max_lag_ns=250_000_000,
max_wait_ns=250_000_000, timeout_ms=1000)` to establish a passive fixed 1:1
mapping between native virtual time and host `time.monotonic_ns`. This policy
counts all host elapsed time since start, including Python work, control and
persistence overhead, debugging pauses and caller idle time. Stop the mapping
before an intentional long inspection pause.

At each explicit `clock_sync_step(timeout_ms=1000)`, retain the original
anchors and automatically choose one action: no correction within tolerance,
one native clock budget when behind, or one host-only wait while the guest is
stopped when ahead. Actual intervening guest progress and timer overshoot are
accounted for. The target is frozen for the call; there is no moving-target
loop, background execution or implicit correction in other methods.

Inspect the receipt's state, outcome, complete `execution`, actual wait and
residual drift. Reaching the frozen target does not promise zero drift at
return. Excess lag/wait latches `desynchronized` without execution/wait;
early or coincident native stops latch `interrupted` without continuing.
Scheduled input retains its first-stop cancellation and explicit resolution.
Use `clock_sync_observe()` for passive state/drift evidence and
`clock_sync_stop()` to stop future corrections between calls. A fresh mapping
requires explicit stop/start; saved history never restores live ownership.

With `retrace_wait` capability, call `retrace_wait(edge='enter'|'exit',
timeout_ms=1000)` to attempt the strictly next modeled vertical edge once.
Check `synchronized`, not only the final phase bit. The exact absolute target
window, clock/device identity and timing generation must all survive. A later
cycle in the same phase does not qualify. Unsupported timing or a whole-period
retrace returns unsupported/no-transition without execution. Timing changes,
missed windows and original debugger/DOS stops stay explicit; never retry them
automatically.

JSON routes are `debug-clock-sync-start/observe/step/stop` and
`debug-retrace-wait`; script operations omit `debug-`. Whole-script capability,
signature, literal-option and transaction checks precede earlier mutations.
Each operation shares one deadline from lock admission through persistence.
Inspect `error.result` after a late or failed evidence write. No claim is made
for continuous real-time fidelity, full VBlank, guest-frame completion, device
resampling, input consumption or hardware-cycle parity. VGA changes do not
rebase the host mapping. Start/observe/stop are passive; step and retrace-wait
are explicit execution controls. In-flight cancellation uses the existing
deadline/terminal-close path, not a concurrent stop command.

## Observe renderer publications and PC-speaker output

Use the current clock patch plus `native/qemu-media/` for these optional native
API1 operations. Select `qemu_clock='virtual'`; add `qemu_audio='pc-speaker'`
only for PC-speaker capture. The raw machine factory takes `clock_profile` and
`audio_profile` instead. This profile uses QEMU's timer-driven `none` audiodev,
32,000 Hz mono unsigned 8-bit PCM, and no host playback. Other sound devices
remain unqualified. Host clock auto-sync is separate from media capture and
does not change its sampling rate, renderer cadence or playback qualification.

Start windows at a caller-selected stopped point with
`display_start(period_ns=20_000_000)` and `audio_start(max_frames=320_000)`.
Advance once with the existing `clock_advance()` or another bounded execution
control. Preserve an earlier breakpoint, watchpoint or process completion;
do not automatically continue to manufacture media output.

Inspect `display_observe()` before `capture_display(name, after_update=...)`.
It reports the latest completed synchronous renderer update, its window token,
ID, publication virtual time and age. No update exists until a real observer
callback runs. `after_update` is local to the current window and refuses stale
publications without waiting. Export reads a private RGB copy; it never calls
the renderer. A later ordinary screenshot can show different current VRAM
without changing those retained pixels. A published image can still contain
partial guest drawing: keep `completed_guest_frame` and `guest_frame_id`
unknown. The observation period is not a VGA refresh rate or VBlank interval.

Inspect `audio_observe()` and save exact retained output with
`capture_audio(name)`. Callback sample ranges are contiguous within the WAV,
but their delivery timestamps are not precise sample onset times. Inactive
intervals are not filled with silence. Sample duration does not measure elapsed
guest time or certify queue drain. Overflow reports dropped frames and refuses
export; stop and explicitly start a new bounded window.

Use `display_stop()` and `audio_stop()` to disarm/detach while retaining data.
Both are idempotent for the current token and never run, refresh or flush.
New windows start empty. Reset/epoch changes invalidate the live windows;
these observers cannot be restored from saved run metadata. Native migration
is blocked after use. All eight operations have `debug-` JSON routes and
same-name hyphenated script operations, such as `display-start` and
`capture-audio`. Script admission and one shared host deadline apply before
earlier input/media mutations. Keep explicit output observations separate from
later automatic synchronization, checkpoint and frame-history work.
