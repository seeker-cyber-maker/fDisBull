# Native QEMU DOS migration

`qemu-dos` supplies an explicit, native QEMU PC backend. It boots a caller-owned
disk and can launch an original COM/MZ project through real DOS. `dosbox` remains the default
for DOS programs while replacement capabilities and compatibility are being qualified.

The first slice supplies owned startup/shutdown, private disk isolation,
capability discovery, stopped CPU/RAM inspection and edits, break/watchpoints,
bounded execution, instruction traces and stored-display screenshots. Existing
memory snapshots, searches, guarded edits and explicit rule ticks use the
native machine context. The [capability inventory](DOSBOX_QEMU_CAPABILITY_INVENTORY.md)
tracks every existing DOSBox protocol method and public debugger route, plus
capabilities that a method count misses.

The second slice adds verified DOS process entry, PSP/source identity,
termination versus TSR residency and driver-chain observations. The maintained
[migration plan and handoff log](DOS_QEMU_HANDOFF.md) records decisions,
expected difficulties, findings and dated validation.

The third slice connects that verified process to stopped-boundary traces,
register/PC/region predicates and persistent execution-event searches. Its
source identity survives ordinary MZ relocation and later process closure.
Overlays, mode changes and input-to-source-trace causality remain explicit
boundaries.

The fourth slice now supplies owned physical keyboard/PS/2 input, explicit
instruction and native virtual-clock profiles, and stopped display captures
with CPU/clock brackets. The optional virtual profile adds native timer budgets,
retained completed renderer updates, bounded PC-speaker PCM capture and optional
virtual-time dispatch of one owned physical-input batch. An explicit precise
VGA profile also provides stopped retrace-model observations and timing generations.
An opt-in host controller now synchronizes the native clock at explicit cooperation
points, while a separate bounded wait verifies the next modeled retrace transition.
Completed guest frames, broader sound devices and legacy timing parity remain
open gates. See [native timing synchronization](DOS_QEMU_TIMING.md) for the
mapping, stop policy and exact limits.

The standard profile supports restricted raw-machine checkpoints and
process checkpoints for original COM/MZ programs. The optional native layers
extension supplies guarded RAM and instruction-fetch views. The default-switch
gate still requires qualification of the outstanding surfaces and compatibility
campaigns.

## Select the execution environment

| Backend | What executes | Input and scope |
| --- | --- | --- |
| `dosbox` | The existing patched DOSBox-X | Existing DOS program project; retained default and fallback |
| `dosbox-qemu` | DOSBox-X inside a prepared Linux/QEMU guest | Existing DOS project plus Linux kernel/initramfs; retained fallback |
| `qemu-dos` | DOS or an authored boot program directly on QEMU's virtual PC | Original raw disk, or original COM/MZ plus a separate DOS boot disk; single TCG vCPU and explicit physical/virtual controls |
| `qemu-machine` | Generic existing QEMU machine context | Original raw disk; existing QEMM/DESQview profiles remain supported |

Selecting QEMU never silently launches DOSBox. After a failed or uncertain
operation, the caller inspects the result and explicitly starts a separate
fallback session. A DOSBox state cannot be loaded as a QEMU checkpoint.

## Planned bundled FreeDOS and directory layers

