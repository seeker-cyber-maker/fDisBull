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
  instruction and native virtual-clock observations, token-bound native timer
  budgets, retained synchronous renderer publications, bounded PC-speaker PCM
  windows, one-shot native virtual-time input scheduling, timestamped source
  observations and temporal event queries, explicit precise VGA retrace-model
  observations with timing generations, one-shot precise retrace waits,
  generation-checked native input at a strictly next modeled retrace edge,
  cooperative fixed 1:1 host/native clock auto-sync, and stopped
  media/CPU/clock brackets, alongside the earlier
  source-bound real-mode COM/MZ traces and event searches.
- Takeover: `chat:54d0a46c7daf` recovered the unpublished slice-4 commit
  `6434474b0318bf9ee6d7d3d1b2ea094a3a81629d` from the previous checkout. The
  existing branch, originating handoff marker and stacked MR target are retained.
- Next gate: qualify guest frame/VBlank semantics, additional audio devices,
  legacy timed helpers and frame-edge input, coordinate mapping and input-to-source causality
  before claiming those behaviors or depending on them in checkpoints and
  histories. Renderer completion and capture-callback delivery are now explicit
  narrower boundaries. Scheduled input now records PS/2 callbacks and sync at
  native virtual time; device acceptance and guest consumption need independent
  observations. Source traces now retain clock-qualified stopped boundaries
  and temporal queries, with no natural-instruction-timing or causal claim.
  The retrace wait now verifies one strictly next modeled transition. Retrace
  input now checks that same admitted model and the original absolute window
  immediately before PS/2 callbacks; timing changes or missed windows cancel
  for explicit resolution. This boundary does not qualify full VBlank or
  guest-frame input. The
  user authorized timing auto-sync in the latest continuation; the host
  controller now makes one bounded correction at an explicit cooperation
  point. Full VBlank, frame completion, legacy guest_ms, timed helpers and
  DOSBox timing parity remain separate
  qualifications. The full slice remains open.
- Defaults and rollback: DOSBox remains the default; both DOSBox selectors stay
  available. Native default promotion and DOSBox removal are blocked.
- Publication: authored source and this maintained engineering log belong in the
  branch. Vendor images, game bytes, runtime databases and emulator states stay
  outside Git. Routine publication must not start hosted CI.
- Local mirror: the configured macOS `/Volumes/...` mirrors are not mounted in
  this Linux workspace; do not report them synchronized.

## 2026-11-09: generation-checked input at a modeled retrace edge

This continuation starts from
`67a6c40d91de383f3986bc1902932a0a7dca16c2` on the existing source branch and
draft MR !117. The user requested continued implementation and another GitLab
publication attempt. The preceding clock auto-sync/wait commit and description
were already present when read back. The stacked target remains
`agent/execution-event-search-284eb73c` at
`089c1841c415eb2b5cdfa90d03b6291a07f73919`.

### Public and native boundary

`input_schedule_retrace(edge='enter'|'exit', timeout_ms=1000)`, JSON
`debug-input-schedule-retrace` and saved-script `input-schedule-retrace` arm
the existing pending physical batch without executing the guest. Admission
requires explicit virtual/precise profiles, all existing native clock/input/
retrace commands and the new `x-fdisbull-arm-input-retrace` command. The
`retrace_input_schedule` capability is separate from ordinary delta scheduling.

The optional fifth [native patch](../native/qemu-input-retrace/README.md)
applies after the unchanged exact clock, media, input and retrace layers.
It reuses the existing one-shot timer, event-batch preflight, PS/2 callbacks,
final sync, bounds and token history. Native code checks all expected stopped
identity fields and independently computes the strictly next target and its
exclusive absolute window. Unsupported timing or no transition refuses before
accepting an arm. Caller-supplied deadlines are not accepted as phase evidence.

At the callback, existing invalidation, pending-stop and reached/equal-budget
checks run first. Only then does a private BQL-held helper snapshot the already
pinned VGA model. It performs no new admission, guest I/O, rendering or timing
repair. The public passive retrace query retains its stopped/no-active-budget
guard; builds without standard VGA have an explicit helper error stub.

A higher generation, including hidden A-to-B-to-A changes or newly enabled
VBE, cancels as `retrace-timing-changed`. An unchanged coherent generation
sampled at or beyond the original window cancels as `retrace-missed-window`.
Both leave pending input bound for explicit reschedule/cancel and do not add
a VM stop. Identity/cache/epoch loss remains fatal. The caller must allow its
bounded execution beyond the target to permit delivery: an equal clock
deadline, including a retrace wait to that edge, cancels before callbacks in
either timer insertion order. A cancelled release retains its prior hold.

