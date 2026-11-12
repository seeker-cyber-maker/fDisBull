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
| 2. DOS process and drivers | Real DOS COM/MZ loading, loaded-source and PSP identity, termination versus residency, explicit driver observations; planned bundled FreeDOS and automatic directory workspace | Real DOS loader and independent COM/MZ/TSR witnesses; no fabricated PSP or inferred successful driver load; separately qualify runtime packaging, directory mapping and preservation of original files |
| 3. Trace and events | Source-bound traces, execution-event searches and entry/transition predicates | Correct mapping across relocation, overlays and mode changes; completed versus attempted execution kept distinct |
| 4. Clock, media and input | Guest-time control, coherent frames, audio and physical input | Defined clocks and completed-frame evidence; no claim of cycle parity from a screenshot |
| 5. Checkpoints | Native save/restore, Anchor Stones and restore epochs; planned filesystem generations and file-service state | Cold reopen, complete machine/device state and explicit compatibility checks; file-aware restore binds the matching base, layers and handles |
| 6. Layers and block services | RAM/fetch layers, priorities, hooks and UDL/UIL host services; planned copy-on-write file layers | Correct fetch/data and filesystem views, invalidation, effect ownership, synchronization and fallback boundaries |
| 7. Histories | Rewind, deltas, frame history and comparative trials; planned file-layer branching | Histories remain bound to the right source, machine, epoch, file generation and layer selection |
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
| Directory layers and open files | Guest writes, file names, directory searches and open-handle positions belong to one filesystem generation. Preserve original host files and restore the file view together with the VM; a disk-image overlay alone does not capture a host file service. |
| Partial control operations | A timeout can occur after a command took effect. Bound operations, record their disposition and close an uncertain control channel; do not automatically retry memory writes or process starts. |
| Multiple clocks and host effects | CPU progress, PIT/IRQ timing, audio duration and Python wall time do not advance together. Later host services need an explicit clock and ownership contract, including cancellation and desynchronization policy. |
| Paused input and cross-channel ordering | Stock QEMU rejects paused physical input, and a successful paused send-key did not deliver in the native witness. Queue in the owner, dispatch at most once during GDB continue, and retain the original stop; acceptance is not consumption. |
| Instruction counting and idle time | Fixed icount can observe machine progress, but HLT timer warps advance virtual time separately. Never multiply the counter into a generic guest clock or promise an exact live count stop from replay-only commands. |
| Layer selection and translation caches | Changing executable overlays must invalidate translated blocks while preserving required data views and priority rules. Parallel timing-only execution must not duplicate visible effects. |
| Checkpoint portability | QEMU and DOSBox state formats are unrelated. QEMU snapshots also depend on executable, machine and device identities. Require native cold-restore tests rather than treating saved metadata as restored state. |
| Windows and additional architectures | SMP, threads, interrupts, memory ordering and architecture-specific traps make a DOS-only global stop insufficient. Keep machine, OS/process and target contracts separate. |
| Runtime and host variability | Firmware, QEMU feature selection, Unix socket restrictions and macOS behavior vary. Discover capabilities and record exact runtime evidence; a Linux pipe result does not qualify every host. |
| Workspace resets and publication | Scratch inputs and receipts can disappear between turns. Keep this authored log and source in GitLab, record private runtime provenance without uploading vendor images, and re-establish evidence after reset. |

## Planned bundled FreeDOS and layered directory workspace (2026-11-11)

This user-requested addition is planned work across slices 2, 5, 6 and 7. It
does not advertise a current capability or broaden the existing checkpoint
receipts. The current native route already separates a COM/MZ target from its
caller-supplied DOS boot disk; this addition supplies a reusable bundled runtime
and an automatic directory workspace above that foundation.

### Bundled runtime and automatic directory access

