# Native QEMU timing synchronization

The explicit native virtual-clock profile supports two separate controls:

- **Host clock auto-sync:** maintain a persistent 1:1 mapping between QEMU
  virtual nanoseconds and host monotonic elapsed time, then automatically
  choose one correction at an explicit cooperation point.
- **Retrace wait:** continue once toward a strictly next modeled VGA retrace
  transition and verify the stopped timing evidence afterward.

These compose the existing native clock and retrace extensions. No additional
QEMU patch or launch-time automatic pacing mode is required. See the
[migration guide](DOS_QEMU_MIGRATION.md), [clock extension](../native/qemu-clock/README.md)
and [precise retrace model](../native/qemu-retrace/README.md) for admission.
The [handoff log](DOS_QEMU_HANDOFF.md) records dated qualification results.

## Select the clock and inspect capability

Launch a fresh paused PC machine or original COM/MZ process with the explicit
`qemu_clock='virtual'` profile and the prepared native extension. Its
`host_clock_sync` capability admits the host mapping. Add
`qemu_retrace='precise'` for `retrace_wait`; its capability does not guarantee
that the current mode has an eligible transition.

The default standard profile is unchanged. Existing `guest_time_control`,
`timed_input` and `completed_guest_frames` flags retain their separate meanings.
Instruction counts, PIT/BIOS ticks, PCM sample duration, renderer IDs and host
elapsed time are not substituted for native virtual nanoseconds.

## Establish one persistent host mapping

All methods operate on the owned machine context and require a project outside
a caller-owned transaction.

| Python operation | Behavior |
| --- | --- |
| `clock_sync_start(...)` | Passively bind a fresh token, run, clock epochs, configuration and host/virtual anchors |
| `clock_sync_observe(timeout_ms=...)` | Passively report accumulated drift and mapping state |
| `clock_sync_step(timeout_ms=...)` | Automatically select at most one guest catch-up or stopped host wait |
| `clock_sync_stop(timeout_ms=...)` | Stop future corrections between calls; repeated stop is passive |

Start accepts these strict integer options; booleans are rejected:

| Option | Default | Admitted range |
| --- | ---: | ---: |
| `tolerance_ns` | 1,000,000 | 0 through 60,000,000,000 |
| `max_lag_ns` | 250,000,000 | 1 through 60,000,000,000 |
| `max_wait_ns` | 250,000,000 | 1 through 60,000,000,000 |
| `timeout_ms` | 1,000 | 1 through 600,000 |

All other methods also accept `timeout_ms` in that range. This version uses a
fixed 1:1 rate. It does not alter the selected icount configuration, CPU speed,
audio sample rate or renderer period.

Let the admitted virtual and host anchors be `V0` and `H0`. At a later stopped
native sample `V`, the host timestamp `H` is taken after that native observation:

```text
expected_virtual_ns = V0 + (H - H0)
drift_ns = V - expected_virtual_ns
```

Positive drift means virtual time is ahead; negative drift means it is behind.
The original anchors persist across calls. This counts **all host elapsed time
since start**, including Python/helper work, control and persistence overhead,
debugger pauses and caller idle time. Actual intervening guest progress is
subtracted through `V`; it is not charged twice. Native timer overshoot remains
visible in the next correction instead of becoming a new baseline.

Start the mapping when that elapsed-time policy is appropriate. Stop it before
an intentional long inspection pause. After an excessive gap, explicitly stop
and start again to choose a fresh origin; no operation silently discards debt
or rewrites the old anchors.

## One correction per explicit step

The step freezes its target after one stopped sample. Its decision is:

| Observed drift | Action |
| --- | --- |
| Within tolerance | Observe without executing or waiting |
| Behind, within `max_lag_ns` | Arm one native budget for the deficit and continue once |
| Behind beyond `max_lag_ns` | Latch `desynchronized` / `lag-limit` without executing |
| Ahead, within `max_wait_ns` | Keep the guest stopped and wait on the host for the anchor-derived deadline |
| Ahead beyond `max_wait_ns` | Latch `desynchronized` / `wait-limit` without waiting |

After that one correction, the result reports the actual final clocks and
residual drift against the original mapping. Execution, QMP reads and evidence
storage take host time, so reaching the frozen target does not promise zero
drift at return. `within_tolerance` describes the final observed samples.
`requested_wait_ns` retains the initial positive drift. The one sleep request
is reduced by elapsed planning time and the remaining host deadline; actual
elapsed wait is reported separately. A short or late host sleep does not
trigger another correction loop.

