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
Optional native extensions support RAM/fetch layers, hooks and private DOS
process checkpoints with same-project cold restore. Instrumented checkpoints
preserve virtual time, retained audio/display windows and precise retrace under
fresh owner tokens; inspect `docs/DOS_QEMU_MIGRATION.md` in a source checkout
for the checkpoint contract. Protected/V86 ownership can include observed
remapped RAM under the native task-context extension, with the selected PC in
the verified module. A stopped cooperating monitor may bind its explicit
`FDBTASK1` RAM anchor using `debug-dos-task-bind` and observe it using
`debug-dos-task-observe`; the lifetime combines monitor UUID, cookie,
incarnation and the DOS process nonce. Architectural CR3/TR observations alone
do not identify a software task. An authored two-task V86 witness covers a
cold restore and A → B → A with active layers and task-scoped hooks. Ordinary
physical layer effects are shared by aliases. A separate experimental
`debug-dos-task-switching`, `debug-dos-task-register`,
`debug-dos-task-layer-patch`, `debug-dos-task-layers`, `debug-dos-task-memory`
and `debug-dos-task-retire` interface targets isolated CPU RAM/fetch views for
cooperating tasks even when they share a physical page. The guest monitor
publishes an even anchor and commits it with OUTW `0xf1db`, `0x4446`; it still
owns task scheduling. GDB/QMP debugger and device access use base RAM. The
local native build and authored same-page A → B → A → B → A checkpoint witness
passed, including separate-process restore, shared hooks, virtual clock and
precise retrace. See the source migration guide for page limits, tombstones and admission
boundaries. This is not vendor QEMM/DESQview compatibility or general DPMI
qualification. A separate experimental native cooperative scheduler adds
`debug-dos-task-scheduler`, `debug-dos-task-fork`, `debug-dos-task-context`,
`debug-dos-task-runnable`, `debug-dos-task-scheduler-observe` and
`debug-dos-task-scheduler-disable`. It targets registered task-private views and
forks within one verified DOS source/allocation: guest INT 60h yields and INT
62h blocks while the native engine selects runnable tasks and retains CPU and
interrupt-frame state. An authored local V86 witness passed cooperative
task switching and separate-process cold restore with distinct CPU/x87 states,
private views and a dormant protected-mode interrupt frame; per-task x87
rounding of 1.5 to 1 and 2 and guest watchpoints with matching DR7 controls but
different DR0 addresses also survived switching and cold restore. It exercised
single-step yield, idle and guest DOS exit. Its instrumented audio window had
zero frames and zero dropped frames, establishing observer state and token
rotation only, with no PCM or audible playback evidence. These are bounded
results: general interrupt preemption and vendor compatibility do not follow
from this cooperative interface. A separate opt-in
`debug-dos-task-preemption` extension has bounded local authored PIT/PIC IRQ0
and i8042 IRQ1 evidence, including guest EOI, task-owned frames, quantum-three
cold restore and IF/PIC-mask deferral. Chained STI/MOV SS delivery may occur
after MOV SS or its next instruction; isolated MOV SS with an already-pending
IRQ remains unqualified. A combined virtual-clock/precise-retrace/audio IRQ
checkpoint profile passed locally with observer state and token rotation at
pre- and post-EOI cold restore. Both windows had zero frames and zero drops,
so there is no PCM or audible-playback evidence. No vendor multitasker or
general IRQ-timing parity follows. API 3 adds slave PIC IRQs 8–15 as well as
direct master IRQs other than cascade IRQ2, tracking nested frame ownership and
slave-before-master EOI obligations. Locally passed authored RTC IRQ8/nested
keyboard IRQ1 witnesses cover cold restore before EOI and after slave EOI,
including an IRQ1-target pending handoff that switches only after the outer
master EOI. Additional real empty IRQ1 entries are serviced and accounted for;
the witness stops after A resumes and does not claim DOS cleanup. API 1
cooperative and API 2 direct master-PIC runtimes remain recognized; unsupported
PIC modes still fail closed. Frame-timed input and
scene parity remain later slices.
Explicit stopped rule ticks are available. `memory_rule_run(rule, *, ticks,
interval_ms=100, timeout_ms=10000)` also admits the explicit QEMU virtual clock:
first tick immediately, subsequent token-bound native intervals under one host
deadline. Each tick rechecks identity and mapping, reads fresh values, performs
a guarded write and journals its result. A hook is dispatched once and stops
the interval; any nonordinary stop ends without another tick or replay.

