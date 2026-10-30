# Console media parsing

This stage reads console media as data. It identifies supported headers,
reports declared hardware and sizes, records original file offsets, and checks
bounded structural extents. It does not create CPU mappings, disassemble these
CPUs, emulate a console, recover game rules or decompile C. `loadable` is always
false for these reports. The ordinary executable loader remains separate.

```sh
fdisbull identify /private/game.nes
fdisbull inspect /private/game.sfc
fdisbull rom-inspect /private/game.md
fdisbull rom-inspect /private/data-track.bin
```

`identify` and `inspect` keep their 64 MiB input limit. `rom-inspect` reads a
cartridge completely within that limit. For a recognized Sega data track it
reads a 4 KiB prefix and at most one additional physical sector, so an ordinary
CD image can be inspected without loading the whole track. Supply the data
track beginning at sector zero, rather than a CUE sheet or an audio track.
JSON requests use `{"method":"rom-inspect","params":{"path":"/private/game.md"}}`.
The Python API is `fdisbull.roms.inspect_rom(bytes)` or `inspect_rom_path(path)`.

## Implemented profile

| Family | Parsed now | Deliberate limits |
| --- | --- | --- |
| NES | iNES and NES 2.0; trainer, PRG/CHR extents, mapper/submapper, size encodings, RAM declarations and trailing data | Mapper behavior and CPU banks are not inferred; polluted legacy fields remain uncertain |
| SNES | Plausible LoROM, HiROM and ExHiROM header candidates; raw or 512-byte copier prefix; title, map/chip/size/region fields and reset vector | Heuristic detection; ambiguous headers stay unresolved; checksum/complement consistency is not a whole-ROM checksum; ExLoROM, interleaving and special chip mappings are not established |
| Genesis / Mega Drive | Raw big-endian cartridge header, titles/product/region, declared ranges, reset/SP vector plausibility and available checksum range | Byte-swapped and SMD signatures are recognized as unsupported; bytes are not transformed |
| Sega 32X | Header variant recognition within the Genesis profile | SH-2 programs and multi-CPU mapping are not parsed |
| Master System / Game Gear | `TMR SEGA` at standard header offsets; product/version, region, size and stored checksum | Mapper behavior and checksum verification remain open; unknown/malformed fields are flagged |
| Sega CD / Mega-CD | Sector-zero system identifier and selected software information | Cooked 2048 or raw Mode 1/2352 data track; no CUE/multisession/audio/security processing |
| Sega Saturn | Sector-zero system descriptor: title, product, version, date, region, peripherals and declared IP size | Same framing limits; no SH-2 code loading |
| ISO 9660 on these Sega tracks | A primary volume descriptor at sector 16, dual-endian size checks, volume label and bounded root extent | This is a single-descriptor probe; a boot record at sector 16, later primary descriptors, directory traversal and file extraction require a fuller reader |

`valid` describes the structures checked by that parser and its stated profile.
It is not an authenticity, bootability or gameplay result. Checksums are
reported separately. SNES sizes are rounded capacities: a 1.5 MiB file with a
2 MiB size code is retained with an uncertainty warning, since size alone does
not distinguish a legitimate non-power-of-two image from truncation. Conservative
SNES detection can miss unusual titles or trivial checksum pairs.

Reports use `fdisbull-rom-inspection-1` in `report_format`; `format` names the
detected media. `regions` contain original `file_offset` and `file_size`, never
guessed virtual addresses. Ordinary `inspect` exposes them in `rom_regions`
and leaves native sections/imports/exports empty. Strings retain file offsets
with no guessed CPU addresses.

Complete supplied bytes receive `source_sha256`. A disc path report instead
sets that field to null and hashes each sampled region; its `hash_scope`
explicitly says that whole-file identity was not established. Bind an intake's
independently verified full-file hash to that report when identifying a target.

## Civilization pilot

The local download and existing intake contain the Japanese **Sega Saturn**
edition. This is distinct from the commercial SNES edition and the unofficial
Genesis project CivGen. The intake's original Track 1 was read from the local
archive into a private analysis copy and verified against its recorded identity:

