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

## Technical references

- [QEMU instruction-counting design](https://www.qemu.org/docs/master/devel/tcg-icount.html)
  explains the distinction between instruction counting and hardware-cycle
  accuracy. The tested implementation remains the pinned QEMU 10.0.13 patch chain.
- [Python monotonic clocks and sleep](https://docs.python.org/3.13/library/time.html)
  document the host primitives. Actual timestamps and waits are retained because
  a requested sleep duration is not a precise scheduling guarantee.