This is cooperative auto-sync: the caller chooses a safe boundary and the
controller chooses the correction. There is no background thread or implicit
execution added to ordinary `run()`, traces, captures or input operations.
For example, after an explicitly selected virtual-profile launch:

```python
mapping = debug.clock_sync_start(
    tolerance_ns=1_000_000,
    max_lag_ns=100_000_000,
    max_wait_ns=100_000_000,
)

# Perform the intended bounded Python work or explicit native operation.
correction = debug.clock_sync_step(timeout_ms=1000)
if correction['state'] != 'active':
    # Inspect correction['execution'], outcome and reason before more work.
    debug.clock_sync_stop()
else:
    drift = debug.clock_sync_observe()
    debug.clock_sync_stop()
```

An active, desynchronized, interrupted or invalidated mapping must be stopped
before a new mapping can start. A live owner can observe latched and stopped
states. Saved events retain history, but opening a project does not reconnect
the VM, revive a mapping or resume execution.

## Preserve stops, deadlines and input ownership

A sync step retains the complete native execution receipt. An early or
coincident breakpoint, watchpoint, DOS return/TSR, exception, timeout or
unexplained stop latches `interrupted`. A fired timer cannot override another
observed cause. There is no automatic continuation, rebase or replay.

Scheduled input keeps its existing first-stop behavior. If the sync budget
stops before the input deadline, the unfired batch is cancelled by that stop.
The caller must explicitly reschedule or cancel/discard it before further
execution. Sync adds no automatic re-arm or key release. A step can still
dispatch an explicitly queued or scheduled key-up through the existing input
path, preserving that caller-owned transition's evidence.

One absolute host deadline begins before lock admission and includes stopped
observations, host waiting or native execution, cleanup and persistence. It
intersects existing script, session, VM and channel bounds; each previous
bound is restored separately. A final wrapper deadline failure also latches
the matching sync mapping, even if the method's own last check just succeeded.

Stop prevents future correction calls between operations. It is not an
asynchronous cancellation command for a call holding the machine lock.
In-flight execution is bounded by the existing native timeout and terminal
cleanup policy. Epoch/profile loss or contradictory native evidence invalidates
ownership. A failed or late evidence write can follow completed execution;
`error.result` retains available observations and the original stop. Do not
infer rollback from an exception.

## Wait for a modeled retrace transition

`retrace_wait(edge='enter'|'exit', timeout_ms=1000)` requires the explicit
precise VGA model and virtual clock. The default edge is `enter`. It derives
the strictly next occurrence, even if called exactly at an edge.

For character time `T`, characters per line `H`, total characters `N` and the
model's inclusive vertical interval `vstart..vend`:

```text
period P = T * N
entry phase E = T * H * vstart
exclusive exit X = T * H * (vend + 1)
edge phase e = E for enter, X % P for exit
delta = (e - current_virtual_ns) % P, using P when the result is zero
```

Uninitialized, VBE or invalid timing returns `unsupported` without execution.
A supported phase that is vertically in retrace for the whole period has no
transition and returns `unsupported_reason='no-transition'`. Entry at phase
zero or exit at the period boundary is otherwise valid for a strict subinterval.

The operation makes one `clock_advance(delta)` and one after observation.
`synchronized=True` requires the same run, both epochs, device, model and
timing generation; the exact owned timer/stop receipt; no conflicting observed
stop classification; and the actual stop inside the planned absolute window.
Entry uses `[target_entry, target_exit)`, while exit uses
`[target_exit, next_entry)`. A matching phase in a later period does not qualify.

The result preserves `before`, `after`, `target_ns`, `window_end_ns` and the
complete `execution`. Outcomes distinguish `synchronized`, `unsupported`,
`timing-changed`, `missed-edge` and `interrupted`. A timing-generation change
takes precedence in the synchronization outcome while the original execution
stop remains intact. No outcome causes a retry or dynamic retargeting.

VGA timing changes do not rebase the host clock mapping. The two operations
answer different questions. A retrace wait does not establish full VBlank,
guest drawing completion, input readiness, renderer publication or physical
VGA accuracy. The native model's documented approximations remain in force.

