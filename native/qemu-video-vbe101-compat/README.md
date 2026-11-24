# VBE 101h controller and control-call compatibility

Apply this SeaVGABIOS delta after [VBE 4F04h display state](../qemu-video-vbe101-state/README.md).
The [source manifest](source-manifest.json) pins the exact patch preimages,
configuration, compiler, ROM and unchanged QEMU producer. Build the standard
VGA ROM with `EXTRAVERSION=-fdisbull-vbe101-compat`. Resolve the pinned
`config.vga-stdvga` with `make olddefconfig` in a separate invocation
before building `out-compat/vgabios.bin`, so `CONFIG_VGA_FIXUP_ASM` is
selected when Make parses the build rules. Copy the result into an
explicit private firmware directory as `fdisbull-vgabios-vbe101-compat.bin`.

Select `vga-640x480-vbe-compat` to use this ROM with the existing linear and
banked 101h device model and checkpoint format 14. Existing profiles keep their
own firmware and the same device implementation.

VBE 4F00h writes the standard 256-byte controller block for a legacy caller.
A `VBE2` caller receives the 512-byte form, with its OEM strings and far
pointers inside the caller's extension area. VBE 4F01h reports the 101h
banked and linear image-page counts from the same advertised 16 MiB backing
store. The ROM checks each caller's segment extent before writing a controller
or mode-info block.

VBE 4F05h rejects a bank beyond the advertised backing range before changing
the window register. VBE 4F09h checks the whole BGRX palette span before
accessing the DAC, keeps primary palette set/get behavior, and returns
`024Fh` for an unsupported secondary palette request. The paired DOSBox-X
reference has measured differences for these two unsupported requests; the
[QEMU migration handoff](../../docs/DOS_QEMU_HANDOFF.md) records them.

[VBE 3.0 BIOS function specification](https://www.sra.uni-hannover.de/Lehre/SS21/V_BSB/doc/vbe3.pdf)
