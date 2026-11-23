# DOSBox-X packed VGA panning observation

Apply the manifest-pinned delta after the
[640×480 visible row timing diagnostic](../dosbox-vga-visible-row-timing/README.md).
The existing `video.probe` option observes packed8 rows with a latched fine
pan of up to three pixels. Per-scanline horizontal panning effects must be
disabled. Each retained receipt still records the coarse latch in CRTC
units and the byte address used by the renderer for every actual row.

Set `FDISBULL_REQUIRE_DOSBOX_VBE_PAN=1`, `FDISBULL_DOSBOX_VBE_PAN`,
`FDISBULL_DOSBOX_VBE_PAN_SHA256`, and `NASM` to run
`python -m pytest -q tests/test_dosbox_vbe_pan_native.py`. The authored
probe measures both retrace edges through real BIOS calls and PIT reads.
It checks 480 sampled row addresses and every RGB pixel at the resulting
coarse and fine offsets.