Native snapshots offer `base`, `ram` and inspection-only `execute` views. A
base-view caller label is not native task identity. Active layers or native
task bindings require an explicit RAM view; task-private capture binds the
selected registered task's lifetime, backing, epoch and view generation.
Rule-owned immutable RAM overlays preserve authored RAM/fetch layers. Queued,
held or scheduled input, active clock synchronization or budget, and
caller-owned transactions remain refused. A changed task/view refuses before
another edit. Old rules remain stale after restore; use a fresh capture and
new rule. Ten authored native cases passed locally, including an actual
IRQ-driven A/B private-view and cold-restore witness; 823 host checks passed.
The fresh bounded broader regression passed 1,159 tests across 72 files with
no failures, errors or skips, including the 19 native scheduler and IRQ
preservation cases. The retained actual DOSBox witness passed once. These
results do not qualify generic
`guest_ms`, cycle or real-time scheduling, or promote the formal gates.

## Checkpoint histories

The first native DOS Histories slice is in progress: `rewind_start`,
`rewind_record`, `rewind` and `rewind_status` use bounded, immutable full
process checkpoints in a persistent branch DAG. The default record steps once;
`advance='capture'` records a manually reached stopped boundary, with the
intervening execution unobserved. A stored manifest and node can select a
cross-session restore. For a stopped admitted `debug` session:

```python
root = debug.rewind_start()
first = debug.rewind_record()                 # one stopped step
old_node = first["node"]
debug.rewind(count=1)
branch = debug.rewind_record()                # old child remains retained
status = debug.rewind_status()                # history artifact and node IDs
manual = debug.rewind_record(count=1, advance="capture")  # stopped boundary
history = manual["history_artifact"]
# In a new stopped session for the same project, source and runtime:
restored = debug2.rewind(history=history, node=old_node)
```

`max_steps` counts all nodes including the root and retained branches (default
16, maximum 128). `max_bytes` counts cumulative checkpoint payloads (default
512 MiB, maximum 1 GiB), with 128 MiB per state. The project-wide 256 MiB
aggregate runtime-artifact cap can bind first. Live QCOW2 growth is measured
separately, not capped by this budget. A manual capture does not observe the
intervening execution.

The admitted checkpoint covers private QCOW2 and native controls, with
`host_files_restored=false`; planned host-directory/file-layer restoration is
separate. General frame/input parity remains open. Native comparative trials and a
bounded selected CPU/RAM partial undo is described below. Local native witnesses cover ordinary
Python/JSON/script step and rewind, retained IRQ branches and separate-process
restore with task-private RAM/fetch layers and hooks; the dated handoff and
!117 record the exact validation receipt. The four
routes are partial and unqualified; DOSBox remains the default.

## Selected native CPU/RAM undo

On a stopped, source-bound QEMU DOS session, use `cpu_delta_start(ranges,
registers=None, max_steps=16, max_bytes=67108864, timeout_ms=60000)` to capture
a full recovery anchor and start a per-live-session projection. Then use
`cpu_delta_record(count=1)`, `cpu_delta_rewind(count=1)`, `cpu_delta_status()`
and `cpu_delta_recover()`. JSON routes are `debug-delta-start`,
`debug-delta-record`, `debug-delta-rewind`, `debug-delta-status` and
`debug-delta-recover`; script operations omit `debug-`. An interrupted,
context-changed or short script record fails before subsequent steps.

```python
debug.cpu_delta_start([{"address": "0x10000", "length": 2}],
                      registers=["rax", "rip"])
debug.cpu_delta_record(count=1)
undo = debug.cpu_delta_rewind(count=1)  # execution is now frozen
debug.cpu_delta_recover()              # full anchor before continuing
```

Ranges are 1–64 nonempty source-address ranges with optional `cs`, at most
65,536 bytes total and uniquely backed by owned RAM. Select from the 16 exposed
GPRs, `rip` and `eflags`; the default selects all. Only arithmetic flag bits
(`0x8d5`) may change; `rsp` cannot change with owned interrupt frames. Control,
segment and FPU registers are outside the projection. The maximum is 128 recorded steps and
256 MiB including anchor and provenance, with 128 MiB per anchor.

