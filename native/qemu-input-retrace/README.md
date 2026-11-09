# Native input at a modeled VGA retrace edge

This optional fifth patch extends the existing input API 1 timer with a
generation-checked VGA retrace target. Apply the exact clock, media, input and
retrace patches before this patch. The [source manifest](source-manifest.json)
pins that chain, every changed source member and this patch. The first four
patches retain their original bytes.

Select `qemu_clock='virtual', qemu_retrace='precise'` and inspect
`capabilities['retrace_input_schedule']`. The capability requires all clock,
input and retrace commands plus `x-fdisbull-arm-input-retrace`. An older
four-patch binary continues to support ordinary virtual-delay input scheduling;
it does not advertise retrace input scheduling.

## One passive arm, one explicitly owned attempt

Queue physical keyboard or relative PS/2 mouse edges while stopped, then call
`input_schedule_retrace(edge='enter', timeout_ms=1000)`. `edge` is exactly
`enter` or `exit`. The timeout is a strict integer from 1 through 600000 ms.
Arming chooses the strictly next occurrence and copies the existing pending
batch without executing the guest or dispatching input.

The caller then chooses a bounded `run()` or `clock_advance()`. Its budget
must extend beyond the input target for delivery to be possible. A pending
stop or a reached clock-budget deadline wins, including when the input and
clock deadlines are equal, in either timer insertion order. A `retrace_wait`
to the same edge therefore cancels this input attempt. No operation implicitly
resumes, retries or moves the target to another period.

The timer retains the input extension's batch and lease rules: at most 256
events, one edge per ordinary mouse button, relative values -32767..32767,
at most 64 host leases, 4096 successful native tokens per process and a target
delay from 1 through 60,000,000,000 ns. A dispatched hold still needs an
explicit release. Cancelling an undelivered release preserves its prior hold.

