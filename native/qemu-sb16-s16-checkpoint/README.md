# Signed 16-bit SB16 checkpoints

This package extends the existing private SB16 checkpoint codec to preserve a
signed little-endian 16-bit guest voice. It keeps the existing U8 behavior and
uses the audio core's existing signed-sample, resampler and buffer serialization.
Only `hw/audio/sb16.c` changes. There is no new QAPI command, VMState layout or
Python API.

## Source boundary

Apply this patch after `native/qemu-sb16-transfer-count`. Verify the exact
prerequisite manifest, patch bytes and `sb16.c` before/after hashes in
`source-manifest.json`. Use strip level 1, with no patch fuzz. The independent
raster-proof change touches other files and is not a dependency of this package.

The C patch was recovered byte-for-byte from the original preparation. This
manifest and the replacement tests are new recovery work; the original
integration object, acceptance fixture and raw native results were not recovered.
Any new build is a new producer and requires its own execution evidence.

## Admitted state

The live voice must be U8 or signed little-endian S16, mono or stereo, at
5,000–45,000 Hz. For S16, the selected SB16 must own incrementing DMA5 in
memory-to-device mode. DMA controller registers are words; the current internal
DMA position and SB16 IRQ credit are bytes. Address, extent and credit checks
must retain those units.

S16 admission requires complete frames and agreement between the live DSP and
software voice on sample format, channel count, alignment and byte rate. The
existing stopped-state, timer, mixer-credit and DMA-controller guards also apply.
Decrementing DMA, a different transfer owner, partial frames, a mismatched voice,
signed U8 and unsigned S16 remain outside the supported extension.

The existing codecs preserve pending IRQs and DREQ, including an older pending
8-bit IRQ. The patch does not normalize those states or infer them from the live
format. Saving records the actual voice format; loading validates and recreates
that format before the existing audio-core restoration.

Guest sample format and capture format are separate choices. This package does
not change default U8 mono capture or relax the explicit stereo capture profile.
Checkpoints remain bound to the exact executing native producer; matching a
profile name or state-layout version does not permit cross-binary import.

## Qualification

Fresh native qualification is pending. Both complete source trees were rebuilt
from the official QEMU 10.0.13 archive: the 31-patch parent and that parent plus
this recovered patch. Every source byte, file mode and symlink target was
independently checked; the two trees differ only in `hw/audio/sb16.c` at the
recorded hashes. Patch applications used zero fuzz.

The 12 source probes pass while executing the exact added C admission helpers
with undefined-behavior sanitization. The replacement guest fixture also passed
121 host checks, including 31 actual NASM assembly/disassembly checks. Its first
host attempt correctly refused a temporary object store inside repository
ancestry; moving only that temporary store and pytest directory outside Git
allowed the unchanged tests to pass. The failed attempt remains recorded.
The final host gate also covers bounded retention of emulator/serial logs and
preservation of an original body error when session or project cleanup fails.
These results qualify source and harness behavior, not complete QEMU device
persistence or guest execution.

The published `tests/test_qemu_sb16_count_native.py` deliberately expects S16
checkpoint refusal on its legacy producer. Keep that control separate from the
new producer's success gate. A test that accepts either refusal or success would
erase the compatibility boundary.

Native acceptance must compare the complete guest CPU register dictionary, the
fixture's report and all 16 KiB of its authored DMA arena, the SB16 device
dictionary, every PCM byte and callback chunk, virtual time and retired
instruction count. This does not claim comparison of unrelated DOS/system RAM.
Owner and epoch renewal are checked separately. Only host receipt fields `sequence` and
`host_monotonic_ns` may differ in a stationary clock comparison, and their
expected monotonic behavior still needs an explicit assertion. Cold tests must
own and reap both the worker and its emulator process group.

No broader DOSBox-X parity or macOS native qualification follows from recovering
the patch. DOSBox-X remains the default.