Recording requires stable source, mode, task, view, backing and interrupt-frame
ownership; pending hooks and steps starting at active hooks are refused.
Admitted existing layers, hooks and owned input retain their ownership. The
inverse freezes before a guarded RAM-view overlay and register write; uncertain
failure closes the session. The RAM overlay and register batch are sequential,
not one atomic CPU-plus-RAM transaction. `allow_partial_resume=True` is refused.
Restore the full anchor or a trusted full checkpoint or reconstructed
lossless-delta frame point to continue. Histories remain
stored, but the partial edit invalidates their live edge. Unselected RAM and
registers remain current; devices and host files are not rolled back, and a
native step stop does not prove instruction retirement. This is not full-machine
rewind or a resumable partial machine state. Immutable projection artifacts
remain retained, but the live cursor does not reattach after restart. DOSBox
remains the default.

## Native comparative trials

Use `save_experiment(name, script=..., observations=[...])`,
`restore_experiment(experiment)` and
`compare_experiment(experiment, layers=[...], timeout_ms=60000)` on a stopped,
source-bound QEMU DOS process with full checkpoints. `controls()` inspects
owned controls. Existing JSON routes are `debug-controls`,
`debug-save-experiment`, `debug-restore-experiment` and
`debug-compare-experiment`; offline `debug-experiment-info` and
`debug-experiments` retain inspection after closing the session.

Each arm restores the same full checkpoint and runs the same bounded script.
The explicit ordered `layers` replaces the global stack, or only the saved
selected task's stack when task-private views are enabled. Other tasks retain
their saved stacks. Native-bound candidates must match the captured origin
and task; fresh restore bindings leave original definitions immutable.
Source RAM observations use the selected native RAM view, including private
pages. Script memory reads retain their declared machine address space.

Trial scripts allow step/run/registers/memory/trace/screenshot/capture-surface, assertions and
deletion of restored controls. They exclude input, layer/history mutations,
selected undo and nested restoration. Limits are 128 expanded steps, 64 KiB
combined endpoint/script RAM observations, 1,024 trace boundaries and four
ungridded screenshots. Admission and artifact budgets can bind earlier.

Compare only validated captures, preserving source/task/mode/byte identity.
Fresh epochs and rearmed control IDs remain provenance. Incomplete, corrupt,
interrupted or misaligned observations cannot prove equality; a failed
baseline skips the candidate. Final full baseline recovery shares the same
overall deadline; uncertain effects or failed recovery close without retry.
Full/lossless history DAGs and selected-undo artifacts remain retained, with
their live cursors invalidated. A frozen selected inverse first needs explicit
full recovery, which can be `restore_experiment`. Held keys, layers, hooks and
IRQs use the full checkpoint path without input reinjection. No deterministic
replay, full equivalence, completed guest frame or host-file rollback is
claimed. See `docs/DOS_QEMU_MIGRATION.md` and !117 for scope and evidence;
DOSBox remains default and retained pending local parity.

## Native renderer frame histories

The next optional native frame-history increment uses a token-bound fence on
the next completed synchronous QEMU renderer publication and a safe CPU stop.
`timeline_start/advance/rewind/status/image/pin/stop` retain full checkpoint/PNG
points and earlier branches; a named timeline/point can restore across sessions.
The root is a paused surface point, not a completed frame. The publication is
not proof of guest drawing completion, VBlank, physical scanout or input
consumption. `completed_guest_frames` stays false.

Complete checkpoints are captured at every point. Retention supports default
`full` or opt-in `delta` with `keyframe_interval=1..128`. Deltas bind exact
checkpoint bytes to their immediate retained DAG parent and use bounded chains;
full keyframes or an unprofitable/oversized-delta fallback reset depth. PNGs stay
full and lossless. No redundant full checkpoint is published for a delta point;
restore reconstructs transiently, and pin explicitly exports a byte-identical
standalone full state. New delta manifests use a version fence; older full
histories remain readable. Validate chains and images before restore or forward
execution. Status reports encoded payload, canonical metadata, raw reconstructed
bytes, PNGs and input journal separately; live QCOW2 growth remains separate.
Codec work is bounded with deadline checks before/after, rather than interrupted
inside zlib. N21 additionally admits atomic stopped
`frame_inputs` and scheduled edges with token/epoch/generation ownership,
separate from ordinary physical leases. Native capacity is two edges only when
the PS/2 FIFO/controller output is quiescent, zero otherwise. Validate the whole
schedule before dispatch; an incomplete prefix stops scripts without a retry.
Accepted input makes the current timeline point dirty until a new renderer
child is captured or restored; pinning dirty points refuses, and
`timeline_rewind(frames=0)` restores the cached current point.

