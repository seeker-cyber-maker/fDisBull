# DOSBox-X to QEMU: migration plan and handoff log

## Migration plan

Transfer the existing DOS capabilities in dependency order. Keep `dosbox` as
the default until native parity is qualified, and keep both `dosbox` and
`dosbox-qemu` explicitly selectable after promotion. Never replay an uncertain
operation automatically in another backend. The authoritative surface mapping
is [the capability inventory](DOSBOX_QEMU_CAPABILITY_INVENTORY.md), backed by
`src/fdisbull/data/dos-migration.json` and source-derived coverage tests.

| Slice | Deliverable | Acceptance boundary |
| --- | --- | --- |
| 1. Core | Owned QEMU launch/stop, isolated disk, CPU/RAM controls, break/watchpoints, traces, stored display capture | Native execution, bounded failure, source isolation and process cleanup |
| 2. DOS process and drivers | Real DOS COM/MZ loading, loaded-source and PSP identity, termination versus residency, explicit driver observations | Real DOS loader and independent COM/MZ/TSR witnesses; no fabricated PSP or inferred successful driver load |
| 3. Trace and events | Source-bound traces, execution-event searches and entry/transition predicates | Correct mapping across relocation, overlays and mode changes; completed versus attempted execution kept distinct |
| 4. Clock, media and input | Guest-time control, coherent frames, audio and physical input | Defined clocks and completed-frame evidence; no claim of cycle parity from a screenshot |
| 5. Checkpoints | Native save/restore, Anchor Stones and restore epochs | Cold reopen, complete machine/device state and explicit compatibility checks |
| 6. Layers and block services | RAM/fetch layers, priorities, hooks and UDL/UIL host services | Correct fetch/data views, invalidation, effect ownership, synchronization and fallback boundaries |
| 7. Histories | Rewind, deltas, frame history and comparative trials | Histories remain bound to the right source, machine, epoch and layer selection |
| 8. Workflows | Scenes, scripts, player and analysis consumers | Existing public workflows work through the native backend with explicit capability checks |
| 9. Qualification | Driver/game compatibility matrix, Windows scaling checks and fallback rehearsal | Every required surface has fresh evidence; retained DOSBox remains usable |

For each slice: identify the missing public behavior, add a deterministic
witness, implement a complete vertical path, run affected native and retained
DOSBox checks, update the inventory and this log, then publish the authored
changes to the existing draft MR. A test filename in the inventory is a required
witness, not a passing result. Record partial and unverified behavior explicitly.

## Potential difficulties to expect

| Difficulty | Consequence and intended check |
| --- | --- |
| File offsets versus loaded addresses | A raw disk offset, COM offset, MZ module offset and segmented PC are different identities. Derive mappings from the actual loader result and verify original bytes after declared MZ relocations. |
| DOS owns process creation | COM/MZ startup includes a PSP, environment, command tail, FCBs, stack and parent process. Use real DOS loader services and inspect the resulting state instead of synthesizing a plausible process. |
| MZ relocation and allocation | Entry CS:IP and SS:SP depend on the load segment; allocation can exceed file size. Test nonzero segments, multiple relocation entries, initialized data and uninitialized allocation separately. |
| Shell and environment differences | Boot disks differ in CONFIG/AUTOEXEC names, shell paths, drive letters and free space. Require an explicit preparation contract; do not silently rewrite a caller's original disk. |
| Exit versus TSR residency | Returning to a parent does not imply resident code, memory or interrupt hooks disappeared. Distinguish normal exit, INT 21h/AH=31h and INT 27h, with observed ownership and retained-range evidence. |
| Device drivers are not ordinary programs | CONFIG.SYS strategy/interrupt entry points and initialization precede the shell. Reuse explicit boot configurations and inspect driver chains; do not route SYS images through the COM/MZ launcher. |
| QEMM, DESQview and protected mode | Paging, V86 mode, banked EMS and task switching invalidate simplistic physical-address or process assumptions. Preserve unknown mappings and qualify these combinations separately. |
| Overlays and self-modification | A source-bound address can later hold different code. Bind mappings and observations to source identity and execution epoch; do not retain stale certainty. |
| Partial control operations | A timeout can occur after a command took effect. Bound operations, record their disposition and close an uncertain control channel; do not automatically retry memory writes or process starts. |
| Multiple clocks and host effects | CPU progress, PIT/IRQ timing, audio duration and Python wall time do not advance together. Later host services need an explicit clock and ownership contract, including cancellation and desynchronization policy. |
| Paused input and cross-channel ordering | Stock QEMU rejects paused physical input, and a successful paused send-key did not deliver in the native witness. Queue in the owner, dispatch at most once during GDB continue, and retain the original stop; acceptance is not consumption. |
| Instruction counting and idle time | Fixed icount can observe machine progress, but HLT timer warps advance virtual time separately. Never multiply the counter into a generic guest clock or promise an exact live count stop from replay-only commands. |
| Layer selection and translation caches | Changing executable overlays must invalidate translated blocks while preserving required data views and priority rules. Parallel timing-only execution must not duplicate visible effects. |
| Checkpoint portability | QEMU and DOSBox state formats are unrelated. QEMU snapshots also depend on executable, machine and device identities. Require native cold-restore tests rather than treating saved metadata as restored state. |
| Windows and additional architectures | SMP, threads, interrupts, memory ordering and architecture-specific traps make a DOS-only global stop insufficient. Keep machine, OS/process and target contracts separate. |
| Runtime and host variability | Firmware, QEMU feature selection, Unix socket restrictions and macOS behavior vary. Discover capabilities and record exact runtime evidence; a Linux pipe result does not qualify every host. |
| Workspace resets and publication | Scratch inputs and receipts can disappear between turns. Keep this authored log and source in GitLab, record private runtime provenance without uploading vendor images, and re-establish evidence after reset. |

