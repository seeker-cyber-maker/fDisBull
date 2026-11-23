# Combined VBE 101h X/Y panning

Apply the QEMU 10.0.13 delta after
[horizontal panning](../qemu-video-vbe101-pan/README.md). The
[source manifest](source-manifest.json) pins both native preimages.

Select `--qemu-video-source-profile vga-640x480-xy` with the virtual
clock, precise retrace and an explicit firmware directory containing
`fdisbull-vgabios-vbe101-xy.bin`. The source model is
`qemu-vga-640x480-xy-v1` and checkpoints use format 12.

Build this ROM from the pinned SeaBIOS source with the
[prior VGA retrace-wait delta](../qemu-video-vbe101-flip/README.md) applied.
Apply the additional SeaVGABIOS X/Y patch in `roms/seabios` and use the
same stdvga build commands. Copy the output to the distinct X/Y ROM
filename. The earlier flip and panning profiles still select their ROM.

VBE 4F07h BL=00h and BL=80h submit both coordinates at one guest I/O
boundary. The getter reads the programmed pair together. The device
validates the visible row and full backing span before updating either
coordinate. An unavailable position returns failure and preserves the
existing programmed and pending state. The [VBE 3.0 specification
for 4F07h](https://www.sra.uni-hannover.de/Lehre/SS21/V_BSB/doc/vbe3.pdf)
defines the failure behavior.

The VGA start address and the fine offset still latch independently
at lines 490 and 492. A request between the edges can produce a
mixed viewport for one frame. Requesting the currently visible viewport
again before either latch retires both pending changes. Checkpoints retain the active and programmed viewport plus
each pending absolute deadline and the partial raster. The paired I/O
uses a single write and has no separate staged coordinate.