Instrumentation format 2 preserves held QCodes, PS/2 modifiers/queue, controller
state and the exact throttle deadline. Cold restore validates the loaded device
proof and adopts a fresh token/epoch without injecting makes again. Foreign
input invalidates an active owner. Ordinary leases/pending input/schedules
still require resolution before checkpointing; release all owned keys before
switching back to ordinary physical input. N20 remains released-input only.
Typematic repeat is unsupported; held ownership does not prove repeated output
or guest consumption. Partial-memory policies remain open.
Hooks and task-private RAM/fetch layers use the existing full checkpoint
contract, including native task/IRQ state. Earlier nonordinary stops do not
create a completed frame or trigger another continue. Limits include the root
and retained branches (default 16 points, maximum 128), cumulative state/PNG
payloads (default 512 MiB, maximum 1 GiB), per-state/per-image bounds and the
earlier-binding 256 MiB project runtime-artifact cap. Live QCOW2 growth remains
separate. Nine direct native witnesses cover renderer history, cold restore,
early stops, controller guards and task-private IRQ/layer/hook preservation;
DOSBox-X remains retained and default.
See `docs/DOS_QEMU_MIGRATION.md` for the API example and exact receipt.

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
Pixel clicks and frame-edge timing remain unsupported. The separate
`virtual_keyboard_press`, `virtual_keyboard_type` and `virtual_mouse_click`
capabilities below supply one timed native chord, bounded US-layout text or a
physical mouse-button pair.
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

## Timed keyboard and physical mouse helpers

With the explicit virtual clock and the corresponding optional native patches,
check `virtual_keyboard_press`, `virtual_keyboard_type` or `virtual_mouse_click`
before using `keyboard.press`, `keyboard.type` or `mouse_button_click`. Their
JSON routes are `debug-keyboard-press`, `debug-keyboard-type` and
`debug-mouse-button-click`; script operations are `keyboard.press`,
`keyboard.type` and `mouse.button-click`. Arming requires a stopped owner,
empty queue and no held leases; select the later bounded run, clock advance or
clock-sync step explicitly. Press/type timings and click hold are strict integer
1..1000 ms. Text accepts 1..64 printable US-layout ASCII characters, CR, LF
or Tab; verify guest layout and lock state independently. Click accepts only
left/middle/right and sends down and up in separate batches.

Inspect the retained press, typing or click steps, delivered prefix, leases and
individual deadline/lateness evidence. A first stop cancels the unsent suffix;
call `input_cancel_pending()` and explicitly release any dispatched holds with
a separately chosen execution. Cancellation does not release or replay edges.
Accepted uncertain effects close the VM without replay. Callback receipts do
not prove FIFO acceptance, guest consumption, cursor position, INT33 or a
completed frame. Coordinate and legacy frame click helpers remain unqualified.
For exact scheduling, timeout, cancellation and native patch requirements, see
the full repository guide `docs/DOS_QEMU_MIGRATION.md`.

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

## Probe selected retained renderer pixels

Inspect `renderer_probe` before calling
`display_probe(points, *, window=None, update_id=None, timeout_ms=1000)`, JSON
`debug-display-probe` or script `display-probe`. Require the ninth native
`x-fdisbull-probe-display` extension and the explicit virtual clock. An older
eight-layer executable retains ordinary renderer capture and timed mouse input
but refuses the new helper.

Supply a list of zero through 256 two-coordinate points. Use strict integer
coordinates in `0..8191`, within the retained publication's width and height;
booleans are invalid. Preserve order and duplicates. Even an empty list requires
an existing publication. To check identity, supply both the exact `window` and
positive uint64 `update_id` returned by `display_observe()`. IDs restart per
window, so an ID alone is refused. Leave both unset only when selecting the
latest retained publication under the machine lock is intended.

```python
publication = debug.display_observe()
if publication['updates']:
    result = debug.display_probe([[0, 0]], window=publication['window'],
                                 update_id=publication['update_id'])
    rgb = result['pixels'][0]['rgb']
```

Read `fdisbull-renderer-probe-1` as sparse evidence from one owned RGB copy.
It retains requested points, ordered `{x, y, rgb}` pixels, publication dimensions,
time and age, unchanged stopped clock brackets, and the full native response.
It writes no image artifact and does not render, run, wait, send input or call
clock auto-sync. Explicit later execution may publish a new image; an earlier
stop may leave the same one. A current surface can show changed VRAM, palette or
mode while the retained probe still reports older pixels and dimensions.

