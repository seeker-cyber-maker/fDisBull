# CPU VGA read-plane selection during timed scanout

Apply this QEMU 10.0.13 delta after
[the timed unchained VGA latch](../qemu-vga-unchained-latch/README.md). The
[source manifest](source-manifest.json) pins the exact input and output.

The VGA graphics controller read-map selection controls which plane the CPU
reads through the VGA aperture. The display continues to sample all four
planes. The timed source stream now retains its existing layout across this
register change. The full configuration census still records the register
and increments its generation. Actual display layout changes still
invalidate a timed stream, and its programmed and selected origins keep
their existing latch and checkpoint semantics.

Original Doom's stock timedemo exercises this path in its fuzz renderer. On
the preimage build, the actual `OUT DX,AX` to `03CEh` changed only graphics
register 4 and retired the timed source. A native regression repeats the
CPU read-plane change after arming and requires a complete exact raster
with the new configuration generation. It also switches the display shift
mode and requires stream invalidation.