- Package a small, ready-to-boot FreeDOS system with the required shell,
  drivers and fDisBull helpers as a versioned runtime component. Pin the
  distribution/package inputs, build recipe, firmware and output identities;
  retain license notices and corresponding source requirements. Keep game
  inputs and session states outside the tool/runtime packages. The
  [official FreeDOS distribution](https://www.freedos.org/download/) is the
  upstream input; no runtime image is built by this plan update.
- Use an immutable system image for `C:` with a private writable disk view per
  session. Starting the runtime requires no DOS installation per target. Keep
  the VM owned by the live server/context; retain cold restoration as a
  separately verified path rather than requiring an always-running service.
- Capture and resolve the CLI/Python caller's working directory at the launch
  request boundary, before changing to any private runtime directory, and expose
  it automatically as the guest workspace, proposed as `D:`. An explicit
  directory override selects another root. JSON/server requests use an explicit
  root or the owner's recorded startup workspace; report that choice and never
  infer a remote caller's working directory. During DOS startup, select the
  mapped drive and working path before executing the target so relative asset
  reads and saves use that workspace. Discover its files within declared
  count/size limits without requiring a manual per-file upload list. Record the
  resolved root, membership, DOS name mappings, mode and source identities before execution.
  Never silently omit an unsupported entry or expose parent directories through
  aliases or symlinks. Define case, 8.3 alias, attribute and timestamp behavior.
- Supply guest read/write access through a filesystem bridge/redirector or a
  qualified private FAT-image path. Ordinary DOS reads and directory listings
  observe the composed workspace; raw BIOS/disk access requires an admitted
  private block-device view and must not bypass original-file preservation.

### Preserve originals with copy-on-write file layers

Both file modes keep the analyzed executable and surrounding files present at
admission unchanged on the host. Guest read/write
access applies to an effective view: immutable or guarded base content plus
ordered file layers. A write stores changed ranges in the active layer;
creation, extension, truncation, metadata changes, rename and deletion are also
layer operations. Deletions use tombstones and rename updates the namespace
atomically. Subsequent reads, executable loads and directory enumeration must
see the same composed state. Provide explicit base, effective and difference
inspection, plus export to a new destination. Applying changes back to original
paths is a separate, guarded user-authorized operation.

Reuse the existing code-layer principles: stable identities, ordered views,
base-content guards, paused transitions and retained earlier versions. File
layers need their own filesystem contract rather than the same-size byte-patch
schema. A file-layer change does not rewrite already loaded guest RAM or
silently rebind the analyzed source. Record effective file identity and source
mapping when DOS loads it; invalidate affected bindings when that view changes.

An active generation may buffer dirty chunks and namespace changes in bounded
host memory. Seal immutable generations at declared boundaries and branch from
an earlier generation on the next write after rewind. Share unchanged chunks
instead of copying the whole directory per checkpoint. Persist sealed payloads
and journals in the private external object store when cold restoration is
requested; permit bounded spill for large layers. State the durability boundary
for volatile writes, flush/close and saved checkpoints. RAM buffering alone
does not make a saved state durable or establish a rewind performance gain.
Apply storage admission before runtime-image creation, base capture, spill or
other material growth; keep these outputs off internal temporary storage.

### Keep newly created saves across rewind

New guest-created saves and output files have a separate persistence option
from protected pre-existing inputs. Support an explicit keep/export operation
and an opt-in policy for selected new-file paths or patterns. A selected output
can be physically saved to a private host destination, including the selected
target directory, so the user can keep it after rewind or session exit.
Other new files remain in the ordinary rewindable layer. Deleting and recreating
an original path does not turn it into a new-file exception; the admission
inventory and original identity still protect it.

Keep only a completed, flushed/closed output or a separately qualified coherent
capture. Seal its layer revision, retain exact bytes in the durable private
store, and atomically create the chosen physical destination without replacing
an existing file. Check host path containment, case/8.3 aliases and symlinks.
The keep operation refuses existing destinations; overwrites use the separate
guarded, user-authorized apply operation. A partial or uncertain export is not
a kept save. Record guest path, source layer
generation, size/hash, destination and durable completion. These private saves
remain outside Git and tool/runtime packages.

Pinned payloads and successful physical exports have a lifetime independent
of the rewind cursor. Rewind neither deletes them nor silently inserts their
later bytes into the historical guest view. Restore the saved namespace and
file generation; make a kept save available there through an explicit import
or refresh into a stopped session, with collision/open-handle checks and a new
child layer revision. This is a recorded branch from the restored state.
An export into the mapped host directory is a new host revision; live mode
must reconcile it without duplicating the active overlay, and restoration must
retain its pinned base until a deliberate refresh admits that newer revision.
Report physical persistence separately from visibility in the current guest.

### Live and checkpointed file modes

| Mode | Base and host changes | Guest writes and restoration |
| --- | --- | --- |
| Live layered workspace | New opens or a controlled refresh can observe current host files. Pin each open file's content revision as well as identity; retaining a host file descriptor alone does not freeze its bytes. External changes create a new observed base revision; conflicts require explicit reconciliation and invalidate incompatible history. | Writes immediately affect the session's effective layer and are inspectable/exportable without changing originals. File-aware checkpointing must first retain a consistent exact base, pinned handle revisions and the matching sealed layer generation; otherwise report/refuse that capability. |
| Checkpointed layered workspace | Freeze directory membership, content and relevant metadata at admission, using a private content-retaining snapshot/store. Hashes alone cannot reconstruct files after the host changes them. | Writes create private layer generations. Anchor Stones and admitted histories restore the pinned base and layer generation together with the VM, including after the original process closes. |

Use checkpointed mode as the proposed debugger default; select live mode
explicitly. Both modes satisfy automatic guest read/write access while
preserving original files. Host tools inspect a separate effective working view
or an export. The keep option above can create physical new saves; writes to
pre-existing files remain layered. No background merge into original files is
implied.

### Anchor Stones, rewind and consistency

Pause guest execution, drain in-flight file operations, flush required payloads
and seal a filesystem generation before committing a file-aware checkpoint.
Pausing the guest does not stop host writers. Capture the live base using an
atomic host snapshot or a protocol that verifies stable directory membership,
metadata and content revisions before and after capture. Refuse a changing or
unverifiable capture without replaying file mutations. Retain each open handle's
actual base revision even when a newer host version now has the same path;
checkpointed-mode admission needs the same consistent-capture guarantee.
Bind its VM/disk state to runtime identity, base snapshot, layer stack/root,
namespace generation and any host file-service state. Preserve DOS handle
identity, offsets, access/sharing modes, locks and directory-search cursors;
guest-side state alone does not capture a host broker. If the selected bridge
cannot restore an open-handle case, refuse that checkpoint rather than
certifying an inconsistent restore. Publish the checkpoint only after every
component is durable and verified; a failed or partial restore must not resume.

Rewind selects a recorded VM/filesystem boundary and creates a child branch
when execution continues. Keep later generations as immutable evidence. Merely
popping a file layer while CPU/RAM and open handles describe its newer state
is a partial experiment, subject to explicit admission and history invalidation;
it is not a full rewind. Reordering/disabling layers requires a stopped guest,
dependency and base guards, and coherent handle/namespace state. Existing
artifacts retain their current restoration scope until the new format and
native witnesses qualify the wider contract.

QEMU already supports private disk-image snapshots, but a block overlay does
not automatically virtualize host directory operations. Its
[writable virtual FAT mode](https://www.qemu.org/docs/master/system/images.html#virtual-fat-disk-images)
is documented as beta with restrictions on snapshots, `loadvm` and concurrent
host writes. It may support a bounded prototype; it does not establish this
layered directory or checkpoint contract. Compare a DOS redirector/file service
with a private FAT image plus controlled import/export before selecting the
implementation. Measure capture, write, seal, restore and branch costs.

### Required implementation and qualification

1. Build and verify the redistributable FreeDOS runtime, source/notice manifest
   and installed selector independently of game inputs. Keep the current
   caller-owned boot-disk route available during qualification.
2. Implement automatic root discovery and the effective read/write file view;
   witness CLI/Python/server root selection, DOS active drive/path, relative
   asset reads and saves, binary files, subdirectories, DOS name collisions,
   resizing, rename/delete and unchanged pre-existing files after close or
   failure. With new-file persistence selected, verify only the requested
   output paths are physically created.
3. Qualify both modes with external host changes, guarded open files, layer
   enable/disable and branch behavior, explicit export, and bounded storage
   exhaustion. Record the selected driver/file-API compatibility limits.
4. Cold-restore an Anchor Stone in a new process with file writes and open-handle
   state; then rewind and branch across create/write/truncate/rename/delete.
   Verify CPU/RAM, effective file contents, namespace and handle positions at the
   same boundary, plus preserved originals and retained later generations.
   Keep a new save physically, rewind to before its creation, and verify the
   physical copy survives while historical guest membership remains correct;
   then explicitly import it into a new branch. Exercise both the manual keep
   action and opt-in new-file policy, destination collisions, incomplete saves
   and interrupted exports.
5. Inject concurrent host changes during base capture, interrupted file
   operations, failed flush/seal/restore, missing or corrupt layer payloads and
   base-identity conflicts. Preserve incomplete evidence and refuse unsafe
   continuation without replaying uncertain writes.
6. Integrate filesystem generations with source traces, code/RAM layers,
   scripts and histories; update capability inventory and package/native
   qualification only for behavior actually demonstrated.

## Current handoff

- Branch: `agent/qemu-sunset-284eb73c`.
- Draft integration MR: [!117](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/117).
- Stack parent: `agent/execution-event-search-284eb73c` / [!113](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/113).
- Restored baseline: `3b7ffedd848736174ad055b506bbbe44567ea6a2`.
- Latest implemented path: the earlier slice-4 source-bound traces, native
  virtual-clock/input observations, bounded media windows, retrace and
  renderer probes, declared mouse motion and cooperative clock sync now sit
  alongside bounded real-mode COM/MZ checkpoints, instrumented checkpoint
  restore, remapped protected/V86 task ownership, task-private RAM/fetch layers
  and hooks, native CPU task contexts, and opt-in real-PIC task preemption.
  The N19 increment adds nested master/slave PIC ownership and partial-EOI
  checkpoints; its authored source and limits are recorded below.
- Takeover: `chat:54d0a46c7daf` recovered the unpublished slice-4 commit
  `6434474b0318bf9ee6d7d3d1b2ea094a3a81629d` from the previous checkout. The
  existing branch, originating handoff marker and stacked MR target are retained.
- Latest clock/memory-rule continuation: the bounded periodic `memory_rule_run`
  route includes explicit RAM-view identity and guarded rule-owned overlays for
  task-private or ordinary RAM/code stacks. Native hook dispatch shares the
  bounded virtual-clock interval and stops before another tick on a hook hit.
- Next integration gates: broader layer/task/clock workflow qualification,
  frame/VBlank semantics, additional
  audio devices, coordinate/frame-bound clicks, guest text consumption/layout,
  frame-edge input, pointer calibration and input-to-source causality remain
  open slice-4 boundaries. This incremental clock/memory-rule work is a
  prerequisite gap before the dependency-ordered Histories slice; Histories
  remains pending until its checkpoint, layer, clock/input and trace
  dependencies are separately admitted.
- Planned environment/filesystem addition: bundled FreeDOS, automatic current
  directory access, both live/checkpointed copy-on-write file views and optional
  physical persistence of new saves are specified above. Runtime packaging,
  the directory bridge and file-aware
  checkpoint/history qualification remain pending; this documentation adds no
  implemented capability or passing result.
- Defaults and rollback: DOSBox remains the default; both DOSBox selectors stay
  available. Native default promotion and DOSBox removal are blocked.
- Publication: authored source and this maintained engineering log belong in the
  branch. Vendor images, game bytes, runtime databases and emulator states stay
  outside Git. Routine publication must not start hosted CI.
- Integration snapshot before the periodic-rule continuation: the existing MR
  source and both local-hub/GitLab branches were fast-forwarded to
  `28108fe746fc9838e06c3291d268f809e0acc283`, carrying the verified N12–N19 work
  and reconciled handoff. MR !117 remained draft with target
  `agent/execution-event-search-284eb73c` /
  `089c1841c415eb2b5cdfa90d03b6291a07f73919`. The source ancestry required no
  rebase or force push. Earlier Mac-mirror availability notes describe the
  prior Linux session. Routine publication uses `ci.skip`; no CI was run.

## 2026-11-10: publication-bound declared mouse displacement

Continued from the verified VGA-configuration publication
`804c507d652312fb160bb027e0cdcfe38ac7ecb6`, retaining `agent/qemu-sunset-284eb73c`, draft MR !117 and target
`agent/execution-event-search-284eb73c` /
`089c1841c415eb2b5cdfa90d03b6291a07f73919`. The preceding dated entries, their qualifications and
retained failures remain history; their test counts are not new executions.
The next gap was the interval between a host-side image-to-relative conversion
and its eventual native callback. A stopped configuration observation alone
cannot guard that interval while the guest executes.

### Public contract and declared scale

The optional eleventh native extension adds the separate
`mapped_mouse_motion` capability and:

```python
mouse_move_mapped(
    dx_pixels, dy_pixels, *, counts_per_pixel,
    window, update_id, configuration_generation, timeout_ms=1000,
)
```

JSON uses `debug-mouse-move-mapped`; saved scripts use `mouse.move-mapped`.
The route requires the existing explicit virtual/precise profiles, all native
clock/input/display/retrace/configuration commands, and the new
`x-fdisbull-arm-display-motion` command. Ten-layer executables retain their
existing operations and refuse this helper. No new launch option, legacy
DOSBox stub or absolute-pointer facade is introduced. The maintained public
contract is in [the migration guide](DOS_QEMU_MIGRATION.md#move-with-a-declared-image-to-relative-scale)
and [native README](../native/qemu-display-motion/README.md).

The request is a relative displacement expressed in retained-image pixels.
It supplies no pointer origin or absolute destination. `counts_per_pixel` is
exactly an `x`/`y` dict, each value a two-integer list containing a signed
nonzero numerator and a positive denominator. Its units are QEMU REL input
events per retained-image pixel: positive x is right and positive y is down.
QEMU negates relative y in the PS/2 accumulator, so the declared units are
distinct from raw wire y counts.

Pixel components are strict integers in -8191..8191 with a nonzero pair.
Numerator magnitudes and denominators are bounded to 1..32767. Each converted
axis must divide exactly and fit -127..127; native code independently enforces
that count bound and a nonzero pair. There is no rounding, clipping, splitting
or implicit retry. Each displacement magnitude must also be less than the
corresponding retained image extent. This bounds a displacement, not endpoints
inside the image. The host freezes the nested declaration before deriving
counts or making native calls, so the accepted receipt retains the declaration
that produced those counts.

The scale remains a caller assertion about the selected guest driver or
application. Successful arithmetic and binding checks cannot verify that
assertion, guest acceleration, clipping or actual pixel travel. The narrow
count bound also does not establish one-packet delivery when residual movement,
device mode or queue capacity is unknown.

### Atomic publication/configuration binding

Admission requires an owned project outside caller transactions, an empty
physical input queue, no owned held leases and no other bound schedule. The
retained renderer window must already be explicitly stopped and nonempty.
The requested window, update ID and configuration generation must match a
fresh validated observation, whose current and published VGA configurations
have equal generation and raw values. The operation neither stops the observer
nor refreshes or manufactures a publication. An active observer can republish
even unchanged pixels, so it does not provide this stable publication anchor.

Native arm admission compares every expected field atomically: native epoch,
stopped time, exact VGA device/model, configuration generation, display token,
update ID, publication timestamp and dimensions. The accepted `motion`
descriptor retains signed relative counts, the fixed delay and the full
`armed` display/current/published observation. Before any relative callback,
an internal BQL-only helper takes a fresh observation of the already admitted
owner. It supports the running callback without invoking the public stopped
query, admitting another device, initializing a display timer or rendering.
The optional `checked` observation is retained once and never refreshed.

Impossible histories are rejected before choosing a cancellation reason.
These include native identity or generation regression, changed raw values
under one generation, contradictory current/published time and generation
ordering, regressed window history, and changed dimensions, publication time
or full published stamp under one publication identity. A coherent state-only
observer transition can cancel; it cannot hide a contradictory stamp.

Among otherwise valid binding changes, current configuration generation has
priority. An increase cancels with
`display-motion-configuration-changed`, including A-to-B-to-A even when raw
values return to the original values. With unchanged configuration, a replaced
window/publication or resumed observer cancels with
`display-motion-publication-changed`. No relative callback starts after a
failed binding check. Callback evidence is checked against both the arm and
already observed VGA/display history without replacing the live observation
frontiers. Equal virtual timestamps do not order paused QOM changes; equal
generations and publication identities still require immutable values.

### Passive timing, explicit execution and recovery

The operation arms one attempt due 2 ms of native virtual time after acceptance. Its one owned batch
contains nonzero x first and nonzero y second, followed by one final sync.
`event-count` is exactly one or two, and no zero-valued callback or button edge
is invented. Arming does not execute the guest. The caller selects `run`,
`clock_advance` or the existing cooperative `clock_sync_step` to execute it.
The helper does not start timing auto-sync or introduce a background loop.

Native pending-stop and equal/reached clock-budget precedence runs before
the guard snapshot. An equal deadline wins in either timer insertion order.
The first actual VM stop consumes an unfired attempt. A clock-sync step can
supply one bounded execution attempt, but a step that stops too early does not
automatically continue, rebase or replay motion. Completion does not itself
stop the guest. See [the timing guide](DOS_QEMU_TIMING.md) for the existing
single-correction auto-sync and stop/ownership contracts.

A cancelled mapped plan retains its unsent records and protected binding.
Neither `input_schedule()` nor `input_schedule_retrace()` may convert those
records into unguarded input. Recovery requires `input_cancel_pending()`
followed by a fresh mapped request and fresh caller expectations. The operation
creates no held-button lease; pre-existing guest/device buttons remain unknown.
All native input modes share query/cancel, token history and migration
restrictions. The optional `motion`, `retrace`, `press`, `typing` and `click`
descriptors are mutually exclusive; only an accepted replacement arm clears
the preceding descriptor.

The top-level receipt remains `fdisbull-qemu-scheduled-input-1`. Its
`fdisbull-mapped-mouse-motion-1` descriptor retains the pixel request, exact
ratio declaration, derived REL counts, full pre-arm VGA receipt, immutable
native arm/check observations and `binding_verified`. That flag is true only
for validated dispatch. Terminal observations remain frozen through later
queries and journal reopening; reopening restores evidence, not live ownership.

Direct signatures and visible script literals validate before lock/I/O or
earlier script effects, including known-axis arithmetic when another axis is
a reference. Resolved values validate before deadline clamping. One shrinking
host allowance, default 1000 ms with strict range 1..600000, covers admission,
observations, arm, validation, journal persistence and final return. Known
pre-arm binding refusals preserve a valid stopped owner. Uncertain or late
accepted arms, malformed native evidence and persistence failures close with
available evidence and no replay. Large JSON/script results may use the
existing `fdisbull-output-ref-1` delivery marker; read/export the retained
output artifact rather than repeating input to obtain an inline result.

### Independent guest and host witnesses

The authored COM fixture in `tests/support/qemu_mapped_mouse_fixture.py`
owns its PS/2 setup and IRQ12 handler. It verifies a separate initial
zero-motion packet and records bytes actually read by the guest. Its own
application policy moves two VGA pixels per horizontal count and three per
vertical count, beginning at a fixture-defined position. Separate gates and
fences distinguish packet receipt, application pointer commit and drawing.
The host's declarations account for the actual retained renderer extent;
the fixture does not consume the production planner's answer as its oracle.

The cases in `tests/test_qemu_mapped_mouse_native.py` independently specify
signed packet bytes, application positions and pixel markers. They include
positive, negative and single-axis displacement through explicit run, clock
advance and clock-sync execution. The deliberately wrong-scale/sign control
expects valid native binding and different application travel, while
`mapping_verified` and `target_reached` remain unknown. Other cases retain an
old stopped raster after a separately observed guest draw, then obtain an
explicit new publication to distinguish the two images.

Root verified all 15 native cases in `native-motion-03`: 15 passed, zero skips.

Native acceptance cases also cover a page change and unobserved A-to-B-to-A
between arm and callback without an intervening stop; paused QOM change plus
publication replacement; ignored writes and excluded palette/VRAM mutations;
active/stale/replaced publication refusal or cancellation; equal-budget
precedence in both arm orders; first-stop cancellation and explicit recovery;
JSON/script/journal reopening; old-ten-layer refusal with lower-level relative
input retained; and raw native rejection without token consumption. These
authored cases establish their results only through the execution receipts
recorded below.

Focused host/public cases independently exercise exact schemas and arithmetic,
whole-script preflight, partial references, command-set/profile admission,
shared deadlines, immutable history, cancellation reasons, protected rearm,
caller-declaration mutation and persistence failures. Routing sentinels qualify
forwarding or stored evidence, not native guest behavior. Their files are
`tests/test_qemu_mapped_mouse.py` and
`tests/test_qemu_mapped_mouse_public.py`.
Root verified `focused-new-03`: 335 passed, zero skips.

### Source identities and final local evidence

The eleventh patch pins all ten exact prerequisites. Source-only preparation
verified the 27-member ten-layer source union. Forward/reverse patch
reproduction passed with zero fuzz/offset: four resulting members matched,
the three prior members were restored, and the new internal header was removed.
An independent read-only review found no actionable arm/callback defect.
Root then applied and compiled this eleventh layer in the private Linux
x86_64-softmmu TCG/Pixman runtime: all 28 resulting native members and 396
generated QAPI files were recorded, and compilation completed successfully.

| Identity | SHA256 |
| --- | --- |
| Eleventh native patch | `27ca5b889e6be2758b812b7e19936281b4640dddf0b398519c209dd202937ec8` |
| Eleventh source manifest | `56a32945488f95fdb71704b09414769f402d2aab28a215521213abacdcebaa10` |
| Eleven-layer executable | `aa5d913b609907585779e71b37f442b50810f52bc5c7e5b1bee7ebfba8f61a3a` |

Root remained the sole build, test, emulator and publication owner. These
are fresh finite local Linux executions of the final source; overlapping
selections are not disjoint totals. Each final lane preserved its source and
private runtime inventory, with no errors or failures.

| Lane | Passed | Skipped | Elapsed seconds |
| --- | ---: | ---: | ---: |
| Focused new host/public | 335 | 0 | 28.25 |
| New native mapped motion | 15 | 0 | 11.35 |
| Affected source host regression | 3140 | 5 | 201.70 |
| Source native regression | 162 | 0 | 105.24 |
| Installed wheel/copied host tests | 2217 | 5 | 179.45 |
| Installed wheel/copied native tests | 162 | 0 | 105.99 |
| Installed retained DOSBox witnesses | 5 | 0 | 6.83 |

The five source/installed host skips explicitly require an unconfigured
`FDISBULL_MACHINE_QEMU` standalone machine witness; they are not native motion
passes. The installed host selection also deselects the same two pre-existing
source-tree inspection cases. All new native motion, broader native and
retained DOSBox selections have zero skips. The retained witnesses cover
keyboard chords/text and interruption recovery, execution predicates,
protected/paged mouse consumption and release, and scene/restart behavior.

The fresh private candidate installation used the tested core wheel, an
isolated interpreter and copied tests. Import-origin checks excluded source
checkout fallback. No shared prefix or active installation changed.
All 643 installed runtime payload files and 639 copied test/support
files match the frozen source. The declared private runtime inventory contains
1065 hashed inputs, including retained five- through ten-layer executables.

| Tested candidate package | SHA256 |
| --- | --- |
| fdisbull-0.33.0-py3-none-any.whl | `b3ddecf79ebcc383d075fc05276c31047aa700625ffee7b2ee429af9b705c27a` |
| fdisbull_player-0.33.0-py3-none-any.whl | `bad3743bb70dc4b35235db319249d24116cad7b989a38a2b9bbbf37588d3fefc` |

Final source distribution/tool ZIP assembly and four-artifact privacy/payload
verification use this completed handoff. Their resulting hashes and final
source/package readback are recorded in the MR publication receipt, avoiding
self-referential archive hashes inside the source document. Vendor images,
prepared media, firmware, executables, runtime databases and raw delivery logs
remain outside the authored source and tool packages. Previous inaccessible
macOS mirror paths remain unverified; these Linux results do not qualify macOS
or a hosted pipeline.

### Retained diagnostics and corrections

`native-motion-01` and `native-motion-02` each completed with 14 passes and one
fixture failure. The first fixture assumed the large script response would be
inline; the existing default output budget correctly returned an output
reference. The next attempt reached the output store, which correctly refused
a private artifact location under `/workspace` Git ancestry. Neither failure
required widening the product's output budget or weakening its storage guard.

The corrected fixture uses a private `/tmp` artifact/export location and the
default 65536-byte reply limit. It verifies the stored full RPC response
identity and hash, and checks that retrieving the saved response does not
repeat native input execution. `native-motion-03` then passed all 15 cases.
Both original failure receipts remain retained; these are fixture corrections,
not guest behavior inferred from a routing sentinel.

Before implementation, `missing-public-01` produced the three intended
failures for absent Python, JSON and script routes. `review-gaps-01` then
preserved four failing regressions: mutation of the caller's scale at either
of two observation points could rewrite the accepted declaration, and a later
forged callback could contradict a previously observed configuration or
replacement window. The implementation now copies the declaration before
conversion/I/O and validates a first terminal callback against established
observation history without advancing the live caches. Equal-time QOM
ambiguity and legitimate post-callback observations remain allowed.
`review-gaps-02` preserved one further failure where a later update ID could
carry a publication timestamp older than an already known replacement-window
publication; the history validator now rejects that regression.

`focused-new-01` retained 327 passes and six fixture failures: two changed an
already admitted profile while expecting a nonterminal refusal, and four
attempted a wrapped state query under an already expired operation deadline.
Those fixtures were corrected without weakening the close/deadline behavior.
`focused-new-02` then passed 335 cases; `focused-new-03` repeats that result
against the final native-test and bundled-documentation bytes. A pre-start
launcher invocation also failed because `build.env` did not export
`VIRTUAL_ENV`; no test or build began in that invocation, and the subsequent
lane used the verified interpreter's explicit path. Every original failure
receipt remains retained and is not relabeled as a passing execution.

### Remaining qualification boundaries

The public result keeps `guest_pixel_displacement`, `guest_pointer_position`,
`mapping_verified`, `raster_coherence` and `target_reached` unknown, along with
top-level `device_queue_accepted` and `guest_consumed`. A disabled mouse may
ignore callbacks, remote mode may retain motion without a stream packet, and
FIFO capacity or existing accumulators can alter emission. External held
buttons can make motion act as a drag even though no button event is requested.

The guard binds retained publication/configuration identity, not current-image
freshness. Palette, VRAM/fonts and application state can change without a
configuration-generation change, and a stopped publication has no implicit
age limit. The fixture's packet receipt, gains, pointer commit and drawing
are controlled application facts; they do not establish arbitrary DOS/INT33
calibration, cursor ownership, target readiness or completed guest frames.

Legacy absolute/coordinate/frame clicks, generic frame consumers and scenes
remain unqualified. Broad `timed_input`, `absolute_mouse`, `guest_time_control`
and `completed_guest_frames` remain false. DOSBox remains the default and all
127 default-promotion qualifications remain open. Checkpoint compatibility,
arbitrary driver/game campaigns, protected/V86 consumers and cross-platform
qualification still require their own evidence. No merge, release, shared
installation or hosted CI is implied by this slice.

## 2026-11-09: current and published VGA configuration identity

Continued from `55c549c3c3bf714ee150c1b29fa93a3cc51fd2e5` on
`agent/qemu-sunset-284eb73c`, retaining draft MR !117 and target
`agent/execution-event-search-284eb73c` /
`089c1841c415eb2b5cdfa90d03b6291a07f73919`. The preceding sparse renderer-probe
slice was already fully published. Its authored history and retained failures
remain intact. Work began on 2026-11-09; final verification and publication
continued after midnight UTC on 2026-11-10. The existing private runtime survived
this interruption and was
verified before reuse; no previous test result is treated as a new execution.

### Public contract and identity

The optional tenth native extension adds
`vga_configuration_observe(*, timeout_ms=1000)`, JSON
`debug-vga-configuration` and saved-script `vga-configuration`, advertised
separately as `vga_configuration`. It requires an owned stopped machine, the
existing explicit virtual/precise profiles, all native clock/display/retrace
commands, the new `x-fdisbull-query-vga-configuration` command, and a project
outside a caller-owned transaction. Nine-layer executables retain their earlier
operations and refuse this helper; the default retrace profile does not
advertise it. No new launch option or legacy DOSBox stub is introduced.

The atomic native response contains existing `display` metadata, current
configuration, and an optional frozen configuration observed alongside the
retained renderer publication. API1/model
`qemu-vga-configuration-fdisbull-v1` identifies the exact VGA device,
console/head, native clock epoch/time, positive process/device-local uint64
generation and a bounded raw vector. Public results use
`fdisbull-vga-configuration-1` and persist
`machine-vga-configuration-observe` events.

The raw vector conservatively includes both stored sequencer banks, graphics
and CRTC registers, attribute controls 0x10..0x14, display enable,
miscellaneous/feature output, ten VBE words, derived origin/pitch/bank/size,
DAC width and framebuffer byte order. Palette contents, VRAM/fonts, ordinary
selectors/flip-flops, status/latches, renderer caches and dimensions are excluded.
The exact fields and native sources are documented in the new patch README.

Generation advances once after each complete mutator whose final vector
changes. Hooks cover ordinary and protected legacy writes, VBE normalization,
QEXT and QOM byte order, and initialization/reset. MMIO aliases delegate to the
same handlers. Reset always advances; overflow never wraps and unsupported
post-load invalidates identity. A query compares fresh raw state to the
committed vector and refuses unexplained changes without repairing their
history. A-to-B-to-A writes advance twice even without an intervening query.
Window replacement and stopping do not reset generation.

`configuration_sha256` hashes canonical raw JSON only. Equal values or image
dimensions do not establish equal generation. Current/published identity also
requires the epoch, exact device, model and consistent raw values. A paused
QOM change can advance generation at the same virtual nanosecond; equal
timestamps do not order such changes.

### Publication semantics and bounded history

The native display callback captures its already pinned selected VGA under
BQL alongside the RGB copy, before publishing the timestamp/update ID. Capture
does not depend on a previous public configuration or retrace query. A new
window clears the stamp; stopping retains it. Missing selected publication
stamps refuse instead of receiving current state retrospectively. Ordinary
display query/export/probe schemas remain unchanged; unsupported PCI-VGA
targets have explicit snapshot stubs.

The stamp means `configuration_observed_at_publication`. Transient invalid text
layouts or blanking can leave older surface pixels in place. Even
`configuration_matches=True` does not establish raster coherence or a guest
frame. `raster_coherence`, `completed_guest_frame`, `guest_frame_id` and
`cursor_mapping` remain unknown. The display dimensions describe the retained
image; no current dimensions, BIOS mode, INT33 mapping or application readiness
are inferred.

Host validation retains one current snapshot and the last actual publication
stamp. Equal generation requires equal raw values; generations and strict time
order cannot regress or contradict prior observations. Empty windows return
`published=None` and `configuration_matches=None` while preserving the last
actual publication frontier for later validation. Historical reads never
replace current history. A stamp is immutable under one window/update pair.

This observation performs no guest execution, rendering, guest I/O/memory
read, input, sleep/wait, image export or implicit clock synchronization.
Direct signature and strict integer timeout validation precede locking/I/O.
Scripts preflight capabilities, visible values and transaction ownership before
earlier effects, then validate resolved timeouts before clamping. One shrinking
deadline, default 1000 ms and range 1..600000, covers admission, native queries,
unchanged clock brackets, validation, journal persistence and final return.
Tighter caller/script bounds intersect it. Malformed, contradictory, control,
persistence and late-result failures close ownership without retry and retain
available raw evidence and completed clock brackets on `error.result`.
Reopened journals restore history, not a live machine owner.

### Native and host witnesses

The new staged authored COM fixture reads port-visible sequencer, graphics,
CRTC, attribute and VBE values independently of the host response. It discovers
the real PCI VGA device/BAR through guest configuration reads and briefly loads
a private flat FS descriptor for genuine QEXT/MMIO access, preserving the
firmware-assigned BAR. Distinct fences delimit each complete guest mutation.
Original COM bytes and the prepared FreeDOS disk remain hash-unchanged.

All 15 new native cases passed. They cover:

- Passive clock/register/file/artifact invariance and preservation of a pending
  attribute-controller data phase.
- Same-extent page origin, pitch, panning and line-compare changes; unobserved
  A-to-B-to-A with equal raw hash and a generation increase of two.
- No-op and ignored protected CR0 writes versus writable CR7 bit 4; selector
  exclusions versus tracked display enable.
- Palette/VRAM changes that alter actual retained RGB markers while configuration
  remains equal.
- VBE 8-bit and 32-bit configurations with equal 320x200 dimensions; guest-read
  offsets/bank/DAC values and independently expected derived pitch/start/bank.
- Stopped QOM byte order and guest QEXT writes, including repeated/invalid writes;
  genuine MMIO VGA/VBE and monochrome/color-port aliases.
- Publication capture before the first public configuration query, frozen stamps
  after stop, and an empty replacement window followed by a fresh publication.
- A one-cell invalid text configuration: publication IDs advance and configuration
  matches while retained dimensions and two RGB marker samples stay unchanged.
- Armed-budget refusal without consuming the budget; reset invalidation; old
  nine-layer/default-profile refusal with existing renderer probing retained.
- JSON and saved-script dispatch, persisted receipts and reopening without live
  ownership.

The 244 focused host/public cases passed: 172 protocol/history/deadline cases
and 72 routing/capability/script cases. Success sentinels in routing tests qualify
forwarding and persistence only; real native cases separately exercise the
configuration responses. Host tests use production QMP envelopes and real
project persistence for exact schemas, bounds, null/malformed responses,
immutable frontiers, equal-time changes, shrinking deadlines and failures.

### Private runtime and build identities

Fresh reuse checks verified the previous 1063 runtime inputs, all 26 members of
the nine-layer native source union, 388 generated QAPI files, prior receipt/XML
and package hashes, and the recorded private Python distribution/RECORD payloads.
Those are input-identity checks, not new test executions. No shared installation,
dependency download, new runtime image or credential was required.

The tenth patch applied to the exact nine-layer source with zero fuzz/offset.
An independent private forward/reverse proof matched all 27 resulting source
members and restored all 26 preceding members, removing the new schema.
The root incremental `x86_64-softmmu` TCG/Pixman build regenerated 396 QAPI
source/header files and compiled successfully in 19.911 seconds. All 27 native
source identities were rechecked after compilation; older binaries and all
nine earlier patch bytes remain unchanged.

| Identity | SHA256 |
| --- | --- |
| Official QEMU 10.0.13 source archive | `4a59b74dac7ead8b162a7c4595dcbbeebe989b90c89cfe6bb4dec5447342f6fa` |
| Tenth native patch | `960a2cee1ffc95705760d1af314f7081d94db4b7f70c96bbd7b73845451a5ad7` |
| Tenth source manifest | `35a32909614f1135f2b3edf70096dc735d8024ee0209b96616cd5fad48704ec1` |
| Ten-layer native executable | `4a8b7bfbdf7815d8ce330d9068ea7b74fd51e44b89eb8ebbfbab6954339f1c71` |
| Retained nine-layer executable | `d42afdd33876a3bef38b45dae8787e9a83ad5838c3d82b1dd9ec5f8ce41dc4a2` |
| Prepared FreeDOS 1.4 disk | `0c1d6e413102e66059fbf9820d796b5c94e73bf5279e2413f87fd302eb32cdbf` |
| Retained DOSBox executable | `795df754019b5e9876d68067cb8d91314b001f28c9c6964502dd57ef21adf79d` |

The immutable runtime inventory now contains 1064 files, including the new
candidate and all required five-through-nine-layer legacy witnesses. Firmware,
DOS media, compiled binaries, logs and project databases remain private.

### Fresh finite local verification

Root was the sole build/test owner. Every material phase admitted 3 GiB growth
with at least 20 GiB reserve. Commands had finite deadlines, separate result
directories, before/after source and runtime identities, retained output and
JUnit receipts. No provider pipeline was started.

| Lane | Result | Elapsed |
| --- | --- | --- |
| Focused new host/public | 244 passed; 0 skipped | 3.577 s |
| New native configuration witnesses | 15 passed; 0 skipped | 12.531 s |
| Source host regression selection | 2805 passed; 5 skipped | 239.394 s |
| Combined source native selection | 147 passed; 0 skipped | 124.186 s |
| Fresh installed-wheel host selection | 1882 passed; 5 skipped; 2 deselected | 200.424 s |
| Fresh installed-wheel native selection | 147 passed; 0 skipped | 126.297 s |
| Installed retained-DOSBox selection | 5 passed; 0 skipped | 7.650 s |

The focused and new-native cases are also included in the larger source and
installed selections; these rows are not disjoint test totals.

The five source/installed host skips are the existing raw-machine opt-in cases
requiring `FDISBULL_MACHINE_QEMU`; none of the required 147 native cases skipped.
Installed host selection excludes the two source-only gate files and two
source-only nodes. Installed execution uses a fresh private wheel target,
copied tests/support and a separate Python environment without system packages;
import receipts verify that product modules come from that target. Package
privacy/payload checks keep external inputs out of the delivered tool.

Core wheel SHA256: `3d9a37a708318af646f31c4b73a22060ea1273dfed6dda808238521f846308ad`.
The installed payload contains 642 exact runtime files and
635 copied test/support files. Source archive checks additionally
bind the completed handoff and every changed authored file to the final bytes.

### Retained failures and corrections

Three initial seam assertions failed because the direct method, JSON catalog
entry and script operation did not yet exist. Independent review then identified
same-generation publication contradictions and loss of the last publication
frontier across empty windows. A previous-current cross-check and retention of
both clock brackets were also required. Four deterministic regressions failed
before those fixes and passed afterward; the expanded final suite preserves
their coverage.

The first expanded focused run had 236 passes and eight failures. Its earlier
write-memory fixture omitted required `expected_hex`, so static preflight
stopped before reaching the intended invalid-timeout case. The fixture now
supplies the guard and accepts it in the forwarding sentinel; all 244 cases
then passed. The same correction ensures bad VGA signature cases cannot pass
on an unrelated earlier-write signature failure. No product workaround was
introduced. Original failing receipts and outputs remain unchanged.

### Remaining boundaries and next slice

This supplies conservative configuration identity, not full video-mode or
renderer-raster identity. Overflow and post-load guards were compiled and source-reviewed, but not
executed. Non-PCI-VGA stubs have source review only; they were not compiled
or executed in this standard-VGA build. Reset testing proves owner invalidation, not a successful
post-reset generation observation. Arbitrary VGA variants and protected/V86
game/driver campaigns remain unqualified.

Coordinate/frame clicks still need an explicit pixel-to-guest-pointer mapping,
cursor ownership and stale-publication policy. BIOS/INT33 mode semantics,
completed guest drawing, VBlank, text consumption, additional audio devices,
input-to-source causality and DOSBox timing parity remain open. The existing
clock auto-sync controller remains explicit and cooperative; this passive query
does not invoke it. General `timed_input`, `absolute_mouse`, `guest_time_control`
and `completed_guest_frames` stay false.

All 127 default-promotion qualifications remain open and DOSBox remains the
default. The next bounded slice can establish a declared guest mouse-coordinate
contract using these independent publication/configuration observations as
prerequisites. Checkpoints, histories and dependent scene/player consumers
still require their own acceptance. macOS mirrors are not mounted here; hosted
CI, merge, release and shared installation are not claimed.


## 2026-11-09: sparse retained-renderer pixel probes

Continued from `fd46fbe8fa4c7819aff3bd19c08415566f8df0db` on
`agent/qemu-sunset-284eb73c` and the same draft MR !117, retaining target
`agent/execution-event-search-284eb73c` /
`089c1841c415eb2b5cdfa90d03b6291a07f73919`. The interruption had removed the
temporary checkout and private runtimes. The published source was restored
first; the test environment was then recreated from pinned inputs. The earlier
mouse-button slice and its historical evidence remain intact.

### Public contract and retained image identity

The ninth optional extension adds
`display_probe(points, *, window=None, update_id=None, timeout_ms=1000)`, JSON
`debug-display-probe` and saved-script `display-probe`, advertised separately by
`renderer_probe`. It requires an owned stopped machine, the explicit virtual
clock, all existing native clock/display commands, the new
`x-fdisbull-probe-display` command and a project outside a caller-owned
transaction. Precise retrace is unnecessary. An eight-layer executable keeps
`renderer_capture` and its existing input operations while refusing this helper.

Accept a list of zero through 256 two-coordinate points. Coordinates are strict
integers in `0..8191`, with booleans rejected, and must lie inside the retained
publication's dimensions. Preserve order and duplicates. Empty points still
require an existing publication. The optional expected `window` and positive
uint64 `update_id` must be supplied together and match exactly; with both unset,
select the latest retained publication under the machine lock. IDs restart in
each new window, so an ID alone is insufficient. The native request always
carries the selected owned token and exact update ID.

The result is `fdisbull-renderer-probe-1`, with ordinary renderer publication
metadata, requested `points`, ordered `pixels` containing `{x, y, rgb}`,
`pixel_format="RGB24"`, `coordinate_domain="retained_renderer_pixels"`, both
stopped clock brackets and the full native response. It samples the existing
private packed RGB copy under BQL. The entire native point list validates
before allocating the result or reading samples; a bad suffix cannot produce
a partial successful prefix.

There is no image artifact, temporary PPM, file export, screen refresh, guest
execution, input, sleep, implicit wait, clock-sync step, retry or fallback.
VRAM, palette or mode changes can appear in a freshly captured current surface
while the probe still returns older retained pixels and dimensions. A stopped
observer retains that image even after the guest leaves its mode. Publication
time and observed age describe this distinction. Only explicit caller-selected
execution, including an explicit cooperative clock-sync step, can permit a
later observer callback; the probe does not wait for or manufacture one.

The host compares the full native display receipt with its stopped prequery,
checks exact sample count/order/coordinates and RGB byte types/ranges, and
requires unchanged native epoch, instruction counter and virtual time across
the clock bracket. Duplicate samples must agree. At most the immediately
previous probe's 256-point map is cached for overlap contradiction checks;
this is neither an accumulated image history nor a proof of unseen pixels.
No full-raster hash is invented. `capture_display()` remains the full-image
pixel-hash route, and native witnesses compare probe samples with its pixels.

### Admission, bounded failure and historical evidence

Direct signatures and complete values validate before lock/deadline admission.
Whole-script capability, signature, transaction and visible-literal checks
precede earlier effects; resolved values validate again before sampling and
timeout clamping. References may name whole lists, list points or individual
list coordinates. Tuple points with references are refused during preflight;
direct integer tuple points remain accepted.

One allowance, default 1000 ms and bounded to `1..600000` ms, covers lock
admission, native reads, validation, clock brackets and event persistence.
Tighter caller, script, machine and channel deadlines are preserved and
restored. Missing publication, stale expectation and outside coordinates refuse
before native sampling while leaving a valid stopped owner available.

Malformed native evidence, broken read/control channels, failed persistence or
a late accepted result closes ownership without replay. Available responses
are attached to `error.result`; an explicit received flag preserves a native
JSON `null` rather than confusing it with no response. Prequery failure also
closes, including a completed QMP error with a healthy transport. A journal
committed before expiry remains historical evidence. Successful
`machine-display-probe` entries survive project reopening; reopening does not
restore the observer, live owner or VM.

### Fresh local verification

| Completed local lane | Recorded outcome |
| --- | --- |
| Focused host/public/display integration (`focused-host-03`) | 142 passed; 0 skipped |
| New native renderer-probe matrix (`native-probe-01`) | 7 passed; 0 skipped |
| Source host regressions (`source-host-01`) | 2561 passed; 5 optional machine-QEMU skips; 0 failures/errors; separately adjudicated |
| Source combined native (`source-native-01`) | 132 passed; 0 skipped; 124.799 seconds |

| Installed local lane | Recorded outcome |
| --- | --- |
| Fresh installed host regressions (`installed-host-01`) | 1638 passed; 5 optional machine-QEMU skips; 2 source-only nodes deselected |
| Fresh installed combined native (`installed-native-01`) | 132 passed; 0 skipped |
| Installed retained DOSBox (`installed-retained-01`) | 5 passed; 0 skipped |

The installed host selection contains 50 files, excluding the checkout-only
`test_distribution.py` and `test_package_payloads.py`, and deselecting the
source-derived DOS-method census and isolated source discovery nodes. Those
files and nodes are covered by the source lane. Import receipts verify that
all loaded fDisBull modules came from the fresh installed target. The retained
DOSBox cases cover chord/text input and restore, protected/paged mouse queue
versus guest consumption and explicit release, scene action/outcome/restart,
and an execution-event stop before effect.

Each completed lane recorded unchanged source and runtime inputs during its
execution. The first seven-case native run preceded only package-selector,
ledger/reference and distribution-test updates; the complete native lanes run
those same seven cases again against the final implementation. The source
host selection contains 52 files. Its five skips all request
`FDISBULL_MACHINE_QEMU` for optional raw-machine runtime checks. The wrapper
initially expected nine skips inherited from a different selection; the four
kernel/initramfs cases in `tests/test_dos_qemu.py` are absent from this selection
and are not qualified here. The original rejected wrapper receipt remains
unchanged. `source-host-01-adjudication.json` binds that receipt, enumerates the
five actual skips and accepts the test result without rerunning or relabeling
the original attempt.

The seven native tests use authored DOS programs and actual QEMU/FreeDOS:

| Witness | Established boundary |
| --- | --- |
| Partial and completed authored drawing | Probe/export pixel equality, ordered duplicates, empty and 256-point requests; retained black pixels remain distinct from refreshed partial drawing, then explicit execution publishes red/green changes |
| Palette mutation | A current surface changes red to blue while the older publication remains red; a later explicit publication changes the sampled RGB |
| Mode change and new window | A stopped publication keeps old dimensions and pixels while the current surface changes; a fresh window restarts at update 1 and refuses the old token and outside points |
| JSON, saved script and reopen | Both public routes identify the same publication; probes create no screenshot artifact; three journal entries survive reopen without a live debugger |
| Invalid native requests | Wrong/missing identity, count, coordinate, type and extra-field requests preserve the publication and clock; no partial success |
| Armed budget and reset epoch | Native sampling refuses an armed budget without changing it, and reset invalidates old publication ownership |
| Eight-layer runtime | New helper refuses before QMP I/O while ordinary retained display capture and existing timed-mouse capability remain available |

The authored program's drawing fences do not establish a generic guest-frame
boundary. Renderer completion, current VGA state, guest drawing completion and
mouse input consumption remain distinct observations.

### Review corrections and retained unsuccessful attempts

The initial missing-public-behavior witness produced three intended failures
before implementation. Independent read-only review then identified three
concrete host gaps: initial clock-journal/prequery failures bypassed closure,
JSON `null` lost available raw evidence, and tuple-contained script references
passed validation without resolving. The implementation now covers initial
reads, uses received flags and refuses tuple-contained references in preflight.
Focused regression cases exercise these conditions. Subsequent source review
found no remaining concrete mismatch in the reviewed host/public contract,
documentation, native manifest, package selectors or capability ledger.

Retain the separate environment/build/test failures rather than rewriting them:

- Initial private `pkg-config` flags inspection failed because the extracted
  GLib development package required `sysprof-capture-4`. Extracting the pinned
  private `libsysprof-capture-4-dev` dependency made the second inspection pass.
- The first ninth-layer build stopped during full QAPI generation with
  `unexpected de-indent (expected at least 4 spaces)`. The command's QAPI
  documentation lacked a blank `#` separator before `Since` after a multiline
  `Returns` entry. Only that documentation was corrected; native C stayed unchanged. The corrected patch
  passed forward/reverse source checks, QAPI generation and native compilation.
- `focused-host-01` recorded 140 passes and one test failure: the new journal
  assertion used nonexistent `debug_events.kind` instead of `operation`.
- `focused-host-02` recorded 141 passes and one test failure: the assertion
  expected an exact 50 ms script allowance, whereas the existing integer floor
  yielded 49 ms and then 29/9 ms transport allowances. The assertion now checks
  that existing bounded behavior; production deadline semantics were retained.
- `source-host-01` completed without test failures but its wrapper rejected the
  five-versus-nine skip count. The separate adjudication above retains both
  that rejection and the actual result.

### Recreated native runtime and package identity

The official QEMU 10.0.13 archive was recovered again: 141,718,608 bytes,
SHA256 `4a59b74dac7ead8b162a7c4595dcbbeebe989b90c89cfe6bb4dec5447342f6fa`.
The private environment uses Python 3.12.14, Meson 1.7.0, Ninja 1.11.1,
GLib 2.84.4, Pixman 0.44.0, PCRE2 10.46, FFI 3.4.8, zlib 1.3.1,
NASM 2.16.03 and mtools 4.0.48, with 21 extracted Debian packages and 75
firmware files. Builds used private `x86_64-softmmu`, TCG/Pixman and finite
`ninja -j6`; material growth used 3 GiB estimates plus a 20 GiB reserve.
No shared/system installation or hosted CI was performed.

All eight earlier patch files retain their bytes. The ninth patch changes only
`qapi/fdisbull-display.json` and `system/fdisbull-display.c`; it adds no timer,
event handler or publication state. Its corrected SHA256 is
`d4dc9a87a9c00e807da66339bc8cf055779de754a937ce727b0baa143300f5aa`.
Current native outputs and media have these identities; old binary hashes are
historical evidence and are not substituted for these rebuilt files:

| Input | SHA256 |
| --- | --- |
| Nine-layer candidate | `d42afdd33876a3bef38b45dae8787e9a83ad5838c3d82b1dd9ec5f8ce41dc4a2` |
| Eight-layer probe-legacy witness | `fe840b3513b867020c1af4a80be7662b974b347f3993c55c2101924621edcb00` |
| Seven-layer mouse-click-legacy witness | `cbba1af399b834a1e2d6215fc46bfbc2dd0431526db9efa725b5e49950493b0c` |
| Six-layer standard DOS/type-legacy witness | `9f152f65a5c7affd7dbb4a08150bd9e921765b478da2e2603686d20cd55a2b92` |
| Five-layer press-legacy witness | `806cc8b65ef02a2e361b3efafaec6e08a14585cbd381f800428255a0d825bffa` |
| Original FreeDOS boot image | `552f7cbb0625960c050a3e682a4d2121cc2ffdfa9dc9d592ccd49edf179333dc` |
| Current private prepared FreeDOS image | `0c1d6e413102e66059fbf9820d796b5c94e73bf5279e2413f87fd302eb32cdbf` |
| Retained offline-kit DOSBox-X executable | `795df754019b5e9876d68067cb8d91314b001f28c9c6964502dd57ef21adf79d` |

The fresh private core wheel contains 641 exact core files and has SHA256
`e49c311a96deb917232ad6af2a40acef268e647daba0f8fc89af94b8d83c6986`.
The isolated installed lane received 630 exact copied tests/support files plus
one support script. The tracked source-payload inventory has 1612 entries.
Wheel build/install, CLI, import-origin and bundled-skill checks completed;
the final installed/native outcomes and source-archive acceptance are recorded
with the remaining qualification evidence.

The final source-distribution/tool-ZIP gate compares all 1612 tracked payload
entries and all 24 changed authored files, including this handoff. Publication
requires the privacy and exact-byte checks across both wheels, the sdist and
the tool ZIP, plus final installed-package, copied-test and 1063-input runtime
identity checks. Separate qualification receipts retain archive hashes and
actual imported module paths. The source selectors include the new native
README, manifest and patch. No private runtime, vendor media, project database
or original game bytes enter those authored source artifacts.

### Remaining boundary and continuation

This slice supplies sparse evidence tied to a retained renderer image. It does
not implement legacy `frame_probe`/`video.probe`, `click(x, y)`/`click-frame`,
scene readiness, a full guest-mode epoch, completed guest frames or INT33 mouse
mapping. Equal image dimensions do not establish equal modes; relative PS/2
state does not establish guest cursor coordinates. Preserve those unknowns
when selecting the next coordinate/mode/frame slice. `timed_input`,
`absolute_mouse`, `guest_time_control` and `completed_guest_frames` stay false.
DOSBox remains the default and all 127 promotion qualifications remain open.
Vendor inputs, native binaries, raw logs, runtime databases and emulator states
remain outside Git/packages. The configured macOS mirrors are unavailable here;
this local Linux work does not establish their synchronization or hosted CI.

## 2026-11-09: callback-relative native mouse button clicks

Continued from `54c4df083d44d6070722fa1298eebbca6ef85d68` on the same source
branch and draft MR !117, retaining target
`089c1841c415eb2b5cdfa90d03b6291a07f73919`. This eighth optional native
extension adds a physical button pair to slice 4. The published seven-layer
source and its private runtime were already available and were hash-checked
before the incremental build. No earlier native patch changed.

### Public contract and timing

The QEMU-only API is `mouse_button_click(button='left', *, hold_ms=80)`, JSON
`debug-mouse-button-click` and saved-script `mouse.button-click`, advertised by
`virtual_mouse_click`. It requires the explicit virtual-clock profile, native
clock/input commands, `input-send-event` and `x-fdisbull-arm-mouse-click`.
Precise retrace is unnecessary. No `GuestMouse` facade or legacy `DebugSession`
stub is introduced. The existing `click(x, y)`, `debug-click`, `click`/
`click-frame` and `input.mouse.click` retain their coordinate/frame contracts
and remain unavailable through native QEMU.

Accept exact `left`, `middle` or `right` strings and strict integer holds of
1..1000 ms. Complete values and signatures validate before deadline/lock
admission or I/O. A stopped arm requires an empty owned queue, no owned held
leases, no bound schedule and no caller-owned project transaction. Whole-script
capability, literal and transaction checks precede earlier effects; resolved
values are validated again before arm.

One accepted plan has exactly two separately prepared and pinned one-button
batches, each with its own sync. Down is due 2 ms after arm. The actual down
callback/sync completion establishes the release deadline `hold_ms` later,
so late down delivery cannot shorten the hold. There is no movement request,
trailing timer, implicit run/sleep/resume, rebase, subdivision or replay. The
caller chooses bounded execution through `run`, `clock_advance` or one explicit
`clock_sync_step`. Completing both edges does not itself stop the VM.

Input API1 adds a mutually exclusive `click` descriptor beside `press`,
`typing` and `retrace`. Accepted arms clear incompatible descriptors; refused
arms preserve the preceding evidence and proposed token. Public evidence keeps
`fdisbull-qemu-scheduled-input-1` with `fdisbull-mouse-click-1`: button, hold,
delivered/undelivered counts, a shared paired lease, immutable step identity,
assigned deadlines, actual callbacks and per-edge lateness. Public `edge_count`
and native `event-count` stay two. The first deadline remains fixed; top-level
lateness is `None`, and top-level dispatch exists only after full completion,
equal to the final callback and terminal time. Terminal evidence freezes.

### Stops, ownership and bounded failure

Native epoch/profile, pending-stop, equal/reached budget and pinned-handler
checks precede each edge. The first actual stop cancels the undispatched suffix.
The host validates the full native plan, prefix and owned cutoff before
committing a candidate mouse ledger; the keyboard-specific reconciliation
helper is unchanged. An interrupted down remains an owned hold. A bound partial
click refuses further execution, new input and ordinary/retrace rescheduling.

`input_cancel_pending()` discards only the unsent suffix, retains delivered
holds and clears their pending releases. The caller explicitly calls
`mouse_button_up(lease)` and chooses release execution. No cleanup release or
suffix replay is synthesized. Arm/prefix/result journals survive project
reopening as evidence; reopening does not restore the live owner.

Direct arm has one 1000 ms host allowance across lock admission, native I/O and
persistence, intersected with tighter incoming bounds. A pre-arm expiry leaves
a valid stopped owner. Accepted or uncertain late arms, malformed/native failed
evidence and persistence failures retain available evidence and close ownership
without replay. The wrapper also closes a late accepted result after its final
outer check. Input-touch script failure retains the existing close behavior.

### Fresh local verification

| Local lane | Result |
| --- | --- |
| Focused host/public integration | 210 passed; 0 skipped |
| New native IRQ12 click matrix | 16 passed; 0 skipped |
| Source host regressions | 2328 passed; 9 skipped |
| Source combined native | 125 passed; 0 skipped |
| Fresh installed host regressions | 1405 passed; 9 skipped |
| Fresh installed combined native | 125 passed; 0 skipped |
| Installed retained DOSBox | 5 passed; 0 skipped |

The source and installed host lanes retain the nine declared optional machine
prerequisite skips. The installed lane excludes two checkout-only files and
deselects two source-only nodes; those are exercised in the source lane. All
native and retained DOSBox cases execute with zero skips. These are finite
local Linux receipts, with unchanged recorded inputs and explicit time/storage
bounds. They are not hosted pipeline results.

The 16-case click matrix independently compares complete IRQ12 packets after
an authored guest reset, stream-mode setup and polled zero-state check:
left `09 00 00`, right `0a 00 00`, middle `0c 00 00`, followed by release
`08 00 00`. It exercises busy/HLT loops, the original stop before down and after
a complete down packet, explicit recovery, both equal-budget command-arm orders,
seven-layer refusal with ordinary mouse input retained, JSON/script/journal/
reopen and descriptor transitions, and one HLT clock-sync step with the default
80 ms hold. Only the down boundary covers both actual timer insertion orders;
the release timer is created after an already armed budget. Strict native
argument/token checks and inclusive hold bounds are also exercised.

The native tests observe guest packets only in that deliberately initialized
fixture. Existing accumulators or external button state can affect arbitrary
packets; disabled/remote devices and FIFO capacity are not normalized. Callback
completion does not establish arbitrary FIFO acceptance, INT33 semantics,
cursor position, application click recognition or frame completion. Dynamic
handler replacement between edges is checked by the existing pinned-handler
code path but is not exercised by this click-specific native matrix.

The retained installed DOSBox witnesses cover keyboard chord/text and restore,
protected/paged mouse queue versus actual program consumption and explicit
release, scene action/outcome/restart, and an execution-event stop before effect.
The old seven-layer QEMU refuses only the new helper while retaining keyboard
press/type and ordinary scheduled mouse input.

### Reproduction, packages and retained observations

The eighth patch is
`23f38d65391587b0be11af021fc3858872475d25a03719844b486719eee154d9`.
Forward/reverse application used zero fuzz/offset and restored all 26 prior
native members; full QAPI schema/generation produced the expected command and
432 generated files. The dedicated mouse dispatcher leaves the keyboard
dispatcher byte-identical. Root application and compilation independently
verified the 26-member layer state and all seven prerequisite patch hashes.
The incremental candidate build completed in 3.812 seconds with binary SHA-256
`daac51e3d63d24dad8e39b8df5d1c6c843411d962fa1d37527fa25a11dbf50f5`.
The seven-layer refusal witness is
`07322555c94ac7acfb6e5fcf0fcc6af42c4742fe169095854fa8f86bf68b9368`.
Six- and five-layer binaries remain selected for the existing keyboard legacy
checks. The prior section records the unchanged private toolchain, firmware,
FreeDOS prepared image and retained DOSBox provenance.

The fresh private wheel has 641 exact core files, with 626
byte-identical copied test/support files. Installed lanes use that target
outside the checkout and assert import origins. The source selectors now include
the eighth patch, manifest and contract. The final source-distribution/tool-ZIP
gate compares 1605 authored payload entries and every one of this
slice's 26 changed files, including this final handoff, before publication.
No private runtime, vendor media, project database or original game bytes enter
the source artifacts. No shared installation or release is performed.

Retained evidence includes the intended initial missing public-route and host
method failures. The first focused host attempt had one pass and 108 fixture
setup errors because its target store was beneath Git-managed `/workspace`;
correcting that private store location to a protected `/tmp` directory and
expanding the selection to include the public tests yielded 147 passes. Independent review then identified invalid direct values reaching
lock admission. Four busy/expired admission regressions failed for the intended
reason before the pure mouse validator was moved ahead of admission; the fresh
210-case integrated lane passed afterward. The first broad source lane had no
assertion failures (2311 passed) but lacked runtime variables for 17 embedded
native cases; its 26 skips were rejected by the wrapper. A fresh full lane with
the declared runtime executes those cases and retains only the nine allowed
machine/kernel prerequisites. No native or package result is
inferred from those initial failures. Older unresolved observations remain
verbatim in the historical log below.

Private evidence lives under `mouse-click-runtime`, `mouse-click-native-work`
and `mouse-click-validation`. Each test lane records commands, exit/XML/log
results and before/after source/runtime hashes; material growth requires a
3 GiB allowance above a 20 GiB free-space reserve. Source/package verification
and publication compare the exact final tree rather than a nearby revision.
The configured Mac mirrors remain unavailable in this Linux workspace.

`timed_input`, `absolute_mouse`, `guest_time_control` and
`completed_guest_frames` stay false. DOSBox remains the default and all 127
promotion qualifications remain open. Next work remains coordinate/frame clicks,
INT33 mapping and arbitrary consumption, full VBlank/frame semantics, additional
audio devices, real QEMM/DESQview/game campaigns, then dependent checkpoint and
history contracts. The full migration slice is still partial.

## 2026-11-09: callback-relative native keyboard text

Continued from `16d115769c027e02427c24fa60b1b12496c8be47` on the same source
branch and draft MR !117, retaining target
`089c1841c415eb2b5cdfa90d03b6291a07f73919`. The published source was recovered
after the temporary workspace reset, and the private native and Python runtimes
were restored afresh. This increment implements the existing bounded text
workflow; it does not close the remaining migration or promotion gates.

### Existing text workflow and native timing

`keyboard_type(text, *, hold_ms=40, gap_ms=40)`, `GuestKeyboard.type`, JSON
`debug-keyboard-type` and script `keyboard.type` share the optional
`virtual_keyboard_type` capability. It requires the explicit virtual clock,
existing native clock/input commands and `x-fdisbull-arm-keyboard-type`.
A precise retrace profile is unnecessary. The restored six-patch executable
still supports native press, refuses native type and does not execute while
refusing it.

One stopped admission requires an empty owned queue and no active owned leases.
The native command validates and prepares the entire sequence before consuming
its token: 1..64 US-layout ASCII characters, comprising printable ASCII plus
CR, LF and Tab; strict integer hold/gap values of 1..1000 ms, excluding booleans.
CR and LF each produce Enter without folding. Each uppercase or shifted
punctuation character gets its own Shift chord. The mapping assumes an
unmodified US layout and does not infer the guest's layout or Caps Lock state.
Invalid text, including embedded NUL and a non-ASCII suffix after a valid
prefix, is rejected atomically.

The seventh optional native patch prepares 2..256 edges. Per character the
order is optional Shift make, main make, main break and optional Shift break.
The first edge and other make/modifier-break edges wait 2 ms; the main break
waits hold_ms after the actual main make. Starting with the second character,
its first edge waits gap_ms + 2 ms after the preceding character's actual final
release callback. Every next deadline derives from the preceding callback,
so late dispatch cannot shorten a hold or collapse the gap. There is no
trailing-gap timer. Arming is passive: the caller explicitly chooses a bounded
run, clock advance or cooperative clock-sync step. Input does not sleep, run,
rebase or split the sequence itself. At maximum timing, 64 shifted characters have a nominal duration of
127,384 ms, exceeding the 60-second clock-advance limit. A shorter budget
cancels the suffix; no implicit splitting or resumption occurs.

### Prefix evidence, ownership and failure handling

The existing input API1 receipt gains an optional `typing` descriptor,
mutually exclusive with press/retrace metadata. It binds text, timing, the
full plan and its delivered-prefix count. Public `typing` uses
`fdisbull-keyboard-type-1` within the existing scheduled-input format; each
step includes its character index, key, unique lease, delay, assigned deadline,
actual dispatch and lateness. Delivered deadlines remain frozen, and only the immediate next unsent
deadline is assigned.
Top-level dispatch is present only for complete delivery, and top-level
lateness remains None. Terminal evidence stays frozen across later observation.

The host reconciles a complete newly proven prefix privately before changing
leases. Repeated letters and repeated Shift uses have distinct lifetimes;
future reservations do not appear as held keys. The 256-edge plan can reserve
128 distinct lifetimes while holding at most two keys. The general limit of
64 active leases is unchanged. Cancellation reports discarded future reservations
separately from retained active holds.
Native stop/breakpoint and reached/equal budget precedence remain intact;
the first actual stop cancels the undispatched suffix, while completion itself
does not stop the guest. A cancelled sequence cannot run again or be converted
into another input schedule. Explicit `input_cancel_pending` discards unsent
reservations, preserves delivered holds and clears their pending releases;
the caller then explicitly releases held leases and chooses execution. No
suffix replay or synthetic cleanup release occurs.

Literal, capability and transaction script checks precede earlier mutations;
resolved arguments are checked again before native arm. One direct-arm
1000 ms host bound covers lock admission, I/O and persistence and intersects
tighter incoming bounds. Pre-arm expiry leaves a valid owner. Accepted or
uncertain late arms, malformed/native-failed evidence and persistence failures
preserve available evidence and close without replay. Existing journals and
reopened artifacts retain typing evidence and clear stale descriptors when
switching among press, type, ordinary and retrace input.

### Fresh runtime provenance and fixture compatibility

The official QEMU 10.0.13 archive was restored with pinned SHA256
`4a59b74dac7ead8b162a7c4595dcbbeebe989b90c89cfe6bb4dec5447342f6fa`.
Safe extraction excluded its unsafe absolute EDK2 X11 include link. All six
existing patches applied sequentially with zero fuzz/offset and the full
26-member source manifest matched before the new layer was applied. The
private build used Meson 1.7.0, Ninja 1.11.1, GLib 2.84.4 and Pixman 0.44.0;
19 official Debian packages were verified and extracted privately, with no
system installation. Firmware, NASM 2.16.03 and mtools 4.0.48 were restored
and inventoried. The restoration receipt records 949 private dependency files,
75 firmware files and exact tool/input hashes.

Official FreeDOS 1.4 media was verified against its published checksum. Its
original boot image still matches
`552f7cbb0625960c050a3e682a4d2121cc2ffdfa9dc9d592ccd49edf179333dc`.
The documented preparation recipe produced a fresh baseline with SHA256
`ad852960ff1fd1355c28ac6295924c90ae88a0e23d66586f6c0ad6dff173a0af`;
DOS directory timestamps differ from the lost prepared image, so this is
new runtime provenance rather than a claim to reproduce that old image hash.
The retained DOSBox executable was recovered from the offline kit with its
previous SHA256
`795df754019b5e9876d68067cb8d91314b001f28c9c6964502dd57ef21adf79d`.

The Python validation environment was created afresh from the managed
Python 3.12.14 interpreter, with system site packages disabled and the
repository's `[test]` dependencies plus `build` installed privately. The source
native run imported this checkout's `src` and `tests`; fresh installed-wheel results
are recorded separately below. The fresh six-patch QEMU binary is
`8abd9cc2bf2148d9b53043a7b611df8a0bd06fca63b27e63d0a78aae48d0b05c`;
the seven-patch candidate is
`07322555c94ac7acfb6e5fcf0fcc6af42c4742fe169095854fa8f86bf68b9368`.

The IRQ1 fixture now accepts an explicit capacity up to 256. Its default stays
16, and both default binaries and symbol offsets are byte-compatible with the
previous fixture: busy is 371 bytes with SHA256
`c361ed48c890ee7459cb5eecb2eb4409142226c3755d0dc8aff0d1076391c9b5`;
HLT is 376 bytes with SHA256
`6f97d5d4e4a5ad10e96a6353ce3aa057a1ba7e398240cfa4816473b1f1e5cbd8`.
Only the new typing witnesses request capacity 256.

### Retained failures and current qualification

The pre-change host refusal and public script-grammar gap were captured before
implementation. The first complete public selection then retained 45 passes
and 12 failures: eleven exposed the missing `keyboard.type` entry in
`MachineDebugSession.script_operations`, and one exposed accepted-arm cleanup
when the outer deadline expired. Adding the script operation and including
`keyboard_type` in the existing accepted-arm deadline cleanup fixed these
paths; the owner now closes while retaining the accepted receipt. The failed
receipts remain retained. The focused host selection subsequently passed all
323 cases, and the complete press/type public selection passed all 57.

All 20 new native cases passed on their first feature run, with unchanged
source/runtime inputs: 15.634 s in pytest (16.459 s for the complete lane).
The independent US-map/scancode and callback-delay oracles cover busy/HLT
execution with repeated lowercase, uppercase/shifted punctuation and
CR/LF/Tab/space/tilde; passive arm; no trailing gap; and the 64-uppercase
maximum of 256 edges with 128 distinct key lifetimes. That maximum witness
uses hold/gap 1 ms, yielding a nominal 511 ms sequence.

Further witnesses preserve original breakpoints before the first make and
after the first Shift IRQ, prove suffix cancellation and explicit held-lease
recovery, stop between characters without leaving holds, and enforce equal
budget cutoffs at the first make, release and next-character edge. Both
command-arm orders are covered at each cutoff. **Only the first-make cases
exercise both actual timer insertion orders**: the release and later-character
timers are created by preceding callbacks, after the budget timer is already
queued in either command order. Other cases verify the older six-patch
capability refusal while press works, JSON/script/journal/reopen evidence,
one explicit clock-sync step driving halted text, and invalid direct-native
arguments leaving the owner token reusable. The native matrix covers selected
ASCII groups; complete character mapping is covered by host contracts, not
claimed as a native test of every printable character.

| Local selection or artifact gate | Result |
| --- | --- |
| Focused type/press/physical/ordinary/retrace host contracts | 323 passed; zero skips |
| Public press/type routing, script and deadline contracts | 57 passed; zero skips |
| New native typing witnesses, first feature run | 20 passed; zero skips; 15.634 s |
| Broad affected source regressions | 2,177 passed; 9 prerequisite skips; 134.715 s |
| Combined source native selection | 109 passed; zero skips; 69.644 s |
| Fresh installed-wheel host regressions | 1,254 passed; 9 prerequisite skips; 2 metadata nodes deselected; 107.541 s |
| Fresh installed-wheel combined native selection | 109 passed; zero skips; 70.885 s |
| Retained DOSBox chord, text/script/restore and event-predicate witnesses from the installed wheel | 3 passed; zero skips; 4.262 s |
| Seventh-patch reproduction, schema/generation and native compilation | Zero-fuzz/offset roundtrip; all 26 native members matched/restored; all three selected native builds passed |
| Fresh core wheel, private installation and copied tests | 640 core members match source/wheel/install; 622 copied test/support files match source; isolated CLI and import-origin checks passed |

Selections overlap and must not be added into a unique-test total. Each lane
retained exclusive command/log/XML receipts and unchanged before/after hashes
of its selected inputs. Runtime lanes also pinned their selectors, executables,
media and private libraries.
Material growth admitted 3 GiB plus a 20 GiB reserve; builds and runtime lanes
ran serially with finite timeouts and no automatic retry loop.

The nine stock skips are five separately selected raw-machine checks and four
legacy Linux-hosted DOS/QEMU shim checks whose kernel/initramfs inputs were not
selected. The first source driver's allowlist omitted that latter prerequisite
message: pytest had zero failures/errors, but the driver retained a failed
classification result. A separate review records the four known missing-input
skips without rerunning or counting them as passes. The installed lane explicitly
allowed both prerequisite messages. It excluded only the checkout-only package
and distribution-policy files and two source-only inventory/discovery nodes;
those checks ran in the source lane. Installed tests ran outside the checkout,
with explicit rootdir, importlib mode and an empty pytest config. Origin guards
verified 129 loaded host modules and 114 loaded native-lane modules from the
fresh target installation. The driver rootdir correction changed no product code.

The seventh patch SHA256 is
`d680d253af93b60d3101ef74c1243e19e887b1cabdf0df194fdec0aafed23cc5`.
The core wheel SHA256 is
`14fd94d362c967e189197fc9dfb4cbdf06916da0927f7f835366dacc18331675`
(2,400,520 bytes, 645 total members). The seven-patch binary supplies the clock
selector; the six-patch binary supplies standard DOS and the type legacy
witness. A separately built five-patch binary supplies the press legacy
witness. The optional four-patch retrace-legacy secondary VM was not restored
or newly witnessed in this workspace.

After this entry is frozen, publication is gated on fresh sdist/tool ZIP
privacy and exact-payload comparisons, all 23 authored changed paths including
this handoff, and reconciliation of the tested source/wheel bytes with the final
Git tree. Final source archive hashes and publication identities are recorded
in the draft MR after those gates. This bounded slice does not claim the full
release package-smoke route, separate player-wheel installation, extracted-source
installation, hosted CI or a release. Current guides and the bundled investigation
reference describe typing; earlier dated handoff entries remain unchanged.

### Historical observation and remaining boundaries

Preserve the preceding press entry's first installed combined native attempt:
88 passes and one failure in the unchanged retrace budget-first witness.
Its initial passive observation completed six QMP calls, then refused the
final clock query locally because the shared host deadline had expired,
before input or clock arm. The effective default was 1000 ms intersected
with incoming bounds; the failed observation did not establish where time
was consumed or whether an inherited bound shortened it. The unchanged
isolated follow-up and full 89-case repeat passed, and independent comparison
found no changed observation path or effective default. No cause was
established and no timeout fix/increase was made. The new typing results do
not resolve that historical unknown. The published handoff retains this
record; this fresh workspace does not assert recovery of every old raw log.

DOSBox remains the default and both selectors remain available. All 127
promotion qualifications remain open. Native callback delivery does not
prove arbitrary guest consumption, keyboard layout or completed drawing.
Timed clicks, coordinate mapping, frame/VBlank semantics, input-to-source
causality, wider audio, real QEMM/DESQview/game campaigns and checkpoint/history
dependencies remain outside this slice. General `timed_input`,
`guest_time_control` and `completed_guest_frames` stay false. No hosted CI,
merge, release or shared installation is claimed; configured Mac mirrors
remain unavailable.

## 2026-11-09: callback-relative native keyboard presses

Continued from `b6011c68042918942a1d52ff0d8c17ff42343501` on the same source
branch and draft MR117, retaining target
`089c1841c415eb2b5cdfa90d03b6291a07f73919`. This increment supplies the existing
single-chord press workflow through native QEMU. Timed text/clicks, frame
semantics and the remaining migration stages are separate gates.

### Existing public workflow, passive native timing

`keyboard_press(key, modifiers=(), hold_ms=40, gap_ms=40)`,
`GuestKeyboard.press`, JSON `debug-keyboard-press` and script `keyboard.press`
now share the optional `virtual_keyboard_press` capability. It requires the
explicit virtual clock, existing clock/input command set and the new
`x-fdisbull-arm-keyboard-press` command. A precise retrace profile is unnecessary.
Older native binaries retain their existing capabilities and refuse this route.

One stopped admission requires an empty owned queue and no active owned leases.
It prepares a chord of two through eight edges without executing the guest:
caller-order modifier makes, main make, main break, reverse modifier breaks.
The first edge and every later make/modifier break waits 2 ms; the main break
waits hold_ms from the actual main make. Each next deadline derives from the
preceding actual callback, so late dispatch cannot shorten the requested hold
or collapse later release spacing. Strict hold_ms/gap_ms bounds are 1..1000.
gap_ms is validated and retained without effect for a single press, matching
the retained DOSBox contract; it belongs to that backend's separate text queue.

The caller chooses one later bounded run, clock advance or cooperative
clock-sync step. Input never runs or rebases the clock itself. The native
acceptance witness drives a halted chord with exactly one explicit
clock_sync_step while preserving the controller's fixed host/native anchors.

### Prefix evidence and explicit recovery

The sixth native patch adds an optional press descriptor to the existing input
API1 receipt and retains the existing query/cancel commands. It copies and
pins each one-key batch before committing the arm/token. The descriptor binds
the key/modifiers/timing, immutable step order, each assigned deadline, actual
callback/sync timestamps and a delivered-prefix count. Only the immediate next
deadline is assigned; later edges are not placed on a predicted absolute grid.
Ordinary/retrace accepted arms clear press metadata, and press arms clear
retrace metadata. Shared bounds, token history and migration restrictions remain.

Every edge preserves pending debugger/native-stop and reached/equal
clock-budget precedence. The first actual stop cancels the undispatched suffix;
completion itself does not stop the VM. Both actual timer insertion orders are
witnessed for the first make. The release witness covers both command-arm
orders, while accurately retaining that its timer is created only after make,
so its clock budget is already queued in both cases.

The host validates the full plan, callback-relative recurrence, prefix
monotonicity/freeze, epoch/token, terminal times and every edge's owned-budget
cutoff before changing leases. It applies only a newly proven prefix to a
private lease ledger. Top-level dispatch_ns is absent for cancellation even
when makes were delivered; inspect press.dispatched_count and leases.
Top-level lateness_ns is None for a chord; each public step reports its own
lateness against its assigned deadline. This avoids counting the requested
hold duration as lateness.

A cancelled press remains bound and cannot run again or be converted into
ordinary/retrace scheduling. Explicit input_cancel_pending discards unsent
steps while retaining dispatched holds and clearing their pending releases.
Callers then explicitly key_up each retained lease and choose its execution.
There is no automatic suffix replay or synthetic cleanup release.

Literal/capability/transaction script checks precede earlier script mutations;
resolved values are revalidated before arming. One 1000 ms direct-arm host bound
covers lock admission, I/O and persistence, intersecting tighter incoming
bounds. Pre-arm admission expiry leaves a valid owner available. Accepted or
uncertain late arms, malformed/native-failed evidence and failed persistence
retain available native/stop evidence and close without replay. Failed scripts
that touched input close the owner. Terminal native step evidence stays frozen.

### Native witnesses, compatibility and retained corrections

The original press refusal and script-grammar failure were retained before
implementation. The new focused host selection has 75 press cases and the
existing physical/ordinary/retrace input checks: 228 passed, zero skips. Public
routing/admission/deadline checks add 26 cases, also exercised in the full lanes.

All 16 new native cases passed on the first feature run and again in the source
and installed combined selections. Busy/HLT × plain/shift/full chords inspect
actual IRQ1/scancode bytes and an independent delay recurrence. The busy full
chord demonstrates a late main-break callback followed by a deadline based on
that actual time. Other witnesses retain original breakpoints before/after
make, demonstrate held-lease cancellation/release, verify equal cutoffs, refuse
the older five-patch executable, preserve JSON/script/journal/reopened evidence,
compose with clock auto-sync and reject invalid native command arguments
without consuming their token. The fixed gap value of 1000 ms does not create a
tail timer: each admitted chord completes well before that interval.

Three early host-test assertions attempted a public state read after their
intentionally expired deadline; they were corrected to inspect retained private
invalidation state. Compatibility checks exposed a minimal unsupported owner's
missing configuration producing AttributeError; the guard now returns the
established unsupported guest-time ValueError. The first broad source lane had
1302 passed, one failure and five optional skips: the operation correctly
refused before an earlier script step, but its error text lacked the retained
"guest clock" wording. The wording was restored, that regression passed, and
the full final source lane passed afterward. All failed receipts remain retained.
No native implementation change or rebuild was needed after its first build.

The first installed combined native attempt retained 88 passes and one failure
in the unchanged retrace-input budget-first witness. Its initial stopped
retrace bracket completed six QMP calls, then locally refused the final clock
query because the shared host deadline had expired, before any input or clock
arm. The request's default allowance is 1000 ms, intersected with incoming
bounds; the failed log does not establish where time was consumed or whether
an inherited bound shortened it. An observation-only isolated repeat passed
with the same wheel, binary and production bounds. Independent comparison
found no change to the observation path or its effective default. The one
finite full installed-native repeat passed all 89 cases without changing code
or increasing timeouts. The original failure and isolated timing records remain
retained; no root cause is assigned from the successful follow-up.

### Exact reproduction and local qualification

The unchanged five prior patches and new sixth patch reproduced from the
pinned official QEMU 10.0.13 archive using 92 required regular source/QAPI/parser
inputs. Forward/reverse application had zero fuzz/offset; both changed native
members matched the built source and reverse restored all 26 prior native
members. QAPI schema validation and generation passed. The private x86_64
TCG/Pixman build configured in 15.751 s and compiled in 90.197 s, with no source
change during either phase. Runtime inputs, databases and vendor media remain
outside Git.

- Sixth patch SHA256: `0098d4301d8703d7d740b58ae0f048d0a73ec6e9c9ce10cec04457bebb1c4ed0`.
- Native executable SHA256: `b09fa87715cd0c7826fcd03ce8537b9b95ae2e209f15c677ffbc579ad261a78a`.
- Private wheel SHA256: `2498503d9580c0fac926b60cc01aa05cc0eeb3b2ab719f4efc321722840928bd`.

| Local selection | Result | Elapsed |
| --- | --- | --- |
| Affected source regressions | 1303 passed; 5 skipped | 159.977 s |
| Combined source native selection | 89 passed; 0 skipped | 72.562 s |
| Fresh installed-wheel regressions | 1292 passed; 5 skipped | 127.405 s |
| Fresh installed-wheel native selection | 89 passed; 0 skipped | 319.924 s |
| Retained DOSBox chord and trace witnesses | 2 passed; 0 skipped | 17.354 s |

Selections overlap. The five skips in each broader lane are the existing
optional raw-machine session cases with FDISBULL_MACHINE_QEMU unset; they are
not counted as native passes. Both required native lanes include all 89 cases
with zero skips. The retained DOSBox lane exercises actual timed chords,
pending-input checkpoint restoration, and the earlier source predicate/hook
boundary. This does not establish native QEMU checkpoint support.

The wheel's 639 core members and 619 copied test/support members are verified
against source, with installed import-origin checks outside the checkout.
Final source artifacts bind 1590 tracked payload files and all 21 authored paths;
their hashes and the exact tested tree are retained in the MR publication
receipt. Package payload/distribution checks are mandatory before publication.

The source ledger now includes the previously implemented fifth-layer witness
set as well as this press increment. Its press routes change from pending to
partial; all 127 promotion qualifications remain open. DOSBox remains default
and both selectors remain available. Native callback completion still leaves
FIFO acceptance, arbitrary guest consumption and completed drawing unknown.
Text/click helpers, renderer/frame/VBlank semantics, coordinate mapping,
input-to-source causality, broader audio, real QEMM/DESQview/game campaigns and
checkpoint/history dependencies remain open. No hosted CI, merge, release or
shared installation is claimed; the configured Mac mirrors remain unavailable.

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


## Local continuation 2026-11-11: instrumented checkpoints and bounded modes

The local branch `codex/qemu-dosbox-parity-20261110`, following `a834a55c`,
adds private COM/MZ checkpoint restore with the virtual clock, PC-speaker
capture and precise VGA retrace profiles. Native observer state carries
retained PCM and renderer pixels, publication configuration, timing
provenance, bounded mixer/backend queues, oscillator position and timer
state. Restore reads the saved state back under fresh native and host clock
epochs and fresh observer tokens. RAM/fetch layers, hook actions and hit
counts, pending hook step-over and breakpoints remain part of the process
envelope. A separate Python host restores and continues the same artifact.

The stopped selected CPU can also be in protected or V86 mode under the
identity-backed low-memory ownership contract. Authored witnesses cover a
loaded GDT with 32-bit code/data/stack caches, identity paging, actual V86
execution, a remapped page-zero refusal, layer/hook restore and return to DOS.
Descriptor contents, exact PDE/PTE bits, source RAM, helper, PSP and DOS
allocation observations are compared across restore. Scheduler task identity
remains unknown. Arbitrary QEMM/DESQview/DPMI mappings are not qualified.

Fresh macOS local verification: 817 tests passed with zero failures or skips
in the integrated 49-file regression selection, including retained DOSBox
cases. Another 23 host contract checks passed after adding explicit refusal
of instrumented checkpoints on raw boot projects. These counts overlap and
must not be added. The focused tests also prove immediate re-saving of a
verified cold-restored process and ordinary-snapshot refusal by restored
audio-only and display-only blockers without clock-budget/retrace blockers
masking them. The POSIX socket tests use a short external temporary alias;
older generic VM tests use a private wrapper that supplies the pinned firmware.
Feature tests pin the real QEMU executable and firmware directly.

The native delta is in `native/qemu-instrumented-checkpoint/`. Its manifest
pins all 23 before/after source pairs and the exact 13-patch prerequisite.
The patch applies in a dry run against that prerequisite; no whole QEMU tree
or private machine/media state is added to this repository. The tested
QEMU executable SHA-256 is
`b24403a451d4a52e3bf21f183c67bc1159ab736f78f8dd6093a7bedd452b3a08`.

Host monotonic synchronization must be stopped, and pending/held/scheduled
input and outstanding clock budgets must be resolved before checkpointing.
Unsupported audio graphs/resampling and malformed or uncertain restoration
fail closed. Raw-machine checkpoints retain standard-profile restrictions.
New restored-epoch source histories, other audio devices, arbitrary protected
ownership, actual drivers/games and the formal parity campaigns remain open.

No CI, release, installation or mirror publication is part of this local
continuation. DOSBox remains the default, removal remains forbidden, and all
127 formal surface qualifications and seven campaign gates remain open.

## Local continuation 2026-11-11: task-private scheduling and cascaded PIC checkpoints

This continuation advances the bounded work recorded in the previous
checkpoint section. The source head is
`4da1a2f2270672593720d57fae1fc782175a3ace` (`Add native cascaded and nested PIC
IRQ checkpoints`). The N19 source-only delta is documented in
[`native/qemu-task-cascade/README.md`](../native/qemu-task-cascade/README.md)
and pinned by its source manifest. The earlier statement that scheduler task
identity remained unknown describes the checkpoint/mode work before the
subsequent task-context and scheduler increments; it is not the current
handoff state.

N12–N19 map to the nine canonical slices as follows:

- **1. Core:** Reuses the owned x86 TCG machine and stopped controls. The
  general core remains in progress; this does not promote a backend.
- **2. DOS process and drivers:** Extends real COM/MZ process identity with an
  explicit cooperating FDBTASK1 lifetime and bounded remapped protected/V86
  ownership. It does not identify a QEMM or DESQview task.
- **3. Trace and events:** Task-scoped hooks and native interrupt-frame
  observations carry CPU/task identity through selected boundaries. General
  retirement, causal input attribution and arbitrary overlays remain open.
- **4. Clock, media and input:** Exercises real PIT IRQ0, i8042 IRQ1, IF/mask
  deferral and nested RTC IRQ8. General IRQ timing, completed frames, audio
  playback and DOSBox timing parity remain unqualified.
- **5. Checkpoints:** Fresh-process snapshots preserve bounded task CPU
  contexts, private RAM/fetch state, hooks and consistent nested or partial
  PIC EOIs. Cross-binary VMState exchange remains unqualified.
- **6. Layers and block services:** Adds task-private RAM/fetch, same-site
  hooks, shared-allocation forks, CPU scheduling and PIC frame ownership.
  Arbitrary vendor schedulers, DMA/private-device views and UDL/UIL host
  services remain open.
- **7. Histories:** Pending. The next bounded periodic memory-rule increment
  remains ahead while its explicit virtual-clock route and layer/task
  preflight fences are being established.
- **8. Workflows:** Pending. General scene, script, player and analysis
  workflow coverage does not follow from the native task witnesses.
- **9. Qualification:** Targeted local evidence passed; real QEMM/DESQview/game,
  Windows, full cold-restore and fallback campaigns remain unqualified.
  DOSBox stays the default and remains selectable.

The N19 native receipt reports 19 focused native cases passed with zero
failures or skips. The recorded validation at this source revision also
includes a 66-file local regression (1,046 cases), a 19-file host/public/
packaging contract set (709 cases), an N18/API2 compatibility set (141 cases),
and an N17/API1 compatibility set (7 cases); each recorded zero failures and
skips. These selections overlap and their counts must not be added. The focused evidence includes RTC
IRQ8 through the slave/master cascade, nested keyboard IRQ1, checkpoints with
both EOIs pending and with slave EOI complete but master EOI pending, both
policy-target choices, deferred handoff until the outer frame is fully
EOI'd, and guards for out-of-order EOI and IRET. These are bounded authored
FreeDOS/V86 fixtures on one x86 TCG vCPU, not compatibility tests for
arbitrary DOS software.

The N19 patch applies after the sealed N18/API2 patch; its manifest records
source hashes, build identity and the 19-case receipt. No private DOS target,
runtime image, VM state or raw external receipt is included here. This local
continuation did not run hosted CI. The default-switch gate still has 127
unqualified surface rows and seven unqualified campaigns. DOSBox remains the
default, and removal remains forbidden.


## Local continuation 2026-11-11: periodic native-clock memory rules

This host-adapter increment follows integration parent
`28108fe746fc9838e06c3291d268f809e0acc283` on the same source stack and draft
MR !117. It uses the already verified N19 native executable; no new QEMU patch
or native engine version is required. The [milestone progress note](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/117#note_4211660592)
records the N12–N19 catch-up and start of this increment.

The existing `memory_rule_run(rule, *, ticks, interval_ms=100,
timeout_ms=10000)`, JSON `debug-memory-rule-run` and saved-script
`memory-rule-run` now admit an explicitly selected QEMU virtual-clock profile.
The first tick runs while stopped, and later intervals use token-bound native
virtual-clock budgets. One host deadline begins before machine-lock admission
and covers all nested clock and memory operations. Each tick rechecks its
original run/task label, epoch and complete mapping before capturing fresh
values and issuing a new one-shot expected-byte edit. Rule progress is a
persistent append-only journal; an uncertain completion cannot become a retry.

Any nonordinary native stop, including a fired timer coincident with another
stop, ends the invocation without another tick or write. Guest exit/residency
retains its own outcome and disables the old rule lifetime. The explicit
virtual-nanosecond contract does not implement generic DOSBox `guest_ms`,
cycle accuracy, an installed timer hook, background execution or real-time
frequency. DOSBox retains its earlier guest-time route.

This historical increment advanced the clock/control part of **slice 4** and the guarded-memory
prerequisite in **slice 6**, with bounded Python/JSON/script coverage in
**slice 8**. It does not close those slices. Ordinary active RAM/fetch layers,
private task bindings/views/scheduling, native hooks, queued/held/scheduled
input, active clock synchronization/budgets and caller-owned transactions are
refused before the first rule read/tick or target execution. Memory-search
snapshots do not yet identify the native layer/fetch/private-task view; new
periodic rules must not edit that unqualified view. Layer/task-aware memory
identity and hook-aware clock execution remain a later integration step.

Fresh focused evidence includes eight actual FreeDOS cases: all three public
routes make three independently guarded writes across two distinct native
clock tokens and preserve progress after project reopen; early breakpoint
and DOS exit stop before the second tick; nonvirtual, hook and simultaneous
RAM/fetch-layer admission refusals preserve the stopped state. A separate
25-case native selection includes six of those cases and the previous 19
checkpoint, private-layer/hook, scheduler and IRQ witnesses. The integrated
host/public selection passed 102 cases, including the retained 52 DOSBox rule
checks, and one retained DOSBox saved-script/save/restore case passed on its
actual backend. These selections overlap and are not additive. Broader local
and packaging receipts are logged against the final source in !117.

Histories remain pending and all 127 formal surface qualifications plus seven
campaigns remain open. DOSBox stays default and retained. No CI, merge,
release, shared installation or private runtime/state upload is part of this
increment.

## Local continuation 2026-11-11: periodic rules over explicit RAM views

This continuation follows `ef318175478646e93b58c5e2b403ee633aee6326` on draft
MR !117 and reuses the sealed N19 executable. It adds no new native patch or
runtime version. The [start note](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/117#note_4212023694)
records the scope against the same nine canonical milestones.

`memory_snapshot(..., view='ram', task_id=<native task>)` captures a registered
selected task's effective data view. Its context binds the full native task
lifetime, runtime epoch, private backing pages, active layer IDs and native
view generation. Every captured page must belong to that private view; shared
fallback does not establish ownership. `view='base'` retains the older debugger
domain and caller-label semantics. `view='execute'` supports inspection only;
memory edits and periodic rules require the RAM view. Explicit native views
are limited to 64 KiB. A linear mapping change still invalidates that domain;
the cross-mode witness deliberately binds registered physical private pages.

A verified RAM edit creates an immutable rule-owned overlay above authored
RAM layers, replacing only the previous overlay owned by that rule. Authored
definitions, private backing, other tasks and fetch layers remain represented
separately. Each tick still captures fresh values and creates a new one-shot
expected-byte plan. Durable progress advances its view context only after a
verified overlay write. Selecting another task refuses before a tick journal
or write; a later return to the same task and unchanged view can resume the
rule. An external stack change needs a fresh capture/rule.

Intervals retain one token-bound native clock budget but dispatch through the
hook runner. A hook hit or another nonordinary stop ends the invocation before
the next tick, including a hook coincident with a fired timer. An interrupted
hook step-over retains its pending task identity so explicit continuation does
not dispatch that same action twice. Checkpoint restore preserves native
layers, hooks, task/IRQ state and the append-only rule journal; an old rule's
captured epoch is stale after cold restore and refuses without replay. A fresh
capture and new rule are required in the restored lifetime.

Fresh local validation:

- **1,159 passes, zero failures/errors/skips** across 72 regression files,
  including all 19 retained native CPU scheduler, timer/IRQ, cascade/nested
  IRQ and checkpoint preservation cases.
- **823 passes, zero failures/errors/skips** in the 24-file host/public/package
  contract selection. A subsequent 12-case view-guard selection includes the
  additional imported-source-layer physical-budget check, pre-dispatch dirty
  layer and target-CAS race refusals, execute-view and capability guards.
- **10 actual native cases** cover Python/JSON/script routes, ordinary RAM/fetch
  rules, hooks, and the integrated task-private IRQ/cold-restore witness.
  The latter uses real guest writes to A's private value, replaces its prior
  rule overlay on return to A, preserves aliased B/base/fetch views, and proves
  both stale-rule refusal and fresh-rule success after separate-process restore.
- **One retained actual DOSBox saved-script/save/restore case** passed.

These selections overlap and are not additive. The native executable is still
N19 SHA-256 `74daa2ab4e6cdb03a7d4a7f6725656fc81a0022cf171242813cfe188943e8b0f`.
This advances **slices 4, 6 and 8** without closing them. Histories, broader
vendor compatibility and formal migration qualification remain open: 127
surface rows and seven campaigns. DOSBox remains default and retained. No CI,
merge, release, shared installation or private runtime/state upload was part
of this continuation.


## Local continuation 2026-11-11: first native checkpoint histories

The first bounded part of **slice 7, Histories**, is implemented; the slice
remains in progress. This continuation follows the FreeDOS/file-workspace plan
amendment at `b2b7483af10675989846942da5e26f3a3482d732` and
adds persistent immutable full-process checkpoint DAGs for an owned native DOS
session. `rewind_start`, `rewind_record`, `rewind` and `rewind_status` expose
bounded nodes, retained branches and explicit manifest/node selection across
sessions. An ordinary record performs a stopped single step; explicit
`advance='capture'` records a manually advanced stopped boundary, including an
admitted active hook/IRQ boundary, while leaving the interval unobserved.
Branching retains earlier nodes and counts their checkpoint payloads against the
cumulative history budget. The native checkpoint remains scoped to private
QCOW2 and admitted controls and reports `host_files_restored=false`.

Before any step, capture or restore, an immutable pending revision records the
intent. Uncertain completion closes the owner and leaves that journal unresolved
instead of replaying it. Manifest updates use an atomic latest-parent check.
Unrecorded mutations invalidate the live edge; explicit capture can attach the
new stopped state without describing the intervening instructions. A process
nonce still fences each live owner, while compatibility neutralizes only the
authored loader nonce field so a fresh process can restore a matching node.
Existing checkpoint admission runs before an intent or forward step: held or
queued input, a bound input schedule and active clock controllers refuse while
preserving their live owner. Failure after possible execution or capture keeps
the pending journal and closes the owner.

Fresh local validation includes **79 focused host/public/deadline/hook passes**
and **five actual QEMU Histories witnesses**: ordinary step/rewind through
Python, JSON and scripts; an IRQ/task-private capture, retained branch and
separate-process restore; and queued-input admission refusal with an unchanged
guest and history.
The IRQ/task-private witness compares CPU/PC, clock, pending IRQ frames and PIC state, hook counts,
private RAM and fetch bytes for both tasks, and untouched shared base bytes.
The host suite includes 41 actual-project/fake-native cases for immutable DAGs,
project reopen, changed identity, budgets, corruption, unresolved intents,
partial batches, stale epochs, closed owners and replacement-channel cleanup.
The first native runs exposed and then verified fixes for replaced-channel
deadline cleanup and the nonce-dependent compatibility key. The input/controller
refusal regressions also caught and verified the pre-intent admission order.
The integrated preservation selection passed **1,724 tests across 87 files**,
with zero failures, errors or skips and unchanged source/witness hashes. It
includes the five new native history cases and all 19 retained native scheduler,
timer/IRQ, slave-PIC/cascade, nested-interrupt and checkpoint preservation cases.
The retained DOSBox histories/deltas/timelines/trials selection passed **229
tests**, including four actual native rewind cases. The final payload, skill
and migration metadata selection passed **48 tests**. These selections overlap
and are not additive. The local evidence is retained in the external study's
`histories-preservation-final`, `histories-host-final`,
`histories-admission-native`, `histories-dosbox-final` and
`histories-metadata-final` log/JUnit receipts. The exact final commit and mirror
readback are logged in !117.

Frame history, inverse
CPU/RAM partial undo, comparative trials and the separately planned bundled
FreeDOS/directory-layer and file-aware restore work remain open. The four public
rewind operations remain partial and unqualified, all 127 formal surface
qualifications and seven campaigns stay open, and DOSBox remains the retained
default. No CI result is implied.

## Local continuation 2026-11-11: native renderer frame histories

This continuation follows `50c40f7aa3d7dd96306b7da940d81356117e9bb9` on
draft !117. The [start note](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/117#note_4213293580)
records the next bounded part of **slice 7, Histories**. The complete bundled
FreeDOS/directory-workspace amendment remains preserved.

The new native fence arms the next successful synchronous QEMU renderer
publication, including its copied pixels, and requests the ordinary pause at
the next safe CPU boundary. The fence binds its own token, the retained display
window, native epoch and exact `baseline-update-id + 1`. An earlier debugger,
hook or other stop wins. Active/unacknowledged fences exclude clock budgets and
instrumented checkpoint export/import. Cancellation retains the actual
publication/stop receipt and never retries execution.

`timeline_start/advance/rewind/status/image/pin/stop` retain immutable full
process checkpoint/PNG points in the existing persistent DAG. The root is an
explicitly paused CPU/surface point. Every completed child binds one native
renderer publication, full private QCOW2 state and stored PNG. Rewinding and
creating a child retains the previous branch; named points restore after the
original process and project close. Image retrieval reads stored bytes, and
pinning copies a cached checkpoint without recapture. Unrecorded mutations
invalidate the live edge. Full storage and released input are admitted; held
frame keys, scheduled frame edges, partial-memory policies and delta retention
remain open.

Every execution/capture/restore has a prior immutable intent. Uncertain
completion closes the owner with that intent retained. A known early stop
ends the invocation without another continue or a fabricated frame point.
Both observed and final fence receipts survive a coincident nonordinary stop,
distinguishing a published image from a recorded safe history node. A frame
fence completed during pending hook displacement also ends that invocation
before another continue. PNG payload limits apply before artifact publication;
restore checks stored image/version/hash and decoded pixels before native
load, then compares the retained native publication and RGB bytes after load.

The **unit is a completed synchronous renderer update**, not completed guest
drawing, VBlank or physical scanout. `completed_guest_frames` remains false.
Observation cadence is not a claimed VGA refresh rate. State and PNG payloads
count against cumulative history limits, with the existing project-wide
256 MiB artifact cap able to bind first; live QCOW2 growth remains separate.
The full checkpoint still reports `host_files_restored=false`.

An isolated N20 runtime adds the fence without changing N19. Its source patch
and manifest are under `native/qemu-frame-history/`; binary SHA-256 is
`411e868d941cf7cd138a39b931ac9886cd8156f79eb658174bfff44bc01800ed`.
The first native run passed seven cases but exposed a display-checkpoint
decoder that required precise-VGA configuration for standard-profile pixels.
The native fix makes that requirement conditional on admitted precise retrace;
precise snapshots retain the strict requirement. The mode-13h renderer-publication
rewind/branch/cold-restore witness then passed with its pixel oracle intact.

The focused integrated selection passed **133 tests**, including all **nine
new actual QEMU cases** and the five retained native checkpoint-history cases.
New witnesses cover mode-13h renderer pixels against stopped guest VGA memory,
branch/image retention, offline PNG export, separate-process restore and the
next real publication, early hook/breakpoint stops, input refusal, native
clock/checkpoint-controller exclusion and idempotent cancellation, and
task-private RAM/fetch layers with same-site hooks and genuine IRQ state.
The retained DOSBox history/delta/timeline/trial selection passed **317 tests**,
including eight actual frame-timeline and four native rewind cases, with zero
failures, errors or skips. The final integrated preservation run passed
**1,864 tests across 98 files**, with zero failures, errors or skips and
unchanged Python source/witness hashes. It includes all 19 retained native
scheduler, timer/IRQ, slave-PIC/cascade, nested-interrupt and checkpoint cases,
the five retained native history cases, all nine new renderer-history cases,
and the four late frame-completion regressions. A focused deadline selection
passed **88 tests** after the wrapper was extended to close all four new
mutating frame operations on late completion, retaining the actual result.
Final payload/skill/migration checks passed **48 tests**. These selections
overlap and are not additive. The external study retains
`frames-preservation-complete`, `frames-dosbox-complete`,
`frames-deadline-final` and `frames-metadata-final` log/JUnit receipts; !117
records the exact final commit and both mirror readbacks.

This advances slices **4, 5, 7 and 8** without qualifying a whole milestone.
Frame/input parity, lossless delta retention, inverse CPU/RAM partial undo,
comparative trials, planned directory/file-aware restore, all 127 formal
surface qualifications and seven campaigns remain open. DOSBox-X remains
default and retained pending local parity. No CI, merge, tag, release, shared
installation or private runtime/state upload is part of this continuation.


## Local continuation 2026-11-11: native frame-key ownership and input restore

This continuation follows `972250231055d50a2ee66cdcac6ffa16e123258d` on
draft !117. The [start note](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/117#note_4213836028)
records the next bounded part of **slice 7, Histories**, with associated input
and checkpoint work. The complete FreeDOS/directory-workspace amendment,
original stack target and prior evidence remain preserved.

The optional N21 native extension applies atomic PS/2 makes/breaks with the CPU
stopped. A token, native clock epoch and monotone generation bind ownership;
ordinary physical leases remain separate. Query is observational. The first
accepted batch claims an owner only after preflight, and an empty owner can be
explicitly detached before ordinary input resumes. Detach increments the CAS
generation and retains accepted-edge counts, so reacquisition uses the observed
highwater. Wrong tokens, stale generations, invalid transitions, foreign holds,
controller conflicts and unavailable capacity refuse before input effects.
Active foreign keyboard input invalidates ownership.

PS/2 capacity is conservative: at most two edges when its FIFO/controller
output is quiescent, zero otherwise. This does not add typematic repeat;
`repeat_supported=false` remains explicit. Input acceptance is not evidence of
guest consumption, completed guest drawing or DOSBox parity. Native dispatch
uses the validated captured PS/2 handler under QEMU's global lock while paused,
without continuing the CPU or virtual clock.

Frame histories retain their full checkpoint/PNG DAG, stored images and earlier
branches. Accepted current-point input appends a journal and marks the live
point dirty. A completed renderer child binds the resulting key state; pinning
a dirty point refuses, and zero-frame rewind restores the cached current point.
Scheduled input is fully validated before the first effect, with later actual
capacity refusal preserving the recorded prefix. Scripts stop on incomplete
frame advancement and retain the stop/result. Failure closes newly acquired,
restored or uncertain held ownership, while an untouched entry-held key can
remain paused. Legacy DOSBox cleanup semantics are preserved.

Instrumentation format 2 records held QCodes and counters together with PS/2
modifier, queue and command state, controller state and exact throttle deadline.
The canonical digest covers device behavior bytes using fixed-width scalar
encodings. VMState now carries the missing modifier state and throttle timer.
Cold restore validates the restored device proof and adopts ownership under a
fresh token/epoch without reinjecting makes. Ordinary leases, pending inputs and
active schedules still require explicit resolution before saving. Format 1
remains supported for the prior runtime; N20 retains released-input frame
histories. Full restore still reports `host_files_restored=false`.

The first native run exposed that the ordinary QEMU input route silently drops
events while paused; the new stopped path calls the preflighted handler directly.
Review also found the need for transient exact-keyboard authorization on the
first batch and script termination at interrupted publications. Those paths
have dedicated regressions rather than a weaker acceptance-only claim.
The first broad run also exposed a host guard that queried frame ownership
while an ordinary native input plan was already active, preventing legacy
schedule observation/cancellation. The guard now admits observation and
resolution of a valid bound schedule, refuses inconsistent simultaneous
ownership, and still checks/detaches before a new plan is armed.

The corrected N21 native selection passed **14 actual QEMU cases**: BIOS and
raw IRQ1 makes/consumption/releases, separate-process held-key restore without
reinjection, scheduled edges/branching/dirty zero rewind, CAS/capacity guards,
Python/JSON/script dispatch, failure cleanup, task-private IRQ checkpoints,
legacy detach/reacquisition and actual running foreign-input invalidation.
The binary SHA-256 is
`54773e161f54f5c356bb1626b6c82f5cb1362e77329ce8c7001aea892ebfe19a`.
The packaged 14-file incremental patch applies to a separate copy of sealed N20
source and yields exactly the recorded N21 file hashes. N19 and N20 binaries
remain unchanged. Source, patch and build identities are under
`native/qemu-frame-keys/`.

The final integrated preservation run passed **1,917 tests across 102 files**,
with zero failures, errors or skips and unchanged Python source/witness hashes.
It includes the retained native task/scheduler/timer/cascade/nested-IRQ,
checkpoint-history and renderer-history cases, plus all new frame-key cases.
The retained DOSBox history/delta/timeline/trial selection passed **317 tests**,
including the actual native frame-timeline and rewind cases. The focused native
legacy input-schedule/retrace/press/type selection passed **58 tests**, and
N20 retained runtime/history preservation passed **14 tests**. Selections overlap
and are not additive. External log/JUnit receipts use the
`frame-keys-preservation-final`, `frame-keys-dosbox-final`,
`frame-keys-native-corrected`, `frame-keys-schedule-preservation` and
`frame-keys-n20-preservation` stems. Final payload/skill/migration metadata
verification passed **48 tests** (`frame-keys-metadata-final` receipts). The
exact commit/mirror readback is recorded in !117.

All **127 formal surface qualifications and seven campaigns** remain open.
Partial CPU/RAM undo, lossless delta retention, comparative trials and the
planned FreeDOS/directory/file layers remain future work. DOSBox-X remains
default and retained. All checks were local; no CI result is implied.


## Local continuation 2026-11-11: lossless frame-history checkpoint deltas

This continuation follows `8bf6e49f0605a88a49284f19ec7065f1f3f41a1c` on
Draft !117. The [start note](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/117#note_4214379025)
records the next bounded part of **slice 7, Histories**. The complete prior
handoff and FreeDOS/directory-workspace amendment remain preserved.

`timeline_start(storage_mode="delta", keyframe_interval=...)` now opts into
lossless retention of the exact full native checkpoint archive captured at each
renderer point. Full is still the default. The shared bounded XOR/zlib codec
binds immediate DAG-parent identity, lengths, hashes, depth, descriptor, payload
and canonical metadata; full keyframes and full fallback keep reconstruction
bounded. PNGs remain full and lossless. No original target, screenshot, private
checkpoint or database is added to Git.

Internal capture-to-bytes and verified load-from-bytes paths share the existing
full checkpoint controls and native restoration. Selected deltas are published
without first persisting a duplicate full checkpoint. Full keyframes remain
ordinary state artifacts. Restore reconstructs transiently; pin is an explicit
standalone full-state export with the original exact bytes. A version-fenced
renderer manifest preserves old full histories and makes older readers refuse
new delta histories. There is no eviction, branch truncation or deletion.

State, PNG and input dependencies are checked before restore intent or forward
execution. Corrupt/missing ancestors, mismatched source/version/metadata,
invalid depth and conflicting budgets refuse before replacing the live owner.
After an uncertain execution/capture/publication failure, the existing pending
intent and close behavior remain. Known early hook/debugger stops retain their
actual prefix. Frame-key ownership, dirty input journals, zero-frame rollback,
private RAM/fetch layers, hooks, checkpoints and real IRQ state use the same
full-state semantics.

Status separates retained checkpoint payload/canonical metadata, reconstructed
full bytes, PNG bytes and input journal. Delta selection includes wrapper cost
and falls back when unprofitable or above the 16 MiB non-state artifact cap;
full states retain the existing 128 MiB cap. History admission conservatively
reserves a comparable full checkpoint and PNG. Immutable manifest revisions,
explicit pins, live private QCOW2 growth and codec working memory are separate
costs; no quota or future compression ratio is promised. Deadline checks bracket
bounded codec calls, without interrupting zlib mid-call.

The focused local selection passed **160 host tests**, and all **four new
actual QEMU cases** passed on the unchanged N21 binary
`54773e161f54f5c356bb1626b6c82f5cb1362e77329ce8c7001aea892ebfe19a`.
The native byte oracle records each point's original pre-encoding capture;
separately executed snapshots are not substituted for that oracle. Witnesses
cover exact pin reconstruction, full PNG/VRAM pixels, retained branches,
offline images and separate-process delta restore, corrupt-base refusal,
held-key restore without make reinjection, and genuine task-private IRQ,
layer and hook continuation.

In the authored mode-13h branch/cold-restore fixture, six retained nodes used
20,892,989 checkpoint payload bytes for 31,574,427 reconstructed bytes
(**33.83% payload reduction**), plus 5,044 canonical metadata bytes and 9,026
PNG bytes. This is a measured fixture's node retention, excluding explicit pin
exports, manifest revisions and live disk; it is not a whole-database or
arbitrary-workload compression claim. The external sanitized observation is
`frame-deltas-storage-observation.json`.

The final integrated preservation run passed **1,950 tests across 107 files**,
with zero failures, errors or skips and unchanged Python source/witness hashes.
It includes all four new actual delta cases and the retained 14 owned-key,
nine renderer-history, five checkpoint-history and native task/scheduler/IRQ
preservation cases. The retained DOSBox history/delta/timeline/trial selection
passed **317 tests**, and the sealed N20 renderer/checkpoint history selection
passed **14 tests**. Final payload/skill/migration metadata passed **48 tests**.
Selections overlap and are not additive. External log/JUnit receipts use
`frame-deltas-preservation-final`, `frame-deltas-dosbox-final`,
`frame-deltas-n20-preservation`, `frame-deltas-native-focused`,
`frame-deltas-host-integrated` and `frame-deltas-metadata-final` stems. Exact
commit and both-mirror readback are logged in !117.

Histories remains in progress; selected CPU/RAM undo, comparative trials and
the planned FreeDOS/directory/file layers remain open. All 127 formal
qualifications and seven campaigns remain open. DOSBox-X remains default and
retained. All verification is local; no CI is run for this continuation.


## Local continuation 2026-11-11: selected CPU/RAM undo

This continuation follows `4392f24b3aaea43ca9d918937fbb8bcb5663ba44` on
Draft !117. The [start note](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/117#note_4214684570)
records the next bounded part of **slice 7, Histories**. The entire prior
handoff, FreeDOS/directory-workspace amendment and stack target are preserved.

Source-bound native DOS processes now expose `cpu_delta_start/status/record/rewind/recover`
through Python, the existing `debug-delta-*` JSON methods and `delta-*` scripts.
An explicit projection selects 1..64 source RAM ranges totaling at most 64 KiB
and exposed GPRs/RIP/EFLAGS. Ranges must have unique owned physical backing;
RAM reads and inverse overlays use the selected task-private view when active.
Control/segment/FPU registers are outside the projection. Only arithmetic
EFLAGS bits may change; changing RSP with owned native interrupt frames refuses.
The target PC must remain within the verified source module and CS context.

A full native recovery anchor precedes recording. Immutable hash-bound JSON
deltas retain selected before/after fingerprints and the actual observed
single-step stop under stable source/run/epoch, mode, task, backing, layers,
frame-key and IRQ ownership. They are observations, not instruction-retirement
proof, memory-access tracing or deterministic replay. Pending task switches,
pending hooks and steps starting at active hooks refuse. Known interrupted or
context-changing stops retain the actual completed prefix and end recording;
scripts stop before subsequent operations. An observed ownership mismatch
permanently invalidates the cursor, even if the context later switches back.
Anchor, delta and inverse-provenance costs share conservative cumulative
budgets, with the existing project-wide artifact cap still binding.

The inverse validates the complete selected preimage and chain, then freezes
before the first write. It applies one immutable native RAM overlay and one
guarded register batch, followed by full selected and unselected-register
readback plus controller proofs. This is sequential, not an atomic CPU/RAM
transaction. Unselected RAM/registers and devices remain current; hidden CPU
state remains unknown. Preservation policies can retain declared selected
registers/bytes, but `allow_partial_resume=True` refuses, including whole-script
static preflight. Uncertain dispatch/readback/publication closes the owner.
After a successful inverse, inspection is allowed; execution, capture, further
inverse and other mutation remain blocked until verified full recovery.

Recovery loads the validated full anchor or an explicitly selected complete
checkpoint/frame point. The shared full loader clears the freeze only after
source/native/control restoration succeeds. Both default full frame points
and reconstructed lossless-delta frame points use that path. Full recovery
rotates owner/epoch identities and preserves held keys without make reinjection.
Existing full/delta history DAGs, branches and stored images remain retained;
selected operations invalidate only their live edge. Projection artifacts stay
immutable, but the selected live cursor does not reattach across a restart.

Five new actual QEMU cases passed on unchanged N21. COM and genuinely relocated
MZ witnesses revert selected RAX/RIP and RAM while excluded RBX/RAM retain
later values, enforce the freeze, fully recover and execute again. The combined
private-task witness undoes task A's selected RAM while preserving task B,
shared backing, active RAM/fetch layers, same-site hooks, held Shift+A keys,
clock state and a genuine in-flight IRQ. The expected task-manager generation
advances once for the verified private overlay; all other task/frame/controller
proofs remain strict. Full recovery continues to the next real task hook.
Separate witnesses recover frozen state through full and lossless-delta frame
points. N21 remains `54773e161f54f5c356bb1626b6c82f5cb1362e77329ce8c7001aea892ebfe19a`;
no native rebuild was needed. Private native states, databases, target inputs
and media remain outside Git.

The final integrated preservation run passed **2,022 tests across 112 files**,
with zero failures, errors or skips and unchanged Python source/witness hashes.
It includes all five new actual CPU/RAM cases, four lossless-delta cases,
14 frame-key cases, nine renderer-history cases, five checkpoint-history cases
and the retained native task/scheduler/timer/cascade/nested-IRQ witnesses.
The retained DOSBox history/delta/timeline/trial selection, now also including
its native CPU/RAM inverse and recovery tests, passed **323 tests**. Sealed N20
renderer/checkpoint histories passed **14 tests**, and final payload/skill/
migration metadata passed **48 tests**. Selections overlap and are not additive.
External log/JUnit receipts use the `cpu-undo-preservation-final`,
`cpu-undo-dosbox-final`, `cpu-undo-n20-final`, `cpu-undo-native-final` and
`cpu-undo-metadata-final` stems. The exact source commit, mirror heads and
GitLab readback are logged in !117 and `cpu-undo-final-receipt.json` outside Git.

Histories remains in progress. Comparative trials, general completed-frame/input
parity and the planned FreeDOS/directory/file layers remain open. All **127
formal surface qualifications and seven campaigns** remain open. DOSBox-X
remains default and retained until local parity is proved. No CI, release tag,
release publication or installation change is part of this continuation.


## Local continuation 2026-11-11: native comparative trials

This continuation follows `426e15eb3d4973fadd91f3c63286a5059b02d3b9` on
Draft !117. The [start note](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/117#note_4214884962)
records the next bounded part of **slice 7, Histories**. The complete earlier
handoff, FreeDOS/directory-workspace amendment and stack target are preserved.

Native QEMU DOS now uses a distinct immutable experiment format behind
`controls`, `save_experiment`, `restore_experiment` and `compare_experiment`.
The existing JSON routes and offline project experiment listing/info share
those artifacts. A saved experiment binds a complete process checkpoint,
source/version/runtime identity, endpoint CPU/source RAM, owned controls,
global and private task layer stacks, a canonical expanded script and hashes.
It uses the existing validated full loader and its fresh control/layer bindings.
The selected CPU/RAM inverse is never a whole-machine trial reset.

Each arm restores the same full checkpoint and runs the same bounded script.
The candidate replaces one explicit ordered global stack, or the saved
selected task's private stack while preserving all other tasks. Original
layer definitions stay immutable; native-bound candidates require captured
origin/task/backing proof before fresh binding. Logical layer identity omits
storage creation time and fresh owner fields, while retaining version, kind,
patches and stable task/backing identity. The saved endpoint is checked against
the checkpoint and after restoration before execution.

Admission limits cover 128 expanded script steps, at most 64 KiB of combined
endpoint and script memory observations, 1,024 requested trace boundaries and
four ungridded images. Omitted trace counts retain the native default of 128.
Project capacity is reserved before capture or trial dispatch, including
script reports, traces, images and the final comparison; ordinary per-artifact
and project limits still bind. Input, layer/history mutation, selected undo
and nested restoration are excluded from trial scripts. Assertions and control
deletion use validated receipts and restored logical control bindings.

Endpoint observations use source coordinates and the explicit native RAM view,
including selected task-private pages. Script memory reads remain explicit
runtime address/space observations. The comparator validates capture counts,
operation/range identity, artifact kind/run/version/bytes/hash, stopped image
proof, source trace qualification and endpoint source/runtime/task identity.
It retains raw receipts while normalizing only verified fresh owner/control
identities. PNG byte identity and decoded pixel identity remain distinct.
An incomplete, interrupted, corrupt or misaligned capture cannot prove equality.
A failed baseline skips the candidate. Equality is only over captured qualified
observations, with no deterministic replay or full-program equivalence claim.

All execution and final full baseline recovery share one outer deadline.
Uncertain dispatch, capture/publication or recovery effects close the owner;
there is no automatic trial retry. Full checkpoint restoration preserves the
admitted native clock/media/input profile, held frame keys, private RAM/fetch
layers, hooks, scheduler and IRQ frames. Full/lossless history DAGs, branches,
PNGs and selected-undo artifacts remain retained; trial operations invalidate
their live cursors. A frozen selected inverse refuses save/compare, while
explicit `restore_experiment` can recover through the trusted full checkpoint.

The first actual COM trial exposed an existing timed-source-trace issue after
full restoration: its native clock had a fresh verified owner epoch while
trace metadata still used launch admission. Capture-local metadata now uses
the current verified clock admission. Launch metadata and strict epoch checks
are preserved; the original-epoch event-index qualification is not expanded.
The reproduced trial then passed with complete timed source observations.

The final integrated preservation selection passed **2,144 tests across 118
files**, with zero failures, errors or skips and unchanged Python source/witness
hashes. It includes all six new actual QEMU cases, all five retained selected
CPU/RAM undo cases, four lossless-delta cases, 14 frame-key cases, nine renderer
history cases, five checkpoint-history cases, and native task/scheduler/timer/
cascade/nested-IRQ preservation. The focused host selection passed **160 tests**.
The retained DOSBox history/delta/timeline/trial and native selected-undo
selection passed **323 tests**; sealed N20 histories passed **14 tests**, and
final payload/skill/migration metadata passed **48 tests**. Selections overlap
and are not additive. External log/JUnit receipts use the
`trials-preservation-final`, `trials-host-final`, `trials-native-final`,
`trials-dosbox-final`, `trials-n20-final` and `trials-metadata-final` stems.

The six native cases cover COM/MZ source-layer comparisons, ordinary global
physical-bound layer rebinding, actual step/trace/run/machine-memory receipts,
PNG export, offline experiment info and reopened restore. They compare an
unchanged baseline and a differing candidate, retain original candidate hashes,
restore a failed baseline with hook hit counts and controls, preserve A/B
private IRQ/held-key state and continue to the next real task hook, and recover
frozen selected undo while retaining lossless frame points and images. A probe
that placed a breakpoint at the trace's next stop correctly produced an
incomplete baseline and skipped the candidate; the successful witness places
its subsequent run stop outside that traced interval. No incomplete trace was
reclassified as equal.

N19/N20/N21 hashes remain unchanged; no native rebuild was needed. N21 remains
`54773e161f54f5c356bb1626b6c82f5cb1362e77329ce8c7001aea892ebfe19a`.
The exact source commit, four mirror refs and !117 note/description readback
are recorded in `trials-final-receipt.json` outside Git. Private checkpoints,
media, target inputs and project databases remain outside the checkout.

Histories remains in progress. General frame/input and workflow parity, the
planned FreeDOS/directory/file layers, and all **127 formal surface
qualifications and seven campaigns** remain open. DOSBox-X stays default and
retained until local parity is proved. No CI, release tag, release publication
or installation change is part of this continuation.


## Checkpointed FreeDOS directory/file layers (2026-11-11)

This bounded implementation advances the bundled FreeDOS/file-workspace
amendment without closing that entire plan. It keeps DOSBox-X as the default
and retained backend. No CI, release/tag or shared-prefix installation is part
of this continuation.

The optional native COM/MZ launch prepares one private composite disk: a small
FreeDOS 1.4 C: system and a FAT16 D: directory workspace. C: and D: share disk0,
so the existing native full snapshot transaction captures both alongside CPU,
DOS kernel caches, JFT/SFT handles, file offsets and directory-search state.
The process helper selects D: and the executable's parent directory before
load-only EXEC. Explicit roots and deterministic 8.3 aliases cover bounded
nested paths; symlinks/special entries, unstable captures and unsupported
mappings refuse admission. See [the file-layer guide](DOS_FILE_LAYERS.md).

A caller-selected root defaults to game_dir; only omitted game_dir uses the
captured Python/CLI cwd or server startup workspace. Admission retains original
host paths, mappings and identities. Guest reads/writes use a copied private
FAT volume, including raw disk access; host originals are never mounted writable.
File generations retain immutable 64 KiB chunks, hashes, lineage and protected
original paths. Full checkpoints seal committed FAT inventories from a supplied
standalone snapshot copy, never from a live QCOW image. Rewind branches preserve
earlier generations and original chunks. New checkpoint format
`fdisbull-qemu-dos-workspace-qcow2-v1` binds the file-generation record, disk
layout, runtime component and QCOW/raw/volume hashes. Restore validates these
before replacing the VM and adopts the namespace only after full restoration.
Older checkpoint formats keep their earlier scope.

Python and JSON expose workspace status, base/effective/difference inventories,
reads, full-checkpoint seal, exclusive export/keep, and immutable staged edits.
Create/import/write/range/resize/rename/delete produce inactive children;
`dos_generation` activates a selected child at cold boot without requiring the
original host tree. A changed executable cannot silently replace the original
source-bound program. JSON file payloads use data_hex. Physical exports survive
rewind while historical guest namespace membership is restored; importing an
export and cold launching a new generation makes it visible again. An explicitly
authored create can qualify for keep. A raw guest directory difference cannot
prove create versus rename, so guest outputs use general exclusive export after
the caller establishes close/flush. Originals and pre-existing destinations
remain protected, including after rename and deletion.

FreeDOS runtime preparation pins the official floppy, kernel and FreeCOM
archives, carries their complete source packages/notices, extracts matching
kernel/shell bytes, and builds a separate minimal image and portable archive.
Source and installed-wheel recipe resources are covered by local checks.
The final private receipt pins component-04 and its native boot evidence;
manifest boot_validation remains pending because the builder does not run QEMU.
The standalone rebuild reproduced guest files/boot code but changed FAT serial
and timestamps; byte-reproducible builds remain open. Authored MBR assembly
matches the emitted 440-byte loader exactly.

Local witnesses cover COM/MZ CRUD and open-handle/offset restore, dirty writes
and FindFirst/FindNext cursor restoration, cold restore after moving the original
host tree, staged-byte activation, aliased subdirectory relative I/O, and a
flushed binary export that survives rewind. Separate existing deep native
scenarios run against the composite disk with their assertions preserved:
comparative trials with private IRQ/held-key state, selected CPU/RAM inverse
with full recovery, and lossless frame histories with task-private RAM/fetch
layers and hooks. The full prior preservation selection is retained as well.

Limits remain explicit: live refresh/host synchronization is refused; automatic
keep patterns and guest-create provenance are open; file inventories contain
committed FAT bytes, while unclosed buffers live in the accompanying full VM
checkpoint. A malformed/transient FAT inventory is refused. Long-filename DOS
APIs, network filesystems, general driver/application compatibility and every
internal DOS capture boundary are unqualified. Selected CPU/RAM undo still
freezes execution and does not rewind files/devices; a full recovery restores
the file-aware anchor. Manual/renderer histories retain their existing scopes,
including completed_guest_frames=false. host_files_restored=false remains
accurate: the private guest filesystem is restored; physical host files are not.

The inventory now tracks 134 surfaces (the 127 prior surfaces plus seven
native-only workspace routes) and seven compatibility campaigns. All formal
promotion qualifications remain open. No DOSBox removal is permitted.


Fresh local verification for this slice: **2,257 passes across 131 preservation
files**, **nine new native workspace cases**, **323 retained DOSBox cases**,
**14 retained N20 history cases**, and **63 payload/skill/migration/dispatch
checks**; zero failures/errors/skips in these completed selections. Selections
overlap. Python source/test hashes stayed unchanged during the 131-file run.
A subsequent CLI-only correction permits omitted --game-dir for qemu-dos and
adds a parser regression; affected CLI/backend/dispatch and package checks are
rerun after that correction. Native engine, checkpoint and filesystem code is
unchanged from the preservation run. N19/N20/N21 binaries are unchanged.

The final CLI follow-up selection passed **83 tests** with **one unrelated
ScummVM/private-KQ1 test skipped** because that separate runtime/input was not
provided. Only cli.py and its new runtime CLI test differ from the frozen
preservation-run Python hashes; the affected parser/backend/dispatch/payload
selection was rerun on those final bytes. This is a source contribution and
private prepared runtime, not a tagged release or activated installation.

## Controlled checkpointed host refresh (2026-11-12)

The next file-workspace increment makes the existing Python/JSON
`workspace_edit(generation, 'refresh')` operation usable for checkpointed
workspaces. It captures the admitted host root again and publishes an inactive
immutable child. A separate cold launch can select that generation. It never
changes the active guest disk, loaded RAM, file handles/offsets, caches, source
binding or history cursor. Full checkpoints retain their previous filesystem
view even after host files change.

The selected branch must match its last admitted host revision; private
content, namespace or metadata edits refuse refresh instead of being merged.
The recorded root device/inode must still match. The executable must retain
the immutable base's host-relative path, DOS alias and original SHA-256.
Changed, deleted or remapped source files refuse before generation publication.
New host paths extend protected original/alias sets monotonically; older
generations, chunks and tombstones remain readable. Capture retains its
two-stable-pass no-follow contract and does not exclude noncooperating ABA
writers. General live host visibility remains refused at launch.

Review exposed two related edge cases. A checkpoint can order inventory entries
by DOS alias while host capture orders them by host spelling. Refresh now
compares unique DOS-path-keyed projections, preserving exact content/metadata
checks without a false ordering conflict. Cold launch now refuses multiple
original executables with the same project basename and hash instead of
choosing a potentially different parent directory; it also verifies the
selected host-relative path. Separate regressions reproduced the former
false conflict and ambiguous selection before their fixes.

Native COM/MZ witnesses refresh while an actual guest handle is open at offset
two, retain that handle and history cursor, restore the earlier full checkpoint,
and cold launch both generations to their respective file bytes. Host file
addition, modification and deletion remain isolated from the active guest.
Private-edit conflicts, executable changes and root replacement refuse while
the original live owner remains usable. Source and staged-generation host
tests additionally cover missing/remapped executables, unstable capture,
symlinks, repeated refresh, retained old bytes and protected host paths.

This advances the file-workspace amendment across slices 5, 6, 7 and 8; it does
not qualify general live filesystem access or the whole migration milestone.
Automatic keep policies, guest-create provenance, live reconciliation and broad
filesystem/application/driver parity remain open. Trials, full/lossless
histories, selected CPU/RAM undo, frame keys, task-private RAM/fetch layers,
hooks, checkpoints and IRQs retain their established scopes. All 134 surface
qualifications and seven campaigns remain open. DOSBox-X stays default and
retained; no CI, native rebuild, release/tag or installation is performed.

Fresh local verification on the integrated source passed **2,273 cases across
132 preservation files**, including the three new actual-QEMU refresh cases,
with zero failures/errors/skips. Python source and test hashes remained
unchanged throughout that run. Separate focused selections passed 46 host
workspace cases, 323 retained DOSBox cases and 58 runtime/dispatch/package/skill
checks, also with zero failures/errors/skips. Selections overlap. Receipt/log
names use the private `refresh-preservation-final`, `workspace-refresh-native-final`,
`refresh-host-final`, `refresh-dosbox-final` and `refresh-metadata-final` prefixes;
earlier evidence remains intact.

The retained N20 renderer/checkpoint history selection also passed all 14 cases
with zero failures/errors/skips. Final staged metadata verification passed all
58 cases again. No Python source or test bytes changed after the integrated run.

## Caller-attested output capture and atomic exports (2026-11-12)

The next file-workspace slice adds Python `workspace_save_output` and JSON
`debug-workspace-save-output`. It requires literal `closed_and_flushed=True`
caller attestation, checks a stopped qualified FreeDOS file/buffer boundary,
seals a complete native checkpoint, validates the selected file in that sealed
generation and exports it to a new absolute physical destination. The receipt
binds source/version, process nonce hash and epoch, runtime, checkpoint,
generation, exact file bytes and the durable export. It records caller-attested
provenance and guest_create_provenance=false. Strict `workspace_keep` is unchanged.

The observer uses explicitly physical, unwrapped conventional RAM below
0xA0000. Complete global SFT and DOS buffer lists must show no ordinary open
files and no dirty buffers in repeated equal observations before and after the
full checkpoint, with stable CPU/process identity. No guest execution or DOS
close/flush is injected. Full paths, sharing, locks, coherence and the actual
flush boundary remain unknown. This is a trusted-runtime observation plus
caller attestation, not a general guest-create or kernel-integrity proof.

Initial admission is restricted to the boot-witnessed component-04 system image
and matching minimal runtime/package identities. A verified real-mode,
unpaged, single-CPU context is required; active global/task-private layers,
physical/scheduled input or frame-key ownership, clock budgets/sync and caller
transactions refuse this route. Other existing debugging paths retain their
contracts. Broader runtime/layout and contextual qualification remains open.

All existing workspace exports now stage bytes in a random same-parent file,
fsync/readback-verify them, recheck protected/case/DOS aliases and publish with
an exclusive hard link. No final path is exposed by a partial write. Existing
destinations are never overwritten. Post-publication or receipt failures retain
the physical file and precise available effect evidence; no operation is
automatically replayed. Exact-name link races are exclusive; concurrent
case/alias behavior and hard-link support remain filesystem-dependent.

The first actual COM output witness exposed a pre-existing cold-import defect:
staged import/create defaulted to invalid DOS date zero. Both now default to
1980-01-01. A host cold-disk regression fails for both operations against the
previous store and passes with the corrected defaults. Existing immutable
generations and host metadata are not rewritten. The first failing native run
is retained separately from the corrected COM/MZ passes.

The native witnesses verify binary output export, refusal with open/dirty
files and without explicit attestation, protected paths and existing
destinations, checkpoint restore to before the output existed, physical bytes
surviving rewind, and explicit staged import plus cold launch. They retain
unknown guest-create provenance and the strict keep refusal. Host failure
injection covers pre-publication writes, publication races, lost receipts and
partial-effect reporting after checkpoint creation. Histories, trials,
task-private RAM/fetch layers, hooks, checkpoints and IRQ support retain their
broader preservation suites.

The inventory now tracks 135 formally unqualified surfaces and seven open
campaigns. Automatic keep policies, general guest-create provenance, live
filesystem reconciliation and broader application/driver parity remain open.
DOSBox-X stays default and retained. No CI, native rebuild, release/tag, merge
or installation change is part of this source continuation.

Fresh integrated local verification passed **2,328 cases across 135 files**,
including all three new actual-QEMU output cases, with zero failures/errors/skips.
All Python source/test hashes remained unchanged throughout that run. Separate
focused checks passed 104 host cases, 323 retained DOSBox cases and 59
runtime/dispatch/payload/skill/migration cases, also without failures/errors/skips.
Selections overlap. The original native cold-import failure and the two
baseline-store regression failures are retained with the corrected passes;
the separate failed baseline test-setup import is labeled as a collection error.
Private receipts use `output-preservation-final`, `output-native-fixed-02`,
`output-host-final`, `output-dosbox-final` and `output-metadata-final` prefixes.

The retained N20 history selection passed all 14 cases, and the final staged
metadata selection passed all 59 cases, with zero failures/errors/skips.
All 1,170 Python source/test files remained identical to the integrated run.


## Guest-create provenance and opt-in save keeps (2026-11-12)

This slice adds an isolated native N22 candidate and six Python/JSON workspace
routes: provenance start/status/capture/stop and keep policy creation/enabling.
`workspace_keep` can consume a stored native proof; its plain authored-create
contract is retained. `workspace_keep_policy` explicitly arms one absent,
unprotected root D: non-device 8.3 path with an existing pinned physical output
directory. `workspace_seal` services that policy after the full VM/file capture;
internal history/trial captures do not publish files. There is no background
watcher, guest-boundary stop injection or automatic retry.

Native evidence covers real DOS AH=5Bh exclusive creation, zero or more complete
positive AH=40h sequential writes, optional AH=68h commit, AH=3Eh close and
returned AH=0Dh flush. It retains actual accepted payload bytes, return flags,
caller/return identities, pending INT 21h state and nested hardware frames.
Source ranges are bounded to 64 below 0xA0000, payload to 64 KiB, events to 256
and hardware nesting to 16. Unsupported mutators/process changes, vector changes,
source escapes and unowned storage/DMA/PCI activity taint evidence without
changing guest execution. Ready/invalid records remain owned until disarmed.
Full checkpoint restore compares the entire logical ledger and advances native
epoch and generation before host adoption; old idle checkpoints remain usable.

The host requires the verified original entry, where its helper establishes the
child PSP, and admits no prior unobserved interval. Observed PSP queries must
agree and process-changing calls invalidate; there is no independently justified
kernel current-PSP global read on every call. Admission and final capture use
the exact qualified component-04 initial image and matching runtime descriptors,
real/unpaged single CPU, no active layers/task views/input ownership/clock sync
or budget. Kernel RAM integrity, arbitrary TSRs/drivers and later entry arming
remain unqualified. The caller must stop after flush before termination or
another unsupported operation. Existing broader layers/hooks/task/IRQ/history
operations retain their contracts, without acquiring this new proof scope.

A proof requires stable repeated stopped file/buffer observations around the
full checkpoint and exact sealed FAT bytes equal to the captured accepted
writes. The keep policy independently validates stored proof/source/path/base
and bytes, reserves each content SHA-256 in an immutable project journal before
exclusive export, and records completion after durable publication. Versioned
names use 00000001.SAV onward, with 128 distinct versions and 1,024 events per
policy. Existing files are never overwritten. Opened-parent identity checks
reject destination swaps. Matching completed content verifies its existing file;
pending/uncertain reservations return needs-reconciliation without replay.
Journal and disable decisions survive guest rewind and reopened analysis runs,
but not a deliberate rollback of the whole FDB. Different policies are separate.

Review fixed event-persistence failure after arming and post-seal proof failures
to preserve concrete owner/checkpoint effects. An unverified post-seal native
or boundary observation closes the owner. Host mutation taints live evidence;
full restore rebinds the historical observer rather than forging a new proof.
The first real native attempt exposed a host summary size-key collision; the
artifact size now stays distinct from payload_size. Earlier failing/interrupted
logs remain separate from the corrected passes. A manually interrupted first
broad run is not counted as completed preservation evidence.

The authored N22 patch and manifest are in native/qemu-dos-provenance, applied
incrementally to sealed N21 QEMU 10.0.13. The final build09 binary SHA-256 is
0665e6d87e5c7fd23f1c62f4fabab534618fabe40c656ecbcd61d4e0d7703ce1; patch SHA-256
99f615226a728a0d80ac6456ddd8f7f6e32f0a6c020de3a73f2cbbc2aac2e6aa.
Source packaging now includes that patch and the omitted checkpoint/layer/task/
frame prerequisite directories, with fixture checks excluding runtime binaries.
No native executable, private disk, FDB or original target is added to Git.

Final focused host verification passed 147 cases, retained DOSBox-X passed 323,
and the final native provenance selection passed 13. Native witnesses include
COM/MZ payloads, explicit proof keep, policy deduplication and disabling across
rewind, in-flight INT 21h restore, actual PIT IRQ0 activity, real failed-exclusive-
create carry/error results, open output refusal and six unsupported-operation
taints. These bounded witnesses do not qualify general DOSBox or game parity.

The inventory now contains 141 formally unqualified surfaces and seven open
campaigns. DOSBox-X remains the default and retained backend. No CI, release/tag,
merge, shared installation or default-selector change is part of this slice.
Broader runtime/context coverage, overwrite/rename/seek saves, automatic safe
boundary selection, live filesystem reconciliation and application/driver
campaigns remain open. See DOS_FILE_LAYERS.md for APIs and exact scope.


Integrated N22 preservation passed **2,384 cases across 138 files** with zero
failures/errors/skips. All 1,175 Python source/test SHA-256 values stayed fixed
through that run and match the staged source. Final staged metadata/runtime/
dispatch/payload/skill checks passed all 60 cases. Selections overlap.

A separate private COM/MZ witness passed both cases after closing the debugger
and Project, reopening the persisted FDB in a new run/VM and restoring the
armed observer. It verified already-kept content produces no duplicate and a
host disable remains in force after another restore. This uses the same N22
binary and does not establish cross-binary migration. Exact patch replay from
only its touched N21 files reproduced all eight N22 after-images. Private
receipts use provenance-preservation-02-final, provenance-host-verified,
provenance-native-09, provenance-dosbox-final, provenance-reopen-final,
provenance-metadata-staged and provenance-patch-replay-receipt.json; all earlier
failure/interruption evidence remains separate. N19/N20/N21, the component-04
system image and the shared installation selector retain their prior identities.

The retained N20 renderer/checkpoint history selection passed all 14 cases,
also with zero failures/errors/skips (provenance-n20-final).


## Overwrite, rename and seek save provenance (2026-11-12)

This slice extends provenance start and keep-policy APIs with explicit
`mode="save"`, an optional temporary path and an optional stored predecessor
reference. The default exclusive-create mode and v1 receipts retain their
contracts. New native support is capability-gated through
x-fdisbull-arm-dos-save-operations and an API2 operation transcript. DOSBox-X
remains default and retained; no CI, release/tag, merge, shared installation or
default-selector change is part of this continuation.

The N23 native observer covers AH=3Ch create/truncate, AH=5Bh exclusive create,
AH=3Dh write/readwrite open, AH=40h complete writes and zero-count truncation,
AH=42h signed BOF/current/EOF seeks, AH=68h commit, AH=3Eh close, tracked AH=41h
delete, closed-file AH=56h rename, and returned AH=0Dh flush. Captured event
inputs and return flags/counts bind path, handle, cursor and size transitions.
The host independently reconstructs the final bytes from the immutable initial
preimage and chronological accepted write stream, validates every transition,
and compares the result with the sealed FAT file before proof or publication.
Native payload-hex in v2 means write stream; public proof payload hash/size mean
the reconstructed final file. Unsupported/short/failed operations taint evidence.

An existing final file must be an immutable authored create or match an exact
stored predecessor proof for the same path/source/version/workspace base.
Arbitrary unproven files and original protected host/DOS aliases cannot acquire
keep or overwrite rights. A full v2 proof revalidates its immutable arm generation
and predecessor dependencies, bounded to 32 receipts. Direct policy application
now uses that same stored-proof validation before any host reservation; source
review caught and closed the initial transcript-only policy path.

One current file identity and one open handle are modeled. A configured absent
temporary path may be written while the eligible old final remains as a shadow,
then the observer can follow deletion of that final and rename of the closed
temporary image into place. Final proof requires the configured final name and
no remaining temporary entry in the sealed generation. Policy names do not
silently follow renames. Multiple save cycles keep distinct content hashes once
per policy; the journal and disable decisions remain outside guest rewind.

Pending seek/rename inputs and ledger state survive full snapshots and fresh
process/FDB reopening. The N23 native VMState uses schema2/minimum2, explicitly
rejecting older native streams. Legacy v1 QMP/proof support is separate from
that internal schema. N22 and its exact runtime remain available for N22
checkpoints; cross-binary state migration remains unqualified. Existing trials,
histories, selected CPU/RAM undo, task-private RAM/code layers, hooks and IRQ
contracts are retained and undergo the integrated preservation selection.

Admission remains verified original entry, trusted component-04 runtime,
real/unpaged single CPU and no active layer/task/input/clock ownership. Bounds
are 32 source ranges below A0000, 256 events, 16 hardware frames, 64 KiB logical
file/cursor/preimage and a cumulative 64 KiB accepted write stream per observer.
The earlier guide's 64 source-range count is corrected to the actual native
32-range limit. V2 code mappings may exceed 64 KiB. Seek beyond EOF is observed
within the cursor bound, but subsequent hole writes or zero-count extension
refuse rather than inventing bytes. Multiple simultaneous handles, unmodeled
reads, arbitrary drivers/TSRs and automatic safe-stop selection remain open.

The authored incremental N23 patch is packaged separately in
native/qemu-dos-save-operations over sealed N22. Exact two-file apply-and-hash
replay passed. Build04 binary SHA-256 is
cf7d52018709d4d467d0cf426aa4616361a34c46c4fb590337f47f1ad0badaca;
patch SHA-256 is
8d7ac0a56445afe2ad47e9aaaa8977579ce8d1c559616a0f85bf3c5864f23339.
Earlier compiler diagnostics are retained separately; the post-load validation
was simplified into reviewed early-return checks. Review also corrected reopen
cursor reset and preservation of close/commit state across shadow deletion and
rename before final native validation.

Thirteen new real COM/MZ cases pass, including actual PIT ticks, commit,
overlapping signed seeks, truncation, two policy content versions, replay
deduplication, eligible-file open/overwrite, temp replacement, pending seek and
rename restoration after FDB reopen, and stored predecessor refusal/acceptance.
The retained v1 provenance suite passes all 13 cases on both N23 and unchanged
N22. Final host checks pass 176 cases, retained DOSBox-X 323, retained N20 14 and
metadata/runtime/dispatch/payload/skill/migration 60, all with zero
failures/errors/skips. Selections overlap. Native disk-full/short-write behavior
has not been independently exercised; that path remains unqualified despite
fail-closed implementation and host transcript rejection tests. Broader parity
and all 141 formal surface qualifications plus seven campaigns remain open.


Integrated preservation on N23 passed **2,426 cases across 141 files**, with
zero failures/errors/skips. All 1,179 Python source/test hashes remained fixed
through that run. Evidence uses save-operations-preservation-final,
save-operations-host-final, save-ops-native-02, save-ops-v1-native-01,
save-operations-n22-legacy, save-ops-dosbox-final, save-ops-n20-final,
save-operations-metadata-final and save-operations-patch-replay-receipt.json.
Native build01–03 diagnostics and initial host-fixture failures are retained
separately. The final consolidated private receipt is save-operations-final-receipt.json.
N19/N20/N21/N22, the exact component-04 image and shared installation selector
retain their prior identities.


## Automatic safe-stop selection for save keeps (2026-11-12)

N24 adds explicit safe_stop=True to a mode=save workspace keep policy. Its
outer public run selects a matched completed DOS AH=0Dh return, pauses before
the next guest instruction, validates the native stop and file evidence, seals
a full checkpoint and keeps one version under the original host deadline.
Defaults stay unchanged; no implicit continue follows publication. Scripts,
comparative trials, internal histories/CPU undo, frame and timing execution
suppress this controller and retain their existing behavior.

Three separate QMP commands SET/QUERY/ACK configure and reconcile the auxiliary
qemu-pc-dos-save-stop-v1 receipt, preserving v1/v2 save-witness info contracts.
The native request records the exact returned PC/CS/SS/SP, event count and
witness generation. The main-loop callback credits a PAUSED stop only if the
request wins. Debugger, single-step and return-site breakpoint conflicts retain
their actual cause; active clock/frame controllers cannot share ownership. The
host verifies raw GDB attribution and the last DOS return. Hook hits and pending
step-over are not swallowed by automatic continuation or a fabricated breakpoint.

Each completed eligible flush can create one fresh sequence. A ready record,
query, IRQ return or restored old attempt cannot reissue it. Settled receipts
are persisted before CAS-bound ACK. Invalid repeated unacknowledged attempts
lose automatic-stop credit while the core file-provenance ledger remains a
separate contract. Host file keeps and disable decisions remain outside rewind;
pending reservations require reconciliation without replay. The stop controller
is disabled when the outer public run returns.

Full checkpoints include the auxiliary state when opted in. Pending main-loop
handoffs refuse capture; settled consumed/preempted states are validated and
restored with advanced native owner counters. An old restored receipt is ACKed
without publication before explicit resume, and only a later fresh flush can
stop again. Native schema3/minimum3 is same-binary N24 only; N22/N23 and matching
runtimes stay retained for their checkpoints. Original-entry, qualified FreeDOS,
real/unpaged single CPU and no active layered/task/input/clock admission rules
remain unchanged. Arbitrary driver/runtime and cross-binary parity remain open.

Review closed the path that allowed an unexpectedly missing/inactive native
owner to proceed to guest dispatch. Known stop/checkpoint/export/ACK effects
survive failures, including failure to persist the close. The initial native
build exposed a target-specific macro in common runstate; a target-neutral
registered callback replaced it. Initial clean-build warnings in unchanged
media code and the first compile failure remain in their dated logs. Build02
then compiled successfully; no guest retry was needed for the first 12-case
integration pass.

The authored N24 patch is in native/qemu-dos-save-stop. Exact isolated replay
seeded six N23 files and one new callback header and matched all seven N24
outputs. Binary SHA-256 is
8af033a259892808dd5b15b524f64145aa17a6dcf3a774dc6e8d2985c31e4d27;
patch SHA-256 is
468f3bf0f1adb8f7d9f1dc11b822e983e180d892cbe1573a09a2f91dc583d195.
Source packaging includes its authored README/manifest/patch, excluding runtime
binaries. Existing N19/N20/N21/N22/N23 and component-04 inputs remain retained.

The new 12 native cases pass: exact COM/MZ post-flush PC and unchanged next
instruction marker, repeated versions, temp replacement, pending-flush snapshots,
FDB reopen/dedup/disable, competing BP/hook, script/trial suppression, tainted
save refusal and post-export journal failure. A separate private consumed-stop
checkpoint/FDB-reopen witness passes: the old attempt is durably acknowledged
without publication, the next fresh boundary is already-kept, and exactly two
physical versions remain. Focused host verification passes 235 cases, retained
DOSBox 323, retained N23 save operations 13, retained N20 histories 14 and
metadata/runtime/dispatch/payload/skill/migration 60, all with zero
failures/errors/skips. Selections overlap. Formal 141-surface qualification and
seven campaigns remain open. DOSBox-X stays default and retained; no CI,
release/tag, merge, shared installation or default-selector change.


Integrated preservation on N24 passed **2,459 cases across 144 files**, with
zero failures/errors/skips. All 1,183 Python source/test SHA-256 values stayed
fixed through the run. Private evidence uses save-stop-preservation-final,
save-stop-host-final, save-stop-native-01, save-stop-dosbox-final,
save-stop-n23-legacy, save-stop-n20-final, save-stop-metadata-final,
save-stop-consumed-restore-final and save-stop-patch-replay-receipt.json. The
consolidated private receipt is save-stop-final-receipt.json. Earlier diagnostics
remain separate. No source/native runtime is promoted by these bounded local
results; all formal qualification campaigns remain open.


## Disk-full save refusal and CHIP-8 feasibility (2026-11-12)

This slice closes two concrete negative-save witnesses without changing the
production engine or the retained N24 binary. The native test uses a real,
bounded 4,595,712-byte FAT16 D: volume, independently counts its free clusters,
and runs an authored COM program through the normal FreeDOS loader. A requested
1,024-byte AH=40h write returns AX=512 with one free 512-byte cluster and AX=0
with none; carry is clear in both observed cases. The sealed files contain
exactly 512 authored Z bytes and zero bytes, respectively.

Both completed close/flush routes reach the genuine user breakpoint, not an
automatic save boundary. The witness faults with DOS write failed or was short,
admits no payload to the proof, and creates no keep reservation, completion or
physical output. Explicit sealing reports not-ready for that policy while
retaining actual workspace bytes. Full checkpoint restore into a fresh native
process preserves the invalid witness and empty keep journal. The source and
filler originals remain unchanged; a later explicit disarm and run reaches
ordinary guest exit. The production workspace default remains 32 MiB.

The first 4 MiB, source-after-filler fixture timed out before source entry.
Retained boot-only controls show that changing either file placement or the
image size/alignment reaches entry. QEMU's first-partition CHS heuristic and
the composite BPB also disagree. That metadata finding is not a demonstrated
cause; no geometry fix is claimed or applied. The final fixture allocates the
source before filler and ends the complete disk on a 16x63 cylinder boundary.
Arbitrary near-full layouts, BIOS geometry, carry-set failures, other runtimes
and the wider overwrite/seek/rename failure matrix remain open.

Fresh verification of the final aligned fixture passes all 14 N24 native
safe-stop cases, including the two new disk-full cases, with zero failures,
errors or skips. Its two machine-readable witnesses record actual DOS AX/CF,
free clusters, file size/hash, stop cause and invalid-after-restore result.
The separate staged payload/skill/runtime/dispatch/migration selection passes
60 cases. Earlier diagnostic receipts remain distinct from this final source
run: disk-full-native-01, the positive/small-volume/probe controls,
disk-full-native-02 and disk-full-matrix-controls-01.

CHIP8_QEMU_FEASIBILITY.md separately documents a source-grounded architecture
experiment. QEMU 10.0.13 in the inspected tree has no CHIP-8 target. The existing
CHIP-8 pilot is an authored Python interpreter/decoder, not a QEMU CPU or an
independent correctness oracle. A real experiment needs a compiled TCG CPU,
minimal system machine, GDB/VMState support and a thin fDisBull non-x86 profile
before it demonstrates debugger reuse. Transport, operation budgets and
artifacts are candidates for reuse; current launch/register/PC/address/decoder
paths and DOS-specific scheduling/layers/IRQ/file protocols need explicit
architecture boundaries. The proposed later layer/hook/history/device tests
are acceptance gates, not completed capabilities. No CHIP-8 QEMU source, build,
guest execution or end-to-end package qualification is claimed.

DOSBox-X stays default and retained. All 141 formal surface qualifications and
seven campaigns remain open. Existing trials, histories, task-private layers,
hooks, checkpoints and IRQ contracts remain in the preservation selection.
No native rebuild, CI, release/tag, merge or shared installation change.

Integrated preservation passes **2,461 cases across 144 files**, with zero
failures, errors or skips. All 1,183 Python source/test hashes remained fixed
through the run. The separate retained DOSBox-X history/undo selection passes
323 cases, final native safe-stop selection 14 and staged metadata/runtime/
dispatch/payload/skill/migration selection 60; selections overlap. N19 through
N24 binary hashes, component-04 system image and the shared installation
selector retain their previous identities. Final evidence uses
save-diskfull-preservation-final, save-diskfull-native-final,
save-diskfull-dosbox-final, save-diskfull-metadata-final and
chip8-qemu-feasibility-source-audit.json. The consolidated private receipt is
save-diskfull-final-receipt.json. Earlier handoff text is preserved verbatim.


## Minimal CHIP-8 QEMU CPU/machine and fDisBull adapter (2026-11-12)

The new native/qemu-chip8 package adds a compiled chip8-softmmu TCG target and
chip8-test machine over clean QEMU 10.0.13. It is a CPU-only architecture
experiment with one helper-backed instruction per translated block, not a
Python interpreter wrapped by an x86 guest. A caller-owned raw ROM loads at
0x200 in exactly 4 KiB RAM. The named classic-pilot-default profile and separate
CPU-subset marker bind the quirks and implemented operations; display, keys,
timers, audio and RNG remain unavailable.

Existing CHIP-8 work is retained and reused: the current pilot supplies the
static opcode patterns and declared quirks, while the earlier Python UDC
catalog/compiler/sweding proof of concept remains separately preserved at
3e437a9e9ca313a2a24d18ef928a40fc5084b5f7, verified against its GitLab branch.
Its interpreter fallback and candidate UDL/UIL are not promoted to a standalone
conversion or accepted common UIL. The existing G0-G8 end-to-end plan remains
the gate for independent semantics, registered providers, emitted target
execution and held-out reuse.

The production loader admits arch=chip8 or its exact named profile, fixes the
ROM and entry at 0x200, preserves raw source identity and uses chip8:16:big
instruction facts. Classic skip/call/return edges enter the normal persistent
analyzer; unknown I-based memory addresses and V0-indexed jumps remain unknown.
SYS, SCHIP/XO, invalid and truncated words refuse static decoding. The 65,536
word classifier comparison reuses the earlier pilot and is not an independent
historical emulator oracle. Restart, patch isolation and stored SVG/PNG listing
exports pass through the ordinary project API.

An explicit qemu-chip8 backend reuses QMP/GDB transport, artifact persistence
and operation-budget patterns without x86 HMP or segmented PC interpretation.
It exposes registers, bounded RAM, guarded edits, run/step and execution
breakpoints. A QMP profile/fault receipt identifies unsupported words, fetch/
transfer bounds, stack faults and odd fetch. Faults are sticky across debugger
edits and restore; faulting operations commit no partial architectural update.
Guarded mutations require readback, including direct GDB writes whose generic
OK does not prove target acceptance. Uncertain mutation/stop paths close the
owner and retain available effects and bounded stderr diagnostics.

Native VMState schema1 checkpoints use a private guest-unattached qcow2 node,
binding exact ROM/version, profile/subset, machine/RAM, QEMU binary and
checkpoint tool. Fresh-process and reopened-FDB restore verify registers,
stack, fault receipt and the complete 4 KiB RAM before replacing the old owner.
Remove breakpoints before this first checkpoint profile. No cross-binary
restore or host-file rewind is claimed. CHIP-8 layers/hooks/histories/trials,
selected undo, devices and IRQ models remain unavailable; the corresponding
existing DOS machinery is retained separately.

All 12 authored native cases pass on binary SHA-256
65fa79f9104bf20997d9454fc0b0acabce2717816fd029323e6500bcd54cdbb6.
They include real TCG step/branch/call/return, arithmetic/logic/VF alias and
shift-from-Vy behavior, RAM transfers and limits, unsupported/device words,
stack overflow/underflow, sticky fetch fault restore, SP retirement, code
mutation/TB invalidation, source immutability and public JSON dispatch.
The 26-file source patch SHA-256 is
81fdfca213e47439d2acadea0d05ddc1e3e810e732942e8bc35cd1e1e4101e69.
Isolated replay seeded eight baseline files from the pinned archive, created
18 files, and matched all 26 output hashes; the parent also compared the
delivered manifest against the built source and binary.

The first native step crashed because the TCG frontend omitted its mandatory
tb_start callback. A second failure at PC=0x1000 exposed a non-probe TLB miss
returning false instead of raising the guest fault. Both mechanisms were
corrected before the 12-case pass, and the failed runs remain separate. Review
also tightened debug memory mapping, stack/VMState bounds, inactive slot
handling, deadlines and uncertain breakpoint cleanup. The first preservation
attempt caught an eager arch lookup in metadata-only QEMM launch; the guard
now checks the field when present, with its focused 11-case regression passing.

The source package includes build instructions and explicit local macOS arm64
limits. Linux, other hosts, performance, arbitrary ROM compatibility and full
source-to-UIL-to-UDC completion remain unqualified. DOSBox-X stays the default;
all 141 DOS surfaces and seven campaigns remain open. No CI, release/tag,
merge, shared installation or default-selector change.

Final integrated preservation passes **2,658 tests across 158 files**, with
zero failures, errors or skips. One existing private DinoPark identification
check was explicitly deselected because its input is unavailable. All 1,190
Python source/test hashes match before and after that run. Separate selections
pass 12 native CHIP-8 cases, 323 retained DOSBox-X history/undo cases and 77
staged package/skill/capability/runtime/dispatch/migration cases; selections
overlap. The native archive/patch, all 26 built/replayed source hashes and exact
binary identity were checked. N19-N24, component-04 and the shared selector
retain their earlier identities. Evidence is chip8-preservation-final-02,
chip8-native-03, chip8-dosbox-final, chip8-metadata-final and the source replay
receipt. The consolidated private receipt is chip8-final-receipt.json. Earlier
failed attempts remain separately retained and the old handoff prefix is exact.


## CHIP-8 display, keypad and virtual timers (2026-11-12)

This slice adds an optional device extension over the retained native CHIP-8
CPU target. The named classic profile is unchanged; native subset
fdisbull-chip8-classic-devices-2 and environment model
fdisbull-chip8-display-keypad-timers-1 distinguish the new runtime. The original
CPU-only patch/runtime and schema1 checkpoints remain separately preserved.
DOSBox-X stays the default and retained fallback. No CI is used.

The native machine stores exact 64x32 monochrome pixels and implements clear,
clipped XOR sprites, collision VF, coordinate aliases and the classic font at
0x50. Sprite RAM extent is validated before architectural or display effects.
The adapter derives exact RGBA bytes and stored PNG artifacts from that native
state without a GUI. Logical held keys use a sixteen-bit mask; key skips reject
out-of-range register values as unpressed. FX0A selects the lowest held key or
stops at its unchanged PC with an attributed key_wait event. Setting/releasing
keys never resumes the CPU. Ephemeral wait-stop ownership is cleared at CPU
entry, debugger mutation and snapshot restore, so a restored wait cannot be
misreported as a new execution event or hide an actual breakpoint.

DT/ST use a native QEMU_CLOCK_VIRTUAL timer at rational 60 Hz. Callbacks dispatch
mutations on the CPU thread and advance from prior absolute deadlines, including
overdue ticks. Fractional phase is carried from the first deadline; late callback
dispatch does not rebase the schedule. Stopped debug ticks decrement/clamp the
same timers without executing CPU instructions or changing virtual time, phase
or deadline, and their counter remains separate from virtual ticks. Sound-active
is native timer state only; audio output remains unavailable. Owned debugger
key waits pause the virtual clock; historical nonblocking wait timing and a
wall-clock instruction rate are not qualified.

Stopped JSON/Python environment, keypad and tick methods check profile/subset,
command availability, generation and full readback. Uncertain mutations close
the owner. Device schema2 checkpoints bind the exact ROM/runtime/tool identity,
and fresh-process restore compares all CPU/RAM, pixels, keys, wait state,
DT/ST, sound-active, virtual time, phase, deadline and counters before replacing
the previous owner. Restored wait ownership is cleared. No cross-binary restore
or host-file rewind is claimed.

Nine real-native device witnesses pass, including PNG pixel identity, VF alias
and atomic out-of-bounds draw, font bytes, held-key skips/waits, deterministic
ticks, nonzero virtual-time/phase cold restore, wait/breakpoint attribution and
native stale-generation/invalid-argument refusal. Ten additional retained CPU
semantics and JSON dispatch cases pass on the device binary; the CPU-only CLS
refusal is explicitly excluded because CLS is implemented here. Review caught
and corrected initial callback-relative timer drift and preservation of old VF
on a non-colliding draw before this accepted native run. Earlier build feedback
and failed host-discovery expectations remain separate diagnostic evidence.
The first integrated run passed 2,516 cases before a phase-selection test
failed: repeated 250 ms samples can remain on the same 15-tick phase. The
test now selects a nonzero observed phase using bounded finer samples. The
corrected nine-case device selection and five additional cold-restore phase
probes pass on the unchanged native binary; the failed run is retained separately.
Final raw-SQLite inspection found that the native pixels-hex field needed an
explicit external-object classification. It is now externalized recursively
in event/checkpoint/screenshot metadata before SQLite/WAL writes, with exact
readback and reopen coverage. The 32-case storage/device selection includes
actual DOSBox-X and CHIP-8 execution and passes without skips. The second
integrated run was stopped after 401 passes to refresh this source; its partial
receipt is retained. Final preservation includes the target-storage file.

The upgraded host also restored an already-created schema1 artifact using the
retained original native binary: PC=0x208, V0=3, I=0x301, SP=0 and RAM[0x300]=03.
The original FDB, WAL, SHM and ROM hashes were unchanged. This is a preserved
artifact witness, separately from creating new checkpoints under the new host.

CHIP-8 code/RAM layers, hooks, histories, selected undo, comparative trials,
audio/RNG and IRQ models remain unavailable. Existing DOS task-private layers,
hooks, checkpoints, trials, histories and IRQ implementations remain retained.
Independent historical/quirk qualification, arbitrary ROM compatibility,
Linux/other-host builds, performance and the G0-G8 conversion gates remain open.
All 141 DOS surfaces and seven compatibility campaigns remain unqualified for
default switching/removal. No release/tag, merge, shared installation or selector
change is included.


Final integrated preservation passes **2,697 tests across 163 files**, with
zero failures, errors or skips and one explicit private DinoPark identification
fixture deselection. All **1,194 Python source/test hashes** match before and
after the run. Separate overlapping selections pass nine native device cases,
ten CPU/JSON cases on the new binary, 323 DOSBox-X history/undo cases, 97
host/package/skill/capability/runtime/dispatch/migration cases and 32
storage/device cases. Five extra phase/restore probes pass. External-object
readback verifies eight native artifacts and twenty key/timer events, with
inspected database bytes unchanged.

The device binary SHA-256 is
8dfc32e0853dba5096563d97f4dd5f54b319b7e4d4c5ebfa416dbfc82d903ebd;
the incremental patch SHA-256 is
0bfaec7730ac13b172b3a743c10dbb39d0b214924098e7cc475afb48c1a37d11.
Both author and parent replayed the seven-file patch over the unchanged v1
baseline and matched the built-source hashes. Evidence is
chip8-devices-preservation-final-03, chip8-devices-storage-native-05,
chip8-devices-cpu-regression-02, chip8-devices-dosbox-final-02,
chip8-devices-metadata-host-final-02 and the external-storage/replay receipts.
The consolidated private receipt is chip8-devices-final-receipt.json. Earlier
failed/interrupted diagnostics remain separate. The historical handoff prefix,
v1 package/source/runtime, N19-N24, component-04 and shared selector retain
their earlier identities. No CI, release/tag, merge or default switch.


## Complete classic CHIP-8 source and RNG candidate (2026-11-12)

The four remaining non-legacy classic families are implemented in a new isolated
source extension over the retained v2 device target: Bnnn uses nnn+V0 without
12-bit wrapping, Fx1E adds VX to I modulo 65536 without changing VF, Fx33
preflights all three decimal-digit bytes before writing, and Cxkk advances an
explicit native LCG32 stream before masking its high byte. A baseline probe on
the retained v2 binary confirmed all four still raise unsupported-opcode faults.
The 34-family claim is source implementation and prepared witness coverage;
new native execution is not yet qualified. Legacy 0nnn, SCHIP and XO stay outside
the declared profile.

RNG model fdisbull-lcg32-high8-v1 uses state=(1664525*state+1013904223) modulo
2^32 and byte=state>>24. Seed/state start at zero, Cxkk consumes a draw even for
mask zero, and VF is unchanged unless it is the destination. The model is a
deterministic analysis stream, not the earlier Python random.Random sequence.
Stopped generation-guarded reseeding resets seed/state/count without executing
CPU code or changing other machine state. New subset
fdisbull-chip8-classic-complete-3 and environment model
fdisbull-chip8-display-keypad-timers-rng-2 identify it; native VMState3 and host
format fdisbull-qemu-chip8-state-3 include the RNG fields. Receipt counters
saturate and stopped mutators reject an exhausted state generation. V1/v2
identities and formats remain separately supported with their retained binaries.

The adapter, JSON seed route, package selectors and portable guide are prepared.
The focused host selection passes **138 tests**, zero failures/errors/skips,
with all **1,197 Python source/test hashes unchanged**. One native DOSBox storage
test is explicitly deselected for this host-only pass. The new prepared native
selection contains 29 execution cases plus one host witness-map check; it covers
the missing families, remaining ALU/skip family gaps, nonempty CLS, fixed RNG
vectors, zero masks, VF preservation, atomic BCD refusal, seed CAS and future
RNG replay after fresh-process/FDB reopen. Prepared cases are not passes.

A fresh source tree/configuration uses external TMPDIR. The required memory-run
admission refused the 4 GB estimated compile before Ninja started: compressed
memory exceeds one quarter of physical memory, swap exceeds 4 GiB, and the
shared-memory reserve would be crossed. No ticket was granted. The refusal is
preserved, and the launcher is not bypassed. Native compilation, these new
execution cases, checkpoint replay and integrated preservation remain pending
until resource admission succeeds. Earlier v2 acceptance results remain dated
prior evidence rather than being relabelled as current-v3 verification.

The original v1/v2 source packages/runtimes and existing DOS implementations
remain retained. DOSBox-X is still the default/fallback; all 141 DOS surfaces
and seven campaigns remain open. No CI, release/tag, merge or shared selector
change. This source candidate does not add CHIP-8 layers/hooks/histories/trials
or IRQ machinery, audio output, historical timing or arbitrary ROM qualification,
or complete the G0-G8 conversion gates.


The frozen six-file incremental patch SHA-256 is
cb80c64be2ea206177fb9d5f787dad9f640a15de6dc2b4a34f2e768923713124.
Both author and parent independently replayed it and verified all six source
hashes; both lightweight QAPI generation passes completed without C compilation.
The private memory refusal is chip8-classic-memory-run-refusal.json. The new
source/host progress receipt is chip8-classic-source-receipt.json; its status
remains native-build-and-acceptance-pending. The retained v2 acceptance receipt
chip8-devices-final-receipt.json is separate prior evidence.


## Classic CHIP-8 native acceptance resumed (2026-11-12)

The user explicitly directed this slice to disregard the memory guard. The
original refusal remains preserved; only the current build/test work used the
override. No global guard state/policy or unrelated process was changed. Fresh
storage admission passed for the bounded external build and test outputs.
The direct external-TMPDIR build completed and froze qemu-system-chip8 SHA-256
c1dca2817894b3d45e0ea3262f3b907167c854f28e4c35df25e283a24262a987
at 6,220,664 bytes. The six-file source patch remains unchanged at
cb80c64be2ea206177fb9d5f787dad9f640a15de6dc2b4a34f2e768923713124.

The new selection passes **31 cases: 30 actual native cases plus one host
family-map check**. These cover Bnnn high/odd destinations, 16-bit I/VF aliasing,
six BCD values and atomic boundary refusal, fixed RNG vectors/masked zero draws,
nonzero VF preservation, repeated/different seeds, cold/FDB-reopen future-stream
replay, stale/invalid native seed rejection with complete CPU/RAM/device
readback, and the public JSON seed route without hidden execution. A further
**19 retained CPU/device cases pass on the new classic binary**, excluding
only the obsolete CPU-only CLS refusal because CLS is implemented. Together
the explicit executed witnesses cover all 34 non-legacy classic families;
this is representative family coverage, not exhaustive dialect/ROM qualification.

Two already-created schema2 artifacts also restore with the upgraded host and
unchanged original v2 binary: one retains held keys/key wait, and the other
retains nonzero virtual time, tick count, phase and deadline. Fresh-process
readback matched all CPU registers, RAM hash, fault and saved environment except
its documented ephemeral wait-stop ownership. Original FDB/WAL/SHM/ROM hashes
were unchanged and verified object closures were copied privately. Evidence is
chip8-v2-upgraded-host-01/receipt.json. V1/v2 packages/sources/binaries remain
retained separately; cross-binary snapshot restore is still refused.

The integrated 166-file preservation run follows against frozen Python source.
DOSBox-X remains the default/fallback. No CI, release/tag, merge or shared
installation/default change is included.


Final integrated acceptance passes **2,731 tests across 166 files**, with zero
failures/errors/skips and one explicit unavailable private DinoPark fixture
deselection. All **1,197 Python source/test hashes** match before/after the run.
Separate overlapping selections pass 31 new cases (30 native plus one host
map), 19 retained CPU/device cases on v3, 323 DOSBox-X history/undo cases and
138 host/package cases. Direct external-object readback verified four schema3
checkpoint artifacts and eighteen seed events without changing database bytes.

Evidence is chip8-classic-preservation-final-01, chip8-classic-native-01,
chip8-classic-compat-01, chip8-classic-dosbox-final-01,
chip8-classic-host-final-02, chip8-classic-external-state-receipt.json and
chip8-v2-upgraded-host-01/receipt.json. The consolidated private receipt is
chip8-classic-native-final-receipt.json. The original source-only receipt,
refusal and explicit override/build receipts remain separately preserved.
V1/v2 packages/sources/binaries, N19-N24, component-04 and shared selector retain
their identities. All 141 DOS surfaces and seven campaigns remain open; the
bounded classic/RNG acceptance does not authorize DOSBox default promotion or
removal, a release/tag, a merge or a shared installation change. No CI.