Use list points for script references, including individual coordinates or a
whole point/list. Validate every visible literal before earlier effects and
fully validate resolved values before sampling. The default 1000 ms host bound
includes lock admission, I/O, clock brackets and journal persistence, intersected
with tighter script/caller bounds. Refuse caller-owned transactions. A missing
publication, stale expectation or outside point leaves the valid stopped owner
usable. Malformed native evidence, failed persistence or a late result closes
without replay; inspect any retained `error.result` before reporting failure.

Keep successful `machine-display-probe` journal entries as historical evidence
after reopening, without claiming restored live ownership. The host compares
overlapping coordinates only with the immediately preceding probe, bounded to
256 points. Use `capture_display()` for a full-image hash; a sparse result does
not contain one. Keep `frame_probe`, `video.probe`, coordinate clicks and scene
readiness unavailable until their mode/frame/state and mouse mappings are
qualified. Do not infer cursor position, INT33 semantics, VBlank, input
consumption or guest drawing completion. All 127 promotion qualifications remain
open, and DOSBox remains the default.

## Observe VGA configuration identity

Inspect `vga_configuration` before calling
`vga_configuration_observe(*, timeout_ms=1000)`, JSON
`debug-vga-configuration` or script `vga-configuration`. Require the tenth
`x-fdisbull-query-vga-configuration` extension, all native clock/display/retrace
commands, and the existing explicit virtual/precise profiles. A nine-layer
executable retains its earlier operations and refuses this helper.

```python
result = debug.vga_configuration_observe()
current = result['current']
published = result['published']
if published is not None:
    configuration_unchanged = result['configuration_matches']
```

The `fdisbull-vga-configuration-1` receipt separates current configuration from
the configuration observed alongside the retained renderer publication. Both
snapshots retain native epoch, model, device/console/head, observation time,
positive lifetime generation, bounded raw values and their canonical SHA-256.
Use the identity fields and generation together. A raw hash identifies values
only: A-to-B-to-A writes can restore those values while advancing generation
twice. Same-size page, pitch, panning and pixel-interpretation changes matter.
Even paused QOM writes can change generation at the same virtual time.

The conservative vector includes legacy/VBE sequencers, graphics and CRTC
registers, attribute mode/panning/color controls, display enable, miscellaneous
and feature output, VBE words and derived origin/pitch/bank/size, DAC width and
framebuffer byte order. It excludes palette contents, VRAM/fonts, ordinary
selectors and flip-flops, renderer caches and dimensions. Equal configuration
does not imply equal images or application state. The model is
`qemu-vga-configuration-fdisbull-v1`; it does not infer a BIOS mode number.

The native observer captures the stamp directly with the retained RGB copy,
even before the first public configuration query. Stopping preserves it; a new
empty window returns `published=None` and `configuration_matches=None` without
resetting the device's generation. The host keeps one current snapshot and the
last actual publication stamp to reject contradictory or regressing history,
including across empty windows. Old publications never replace current history
or receive a stamp copied from current registers.

Interpret `publication_configuration_semantics` as
`configuration_observed_at_publication`. A transient invalid text layout or
blanking can preserve older surface pixels. A true `configuration_matches`
therefore does not establish raster coherence, completed drawing, cursor
mapping or input readiness. `raster_coherence`, `completed_guest_frame`,
`guest_frame_id` and `cursor_mapping` stay unknown. Retained dimensions keep
their original image meaning. Do not unlock frame probes, coordinate clicks or
scene consumers from this observation alone.

This is a passive stopped read with unchanged clock brackets. It performs no
guest execution, render, guest I/O/memory read, input, sleep/wait, image export
or implicit auto-sync. Validate direct signatures and strict integer timeout
before admission; default 1000 ms, range 1..600000. Scripts preflight visible
values, capability and transaction ownership before earlier effects and check
resolved values before clamping. One shrinking host deadline covers locking,
native queries, validation, journal persistence and final return.

Refuse caller-owned transactions. Malformed, contradictory, control,
persistence or late-result failures close without replay; inspect available
native evidence and completed clock brackets in `error.result`. Successful
`machine-vga-configuration-observe` journal entries survive reopening as
history, without restoring a live machine. Reset/overflow/restore identity
rules do not provide checkpoint compatibility. DOSBox stays the default and
all 127 promotion qualifications remain open.

