# Native stopped unchained VGA source probe

Apply after the verified mode-13 phase patch to QEMU 10.0.13. The command
`x-fdisbull-probe-unchained-vga-rows` reads one to sixteen unique logical
rows of the currently programmed source page on stopped precise primary
standard VGA. The reply names its mode, native clock and VGA generations,
programmed byte origin, pitch and DAC interpretation, with exact RGB888
rows in request order.

For 6-bit DAC input, RGB conversion uses the same upper-bit replication as
the timed source-raster path. The stock QEMU screenshot renderer duplicates
the lowest bit. Comparing the two requires recovering the six original
bits before projecting both to a common RGB representation.

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

The authored two-page fixture and the adjacent Mode 13h checkpoint test
passed locally on Darwin arm64 with QEMU SHA-256
`4f943d26699f1e870c9196e83dd47ccf5b7f12a9e32369e1153aa862c427a3fc`.
The native test receipt digest is
`1eb7ac31d38fc34b8647f4772e491ffda7a6bdd881b2bda2a0b34443390d232d`.
In a separate original Doom run, logical rows 0, 100 and 199 agreed with
both doubled renderer scanlines after DAC projection and matched exactly
through same-process and separate-process checkpoint restore.

This is a stopped programmable-origin observation. The complete timed
raster and format-4/5 checkpoint producers retain their existing
contracts. Qualifying a live page flip will require independent
evidence of the effective latch boundary and pending origin across
restore.
