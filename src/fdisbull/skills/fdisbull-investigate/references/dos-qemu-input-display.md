# QEMU scheduled input and display observations

Start with the [DOS QEMU migration guide](dos-qemu-migration.md) for backend
admission, launch, source binding and basic event observations. This reference
continues with bounded scheduling and display contracts.

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
All 134 default-switch qualifications remain open and DOSBox stays the default.
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
or host auto-sync. All 134 default-switch gates remain open.

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
consumption or guest drawing completion. All 134 promotion qualifications remain
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
all 134 promotion qualifications remain open.

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
DOSBox stays the default; all 134 promotion qualifications remain open.
