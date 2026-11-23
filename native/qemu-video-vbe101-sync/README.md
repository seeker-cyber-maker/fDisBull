# Guest-visible VBE 101h retrace and timed scanout

Apply this QEMU 10.0.13 delta after
[timed 640 × 480 VGA](../qemu-video-vga480/README.md).
The [source manifest](source-manifest.json) pins the exact preimages.

Select `--qemu-video-source-profile vga-640x480-sync` with virtual clock and
precise retrace. The new profile keeps the Mode 12h source path and admits
VBE 101h with the standard banked 8-bit layout, six-bit DAC, color status port
and zero display origin. The native source model is
`qemu-vga-640x480-sync-v1`.

Guest Input Status 1 reads, native edge waits and timed source rows share a
525-line frame grid on QEMU's virtual clock. Each line lasts 27,208 ns,
rounded from the DOSBox-X S3 BIOS's 29.403 MHz clock across 800 dots.
Status bit 0 asserts after visible line 479 or during horizontal blanking
at 80 to 98 of 100 character positions. Bit 3 asserts from the beginning
of line 490 through the beginning of line 492, inclusive. Row zero is
sampled one quarter of a line after the local frame boundary. CPU aperture
bank changes leave this layout and cadence intact.

The effective `vbe101-timing` receipt describes these boundaries. The
inherited VGA register census and cached CRTC timing are retained as
independent hardware state. Format 9 restores the virtual timestamp,
effective VBE timing, completed raster and sampled prefix together. Live
phase is recomputed from that restored clock. Formats 3–8 keep their
existing profile and checkpoint contracts.
