# Native timed keyboard presses

This optional sixth patch implements one timed keyboard chord on
`QEMU_CLOCK_VIRTUAL`. Apply the exact clock, media, input, retrace and
retrace-input patches first. The [source manifest](source-manifest.json) pins
the patch chain and every changed native member. Earlier patches keep their
original bytes; their commands retain their existing behavior.

Select `qemu_clock='virtual'` and inspect `virtual_keyboard_press`. The
capability requires the native clock/input commands, `input-send-event` and
`x-fdisbull-arm-keyboard-press`. The precise retrace launch profile is not
required. Older binaries continue to provide their own advertised operations.

The existing `keyboard_press`, `keyboard.press`, `debug-keyboard-press` and
saved-script `keyboard.press` routes use this capability. A press arms while
stopped, with an empty owned input queue and no active owned leases. It never
executes the guest. The caller chooses a later bounded `run()` or
`clock_advance()` that allows enough time for the desired callbacks.

## Chord timing

The main key is one existing physical key name. Modifiers are zero through
three distinct `ctrl`, `alt` and `shift` names, in caller order; the main key
cannot also appear among them. `hold_ms` and `gap_ms` are strict integers from
1 through 1000, with defaults of 40.

| Edge | Delay from preceding callback, or arm for the first edge |
| --- | --- |
| Each modifier make, in caller order | 2 ms |
| Main key make | 2 ms |
| Main key break | `hold_ms` |
| Each modifier break, in reverse caller order | 2 ms |

This is the retained DOSBox single-press ordering. `gap_ms` is validated and
recorded but does not affect one press: the retained implementation applies
that option only between characters in its separate text operation. There is
no trailing gap timer. The optional seventh
[keyboard-type patch](../qemu-keyboard-type/README.md) supplies a separately
admitted bounded US-layout text sequence.

Each deadline is computed from the **actual preceding callback time**. A late
make therefore cannot shorten the requested hold, and a late break cannot
collapse the spacing before later modifier releases. This is modeled virtual
time, not physical CPU cycle timing.

## Native command and receipt

`x-fdisbull-arm-keyboard-press` accepts `token`, `key:QKeyCode`,
`modifiers:[QKeyCode]`, `hold-ms` and `gap-ms`. It returns the existing
`FdisbullInputInfo`, with one optional `press` descriptor. The native command
validates every key and timing value and prepares all two through eight
individual one-event batches before accepting the token. Each batch retains
the selected PS/2 handler identity and revalidates it immediately before its
callback. It does not use QEMU's delayed legacy keyboard queue.

The descriptor contains `key`, `modifiers`, `hold-ms`, `gap-ms`, `steps` and
`dispatched-count`. Each immutable step plan contains `key`, `down` and
`delay-ns`. `deadline-ns` appears when that step is armed, and `dispatch-ns`
appears only after its input callback and sync return. At most the delivered
prefix and the immediate next step have deadlines. Later steps cannot claim
a precomputed dispatch schedule.

The top-level `event-count` remains the full plan length and `deadline-ns`
remains the first deadline. Top-level `dispatch-ns` appears only when every
step has dispatched, and equals the last step's dispatch time and terminal
time. A cancelled press can have a delivered prefix while its top-level
`dispatch-ns` is absent. Inspect its descriptor before interpreting delivery.
The public adapter reports lateness separately for each delivered step; its
batch-level `lateness_ns` is `None` because the first deadline and final
dispatch belong to different edges.

Terminal step evidence freezes across queries. The press descriptor is
mutually exclusive with retrace input evidence. A new ordinary or retrace arm
clears it; a new press clears any previous retrace descriptor. All three modes
share the existing query/cancel commands and bounded 4096-token history.

## Stop precedence and recovery

Every edge checks native clock/profile/epoch ownership, pending stops and
reached clock budgets before dispatch. A pending debugger/native stop wins.
A reached or equal clock-budget deadline wins even if the input timer was
inserted first. The first actual
VM stop cancels any remaining steps. Completion does not itself stop the VM.

The host validates the complete receipt and delivered prefix before updating
any lease. It removes only proven delivered edges from the pending queue.
Successful completion releases every owned chord lease. Early cancellation
retains dispatched holds and the unsent suffix, with `requires_resolution`.
Another run, a new press or conversion to ordinary/retrace batch scheduling
is refused until the caller explicitly cancels that suffix.

Call `input_cancel_pending()` to discard the unsent suffix. Then inspect
`input_state()['leases']` and explicitly release each retained keyboard lease
with `keyboard_key_up(lease)` and a separately chosen execution. Cancellation
does not synthesize releases. No partial chord or uncertain callback is
automatically replayed.

An unknown arm outcome, malformed or regressing evidence, failed dispatch,
expired accepted/uncertain arm or failed evidence persistence invalidates
ownership and closes the VM. A lock/admission timeout before arming leaves
the valid stopped machine available. Native evidence remains attached to the original
stop/error result. Direct press arming has one 1000 ms host allowance including
lock admission, and respects tighter script, session or transport deadlines.

## Evidence boundary

Receipts prove selected PS/2 callbacks and sync completion. They leave device
FIFO acceptance and guest consumption unknown. The authored native witnesses
separately inspect IRQ1/scancode memory; they do not establish generic game
consumption or completed drawing.

`timed_input`, `guest_time_control` and `completed_guest_frames` remain false.
The optional eighth [mouse-click extension](../qemu-mouse-click/README.md)
adds a timed physical button pair without requesting movement. Guest text
consumption and layout, coordinate/frame-bound clicks, frame-edge input and
generic DOSBox timing parity still need their own qualification. Migration remains blocked after native
input use, and reset/profile loss invalidates the scheduler.

See the [timing workflow](../../docs/DOS_QEMU_TIMING.md#queue-one-timed-keyboard-press)
and [handoff log](../../docs/DOS_QEMU_HANDOFF.md) for usage and dated local
verification. Source and installed native witnesses run separately from the
host protocol tests; a test listed in the inventory is not a passing receipt.
