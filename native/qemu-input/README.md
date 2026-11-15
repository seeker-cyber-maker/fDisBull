# Native QEMU scheduled physical input, API 1

This optional patch adds one-shot physical input dispatch to the separately
built **QEMU 10.0.13** runtime. Apply the exact
[clock patch](../qemu-clock/README.md), then the exact
[media patch](../qemu-media/README.md), then this input patch. The source
manifests pin each dependency and every changed source file. These are
experimental private QMP interfaces; the Python package does not install QEMU.

The observed boundary is completion of the selected **PS/2 handler callbacks
and one final input sync** at a native `QEMU_CLOCK_VIRTUAL` timestamp. A
`dispatched` receipt leaves device queue acceptance and guest consumption
unknown. Full or disabled device queues can ignore events; a mouse in remote
mode can retain motion without emitting a packet. This boundary does not
establish a completed guest frame, game action, timed-key parity or host-time
synchronization. The separate [host clock-sync controller](../../docs/DOS_QEMU_TIMING.md)
preserves this scheduler's first-stop cancellation and never replays its batch.

## Reproduce the patch

Start with the official archive and private build prerequisites in the clock
README. Verify and apply `native/qemu-clock/source-manifest.json` and then
`native/qemu-media/source-manifest.json`. From the fDisBull checkout, apply the
input patch to that same tree:

```sh
python3 - "$FDB_QEMU_SOURCE" native/qemu-input/source-manifest.json <<'PY'
from pathlib import Path
import hashlib, json, subprocess, sys
source, manifest = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
record = json.loads(manifest.read_text())
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
assert (source / 'VERSION').read_text().strip() == record['qemu_version']
for kind in ('clock', 'media'):
    dependency = manifest.parent.parent / ('qemu-' + kind) / record['requires_' + kind + '_patch']
    assert digest(dependency) == record['requires_' + kind + '_patch_sha256']
patch = manifest.parent / record['patch']
assert digest(patch) == record['patch_sha256']
for item in record['files']:
    path = source / item['path']
    assert (not path.exists() if item['base_sha256'] is None
            else digest(path) == item['base_sha256']), path
subprocess.run(['patch', '--batch', '--forward', '--fuzz=0', '-p1', '-i', str(patch)],
               cwd=source, check=True)
for item in record['files']:
    assert digest(source / item['path']) == item['patched_sha256'], item['path']
print('All native input source hashes verified')
PY
```

Use the clock README's private `x86_64-softmmu` build recipe with TCG and
Pixman. The patch adds no host input driver and requires no global installation.
Source distributions and tool-source ZIPs contain this authored patch,
manifest and guide. Runtime binaries, firmware, DOS disks and byte-containing
databases stay outside tool packages.

## QMP contract

Commands require the valid stopped native clock profile: one TCG vCPU,
fixed icount, no replay or migration, and no pending stop. A stopped armed
clock budget is allowed, so native callers may arm input and budget in either
order. Arming input never resumes the VM, dispatches events, or requests a stop.

| Native command | Parameters | Result |
| --- | --- | --- |
| `x-fdisbull-arm-input` | Unused `token`, `delta-ns`, and nonempty `events` | Copies and validates one batch, then arms one virtual timer |
| `x-fdisbull-query-input` | None | Observes the latest batch without executing or dispatching input |
| `x-fdisbull-cancel-input` | Current `token` | Disarms an unfired batch; an already terminal receipt is retained |

Tokens contain 1 through 128 bytes and cannot be reused during the process
lifetime. The bounded token history permits 4096 successful arms; after that,
a new VM is required. The delay is an integer from 1 through 60,000,000,000
nanoseconds, and `start + delay` must fit in signed 64-bit nanoseconds.

A batch contains 1 through 256 events. Supported events are mapped qcode
keyboard edges, relative X/Y values in `-32767..32767`, and left, middle or
right mouse button edges. A batch admits at most one edge of each mouse
button because its final sync represents one button state. Absolute motion,
wheel, multitouch and numeric key encodings are unsupported.

| Receipt field | Meaning |
| --- | --- |
| `api-version` | Exactly `1` |
| `epoch` | Native clock epoch owned by this scheduler |
| `state` | `idle`, `armed`, `dispatched`, `cancelled` or `failed` |
| `virtual-ns` | Native virtual time at stopped observation |
| `event-count` | Owned batch size; zero before the first successful arm |
| `token`, `start-ns`, `deadline-ns` | Accepted identity and requested timing; absent before the first successful arm |
| `terminal-ns`, `reason` | Terminal transition time and reason of at most 256 UTF-8 bytes; absent while idle or armed |
| `dispatch-ns` | Actual callback/sync completion time; present only for `dispatched` |

