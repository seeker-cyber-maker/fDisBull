# Opt-in stereo capture

This incremental QEMU 10.0.13 package extends the exact
[passive mixer parent](../qemu-mixer-observe/README.md). The adjacent
[source manifest](source-manifest.json) pins the prerequisite and the three
before/after source identities. Native compilation and runtime qualification
are pending; source implementation alone does not qualify this package.

`x-fdisbull-start-audio-format` accepts an immutable capture format for a new
window: the historical `u8-mono`, or `s16-stereo` on the exclusive `sb16-opl`
profile. Stereo output contains 32,000 complete frames per second, with signed
16-bit little-endian left and right samples in each four-byte frame. The
existing start command and default format remain mono unsigned8. Optional
command discovery keeps older native binaries usable with their existing
operations.

The new tap consumes the mixer's internal left/right samples before output
clipping. It changes the observer conversion, not guest SB16/OPL programming,
the headless hardware output format, gain laws, DMA/IRQ behavior, clock pacing
or synthesis. Both rates remain 32 kHz, so the capture resampler retains its
existing equal-rate state invariant. Dropped-frame and callback counters stay
in whole frames; storage, exports and checkpoint payloads scale by frame width.
The maximum is 1,920,000 frames, or 7,680,000 raw stereo bytes.

An attached stereo tap uses audio-core format 4: the unchanged core3 header
followed by a bounded capture-geometry record. Loading validates the complete
record, payload length and destination geometry before restoring core rings
and voices. Mono and absent-tap graphs retain core3; a stopped stereo window
retains its stereo PCM metadata with the absent-tap core3 graph. Existing
fresh-destination failure cleanup and exact native/producer fences remain in
force. This is not cross-binary snapshot portability.

Reconstruct the pinned parent, check each `before_sha256`, apply the patch with
`patch --batch --forward -p1`, and verify every `after_sha256`. Use separate
source/build copies, regenerate QAPI and private audio trace output, and compute
the current source/header dependency closure before compiling. Preserve earlier
native binaries for their producer-bound states.

Qualification requires asymmetric left/right tone evidence, negative controls
for swapped or duplicated mono output, complete hot and separate-process cold
checkpoint futures, initial inactive and empty windows, malformed-geometry
refusal, and legacy mono preservation. A passing scoped slice does not establish
general audio fidelity, OPL3/MIDI support, or complete DOSBox-X parity. DOSBox-X
remains the default. Commercial inputs and retained media/states remain private.
