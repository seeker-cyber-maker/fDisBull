# Banked VBE 101h horizontal panning

Apply the QEMU 10.0.13 delta after
[overdue keyboard-repeat stability](../qemu-frame-key-repeat-stability/README.md).
The [source manifest](source-manifest.json) pins every preimage.

Select `--qemu-video-source-profile vga-640x480-pan` with the virtual
clock, precise retrace and the existing
[alternate SeaVGABIOS](../qemu-video-vbe101-flip/README.md). The source
model is `qemu-vga-640x480-pan-v1` and checkpoints use format 11.

The banked 640 × 480 × 8 viewport uses a guest-selected pitch of
640 to 8,184 bytes in eight-byte units. VBE 4F06h rounds supported
wider requests upward to that alignment within the VGA memory limit.
The programmed viewport fits one logical row. A transient combination
of independently latched values can extend by up to three adjacent
pixels at the right edge. Timed scanout requires the complete window
to fit backing VRAM.

VBE 4F07h programs the display start and fine offset. The coarse
four-byte origin latches at the leading retrace edge on line 490.
The zero-to-three pixel offset latches at the trailing edge on line 492.
The firmware wait still returns at a leading edge. A write between the
edges can select a combined viewport for one frame. The getter returns
the programmed coordinates.

Format 11 saves the live pitch, both active and programmed values and
each pending absolute deadline. Timed scanout reads the coarse origin and
fine offset active for each raster and records its own viewport together
with the row schedule and pixels. A pitch change starts a fresh viewport
and retires the old source stream. Modes and checkpoints using earlier
profiles retain their existing layout contracts.
