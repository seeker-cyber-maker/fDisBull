# Native timed mouse-button click

This optional eighth patch implements one physical mouse-button down/up pair
on `QEMU_CLOCK_VIRTUAL`. Apply the exact clock, media, input, retrace,
retrace-input, keyboard-press and keyboard-type patches first. The
[source manifest](source-manifest.json) pins all seven prerequisites, this
patch and both changed native members. Earlier patches keep their original
bytes, and the existing keyboard dispatcher remains unchanged.

Select `qemu_clock='virtual'` and inspect `virtual_mouse_click`. The capability
requires the native clock/input commands, `input-send-event` and the new
`x-fdisbull-arm-mouse-click`. A precise retrace profile is unnecessary. A
seven-patch executable refuses this helper while retaining its independently
advertised physical input and keyboard operations.

The QEMU-only public method is
`mouse_button_click(button='left', *, hold_ms=80)`. JSON uses
`debug-mouse-button-click`; saved scripts use `mouse.button-click`. The host
requires a stopped owner, an empty owned input queue, no owned held leases,
no bound schedule and a project outside a caller-owned transaction. One arm
prepares the pair without running the guest. The caller chooses a later
bounded run, clock advance or explicit clock-sync step.

Existing `click(x, y)`, `debug-click`, `click`/`click-frame` and
`input.mouse.click` retain their screenshot/pixel/frame contracts and their
native QEMU refusals. This helper does not add coordinate or frame mapping.

## Buttons and timing

`button` must be exactly `left`, `middle` or `right`. `hold_ms` is a strict
integer in 1 through 1000; booleans, coercions and other button names refuse
before host admission. The native command also rejects wheel, side and extra
buttons admitted by the broader QAPI `InputButton` enum.

| Edge | Deadline |
| --- | --- |
| Button down | Arm time plus 2 ms |
| Button up | Actual down callback and sync completion plus `hold_ms` |

The release deadline is established only after the down callback completes.
A late down cannot shorten the requested hold. There is no trailing timer,
implicit run, sleep, continuation, rebase or replay. Full completion does not
itself stop the VM.

No movement is requested. Pre-existing mouse accumulators or external button
state may affect the resulting packets, including their movement fields.
The operation does not inspect, neutralize or establish external physical
button state, cursor position or an application's interpretation of a click.

## Native command and evidence

`x-fdisbull-arm-mouse-click` accepts `token`, `button` and `hold-ms`. It checks
the full signed nominal horizon before preparing two separate one-button
batches. Both batches pin their PS/2 handler and device before the token is
accepted. Each edge revalidates that ownership and gets its own callback and
sync. Combining down and up under one mouse sync could collapse the press;
this patch never combines those edges into one batch.

The existing input API1 receipt gains an optional `click` descriptor:
`button`, `hold-ms`, `steps` and `dispatched-count`. There are exactly two
steps, each containing immutable `button`, `down` and `delay-ns` fields.
`deadline-ns` appears for the delivered prefix and immediate next edge;
`dispatch-ns` appears only after the corresponding callback and sync complete.
The plan never predicts later absolute deadlines.

Top-level `event-count` is two and `deadline-ns` remains the first deadline.
Top-level `dispatch-ns` is present only after both callbacks complete and
equals the final step's dispatch and terminal time. A cancelled or failed
click retains its actual prefix without claiming full completion. Terminal
fields and per-edge evidence freeze until another token is accepted.

`click`, `press`, `typing` and `retrace` are mutually exclusive. Every accepted
mode clears incompatible descriptors. A rejected arm preserves the previous
receipt and does not consume the proposed token. All modes share query/cancel,
the process-lifetime 4096-token history and the existing migration blocker.

The public receipt retains `fdisbull-qemu-scheduled-input-1` as its base and
uses `fdisbull-mouse-click-1` for the click descriptor. Public steps also retain
their sequence, lease and individual lateness. Whole-operation lateness is
`None` because the first deadline and final dispatch describe different edges.
The existing journal records arm, prefix and terminal evidence for reopening.

## Stops and explicit recovery

Every edge preserves native profile/epoch checks, pending debugger/native stop
precedence and reached/equal clock-budget precedence. A budget at either edge's
deadline wins before that edge. The first actual VM stop cancels the remaining
suffix. Reset or profile loss invalidates the scheduler; migration after input
use remains blocked.

The host reserves one paired mouse lease and two pending records at successful
arm. It validates the complete native plan, prefix and owned budget cutoff
before committing any lease transition. A delivered down remains an owned hold
after interruption. A cancelled click remains bound and refuses another run
or a new/converted schedule until the caller resolves it.

Call `input_cancel_pending()` to discard the unsent suffix. Inspect
`input_state()['leases']`, release a retained hold with
`mouse_button_up(lease)`, then explicitly choose execution. Cancelling pending
work retains any delivered hold and clears its pending release; it does not
synthesize a release, replay an edge or clear device queues.

Direct arming has one 1000 ms host allowance covering lock admission, native
I/O and evidence persistence, intersected with tighter incoming bounds. A
pre-arm admission failure leaves a valid stopped owner available. Accepted or
uncertain late arms, malformed native evidence and persistence failures close
the owner with available evidence and without replay.

## Qualification boundary

Native receipts establish selected PS/2 callback and sync completion. A
disabled mouse can ignore an edge, remote mode can retain state without a
stream packet, and a full queue can prevent packet emission. These states do
not establish delivery. Device FIFO acceptance, arbitrary guest consumption,
INT33 behavior, cursor position and application response remain unknown.

A controlled IRQ12 fixture can independently observe distinct down and up
packets after it configures and enables a default PS/2 stream mouse. Those
selected guest observations do not qualify arbitrary guests, external button
state, accumulated movement or alternative mouse modes. Source/schema
reproduction, native compilation and guest observation remain separate
evidence boundaries; dated results live in the handoff log.

`timed_input`, `absolute_mouse`, `guest_time_control` and
`completed_guest_frames` remain false. Screenshot mapping, frame/VBlank
semantics and generic DOSBox timing parity keep their separate gates. DOSBox
remains the default, and all 127 promotion qualifications remain open.

See the [timing guide](../../docs/DOS_QEMU_TIMING.md) and
[handoff log](../../docs/DOS_QEMU_HANDOFF.md) for usage and dated local results.
