# Timed 640 × 480 VGA and VBE source rows

Apply this QEMU 10.0.13 delta after
[Mode 13h BIOS reapply](../qemu-video-mode13-overlap/README.md).
The [source manifest](source-manifest.json) pins the exact preimages and
postimages.

Select `--qemu-video-source-profile vga-640x480` with virtual clock and
precise retrace. The source model is `qemu-vga-640x480-scanline-v1`.
Its admitted layouts are standard four-plane VGA Mode 12h and banked
8-bit packed VBE 101h. Both use six-bit DAC inputs, a zero display origin,
the standard pitch and 480 visible rows. A mode transition retires the
stream and the next mode is armed explicitly.

The planar sampler recombines the four VRAM bitplanes, applies the active
plane-enable mask and attribute palette, and reads the live DAC. The VBE
sampler reads packed backing VRAM. The CPU's 64 KiB aperture window can move
while the display still reads the same backing raster. Actual layout
changes invalidate the source. The first visible row is scheduled a quarter
of a line after the native frame boundary. Every subsequent row is sampled
one physical line apart.

Mode 12h uses the native VGA CRTC timing. Bochs VBE does not supply a
physical raster clock, so the opt-in VBE 101h profile models the DOSBox-X
S3 BIOS's 29.403 MHz clock, with 800 dots and 525 lines. This yields
27,208 virtual nanoseconds per line and a 14,284,200 ns quantized frame.
The existing VGA retrace API continues to report VBE phase as unsupported.

Instrumented format 8 binds the layout, pending row timer and expiry,
partial RGB prefix and exact sampled timestamps alongside any complete
raster. Restore requires the matching layout and live backing VRAM. The
new format is specific to this profile. Formats 3–7 retain their
existing descriptors and timing.
