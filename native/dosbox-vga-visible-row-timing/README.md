# DOSBox-X 640×480 visible row timing

Apply the manifest-pinned delta after the
[chain-4 timing diagnostic](../dosbox-vga-row-timing/README.md).
The new observation is opt-in and independent of palette and index capture.

In a stopped session with a completed frame, call `video.probe` with no points
and `source_visible_rows: true`. This enables capture for following frames.
Use the same option with a completed `frame_id` and `mode_id` to read the
retained schedule, and pass `false` to disarm. Each receipt is stored with the
same completed renderer frame that supplies the screenshot and RGB probes.
Unsupported geometry and incomplete observations report unavailable.

This diagnostic observes the standard planar4 and packed8 draw paths at
640×480, with one renderer sample per physical line. Each row records the
producer's scheduled PIC event, actual emulated clock, raw renderer address
and address line. The header records the frame start, first callback,
horizontal and vertical periods, retrace, and latched CRTC start. The
packed8 renderer reads the full framebuffer directly while the paired
fixture populates it through five banked VBE windows.

Run the authored text → Mode 12h → banked Mode 101h → text fixture with
`FDISBULL_REQUIRE_DOSBOX_VGA_VISIBLE_ROWS=1`,
`FDISBULL_DOSBOX_VGA_VISIBLE_ROWS`, its exact
`FDISBULL_DOSBOX_VGA_VISIBLE_ROWS_SHA256`, and `NASM`.

```sh
python -m pytest -q tests/test_dosbox_vga_visible_rows_native.py
```

The witness checks the independent source-clock lattice first and then verifies
all RGB pixels from the same completed frame. Mode 12h uses a fixed
25.175 MHz dot clock. The S3 BIOS translates the VBE request for 70 Hz
refresh into a 29.403 MHz PLL clock, which gives the measured period.
The captured clocks apply to the authored fixture and the selected DOSBox-X
configuration.