The [bundled environment and filesystem plan](DOS_QEMU_HANDOFF.md#planned-bundled-freedos-and-layered-directory-workspace-2026-11-11)
adds a ready-to-boot, versioned FreeDOS runtime and automatic guest read/write
access to the host launch directory, with an explicit directory override.
The proposed system drive is `C:` and the directory workspace is `D:`.
Capture the caller-selected root before runtime-directory changes and select
the mapped DOS drive/path before target execution, including relative reads
and saves; server requests report their explicit or owner-workspace root.
This is planned work; current launches still use an explicitly supplied boot
disk and the existing staging contract.

Both proposed modes preserve original host files through copy-on-write file
layers. Live mode observes guarded current host content and applies writes to
the session's effective view. Checkpointed mode pins base content and binds each
Anchor Stone to the matching file-layer generation and file-service state.
The proposed debugger default is checkpointed mode. Changes are inspectable,
revertible and exportable without overwriting the original directory.

New guest-created saves have an explicit keep/export option and an opt-in
policy for selected new-file paths. After a coherent flush/close, this can
physically create a private host file that survives rewind and session exit.
Pre-existing executables and surrounding files retain their layer protection.
Rewind preserves the physical copy while restoring historical guest membership;
explicit import/refresh makes that save visible in a new child layer revision.
Exports use guarded creation and do not silently overwrite existing paths.

File-aware restore must synchronize VM state, directory membership, file
contents and open handles, with a verified consistent base capture despite
external host writers. Existing checkpoint artifacts retain their documented
scope below; this plan does not retroactively give them host-file rollback or
new directory-sharing support. The linked plan records runtime packaging,
memory buffering/durable storage, branching and required native acceptance.

## Native DOS checkpoint histories

The first Histories slice is in progress. On a source-bound QEMU DOS process,
`rewind_start`, `rewind_record`, `rewind` and `rewind_status` provide a bounded
persistent DAG of immutable full-process checkpoints. A recorded child after
rewind preserves earlier branches; an explicit manifest and node can select a
checkpoint in a new session. The default record advances one stopped step;
`advance='capture'` records a manually advanced stopped boundary, including an
admitted active hook or IRQ boundary, without claiming observation of the
interval between nodes. Restore is governed by the native process checkpoint's
identity, input and compatibility preflight.

For an already stopped `debug` session with the admitted QEMU DOS checkpoint
profile, a branch and later cross-session restore can be selected explicitly:

```python
root = debug.rewind_start()                 # captures the root checkpoint
first = debug.rewind_record()               # one stopped step and checkpoint
old_node = first["node"]
debug.rewind(count=1)                       # restore the root
branch = debug.rewind_record()              # new child; old_node is retained
status = debug.rewind_status()              # history artifact and node IDs

# At a separately reached, admitted stopped boundary:
manual = debug.rewind_record(count=1, advance="capture")
history = manual["history_artifact"]

# In a new stopped session `debug2` for the same project, source and runtime:
restored = debug2.rewind(history=history, node=old_node)
```

The default `max_steps=16` counts all captured nodes including the root and
retained branches, with a maximum of 128. `max_bytes` bounds cumulative
checkpoint payloads (default 512 MiB, maximum 1 GiB); each state has a 128 MiB
limit. The existing project-wide aggregate runtime-artifact limit of 256 MiB
can bind earlier. Live QCOW2 growth is measured separately and is not a quota.
The manual capture's intervening execution is unobserved; it is not an
instruction trace or replay guarantee.

This scope includes the private QCOW2 process checkpoint and its admitted
native controls. It reports `host_files_restored=false` and does not implement
the planned host-directory or file-layer rollback described above. It is not
inverse CPU/RAM undo, deterministic replay or a completed-frame history.
The separate bounded selected CPU/RAM undo and renderer frame histories are
described below; comparative trials remain open. Local native witnesses cover ordinary Python/JSON/script step and rewind,
retained IRQ branches and separate-process restore with task-private RAM/fetch
layers and hooks. See the dated handoff and !117 for the exact validation
receipt. All 127 formal surface qualifications and seven campaigns remain open,
with DOSBox retained as the default.

## Selected native CPU/RAM undo

For a stopped, source-bound QEMU DOS process, `cpu_delta_start` captures a full
recovery anchor and starts a per-live-session projection. `cpu_delta_record`
records observed single-step stops; `cpu_delta_rewind` applies the selected
inverse and `cpu_delta_status` reports its bounds and frozen state. For example:

```python
debug.cpu_delta_start(ranges=[{"address": "0x10000", "length": 2}],
                      registers=["rax", "rip"])
record = debug.cpu_delta_record(count=1)
undo = debug.cpu_delta_rewind(count=1)
assert undo["execution_allowed"] is False
debug.cpu_delta_recover()  # restore the full anchor before continuing
```

The corresponding JSON methods are `debug-delta-start`, `debug-delta-record`,
`debug-delta-rewind`, `debug-delta-status` and `debug-delta-recover`; script
operations omit `debug-`. An interrupted, context-changed or short script
record fails that route before subsequent steps. Ranges use source addresses
and optional `cs`: 1–64 nonempty ranges, at most 65,536 bytes total, uniquely
backed by owned RAM. Registers may select the 16 exposed GPRs, `rip` and
`eflags`; the default selects all exposed members. An inverse may change only
arithmetic flag bits (`0x8d5`) and cannot change `rsp` while native interrupt
frames are owned. Control, segment and FPU registers are outside the
projection. Defaults are 16 recorded
steps and 64 MiB; maxima are 128 steps and 256 MiB, including the anchor and
recorded provenance, with a 128 MiB per-anchor limit.

Each interval requires stable source, mode, task, RAM view and backing, and
interrupt-frame ownership. Existing layers, hooks and owned input may be
admitted, but recording refuses a pending hook or a step beginning at an
active hook. The inverse freezes execution before a guarded RAM-view overlay
and register write; a failure of uncertain effect closes the session.
`allow_partial_resume=True` is refused. This is one guarded RAM overlay followed
by one guarded register batch, not an atomic CPU-plus-RAM transaction. Recover
with the full anchor or restore a trusted full checkpoint or reconstructed
lossless-delta frame point before continuing. Existing histories remain stored,
but their live edge is invalidated by the partial edit.

This is a selected-state projection: unselected RAM and registers remain
current, devices and host files are not rolled back, and an observed step stop
does not prove native instruction retirement. It is not a resumable partial
machine state or a full-machine rewind. Projection artifacts remain immutable,
but their live cursor does not reattach after a restart. These bounded operations do not qualify
the full parity surfaces; DOSBox remains the default.

## Native renderer frame histories

The next Histories increment adds an optional native renderer-publication
fence. It arms the next successful synchronous QEMU renderer update, retains
all copied pixels, and requests a stop at the next safe CPU boundary. Its
window token, native epoch and exact next update ID identify that publication.
A clock interval, retrace edge or screendump alone is not counted as a frame.
The unit is a **completed synchronous renderer publication**; guest drawing
completion, VBlank, physical scanout and input consumption remain unknown.
The capability continues to report `completed_guest_frames=false`.

On a source-bound process with full checkpoints, the virtual clock and the
new fence extension, `timeline_start`, `timeline_advance`, `timeline_rewind`,
`timeline_status`, `timeline_image`, `timeline_pin` and `timeline_stop` use an
immutable full-checkpoint/image DAG. The initial root is explicitly a paused
CPU/surface point and is not counted as a completed renderer update. Every
completed child carries its native publication and full private-disk state.
Earlier branches and stored images remain available after a new child or a
closed session. Image export reads the stored PNG without running or
refreshing the guest; pinning exports the exact cached full checkpoint bytes without
recapturing them.

```python
root = debug.timeline_start(max_frames=8, period_ns=16_666_667)
first = debug.timeline_advance(frames=1)
first_point = first["point"]
image = debug.timeline_image("first-frame.png")
debug.timeline_advance(frames=1)
debug.timeline_rewind(frames=1)
branch = debug.timeline_advance(frames=1)  # earlier child stays retained
stone = debug.timeline_pin("frame-anchor.qcow2")

# A new stopped session for the same project, source and native runtime:
restored = debug2.timeline_rewind(timeline=branch["timeline"], point=first_point)
```

Every point captures a complete native checkpoint. Retention can use full
payloads or opt-in lossless deltas. The optional N21 frame-key extension adds
owned physical makes/breaks while the CPU is stopped, scheduled edges before
a renderer advance, and held-key cold restore. N20 retains its released-input
contract. Partial-memory restore policies remain unqualified. Active task-private RAM/fetch layers and hooks are preserved by
the underlying full checkpoint. An earlier
hook, breakpoint, watchpoint or lifecycle stop ends the invocation without a
fabricated frame or another continue; uncertain execution/capture stays
journaled and is never silently retried. Known checkpoint/controller admission
failures refuse before an intent or execution, preserving the live owner.

The default 16-point limit includes the paused root and retained branches;
`max_captures` can bind earlier and no point limit exceeds 128. `max_bytes`
counts retained checkpoint and PNG payloads (default 512 MiB, maximum 1 GiB).
Per-state and per-image bounds are independent, and the project-wide 256 MiB
runtime-artifact cap can bind first. Live QCOW2 growth is measured separately.
The display period is an observation cadence, not a refresh-rate assertion.
The current checkpoint scope remains private QCOW2 and admitted controls,
with `host_files_restored=false`; planned directory/file layers remain open.
Nine direct native witnesses cover completed publication/PNG capture, retained
branches, offline export, separate-process restore, early stops, controller
guards and task-private IRQ/layer/hook preservation. The dated handoff and
!117 record the exact final source and verification receipt. The formal
migration gate remains open and DOSBox-X stays default and retained.

### Lossless checkpoint delta retention

Select `storage_mode="delta"` and a `keyframe_interval` in 1..128 to retain
complete checkpoint bytes as full keyframes or lossless XOR/zlib deltas. The
default remains `full`. This changes storage only: every point still takes a
complete native snapshot with the same input, layer, hook and IRQ state.
PNGs remain full, lossless screenshot artifacts.

```python
root = debug.timeline_start(storage_mode="delta", keyframe_interval=4,
                            max_frames=12, period_ns=20_000_000)
points = debug.timeline_advance(frames=3)
status = debug.timeline_status()
assert status["storage_mode"] == "delta"
full = debug.timeline_pin("portable-checkpoint.qcow2")
```

A delta binds its immediate DAG parent, base/result lengths and SHA-256 hashes,
codec descriptor, encoded payload and canonical artifact metadata. Full
keyframes reset chain depth; no chain reaches `keyframe_interval`. A result
that does not save space, including wrapper metadata, falls back to a full
checkpoint. Delta payloads above the ordinary 16 MiB artifact limit also fall
back to a full state, whose existing 128 MiB limit remains unchanged. Earlier
branches and all existing artifacts remain immutable and retained.

Transient capture returns complete checkpoint bytes before persistence, so a
delta point does not leave a hidden full checkpoint artifact. Restore validates
the entire dependency chain and PNG before journaling a restore or replacing
the live VM. It then uses the existing full-checkpoint source, runtime, native
control and owned-key validation. Reconstruction creates no permanent full
copy. `timeline_pin` explicitly publishes an ordinary standalone state artifact
with byte-identical original checkpoint data; it does not recapture or run the
guest. The version-2 renderer manifest is rejected by older full-only readers.
Previously stored full histories remain supported.

Status distinguishes `retained_encoded_state_payload_bytes`,
`retained_state_metadata_bytes`, `reconstructed_state_payload_bytes`,
`image_bytes_used`, `input_bytes_used` and `storage_bytes_used`, plus full/delta
point counts and the keyframe interval. The retained timeline budget charges
selected checkpoint payloads and canonical metadata, full PNG payloads and the
input journal. The project runtime-artifact cap separately covers actual
artifact payloads, including immutable manifest revisions and explicit pin
exports. Live QCOW2 growth and codec working memory remain separate; this is
not a disk or process-memory quota. Forward admission still reserves space for
a comparable full checkpoint and PNG, without assuming future compression.
Codec deadlines are checked before and after each bounded operation; zlib work
already in progress is not interrupted.

Four direct native witnesses compare reconstruction with the same point's
pre-encoding bytes, verify full PNG pixels, retain branches and cold restore,
refuse a corrupt base before VM replacement, restore held keys without
reinjection, and preserve task-private RAM/fetch, hooks and real IRQ state.
These are bounded local results; formal parity and DOSBox retirement stay open.

### Owned frame keys and input restore

`frame_inputs` requires the explicit virtual-clock profile and all three
native frame-key commands. Native ownership uses a token, epoch and generation
compare-and-swap, separate from ordinary physical-key leases. A validated batch
is applied atomically under QEMU's global lock without advancing the CPU or
virtual clock. Capacity is conservative: two edges when the PS/2 FIFO and
controller output are quiescent, zero otherwise. A refused batch has no input
effects. The supported grammar allows larger batches, but actual native
capacity always binds first; callers must inspect it rather than split and
retry an uncertain operation.

```python
debug.frame_inputs([{"key": "shift", "pressed": True},
                    {"key": "a", "pressed": True}])
held = debug.keyboard_state()["keyboard"]["frame_keys"]
point = debug.save_state("held-key.qcow2")
# Run to the next renderer publications; guest consumption needs its own oracle.
debug.timeline_advance(frames=3)
debug.frame_inputs([{"key": "a", "pressed": False},
                    {"key": "shift", "pressed": False}])
```

Frame edges accepted at the current timeline point append an input journal and
mark that live point dirty. Capturing the next completed renderer publication
clears the dirty flag and binds the input to a new full-state child. Pinning a
dirty point refuses; `timeline_rewind(frames=0)` restores the cached current
point and undoes pending input. Scheduled edges are validated for the entire
requested sequence before its first effect. A later capacity refusal or early
stop retains the recorded prefix and reports an incomplete result; scripts
stop at that result and do not dispatch their next step. Failed scripts close
new or uncertain held ownership instead of inventing release events.

Instrumentation format 2 binds the held QCodes and accepted-edge counters to
the actual PS/2 modifier/queue state, controller state and throttle deadline.
The device digest uses canonical scalar/byte encodings, not structure padding.
Cold restore first loads those device bytes, validates the proof, then adopts
ownership under a fresh native epoch/token without reinjecting makes. Ordinary
physical leases, pending input and active schedules still require explicit
resolution before a checkpoint. Foreign keyboard input invalidates an active
frame owner; no automatic adoption is allowed. After owned keys are released,
ordinary input positively detaches the empty frame owner.

Typematic repeat is not modeled by this increment (`repeat_supported=false`).
A held key proves its ownership and queued make state, not repeated characters,
input consumption, a completed guest frame or DOSBox parity. Full checkpoints
continue to report `host_files_restored=false`. DOSBox-X remains retained.

## Save and restore a restricted raw-machine checkpoint

For an original raw boot-disk project, explicitly select a `qemu-img` executable
with `qemu_checkpoint_tool` in Python/JSON launch or `--qemu-checkpoint-tool`
in the debug CLI. This mode requires a pinned firmware directory, standard
clock and retrace profiles, and audio off. Launch makes one private standalone
QCOW2 disk; writes never change the original boot image.

Stop the machine, remove breakpoints and watchpoints, and resolve pending or
held input before `debug-save-state` or `debug-save-anchor-stone`. The private
artifact contains the guest disk and QEMU internal snapshot. `debug-state-info`
reports its identity without launching an emulator. A compatible raw-machine
session can use `debug-load-state` or `debug-load-anchor-stone`; restore starts
a fresh stopped QEMU, checks the saved CPU observation, and invalidates old
memory edit plans, rule contexts, and framebuffer freshness. Keep this
byte-retaining state and project outside Git.

This does not restore source-bound COM/MZ process identity, host files, or
clock/input/media extension state. Saved-script state operations and state
forks are not admitted for this profile. It is not general DOSBox state or
Anchor Stone parity.

## Save a DOS process and restore in another session

Select `qemu_checkpoint_tool` with `backend='qemu-dos'`, a private DOS boot
image and pinned firmware. The native
[DOS checkpoint extension](../native/qemu-dos-checkpoint/README.md) admits a
stopped COM/MZ process during execution. It verifies the
original source and relocation mapping, child and helper allocation ownership,
the helper report, and an idle COM2 UART with an empty host control channel.
Release pending or held physical input before saving.

`debug-save-state` stores the private disk and VM snapshot together with a
hash-bound process and control record. Active RAM and instruction-fetch layers,
hook actions and hit counts, pending hook step-over, and user breakpoints are
included. The current RAM observation is preserved even when the guest has
changed an active RAM layer.

A later `debug-load-state` in the same project can restore the artifact after
the original session and Python process have closed. Launch a compatible DOS
session from the original source and boot inputs, then load the retained
artifact ID. Restore starts a fresh QEMU, checks the saved CPU, module RAM,
helper, PSP and allocations, reopens the helper channel, and recreates its
parent-return trap and debugger controls. Snapshot data carries the former
private disk and helper identity, so the previous staging directory is
unnecessary.

RAM layers use the restored guest RAM. Fetch overlays are rearmed against that
backing before execution resumes. Native breakpoints and physical layer
definitions receive fresh IDs where needed. The result's `controls` field
maps prior IDs to current IDs. Logical hook tokens and their hit counts are
preserved. The new runtime epoch invalidates previous memory edit plans and
other live bindings.

Existing entry-only QCOW2 artifacts retain their same-session loading route.
Checkpoints remain private byte-retaining artifacts.

### Instrumented clock, audio and retrace checkpoints

The additional [instrumented checkpoint extension](../native/qemu-instrumented-checkpoint/README.md)
supports the explicit `qemu_clock='virtual'` profile, optionally with
`qemu_audio='pc-speaker'` and `qemu_retrace='precise'`. The checkpoint includes
the native observer sidecar with retained PCM and callback ranges, renderer
pixels and publication configuration, timer phase and retrace provenance.
Restore verifies the saved virtual time and instruction counter, validates the
restored observers, and starts a fresh native clock epoch and host observation
epoch. Active observers continue with fresh tokens; the result's
`instrumentation.windows` maps their `old` tokens to their `new` tokens.
Historical receipts retain the former epochs and tokens.
Source-clock traces retain their original process-entry admission; tracing and
querying new restored-epoch source histories remains separate qualification.

Stop host clock synchronization and resolve scheduled input before saving or
loading. Held leases, queued edges, outstanding clock budgets and uncertain
native ownership are refused. Host monotonic anchors are not restored; start
a new synchronization mapping explicitly when needed. Generic QEMU migration
remains blocked after instrumentation use; this route admits only the bounded
local checkpoint operation. It does not establish audio playback, guest input
consumption, completed guest frames or DOSBox-X parity.

### Protected and V86 process checkpoints

A stopped selected CPU may be in protected or V86 mode when its instruction
pointer remains inside the verified DOS module. The ownership adapter observes
unpaged memory or supported non-PAE 4-KiB mappings, including DOS module, PSP,
helper and allocation pages remapped to qualified RAM. For remapped pages it
requires the [native task-context extension](../native/qemu-task-context/README.md),
checks the selected CPU context and page tables, and compares native linear and
physical reads. Restore checks CPU state, descriptor tables, ownership and
backing evidence before recreating controls. Unsupported paging formats,
ambiguous mappings and mixed-device memory remain outside this route.

A cooperating monitor can provide a separate task lifetime identity. While
stopped in the owned COM/MZ process, bind a physical RAM address containing its
`FDBTASK1` anchor and the expected 32-hex monitor UUID:

```json
{"method":"debug-dos-task-bind","params":{"run":"RETURNED_RUN","anchor_address":"0x150000","expected_monitor":"00112233445566778899aabbccddeeff"}}
{"method":"debug-dos-task-observe","params":{"run":"RETURNED_RUN"}}
```

The UUID and address above illustrate an authored monitor, not an automatically
discovered vendor scheduler. The stable task key also includes the monitor's
cookie and non-reused incarnation plus the owned DOS process nonce. The
scheduler generation and native architectural context provide separate
observations; CR3 or a TSS selector alone does not identify a DOS task. An odd
scheduler generation or invalid, changing or non-RAM anchor is refused. A
foreign task that encounters a bound execution hook produces `task-switch`
without dispatching its action or incrementing its hit count; explicitly run
again to continue. The task binding and controls can be restored in a fresh
session with the same project and original inputs.

An authored real-DOS monitor has exercised remapped 32-bit protected-mode
checkpoints in COM and MZ executables and two independently backed V86 tasks
using the same virtual PSP and code addresses, including A → B → A and a cold
restore in a separate Python process with active physical RAM/fetch layers and
task-scoped hooks. The V86 witness also restores virtual time and precise
retrace under the instrumented profile. This is evidence for that fixture,
not vendor compatibility.
Ordinary layers bind physical backing: if multiple tasks map the same physical
page, they share that page's RAM/fetch layer effects. The separate experimental
task-private layer interface below is intended to isolate cooperating tasks
that alias the same backing. When a cooperating task is bound, its source
views, source tracing and hooks require that task; source tracing and hook
redirects still require real mode. There is no automatic
inference of QEMM or DESQview task IDs, and these observations do not
qualify either vendor installation, arbitrary DPMI clients or DOSBox parity.
DOSBox stays available and remains the default while the separate gates remain
unqualified.

### Experimental task-private page views

The task-private extension is opt-in. The local x86 TCG build and bounded
same-page, reset and checkpoint witnesses have passed; the formal migration
and vendor compatibility gates remain unqualified.
In this monitor-committed mode, the guest remains responsible for saving CPU
state, selecting its task and restoring its interrupt frame; fDisBull does not
infer a vendor scheduler. After writing a complete even
`FDBTASK1` anchor, that monitor must issue `OUTW` to port `0xf1db` with value
`0x4446`. The native extension uses the committed identity to select the CPU's
task-private view. An incomplete, unknown or retired lifetime is intended to
revoke the view and stop before the next task executes.

Bind the current task first. `dos_task_switching()` enables the monitor, then
`dos_task_register(cookie=..., incarnation=..., pages=[...])` declares each
task and its aligned physical RAM pages, including pages for the initial task.
The corresponding JSON routes have `debug-` prefixes and hyphenated names.
A private stack can be constructed with `dos_task_layer_patch(...)` and
`dos_task_layers(...)`; `dos_task_memory(..., view='ram'|'execute'|'base')`
inspects a registered task explicitly, including an inactive one. Retire a
nonselected lifetime with `dos_task_retire(task)`. Registration is bounded to
16 task lifetimes and 16 pages per task; retired identities remain tombstones
and cannot be reused as the same lifetime. A reused cookie needs a new,
non-reused incarnation. Task-scoped hooks may share an execution address but
bind to different registered identities.
Clear ordinary global layers before enabling task-private views. Hooks with
nonempty global-layer actions must be replaced with task-private actions at
that boundary; register-edit and redirect hooks retain their existing rules.

The CPU RAM and instruction-fetch views are keyed by task identity and
resolved physical backing. CPU writes to a private page remain in that task's
arena; a different task can have a separate view even when both select the same
physical page and CR3. Ordinary GDB and QMP memory reads and device accesses
continue to observe shared base RAM, not a selected task's private CPU view.
Use the explicit task-memory views when comparing these observations. Bound
source ownership and source views use the task-private read path where needed.
Private anchor pages, paging-structure pages, PAE and unsupported or ambiguous
mappings are rejected rather than treated as private task RAM. Ordinary
physical layers still have their shared-backing semantics.

Native VMState version 1 includes the private arena, selected identity,
registrations and tombstones. The version-3 host control sidecar preserves
per-task stacks, shared hook traps, hit counts and the pending hook; on
restore, task IDs remain stable while `task_views.layers` maps prior private
layer IDs to their fresh IDs. The previous checkpoint formats and
instrumentation remain subject to their own admission checks.

The authored DOS witness runs A → B → A → B → A with identical CR3, TSS,
virtual code/PSP addresses and physical backing. Its guest-written log records
private data reads of `1234`, `5678`, `1235`, `5679`, `1236` and fetched carry
results `0`, `1`, `0`, `1`, `0`; shared base data stays zero. A separate Python
process restores that checkpoint and continues the per-task hooks at their
saved hit counts. The same witness passes with virtual clock and precise
retrace. Other local cases cover dormant generation-zero tasks restored in
protected/V86 mode, single-step commit followed by a selected-B checkpoint,
reset revocation, retired/unknown/odd commits, and atomic MMIO/page-table
refusal. These are bounded cooperating-monitor results, not QEMM/DESQview
vendor qualification or a replacement DOS scheduler.

### Experimental native cooperative CPU scheduler

A separate opt-in native scheduler runs on top of task-private views. A bounded
authored real-DOS/V86 witness has passed locally for cooperative scheduling,
hardware interrupt-frame ownership and cold restoration. This does not
establish QEMM or DESQview compatibility or general interrupt-preemption
parity, and DOSBox remains the default.

After binding the initial cooperating identity, enabling task-private views
and registering the tasks and physical pages, `dos_task_scheduler()` captures
the current task's stopped CPU context. `dos_task_fork(task=..., entry=...,
stack=..., registers=..., eflags=...)` admits a registered child from that
context. Entry is a source address in the same verified COM/MZ allocation;
the stack must also fit that allocation and its cloned segment cache. This is
a controlled shared-source fork, not permission to invent arbitrary dormant
DOS processes or infer their allocations. Use `dos_task_context(task=...)`
and `dos_task_scheduler_observe()` to inspect CPU, frame and runqueue receipts;
`dos_task_runnable(task, runnable=...)` changes an admitted slot's state.
Each has a corresponding `debug-dos-task-...` JSON route.

Guest `INT 60h` is the explicit cooperative yield and `INT 62h` blocks the
current task. The native round-robin scheduler chooses the next
runnable task, owns saving and restoring its architectural context and private
view, and updates the cooperating anchor; the guest does not select the next
task or copy its interrupt frame. An ordinary guest interrupt through a
protected-mode gate still uses CPU-created frames and `IRET`; its ownership
is tracked separately from the yield. If no slot remains runnable, execution
reports `scheduler-idle` at the stopped boundary. The caller can inspect the
result, use `dos_task_scheduler_disable()` at a supported stopped state, and
explicitly continue the guest's own cleanup code; the scheduler does not
manufacture a DOS exit.

The local authored witness exercises two V86 tasks sharing one verified DOS
allocation. They retain distinct registers, direction and carry flags, stacks,
x87 values, private RAM and instruction-fetch layers, and same-site task
hooks. Per-task x87 rounding controls convert the same guest value, 1.5, to 1
and 2 respectively across switches and cold restore. A guest watchpoint witness
uses identical DR7 controls with different DR0 addresses; its exception return
addresses verify the selected task's watched write before and after restore.
A protected-mode INT 61h frame remains owned by dormant task B across cold
restoration in a separate Python process. The witness also exercises a
single step through INT 60h, scheduler idle and disable, and subsequent guest
DOS exit. An instrumented profile preserves virtual clock, precise retrace
and VGA configuration across restore, along with audio observer state and token
rotation. That audio window contained zero frames and zero dropped frames; it
provides no PCM or audible speaker playback evidence. Separate local guards
exercise an unowned interrupt stack, mixed-task IRET and a fault with an error code. These are authored, bounded
results, not general scheduler qualification.

Checkpoint state includes scheduler slots, CPU context, frame ownership and
private views, with fresh native epochs on restore. PAE, long mode, unsupported
CPU or interrupt-frame forms and uncertain ownership are refused;
other real/protected/V86 use still requires the specific admitted mapping and
frame constraints. A cooperative `INT 60h` round robin is not evidence that
PIT/IRQ preemption, real vendor multitasking, arbitrary DPMI clients or general
DOSBox behavior has been qualified.

### Bounded PIC IRQ preemption

The optional `dos_task_preemption(irq=0, quantum=1, enabled=True)` control,
JSON `debug-dos-task-preemption`, requires the native CPU scheduler and its
PIC preemption extension. Scheduler API 2 admits direct master-PIC IRQs 0
through 7 except cascade IRQ2. API 3 additionally admits slave-PIC IRQs 8
through 15; both use a quantum of 1 through 65535.
Native QEMU observes real PIC acknowledgements and the guest's matching EOIs;
after the configured number of eligible IRQs it selects the next runnable
registered task. The guest handler remains responsible for servicing the
device and issuing EOI. Python does not inject an IRQ, acknowledge the PIC or
choose the next task.
`dos_task_scheduler_observe()['preemption']` reports policy, quantum phase,
acknowledgement/EOI/preemption counters, selected transitions, PIC state and
in-flight IRQ/frame ownership.

API 3 maintains an ordered stack of acknowledged hardware IRQs
and the native task/interrupt frame owning each one. A slave IRQ requires its
slave PIC EOI before the master cascade EOI; a nested higher-priority IRQ has
its own acknowledgement and EOI obligations. A pending task switch is deferred
until all outstanding required EOIs have completed, so an outer frame still
awaiting an EOI cannot be parked. Multiple eligible quanta during that wait
coalesce into one pending handoff. A stopped checkpoint may preserve a
consistent nested stack or a partial cascade after the slave EOI and before the
master EOI. An unowned frame, inconsistent PIC state, incomplete unbacked
handoff or unsupported PIC mode is refused. PIC polling, auto-EOI and unsupported priority modes do
not become supported by this interface. Execution remains one TCG vCPU with
the existing same-source/allocation task-fork and private-page limits.

Local authored FreeDOS/V86 witnesses have passed with real RTC IRQ8 and nested
i8042 keyboard IRQ1. They cold-restore both a two-frame state before either EOI
and a state after the slave EOI but before the outer master EOI. With IRQ1 as
the policy target, a pending handoff survives the partial-EOI restore and runs
once only after the outer EOI. The guest services and accounts for any additional
real empty keyboard IRQ instead of discarding it. The witness observes both
inner and outer IRET and stops after A resumes in V86; it makes no DOS-cleanup
or vendor-parity claim. Separate local guards exercised nested IRET without
its required EOI and a master cascade EOI before the slave EOI.

These results are separate from the API 2 direct-master IRQ0/IRQ1 evidence
below. API 1 cooperative scheduling and API 2 direct-master PIC support remain
recognized on compatible earlier runtimes; a saved state still requires a
runtime that admits its actual checkpoint format and features.

Local authored FreeDOS/V86 witnesses have exercised PIT/PIC IRQ0 and actual
i8042 keyboard IRQ1 without guest software yields. The IRQ0 witness preserves
private RAM and instruction-fetch layers, task-scoped hooks and CPU state; it
cold-restores in a separate Python process both before EOI with the PIC in
service and after EOI with the interrupted task's hardware frame dormant.
It checks the saved IRET PC, stack and flags, the quantum-one single-step EOI
boundary and quantum-three phase across a fresh QEMU restore. Separate guards
observe an actually pending IRQ in PIC IRR while IF is clear or IRQ0 is masked.
For the chained `STI; MOV SS; INC` case, delivery is accepted after `MOV SS`
or after `INC`; an isolated `MOV SS` delay with an already-pending IRQ has not
been established by these tests. The IRQ1 witness reads guest keyboard make and
break bytes and observes the corresponding PIC/EOI task transitions; it ends
at a stopped boundary and is not a DOS cleanup or keyboard-parity claim.

A further local IRQ checkpoint profile passed with virtual clock, precise
retrace, VGA configuration, x87 and an active PC-speaker observer at both the
pre-EOI and post-EOI cold restores. It retained observer state and rotated its
token under fresh native clock epochs. Both audio windows contained zero frames
and zero drops, so this provides no evidence of PCM sample continuity or audible
playback. These local IRQ cases are bounded authored evidence, not general
interrupt timing, vendor QEMM/DESQview compatibility or permission to retire DOSBox. Unsupported IRQ,
paging, frame, pending-switch and ownership states remain subject to explicit
admission and refusal.

## Prepare and check the core

Use a separately installed `qemu-system-x86_64` version 9.1 or later and its
matching PC firmware. No custom QEMU patch, DOS installation, Python media
renderer or game is required for the core self-test. QEMU's TCG backend is
selected explicitly; this lane does not use KVM or a host virtualization API.

```sh
fdisbull dos-migration
fdisbull dos-migration --slice layers-hooks --details
fdisbull doctor --backend qemu-dos --executable /path/to/qemu-system-x86_64 \
  --qemu-firmware /path/to/qemu/share/qemu --qemu-transport pipe \
  --output /private/native-qemu-check
