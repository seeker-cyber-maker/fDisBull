# Native timed keyboard text

This optional seventh patch implements one finite US-layout text sequence on
`QEMU_CLOCK_VIRTUAL`. Apply the exact clock, media, input, retrace, retrace-input
and keyboard-press patches first. The [source manifest](source-manifest.json)
pins all six prerequisites, this patch and both changed native members. Earlier
patches retain their original bytes; existing commands keep their contracts.

Select `qemu_clock='virtual'` and inspect `virtual_keyboard_type`. The capability
requires the native clock/input commands, `input-send-event` and the new
`x-fdisbull-arm-keyboard-type`. A precise retrace profile is unnecessary. Older
binaries refuse text while retaining their separately advertised operations.

The existing `keyboard_type`, `keyboard.type`, JSON `debug-keyboard-type` and
saved-script `keyboard.type` routes use this capability. The host requires a
stopped VM, an empty owned input queue and no active owned leases. One arm
prepares the whole string without running the guest. The caller chooses a
later bounded run, clock advance or explicit clock-sync step.

## Mapping and timing

`text` contains 1 through 64 printable US-layout ASCII characters, CR, LF or
Tab. Uppercase letters and shifted punctuation each use a separate Shift
chord. CR and LF independently map to Enter, so CRLF is two Enter presses.
`hold_ms` and `gap_ms` are strict integers in 1 through 1000, defaulting to 40.
Empty text, unsupported characters and invalid timing refuse before arming.

| Edge | Delay from the preceding actual callback, or arm |
| --- | --- |
| First character's first make | 2 ms after arm |
| Each later character's first make | `gap_ms + 2` ms after the prior character's final release |
| Other makes and Shift releases | 2 ms |
| Main-key release | `hold_ms` after its make |

Shift is released after each shifted character. There is no trailing gap
timer. Each new deadline starts from the actual preceding callback, so late
delivery cannot shorten a hold or collapse later release/gap spacing.

This matches the retained DOSBox physical text mapping and relative ordering.
It assumes an unmodified US guest layout and does not inspect or neutralize
Caps Lock, Num Lock or externally held keys. It does not insert characters
directly into DOS memory or establish that a guest application consumed text.

The maximum text has 256 edges and 128 distinct make/break lifetimes. At most
two physical keys are held by its plan at once. The host keeps future lease
reservations separate from its active ledger, materializes a reservation only
after a validated delivered make, and removes it after its matching break.
Repeated characters and Shift chords have distinct lease identities. The
general 256-pending-edge and 64-active-lease limits remain unchanged.

## Native command and evidence

`x-fdisbull-arm-keyboard-type` accepts `token`, `text`, `hold-ms` and `gap-ms`.
It validates the entire string and signed nominal horizon, then prepares and
pins all one-event PS/2 batches before committing the token. Every callback
revalidates the selected handler and device through the existing input seam.

The existing input API1 receipt gains a `typing` descriptor with `text`,
`hold-ms`, `gap-ms`, `steps` and `dispatched-count`. Each step contains immutable
`key`, `down` and `delay-ns`; `deadline-ns` appears when armed and `dispatch-ns`
only after the callback and sync complete. Only the delivered prefix and its
immediate next step have deadlines. There is no predicted absolute schedule.

Top-level `event-count` remains the entire plan length and `deadline-ns` remains
the first deadline. Top-level `dispatch-ns` exists only after full completion,
equal to the final step and terminal time. Cancelled text can have a delivered
prefix without a top-level dispatch time. Public steps also retain their
character index, lease, sequence and individual lateness. Whole-operation
lateness is `None` because the first deadline and final dispatch are different
edges. Terminal evidence freezes across subsequent observations.

The `typing`, `press` and `retrace` descriptors are mutually exclusive.
Successful ordinary/retrace/press arms clear prior typing evidence; a successful
type arm clears press/retrace evidence. Refused arms preserve the old receipt
and do not consume their token. Modes share the existing query/cancel commands,
4096-token history and migration blocker.

## Stops and explicit recovery

Every edge preserves native profile/epoch ownership, pending debugger/native
stops and reached/equal clock-budget precedence. The first actual VM stop
cancels the undispatched suffix. Text completion does not itself stop the VM.

The host validates the full plan and observed prefix before committing any
lease transition. A stopped partial string retains its delivered holds and
unsent suffix with `requires_resolution`. Another run, text/press arm or
conversion into ordinary/retrace scheduling is refused while it remains bound.

Call `input_cancel_pending()` to discard the unsent suffix and future
reservations. Inspect `input_state()['leases']`, explicitly release retained
holds with `keyboard_key_up(lease)`, then choose their execution. Cancellation
does not synthesize releases. No partial or uncertain sequence is replayed.

Legal text can outlast one 60-second clock advance: 64 shifted characters with
1000 ms hold and gap have a nominal duration of 127,384 ms. Admission preserves
the existing text bounds. The caller must choose a suitable bounded run to an
actual guest stop; the adapter never splits the string into hidden runs or
automatically resumes after a shorter budget cancels it.

Direct arming has one 1000 ms host allowance covering lock admission, native
I/O and evidence persistence, intersected with tighter incoming deadlines. An
expired pre-arm admission leaves the valid stopped owner available. Accepted
or uncertain late arms, malformed native evidence and failed persistence close
the owner with available raw evidence, without retrying callbacks.

## Qualification boundary

Receipts establish selected PS/2 callbacks and sync completion. Device FIFO
acceptance, arbitrary guest consumption and completed drawing remain unknown.
Authored native tests independently inspect IRQ1/scancode memory; their selected
guest observations do not qualify arbitrary games or alternate keyboard layouts.

`timed_input`, `guest_time_control` and `completed_guest_frames` remain false.
The optional eighth [mouse-click extension](../qemu-mouse-click/README.md)
adds a timed physical button pair without requesting movement. Coordinate and
frame-bound clicks, frame-edge input, full VBlank/frame semantics and broad
DOSBox timing parity retain separate gates. Migration after
input use remains blocked; reset/profile loss invalidates the scheduler.

See the [timing guide](../../docs/DOS_QEMU_TIMING.md) and
[handoff log](../../docs/DOS_QEMU_HANDOFF.md) for public usage and dated local
results. Source/schema reproduction, native compilation and actual guest
qualification are separate evidence boundaries.