The requested deadline and actual dispatch time are distinct observations.
Dispatch can occur later than the deadline; the receipt records the difference.
Terminal fields remain unchanged until another token is accepted, while a later
query can observe a newer `virtual-ns`.

## Dispatch and stop precedence

All scheduler state and event dispatch are serialized by the big QEMU lock.
The ordinary virtual timer participates in fixed-icount idle warping, allowing
input to wake a halted guest without host sleeps or repeated GDB continues.
An already stopping CPU prevents further input dispatch; a merely halted CPU
is eligible.

Before arming and again before the first callback, the implementation verifies
the exact selected PS/2 device types, their realized state, retained device
identities, handler IDs and callback functions. It also checks the current
keyboard scancode mapping, an empty legacy keyboard queue, no earlier
unsynchronized handler events, and every prefix of mouse accumulator
arithmetic. Every check completes before any event is emitted. The batch then
uses the direct event path and one final sync, avoiding the legacy delayed-key
helper. Existing stock input command behavior is unchanged.

A pending debugger/native stop takes precedence. A reached active clock-budget
deadline also takes precedence, including an equal input/budget deadline and
either timer insertion order. A successful input callback does not stop the
VM; execution continues until the caller's budget, breakpoint or other stop.
The first actual VM stop cancels an unfired batch, so a later continue cannot
replay it. Cancellation emits no synthetic release and cannot undo dispatched
input or clear a device queue.

## Python ownership and explicit execution

Launch with `qemu_clock='virtual'` and inspect `virtual_input_schedule` in the
live capability result. Queue physical input, arm its current pending batch,
then explicitly run the guest:

```python
lease = debug.keyboard_key_down('a')['lease']
armed = debug.input_schedule(5_000_000)
result = debug.clock_advance(20_000_000, timeout_ms=5000)
receipt = result['input_delivery']
```

Inspect `receipt['state']` and the original stop before choosing the next
action. A validated dispatch commits those exact pending edges once and
records held input as `native_dispatched`. A release is a separate queued edge
using the returned lease, followed by an explicit schedule and execution.
The receipt does not establish that the guest recognized either edge.

An early stop leaves a `cancelled` attempt and its pending batch bound. Another
run is refused until the caller explicitly reschedules that batch or calls
`input_cancel_pending()`. Passive `input_schedule_observe()` cannot resume the
guest or replay events. Queue mutation, stepping and tracing are refused while
the scheduled batch remains pending. Cancelling a pending release preserves
the previously dispatched hold.

Native reset, unsupported VM state or clock epoch/profile loss invalidates
the scheduler. Subsequent commands fail. A pre-dispatch validation failure
instead retains a `failed` receipt for inspection, but refuses another arm;
the controller must close the VM. The first successful arm installs a
process-lifetime migration blocker. This slice provides no saved-state
serialization, cold restore or automatic synchronization loop.

The controller validates the owned token, epoch, event count, times and
terminal fields before committing lease transitions. Reconciliation during
`clock_advance` also checks that any dispatch preceded that execution's owned
clock-budget deadline. Uncertain arm/cancel outcomes, malformed evidence,
failed persistence and failed scripts that touched scheduled input close the
VM without replaying events or synthesizing releases. Commands, execution and
receipt reconciliation share the admitted host/script deadline.

## Qualification scope

`tests/test_qemu_input_schedule_native.py` uses authored DOS fixtures and
separately supplied runtime inputs. Its witnesses inspect actual keyboard
make/break bytes and PS/2 mouse packets, an IRQ1 wake-up from `HLT`, earlier
breakpoints, equal and earlier clock-budget deadlines, explicit rescheduling,
token/reset ownership, DOS exit/TSR and saved script evidence. A renderer join
checks a retained pixel publication in the same epoch; it does not establish
a completed guest frame. The dedicated halted keyboard fixture is authored in
`tests/support/qemu_input_schedule_fixture.py`.

Public protocol, ownership and deadline adversaries live separately in
`tests/test_qemu_input_schedule.py`. Their receipts are not substitutes for
guest observations. The build identity and actual run counts are recorded in
the maintained migration handoff; this guide does not qualify QEMM, a real
game, INT 33h coordinate mapping, legacy timed input, trace/input causality,
Windows or macOS.