```

The doctor runs disposable authored boot code and returns a receipt. Its core
result does not qualify DOS services, drivers, a game, checkpoint restore or
DOSBox parity. Inspect the individual checks and reported graphics capability;
minimal QEMU builds may omit `screendump`. Source tests separately exercise an
authored COM probe under an actual FreeDOS installation.

The default control transport remains private Unix sockets. `pipe` is an
explicit POSIX alternative using QMP over the owned process's standard streams
and GDB over private FIFOs. It needs no listening TCP port. Channel errors and
uncertain dispatched control operations close the owned machine; they are not
automatically replayed. QEMU's executable identity and an explicitly selected
firmware directory's top-level file identities are recorded. The default
firmware search path is labelled unpinned when no directory is supplied.

## Boot a private DOS disk

Keep the disk and project outside Git. The initial native DOS profile admits
512-byte sectors, a boot signature and a maximum image size of 64 MiB. Standard
floppy sizes select the floppy device; other sizes select IDE. The basic
profile defaults to a 486 and 32 MiB, with one vCPU and no network.

```sh
fdisbull dos-profile /private/DOS.img
fdisbull import /private/DOS.img /private/dos-native.fdb \
  --arch x86 --bits 32 --base 0 --entry 0
fdisbull debug /private/dos-native.fdb --backend qemu-dos \
  --executable /path/to/qemu-system-x86_64 --game-dir /private \
  --qemu-firmware /path/to/qemu/share/qemu --qemu-transport pipe
