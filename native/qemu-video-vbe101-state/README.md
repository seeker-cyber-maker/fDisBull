# VBE 101h guest display state

Apply this SeaVGABIOS delta after [VBE linear framebuffer support](../qemu-video-vbe101-lfb/README.md).
The [source manifest](source-manifest.json) pins the patch, ROM and
existing QEMU producer. Build with the existing stdvga recipe and
`EXTRAVERSION=-fdisbull-vbe101-state`. Copy the result as
`fdisbull-vgabios-vbe101-state.bin` into the explicit firmware directory.

Select `vga-640x480-vbe-state` with the virtual clock and precise retrace.
The profile runs the existing linear and banked 101h device model and
uses checkpoint format 14.

The real-mode VBE call 4F04h reports the guest buffer size in complete
64-byte blocks. The save and restore operations use the requested
hardware, BIOS data, DAC and extended-register fields. The DAC state
includes the palette width. Restoring VBE 101h keeps the framebuffer
bytes, applies the saved stride and viewport and restores the selected
bank. The guest must use the buffer size and layout from its own ROM.

A guest can call 4F04h restore after returning from an emulator
checkpoint. The emulator checkpoint retains the guest's buffer and
current machine state. The guest restore reapplies the saved display
state to its current machine. Instrumented source capture starts a new
raster stream after the video configuration changes.
[VBE 4F04h state buffer specification](https://www.sra.uni-hannover.de/Lehre/SS21/V_BSB/doc/vbe3.pdf#page=53)