## JSON, scripts and retained evidence

### Schedule input at the next modeled retrace edge

The optional fifth [native retrace-input patch](../native/qemu-input-retrace/README.md)
adds `input_schedule_retrace(edge='enter'|'exit', timeout_ms=1000)`. It requires
the virtual clock, precise VGA profile and `retrace_input_schedule` capability.
Queue physical input while stopped, then arm the existing batch. Arming is
passive and selects the strictly next edge, including when already at that
phase. Unsupported timing or no transition refuses before accepting an arm
and preserves the pending edges.

The caller chooses the following bounded execution. Its clock deadline must
extend beyond the input target: a stop at the exact target cancels delivery.
In particular, a `retrace_wait` to that edge preserves stop precedence. Use
the returned `target_ns` and existing `start_ns` to choose a suitable explicit
budget; no arm performs an implicit continue.

```python
# The machine is stopped in a known eligible mode, with all five patches.
lease = debug.keyboard.key_down('a')['lease']
armed = debug.input_schedule_retrace(edge='enter', timeout_ms=1000)
delay = armed['retrace']['target_ns'] - armed['start_ns']
# Explicitly allow one millisecond beyond the target for this attempt.
execution = debug.clock_advance(delay + 1_000_000, timeout_ms=3000)
delivery = execution['input_delivery']
print(delivery['state'], delivery['retrace']['dispatch_phase_verified'])
```

The native callback checks the pinned device and timing generation immediately
before dispatch. A hidden A-to-B-to-A change cancels as
`retrace-timing-changed`; an unchanged model reached too late cancels as
`retrace-missed-window`. Neither retargets or requests a new stop. The final
execution receipt preserves the caller's original stop. Pending edges then
require explicit rescheduling or `input_cancel_pending()`; a dispatched hold
still requires a separate release.

The base `fdisbull-qemu-scheduled-input-1` receipt adds a
`fdisbull-retrace-input-1` member containing the absolute target/window, full
stopped `before` observation and immutable native arm/check snapshots.
`dispatch_phase_verified=True` requires the actual PS/2 callbacks and final
sync to join the callback snapshot inside that original window. It does not
establish device acceptance, arbitrary guest consumption, full VBlank or a
completed frame. A later retrace query cannot relabel the historical check.

Use JSON `debug-input-schedule-retrace` or saved-script
`input-schedule-retrace` with the same options. Whole-script capability,
signature, literal-option and transaction checks precede earlier writes.
The operation shares the remaining script deadline through lock admission,
observations, arm and persistence. Failed scripts close live ownership after
an arm, including a batch queued before the script. Existing
`input.schedule-arm/result/observe` journal names retain these receipts.

### Queue one timed keyboard press

With all six optional native patches and `virtual_keyboard_press`, the existing
`keyboard_press(key, modifiers=(), hold_ms=40, gap_ms=40)` queues one chord.
Use `qemu_clock='virtual'`; a precise retrace profile is unnecessary for a press.
The machine must be stopped, with an empty owned input queue and no held leases.

```python
armed = debug.keyboard.press('a', modifiers=['shift'], hold_ms=17, gap_ms=40)
# Arming is passive. This explicit budget allows the four edges and later IRQs.
execution = debug.clock_advance(30_000_000, timeout_ms=1000)
state = debug.keyboard.state()
receipt = state['schedule']
```

Modifier makes follow caller order, then the main make, main break and reverse
modifier breaks. Each make and modifier break waits 2 ms; main break waits
`hold_ms` from the actual main make. Every next deadline derives from the
preceding **actual callback**, so lateness cannot shorten the hold. Both timing
options are strict integers 1..1000. `gap_ms` is retained but has no effect on
one press, matching the retained DOSBox single-press contract; it applies to
successive characters in the separate text operation below.

The existing JSON method is `debug-keyboard-press` with `run`, `key` and the
same optional arguments. Saved scripts use `keyboard.press`; whole-script
validation checks literals, capability and caller transactions before earlier
mutations. Resolved options are checked before native arming. The direct Python
arm has a 1000 ms host bound including lock admission and respects any tighter
script or transport bound. A failed script after arming closes the VM.