- Track size: **83,660,640 bytes**, raw Mode 1/2352.
- Track SHA-256: `4556de31764a900831cd213e117c351d4e2a540b0fc9fcec3bc3aeafea8c3dc0`.
- Header: title `CIVILIZATION`, product `T-2003G`, version `V1.003`, date
  `19970325`, region `J`, declared IP size 6,144 bytes.
- ISO volume: `CIVILIZATION`; root directory LBA 20, size 2,048 bytes.
- Available data track: **35,570 sectors**; declared volume: **36,320 sectors**.

The system descriptor is structurally present, while the checked volume extent
does not fit the supplied data track. The report therefore has
`descriptor_valid=true` and `valid=false`. This independently reproduces the
prior intake discrepancy. It does not establish that a particular file is
incomplete or that the game cannot boot. The audio track was not interpreted.
No original media, extracted executable, raw prefix or game bytes are committed.
The private CLI report SHA-256 is
`cb19495a68aee6737fd4b28067628c385ee3c6a04381399bde65305f04d3eb49`.
The CLI sampled 6,448 bytes; the full-track hash above was independently checked
while creating the private analysis copy from the intake source archive.

DOS and Windows intakes can now be compared with this console intake at the
container identity and metadata level. Their internal file formats, graphics,
rules and code correspondence remain separate questions.

## Next parsing priorities

| Priority | Formats | Minimum useful parsing outcome |
| --- | --- | --- |
| 1 | CUE/BIN and cooked ISO; full bounded ISO 9660 | Explicit tracks, sector framing, descriptor sequence, file paths/extents, available bytes and safe extraction budgets; supports Saturn, Sega CD and PS1 carriers |
| 1 | Game Boy / Game Boy Color, GBA | Header fields, declared ROM/RAM, cartridge controller, header checksums, logo/signature evidence, original offsets |
| 2 | N64 `.z64/.v64/.n64`, Nintendo DS | Explicit byte order and transformations, header fields, program/data extents and integrity checks |
| 2 | CHD, GDI, CCD/IMG/SUB, MDS/MDF | Backed track reader with parent/decompression limits and transformation provenance; no extension-only platform guesses |
| 2 | PS-X EXE, DOL and other console executable containers | Section/extents and declared entry metadata, with CPU analysis capability reported separately |
| 2 | Amiga ADF/OFS/FFS, Atari ST/MSA/FAT12, Mac HFS and resource forks, IMD/TD0, C64 D64/PRG | Bring existing private intake knowledge into reusable bounded carrier parsers; retain forks, sector errors and unavailable members |
| 3 | WAD, PAK, GRP and game resource archives; AGI/SCI/SCUMM families | Member/index inventories, offsets, resource types, compression budgets and safe paths before interpreting game-specific content |
| 3 | Godot PCK, Unity bundles/serialized files, Unreal packages and other engine formats | Versioned container metadata and member inventories; capability-specific readers rather than generic file-extension claims |

These rows are a researched work order, not implemented support. Each reader
should retain the same source identity, offset and explicit-unknown rules and
be qualified with malformed fixtures plus an independently identified real
target before claiming that format.

## Verification

Authored cartridge, malformed-header, public API, CLI, sparse large-disc and
existing inspection checks passed locally: **35 passed, 1 deselected**. The
deselected compiler fixture expects Linux ELF output from `gcc`; this macOS
host produces Mach-O. The full run with local Z3 completed with **2,096 passed,
126 skipped, 12 failed and 23 errors**. The remaining failures are Linux ELF
fixture builds on macOS and managed-code tests without optional dependencies;
the full local suite is not a green gate. Independent review checked the raw
sector framing, original offsets, sampled hashes and explicit parsing limits.

References: [NES/iNES](https://www.nesdev.org/wiki/INES),
[NES 2.0](https://www.nesdev.org/wiki/NES_2.0),
[SNES headers](https://snes.nesdev.org/wiki/ROM_header),
[Sega magic definitions](https://github.com/file/file/blob/master/magic/Magdir/console),
[Saturn system-ID tool](https://github.com/SaturnSDK/Saturn-SDK-Tool-IPMaker),
[ECMA-119](https://ecma-international.org/publications-and-standards/standards/ecma-119/),
[Pan Docs](https://gbdev.io/pandocs/), [GBATEK](https://mgba-emu.github.io/gbatek/),
[MAME CHD tools](https://github.com/mamedev/mame/blob/master/docs/source/tools/chdman.rst).