## Current handoff

- Branch: `agent/qemu-sunset-284eb73c`.
- Draft integration MR: [!117](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/117).
- Stack parent: `agent/execution-event-search-284eb73c` / [!113](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/113).
- Restored baseline: `3b7ffedd848736174ad055b506bbbe44567ea6a2`.
- Latest implemented path: slice 4 machine-owned keyboard/PS2 input, explicit
  instruction-clock observations and stopped PNG/CPU/clock brackets, alongside
  the earlier source-bound real-mode COM/MZ traces and event searches.
- Takeover: `chat:54d0a46c7daf` recovered the unpublished slice-4 commit
  `6434474b0318bf9ee6d7d3d1b2ea094a3a81629d` from the previous checkout. The
  existing branch, originating handoff marker and stacked MR target are retained.
- Next gate: finish slice 4's generic virtual-clock read/advance and completed
  frame/audio boundaries before clock-dependent checkpoints, frame histories,
  click-to-event causality or Python media synchronization. These remain open;
  the available input/surface path does not qualify the full slice.
- Defaults and rollback: DOSBox remains the default; both DOSBox selectors stay
  available. Native default promotion and DOSBox removal are blocked.
- Publication: authored source and this maintained engineering log belong in the
  branch. Vendor images, game bytes, runtime databases and emulator states stay
  outside Git. Routine publication must not start hosted CI.
- Local mirror: the configured macOS `/Volumes/...` mirrors are not mounted in
  this Linux workspace; do not report them synchronized.

## Slice 2 acceptance plan

1. Boot a caller-supplied DOS image and execute a small authored loader through
   the actual command interpreter.
2. Load an original COM and an original relocated MZ through DOS, stop at their
   observed entry, and expose the real PSP, entry/stack registers and source map
   through the public debugger path.
3. Refuse a changed source, mismatched disk/profile, unsupported executable type
   or inconsistent loader report before claiming a bound process.
4. Exercise command-tail/environment handling, nonzero segments and DOS output
   with independent authored programs.
5. Separate normal termination from TSR residency and from termination of the
   emulator itself. Inspect resident ownership and interrupt-vector effects.
6. Preserve existing raw-disk debugging and DOSBox behavior, reopen persisted
   evidence, and test an isolated wheel when the public/package seams change.
7. State which real driver configurations and protected-mode cases remain
   unverified. Do not mark the entire slice complete from synthetic fixtures.

## Slice 3 acceptance plan

1. Preserve actual linear and segmented PCs and compare each observed source
   instruction with the original bytes after DOS relocation and startup writes.
2. Keep runtime byte hashes separate from canonical project-site hashes; compare
   independently launched COM/MZ programs at genuinely different load addresses.
3. Reuse existing register, address, mnemonic and transition predicates. Preserve
   user break/watchpoints, enforce one operation deadline, and refuse queued
   input before an earlier script step can mutate the guest.
4. Keep fault/REP stop intervals distinct from retired instructions and record
   the actual QEMU single-step mask without changing it.
5. Admit saved traces only against their unique ordered initial-entry receipt,
   source/version bytes, capture epoch and artifact receipt. Verify reopen and
   history queries after exit; reject contradictory or incomplete evidence.
6. Stop source binding at self-modification, allocation/epoch or mode changes.
   An unbound final runtime match remains an open source window and cannot
   narrow source-event absence. Live overlay rebinding needs a later contract.
7. Run finite affected-source, actual QEMU, retained DOSBox and isolated-wheel
   checks. Leave the default-switch gate closed for unqualified surfaces.

## Work log

### 2026-11-08 — takeover, unpublished slice recovery and screenshot deadline

The user requested takeover of the "Investigate QEMM Driver" agent. Live
GitLab readback found MR !117 and its source branch still at
`ed1746e2525e9239be174a80c873167e52929eeb`, while the previous clean local
checkout held the newer slice-4 commit
`6434474b0318bf9ee6d7d3d1b2ea094a3a81629d`. Its publication receipt was only
`prepared`; the current MR description and notes did not include that commit.
This was a publication gap, not missing implementation. The recovered delta
contains 29 authored Python, JSON and Markdown paths and no binary payloads.
An isolated checkout preserves the original checkout unchanged.

Review of the recovered slice found one additional deadline defect. The legacy
`screenshot()` wrapper still used the ordinary machine-operation lock even
though its nested `capture_surface()` had the new I/O deadline handling. An
already-expired script therefore attempted a new 10-second lock wait, and a
50 ms screenshot script could spend 10 seconds waiting for that lock before
its inner operation rejected the expired budget. Both deterministic regression
cases failed against the recovered implementation (11 other deadline checks
passed). The wrapper now uses the same `machine_io_operation` as the direct
surface path. Expired calls refuse before lock admission; contended calls use
only the remaining script budget; nested QMP/GDB bounds are restored normally.

Fresh source checks after the fix:

```sh
python -m pytest -q tests/test_qemu_clock.py tests/test_qemu_input.py \
  tests/test_qemu_surface.py tests/test_qemu_io_deadlines.py \
  tests/test_qemu_input_checkpoint_guard.py tests/test_qemu_io_public.py \
  tests/test_qemu_operation_deadlines.py tests/test_gdb_standard_replies.py \
  tests/test_dos_migration.py
```

