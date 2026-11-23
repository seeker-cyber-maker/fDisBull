# VBE 101h linear framebuffer

Apply the QEMU 10.0.13 delta after [VBE stride and palette](../qemu-video-vbe101-palette/README.md).
Apply the SeaVGABIOS delta after the [protected-mode interface](../qemu-video-vbe101-pmi/README.md).
The [source manifest](source-manifest.json) pins inputs, patches and the
tested ROM. Build with the stdvga recipe and
`EXTRAVERSION=-fdisbull-vbe101-lfb`. Copy the resulting ROM as
`fdisbull-vgabios-vbe101-lfb.bin` into the explicit firmware directory
for this profile.

Select `vga-640x480-lfb` with the virtual clock and precise retrace.
VBE 4F01h reports the device's assigned PCI aperture in `PhysBasePtr`,
and setting bit 14 through 4F02h selects the packed 640 × 480 × 8 linear
mode. A protected guest can map that address and write directly to
the same VRAM used through the banked window. The device and BIOS
keep the existing pitch, DAC, palette and display-start contracts.

The native model `qemu-vga-640x480-lfb-v1` reports `vbe-linear-101`
while the linear bit is active and `vbe-banked-101` in banked 101h.
The two modes share the timed scanout cadence. Changing the addressing
mode retires the current raster stream and its pending viewport latches.
Format 14 associates the retained frame with the saved addressing
mode, samples and latches. PCI framebuffer writes persist through
the existing QEMU VGA VRAM snapshot.

The VBE bank window is unavailable in active linear mode on this
profile. The protected-mode bank routine returns without changing the
bank. The palette and display-start entries still operate on the
linear framebuffer. Selecting banked 101h with the no-clear bit
allows the guest to read the previous framebuffer through its window.
[VBE mode information and linear framebuffer rules](https://www.sra.uni-hannover.de/Lehre/SS21/V_BSB/doc/vbe3.pdf#page=46)