See [the timing guide](../../docs/DOS_QEMU_TIMING.md#schedule-input-at-the-next-modeled-retrace-edge)
for the public workflow, JSON and saved-script routes.

## Native wire contract

`x-fdisbull-arm-input-retrace` accepts these arguments:

| Argument | Meaning |
| --- | --- |
| `token`, `events` | Existing unique input token and owned physical event batch |
| `edge` | `enter` or `exit` |
| `expected-epoch` | Admitted native virtual-clock epoch |
| `expected-device`, `expected-model` | Exact pinned VGA device and model identities |
| `expected-generation` | Timing generation observed while stopped |
| `expected-virtual-ns` | Exact stopped time of that observation |

Every expected value must match a fresh coherent snapshot of the already
admitted owner. The command computes its own target and window. It does not
accept a caller-supplied deadline as proof of retrace phase. Unsupported
timing, a full-period retrace with no transition, an invalid batch or a target
outside the admitted range refuses before accepting a token.

The return remains `FdisbullInputInfo`, `api-version=1`. Only a retrace arm
adds its optional `retrace` member:

```text
edge: enter | exit
target-ns: signed native virtual nanoseconds
window-end-ns: exclusive signed native virtual nanoseconds
armed: coherent FdisbullRetraceInfo captured at acceptance
checked: optional FdisbullRetraceInfo captured in the timer callback
```

Both snapshots are historical and freeze with the terminal receipt. A later
accepted ordinary `x-fdisbull-arm-input` token clears the entire descriptor.
Existing query and cancellation commands serve both kinds of input schedule.

## Exact target arithmetic

Use the selected model's character time `T`, characters per line `H`, total
characters `N` and inclusive vertical interval `vstart..vend`:

```text
P = T * N
E = T * H * vstart
X = T * H * (vend + 1)
phase = E for enter, X % P for exit
delta = (phase - now) % P; use P when delta is zero
width = X - E for enter, P - (X - E) for exit
target = now + delta
window_end = target + width
```

The accepted window is `[target, window_end)`. Entry at zero and exit at the
period boundary are valid for a strict subinterval. Full-period retrace has
no edge. The implementation checks signed overflow and native delay bounds
before accepting the batch. Arithmetic uses the pinned QEMU integer model,
whose formulas and limits are documented in the
[retrace patch](../qemu-retrace/README.md).

## Timer callback and cancellation

The existing input timer still owns the attempt. It first validates the
clock/profile/epoch and honors pending stops and reached clock budgets.
Only then does it obtain a fresh snapshot of the pinned VGA under the BQL.
That internal helper may run during the callback or a stopped native arm
with an armed budget. The public `x-fdisbull-query-retrace` retains its
stopped, no-active-budget guard.

The helper admits no new owner, reads no guest I/O port, starts no renderer
and never repairs or refreshes timing. It revalidates the admitted identity
and the coherent raw/cache model. Builds without standard VGA use an explicit
error stub.

| Callback evidence | Result before any input callback |
| --- | --- |
| Pending debugger/native stop or reached/equal clock budget | Existing cancellation reason; no retrace check snapshot |
| Higher timing generation, including unseen A-to-B-to-A or newly enabled VBE | `cancelled`, `retrace-timing-changed` |
| Same generation but callback at or beyond the original exclusive window end | `cancelled`, `retrace-missed-window` |
| Lost identity, incoherent cache, changed epoch/profile or contradictory evidence | Fatal failure; close the uncertain owner without replay |
| Same coherent generation and callback in the original window | Existing prepared batch callbacks followed by one final sync |

The two semantic retrace cancellations do not request an additional VM stop.
The caller's bounded execution continues to its original stop, so the retained
cancellation timestamp can precede that final observation. Python keeps the
undelivered edges bound until explicit rescheduling or `input_cancel_pending()`.

## Host validation and retained evidence

The host independently reconstructs the target and validates every native
snapshot before committing input leases. A successful dispatch requires
`checked.virtual-ns == dispatch-ns == terminal-ns` inside the original window,
unchanged device/model/epoch/generation and coherent phase arithmetic.
Timing-change cancellation requires a higher generation; missed-window
cancellation requires the original generation and a timestamp at or beyond
the exclusive end. Other cancellations cannot carry a callback snapshot.

Historical arm/check validation does not move the live retrace observation
frontier backward. An unsolicited descriptor on an ordinary or idle schedule,
changed terminal descriptor, malformed check or uncertain arm reply closes
the owner. Available raw receipt and original execution-stop evidence remain
attached to the error. A failed script that armed a preexisting batch also
closes its live machine ownership.

The base public format stays `fdisbull-qemu-scheduled-input-1`. A retrace arm
adds `retrace` with format `fdisbull-retrace-input-1`, `edge`, `target_ns`,
`window_end_ns`, the full stopped `before` observation, `native_arm`,
`native_check` and `dispatch_phase_verified`. Existing
`input.schedule-arm/result/observe` journal operations retain the exact native
receipt. Stored history does not recreate live input leases or timers.

## Reproduction and qualification boundary

Start with the official QEMU 10.0.13 archive identified in the manifest.
Keep source/build products and runtime media outside the checkout. Adapt the
[four-layer reproduction](../qemu-retrace/README.md#exact-source-and-reproduction)
by using `('clock', 'media', 'input', 'retrace', 'input-retrace')` as the apply
order and `('clock', 'media', 'input', 'retrace')` as dependency keys. Check
every base hash before applying each layer, and every patched hash afterward.
Use the same isolated TCG/Pixman build recipe from the clock extension.

Host adversaries live in `tests/test_qemu_input_retrace.py`; public routing
and ownership checks in `tests/test_qemu_input_retrace_public.py`. Authored
native witnesses in `tests/test_qemu_input_retrace_native.py` use a guest IRQ1
handler, actual status-port reads and a post-read fence. A guest phase witness
qualifies only when callback-to-fence execution stays inside the same absolute
window. Test existence, schema parsing and patch roundtrips are not native
execution receipts; dated results belong in the maintained handoff.

This boundary establishes native modeled-phase PS/2 callback timing. Device
FIFO acceptance, arbitrary guest consumption, full VBlank, completed frames,
legacy timed helpers and whole-game parity retain separate qualifications.
DOSBox stays the default and both retained selectors remain available.