```

The raw disk uses a 32-bit **file-address view** so a complete floppy fits in
the project. This does not make DOS execute in 32-bit mode. Native traces use
the observed CPU mode and code-segment width at each instruction. Disk offsets
do not establish a loaded COM/MZ program's source-to-memory mapping.

The machine starts paused at reset. Use the returned run ID in the same
retained `debug` server, for example:

```json
{"method":"debug-breakpoint","params":{"run":"RETURNED_RUN","address":"0x7c00"}}
{"method":"debug-run","params":{"run":"RETURNED_RUN","timeout_ms":10000}}
{"method":"debug-registers","params":{"run":"RETURNED_RUN"}}
{"method":"debug-memory","params":{"run":"RETURNED_RUN","address":"0x7c00","length":16,"space":"physical"}}
{"method":"debug-stop","params":{"run":"RETURNED_RUN"}}
```

Boot-image identity must match the original project throughout profile admission
and the private runtime copy. QEMU writes to a disposable snapshot over that
copy; the selected source disk stays unchanged. Closing the session discards
runtime disk changes. Firmware identity is an admission observation, not a
promise that the caller will never modify that external directory.

`dos-profile --cpu max --memory-mib 64` can prepare another explicit machine
configuration. Pass the returned profile object as `guest_profile` in a JSON
`debug-launch` request. The ordinary CLI `--guest-profile dos` uses the defaults.
Do not use the Windows-only launch `--memory-mib` flag for this profile.

For an installed QEMM or DESQview configuration, use its existing profile:

```sh
fdisbull debug /private/dos-native.fdb --backend qemu-dos \
  --guest-profile qemm --executable /path/to/qemu-system-x86_64 \
  --game-dir /private --qemu-transport pipe
```

The QEMM/DESQview readers still inspect the selected disk and bind its files;
their live observation rules are unchanged. Profile admission does not prove
that the manager loaded or that scheduling works. See
[DOS drivers and QEMM](DOS_DRIVERS_AND_QEMM.md) and
[DESQview and memory search](DESQVIEW_AND_MEMORY_SEARCH.md).

## Launch an original COM or MZ through DOS

The executable and boot disk are separate inputs. The project binds the
original executable; `--dos-boot-image` selects the DOS installation. Supply
`mcopy` from mtools and a FAT12/FAT16 image with a returning startup batch.
`FDAUTO.BAT` is the default; select `AUTOEXEC.BAT` explicitly for a disk that
uses that name. A partitioned FAT12/FAT16 disk is also admitted within the
64 MiB profile limit.

```sh
fdisbull import /private/game/TARGET.COM /private/target.fdb --image com
fdisbull debug /private/target.fdb --backend qemu-dos \
  --executable /path/to/qemu-system-x86_64 --game-dir /private/game \
  --dos-boot-image /private/DOS.img --dos-mcopy /path/to/mcopy \
  --dos-startup-batch FDAUTO.BAT --dos-arguments ' ALPHA.TXT /Q' \
  --qemu-firmware /path/to/qemu/share/qemu --qemu-transport pipe
```

For a classic MZ EXE, import it normally and use the same debugger options.
JSON `debug-launch` accepts `dos_boot_image`, `dos_mcopy`, `dos_startup_batch`
and `dos_arguments`. The source filename in `game_dir` must still match the
project's original SHA-256. Patched project versions and secondary-format
executable stubs are refused by this initial process path.

Staging copies the selected disk, preserves its configuration and existing
startup bytes, adds the source and an authored loader, and appends the loader
invocation. Existing shell setup executes first. Assets and drivers must
already be present on the image; this route does not import the rest of
`game_dir`. A nonreturning batch, name conflict, changed source, full disk or
loader error fails the launch. Source disk and executable remain unchanged.
COM2 is reserved for the loader's observation protocol.

The launcher uses DOS EXEC load-only, validates the stopped helper report,
PSP, parent, command tail, MCB ownership and full loaded module, then stops at
the child's first instruction. MZ mapping derives from the actual returned
entry, including high-load placement; declared relocations are applied in
order. DOS's exact initial-AX and COM return-zero writes are recorded in
`source_mapping.loader_writes` wherever they overlap file-backed bytes.
Overlay bytes and uninitialized allocation are not misrepresented as loaded
source bytes. Entry DS/ES, SS:SP and initial AX are retained.

Use the returned run ID in that retained debugger server:

```json
{"method":"debug-dos-process","params":{"run":"RETURNED_RUN"}}
{"method":"debug-run","params":{"run":"RETURNED_RUN","timeout_ms":5000}}
{"method":"debug-dos-process","params":{"run":"RETURNED_RUN"}}
```

`debug-dos-process` reports the selected PSP, source map, allocation,
environment segment, FCBs, entry registers, device-header chain and lifecycle.
All register/memory/breakpoint controls still address the native machine.
Use the map's runtime addresses explicitly; a static project address is not
automatically a runtime breakpoint. The map verifies the initial load, not
continuous byte equality after self-modification or subsequent overlay loads.

The reserved parent-return breakpoint separates selected-process completion
from a nested child's exit. A verified DOS return becomes `guest_exit` or
`guest_tsr`; the machine remains owned and stopped. DOS's termination category
does not identify which exit instruction ran. TSR results include observed
retained allocations and before/after interrupt vectors; live source ranges
are clipped to retained allocations. Exit, residency and machine close advance
the capture epoch so old memory-edit plans cannot silently cross lifetimes.
An invalid return report closes the machine and invalidates the binding without
inventing a successful termination. The protocol corroborates guest state;
it is not authentication against a guest that controls its own memory.

Process entry currently requires observed real mode. QEMM, DESQview, DPMI and
V86 process combinations need separate qualification. Existing raw-machine
profiles and report readers remain available. A validated device-chain header
or an authored SYS initialization marker establishes only that observation,
not successful arbitrary driver I/O.

Startup uses one host-time budget across staging and control setup. Execution
timeout recovery may use the existing five-second GDB interrupt allowance;
parent-return observation has a five-second bounded budget, capped by an
enclosing source-trace deadline when present. These are
host control budgets, not DOS cycle or guest-time guarantees.

## Trace the verified DOS process

After original COM/MZ launch stops at its real DOS entry, the existing public
routes can inspect register values and code transitions:

```json
{"method":"debug-trace","params":{"run":"RETURNED_RUN","name":"entry.json","count":8,"timeout_ms":10000}}
{"method":"debug-trace-until","params":{"run":"RETURNED_RUN","until":{"kind":"register","register":"ax","equals":7},"max_steps":100,"timeout_ms":10000,"name":"ax-seven.json"}}
```

The operations are sequential examples: the first advances the process before
the second starts. Use a fresh launch for independent trials. `trace(count=N)`
preserves N attempted stop intervals and N preceding snapshots when successful;
`trace-until(max_steps=N)` records the initial boundary and up to N endpoints.
Budgets count debugger stop intervals, not retired instructions. Predicates
reuse the existing unsigned register comparisons, masked register values,
`pc-range` in project/linear/segmented coordinates, decoded mnemonic,
`region-change`, `nonsequential`, and bounded `all`/`any` combinations.

Every source observation includes actual instruction bytes, full registers,
observed real-mode addressing, selected PSP and the original capture epoch.
Its linear `address` remains available; `segmented_address` records CS:IP and
`identity.project_address` supplies the verified static coordinate. The
runtime instruction hash remains distinct from the canonical source-site hash.
The latter uses the original project's relocation base and exact DOS startup
writes, allowing a normal relocated MZ operand to identify the same site in
independent launches. A changed opcode/decode, relocation crossing an
instruction boundary, unsupported wrapping or an unverified byte sequence
cannot acquire a source-site identity.

QEMU's actual `qqemu.sstepbits` and `qqemu.sstep` replies are retained without
changing the policy. A successful debugger stop does not certify completion:
a fault can stop in its handler and REP can stop after a partial iteration.
`instruction_completed` therefore remains unknown after an attempt. IRQ/timer
masking is reported from the observed mask; this tracing mode does not certify
natural DOS timing or a scheduled task's identity.

The collector checks the selected allocation through the MCB chain and the PSP
parent at each boundary. It checks each decoded instruction against the
verified load, allowing ordinary data writes elsewhere. Leaving the module,
self-modification, a changed allocation, process epoch, hidden segment mapping
or CPU mode stops source capture. It does not silently adopt a new overlay.
User break/watchpoints remain owned by their caller and stop the capture;
the internal parent-return breakpoint retains its lifecycle role.

Saved artifacts work with `event-trace-query`, `event-search-start`,
`event-search-refine` and `event-search-results`, including after exit, session
close and project reopening. Storage rederives original/runtime/canonical bytes
and checks the ordered original entry receipt, artifact receipt, epoch and
instruction identity. A current closed-process state cannot invalidate an
authentic historical capture, and a current live state cannot invent one.
Only closed, qualified observation windows can narrow an event search. A final
unbound boundary may satisfy an explicit runtime predicate, but its open source
window cannot prove absence of a source event or contribute a false site.

Queued `action` input inside `trace-until` remains refused before execution,
including saved-script preflight. Use a bounded natural run to dispatch physical
input, stop at an explicit machine breakpoint, and start a separate source
trace. That earlier run is an unobserved interval, not a contiguous trace or
proof that the input caused a particular instruction.
Raw-disk sessions retain machine traces and do not gain a COM/MZ source binding
or the process-specific `trace-until` method.

### Join source observations to virtual time

With the explicit `qemu_clock='virtual'` process profile,
`capabilities['source_trace_clock']` is true and source traces automatically
retain an optional `clock` on each stopped event. Standard and instruction
profiles retain their existing clockless source traces. This host-side path
uses the existing native clock extension; it introduces no new QEMU patch.

Each `fdisbull-source-clock-1` record identifies `QEMU_CLOCK_VIRTUAL`, the owned
`run`, host observation `epoch`, native `native_epoch`, `virtual_ns` and the
separate `icount`. Its compact `before` and `after` samples surround the whole
ownership/register/instruction observation. Both must report identical native
time, counter and epoch, with increasing observation sequences. An unstable
bracket is rejected and invalidates the owner. Trace samples share the epoch
and sequence used by `clock_observe()` without creating two additional journal
events for every source row.

Use the exact observed identity with a half-open `virtual-time-range` predicate:

```python
anchor = debug.clock_observe()
trace = debug.trace('timed-source.json', count=4, timeout_ms=3000)
last = debug.clock_observe()
interval = {
    'kind': 'virtual-time-range',
    'run': anchor['run'],
    'epoch': anchor['epoch'],
    'native_epoch': anchor['virtual_clock']['native']['epoch'],
    'start_ns': anchor['virtual_ns'],
    'end_ns': last['virtual_ns'] + 1,
}
rows = project.event_trace_query(trace['artifact'], predicate=interval)
```

Use this example at a verified source boundary whose next four stop intervals
remain in the module. Time bounds are integers with
`0 <= start_ns < end_ns <= 2**63`; the end is excluded. Query rows and search
witness samples retain the validated clock. The optional `endpoint_clock` in
a query reports the final stopped endpoint separately: `trace(count=N)` still
stores N preceding events, and its Nth endpoint remains in the artifact's
`collector.current_stop.clock`. That endpoint is not an additional matched row
or source candidate.

The same predicate works in `debug-trace-until` and saved `trace-until` script
operations. Every clock leaf, including a nested `all`/`any` branch, must match
the current run and clock epoch before execution. Saved scripts check those
identities before any earlier mutation and recheck when the trace begins.
Trace-until parameters remain literal: obtain an identity from an earlier
request; `$receipt` interpolation inside its predicate is unsupported. A live
time predicate finds an observed debugger boundary in the interval. It does
not install a clock budget or promise to stop at the interval's first
nanosecond. Keep `max_steps` and `timeout_ms` finite.

On reopen, storage checks source lineage, exact virtual-profile admission,
native epoch, stable brackets and monotonically ordered event clocks. Missing
clocks and foreign identities are unknown in retrospective predicates; old
clockless artifacts remain readable. Malformed clock evidence is rejected
even for a register-only query. Candidate code-site identities remain
independent of time so source comparison across runs still works.

A time predicate can match a clock-qualified final boundary outside the source
binding. Its source site stays unknown and `source_window_closed=False`
prevents search narrowing, as with existing explicit runtime predicates.

Within the same run and both epochs, these timestamps can be compared with
input `dispatch_ns`, renderer `published_ns` and audio callback times. The
comparison establishes temporal ordering of observations. Equal nanoseconds
do not establish callback order. It does not fill an untraced interval, prove
input consumption or causation, identify a completed guest frame, or establish
natural instruction latency. The recorded GDB IRQ/timer step policy still
applies, and `icount * 128` is never substituted for elapsed virtual time.
The separate [host clock controller](DOS_QEMU_TIMING.md) uses the same native
clock without changing source-observation or causality claims.

One absolute host deadline now covers source-trace lock admission, observations,
stepping and persistence, intersecting existing script, session and channel
bounds. A late synchronous storage operation can already have written an
artifact or journal entry; the post-check reports failure and preserves the
known stop and available IDs in `ExecutionTraceError.result`. If the deadline
expires before publication, the partial result can have no trace artifact.
Inspect that result rather than retrying execution. Existing bounded native
interrupt recovery can outlast admission, but cannot authorize a fresh clock
read or successful publication after expiry.

## Physical input, clocks and display observations

### Queue explicit controller edges

The native API queues input in Python while the VM is stopped. By default,
`run()` sends one GDB continue, checks QEMU's run state, sends at most one QMP
input batch, and consumes that same GDB stop packet. This preserves breakpoints/watchpoints
and their reasons. It does not start another run when an early stop wins.

```python
# debug is a live qemu-dos session stopped at a known waiting loop.
lease = debug.keyboard.key_down('a')['lease']
debug.keyboard.key_up(lease)
point = debug.breakpoint(known_runtime_consumption_address)
result = debug.run(timeout_ms=5000)
print(result['input_delivery'])
debug.delete_breakpoint(point['breakpoint_id'])
```

That immediate delivery receipt is `qmp_accepted` or `not_dispatched`;
`guest_consumed` remains `None`. An early breakpoint may leave the batch pending,
or QEMU may accept it before the guest consumes anything. Inspect guest RAM/registers or
driver state to establish consumption. A failed/uncertain QMP acknowledgment
closes the owned VM and invalidates its input without replay.

`keyboard_key_down/up` and the `keyboard` namespace use machine-owned leases.
Aliases such as `esc` and `escape` share ownership. The corresponding mouse
methods are `mouse_move_relative(dx, dy)`, `mouse_button_down(button)` and
`mouse_button_up(lease)`. Motion is relative controller movement, not a pixel
coordinate. Buttons are `left`, `middle` and `right`. The authored native
mouse witness handles IRQ12 directly; a real game still needs its own
admitted mouse driver or hardware consumer. This does not emulate DOSBox's
built-in INT33 driver.

`input_state()` reports the owned queue, leases and last delivery. It does not
read the guest's key state or mouse cursor. `input_cancel_pending()` discards
only unsent transitions; an already accepted hold remains owned and needs an
explicit release. Closing the VM invalidates its leases without claiming that
guest release code ran. Ownership is machine-scoped, including after a DOS
child returns to its parent. Limits are 256 pending edges, 64 active leases,
and relative axis deltas within -32767..32767.

Pending input blocks `step()`, traces and unbounded `resume()` before execution;
use a bounded `run()` or cancel it. Pixel clicks and frame-edge input remain
refused. Separate virtual-clock extensions below provide timed keyboard
chords/text and physical button pairs; their capability checks are explicit.
Queueing make and break together in the ordinary path specifies ordering,
not a held duration.

The retained JSON server exposes `debug-keyboard-down/up/state`,
`debug-mouse-move-relative`, `debug-mouse-button-down/up`, `debug-input-state`
and `debug-input-cancel-pending`. Native saved scripts use
`keyboard.key-down/up/state`, `mouse.move-relative`, `mouse.button-down/up`,
`input-state` and `input-cancel-pending`; aliases can pass returned leases to
later steps. Failed scripts that touched physical input close the owned VM.
All static input/transaction checks precede earlier script mutations.
The new I/O operations share the script's one host-time deadline, including
lock admission and nested QMP/GDB reads. Existing Windows native snapshots
refuse pending or held machine input before migration because their current
sidecar does not restore these leases; the refusal preserves the live owner.

### Observe a declared clock

The default `qemu_clock='standard'` preserves the ordinary TCG launch. Its
`clock_observe()` explicitly reports the instruction counter as unsupported.
Select `qemu_clock='instruction'` in `Project.debugger` or `debug-launch`,
`--qemu-clock instruction` on the CLI, or `clock_profile='instruction'` in
`Project.machine` to enable the single-vCPU fixed-shift profile:

```text
-accel tcg,thread=single -icount shift=7,align=off,sleep=off
```

`clock_observe()` / `debug-clock-observe` / script `clock-observe` then records
the actual `query-replay.icount` value, a machine epoch, an observation sequence
and a separately labelled host monotonic timestamp. No record/replay mode is
enabled. Malformed or regressing counters invalidate the owned machine.

The counter covers firmware, DOS, interrupts and application execution. It is
not a process clock, a retirement proof or cycle-accurate emulation. In this
profile QEMU can jump its virtual clock to a timer deadline while the CPU is
halted. Consequently `icount * 128` does **not** measure all elapsed guest
nanoseconds. Both `virtual_ns` and `guest_ms` remain `None`. `run(timeout_ms=...)`
retains a host-time budget and a bounded interrupt-recovery allowance; it does
not acquire exact instruction-count or guest-time stopping. The instruction
profile changes timing and must be explicitly chosen for comparisons.

Guest boot delays can also outlast a host startup budget under instruction
counting. The I/O witnesses use an explicit FreeDOS configuration containing
`SWITCHES=/F` to skip its F5/F8 boot-key delay, for both clock profiles. This
choice is confined to those tests. Production preserves the caller's CONFIG
and startup batch; it never inserts that switch, increases the deadline or
changes profile automatically. The [handoff](DOS_QEMU_HANDOFF.md) retains the
original timeout, stopped-state diagnosis and controlled comparison. See the
FreeDOS [SWITCHES reference](https://help.fdos.org/en/hhstndrd/cnfigsys/switches.htm)
when deliberately preparing a separate test image.

### Continue with a native virtual timer

Select `qemu_clock='virtual'` in Python/JSON, `--qemu-clock virtual` on the CLI,
or `clock_profile='virtual'` in `Project.machine`. This profile requires the
explicit [QEMU 10.0.13 clock extension](../native/qemu-clock/README.md), with
one TCG CPU and the same fixed `shift=7,align=off,sleep=off` settings. A stock
executable is rejected while the new machine is still paused. The `standard`
and `instruction` profiles continue to work with stock QEMU.

The extension reads `qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)` directly.
`clock_observe()['virtual_ns']` therefore includes QEMU's idle-time advances.
The instruction counter remains a separate value, and `guest_ms` remains
`None`: this is a declared QEMU clock domain, not the legacy DOSBox scheduler.
The native epoch, executable identity and admission receipt remain attached
to the owned machine. A reset, unsupported restore/runstate, changed epoch
or regressing clock invalidates the observation.

```python
with project.debugger(qemu_with_clock_extension, game_dir,
        backend='qemu-dos', dos_boot_image=dos_image, dos_mcopy=mcopy,
        qemu_clock='virtual') as debug:
    before = debug.clock_observe()
    result = debug.clock_advance(20_000_000, timeout_ms=3000)
    budget = result['clock_budget']
    # Inspect both the actual native stop and the timer receipt.
    print(result['outcome'], budget['deadline_reached'], budget['elapsed_ns'])
