# Banked VBE 101h protected-mode interface

Apply this SeaVGABIOS delta after [VBE stride and palette](../qemu-video-vbe101-palette/README.md).
The [source manifest](source-manifest.json) pins the prior QEMU producer,
the firmware sources and the tested ROM. Build with the existing stdvga
recipe and `EXTRAVERSION=-fdisbull-vbe101-pmi`, then copy the generated
ROM as `fdisbull-vgabios-vbe101-pmi.bin`.

Launch with an explicit firmware directory, virtual clock, precise
retrace and `vga-640x480-pmi`. The profile uses the existing palette
device model and format 13. Machine and firmware identity still bind
a checkpoint to this launch profile.

Call INT 10h AX=4F0Ah BL=00h to discover the table, including
before selecting mode 101h. ES:DI and CX describe the copyable code and
its I/O permissions list. The DOSBox-X-compatible BL=01h through BL=03h
views describe the individual routines. The caller supplies 32-bit code,
data and stack selectors with access to the advertised ports.

The three 32-bit near-call routines check the device is in supported
banked 101h before operating.

- Window A selects a 64 KiB bank.
- Display start takes a DWORD address in DX:CX. It preserves any already
  programmed fine panning and submits an atomic bounded viewport change.
  BL=80h waits for a new leading retrace edge after programming.
- Primary palette writes take BGRX entries at ES:EDI. BL=80h waits for
  a new leading edge before writing through the VGA DAC.

Format 13 restores the copied table, caller stack and protected CPU
state with the VGA and raster state. A pending wait resumes directly in
the relocated routine. The comparison is scoped to banked 101h and the
VBE 2.0 near-call interface.
[VESA 4F0Ah specification](https://www.sra.uni-hannover.de/Lehre/SS21/V_BSB/doc/vbe3.pdf#page=64)