The base `fdisbull-qemu-scheduled-input-1` receipt gains a
`fdisbull-retrace-input-1` member with the full stopped observation, exact
target/window and frozen native arm/check snapshots. Success requires
`checked.virtual-ns == dispatch-ns == terminal-ns` inside that original window.
The pure snapshot validator does not move the live retrace frontier backward.
Later observations cannot relabel a historical check. Existing
`input.schedule-arm/result/observe` events retain the exact native receipt.
The [timing guide](DOS_QEMU_TIMING.md#schedule-input-at-the-next-modeled-retrace-edge)
documents the caller workflow and explicit resolution rules.

### Defects and witness corrections retained

The initial method/catalog witnesses failed as expected before implementation.
Focused adversaries then found and fixed four ownership/evidence boundaries:

- A successful arm could expire in the public wrapper's final return check
  while leaving a usable timer. That narrow path now invalidates input and
  closes the VM, retaining the accepted receipt on the timeout.
- A resolved script timeout could be normalized by the remaining-budget clamp
  before strict validation. Resolved options now validate before clamping;
  literal options still validate in whole-script preflight.
- A dispatched receipt could carry a reserved retrace cancellation reason.
  State/reason consistency now rejects that contradictory evidence.
- Malformed/native-failed callback receipts and journal failures could lose
  available phase evidence. Errors now preserve raw native/before evidence
  alongside the original GDB stop; direct observe failures retain the already
  built receipt. No uncertain result is replayed or accepted into the ledger.

Two initial host assertions were corrected to compare the unchanged pending/
lease ledger rather than observation metadata. The first new native run had
12 passes and one witness error: it expected `stopped` after explicitly
cancelling the clock budget. The corrected witness first verifies the actual
stopped receipt and firing chronology, then proves cleanup changes only the
budget state to `cancelled` and leaves input evidence identical. The fresh
combined source and installed native selections below include all 13 cases.
No native implementation changes were needed after its first build.

### Exact native reproduction and build

The original QEMU 10.0.13 archive remains pinned at SHA256
`4a59b74dac7ead8b162a7c4595dcbbeebe989b90c89cfe6bb4dec5447342f6fa`.
The final fifth patch is
`5d80203da6c395aa987c8bdde80bb04db1badd169ce3bea258f50e0cdb6cdc80`.
Its six changed members and four exact dependencies are recorded in the
new source manifest; the combined chain identifies 26 final native paths.

The first full-archive extraction stopped at an unrelated absolute EDK2 link
under the strict data filter. That failure is retained. Reproduction then
selected the 92 required regular source/QAPI/parser inputs from the same
verified archive, without extracting unrelated ROM/submodule links. All five
layers applied with exact intermediate/output hashes. The final patch omits
blank context prefixes so ordinary repository whitespace checks remain useful;
that formatting-only revision was reapplied/reversed with zero fuzz or offset,
matching all six output members and restoring all 25 prior native members.
The full QAPI schema parsed successfully on the reconstructed source.

The isolated x86_64 TCG/Pixman build configured in 16.668 seconds and compiled
in 110.166 seconds, with unchanged native source hashes. Its executable SHA256
is `744270aeecfbe1a05da6b170b7c1be3a634476444f4cf7ef3f583cb3c16819b7`.
The retained four-patch executable
`5d202d2ec57d596351381d7fc1df67211c4d0727ad667119183d41b450c96565`
was explicitly exercised in both native selections: it refuses the new
capability while ordinary delta scheduling remains usable. Runtime media,
firmware, mcopy and the three-patch DOS compatibility binary retain their
previous recorded identities. Material growth phases admitted their bounded
growth estimate plus a 20 GiB free-space reserve.

### Local qualification

These are finite local Linux results, with overlapping selections:

| Selection | Result |
| --- | --- |
| Focused retrace-input and existing scheduling/retrace contracts | 272 passed; 0 skipped |
| Public routes, script admission and ownership | 22 passed; 0 skipped |
| Affected source regressions | 1,190 passed; 5 skipped |
| Combined source native selection | 73 passed; 0 skipped |
| Fresh installed-wheel regressions | 1,179 passed; 5 skipped |
| Fresh installed-wheel combined native selection | 73 passed; 0 skipped |
| Retained DOSBox native witness | 1 passed; 0 skipped |

The focused selection contains 81 new retrace-input cases plus 51 ordinary
input-schedule, 78 passive-retrace and 62 retrace-wait cases. The two broader
lanes each skip the same five optional raw machine-session checks because
`FDISBULL_MACHINE_QEMU` is unset. Those skips are not native passes. Required
native lanes have zero skips and each contains all 13 new cases, including the
explicit retained-binary compatibility branch.

New native witnesses cover busy/HLT and enter/exit combinations, actual IRQ1
scancode and status-port reads inside the same absolute window, ABA and VBE
cancellation, original early breakpoints, both equal-deadline insertion orders,
cancelled release ownership, ordinary-arm descriptor clearing, retained JSON/
scripts/reopened evidence and five stale native expectations. Missed-window
adversaries qualify host receipt rejection; no artificially induced native
missed-window claim is made. Guest status bit 3 is checked only while the
dispatch-to-fence interval remains in the original occurrence.

The private fresh wheel is SHA256
`0d63772ae777196586dc5ad8c04cd78df00d367059e410b085151a15735f65ef`.
All 638 core payload files and 616 copied test/support files are matched to
source before installed validation. The source-archive gates compare 1,583
tracked payload files and all 23 authored paths, including the fifth patch,
manifest, documentation and bundled reference. Complete source/package/tree
verification and publication receipts remain private under
`takeover-validation/retrace-input-*` and `retrace-input-runtime`; authored
source and this engineering log are retained in GitLab.

The qualified boundary is native modeled-phase PS/2 callback/sync timing.
Device FIFO acceptance, arbitrary guest consumption, full VBlank, completed
guest frames, legacy timed-helper/DOSBox parity, broader audio, real QEMM/
games and checkpoint/layer/history semantics remain separate work. The host
auto-sync controller remains explicit and cooperative. All 127 default-
promotion entries stay open; DOSBox remains the default with both retained
selectors. No hosted CI, merge, release or shared installation was performed.
The configured macOS mirrors remain unavailable in this Linux workspace.

## 2026-11-09: cooperative clock auto-sync and bounded retrace waits

The latest continuation explicitly authorizes timing auto-sync, superseding
the deferral recorded in earlier dated entries. This increment starts from
`5d15ff9acb3ab0d87d1c829f3ec8fd505da69c69` on the same source branch and draft
MR !117, with the same originating marker and target
`agent/execution-event-search-284eb73c` at
`089c1841c415eb2b5cdfa90d03b6291a07f73919`.

### Host mapping and correction policy

The [timing contract](DOS_QEMU_TIMING.md) defines the Python, retained JSON
and saved-script interfaces. `clock_sync_start/observe/step/stop` require the
explicit native virtual-clock profile and discovered native clock commands.
The capability is `host_clock_sync`; starting a mapping remains explicit.

One mapping binds a fresh token, run, host/native epochs, selected clock profile,
configuration and original virtual/host anchors. Its fixed 1:1 target is
`V0 + (H - H0)`, with drift `actual_virtual - target`. All monotonic host
elapsed time since start counts, including Python/helper work, I/O, persistence,
debugging and caller idle. Actual intervening native progress and previous
timer overshoot are subtracted through the current virtual observation.
The controller never silently changes anchors to erase accumulated debt.

Each explicit step freezes one target and makes at most one correction.
Within tolerance, it does nothing. Bounded lag uses one native clock advance;
bounded lead uses one host sleep while the guest remains stopped. Excessive
lag or lead latches desynchronization without correction. The final receipt
reports actual residual drift against the original mapping; reaching a frozen
target does not promise zero drift after control and persistence overhead.
There is no background execution, repeated correction loop, icount-rate change,
media resampling or implicit pacing in ordinary debugger operations.

Early or coincident debugger/process stops, exceptions and timeouts preserve
the original execution receipt and interrupt the mapping. A fired timer does
not override another observed stop cause. The shared stop predicate accepts
an active, unterminated DOS process descriptor while refusing terminal or
uncertain lifecycle evidence. It retains breakpoint/watchpoint attribution,
the original GDB reply and normalized machine stop classification.

Explicit stop/start chooses a new origin after a latched condition. Stop is
passive between calls, not asynchronous cancellation of a call holding the
machine lock. Scheduled input retains its first-stop cancellation and explicit
resolution rules. A sync step can deliver caller-queued transitions; it does
not invent a release, re-arm or replay. Saved event history does not reconnect
a VM or restore a live mapping.

### One precise retrace occurrence

`retrace_wait(edge='enter'|'exit')`, JSON `debug-retrace-wait` and script
`retrace-wait` require the additional explicit precise VGA profile. They use
one before observation, one native clock budget and one after observation.
The target is the strictly next modeled transition, including when the current
sample lies exactly at that phase. A full-period retrace has no transition
and returns unsupported without execution.

Success requires the same run, both epochs, device, model and timing generation;
the exact owned timer/stop join; no conflicting observed cause; and the actual
stop within the planned absolute entry or exit interval. A matching phase in
a later cycle cannot qualify. A hidden A-to-B-to-A timing change invalidates
the planned occurrence even when the raw registers return to their old values.
Unsupported timing, timing changes, missed windows and other stops remain
distinct outcomes. No result triggers another continue or a new target.

The two controls remain separate. VGA timing changes do not rebase host anchors.
A modeled retrace transition establishes neither full VBlank nor completed
guest drawing, renderer publication, input consumption or physical VGA accuracy.

### Admission, deadlines and failure evidence

Whole-script capability, signature, literal-option and transaction checks run
before earlier script mutations. A script may start and step a new mapping in
the same request. One absolute host deadline covers lock admission, native
observations, correction, cleanup and synchronous persistence while preserving
each incoming session, machine and channel bound. The wrapper's final expiry
check also latches the matching mapping and retains its result.

Epoch/profile loss and contradictory native evidence preserve the existing
invalidation/closure policy. Failed or late storage can follow completed guest
execution; `error.result` retains known samples, the original native stop and
any available evidence. There is no inferred rollback. Host waiting validates
the subsequent sample against the actual wait endpoint, preventing a regressed
timestamp from claiming a wait longer than its surrounding measured interval.

The initial absent-method/public-route witnesses and adverse host cases are
retained. They exposed transaction admission, profile-loss state, exact budget
joins, unexpected guest progress during host waiting and final wrapper expiry.
An active DOS process descriptor initially caused ordinary timer stops to be
misclassified; the shared predicate and its failure/pass witness correct that.
The independent wait-end review retained a concrete pre-fix receipt with a
20 ms wait inside a reported 10 ms interval, then verified invalidation after
the fix.

The first 14-case native run passed 13 cases. Its remaining saved-script
comparison failed because raw stored DOS addresses are integers while the JSON
response formats them as hex strings; all timing values matched. The corrected
witness compares the full publicly formatted report and separately requires
exact raw artifact-to-journal equality. The host-wait witness now records one
real positive bounded sleep, its actual timestamps, no native continue, and
unchanged native time/counters. Its 300 ms setup lead is checked explicitly.

### Final local verification

| Selection | Result |
| --- | --- |
| Focused host clock-sync contract, including wait-end regression | 57 passed, zero skips |
| Retrace wait and existing passive retrace contract | 140 passed, zero skips: 62 new wait cases plus 78 existing cases |
| Public routes, whole-script preflight and shared stop classification | 40 passed, zero skips |
| Affected source regression selection | 1,087 passed, 5 optional skips |
| Combined source native clock/source-clock/input/audio/display/retrace/timing selection | 60 passed, zero skips |
| Fresh isolated installed-wheel affected regression selection | 1,076 passed, 5 optional skips |
| Fresh isolated installed-wheel combined native selection | 60 passed, zero skips |
| Retained DOSBox native predicate/first-effect/hook witness | 1 passed, zero skips |

Selections overlap. The five optional skips in each broader regression lane
require `FDISBULL_MACHINE_QEMU` for separate real machine-session checks; they
are not native timing passes. The combined native selections include all
14 new timing cases, with mandatory native admission and no skips. The installed
regression selection excludes 11 repository-only inventory/package tests that
passed in the source lane. Installed collection asserts the fresh private prefix
and cannot silently import the checkout.

The fresh wheel matches all 638 core payload files. Its SHA-256 is
`f065776953cb0a6ba76a5d96468773d8da54d873df25c009a8ae1d5886f037e1`.
The source distribution and tool ZIP are compared against all 1,576 tracked
payload files and all 21 authored paths, including this handoff and the new
timing guide. Distribution checks retain the tool-only boundary. Before/after
hashes freeze the 1,265 source-lane inputs, 638 installed core files and 612
copied test/support files. No live runtime input, database, emulator state or
game bytes are added to the authored patch.

Logs, JUnit, command manifests, input hashes, failure receipts, wheel and archive
checks remain under the private `takeover-validation/autosync-*` prefix;
`autosync-runtime` contains the finite validation/publication drivers. Native
source/build and retained backend provenance remain in the preceding runtime
directories. Each material phase admits 2 GiB expected growth above a 20 GiB
free reserve. The final authored tree is checked against these exact runtime
and package identities before commit and GitLab readback.

### Native runtime and qualification boundary

This increment adds no QEMU patch. It reuses the exact QEMU 10.0.13 clock,
media, input and retrace chain already qualified in the previous entry. The
four-patch reproduction receipt still matches all 25 final native source
paths, with zero patch offset/fuzz. The binary SHA-256 is
`5d202d2ec57d596351381d7fc1df67211c4d0727ad667119183d41b450c96565`.
The existing prepared FreeDOS baseline and firmware remain private runtime
inputs; the Linux native fixtures use bounded pipe transports.

The new native witnesses cover busy and CLI/HLT retrace waits, actual CR10 ABA
writes, an earlier breakpoint, busy/HLT/PIT catch-up, cumulative native progress,
host-only waiting, excessive lag, scheduled-input cancellation, real DOS exit,
SQLite journal failure, JSON/script routing, reopened evidence and refusal under
the default standard clock profile. They do not simulate native execution.

All 127 default-promotion entries remain unqualified. DOSBox remains the default
and both retained selectors stay available. Legacy timed helpers, full guest
frames/VBlank, frame-edge input, audio drain/playback alignment, additional sound
devices, QEMM/real-game compatibility, checkpoints, layers and histories remain
separate work. Windows/macOS are unverified. The macOS `/Volumes/...` mirrors
are unavailable here; this Linux checkout and GitLab are the publication targets.
No hosted CI, release, shared installation or merge is implied.

## 2026-11-08: passive precise VGA retrace observations

Re-read GitLab after the requested publication retry: MR !117 and its source
branch already pointed to `652394fd313a0c33e7b8c30bf9b138928b0d2773`, with
the previous source-clock handoff present. No uncertain write was replayed.
Continued from that published tree on the same source branch, stacked target
and draft MR. This increment adds an explicit stopped observation of QEMU's
precise VGA timing model; timing auto-sync remains deferred.

### Public behavior and model boundary

Select `qemu_clock='virtual', qemu_retrace='precise'` for a fresh paused PC
boot with the new [retrace extension](../native/qemu-retrace/README.md).
`retrace_observe(timeout_ms=...)`, JSON `debug-retrace-observe` and saved-script
`retrace-observe` reach the same machine-owned operation. The CLI exposes
`--qemu-retrace standard|precise`; `standard` remains the default. Raw factory
arguments use `clock_profile` and `retrace_profile`.

Each receipt records run and both clock epochs, native virtual nanoseconds,
exact primary VGA identity, model `qemu-vga-precise-fdisbull-v1`, raw timing
registers, cached timing parameters and a monotone timing generation. A stable
before/native/after clock bracket encloses the observation, followed by one
persisted `machine-retrace-observe` event. Supported phases include the modeled
position and retrace status bits. Uninitialized timing, enabled VBE and invalid
or wrapped legacy intervals return explicit unsupported evidence without
closing a sound owner. API availability and current phase eligibility remain
separate; some ordinary text modes have an unsupported interval.

The native opt-in is `-vga std,retrace=precise -global
VGA.x-fdisbull-retrace=on`. It requires the admitted virtual clock, one stopped
TCG CPU and the exact primary PCI `VGA` device at console/head zero. First
admission pins that device and prevents migration for the process lifetime.
It adds no serialization or cold-restore contract.

The property enables coherent timing updates at completed guest writes,
including CR10 and VBE/effective-SR1 transitions omitted by upstream refresh
paths. Generation advances when the returned raw/cache/initialization state
changes, so separate A-to-B-to-A writes cannot disappear between queries.
Already initialized no-op writes do not advance it. Ordinary VGA and ordinary
precise VGA without the property preserve their previous calculation and
status-read behavior.

Querying checks the expected cache without repairing it. It does not execute
the guest, advance virtual time, arm a timer, render, wait for an edge or read
guest status port `3DAh`. In particular it preserves the attribute-controller
flip-flop. The model retains QEMU's integer arithmetic and inclusive endpoints;
this is not a qualification of physical VGA accuracy or the full VBlank
interval. Timing generations exclude palette, page contents and other changes
that can affect pixels. A retained renderer publication remains separate and
can predate the timing observation.

### Failure and deadline boundaries

Strict host validation independently reconstructs the register-to-cache model
and phase arithmetic. Malformed receipts, changed timing under an unchanged
generation, backwards generations/time, device replacement and epoch loss
fail closed. Native queries also reject unsafe runstates, pending stops and
armed or fired clock budgets without consuming the budget.

One absolute observation deadline begins before lock admission and intersects
existing script, session, VM, QMP and GDB limits. Each previous limit is
restored separately. Whole-script capability, literal timeout and caller-owned
transaction checks precede earlier writes. A synchronous evidence write can
finish before a late timeout is reported; `error.result` retains the observed
receipt when available. Neither a timeout nor missing evidence authorizes
automatic replay.

### Verification and runtime recovery

The former thread's scratch tool paths were gone. A separate private Python
3.13.5 environment and verified NASM/mtools inputs restored finite Linux
qualification without changing a shared installation. The DOS baseline was a
surviving, hash-pinned, already prepared FreeDOS image from the earlier clock
tests, not a recovered original distribution image. Firmware was extracted
from the verified official QEMU archive. Private runtime inputs stayed outside
the checkout.

All four authored patches applied to the verified QEMU 10.0.13 source with
zero fuzz and zero offset. All 25 final changed native source paths matched
the separate source used for the successful fresh build. Independent native
and integrated public-surface reviews found no concrete blocker.

| Lane | Result |
| --- | --- |
| Focused host retrace contract and hostile receipts | 78 passed, zero skips |
| Public launch, CLI, JSON and script routes | 23 passed, zero skips |
| Affected source stock/public/process/script/deadline/inventory/package selection | 928 passed, 5 skipped, 109.16 seconds |
| New source native retrace witnesses | 8 passed, zero skips, 9.20 seconds |
| Combined source native source-clock/input/clock/audio/display/retrace selection | 46 passed, zero skips, 38.03 seconds |
| Isolated installed wheel: applicable stock/public regression selection | 917 passed, 5 skipped, 113.54 seconds |
| Isolated installed wheel: combined native selection | 46 passed, zero skips, 40.22 seconds |
| Isolated installed wheel: retained native DOSBox predicate/hook/reopen witness | 1 passed, zero skips, 1.35 seconds |
| Core source/wheel/installed payload identity | All 637 package files match |
| Source distribution and tool-source ZIP | All 1570 tracked payload files and all 22 authored changed paths match; tool-only distribution checks pass |

Selections overlap and are not a unique total. The combined native selection
contains ten source-clock, nine input, eleven clock-budget, five audio, three
display and eight retrace cases. The retrace witnesses compare against actual
guest `3DAh` reads, prove passive stopped/flip-flop behavior, cover CR10 and
unobserved A-to-B-to-A writes, validate VBE/invalid transitions, preserve
separate source/clock/renderer provenance through reopen, retain ordinary DOS
use and refuse armed budgets or lost epochs. Runtime lanes ran serially;
tested core, witness and native input bytes remained unchanged.

Five optional raw-machine boot/watchpoint/foreground tests were skipped in
each stock selection because `FDISBULL_MACHINE_QEMU` was not supplied. Unix socket creation is
restricted in this executor; the required native qualification uses pipes.
The skipped tests are not passing evidence. A frozen previous-wheel gap check
first failed on the absent `qemu_retrace` constructor argument; the new public
selection passes. No final test failure or timeout was hidden by a retry.

- Tested wheel SHA-256:
  `ca0038152f6ca6ea47fb4ca9d6aa836270f33481fd8fda0553519b1e0cfb67db`.
- New native QEMU SHA-256:
  `5d202d2ec57d596351381d7fc1df67211c4d0727ad667119183d41b450c96565`.
- Retrace patch SHA-256:
  `9647eb1c7afc14aeea3e1fb826a389c3865e5d3ab420b060a8d3d45319044a1c`.
- Retained DOSBox-X SHA-256:
  `795df754019b5e9876d68067cb8d91314b001f28c9c6964502dd57ef21adf79d`.

Private command, JUnit, payload and publication receipts use the
`takeover-validation/retrace-*` prefix. Native source/build/recovery proofs
remain under the separate `retrace-runtime` directory. Only authored source,
tests, patches, manifests and this engineering log enter Git.

### Remaining slice-4 gates

A later bounded gate can qualify retrace-edge barriers or an explicit
association with renderer publications. Neither is implemented here. Guest
frame completion, full VBlank semantics, natural instruction timing, input
consumption, frame-edge input, additional audio devices, legacy timed helpers
and timing auto-sync remain separate work. All 127 default-promotion entries
remain unqualified; DOSBox stays the default and both fallback selectors stay
available.

These are local Linux/pipe integration results, not hosted CI, a release or
QEMM/V86, real-game, Windows or macOS qualification. The earlier parallel
startup, large-MZ and DOSBox idle-trial timeout observations remain unresolved.
The configured macOS mirrors remain unavailable. No merge, release, shared
installation, runner or credential change is implied.

## 2026-11-08: clock-qualified source observations and queries

Continued from published head `341847d48f55c877b4db645c3c98a9c72beeafe8`
on the same branch, stack target and draft MR !117. This increment joins the
existing native virtual clock to the initial real-mode COM/MZ source collector
and its persistent event-query/search path. It changes host code only; the
previously built clock/media/input QEMU remains the native runtime.

### Public behavior

The explicit virtual process profile advertises `source_trace_clock`. Each
source event automatically carries a versioned `fdisbull-source-clock-1`
object identifying `QEMU_CLOCK_VIRTUAL`, run, host clock epoch, native epoch,
virtual nanoseconds and the separate instruction counter. Compact before/after
samples enclose MCB/PSP ownership checks, register/address observation and
instruction/source-byte qualification. Native time, counter and epoch must
remain unchanged throughout that bracket. The sampler shares the existing
clock-observation epoch and sequence without creating two extra journal events
per source row. Standard/instruction profiles and raw machine traces remain
clockless.

`virtual-time-range` is available through existing direct, JSON and saved-script
trace/query routes. It requires exact run and both clock epochs, with integer
half-open `start_ns`/`end_ns` bounds. Every live clock leaf is checked before
execution, even within Boolean branches; a saved script checks all literal
clock identities before earlier writes and rechecks at trace admission.
Trace-until result references remain unsupported, so obtain literal identities
from an earlier request. Live range matching observes debugger boundaries and
does not install an exact timer cutoff.

Saved query rows and search witnesses retain the clock. Storage validates
native-profile admission against the owning run, the source/entry lineage,
homogeneous stable brackets, monotonic time/counters and ordered observation
sequences. Invalid clock fields cannot be bypassed with a register-only query.
Missing clocks or a different identity are unknown retrospectively, and old
clockless artifacts remain compatible. Candidate source-site keys do not
include time, preserving cross-run comparison.

`trace(count=N)` retains its N preceding snapshots; the final observed endpoint
clock remains in `collector.current_stop.clock` and is exposed separately as
optional query `endpoint_clock`. It is not an N+1 event or search candidate.
A time predicate may match a final unbound runtime observation, as existing
explicit runtime predicates can; its source site stays unknown and its open
source window cannot narrow candidates.

### Failure and deadline boundaries

One absolute source-trace deadline starts before lock admission and intersects
the existing script, session, VM and channel bounds. Observation, stepping and
persistence use that same bound, then restore each previous limit separately.
A synchronous storage call may finish late, but cannot return successful trace
publication after the post-check. `ExecutionTraceError.result` preserves the
observed stop and any artifact IDs; an expired request before publication can
have no artifact. Native interrupt recovery retains its bounded cleanup role
without authorizing a new observation or publication after expiry.

Independent review added failing witnesses for an unscheduled step losing its
known GDB stop after register/journal failure, DOS return classification lost
on journal failure, and saved-script preflight/publication resetting the script
loop allowance. Their corrections preserve already verified stop evidence and
keep script admission on its original deadline. No execution or input is
replayed to reconstruct missing evidence.

### Evidence scope and next gate

An independent authored guest joins source timestamps to a real PS/2 make-byte
observation and retained red renderer pixel. These are separate observations
on one clock. Ordering alone does not prove input causation or consumption,
and equal nanoseconds do not establish callback order. Native counter values
are never converted into elapsed virtual time. Recorded GDB IRQ/timer masking
still applies; debugger-stepped intervals do not establish natural instruction
latency or architectural retirement.

The VGA seam review found that default QEMU retrace status toggles on reads,
while its opt-in precise mode derives a phase from virtual time without a
retrace event. A later bounded retrace primitive needs an explicit timing
model/admission and generation changes; a renderer snapshot does not establish
guest drawing completion. That work remains separate from the source-clock
join. Timing auto-sync, host pacing and adaptive correction stay deferred at
the user's direction. All default-promotion rows remain unqualified and DOSBox
remains the default.

### Verification

| Lane | Result |
| --- | --- |
| Final affected source: stock QEMU/FreeDOS, source traces, lifecycle, query/search, scripts, deadlines, inventory and package checker | 809 passed, zero skips, 114.28 seconds |
| Source native source-clock/input/clock/audio/display witnesses | 38 passed, zero skips, 30.77 seconds |
| Isolated installed wheel: applicable stock/public regression selection | 798 passed, zero skips, 103.51 seconds |
| Isolated installed wheel: source-clock/input/clock/audio/display witnesses | 38 passed, zero skips, 35.06 seconds |
| Isolated installed wheel: retained native DOSBox predicate/hook/reopen witness | 1 passed, zero skips, 1.33 seconds |
| Core source/wheel/installed payload identity | All 636 package files match |
| Source distribution and tool-source ZIP | All 1562 tracked payload files and all 23 authored changed paths match; tool-only distribution checks pass |

Selections overlap and are not a unique total. The 36 new hostile host-clock
cases are included in the source and installed stock selections. The native
selection has ten source-clock cases, nine input cases, eleven clock-budget
cases, five audio cases and three display cases. Runtime lanes execute
serially with required-runtime gates; native inputs and tested package bytes
remain unchanged.

Retained failing baselines matter: three native stop/journal witnesses and
two deterministic script-deadline witnesses first reproduced the implementation
defects above, then passed after correction. The first expanded source lane
was 807 passed / 2 failed because older tests still expected the discarded DOS
classification and the pre-native-adapter refusal text. The first installed
stock lane was 797 passed / 1 failed because its timeout assertion incorrectly
required the artifact to be absent; a late post-check had correctly retained
the actual artifact ID. Those tests now inspect the precise supported evidence.
Production code and timeout limits were not changed to satisfy the last
assertion. The final lanes above use the corrected tests.

- Tested wheel SHA-256:
  `323ab20264e568333faf249c2162c028a7b6407e618d69f4da944cfb27f9feeb`.
- Reused native QEMU SHA-256:
  `5b8b6c5df2602a34ea284a3efa7048bfacf68b3a1b83f2b9e793cac9c10480cb`.
- Retained DOSBox-X SHA-256:
  `795df754019b5e9876d68067cb8d91314b001f28c9c6964502dd57ef21adf79d`.

Private receipts use the `takeover-validation/source-clock-*` prefix in this
takeover workspace. They retain baseline failures, final command/input hashes,
JUnit results, package identities and publication guards. No runtime executable,
DOS image, FDB, original target bytes or private raw log is committed.
Local Linux/pipe evidence does not establish hosted CI, macOS mirrors,
QEMM/V86 task tracing, real-game parity or a release qualification. The earlier
parallel-startup, large-MZ and DOSBox idle-trial timeout observations remain
unresolved; the new retained DOSBox check does not explain those failures.

## 2026-11-08: native virtual-time input continuation

Continued from published head `5085371a57629d3102b1b3d51860b5af227249b8`
on the same source branch and draft MR !117. This increment schedules one
owned physical-input batch against the explicit native clock. Timing
auto-sync remains deferred: there is no host pacing, adaptive controller,
automatic resampling, repeated continue or guest-frame timing claim.

### Public behavior and ownership

The optional [input extension](../native/qemu-input/README.md) applies after
the exact existing clock and media patches to QEMU 10.0.13. With the explicit
`virtual` clock profile, `virtual_input_schedule` reports the three required
native API-1 commands. Queue keyboard or relative PS/2 mouse edges, call
`input_schedule(delta_ns)`, then choose an explicit bounded `run()` or
`clock_advance()`. Arming and observing never execute the guest.

The Python methods also have retained JSON routes `debug-input-schedule` and
`debug-input-schedule-observe`, and saved-script operations `input-schedule`
and `input-schedule-observe`. Existing queue/lease methods and
`input_cancel_pending()` own cancellation. Whole-script capability, literal
delay and transaction checks run before earlier mutations.

Each receipt records the unique token, owned epoch and batch sequence IDs,
requested start/deadline, actual terminal and dispatch times, observation time,
lateness and cancellation reason. `dispatched` means **the selected PS/2
handler callbacks and final sync completed**. It does not prove device FIFO
acceptance, guest consumption, a held-key action, or a completed frame. Full or
disabled PS/2 queues can ignore events, and remote mouse mode can retain
motion. These limits are explicit in returned receipts.

The pending batch remains immutable while bound. A validated dispatch commits
lease transitions once; repeated observation cannot commit or replay them.
The first actual stop cancels an unfired timer. Its unsent batch then requires
an explicit reschedule or cancellation before another run. Rescheduling uses
a fresh token and a fresh relative deadline. Cancelling a queued release
preserves the previously dispatched hold; it emits no synthetic key-up.
Stepping, traces and unbounded resume remain refused while input is pending.
The ordinary immediate-input path is retained, and legacy `timed_input`
capability remains false.

### Native ordering and failure boundaries

The native scheduler uses an ordinary `QEMU_CLOCK_VIRTUAL` timer so it also
participates in fixed-icount idle warping and can wake a halted CPU. It avoids
the legacy delayed-key helper. Under the big QEMU lock, it preflights the
entire batch before arming and before dispatch: exact realized PS/2 devices,
handler identities/callbacks, qcode mappings, an empty legacy keyboard queue,
no unsynchronized handler events, and every prefix of mouse accumulator
arithmetic. Only then are callbacks invoked and synced.

A pending debugger/native stop wins. A reached active clock-budget deadline
also wins, including equal input and budget deadlines regardless of insertion
order. A merely halted CPU remains eligible. Successful dispatch does not stop
the VM; the original budget, breakpoint, exception or DOS completion remains
the caller's stop. No uncertain attempt is retried.

One batch admits 1..256 events, with at most one edge per mouse button. Delays
are 1..60,000,000,000 ns without signed clock overflow. Tokens cannot be reused;
4096 successful arms exhaust the bounded process-lifetime history. Reset or
loss of the admitted clock profile/epoch invalidates the scheduler. Its first
successful arm blocks migration for the process lifetime; checkpoint/restore
and replay formats are not supplied by this slice.

Independent host review produced failing witnesses for shared-deadline loss
during post-stop QMP reads, dispatch receipts at the owned budget cutoff, a
failed script leaving newly armed pre-existing input live, and malformed UTF-8
reason bounds. The fixes keep one host/script deadline through scheduled
execution and reconciliation, bind the current budget token/epoch before
committing leases, close failed mutating scripts, and enforce the 256-byte
reason limit. A first owned cancellation must match the observed stop time;
later passive observations retain the frozen terminal time.

Additional failing witnesses exposed loss of already known stop evidence when
clock cleanup, DOS-return journaling or late persistence failed. Those paths
now retain `error.result`, including any validated input receipt, before
closing. Original native stop bytes survive even when register readback fails;
in that case classification is explicitly incomplete. Ordinary unscheduled
GDB timeout/interrupt recovery retains its previous behavior.

### Verification

| Lane | Result |
| --- | --- |
| Affected source, stock QEMU/FreeDOS, lifecycle, trace contracts, I/O, deadlines, inventory and payload checker | 328 passed, zero skips, 56.49 seconds |
| Final focused scheduled-input and clock host boundary checks | 80 passed, zero skips, 2.01 seconds |
| Frozen isolated installed wheel: stock QEMU and public boundaries, serial | 317 passed, zero skips, 56.87 seconds |
| Frozen isolated installed wheel: native scheduled input, clock and media, serial | 28 passed, zero skips, 25.60 seconds |
| Wheel/source/installed payload identity | All 635 package files match exactly |

Selections overlap and are not a count of unique tests. The final installed
lanes use the complete frozen host implementation, including the outer cleanup
evidence fixes. Their native selection contains nine new input, eleven clock,
five audio and three renderer cases. The 51 scheduled-input host cases are
included in the source and installed stock selections.

The nine new native cases independently observe keyboard make/break bytes
`1e 9e`, PS/2 movement/button packets `09 05 00` and `08 00 00`, IRQ1 wake-up
from `HLT`, an earlier breakpoint, equal/later input versus budget deadlines,
explicit rescheduling and cancellation without replay, wrong-token refusal,
reset invalidation, DOS exit/TSR, retained JSON and saved-script execution, and
reopened dispatch metadata. A renderer join checks a later publication in the
same epoch and an independently programmed pixel; it makes no frame or input
causation claim. The unchanged clock/media cases run alongside them.

Evidence is local Linux over pipe transport, using disposable owned VMs and
the explicit test-only FreeDOS 1.4 `SWITCHES=/F` baseline. Original authored
program and prepared boot-image hashes are checked. This run does not resolve
the earlier parallel startup failures, large-MZ startup timeout or retained
DOSBox idle timeout recorded below. No retry or production timeout increase
was introduced. Deliberate failing review witnesses and an initial test-command
filename error are retained separately from passing results.

Pinned identities:

- Input patch SHA-256:
  `11ace3ccd39b2a2e507917197980b0b9181b5de3901161b2362be6ea53cbe6bb`.
- Required unchanged clock patch SHA-256:
  `2127b71b7e45cc0e1a0351a405aed3b0a016e98af8d0540f74633c37b6b4dd4b`.
- Required unchanged media patch SHA-256:
  `ad20d1d0670dc5eae166dee1b6be58f6d0a9f8d2386646f12007f342dbcb15a6`.
- Tested native executable SHA-256:
  `5b8b6c5df2602a34ea284a3efa7048bfacf68b3a1b83f2b9e793cac9c10480cb`.
- Tested wheel SHA-256: `5d09079d3c63f3220fdacd791787c3623606ffa05dceaf1e4677f68b972463c6`.

The input patch adds seven changed/new source paths. Applying the complete
clock → media → input chain to the pinned official archive reproduces all
18 unique affected paths exactly, with zero patch fuzz. The private build
completed in 36.087 seconds; its prior tested media executable and original
receipt are retained. Patch source manifests pin the archive, dependencies and
each stage's bytes. Source-distribution and tool-source recipes include all
three patch packages; the Python wheel contains no emulator or DOS disk.

All 127 migration/default-switch entries remain unqualified and DOSBox remains
the default. Guest-frame/VBlank completion, legacy timed helpers, INT33/pixel
mapping, SB16/FM, clock-to-source-trace causality, checkpoints, histories,
QEMM/real-game compatibility, Windows and macOS remain open. Timing auto-sync
is deferred. No hosted pipeline, release, merge, shared installation or
credential change was performed. The configured Mac mirrors are unavailable.

## 2026-11-08: native renderer and PC-speaker continuation

Continued from published head `0edf5a81496e780b1a1f89bd6bd1289dc1e47326`
on the existing branch and draft MR !117. The user explicitly deferred timing
auto-sync. This increment adds independently controlled media observations on
the already admitted native virtual clock; it adds no host pacing, adaptive
clock controller, automatic resampling or synchronization loop.

### Public paths and actual completion boundaries

The optional [native media extension](../native/qemu-media/README.md) applies
after the exact current clock patch to QEMU 10.0.13. Renderer operations are
`display_start(period_ns=...)`, `display_observe()`, `display_stop()` and
`capture_display(name=..., after_update=...)`. They are available through
Python, retained JSON (`debug-` names with hyphens) and saved scripts. A new
window is empty. Its explicit virtual timer invokes the admitted standard VGA
renderer synchronously, copies all RGB rows while holding QEMU's big lock, and
only then publishes an ID and virtual timestamp. It retains the latest copy,
bounded to 16 MiB and 8192 pixels per dimension. The observation period is not
a claimed guest frame rate. Missed observations are skipped without catch-up
execution or host-time synchronization.

This proves **completed renderer updates**, not completed guest application
frames or VBlank. The authored witness deliberately pauses halfway through a
draw. A stopped `capture_surface()` sees the changed VRAM while the previously
published renderer copy remains unchanged; a subsequent explicit clock advance
can publish that same incomplete guest drawing. Receipts retain
`completed_guest_frame=None` and `guest_frame_id=None`. Publication age is
observable, and `after_update` rejects an unchanged window-local publication
without waiting or running the guest. Graphics-to-text dimension changes are
covered; this does not establish complete mode-transition or frame epochs.

Select `qemu_clock='virtual', qemu_audio='pc-speaker'` explicitly at launch to
enable `audio_start(max_frames=...)`, `audio_observe()`, `audio_stop()` and
`capture_audio(name=...)`, with equivalent JSON and script paths. The profile
uses QEMU's `none` audio driver, a 10 ms audio timer and 32,000 Hz mono unsigned
8-bit PCM. It configures only the PC speaker; Sound Blaster and OPL/FM remain
unqualified. The default audio profile is still `off`.

Native capture callbacks retain whole PCM frames, contiguous indices and their
actual virtual delivery timestamps. They do not establish precise sample onset
or that device queues were drained. Buffers can contain samples generated
before registration. Inactive periods do not create synthetic silence, so the
WAV's sample duration is distinct from elapsed guest time. Windows retain a
bounded prefix, at most 1,920,000 frames and 8192 callback records; overflow
counts rejected frames and refuses a complete WAV export. Stop detaches the
callback without flushing, advancing or resuming the guest.

Both observers own unique tokens and the current native clock epoch. Stop is
idempotent, retained fields freeze after stop, and a new window cannot adopt
earlier samples or pixels. The host rejects unsolicited windows, changed
retained bytes, malformed sizes/counters and inconsistent epochs. Exports
validate exact payload lengths, preserve pixel/PCM hashes and bracket reads
with an unchanged stopped clock. Reset invalidates both observers. Their first
use blocks migration for the process lifetime; no checkpoint/restore contract
is implied. All operations share the machine lock and saved script deadline.
An uncertain mutation or a start/stop receipt that overruns closes the owner.

### Clock defect exposed by media work

A new strict native witness found that an ordinary GDB continue, with no clock
budget armed, could still advance virtual time by roughly 54.9 ms on an
authored one-NOP path. The stopped-CPU flag was set before the main loop consumed
the debugger request, allowing an idle warp to the next ordinary device timer.
The earlier guard covered armed budgets only.

The clock patch now suppresses idle warping whenever an explicitly admitted
fixed-icount native-clock machine has a stopping/stopped CPU, regardless of
whether a budget is armed. It still allows a merely halted CPU to reach native
device deadlines. The new regression requires fewer than 100 counted
instructions and less than 100,000 ns across the short path; both pass without
relaxation. Existing CLI/HLT, PIT IRQ, early breakpoint/watchpoint, cancellation,
exit and TSR witnesses also pass. The original failing clock receipt remains
private. This correction does not diagnose unrelated historical host timeouts.

Independent boundary review also prompted stricter unsolicited-token refusal,
stopped-receipt freezing, exact P6/PCM length checks and retained-byte identity
checks. The first display pixel assertion assumed a BIOS palette value that
varied from the observed value. Its fixture now programs its own VGA DAC before
drawing and asserts exact full-scale colors; production rendering was not
changed to accommodate the fixture.

### Verification and remaining startup uncertainty

| Lane | Result |
| --- | --- |
| Affected source, stock QEMU/FreeDOS, lifecycle, I/O, deadlines, inventory and payload checker | 276 passed, zero skips, 121.92 seconds |
| Final public media/routes and hostile boundaries | 138 passed, zero skips, 19.91 seconds |
| Native media and clock, final source | 19 passed, zero skips, 63.36 seconds |
| Isolated installed wheel: stock/native I/O and public boundaries, serial | 154 passed, zero skips, 43.18 seconds |
| Isolated installed wheel: native media and clock, serial | 19 passed, zero skips, 85.46 seconds |
| Wheel/source/installed payload identity | All 634 package files match exactly |

Selections overlap and are not a count of unique tests. The native selection
includes five audio, three renderer and eleven clock cases. It covers a
programmed PIT speaker tone with an independently calculated frequency,
inactive output without synthetic silence, overflow, concurrent audio/display
clock and epoch observations, wrong-token refusal, reset invalidation,
publication freshness, partial drawing, dimension changes, passive exports,
saved scripts and reopened artifact metadata. Evidence is local Linux over
pipe transport with owned disposable VMs and the explicit test-only FreeDOS
1.4 `SWITCHES=/F` baseline. Original source and boot-image bytes are preserved.

The initial installed suites ran concurrently and are retained as failures:
**153 passed, 1 failed** in the stock/public selection and **18 passed, 1
failed** in native media/clock. Both failures exhausted the existing startup
deadline before a media operation: one while awaiting the QMP greeting, the
other while awaiting the DOS loader report in fixture setup. The latter did
not reach its reset operation. Serial reruns used the same wheel, binaries and
deadlines and produced the passing results above. Resource contention is a
possible explanation, not an established cause. Parallel startup reliability
therefore remains unresolved; no automatic retry or larger production budget
was introduced. Earlier unexplained large-MZ startup and retained-DOSBox idle
timeouts remain separate observations without an assigned common cause.

Pinned identities:

- Official QEMU source archive SHA-256:
  `4a59b74dac7ead8b162a7c4595dcbbeebe989b90c89cfe6bb4dec5447342f6fa`.
- Updated clock patch SHA-256:
  `2127b71b7e45cc0e1a0351a405aed3b0a016e98af8d0540f74633c37b6b4dd4b`.
- Media patch SHA-256:
  `ad20d1d0670dc5eae166dee1b6be58f6d0a9f8d2386646f12007f342dbcb15a6`.
- Tested native executable SHA-256:
  `2c60e112a1ea4e48a44f6250a0a1f4b209b78d3fa425f55105dde7662c43918e`.
- Tested wheel SHA-256:
  `7732b3472ef950cfeaa42c31408d0f4d98601e043ee209b48ab3c0221c3fec96`.

Applying both patches in order to pristine official-archive files reproduces
all 14 affected source paths exactly. Manifests pin every stage and the media
patch's clock-patch dependency. Source-distribution and tool-source recipes
retain both patches, manifests and READMEs; the Python wheel contains no native
emulator. Private build, failure and successful test receipts remain outside
Git. The prior tested clock executable and its original receipt are preserved.

All 127 migration/default-switch entries remain unqualified. Guest-frame and
VBlank completion, SB16/FM, timed/frame-edge input, pixel/INT33 mapping,
clock-to-source-trace causality, legacy guest_ms, checkpoints, histories,
real-game/QEMM compatibility, Windows and macOS qualification remain open.
Timing auto-sync is explicitly deferred. No release, hosted CI, merge, shared
installation or credential change was performed; Mac mirrors remain unavailable.

## 2026-11-08: native virtual-clock continuation

Continued from published takeover head
`16bafd40dd89a23f5bfc31130aae1a495e272c74` on the existing branch and MR !117.
The source now provides the explicit `qemu_clock='virtual'` profile and
`clock_advance(delta_ns, timeout_ms=1000)` through Python, retained JSON
(`debug-clock-advance`) and saved scripts (`clock-advance`). The default and
stock `standard`/`instruction` profiles remain available.

### Native boundary and ownership

The separately built QEMU 10.0.13 extension lives as authored source changes
under [native/qemu-clock](../native/qemu-clock/README.md). It adds ordinary
in-band QMP query/arm/cancel commands with API version 1. Observation reads
`qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)` directly, including idle timer advances;
`query-replay.icount` remains a separate counter. The admitted budget profile
is exactly one TCG CPU with fixed `shift=7,align=off,sleep=off`, without replay.
An incompatible executable is refused before a new paused guest can execute.

One call arms one ordinary native virtual timer and issues one existing GDB
continue. It keeps the original breakpoint, watchpoint, DOS exit/TSR and
physical-input result. Its token-bound receipt distinguishes start, requested
deadline, actual firing, stopped time, elapsed time and overshoot. No exact
arbitrary-nanosecond cutoff or cycle accuracy is claimed. A timer firing can
coexist with another native stop, and accepted input still does not imply
guest consumption.

The vCPU timer callback records time, stops the current CPU and queues a
private stop request. The main loop consumes it outside timer dispatch;
existing debugger requests take precedence. The native stop observer disarms
the timer, latches stopped time and consumes that private request. Cancellation
must identify the same token and confirm no pending request. Unknown arm,
execution, cleanup or evidence persistence closes the owner without replay.
Reset and unsupported state transitions invalidate the native epoch. The
first budget installs a process-lifetime migration blocker; this adds no
checkpoint compatibility.

The extension's own stop uses `RUN_STATE_PAUSED`/GDB SIGINT. Genuine debug
traps retain SIGTRAP. Host breakpoint matching now requires trap evidence,
preventing a timer pause at a breakpoint address from inventing a breakpoint
or invoking the reserved DOS parent-return handler.

One absolute host deadline covers lock admission, existing shorter VM/channel
or script limits, debugger initialization, arm, continue, register/process
readback, cleanup and evidence persistence. DOS completion callbacks now
retain those incoming bounds. GDB's existing five-second interrupt recovery
cannot authorize a new run or fresh clock cleanup after expiry. A surface
capture in the virtual profile checks both the direct clock and the separate
instruction counter while retaining `completed_guest_frame=None`.

### Problems found and corrected

Independent review found two host-boundary issues before publication: native
channel deadlines were initially applied only after lock acquisition, and a
PC match alone could assign a breakpoint ID to a timer stop. The corrected
admission and signal checks have dedicated deterministic regressions.

The first actual native run was **6 passed, 2 failed**, zero skips. Busy,
CLI/HLT and PIT IRQ witnesses passed, but early break/watchpoints latched a
clock equal to the armed deadline without firing the budget timer. Exact
QEMU source inspection established why: `cpu_handle_guest_debug()` sets the
CPU's stopped flag and queues a debug request; `main_loop_wait()` can attempt
an idle warp before `main_loop_should_exit()` consumes that request. An armed
budget timer consequently became the warp destination.

The final patch suppresses that warp while its own stop is pending, or while
a budget is armed and a CPU has `stop`/`stopped` set. A merely halted CPU can
still advance through native device deadlines. The original failing tests
remain strict: the early authored writer must stop before the requested
deadline, its virtual interval must equal its short observed instruction
interval, and a later ordinary run must pass the cancelled deadline without
a phantom stop. Both cases pass on the corrected binary.

An added reset probe initially encountered the production `-no-reboot`
policy, which terminates QEMU on reset. The probe now explicitly selects
QMP `set-action(reboot=reset)` only for that test, then verifies an actual
native reset invalidates the epoch and closes host ownership. Production
launch options were not changed to accommodate the probe.

### Verification and reproducible inputs

| Lane | Result |
| --- | --- |
| Affected source, stock QEMU/FreeDOS, I/O, DOS lifecycle, deadlines and inventory | 205 passed, zero skips, 98.96 seconds |
| Final public-route and hostile clock-boundary checks | 68 passed, zero skips, 6.22 seconds |
| Corrected native virtual-clock suite | 10 passed, zero skips, 34.91 seconds |
| Isolated wheel: public routes, deadline/surface checks, doctor and stock native I/O | 103 passed, zero skips, 50.44 seconds |
| Isolated wheel: corrected native virtual-clock suite | 10 passed, zero skips, 37.83 seconds |
| Package-payload checker tests | 5 passed, zero skips |
| Wheel/source identity | All 632 package files match exactly |

The lanes overlap and must not be summed as unique tests. The final native
suite covers paused stability; repeat budgets; busy execution; CLI/HLT idle
time independent of icount; programmed PIT/IRQ wakeups; early execution/data
stops; physical-input receipt preservation; cancellation before execution,
wrong-token refusal and idempotent acknowledgement; reset invalidation;
normal DOS exit/TSR; public JSON and persisted scripts; and a stopped virtual
clock/surface bracket. All tests use owned disposable VMs and preserve source
executable/disk bytes. This is local Linux/pipe evidence on an explicitly
prepared FreeDOS 1.4 baseline with `SWITCHES=/F`.

Pinned authored/native identities:

- QEMU official source archive SHA-256:
  `4a59b74dac7ead8b162a7c4595dcbbeebe989b90c89cfe6bb4dec5447342f6fa`.
- Final source patch SHA-256:
  `d28b9bff0be0d996084ecb52387ac7292064ab1edde2d233fa6c1156b33e96ad`.
- Corrected QEMU executable SHA-256:
  `7e4692ce38bcbab38809c48fb8a8fa9a386fa3b46c76b3207b9cc2318e4747c9`.
- Tested Python wheel SHA-256:
  `e9716f31c8c62e7224196979bd2018e7bbc27999d5c87b533a36f44cd0867131`.

The six upstream/patched file hashes and archive identity are in the native
source manifest. Patch application against pristine official-archive files
produced all six expected hashes. The private build used verified Debian
dependency archives, a bounded six-job build and no global installation.
The initial build took 150 seconds; the corrective incremental build took
11 seconds. The native README contains the source verification/build recipe.
Source-distribution and tool-source package recipes now retain the patch and
manifest; Python wheels contain no emulator binary.

Private build/initial failure/final test receipts remain under
`clock-runtime/` and `takeover-validation/` in this takeover workspace. They
are not published with vendor images or runtime databases. Source and the
sanitized engineering findings belong in Git. Hosted CI, release tagging,
merging and shared installation were not performed. Mac mirrors remain
unavailable here.

Completed-frame ownership, audio timing, timed/frame-edge input, pixel/INT33
mapping, clock-to-source-trace causality, checkpoints and later workflows
remain open. The 127 migration/default-switch entries stay unqualified. The
earlier unexplained large-MZ startup and retained-DOSBox idle timeouts remain
recorded separately; this work does not claim to have diagnosed them.

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