The scheduled-input receipt adds `press`, whose native `steps` retain each
key/direction, relative delay, assigned deadline and actual callback time.
`native['press']['dispatched-count']` identifies the delivered prefix.
Each public press step reports its own `lateness_ns` against its assigned
deadline. The batch-level `lateness_ns` is `None` for a press because its
first deadline and final release describe different edges.
A top-level `state='cancelled'` with `dispatch_ns=None` can still have delivered
makes: always inspect the prefix and the current owned leases. A successful
`state='dispatched'` means all chord callbacks and syncs completed, including
releases; device acceptance and guest consumption remain unknown.

A pending stop or a reached/equal clock-budget deadline wins before **each**
edge. An early stop cancels the suffix and latches explicit resolution. It does
not automatically release held keys, restart the chord or execute its suffix.
Call `input_cancel_pending()` to discard the unsent steps, then explicitly
release each retained keyboard lease with `keyboard.key_up(lease)` and a
separately chosen execution. Ordinary/retrace rescheduling of a bound press is
refused. After full completion, a new press can be admitted normally.

The separate host clock controller can supply that explicitly requested bounded
execution through `clock_sync_step()`. Its fixed mapping, drift latch and
first-stop policy still apply; input never advances the clock or rebases the
mapping by itself. Coordinate clicks remain unavailable, and `timed_input`,
`guest_time_control` and `completed_guest_frames` stay false.
See the [native press contract](../native/qemu-keyboard-press/README.md).

### Queue bounded US-layout text

With the seventh native patch and `virtual_keyboard_type`, use
`keyboard_type(text, hold_ms=40, gap_ms=40)` or `keyboard.type` to passively arm
one finite text plan. The explicit virtual-clock profile, stopped machine,
empty owned queue and absence of held leases are required. The complete input
validates before arming: 1..64 printable US-layout ASCII characters plus CR,
LF and Tab. CR and LF each produce an Enter chord; they are not combined.
Uppercase letters and shifted punctuation get a separate Shift chord each.
The operation does not inspect or change the guest keyboard layout or Caps Lock.

```python
armed = debug.keyboard.type('aA!', hold_ms=7, gap_ms=11)
# The nominal plan is 57 ms. This caller-chosen budget also allows IRQ handling.
execution = debug.clock_advance(70_000_000, timeout_ms=1000)
typing = execution['input_delivery']['typing']
print(typing['dispatched_count'], typing['undispatched_count'])
```

The first character starts after 2 ms. Every later character's first edge waits
`gap_ms + 2 ms` from the preceding character's final release callback. Other
makes and Shift releases wait 2 ms; main-key releases wait `hold_ms`. Every next
deadline uses the actual preceding callback, and there is no trailing gap timer.
Both timing options are strict integers from 1 through 1000.

The receipt's `typing` member has format `fdisbull-keyboard-type-1`. Inspect its
immutable text plan, delivered prefix and per-edge `character_index`, `lease`,
deadline, dispatch and lateness. Repeated keys receive distinct lease lifetimes.
At most 256 edges and 128 future lifetimes are reserved; reservations remain
separate from active held keys and do not raise the 64-active-lease limit.
Only validated delivered makes enter the held-key ledger, and matching breaks
remove them. The entire newly observed prefix validates before ledger mutation.

An early stop can leave a held Shift or main key even though top-level
`dispatch_ns` is `None`. Another run, press, type or batch/retrace reschedule is
refused until `input_cancel_pending()` discards the suffix and future
reservations. Then explicitly release retained leases and choose their
execution, as for a single press. Neither cancellation nor auto-sync replays
or releases input automatically. A successful full dispatch empties its leases.

Use JSON `debug-keyboard-type` or script `keyboard.type` with the same options.
Whole-script checks precede earlier mutations, resolved values are revalidated,
and one 1000 ms direct-arm host allowance includes lock admission and evidence
persistence while respecting tighter incoming bounds. Accepted/uncertain late
arms and malformed or unpersisted evidence close the VM without replay.

The existing clock-sync controller can drive a short plan at one explicit
cooperation point. For long text, choose an appropriate bounded execution:
64 shifted characters with 1000 ms holds and gaps have a nominal duration of
127,384 ms, longer than one `clock_advance` allowance. A shorter budget cancels
the suffix; the helper never divides the string into hidden runs. Callback
evidence remains separate from guest text consumption and completed frames.
See the [native text contract](../native/qemu-keyboard-type/README.md).

### Queue one timed physical mouse click

