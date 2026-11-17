# Passive mixer readback

This incremental QEMU 10.0.13 patch extends the exact
[OPL checkpoint parent](../qemu-opl-checkpoint/README.md). The adjacent
[source manifest](source-manifest.json) pins the prerequisite and both
before/after source identities. A separate macOS arm64 incremental build passes 30 serial compilations and
the retained archive/link/sign recipe. The [local qualification](../../docs/evidence/qemu-mixer-tones-2026-11-16/README.md)
records the exact candidate and bounded preservation/tone gates. Keep earlier native runtimes for their own producer-bound states.

`x-fdisbull-query-mixer` observes the current stopped output graph under BQL.
It reports actual audiodev IDs, registered card names, software voice names,
raw Q32 left/right software gains and mute, voice/HW formats and activity, and
existing capture formats. It sorts and checks identities, with global bounds
of eight audiodevs and 32 cards, voices, HW outputs and capture taps. Names are
limited to 128 UTF-8 bytes. An initially silent card can have no voice, and no
capture descriptor is fabricated before a tap exists.

Gains are `SWVoiceOut.vol` scalars with unity 4,294,967,296. They do not establish
the guest SB16 mixer-register gain law, physical output level or perceived
loudness. `software-volume-applied` identifies whether mixeng applies the gain
rather than delegating volume to a backend. There is no invented master control.
The reported existing channel laws are mono duplication into internal L/R,
mono sum-then-clip and independent stereo clipping. Observation changes none
of those laws. Floating-point, running, malformed, ambiguous or oversized graphs
are refused without altering the graph.

Only `audio/audio.c` and the existing private QAPI audio schema change. The
handler traverses existing records and allocates its response; it does not read
ports, synthesize, flush/drain buffers, execute guest instructions, register a
capture, write gains or change timers. SW/HW layouts, VMState versions, audio
core codecs, SB16 DMA/IRQ behavior and OPL state/timing remain unchanged.

Verify the prerequisite and every `before_sha256`, apply the patch with
`patch --batch --forward -p1`, and verify each `after_sha256`. Build in a separate
source/build copy. Regenerate QAPI and the private audio trace output, then use
the generated-file diff and both current compiler depfiles and Ninja dependency
metadata to select the affected compilation closure. Update the copied utility
archive and replay the retained x86 link/sign recipe. A query addition requires
registration, introspection and visitor outputs; it is not a one-object build.
No configure, unrelated-target build, CI or shared activation is required.

Host discovery of the command is optional, so older admitted native binaries
retain their existing operations. Unchanged checkpoint wire layouts do not
authorize cross-binary restore: existing exact native/producer identity fences
remain in force. DOSBox-X stays the default. This package adds observability;
paired tone/readback and preservation gates must qualify the resulting candidate.