Result: **141 passed, zero skips**. The narrower 93-check follow-up is included
in this selection and is not an additional unique-test count. A separate
read-only review found no concrete issue in the two-file deadline correction;
that review did not run tests.

The native lane used the previously pinned QEMU 10.0.13, firmware, FreeDOS 1.4,
mtools and NASM, with `FDISBULL_REQUIRE_QEMU_DOS=1` and
`FDISBULL_REQUIRE_QEMU_DOS_OS=1`:

```sh
python -m pytest -q tests/test_qemu_io_native.py
```

Result: **9 passed, zero skips, 31.01 seconds**. These fresh witnesses exercise
physical keyboard/mouse consumption, a distinct guest draw boundary, paused
and running clock observations, source traces after an explicit stop, persisted
evidence reopen and terminal VM cleanup. Original budgets and the scoped
`SWITCHES=/F` I/O baseline were retained. Earlier reported large-MZ and retained
DOSBox timeout observations remain unresolved; this run does not erase them.

An isolated wheel install outside the checkout then passed the same 9 native
I/O witnesses, all 7 doctor checks and all 13 I/O deadline checks: **29 passed,
zero skips, 38.70 seconds**. The import path was checked before this run to
exclude a source-tree fallback. The wheel SHA-256 is
`b5574934b839deb87d2298ec6c9db5f746e1490511c65fc1a8127dbf6cdef8d9`;
all 632 `fdisbull/` package files are byte-identical to the candidate source,
with no missing or extra package paths. These package tests repeat selected
source cases and are not an additional unique-test total. This was a private
test installation, not a shared installation or release.

The migration inventory still reports DOSBox as default, both explicit fallback
selectors retained, automatic replay disabled and all 127 parity surfaces
unqualified. No new guest-time, completed-frame, audio, checkpoint or hostcall
claim is made by this recovery. The next engineering gate remains the explicit
native virtual-clock interface and independent busy/HLT/IRQ/media witnesses,
before clock-dependent checkpoint/history work. The configured Mac mirrors are
still not accessible from this executor.

Publication must fast-forward the same branch, retain the original MR marker
and target, and skip provider CI. The exact published head and final packaging
readback belong in the MR description; do not treat the earlier `prepared`
receipt as evidence that its source was already remote.

### 2026-11-08 — clock, physical input and stopped display path

Started from the read-back GitLab head
`ed1746e2525e9239be174a80c873167e52929eeb` on the existing branch/MR. The
user requested continuation. No new source branch, backend default change,
runner, credentials or hosted CI was needed.

The implementation supplies three distinct observations. Physical edges are
queued in Python under a machine-owned lease, accepted once by QMP during an
owned GDB continue, and independently consumed by guest BIOS/IRQ code in the
native witnesses. QMP acceptance always leaves `guest_consumed=None`.
Display capture then records the actual stored surface and a stopped CPU/clock
bracket; it does not infer that the guest finished a frame.

#### Decisions and observed constraints

| Investigation | Actual result and implementation decision |
| --- | --- |
| Paused physical input | QEMU 10.0.13 rejected `input-send-event` with `VM not running`. Paused `send-key` returned success but an authored port-60h consumer read no scancodes after execution. Production uses neither as a paused native queue. |
| Input and debugger stops | A single GDB `c`, one optional QMP batch and the same GDB stop packet preserve the actual breakpoint/watchpoint reason. An early stop may leave the queue pending or occur after QMP acceptance but before consumption. There is no automatic retry or second continue. |
| Generic clock commands | The installed command inventory provided no generic QMP clock reader; HMP `info clocks`/`info timers` were unknown. Qtest memory reads worked alongside TCG, but `clock_step` was unknown; the installed executable did not offer the qtest accelerator. These were not used as an execution clock. |
| Plain instruction counting | `query-replay.icount` progressed with `mode=none` under explicit `-accel tcg,thread=single -icount shift=7,align=off,sleep=off`; recording was unnecessary. The standard launch's zero counter was not a valid progress observation and is reported unsupported. |
| Idle clock warp | In an independent HLT/IRQ witness, icount advanced 6,190,945 to 6,363,605 while BIOS ticks advanced 14 to 429. The instruction delta times 128 ns cannot represent all that guest time. `virtual_ns` and `guest_ms` therefore remain null. |
| Exact count stopping | `replay-break` refused ordinary execution and record mode; it requires replay. The public live run keeps a host-time budget, not an exact icount/guest-ms promise. |
| Display surface | Paused screendump produces pixels but no last-completed guest frame identity. Captures use independent observation IDs, not invented frame/mode ordinals. |
| Python media services | No custom opcode, QEMU plugin, time authority or Python renderer is loaded. PNG capture is available; OGG playback, virtual-clock ownership and UDL/UIL join synchronization remain later work. |

`qemu_clock='instruction'` is an explicit launch option in Python/JSON and
`--qemu-clock instruction` in the CLI; raw `Project.machine` uses
`clock_profile`. The selected descriptor is retained in immutable machine
configuration. It requires one vCPU. Observation epochs/sequences detect a
changed profile or regressing native counter and close that machine.

Keyboard key-down/up and relative mouse/button methods have bounded queues,
machine-scoped leases, duplicate/cross-device/stale-lease guards and explicit
cancellation. Limits are 256 pending edges and 64 leases. Cancelling only
removes unsent transitions; an accepted hold remains owned until an explicit
release or VM close. Machine ownership survives selected DOS-child return and
is never relabelled as process ownership. A failed script that touched input
closes and reaps its VM. Uncertain transport or persistence never replays input.