With the eighth native patch and `virtual_mouse_click`, use the QEMU-only
`mouse_button_click(button='left', *, hold_ms=80)`. The explicit virtual-clock
profile, native clock/input commands, `input-send-event` and
`x-fdisbull-arm-mouse-click` are required; precise retrace is unnecessary.
A seven-patch executable refuses this helper while keeping its separately
advertised physical input and keyboard operations.

Accept only exact strings `left`, `middle` and `right`, and a strict integer
`hold_ms` from 1 through 1000. Booleans, coerced values, wheel/side/extra buttons
and additional positional arguments are rejected. Admission requires a stopped
owner, empty input queue, no owned held leases, no bound schedule and a project
outside a caller-owned transaction.

```python
armed = debug.mouse_button_click('left', hold_ms=17)
# Arming is passive. This caller-chosen budget permits both edges and later IRQs.
execution = debug.clock_advance(30_000_000, timeout_ms=1000)
click = execution['input_delivery']['click']
print(click['dispatched_count'], click['undispatched_count'])
```

One arm prepares two separate button batches. Down is due 2 ms after arm; up
is due `hold_ms` after the actual down callback and sync completion. The release
deadline does not exist until that callback completes, so a late down cannot
shorten the requested hold. Each edge has its own sync: a down/up pair under
one mouse sync could collapse the press. There is no requested movement,
trailing timer, implicit run/sleep/resume, rebase or replay.

The base receipt remains `fdisbull-qemu-scheduled-input-1`. Its `click` member
uses `fdisbull-mouse-click-1` and retains the button, hold, dispatched and
undispatched counts, and exactly two steps. Each step retains its sequence,
shared paired lease, button, direction, relative delay, assigned deadline,
actual dispatch and individual lateness. Only the delivered prefix and next
edge have deadlines. Public `edge_count` stays two (native `event-count` remains
two), `deadline_ns` stays the first deadline and `lateness_ns` is `None`.
Top-level `dispatch_ns` exists
only after full completion and equals the final callback/terminal time.

The `click`, `press`, `typing` and `retrace` descriptors are mutually exclusive.
Every accepted mode clears incompatible descriptors; refused arms preserve
the previous receipt and proposed token. Terminal evidence freezes. Existing
journal routes retain arm, prefix and result evidence across project reopening;
reopening does not reconnect an input owner or replay a callback.

Pending stops and reached/equal clock-budget deadlines win before each edge.
The first actual VM stop cancels the remaining suffix; completing both edges
does not itself stop the VM. A cancelled click can have one delivered down
despite top-level `dispatch_ns=None`. Inspect its prefix and owned leases.
While the cancelled click remains bound, another run or new/converted schedule
is refused. To resolve it explicitly:

```python
cancelled = debug.input_cancel_pending()
for lease in cancelled['retained_dispatched_holds']:
    debug.mouse_button_up(lease)
# These explicit releases are queued. Choose their bounded execution separately.
```

Cancellation discards the unsent suffix, retains a delivered hold and clears
its pending release. It never releases, replays or neutralizes input by itself.

The same click can instead be driven by one explicit host-sync cooperation
point, with an independently admitted `host_clock_sync` mapping:

```python
mapping = debug.clock_sync_start(
    tolerance_ns=1_000_000,
    max_lag_ns=250_000_000,
    max_wait_ns=250_000_000,
)
armed = debug.mouse_button_click('middle', hold_ms=17)
# Do the intended bounded host work before this caller-selected cooperation point.
correction = debug.clock_sync_step(timeout_ms=1000)
delivery = debug.input_schedule_observe()
debug.clock_sync_stop()
```

Inspect both `correction` and `delivery`. A step can observe or wait without
running the guest, leaving the click armed. If it advances only as far as an
edge deadline or stops earlier, it cancels the remaining suffix; it does not
extend its budget to finish the click. A sufficiently long ordinary advance
can dispatch both edges. No second correction, automatic rebase or cleanup
release follows. Resolve a cancelled click explicitly before further execution.

JSON uses `debug-mouse-button-click` with `run`, optional `button` and
`hold_ms`; saved scripts use `mouse.button-click`. Whole-script capability,
signature, literal and transaction checks precede earlier mutations; resolved
arguments validate before arm. One 1000 ms direct-arm host bound covers lock
admission, I/O and evidence persistence and intersects tighter incoming bounds.
A pre-arm admission failure leaves a valid stopped owner. Accepted/uncertain
late arms, malformed native evidence and persistence failure close the owner
with available evidence and no replay; input-touch script failures also close.

