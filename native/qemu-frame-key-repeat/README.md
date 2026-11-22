# Native frame-key repeat

This patch follows the QEMU 10.0.13 source-raster checkpoint, stopped keyboard
batch and pending-event layers. Verify the eight source preimages and patch
digest in `source-manifest.json`, apply the patch, then verify all eight
postimages before regenerating QAPI and building the native executable. The
existing native producers remain usable with their exact checkpoint artifacts.

An eligible frame-owned make selects one repeat key. Its first expiry is the
stopped make time plus the guest-programmed delay. The timer uses
`QEMU_CLOCK_VIRTUAL` and emits a complete make through the actual PS/2 FIFO
and IRQ path. Native repeats leave the owner's explicit edge count intact.
Releasing the candidate cancels repeat without resuming an older held key.
Modifiers, locks and the special Print/Pause sequences are outside this
profile.

The keyboard resets to parameter `0x2b`. PS/2 command `F3` programs seven
parameter bits. Bits 6–5 select a delay in 250 ms increments. Bits 4–0 select
the interval using `(8 + A) * 2**B / 240` seconds, with A in bits 2–0 and B in
bits 4–3. Native deadlines use integer nanoseconds. When controller or queue
state prevents a complete make, the timer skips that occurrence and keeps
the cadence. An already pending synchronous stop takes precedence at a tie.

The stopped `x-fdisbull-query-frame-key-repeat` command returns the parameter,
derived delay and interval, next absolute virtual deadline, and the candidate
QCode when armed. An idle timer reports deadline `-1`. The existing frame-key
receipt exposes capability through `repeat-supported`.

Instrumented checkpoint format 4 includes the repeat proof alongside the
frame-key and source-video proofs. The keyboard device snapshot retains a
nondefault parameter. Import compares the sidecar to the loaded device and
checks that the candidate is an eligible owned held key. It then arms the
saved absolute deadline with fresh frame-key ownership. The host independently
reads the phase before admitting the replacement owner. Restoring the phase
adds no make to the FIFO and needs the same native producer as the checkpoint.

The authored native tests in `tests/test_qemu_frame_key_repeat_native.py`
exercise actual guest scan bytes, initial and programmed timing, release,
and hot and cross-process cold restore through a source-raster timeline.
This scope leaves whole-game and paired DOSBox-X parity open.
