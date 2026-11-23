# Banked VBE 101h stride and timed palette

Apply the QEMU 10.0.13 delta after [combined X/Y panning](../qemu-video-vbe101-xy/README.md).
Apply the separate SeaVGABIOS delta in `roms/seabios` after the X/Y
firmware delta. The [source manifest](source-manifest.json) pins the
inputs, patches, and tested ROM.

Use the existing pinned stdvga build recipe with
`EXTRAVERSION=-fdisbull-vbe101-palette` on both `make` invocations.
Copy its generated VGA ROM to `fdisbull-vgabios-vbe101-palette.bin` in the
explicit QEMU firmware directory. Select `vga-640x480-palette` with the
virtual clock and precise retrace. Its model is `qemu-vga-640x480-palette-v1`
and it uses instrumented checkpoint format 13.

- VBE 4F06h reports the active or maximum logical stride. Byte and pixel
  setters round up to eight-byte units. Zero returns `024Fh`. Oversized
  requests clamp to the lesser of 8184 bytes and the aligned limit from
  VRAM and the visible height. The row count saturates at 65535. A changed
  stride establishes a fresh viewport and invalidates the sampled stream.
  Short strides overlap visible rows and admit X=0 only.
- VBE 4F08h selects six- or eight-bit DAC interpretation without changing
  the aperture bank or rewriting the stored palette. Six-bit writes mask
  each channel to six bits. Scanout uses expanded six-bit channels or
  exact eight-bit channels. A width change invalidates the sampled stream.
- VBE 4F09h immediate and retrace-timed writes accept BGRX records. Readback
  fills BGR and leaves X untouched. An out-of-range request returns before
  the BIOS waits or touches the DAC. A timed call waits for a fresh leading
  retrace edge, then writes through the VGA DAC ports.

The machine snapshot saves a waiting BIOS call through its guest CPU and
RAM. It also saves the raw palette, DAC index and partial RGB write state.
The post-load device derives DAC width from the saved DISPI register before
the instrumented source stream is restored. The sampled prefix and retained
complete frame keep their original pixels and deadlines.

The BIOS behavior is scoped to banked 101h on this profile. The
[pinned DOSBox-X 4F06h and 4F09h implementation](https://raw.githubusercontent.com/joncampbell123/dosbox-x/029bd65c5dcc7cdc7f2e14e35278620d9707d969/src/ints/int10_vesa.cpp)
documents the S3 behavior used for the local comparison.
