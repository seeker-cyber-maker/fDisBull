# Native stopped unchained VGA source probe

Apply after the verified mode-13 phase patch to QEMU 10.0.13. The command
`x-fdisbull-probe-unchained-vga-rows` reads one to sixteen unique logical
rows of the currently programmed source page on stopped precise primary
standard VGA. The reply names its mode, native clock and VGA generations,
programmed byte origin, pitch and DAC interpretation, with exact RGB888
rows in request order.

The admissible mode uses standard 256-color shift, unchained A000 VGA
memory without odd/even writes, 320×200 logical pixels, byte CRTC
addressing and two physical scanlines per logical row. The fixed 320-byte
pitch is derived from `CR13h << 3`. The CPU write map mask may select a
single plane while the display still reads all four. The programmed
CRTC origin is multiplied by four exactly once. Each logical pixel then
loads its existing interleaved plane byte. The entire page must fit
within the smaller of the two backing extents and the standard VGA
256 KiB range. The probe refuses split-screen, panning, banking,
wrapping, VBE and chained layouts.

The authored native test writes distinguishable four-plane pages at
CRTC addresses 4000h and 8000h. It reads rows 199, 0 and 100 from each page
with the CPU map mask set to 08h, checks the full RGB rows and rereads the
stopped CPU and clock. A wrapping source is refused. The existing timed
chain-4 stream continues to refuse the unchained setup.

This is a stopped programmable-origin observation. The complete timed
raster and format-4/5 checkpoint producers retain their existing
contracts. Qualifying a live page flip will require independent
evidence of the effective latch boundary and pending origin across
restore.