No cursor location is selected or established. Pre-existing mouse accumulators
can be flushed by synchronization, and external button state can affect packet
bits. Disabled/remote device state and FIFO capacity are not normalized.
Callback/sync completion does not establish packet acceptance, arbitrary guest
consumption, INT33 behavior or an application click. Zero-delta packets require
independent evidence from a controlled initialized fixture.

There is no `GuestMouse` facade or legacy `DebugSession` stub. `click(x, y)`,
`debug-click`, `click`/`click-frame` and `input.mouse.click` keep their
coordinate/frame contracts and native refusal. General `timed_input`,
`absolute_mouse`, `guest_time_control` and `completed_guest_frames` remain false;
DOSBox stays the default and all 127 promotion qualifications remain open.
See the [native click contract](../native/qemu-mouse-click/README.md).

### Clock synchronization and retrace waits

The JSON routes are `debug-retrace-wait` and
`debug-clock-sync-start`, `debug-clock-sync-observe`, `debug-clock-sync-step`,
`debug-clock-sync-stop`. They take the existing owned `project` and `run`
arguments, with optional explicit machine context and the Python options.

Saved-script operations omit the `debug-` prefix. For example:

```json
{
  "format": "fdisbull-script-1",
  "backend": "qemu-dos",
  "steps": [
    {"op": "clock-sync-start", "max_lag_ns": 100000000, "as": "mapping"},
    {"op": "clock-sync-step", "timeout_ms": 1000, "as": "correction"},
    {"op": "assert", "value": "$correction.state", "equals": "active"},
    {"op": "clock-sync-stop"}
  ]
}
```

Whole-script capability, signature, literal-parameter and transaction checks
precede earlier writes. A mapping can be started and stepped in one script;
preflight does not require it to exist before the start executes. Each timing
operation receives the script's remaining allowance. Assertion failure does
not silently execute a later stop or another correction.

Clock receipts use `fdisbull-clock-sync-1` and persist
`machine-clock-sync-start/observe/step/stop` events. Retrace waits use
`fdisbull-retrace-wait-1` and `machine-retrace-wait`, retaining the underlying
clock and passive-retrace evidence. All timestamps identify their clock domain.
Synchronization receipts do not replace source-event clocks or claim input
causation, audio playback alignment or completed guest frames.

## Sample a retained renderer publication

`display_probe(points, *, window=None, update_id=None, timeout_ms=1000)` reads up
to 256 ordered RGB pixels under `renderer_probe`. It requires the ninth native
extension and the explicit virtual clock. Use JSON `debug-display-probe` or script
`display-probe`. The optional window/update pair checks one exact publication;
an update ID alone is refused because IDs restart in each window.

```python
publication = debug.display_observe()
if publication['updates']:
    sampled = debug.display_probe([[0, 0]], window=publication['window'],
                                  update_id=publication['update_id'])
```

This is passive even while an observation window is active: it reads the latest
retained RGB copy without refreshing pixels, advancing clocks or calling
`clock_sync_step()`. A caller may explicitly use one clock-sync step to permit
later publications, then observe and probe whichever update actually exists.
An earlier stop can leave the previous publication unchanged. The helper does
not wait for a fresh image or rebase a stale expectation.

The result retains publication age, exact window/update identity, ordered pixels
and unchanged stopped clock brackets. Coordinates belong to that retained image;
they do not establish guest mouse position, mode identity, completed guest frames
or input readiness. See the [full probe contract](DOS_QEMU_MIGRATION.md#probe-sparse-pixels-from-one-retained-publication)
for validation, shared deadlines, failure disposition and retained evidence.

## Technical references

- [QEMU instruction-counting design](https://www.qemu.org/docs/master/devel/tcg-icount.html)
  explains the distinction between instruction counting and hardware-cycle
  accuracy. The tested implementation remains the pinned QEMU 10.0.13 patch chain.
- [Python monotonic clocks and sleep](https://docs.python.org/3.13/library/time.html)
  document the host primitives. Actual timestamps and waits are retained because
  a requested sleep duration is not a precise scheduling guarantee.