## Declare pixel displacement for relative mouse motion

Inspect `mapped_mouse_motion` before using the eleventh display-motion
extension. Call `mouse_move_mapped(dx_pixels, dy_pixels, *, counts_per_pixel,
window, update_id, configuration_generation, timeout_ms=1000)`, JSON
`debug-mouse-move-mapped` or saved-script `mouse.move-mapped`. Require explicit
virtual/precise profiles and all clock, input, display, retrace, configuration
and display-motion commands. Ten-layer executables keep their existing routes
and refuse this helper.

The request is a relative displacement with a **caller-declared scale**, no
observed pointer origin or absolute destination. Image axes are +x right and
+y down. `counts_per_pixel` must be exactly `{'x': [numerator, denominator],
'y': [numerator, denominator]}`. These are QEMU REL event units per retained-image
pixel, not raw PS/2 y counts: QEMU negates relative y in the packet accumulator.
Use strict integer pixel components in −8191..8191, a nonzero pair, nonzero
signed numerators in −32767..32767, and positive denominators in 1..32767.
Division must be exact and each result must fit −127..127. There is no rounding,
clamp, splitting or automatic replay. Each displacement magnitude must also be
less than the corresponding retained image extent; that is not an endpoint
inside-image claim. The count bound does not imply packet acceptance or a
single packet when native device state is unknown.

Explicitly stop a nonempty renderer observer, then call
`vga_configuration_observe()` and supply its window, update ID and current
configuration generation. Current and published configurations must match.
Require an owned project outside caller transactions, an empty physical queue,
no owned held leases and no bound schedule. This operation never stops the
observer or refreshes the image for you.

Native admission checks the exact display/configuration identity and arms one
passive attempt due after 2 ms. Nonzero x and then nonzero y share one final
sync. Choose execution explicitly with `run`, `clock_advance` or an existing
`clock_sync_step`; the helper does not start auto-sync. Immediately before any
motion callback, native code rechecks epoch/device, still-stopped publication,
dimensions, publication stamp and current generation. A-to-B-to-A changes cancel
by generation even when raw values return. Changed configuration cancels first
with `display-motion-configuration-changed`; otherwise changed publication or
window cancels with `display-motion-publication-changed`. Pending stops and
equal/reached budgets win before sampling. Contradictory or regressing native
identity fails ownership.

Inspect the existing `fdisbull-qemu-scheduled-input-1` receipt's `motion`
descriptor (`fdisbull-mapped-mouse-motion-1`). It preserves the declaration,
derived `dx`/`dy`, original VGA `before`, frozen `native_arm` and optional
`native_check`. `binding_verified` is true only after dispatch. A valid cancelled
attempt retains its pending records: explicitly `input_cancel_pending()` before
a new request. Neither generic nor retrace scheduling can convert those records
into unguarded input. Terminal observation never refreshes its callback evidence.

Binding proves neither current raster freshness nor scale validity. Palette,
VRAM/fonts and application state can change without a configuration-generation
change; a stopped publication may be old. Keep `guest_pixel_displacement`,
`guest_pointer_position`, `mapping_verified`, `raster_coherence`, `target_reached`,
`device_queue_accepted` and `guest_consumed` unknown. No button event is requested,
but pre-existing external buttons remain unobserved. Never infer INT33 position,
target reached, pointer readiness or completed drawing from callback completion.

Validate every visible script literal before earlier effects, including one
known axis when another uses a result reference; validate resolved values before
budget clamping. One shrinking strict integer 1..600000 ms timeout, default 1000,
covers locking, observation, arm, journal persistence and return. A known
pre-arm binding mismatch can leave the stopped owner usable. Uncertain/late arms,
malformed native evidence and persistence failures preserve available receipts,
close and forbid replay. Reopened journals restore history, not live authority.

Large script reports can return the existing `fdisbull-output-ref-1` delivery
marker. Read/export its saved output artifact; never rerun input to obtain a
larger inline reply.

Qualify controlled packet receipt, application pointer commit and drawing as
separate observations; a deliberately wrong scale can yield correct relative
callbacks with a different application displacement. Do not promote those
fixture facts to arbitrary DOS drivers/games. Legacy coordinate click/frame
operations and scene consumers remain unqualified. General `timed_input`,
`absolute_mouse`, `guest_time_control` and `completed_guest_frames` remain false.
DOSBox stays the default; all 127 promotion qualifications remain open.