```

The matching JSON method is `debug-clock-advance` with `run`, `delta_ns` and
optional `timeout_ms`. Saved scripts use `clock-advance` and may assert
`$advance.clock_budget.deadline_reached` explicitly. Each call accepts an
integer duration from 1 ns to 60 seconds, arms one native virtual timer and
issues exactly one ordinary GDB continue. Earlier breakpoints, watchpoints,
DOS exit/TSR and physical-input receipts remain visible. There is no automatic
continuation to consume the rest of the duration. A successful input dispatch
still does not certify consumption by a guest driver.

The receipt separates `start_ns`, `deadline_ns`, `fired_ns`, `stopped_ns`,
`elapsed_ns` and `overshoot_ns`. `deadline_reached` means the native timer
fired; it does not establish that the timer was the only concurrent stop
cause. An earlier stop has no firing time or overshoot. QEMU rounds busy
execution to instruction quanta, and other due callbacks can share a
boundary, so this API does not promise an exact arbitrary-nanosecond cutoff
or cycle accuracy. The extension's own pause produces GDB SIGINT; genuine
debugger traps retain SIGTRAP, preventing a timer stop at a matching PC from
being relabelled as a breakpoint or DOS return.

The host deadline starts before machine-lock admission and covers startup of
the debugger channel, observation, arm, continue, register/process readback,
token-bound cleanup and evidence persistence. It also respects any shorter
script or channel deadline. GDB retains its existing bounded interrupt
recovery, but that allowance cannot authorize another run or fresh clock
cleanup. An uncertain arm, unconfirmed disarm, expired post-execution budget
or failed execution evidence closes the owned VM. The timer and its deferred
stop request must both be absent before another operation is admitted.

The clock extension blocks generic migration after budget use. The separately
admitted instrumented DOS checkpoint route above preserves its bounded native
state. Completed-frame/audio fences and scene scheduling still need their own
integration and qualification. The bounded periodic memory-rule route below uses
this explicit native virtual clock. The optional
keyboard extensions below implement separately admitted single chords and
bounded US-layout text, with guest consumption and layout still unqualified.

### Schedule one physical-input batch on virtual time

The optional [input extension](../native/qemu-input/README.md) adds
`input_schedule(delta_ns)` and `input_schedule_observe()`. Build its QEMU 10.0.13
patch **after the current clock and media patches**, and select the explicit
`qemu_clock='virtual'` profile described above. The raw machine factory uses
`clock_profile='virtual'`. Check `capabilities['virtual_input_schedule']` before
using this path. Stock QEMU and the standard/instruction profiles retain the
existing immediate-input path; they do not acquire this capability.

Queue the desired keyboard or relative PS/2 mouse edges while stopped, then
arm their one token-owned batch. Arm and observation are passive: they neither
send input nor execute the guest. The caller next chooses one bounded
`run(timeout_ms=...)` or `clock_advance(delta_ns, timeout_ms=...)`. The latter
adds a separate native stop budget; choose an input deadline earlier than its
budget deadline when dispatch is wanted.

```python
# debug uses the clock + media + input build and is stopped at a known wait.
lease = debug.keyboard.key_down('a')['lease']
armed = debug.input_schedule(5_000_000)
assert debug.input_schedule_observe()['state'] == 'armed'
result = debug.clock_advance(20_000_000, timeout_ms=3000)
delivery = result['input_delivery']
print(result['outcome'], delivery['state'], delivery['dispatch_ns'])
```

The timer dispatches through the selected native PS/2 handlers and one final
sync. The receipt format is `fdisbull-qemu-scheduled-input-1`; inspect its
`token`, `state`, `edge_count`, `sequences`, `start_ns`, `deadline_ns`,
`terminal_ns` and `dispatch_ns`. `lateness_ns` is the actual dispatch time minus
the requested deadline, not a host-delay estimate. `input_state()['schedule']`
and `input_schedule_observe()` retain the latest receipt; terminal native evidence
freezes while later observation time may advance.

`dispatched` proves only that all selected event callbacks and their final sync
returned. `device_queue_accepted` and `guest_consumed` remain `None`. A disabled
PS/2 device or a full FIFO may ignore input, and mouse output can include earlier
accumulated motion. Establish consumption, release and later drawing with
independent guest memory, IRQ/driver or display evidence. This is not a frame
boundary, exact CPU-cycle timing, a timed press, or a completed guest-frame ID.

The first actual VM stop cancels an unfired timer. A breakpoint, watchpoint or
DOS exit/TSR keeps its original stop result; the scheduler never continues to
reach its deadline. A pending stop or an equal/already-reached owned clock-budget
deadline wins over input, independent of timer insertion order. In that case
`state='cancelled'`, `dispatch_ns=None` and `requires_resolution=True`: the
Python edges remain pending, and another run or queue mutation is refused until
the caller explicitly chooses one of these actions:

- Call `input_schedule(new_delta_ns)` to reschedule the same pending batch from
  the current stopped time under a new token, then choose another bounded run.
- Call `input_cancel_pending()` to prove native disarm and discard only the
  unsent transitions. This also works before the first run.

After `dispatched`, an owned hold still needs `keyboard.key_up(lease)` or
`mouse_button_up(lease)` and an explicit run to dispatch that release. The
release can have its own `input_schedule(...)`. Cancelling a queued release
retains the previously dispatched hold; cancellation never synthesizes a
release. A second edge for the same mouse button in one scheduled batch is
refused because one final mouse sync cannot represent both press and release.

| Python | Retained JSON method | Saved-script operation |
| --- | --- | --- |
| `input_schedule(delta_ns)` | `debug-input-schedule` | `input-schedule` |
| `input_schedule_observe()` | `debug-input-schedule-observe` | `input-schedule-observe` |
| `input_schedule_retrace(edge='enter', timeout_ms=1000)` | `debug-input-schedule-retrace` | `input-schedule-retrace` |
| `input_cancel_pending()` | `debug-input-cancel-pending` | `input-cancel-pending` |

For an already queued batch in the retained server:

```json
{"method":"debug-input-schedule","params":{"run":"RETURNED_RUN","delta_ns":5000000}}
{"method":"debug-clock-advance","params":{"run":"RETURNED_RUN","delta_ns":20000000,"timeout_ms":3000}}
{"method":"debug-input-schedule-observe","params":{"run":"RETURNED_RUN"}}
```

A saved script can queue, arm and inspect one attempt:

```json
{
  "format": "fdisbull-script-1",
  "backend": "qemu-dos",
  "steps": [
    {"op": "keyboard.key-down", "key": "a", "as": "held"},
    {"op": "input-schedule", "delta_ns": 5000000},
    {"op": "clock-advance", "delta_ns": 20000000, "timeout_ms": 3000},
    {"op": "input-schedule-observe", "as": "delivery"}
  ]
}
```

Inspect the script result before choosing reschedule, cancellation or release;
the example leaves a dispatched hold owned. Script capability/argument checks
precede earlier mutations, and scheduled execution shares the host deadline
through stop reconciliation and persistence. Failure after a script arms a
batch closes the owned VM, including when its pending edges came from an earlier
call. Saved receipts survive project reopening as history; they do not reconnect
a timer or live input owner.

Native API 1 accepts one batch of 1..256 events, with a delay of
1..60,000,000,000 ns without signed-clock overflow. Relative X/Y values remain
bounded to -32767..32767; only left/middle/right buttons are admitted, at most
one edge per button. The machine still has at most 64 active input leases.
An armed or interrupted batch cannot be appended to. Process-lifetime token
history permits 4096 successful arms; exhaustion requires a fresh VM. The
callback revalidates handler identity, the legacy input queue, earlier unsynced
events and safe mouse arithmetic before emitting any event.

Reset, epoch/profile loss or an unsupported runstate invalidates the scheduler;
migration stays blocked for the process lifetime after its first successful
arm. Uncertain arm, cancellation, dispatch, deadline reconciliation or evidence
persistence closes the VM without replay. `timed_input=False`,
`guest_time_control=False` and `completed_guest_frames=False` remain explicit:
legacy `guest_ms`, timed text, frame presses and pixel/INT33 semantics are
not supplied by this batch scheduler. Separate extensions supply one timed
keyboard chord, bounded US-layout text or a physical mouse-button pair.
The separate opt-in [host clock controller](DOS_QEMU_TIMING.md)
preserves these first-stop, explicit-resolution and unknown-consumption rules.

### Queue one timed keyboard chord

The optional sixth [native keyboard-press patch](../native/qemu-keyboard-press/README.md)
adds `virtual_keyboard_press` on the explicit virtual profile. The existing
`keyboard_press` / `keyboard.press`, `debug-keyboard-press` and saved-script
`keyboard.press` routes passively arm one chord with zero to three modifiers.
Native callbacks space modifier edges by 2 ms and hold the main key for the
requested 1..1000 ms, deriving every next deadline from the preceding actual
callback. `gap_ms` is validated and recorded but has no effect for one press.

The first stop cancels the undelivered suffix. Receipts retain the delivered
prefix and owned held leases; cancelling the suffix never releases those holds.
A partially delivered chord cannot be replayed or converted into a batch.
Explicitly cancel pending steps, then explicitly release retained leases.
See [the workflow and recovery contract](DOS_QEMU_TIMING.md#queue-one-timed-keyboard-press).
Coordinate clicks and full DOSBox input parity remain unqualified.

### Queue bounded US-layout text

The optional seventh [native keyboard-type patch](../native/qemu-keyboard-type/README.md)
adds `virtual_keyboard_type`. Use the existing `keyboard_type` / `keyboard.type`,
JSON `debug-keyboard-type` or script `keyboard.type` with 1..64 printable ASCII
characters, Enter (CR or LF) and Tab. CRLF produces two Enter chords. Uppercase
and shifted punctuation use a fresh Shift chord for each character. The caller
must establish the guest's US layout and lock state independently.

The whole string validates before one passive stopped arm. Later characters
start `gap_ms + 2 ms` after the preceding final release, using actual callback
times; there is no trailing gap. Receipts preserve each character index, unique
key lifetime, assigned deadline and delivered prefix. An early stop cancels the
suffix and retains delivered holds for explicit cancellation and release.
Future reservations do not occupy active held-key slots. Legal maximum timing
can exceed the 60-second clock-advance bound; execution is never split or
resumed automatically. See the [text workflow](DOS_QEMU_TIMING.md#queue-bounded-us-layout-text).

### Queue one timed physical mouse click

The optional eighth [native mouse-click patch](../native/qemu-mouse-click/README.md)
follows the exact seven earlier patches and adds `virtual_mouse_click`. Use
`mouse_button_click(button='left', *, hold_ms=80)`, JSON
`debug-mouse-button-click` or script `mouse.button-click`. Require the explicit
virtual clock and discovered native clock/input/mouse-click commands; precise
retrace is unnecessary. Seven-patch builds refuse this helper while preserving
their existing physical input and keyboard capabilities.

Admit only exact left/middle/right names and strict integer holds of 1..1000 ms.
The owner must be stopped with an empty owned queue, no owned held leases,
no bound schedule and no caller-owned project transaction. One passive arm
prepares two separately synchronized batches: down after 2 ms, up `hold_ms`
after the actual down callback. Choose a later bounded run, clock advance or
one explicit `clock_sync_step()`; arming never executes, rebases or replays.

The `click` receipt preserves its two-step plan, delivered prefix and individual
deadlines, dispatch times and lateness. An interruption cancels the suffix and
can retain a delivered down despite top-level `dispatch_ns=None`. Another run
or new/converted schedule refuses until `input_cancel_pending()` discards the
suffix; inspect leases, explicitly call `mouse_button_up(lease)` for a retained
hold, then choose execution. Cancellation does not synthesize a release.

No movement is requested, but prior native mouse accumulators and external
button state can affect packets. Disabled/remote devices or full queues do not
establish delivery. FIFO acceptance, arbitrary guest consumption, cursor
position and INT33 remain unknown. There is no `GuestMouse` facade or legacy
`DebugSession` stub; `click(x, y)`, `debug-click`, `click-frame` and
`input.mouse.click` retain their coordinate/frame contracts and native refusal.
General timing, absolute mouse, guest-time and completed-frame flags stay false;
all 127 promotion qualifications stay open. See the
[click and explicit sync workflow](DOS_QEMU_TIMING.md#queue-one-timed-physical-mouse-click).

### Schedule input at a modeled retrace edge

The separate fifth [native retrace-input patch](../native/qemu-input-retrace/README.md)
combines this model with the existing input timer. Under
`retrace_input_schedule`, `input_schedule_retrace()` passively arms the pending
batch for the strictly next entry or exit. Its callback validates the original
device/generation and absolute window before delivery. Timing changes or a
missed window cancel for explicit resolution. Execution must be explicitly
allowed beyond the target; an equal clock-budget deadline wins over input.
See [the workflow and receipt contract](DOS_QEMU_TIMING.md#schedule-input-at-the-next-modeled-retrace-edge).

### Observe the declared VGA retrace model

Select `qemu_clock='virtual', qemu_retrace='precise'` in Python or retained
JSON launch, or `--qemu-clock virtual --qemu-retrace precise` on the CLI.
`Project.machine` takes `clock_profile='virtual', retrace_profile='precise'`.
The default retrace profile is `standard`. The precise profile requires the
[optional native retrace extension](../native/qemu-retrace/README.md) after
the exact clock, media and input patches, a fresh paused PC boot and one TCG
CPU. It selects standard PCI VGA with QEMU's precise retrace algorithm and
the explicit `qemu-vga-precise-fdisbull-v1` model.

`capabilities['retrace_observation']` admits the observation API; it does not
promise that the current guest timing is supported. Firmware has not programmed
valid timing at launch, and later modes can leave the supported subset.

| Python | Retained JSON method | Saved-script operation |
| --- | --- | --- |
| `retrace_observe(timeout_ms=1000)` | `debug-retrace-observe` | `retrace-observe` |

```python
observation = debug.retrace_observe(timeout_ms=1000)
if observation['phase_supported']:
    vertical_retrace = observation['phase']['vertical-retrace']
    generation = observation['timing_generation']
