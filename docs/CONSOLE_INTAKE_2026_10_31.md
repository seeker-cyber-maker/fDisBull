# Console ROM intake — 2026-10-31

Four supplied ZIP archives were copied byte-for-byte into the private fDisBull target package, then their cartridge members were extracted byte-for-byte into separate target families. The intake contains **14 cartridge payloads** totaling **23,805,984 bytes** (see the hash-bound inventory for exact totals), with no duplicate payload hashes across the four archives. The source ZIPs remain in the user's Downloads folder and were rechecked against the private copies after extraction.

The supplied names are retained as labels, not treated as proof of game identity, region, revision, publisher, or dump quality. The two Shadowrun-labelled archives are deliberately registered as separate SNES and Genesis target families. No source bytes were bound to an FDB, no cartridge was run, and no compatibility or gameplay claim is made. The parser's `structurally_valid` field describes only its bounded header/extent checks; all parser results have `loadable: false`.

## Intake summary

| Supplied archive label | Members | Observed format facts | Scope and qualification |
| --- | ---: | --- | --- |
| `Shadowrun.zip` | 1 | 1 MiB; plausible SNES LoROM header at file offset `0x7FC0`, title field `SHADOWRUN`, reset vector `0xE34C` | Complement/header-checksum pair is plausible. The full ROM checksum was not computed, and the header is not proof of CPU-to-file mapping or execution. Kept separate from the Genesis Shadowrun family. |
| `Shadowrun_Genesis_EN.zip` | 11 | Ten files are 2 MiB and have a `SEGA` Genesis header with a fully present declared extent; one file is 1,179,648 bytes while its header declares a 2 MiB extent | Five complete files' computed Genesis checksums match their header values; five do not. The incomplete member's checksum could not be computed. One otherwise complete file also has an inverted declared address range. No mismatch was repaired. All 11 are retained in one Genesis-labelled variant family, with the incomplete member excluded from the private program archive. |
| `1200-in-1 (J) [p1].zip` | 1 | 524,304 bytes; iNES header declares mapper 227, 512 KiB PRG-ROM and no CHR-ROM | Header extents match the file size. The label does not verify the count or identity of games, mapper behavior, menu behavior, or execution. Sent to the separate display qualification analysis. |
| `Super Mario Bros. _ Duck Hunt.zip` | 1 | 81,936 bytes; iNES header declares mapper 66, 64 KiB PRG-ROM and 16 KiB CHR-ROM | Header extents match the file size. This remains a separate comparator target. |

The archive SHA-256 values, each member SHA-256 and ZIP CRC32, exact parser facts and warnings, target family IDs, and private registry receipt are recorded in [`intake.json`](evidence/console-intake-2026-10-31/intake.json). The private receipt's digest is included there without exposing local source paths.

## Registry and handling

The private target package now contains four target families and 14 staged payloads. All payload hashes are distinct. Thirteen complete cartridge images were added to its private executable registry; the earlier 185 program records remain byte-identical. The private archive's membership/CRC/hash check passed. The one incomplete Genesis member remains preserved in its target folder and provenance inventory but is not selected as a complete cartridge program.

The original ZIPs, extracted cartridge bytes, and analysis databases remain outside the repository and Python distribution. Only this sanitized text record and the JSON inventory are in the source tree. Hash equality establishes byte identity only. Publisher authenticity, licensing, dump provenance, emulator behavior, CPU mapping, and target compatibility remain unknown or unqualified.