`capture_surface` and `screenshot` store PNG, source/run/hash/dimensions,
selected CPU state and a before/after clock bracket. Standard clock stability
is `not_observable`; the instruction profile can establish only unchanged
icount. Source is `qemu_display_surface`, and completed-frame identity remains
unknown. Contradictory stopped CPU/clock observations close the owner.

Public Python, retained JSON and saved-script paths expose these operations.
The source trace starts separately after a natural run reaches an explicit
breakpoint; it does not absorb that untraced interval. The older `trace-until`
queued action remains refused pending causal/IRQ-aware trace admission.

#### Review corrections retained in the implementation

- A native regression caught queued-input step refusal inside the DOS lifecycle
  failure handler. Preflight now runs before that handler; a rejected step or
  trace leaves the live process, registers and queue intact.
- Whole-script preflight now rejects malformed literal mouse releases, timed
  QEMU keyboard requests and incompatible caller transactions before earlier
  steps can mutate the guest. Existing prototype-only script validation remains
  usable without a launched VM.
- A delayed-clock reproduction exceeded a 10 ms script budget and previously
  returned success after about 41 ms. New native I/O operations now intersect
  the script deadline with VM/QMP/GDB bounds, bound lock admission, check return
  time and restore previous channel limits, including a lazily initialized GDB.
- Shared Windows snapshots could otherwise capture an accepted machine-level
  hold while serializing only Wine's separate input leases. Both the public
  state path and the lower capture seam now refuse outstanding machine leases
  or queued edges before migration; a benign refusal keeps the owner usable.

#### Validation and remaining gate

The local lanes used the previously pinned private QEMU 10.0.13, FreeDOS 1.4,
mtools 4.0.48 and NASM 2.16.03 runtime. Vendor images and raw runtime receipts
are excluded from Git. The independent new COM fixtures are authored source.
Selections overlap; their counts must not be added into a unique-test total.

| Local lane | Result and scope |
| --- | --- |
| Affected source/API regression selection | 417 passed, 60 runtime-gated skips. This includes public routes, scripts, input leases, clocks, surfaces, migration inventory and shared Windows host contracts. |
| Additional control and packaging contracts | 124 passed, 4 runtime-gated skips, including deadline propagation, physical-input snapshot guards and bundled-skill checks. |
| New native input/display/clock witnesses | 9 passed, zero skips, including independent guest BIOS/IRQ consumers, saved evidence reopen, JSON/scripts and the separate post-stop source trace. |
| Existing native DOS process/trace/core selection | 124 passed and 2 message-matching failures. The refusal behavior was unchanged; the corrected wording retained `queued input`, and both affected native cases passed at their original budgets. |
| Retained DOSBox native selection | 51 passed and 1 host-timeout failure. A fresh, unchanged-budget follow-up of that case passed; the timing observation remains unresolved, as detailed below. |
| Installed wheel outside checkout | 164 passed and 2 initial failures, zero skips. One was an instruction-profile first-READY timeout; bounded follow-ups diagnosed FreeDOS's boot-key wait, below. The other was a source-layout assumption in the dependency-free doctor test; after making that test portable, its complete installed selection passed all 7 checks. |
| Final controlled I/O configuration | All 9 source native cases passed in 37.40 seconds. With the final wheel installed outside the checkout, all 9 I/O cases and 7 doctor checks passed together: 16 passed, zero skips, in 52.53 seconds. Original startup and operation budgets were retained. |
| Final packaged ledger check | All 6 source-derived migration coverage/default/fallback checks passed after the final scope notes. |
| Installed bundled-skill validation | All 24 references and 75 local Markdown links passed with the isolated installed interpreter. |

The wheel contained exactly the expected 632 `fdisbull/` package files,
byte-identical to the corresponding candidate source, with no extra or missing
package paths. The final private wheel SHA-256 is
`12a7da006287df9f3acdc98271e73110b7bcd2fe57c0f56057e36e98e0c98bfe`.
The doctor correction copies only the actual source or installed
package into an isolated directory before invoking Python with `-S`; it no
longer assumes that the test's parent directory contains a `src/` checkout.

The retained DOSBox case
`test_native_click_trials_keep_shared_handler_register_value` reached its
10-second host budget before the idle trial's 500-step budget. A fresh follow-up
passed without changing the code, budget or assertion. This does not establish
a fix or a cause, and the initial failure remains part of the evidence. The
QEMU changes do not change that DOSBox execution path.

#### Diagnosed instruction-profile startup wait

The installed clock case exceeded its original 15,000 ms startup budget before
the loader's first READY report. A bounded fresh instruction-profile follow-up
reproduced it with zero report bytes; its paired standard-profile boot completed
in 4,599.865 ms and passed the pause/run clock checks. GDB is not initialized
before READY, so the new GDB input callback was not on this failure path.

One further instruction boot retained the same budget and captured the stopped
screen, registers and low memory before cleanup, without additional execution.
It showed FreeDOS kernel 2043's F5/F8 startup line. The firmware interrupt entry
matched the pinned SeaBIOS bytes and decoded as INT 16h/AH=01 keyboard status.
The recovered DOS caller actively polled that status while comparing elapsed
BIOS ticks against its configured two-second delay: start `0xd8fc`, current
`0xd918`, **28 elapsed ticks against a 36-tick target**. Eight ticks remained
when the host budget expired. This identifies the active guest wait; it does
not establish a deadlock, failed serial channel or generic host contention.

