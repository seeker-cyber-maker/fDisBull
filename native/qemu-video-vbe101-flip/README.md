# Retrace-latched VBE 101h page flips

Apply the QEMU 10.0.13 delta after
[guest-visible VBE timing](../qemu-video-vbe101-sync/README.md). The
[source manifest](source-manifest.json) records the QEMU and SeaVGABIOS
preimages. The VGA BIOS patch applies from the `roms/seabios` directory.

Select `--qemu-video-source-profile vga-640x480-flip` with virtual clock,
precise retrace and an explicit firmware directory containing
`fdisbull-vgabios-vbe101-flip.bin`. This profile uses
`qemu-vga-640x480-flip-v1` and format 10 checkpoints. The other profiles
continue to use the stock VGA BIOS and their existing checkpoint formats.

## Build the alternate ROM

Use the pinned SeaBIOS 1.16.3 source and its QEMU stdvga configuration.
The commands below use GNU i686 ELF tools on the build host.

```sh
cd roms/seabios
git apply /absolute/path/to/seabios-1.16.3-fdisbull-vbe101-flip.patch
cp ../config.vga-stdvga .config
make CROSS_PREFIX=i686-elf- CPP='i686-elf-gcc -E' PYTHON=python3 olddefconfig
make CROSS_PREFIX=i686-elf- CPP='i686-elf-gcc -E' PYTHON=python3 out/vgabios.bin
cp out/vgabios.bin /absolute/path/to/firmware/fdisbull-vgabios-vbe101-flip.bin
```

The selected firmware inventory and alternate ROM hash are part of the
machine identity used by checkpoint restore.

## Timing contract

The profile supports banked 640 × 480 × 8 at a 640-byte pitch, with one
complete visible window in backing VRAM, zero horizontal offset, six-bit
DAC and the color VGA status port. CPU aperture banking is independent
of the selected display start.

For VBE function 4F07h, BL=00 programs the origin and returns. BL=80
programs it and waits in the guest BIOS for a fresh leading retrace edge.
A request while bit 3 is already high waits for that bit to clear and
rise again. BL=01 returns the programmed origin. Both set operations
become visible at the next line-490 leading edge on the same virtual
clock used for status reads, with the new origin sampled in the next
visible frame. This matches the DOSBox-X S3 banked mode.

Format 10 retains the programmed origin, active origin and pending
absolute deadline even if timed scanout is idle. Complete timed frames
retain the origin sampled across their 480 rows. A live timed stream
resumes its sampled prefix and next row along with the guest BIOS
instruction state.