else:
    reason = observation['unsupported_reason']
```

A `fdisbull-retrace-observation-1` receipt binds the run, host/native clock
epochs, canonical VGA device, console/head, model and monotone timing generation.
It retains the raw model inputs, cached integer timing, observed virtual
nanoseconds, phase when supported, and stable before/after clock samples.
The native query neither reads the guest VGA status port nor resets its
attribute-controller flip-flop. It does not run a CPU, wait for an edge, refresh
pixels or change the clock. Admission pins the device and blocks migration;
reset or ownership loss requires a fresh machine.

The opt-in model updates cached timing at actual guest register-write boundaries,
including vertical-retrace start (`CR10`) and VBE/effective sequencer changes.
Its generation records relevant changes even when a guest changes A to B and
back to A between host observations. Equal final registers therefore do not
imply an unchanged timing history. Ordinary unselected QEMU behavior is retained.

Phase support is deliberately limited to the model's initialized legacy VGA
timing with VBE disabled, positive integer periods and nonwrapped in-range
horizontal and vertical retrace intervals. An uninitialized cache, enabled
VBE, or unsupported timing returns `phase_supported=False` and an explicit
reason, with no invented phase; this is a valid observation and keeps the
machine available. Malformed evidence, device/epoch replacement, regressing
generation/time or changed timing under the same generation closes the owner.

`vertical-retrace` describes the selected QEMU model's sync interval, not the
entire vertical blank interval. Its synthesized status bits do not establish
visible scanout, completed guest drawing, input consumption or hardware-cycle
accuracy. The generation describes timing inputs and eligibility, not all
palette, address, pixel-format or application-mode changes. A current receipt
cannot assign retrace phase or generation to an older renderer publication.
Retained display captures still use their own renderer window/update identity.

Each request has one absolute host deadline from lock admission through clock
brackets and event persistence. Script capability and literal timeout checks
precede earlier mutations. A late synchronous journal write can have committed
before the deadline check fails; `error.result` retains the observed receipt.
An uncertain native read closes the machine without retry or replay. This
observation stays passive. The separate bounded wait below composes it with
one explicit native budget.

### Synchronize host time or wait for a retrace transition

The explicit virtual-clock profile advertises `host_clock_sync`. Use
`clock_sync_start()` to bind persistent host/native anchors,
`clock_sync_observe()` to inspect drift, `clock_sync_step()` to choose one
bounded correction, and `clock_sync_stop()` to stop future corrections.
The fixed 1:1 mapping counts all host elapsed time since start, including
helper work, debugger pauses and caller idle time. Actual native progress
and previous overshoot are subtracted through the current virtual sample.

One step freezes its target. A bounded deficit uses one native advance;
a bounded lead uses one host sleep while the guest stays stopped. Excessive
drift latches desynchronization. Earlier or coincident debugger/process stops
are retained and interrupt the mapping. Explicit stop/start chooses a new
origin; no operation silently rebases, chases a moving target or replays input.
Normal execution methods do not implicitly run this controller.

With the additional precise profile, `retrace_wait(edge='enter'|'exit')`
plans the strictly next modeled transition and uses one native clock budget.
Success requires unchanged run/epochs/device/model/timing generation,
an ordinary timer stop and the exact absolute entry or exit window.
Unsupported timing, a changed model, a missed window and another observed
stop remain distinct outcomes. No retry establishes a later edge as the
original target. This does not establish full VBlank or completed guest frames.

Both controls have retained JSON and saved-script routes, capability and
literal-parameter preflight, a single host deadline, and persisted evidence
that survives reopening as history. The complete APIs, parameters, state
transitions and examples are in [native timing synchronization](DOS_QEMU_TIMING.md).

### Capture a stopped display surface

`capture_surface(name)` / `debug-capture-surface` / script `capture-surface`
stores PNG bytes with a unique capture ID, run identity, dimensions, SHA-256,
selected-CPU registers and before/after clock observations. The entire bracket
holds the owned machine lock with QEMU stopped. `screenshot()` uses the same
capture path and retains optional grid annotation.

The metadata source is `qemu_display_surface`; `completed_guest_frame` and
`guest_frame_id` are `None`. A capture can show a half-drawn guest scene. A new
capture ID does not establish a new guest frame or input consumption. Standard
clock capture reports `clock_stability='not_observable'`; the instruction
profile can establish only an unchanged observed instruction counter. The
virtual profile checks both the direct virtual clock and instruction counter.
A changed stopped CPU/clock bracket closes the VM and refuses the capture.
Existing DOSBox frame-coherence consumers cannot accept this surface as a
`last_completed_guest_frame`.

Native evidence for this path uses QEMU 10.0.13 and FreeDOS 1.4, with independent
authored BIOS/IRQ programs. It separates queued input, QMP acceptance, BIOS or
IRQ consumption, and the program's later VGA drawing boundary. It does not
qualify arbitrary DOS drivers, QEMM/DESQview, Windows, audio or a real game.

Primary implementation references are QEMU's
[instruction-counting design](https://www.qemu.org/docs/master/devel/tcg-icount.html),
[icount invocation options](https://www.qemu.org/docs/master/system/invocation.html),
and [QMP input, screendump and replay commands](https://www.qemu.org/docs/master/interop/qemu-qmp-ref.html).
Those moving upstream manuals describe a newer development version; the
handoff records the actual installed version used for native acceptance.

### Retain completed renderer updates and audio output

The optional [media extension](../native/qemu-media/README.md) adds explicit
observation windows to the native virtual-clock runtime. Its patch applies
after the current clock patch. The default runtime remains unchanged. Enable
the PC-speaker device only when requested:

```python
with project.debugger(qemu, game_directory, backend='qemu-dos',
                      dos_boot_image=dos_disk, dos_mcopy=mcopy,
                      qemu_transport='pipe', qemu_firmware=firmware,
                      qemu_clock='virtual', qemu_audio='pc-speaker') as debug:
    # At the caller-selected stopped point; start never runs the program.
    display = debug.display_start(period_ns=20_000_000)
    audio = debug.audio_start(max_frames=320_000)
    result = debug.clock_advance(100_000_000, timeout_ms=5000)
    # An earlier debugger/process stop can precede any media production.
    observed = debug.display_observe()
    if observed['updates']:
        image = debug.capture_display('observed.png', after_update=0)
    debug.audio_stop()
    sound = debug.capture_audio('observed.wav')
    debug.display_stop()
