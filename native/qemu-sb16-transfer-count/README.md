# Documented SB16 transfer counts

This incremental QEMU10.0.13 patch follows
[stereo capture](../qemu-stereo-capture/README.md). The adjacent
[source manifest](source-manifest.json) pins its parent and the one changed
file. Candidate build and runtime qualification are pending.

Creative's [Hardware Programming Reference, sections3-27,3-29,6-23 and6-24](https://ardent-tool.com/sound/Dev_Kit_SB_Series_Hardware_Programming_Ref_DSA0085515.pdf)
defines Bx/Cx lengths as channel samples minus one. Cx samples occupy one byte;
Bx samples occupy two bytes. Stereo does not multiply the programmed byte
extent again. The patch removes only the inherited single-cycle stereo
doubling. Auto-init arithmetic, the legacy DMA command path, DMA scheduling,
sample rate, channel format, mixer arithmetic and VMState layout stay intact.

The authored non-wrapping oracle is
`tests/test_qemu_sb16_count_native.py`. It runs identical COM bytes on both
engines and reads actual DMA registers before dispatch, in the IRQ handler,
and after a bounded tail. DMA5 counters remain word units with explicit byte
conversion. Eight variants cover U8/S16, mono/stereo and FIFO off/on. Before
the patch, the installed DOSBox-X follows the documented count in every
variant; frozen QEMU follows it in mono and doubles it in all four stereo
variants. Each case receives the correct IRQ and exits with its owner reaped.
The failing baseline receipts remain retained separately from candidate results.

The source comment formerly justified doubling for Miles `setsound.exe`.
That compatibility behavior is deliberately changed for the documented-count
producer. Preserve the frozen binary for prior acquisitions; no current Miles
qualification is claimed. There is no new compatibility property or alternate
default in this patch.

Signed16 playback/count coverage does not extend checkpoint eligibility.
The existing native U8-only voice guard remains unchanged. Every S16 oracle
case requires the explicit public checkpoint refusal and verifies that the
stopped owner, CPU, clock and device state remain unchanged. S16 in-flight
persistence needs a separate reviewed extension.

Reconstruct the pinned parent into a separate source tree, verify the before
hash, apply with `patch --batch --forward -p1`, then verify the after hash.
Build a new producer and retain its source/toolchain/ELF identity. Existing
exact-producer checkpoint fences remain mandatory even though VMState fields
are unchanged. Do not replace an old binary beneath an existing state receipt.

Qualification must pass the same non-wrapping oracle, the corrected U8
known-wave fixture, explicit ring block-size checks, unchanged paired-tone
guest bytes with strict documented DMA extent, existing U8 hot/cold replay,
old-producer state rejection and bounded actual Doom auto-init continuation.
This package does not establish ADC, ADPCM, S16 checkpoint support, general
hardware timing fidelity or full DOSBox-X parity.
