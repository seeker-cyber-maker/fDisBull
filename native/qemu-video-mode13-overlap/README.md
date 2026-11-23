# Mode 13h BIOS reapply callback overlap

Apply this QEMU 10.0.13 delta after
[the unchained read-plane correction](../qemu-vga-unchained-cpu-planes/README.md).
The [source manifest](source-manifest.json) pins the exact preimages and
postimages.

Select `--qemu-video-source-profile dosbox-mode13-overlap` with virtual clock
and precise retrace. The model is `qemu-vga-chain4-dosbox-mode13-overlap-v1`.
This profile is explicit and exclusive with the existing Mode 13h and
unchained profiles.

The native device requires the observed standard BIOS packet, unchanged
precise timing from a prior Mode 13h setup, and the same full effective VGA
configuration before and after the packet. SeaBIOS display-mask writes
before the packet advance the raw census. They leave the timing identity
available for this comparison. A true text-to-graphics setup uses the
ordinary first even-field raster and subsequent odd-field rasters.

Reapply retires the old source owner. Arm the new stream before the first
new raster boundary to observe the overlap. The native QEMU timer dispatches
two independently advancing callback deadlines over that raster. The new
chain supplies the even physical callbacks. The retained chain supplies
the odd physical callbacks and samples one row at each deadline. Its
relative separation is the observed DOSBox-X phase gap normalized to
QEMU's local physical line period. A callback that runs into the other
chain's deadline invalidates the observation. The next raster uses
ordinary even-line spacing, followed by steady odd-line spacing. Late
attachment starts at the next eligible raster.

Instrumented format 7 retains the exact reapply setup, both chain anchors
and pending deadlines, the actual QEMU timer expiry, sampled RGB prefix and
row times. A completed raster carries its own immutable overlap descriptor.
A load validates those fields and rebinds the owner with a fresh stream token
and epoch. Existing formats 3–6 retain their own validated timing models.
The paired witness and the current scope are recorded in the
[Mode 13h timing diagnostic](../../docs/DOS_QEMU_VGA_STEADY_PHASE_DIAGNOSTIC.md).