```

These calls also have retained JSON routes `debug-display-start`,
`debug-display-observe`, `debug-display-stop`, `debug-capture-display`,
`debug-audio-start`, `debug-audio-observe`, `debug-audio-stop` and
`debug-capture-audio`. Saved scripts use the same names without `debug-`.
The raw `project.machine()` route accepts `audio_profile='pc-speaker'` with
`clock_profile='virtual'`. Audio defaults to `off`.

Renderer publications own an immutable RGB copy taken after the synchronous
standard VGA renderer returns. Native virtual timers provide the explicitly
chosen observation cadence; the period is not a guest refresh rate. Only the
latest publication is retained, identified by its window token and update ID,
with dimensions, publication time and observed age. `capture_display()` reads
those pixels without refreshing. `after_update` refuses stale IDs in the same
window and never waits or continues automatically. Capture stays bounded to
16 MiB of RGB. A later `capture_surface()` refresh does not alter these owned
pixels.

A completed renderer update can itself show half-finished guest drawing.
`completed_renderer_update=True` is therefore separate from
`completed_guest_frame=None` and `guest_frame_id=None`. The observer does not
provide VGA scanout, VBlank, a full guest mode epoch or application readiness.
The native witness explicitly demonstrates a half-drawn published image.

Audio capture observes complete PCM frames from QEMU's mixer callback. The
explicit PC-speaker profile uses the `none` host driver and 32,000 Hz, mono,
unsigned 8-bit samples. The WAV receipt retains contiguous sample ranges and
their callback delivery times, plus stopped clock brackets. Device buffers
can contain earlier generated samples; callback time is not each sample's
onset. Inactive intervals produce no synthetic silence. WAV sample duration
must not be interpreted as elapsed guest time or device queue completion.

Capacity is 1..1,920,000 frames and at most 8192 callback records. Overflow is
reported with a dropped-frame count and refuses a misleading complete WAV.
Stop the old window and explicitly start another. Stop is idempotent, retains
the captured prefix and does not flush the mixer. New windows start empty.
Sound Blaster, FM/OPL and other devices remain separate qualification work.

Both windows bind to the owned machine and native clock epoch. Reset or
incompatible state invalidates them; generic migration after use is blocked.
The instrumented DOS checkpoint route above explicitly restores retained
observer state under new ownership. Passive
queries and exports do not execute the guest. Shared script deadlines include
lock admission and persistence; an uncertain start/stop closes the machine.
The caller advances execution through existing controls or an explicit
[host clock-sync step](DOS_QEMU_TIMING.md). That controller does not qualify
audio resampling, device queue drain or playback alignment.

### Probe sparse pixels from one retained publication

The optional ninth [display-probe extension](../native/qemu-display-probe/README.md)
adds `renderer_probe` independently of `renderer_capture`. Inspect that capability
before using `display_probe(points, *, window=None, update_id=None, timeout_ms=1000)`.
It requires the explicit virtual clock and all native clock/display commands plus
`x-fdisbull-probe-display`. An eight-layer executable keeps its existing display
and input operations and refuses the new helper.

```python
publication = debug.display_observe()
if publication['updates']:
    probe = debug.display_probe(
        [[0, 0], [publication['width'] - 1, publication['height'] - 1]],
        window=publication['window'], update_id=publication['update_id'],
        timeout_ms=1000)
    # Ordered samples use coordinates in this retained renderer image.
    colors = [pixel['rgb'] for pixel in probe['pixels']]
```

The point list contains zero through 256 two-coordinate points. Coordinates are
strict integers in `0..8191`, then checked against the retained dimensions;
booleans are rejected. Order and duplicates are preserved. An empty list still
requires a retained publication and returns its identity with no samples.
Supply both expected `window` and positive uint64 `update_id`, or leave both
unset to select the current publication under the owned lock. Expectations
require exact equality: update IDs restart in a new window, so an ID alone is
not accepted. A stale expectation or outside point refuses before native sampling
and leaves the valid stopped owner available.

The public result is `fdisbull-renderer-probe-1`. It retains the ordinary renderer
window metadata, requested `points`, ordered `pixels` with `{x, y, rgb}`, before/
after clocks and the full native response. `pixel_format` is `RGB24` and
`coordinate_domain` is `retained_renderer_pixels`. The probe reads the existing
private native RGB copy. It creates no image file or screenshot artifact and
does not refresh the display, run the guest, send input, wait, or synchronize
time. A palette, VRAM or mode change can therefore appear in `capture_surface()`
while this probe still returns the older retained publication. A stopped observer
can retain its original dimensions after a guest mode change.

Use JSON `debug-display-probe` or saved-script `display-probe` with the same
parameters. Script references can supply the identity or individual coordinates;
every visible literal validates before earlier script effects, and resolved
values validate again before dispatch. Direct argument/signature validation
precedes lock admission. One host allowance, default 1000 ms and bounded to
1..600000 ms, includes admission, native queries, clock brackets and journal
persistence, intersecting tighter caller/script bounds. Caller-owned project
transactions are refused. Malformed native evidence, failed persistence or an
expired accepted result closes ownership without replay; available evidence is
retained on `error.result`, including a journal that committed before expiry.

Successful `machine-display-probe` events survive project reopening as evidence;
they do not restore a live observer. At most the previous probe's 256 sampled
coordinates are cached for overlap contradiction checks. No full-raster hash is
invented for a sparse read; `capture_display()` remains the full-image hash route.

This operation does not implement legacy `frame_probe`/`video.probe`, whose
consumers require mode/frame/state identities, or coordinate `click`/`click-frame`.
It reports no `mode_id`, `frame_id` or `state_revision`. Completed guest drawing,
VBlank, cursor location, INT33 mapping, application readiness and input consumption
remain unknown. `completed_guest_frame` and `guest_frame_id` remain `None`; all
127 default-promotion qualifications remain open.

### Observe current and published VGA configuration

The optional tenth [VGA configuration extension](../native/qemu-vga-configuration/README.md)
adds `vga_configuration_observe(*, timeout_ms=1000)`, JSON
`debug-vga-configuration` and saved-script `vga-configuration`. Check the separate
`vga_configuration` capability. Use the existing explicit
`qemu_clock='virtual', qemu_retrace='precise'` profile with all native clock,
display, retrace and configuration commands. A nine-layer executable retains
its existing operations and refuses this new one.

```python
configuration = debug.vga_configuration_observe()
current = configuration['current']
published = configuration['published']
if published is not None:
    same_configuration = configuration['configuration_matches']
    publication = configuration['display']