The discriminating control changed only a new test baseline's configuration,
prepending the documented `SWITCHES=/F` to omit FreeDOS's boot-key delay. The
original configuration remained its exact suffix and the startup batch stayed
unchanged. One fresh installed instruction-profile boot, with no retry and the
same 15,000 ms limit, completed in **4,134.816 ms** (READY in 2,214.098 ms).
Its real witness, 80 ms host pause and 300 ms bounded run passed: BIOS ticks
`1043932 -> 1043932 -> 1043942`, and icount
`9936878 -> 9936878 -> 13972803`. Guest milliseconds and virtual nanoseconds
remained unknown. Every diagnostic/control VM was reaped and original inputs
remained unchanged.

The I/O witnesses therefore use an explicit, scoped `SWITCHES=/F` baseline for
both profiles. The broad process fixture and production staging are unchanged;
the tool never inserts this switch into a caller's CONFIG or extends its host
budget. The original failed starts remain evidence that guest boot delays can
outlast a host deadline under instruction counting. These tests qualify
post-boot I/O on the declared configuration, not arbitrary startup performance.
FreeDOS documents the switch in its
[SWITCHES reference](https://help.fdos.org/en/hhstndrd/cnfigsys/switches.htm).
The earlier large-MZ timeout lacks this stopped evidence and retains its
separate unresolved status; this diagnosis is not retroactively assigned to it.

The new native witnesses directly observed BIOS key AX `1e61`, IRQ1 make/break
`1e 9e`, PS/2 movement/left-press `09 05 00` and release `08 00 00`. Before the
BIOS witness's draw point the key was consumed but its sentinel pixel stayed
black; the later draw point turned it red. Mouse press/release pixels became
green/black. Paused BIOS ticks and instruction counts stayed unchanged.

Slice 4 remains **in progress**. The legacy inventory still accounts for
35 RPC methods, 83 public DOS routes and 9 extra surfaces; partial routes do
not change its 127 unqualified-surface default-switch gate. Generic guest-time
budgets, completed frames, audio, frame-edge input, pixel/INT33 mouse mapping,
real drivers/games and Windows timing remain unqualified. Keep DOSBox default
and both fallback selectors. The macOS mirrors remain unavailable here.

Next work: select an explicit native virtual-clock observation/control seam
and a guest drawing/audio completion contract, then prove those with independent
busy/HLT/IRQ/media witnesses before implementing clock-dependent checkpoint and
history consumers. The available stock-QEMU path is already usable for explicit
input-to-breakpoint analysis with separate post-stop source traces.

### 2026-11-08 — trace/event implementation and qualification handoff

Implemented the next vertical path in `QemuDOSProcessSession`: source-bound
`trace`, stopped-boundary `trace_until`, the existing public JSON/script
routes, and persistent execution-event queries/searches. Raw machine tracing
remains separate. DOSBox remains the default and both fallback selectors stay
available; no automatic replay, default promotion or retirement was enabled.

Each capture retains observed runtime bytes/registers, linear and segmented
PCs, the actual read-only stepping policy, initial PSP/allocation and capture
epoch. Source-site identity is independently derived from original bytes,
ordered MZ fixups and exact DOS startup writes. Storage checks the original
entry receipt before the artifact receipt, immutable launch evidence and every
claimed source instruction. Normal lifecycle changes do not erase authentic
historical captures. Changed bytes, module/allocation/epoch departure or an
unsupported mode stop binding; no live overlay/task identity is inferred.

Native witnesses showed an MZ entry moving from `0x23520` to `0x28840` while
its source entry remained `0x10020`. The observed `MOV` bytes changed from
`b85723` to `b88928`; both identify canonical project bytes `b80710`.
Independent command-tail A/B trials retain shared code sites while narrowing
register values, including after VM close and project reopening. Memory
sentinels verify predicate stops before the following instruction's effects.
Foreign execution/data breakpoints, self-modification, CR0 mode transition,
changed allocation ownership and unbound INT 21h endpoints have witnesses.

Corrections discovered during the slice:

- A normal GDB step reply does not establish instruction retirement. Native
  divide-fault and partial REP witnesses invalidate the previous unconditional
  completion wording. QEMU trace annotations now retain unknown completion;
  DOSBox and PE contracts remain unchanged. The actual policy is observed
  through `qqemu.sstepbits` and `qqemu.sstep`, never set by production code.
- `GDBRemote.request` treated every reply beginning with `E` as an error, which
  rejected QEMU's valid `ENABLE=...` bit inventory. Error recognition now uses
  the standard `Exx` and `E.errtext` forms, preserving terminal handling for
  genuine errors and failed transport.
- Caller-owned transactions could roll back evidence after the CPU advanced.
  Direct captures and containing scripts now refuse before native dispatch or
  earlier script mutations. An actual transaction witness confirms unchanged
  registers and zero new commands/artifacts/events.
- A lost dispatched reply left a stale pre-step `current_stop`. The result now
  clears that field before dispatch; preceding observations remain in events,
  and uncertain control closes the machine without replay. Actual SQLite
  artifact/journal rejection retains the observed result for inspection.
- The existing doctor still required the old unconditional completion flag.
  Its independent counter effect already passed. It now verifies observed
  stopped-boundary semantics and the actual policy when reopening evidence.

Primary protocol references are [QEMU's GDB stepping documentation](https://www.qemu.org/docs/master/system/gdb.html#changing-single-stepping-behaviour)
and [GDB standard replies](https://www.sourceware.org/gdb/current/onlinedocs/gdb.html/Standard-Replies.html).
Native conclusions here use the actual installed QEMU 10.0.13, separately from
those current documentation pages.

Fresh local checks are recorded below. Lanes overlap and are not additive;
initial failures and focused corrections are retained rather than rewritten
as a clean first run.

| Lane | Observed result |
| --- | --- |
| Affected source/API/storage/policy/migration/helper/memory/skill checks | 613 passed; 10 explicitly runtime-gated skips |
| Additional GDB/machine/Windows host-control checks | 85 passed; 8 separately gated native skips |
| Native process/trace/core/doctor plus helper lane, required inputs enabled | 125 passed, one doctor assertion failed; no skips. Corrected doctor suite then passed all 7 checks. |
| Retained DOSBox debugger/exit/TSR/state/runtime-code/event/DESQview-memory lane | 42 passed, zero skips |
| Installed wheel outside checkout, source import path disabled | 64 passed, two initial failures; zero skips. Doctor was the same stale assertion and its corrected installed suite passed all 7 checks. The large-MZ startup timeout is detailed below. |
| Large-MZ installed follow-up, unchanged 15-second limit | Two independent fresh VMs passed: testcase durations 3.655 s and 4.501 s |
| Installed investigation skill | 24 references and 75 local Markdown links passed |

The first ordinary source run also exposed three authored machine-peer fixtures
that lacked the new read-only query. Their explicit unsupported reply now
tests preservation of unknown policy; the final source count above includes
the correction. The first new native trace run had two fixture expectations
corrected: physical key names are lowercase, and canonical MZ bytes include
the project's static relocation. Those were not production defects.

**Remaining reliability observation:** the installed 80 KiB MZ case once
expired after 15.055 seconds waiting for the loader's first READY report,
before full-module/chunk validation. The same source case passed in 3.345
seconds. No debug run/event/artifact was committed by the failed launch. Two
fresh installed runs passed at the original budget, without a live-operation
retry or increased timeout. Available evidence does not distinguish boot
delay, loader stall or transport behavior; workload contention is unproven.
Keep this occurrence in the compatibility campaign rather than calling its
cause fixed. Private receipts retain the original failure and both follow-ups.

The final private integration wheel is `fdisbull-0.33.0-py3-none-any.whl`,
SHA-256 `feb1725140a2fc9a6b4e7cced84edebd929ef30c7bf52f30a8840ea9a4763712`.
All 629 core package files match current source bytes, with no extra core files.
The installed run imports the private environment's `site-packages`, uses
`pytest -c /dev/null --import-mode=importlib` outside the checkout, and puts only
the test directory on `PYTHONPATH`. This is not a release, hosted CI result or
shared installation. Vendor files, runtime databases/states and raw receipts
remain outside Git. The draft MR retains its existing stack parent.

Next slice: define native guest-time budgets, coherent frame observations and
keyboard/mouse dispatch/consumption before combining actions with event trials.
Keep host wall time, virtual CPU/PIT progress and media duration distinct.
QEMM/DESQview task scheduling, protected/V86 source maps, live overlays, games,
Windows, macOS, checkpoints and layers/UDL/UIL services remain unqualified.
The full migration ledger still contains 35 RPC, 83 public and 9 supplemental
surfaces; none can disappear from the default-switch gate.

### 2026-11-08 — trace/event slice started from the published DOS process slice

Resumed `d9f5a9caa418b2f0101f83e327c20e9caa66d07d` and verified that
the GitLab draft and source branch still identify that commit. The private
QEMU/FreeDOS runtime and test environment survived this handoff. Existing
results below remain historical until the changed integration is qualified.

Acceptance target: connect the native DOS process to the existing source-bound
trace, predicate and event-search paths. Preserve observed runtime bytes and
derive relocation-independent instruction identity from the original module;
historical traces must remain usable after process exit and project reopening.
Bind captures to the original verified process-entry epoch. Stop on unsupported
mode, ownership or source changes instead of silently rebinding an overlay.

Independent native probes reproduced two errors in the old completion wording:
a divide fault returned a normal GDB stop at its handler without completing the
faulting instruction, and a REP string operation returned after only one
iteration. The new slice records stopped boundaries and the actual QEMU
single-step policy; a stop reply alone does not establish retirement. Queued
input and natural-time IRQ/media behavior remain the next clock/input slice.

The Mac mirror path remains absent here. A Mac-side fast-forward fetch into the
bare hub can synchronize the published branch without a cloud mount. Direct
access needs a configured network route and SSH authentication; this executor
also lacks `/dev/fuse`, so installing SSHFS alone would not enable a mount.
No Mac settings, credentials or mounts were changed.

### 2026-11-08 — restored baseline and started the next slice

Request: maintain a handoff log beginning with the migration plan and expected
difficulties, and continue to the next slice.

Observed: the prior scratch checkout and runtime inputs were gone. Read back
MR !117 and its source branch, then restored the exact published baseline above.
The MR is still opened and draft. The attached 0.32.0 offline kit is available
for recovering dependencies and the retained DOSBox runtime; it is not the
source revision for this implementation.

Historical evidence, recorded in MR !117: 387 ordinary passes with one unrelated
ScummVM skip; 58 core passes; 16 native/doctor passes; 41 retained DOSBox passes;
and 9 native passes from an isolated wheel. Those runs covered the initial
native core and a real FreeDOS service probe. They do not qualify the next
slice, and the lost scratch receipts have not been represented as new runs.

Initial decision: use real DOS loading and observed process identity for the
next slice. A source-disk signature or a fabricated PSP cannot establish that
DOS loaded a program. Independent review is checking the DOS/FreeDOS loader and
termination contracts while the executable test environment is restored.

Next checkpoint: record the selected public API and guest-loader protocol,
then the first real COM/MZ load results and any evidence-driven changes.

### 2026-11-08 — restored execution and fixed the process contract

Fresh baseline: the restored stock QEMU 10.0.13 runtime passed all 16 tests in
`tests/test_qemu_dos_native.py` and `tests/test_qemu_doctor.py`, including the
required actual FreeDOS service test. This is a new Linux pipe-transport run;
it still qualifies only the preceding core slice. Runtime dependencies were
unpacked into a private prefix, with no system installation or hosted CI.

Demonstrated gap before integration: an original authored COM project rejected
`dos_boot_image` as an unknown public launch option. The existing raw-disk
constructor deliberately binds the disk to the project's source SHA. It must
not be weakened to allow unrelated program bytes.

Selected integration: keep `backend=qemu-dos`, retain raw-image behavior, and
route original COM/MZ projects to a dedicated process session. New process
options are `dos_boot_image`, `dos_mcopy`, `dos_startup_batch` and
`dos_arguments`. Machine controls retain their explicit address semantics;
`debug-dos-process` exposes observed PSP, initial source mapping and lifecycle.

Selected preparation: stage a private disk, preserve its configuration and
existing startup batch bytes, and append the authored loader invocation. Do not
copy the old test fixture's configuration replacement into production. If the
existing startup never returns, report a bounded launch failure. Game assets
and drivers required by the program must already be present in the boot image;
this slice does not mount an arbitrary host folder.

Selected guest protocol: an authored COM helper uses DOS EXEC load-only,
reports a fresh nonce and loader-selected entry/stack/PSP through COM2, waits
for host validation, and transfers to the target under a native entry
breakpoint. Its parent-return callback records DOS AH=4Dh exactly once.
The host verifies the real allocation chain, full relocated file-backed module,
PSP parent/tail and helper report. It keeps one machine breakpoint registry and
advances the memory-search epoch at process exit/residency. COM2 must be reserved
for this protocol; guest interference is not treated as an authenticated report.

Research-driven details to preserve:

- Load-only EXEC returns a stack containing an extra initial AX word. Consume
  that word without losing COM's zero return word; qualify with a one-byte RET.
- MZ high-load placement can differ from PSP+10h. Derive the module segment
  from returned CS and relative header CS, then corroborate with relocations.
- Both AH=31h and INT 27h can return DOS's resident termination category. That
  category alone cannot identify the instruction mechanism.
- A target's nested child exit, remapped INT20 that returns, or host close must
  not become the selected target's DOS termination event.
- Device-header registration is an observation, not proof that device I/O works.

Primary references: [Microsoft EXEC implementation](https://github.com/microsoft/MS-DOS/blob/main/v4.0/src/DOS/EXEC.ASM),
[FreeDOS DEBUG loader](https://github.com/FDOS/debug/blob/master/debug.asm), and
[Microsoft DOS system-call reference](https://www.pcjs.org/documents/books/mspl13/msdos/encyclopedia/section5/).
These inform the implementation; fresh native tests still determine its scope.

### 2026-11-08 — native witnesses and independent boundary review

The first 13 native process cases passed through the public `qemu-dos` launcher:
COM entry and near RET, normal and high-load relocated MZ, command tail/FCBs,
inherited environment and DTA, nested EXEC, remapped INT20, both TSR APIs,
resident allocation/vector observations, persistence and private-source checks.
An additional authored CONFIG.SYS character driver passed its initialization
marker and registered-header checks. This establishes that narrow driver path,
not arbitrary device I/O or QEMM/DESQview compatibility.

Independent review produced concrete regressions, now part of the acceptance
work rather than omitted edge cases:

- DOS load-only writes initial AX to the returned raw SS:SP. A valid high-load
  MZ with a file-backed `BEEF` word there was rejected by the original strict
  comparison. A maximum-size COM also contains DOS's zero near-RET word. Model
  both exact loader writes after MZ relocations, record byte-level before/after
  provenance, and retain full comparison of the resulting module. Do not mask
  a stack region or change the original source hash.
- Corrupting the helper's return nonce correctly reaped QEMU, but left active
  process metadata. Shared machine-close invalidation now clears live ranges
  and advances the capture epoch; an unobserved return remains unknown, with
  no invented DOS termination result.
- Publishing a run before its first entry event could leave a phantom session
  after database failure. Publish both atomically, attach live ownership only
  after commit, and refuse launch inside a caller-owned database transaction.
- Staging, executable probing, QMP, GDB and report reads need a shared deadline;
  independent per-command timeouts could exceed the requested launch budget.
  Propagate one absolute operation deadline, retaining only the explicit GDB
  interruption/recovery allowance after an execution timeout.
- Memory-search/report mixins need the same machine failure guard as direct
  register and memory operations. A transport failure must not retain an owned
  emulator merely because the operation used another decorator.

The exact stack-write contract was checked against the
[pinned FreeDOS kernel loader](https://github.com/FDOS/kernel/blob/4f7bdda16a84c416a82a2616aa67335ca4f2bd74/kernel/task.c).
Independent native nonzero-stack probes corroborated both affected formats.
The initial failing regressions are historical red tests; record the final
integrated results below once rerun. Current storage admission has over 55 GiB
free; only small authored fixtures, disposable disks and one test wheel are
planned. No hosted CI or installed/shared runtime changes are involved.

### 2026-11-08 — completed the process path and integration gates

Implemented: real DOS EXEC launch for original COM/MZ projects through the
public Python, CLI and retained JSON paths. Source, original boot disk and
prepared disk identities remain separate. The machine stops at the selected
program's observed entry; `debug-dos-process` exposes the PSP, initial mapping,
allocation and lifecycle. Native scripts accept `guest_exit` and `guest_tsr`
without confusing either with machine termination.

All review regressions now pass. Additional checks caught and fixed the 64 KiB
per-request GDB read limit for larger MZ modules and ownership of the Unix COM2
client descriptor. The 80 KiB MZ witness verifies the full image across bounded
reads, including a nonzero tail. The maximum-size COM and nonzero MZ stack
witnesses preserve strict whole-module verification with exact loader-write
provenance. Initial publication and post-execution database failures are tested
using actual SQLite triggers. Native transport-failure tests reap the emulator
and persist invalidated identity.

Fresh local verification on the integrated source, followed by the matching
private wheel (lane counts overlap and must not be summed):

| Lane | Result | Scope |
| --- | --- | --- |
| Affected source/API/contract tests | 532 passed, 1 unrelated skip | Helper assembly/template equality with required NASM, real mcopy staging, deadlines, lifecycle/source units, migration coverage, memory/report consumers, capabilities, packaged-skill and Windows interface regressions |
| Shared QEMU control/profile checks | 61 passed, 5 intentionally deselected | Existing non-native pipe/GDB/QMP/profile checks and new startup-budget/Unix-descriptor ownership checks |
| Native DOS process | 18 passed, zero skips | Original COM, near RET, relocated/high-load/80 KiB MZ, PSP/tail/FCB/environment/DTA, nested child, remapped INT20, TSRs, preserved SYS setup, source isolation, JSON route, malformed return and timeouts |
| Lifecycle and scripts | 6 passed across focused runs | Caller transaction refusal, entry rollback, inherited transport failure, post-run journal failure, COM and TSR scripted completion |
| Existing native core/doctor | 16 passed, zero skips | Raw-machine launch/control/artifacts and actual FreeDOS service probe |
| Retained DOSBox | 41 passed, zero skips | COM, exit/TSR, layers, checkpoint restore, execution-event and DESQview memory-search witnesses |
| Installed wheel, outside checkout | 40 passed, zero skips | All native process, lifecycle/script, raw-core and doctor cases with source import paths disabled |

The single ordinary skip requires patched ScummVM and a private KQ1 original;
it is unrelated to this migration. Five existing machine cases were excluded
from the separate non-native selection; the native DOS lanes above were required
and had no skips. The installed bundled investigation skill passed with all
24 references and 75 local Markdown links checked.

Runtime provenance: stock Debian QEMU 10.0.13
(`d3c1a558ad220e77a4412048c8d96b44f8c2b41c7ad2a4ecfe522a4b122fe067`),
matching explicitly pinned firmware, FreeDOS 1.4 Floppy Edition boot image
(`552f7cbb0625960c050a3e682a4d2121cc2ffdfa9dc9d592ccd49edf179333dc`),
mtools 4.0.48 and NASM 2.16.03. The DOSBox witness uses the separately retained
patched runtime from the supplied 0.32.0 offline kit, with current source as
the controlling application. These are Linux pipe-transport results; the Unix
descriptor unit check is not an end-to-end Unix backend qualification.

Private test wheel: `fdisbull-0.33.0-py3-none-any.whl`, SHA-256
`9136fd84fefdf57a38a49320a302d1a56aef3b8c1b23c7b68ed29d5d7adc818d`.
All 626 tracked core package files matched their wheel bytes, including the
readable helper assembly and migration reference, with no extra core payload.
This is an integration build, not a release or shared installation. The
source-distribution and tool-source recipes also now include the helper ASM.

Reproduction inputs: `FDISBULL_QEMU_DOS`, `FDISBULL_QEMU_DOS_FIRMWARE`,
`FDISBULL_QEMU_DOS_BOOT_IMAGE`, `FDISBULL_QEMU_DOS_MCOPY` and `NASM`; require
native lanes with `FDISBULL_REQUIRE_QEMU_DOS=1` and
`FDISBULL_REQUIRE_QEMU_DOS_OS=1`. The installed run used an isolated private
site-packages install, `pytest -c /dev/null --import-mode=importlib` from outside
the checkout, and only the test directory on `PYTHONPATH`. Vendor images,
runtime databases, machine states and raw receipts remain outside Git.

Remaining boundaries: process entry requires observed real mode; patched
versions, secondary executable stubs, live overlay rebinding, protected/V86
process mapping, arbitrary driver I/O, actual QEMM/DESQview scheduling, games,
Windows and macOS remain unqualified. Startup must reach and return from the
selected batch. Assets/drivers must already be on the supplied image. COM2 is
reserved. Checkpoints, guest-time media/input and layers/host services remain
later slices. The default-switch gate remains blocked and both DOSBox selectors
are retained.

Next step recorded for that handoff: start the trace/events slice from the verified initial source map
and capture epoch. Define which trace addresses remain machine addresses and
which can be bound to the original source. Add event predicates for register,
entry/new-region and completed-versus-attempted execution; stop source-bound
searches at exit, residency, mapping change or unknown ownership. Qualify IRQ,
fault, REP, nested EXEC, relocation and self-modification boundaries before
connecting higher-level action/event search. Preserve the raw machine trace
and retained DOSBox event path for comparison; the following slice corrects
the earlier unconditional completed-step terminology.