```

The `fdisbull-vga-configuration-1` receipt atomically separates the current
configuration from the configuration observed at the retained renderer
publication. Each snapshot identifies the native epoch, model, exact VGA
device/console/head, observation time, positive `configuration_generation`,
bounded `raw` vector and `configuration_sha256`. The hash covers canonical raw
JSON only; it is neither an image hash nor a mode identifier. A-to-B-to-A changes
can restore the hash while increasing the generation twice. Equality checks
therefore compare generations after verifying epoch, device and raw consistency.

The model conservatively tracks the stored legacy and VBE sequencers, graphics
and CRTC registers, attribute mode/panning/color controls, display enable,
miscellaneous/feature output, VBE words and derived origin/pitch/bank/size,
DAC-width interpretation and framebuffer byte order. It excludes palette
contents, VRAM/fonts, ordinary selectors and flip-flops, renderer caches and
surface dimensions. The [native contract](../native/qemu-vga-configuration/README.md#exact-tracked-vector)
lists every field and bound. Equal configuration can accompany different
pixels; equal dimensions can accompany different configuration.

The lifetime generation advances after complete effective mutators, including
protected CR7, VBE normalization, QEXT and QOM byte-order changes. No-op and
ignored writes do not advance it. Reset always advances it; overflow or an
unsupported restore invalidates identity. Querying an uncommitted raw change
refuses instead of repairing its missing history. Windows do not reset the
generation.

Publication capture records the selected VGA directly beside the retained RGB
copy, even before the first public configuration query. Stopping preserves that
stamp; starting a new empty window clears its public publication. Without an
image, `published` and `configuration_matches` are `None`. The host retains only
one current snapshot and the last actual publication stamp to reject regressing
or contradictory history across empty windows. Historical reads do not replace
the current frontier. No stamp is synthesized from current registers.

`publication_configuration_semantics` is
`configuration_observed_at_publication`. A renderer callback can retain older
surface pixels during a transient invalid text layout or blanking. Even a true
`configuration_matches` does not establish that every pixel was drawn under that
configuration. `raster_coherence`, `completed_guest_frame`, `guest_frame_id` and
`cursor_mapping` remain `None`. Publication dimensions still describe the
retained image; the operation does not infer current dimensions, a BIOS mode,
INT33 coordinates or input readiness.

This is a stopped read: it does not execute, render, read guest I/O/memory,
sleep, wait, send input, export images or call clock auto-sync. Direct signature
and timeout validation precede locking/I/O. Scripts preflight capabilities,
visible literals and transactions before earlier effects, then validate resolved
values before deadline clamping. The strict integer host allowance is
1..600000 ms, default 1000, and covers lock admission, native reads, unchanged
clock brackets, validation, journal persistence and final return. Tighter
caller/script bounds continue to apply. Caller-owned transactions are refused.

Malformed, contradictory, control, persistence or late-result failures close
ownership without retry and retain available native evidence and clock brackets
on `error.result`. Successful `machine-vga-configuration-observe` events survive
project reopening as history, without recreating ownership. Generic frame
probes, coordinate/frame clicks and scenes remain unqualified, and all 127
default-promotion qualifications remain open.

### Move with a declared image-to-relative scale

The optional eleventh [display-motion extension](../native/qemu-display-motion/README.md)
adds the separate `mapped_mouse_motion` capability and
`mouse_move_mapped(dx_pixels, dy_pixels, *, counts_per_pixel, window, update_id,
configuration_generation, timeout_ms=1000)`. JSON uses
`debug-mouse-move-mapped`; saved scripts use `mouse.move-mapped`. Require the
explicit virtual/precise profiles and all native input, clock, display, retrace,
VGA-configuration and display-motion commands. A ten-layer executable retains
its earlier operations and refuses this new capability.

This operation converts a caller-declared image-space displacement to relative
input units. It has no pointer origin or absolute destination. The caller
supplies a scale for the selected guest driver/application; the operation does
not discover or verify that scale. Positive image x points right and positive y
points down. `counts_per_pixel` is exactly an `x`/`y` dictionary, with each value
a list `[signed_numerator, positive_denominator]`. Its units are **QEMU REL input
events per retained-image pixel**. QEMU negates relative y when forming the
PS/2 wire displacement, so these are not raw packet y counts.

For example, after explicitly obtaining a renderer publication and stopping
its observer, a caller with a declared scale can arm one movement:

```python
debug.display_stop()
view = debug.vga_configuration_observe()
motion = debug.mouse_move_mapped(
    12, -6,
    counts_per_pixel={'x': [1, 2], 'y': [1, 3]},
    window=view['display']['window'],
    update_id=view['display']['update_id'],
    configuration_generation=view['current']['configuration_generation'],
)
# The exact relative event values are x=6 and y=-2. Arming did not run the VM.
stop = debug.clock_advance(4_000_000)
delivery = stop['input_delivery']
```

Both pixel components must be strict integers in −8191..8191, with a nonzero
pair. Numerators are nonzero integers in −32767..32767; denominators are integers
in 1..32767. Every transformed axis must divide exactly and fit −127..127.
There is no rounding, clipping, splitting or implicit retry. Each declared
displacement must also be smaller in magnitude than its retained image extent.
That bounds the displacement, not an endpoint. This count limit does not promise
one packet: prior accumulators, disabled/remote mode and FIFO capacity remain
unobserved.

Admission requires an owned project outside caller transactions, an empty
physical queue, no owned held leases and no other bound schedule. The retained
window must already be explicitly **stopped and nonempty**. The supplied window,
update ID and configuration generation must match a fresh observation, and its
current and published VGA configurations must agree. The operation does not
stop the observer, refresh pixels or manufacture a publication. A running
observer can republish as often as every 1 ms, so it cannot serve as this stable
publication anchor for a callback due 2 ms later.

After host validation, native arm admission atomically checks the exact epoch,
device/model, current time, publication token/update/time/dimensions and matching
configuration generation. One passive attempt schedules nonzero x followed by
nonzero y, then one synchronization callback, after 2 ms. The caller chooses
`run`, `clock_advance` or an existing `clock_sync_step` to execute it; this helper
never starts timing auto-sync itself.

Immediately before the first relative callback, native code checks the binding
again under QEMU's global lock. A configuration-generation increase, including
A-to-B-to-A, cancels with `display-motion-configuration-changed`. With unchanged
configuration, a replaced publication/window or resumed observation cancels
with `display-motion-publication-changed`. Stop requests and equal/reached
clock budgets take precedence before this check. Identity regression, changed
raw values under one generation or contradictory publication stamps fail
ownership. No motion callback starts after a failed binding check.

The top-level receipt remains `fdisbull-qemu-scheduled-input-1`. Its mutually
exclusive `motion` descriptor uses `fdisbull-mapped-mouse-motion-1`, preserving
the pixel request, rational scale, derived `dx`/`dy`, original full VGA receipt,
frozen `native_arm`, optional `native_check` and `binding_verified`. The check is
absent when an earlier stop/budget wins. Terminal evidence never refreshes on
query. A valid callback cancellation retains the unsent records and requires
`input_cancel_pending()` before another attempt. Generic `input_schedule()` and
`input_schedule_retrace()` cannot remove its binding. A fresh mapped request
requires a fresh observation and caller expectations.

`binding_verified=True` proves the publication/configuration checks and selected
native callbacks plus sync completed. It does not prove current-image freshness:
palette, VRAM, fonts and application state can change without advancing this
configuration generation, and an old stopped publication has no implicit age
limit. `guest_pixel_displacement`, `guest_pointer_position`, `mapping_verified`,
`raster_coherence` and `target_reached` remain `None`, as do top-level
`device_queue_accepted` and `guest_consumed`. No button events are requested;
pre-existing guest/device button state can still make a motion act as a drag.

Strict direct signatures and every visible script literal validate before
locking or earlier script effects, including independently known axis arithmetic
when another axis is a result reference. Resolved values validate before timeout
clamping. One shrinking 1..600000 ms host allowance, default 1000, covers
admission, observations, native arm, validation, persistence and return. A known
pre-arm binding mismatch leaves a valid stopped owner usable. An uncertain arm,
malformed evidence, failed persistence or late accepted result closes ownership
with available evidence and no replay. Journal reopening restores history only.

Large multi-step motion reports can exceed the normal JSON reply budget and
return an `fdisbull-output-ref-1` artifact reference. Read or export that saved
response with the existing output routes; delivery compaction is not permission
to repeat the input operation.

The authored native witness independently separates IRQ12 packet receipt,
application pointer commit and drawing, with explicit x/y gains and a deliberately
wrong declared scale. Those controlled observations do not qualify arbitrary
INT33 drivers or games. Legacy coordinate clicks, frame probes and scene
consumers retain their existing requirements. Broad `timed_input`,
`absolute_mouse`, `guest_time_control` and `completed_guest_frames` remain false;
DOSBox remains the default and all 127 promotion qualifications remain open.

## What the first slice does and does not qualify

The native tests use independent authored boot and DOS-service fixtures. They
check nonzero `CS:IP` versus linear-PC identity, execution and data controls,
physical/virtual reads, guarded edits, memory searches, stored traces and PNGs,
bounded-run interruption followed by usable control, reopened artifacts, a
fresh machine, source isolation and process cleanup. The real DOS case calls
DOS interrupts and checks the probe's nonce, reported CPU state and VGA output.
It does not stand in for QEMM, DESQview, a game or Windows.

Native machine stops affect the machine's vCPUs. A vCPU is not a DOS task or
Windows thread. Runs are bounded by host time; instruction stepping follows
QEMU's debugger semantics and does not establish original-machine cycle timing.
Stored-surface PNG capture is distinct from the DOSBox completed-frame contract.

Native event searches cover the verified initial real-mode DOS module, not a
whole-program execution history, arbitrary driver mapping or unpacked original
entry discovery. Explicit stopped `memory-rule-tick` is available. The shared
`memory_rule_run(rule, *, ticks, interval_ms=100, timeout_ms=10000)` method supports the
explicit QEMU virtual-clock profile: its first tick is immediate, and each
subsequent interval uses a token-bound native virtual-clock budget in
nanoseconds under one host deadline. Each tick revalidates identity and mapping,
captures fresh values, uses a guarded write and journals its outcome. Any
nonordinary timer stop, including a breakpoint, watchpoint or guest exit
collision, ends the run without an extra tick or replay. This does not establish
generic `guest_ms`, cycle accuracy or real-time scheduling.

Native snapshots expose `base`, `ram` and inspection-only `execute` views.
The base view's caller-declared task label does not confer native task
ownership. With active layers or native task bindings, rules require an
explicit RAM-view snapshot bound to the selected registered native task and
its lifetime, backing, epoch and view generation. Rule-owned immutable RAM
overlays preserve authored RAM and fetch layers. A hook encountered during
an interval is dispatched once and stops the run without another tick.
Queued, held or scheduled input, active clock synchronization or budget, and
caller-owned transactions remain refused before execution. A changed task or
view refuses before its next edit. An old rule is stale after checkpoint
restore; take a fresh capture and create a new rule.

Ten authored FreeDOS native cases passed locally: nine ordinary clock, public
route, hook and layer cases, plus one task-private IRQ case. The latter used an
explicit physical RAM view through A/B mode changes; actual guest mutation of
A's private value was followed by replacement of the rule's prior overlay,
without changing B or shared base. Its cold restore preserved IRQ state, hooks
and layers, refused the old rule, and admitted a fresh rule above the retained
overlay. The host contract suite passed 823 checks, the focused view guard
selection passed 12, and the retained actual DOSBox witness passed once. The
fresh bounded broader regression passed 1,159 tests across 72 files with no
failures, errors or skips, including the existing 19 native scheduler and IRQ
preservation cases. See `tests/test_qemu_memory_rules.py`,
`tests/test_qemu_memory_rules_public.py`, `tests/test_qemu_memory_rules_native.py`
and `tests/test_qemu_memory_rule_views_native.py`. These bounded results do not
promote any of the 127 surfaces or seven campaigns; DOSBox remains the default.

Hostcalls and UDL/UIL block services remain a later slice. The earlier lab's
custom opcodes and plugins are not enabled by this launcher, and experimental
`FDB_HOSTCALL_*`/`FDB_LAYER_*` environment selectors are removed from the child.
The layer slice must preserve separate fetch/data views, selection precedence,
translation invalidation and declared host-effect ownership before it can
replace the existing DOSBox machinery.

## Run the migration gates

The source coverage gate derives the current DOSBox API from the code and
compares it with the packaged ledger. New methods must acquire a slice and
disposition. Test names in the ledger describe required witnesses; they are
not automatically reported as passed.

```sh
python -m pytest -q tests/test_dos_migration.py tests/test_qemu_dos.py tests/test_qemu_pipe.py

FDISBULL_QEMU_DOS=/path/to/qemu-system-x86_64 \
FDISBULL_QEMU_DOS_FIRMWARE=/path/to/qemu/share/qemu \
FDISBULL_REQUIRE_QEMU_DOS=1 \
python -m pytest -q tests/test_qemu_dos_native.py tests/test_qemu_doctor.py
```

The independent FreeDOS case additionally accepts
`FDISBULL_QEMU_DOS_BOOT_IMAGE` and `FDISBULL_QEMU_DOS_MCOPY`. Set
`FDISBULL_REQUIRE_QEMU_DOS_OS=1` to require those inputs and refuse an OS-test
skip. The test edits a private copy to install its authored probe; no vendor
image or runtime state belongs in Git or the wheel. A build without stored
display support cannot pass the complete graphics/native acceptance lane.

For the process slice, run `tests/test_qemu_dos_process_native.py` and
`tests/test_qemu_dos_process_lifecycle.py` with those same required inputs and
`NASM=/path/to/nasm`. NASM assembles independent test programs; production uses
the packaged authored helper and needs no assembler. The helper's readable
source/template equality is checked by `tests/test_dos_process_helper.py`
with `FDISBULL_NASM=/path/to/nasm` and
`FDISBULL_REQUIRE_DOS_HELPER_ASSEMBLY=1`.

The trace slice adds `tests/test_qemu_dos_trace_native.py` and
`tests/test_qemu_trace_semantics_native.py` with the same required native
inputs. Source/persistence and protocol checks are separate from these actual
guest witnesses. Consult the handoff log for the exact run results and scope.

The clock/input slice adds `tests/test_qemu_io_native.py` using the same required
QEMU/FreeDOS/mcopy/NASM inputs. It covers physical consumption and release,
pre/post-draw pixels, early-stop races, clock domains, stale leases, public
JSON/scripts and terminal failure cleanup. `tests/test_qemu_clock.py`,
`tests/test_qemu_input.py`, `tests/test_qemu_surface.py` and
`tests/test_qemu_io_public.py` cover malformed receipts and public preflight.

The scheduling slice adds `tests/test_qemu_input_schedule.py` for hostile
receipts, ownership, public preflight, shared deadlines and terminal failure
cleanup, plus `tests/test_qemu_input_schedule_native.py` for actual timer
callbacks and independent guest IRQ1/IRQ12 observations. The native witnesses
also cover HLT wakeup, earlier stops, equal/later budget cutoffs, held release,
reset, DOS exit/TSR, renderer output, retained JSON/scripts and reopened evidence.
Use `FDISBULL_QEMU_CLOCK` for the separately prepared clock + media + input
executable and `FDISBULL_REQUIRE_QEMU_CLOCK=1`, with the required DOS boot image,
mcopy, firmware and NASM inputs described above. This selection never replaces
the stock `FDISBULL_QEMU_DOS` lane. The handoff records actual results; these
witness references do not close any of the 127 default-switch qualifications.

Rehearse the retained path with a separate original DOS program project:

```sh
fdisbull debug /private/game.fdb --backend dosbox \
  --executable /path/to/patched/dosbox-x --game-dir /private/game
```

After migration, keep this explicit selector, its backend preparation route,
and regression tests. Default promotion requires each remaining surface's
native evidence, real compatibility campaigns, cold restore and a fallback
rehearsal. Retaining DOSBox is part of the migration contract even after those
gates pass.
