# CUE/BIN and ISO parsing

`disc-inspect` reads a supported CUE layout or a single Mode 1 BIN/ISO and
inventories the primary ISO 9660 directory tree. It is read-only: it does not
extract files, decode audio, launch an emulator or analyze console instructions.

```sh
fdisbull disc-inspect /private/disc.cue
fdisbull disc-inspect /private/data-track.bin
fdisbull disc-inspect /private/disc.iso --max-entries 10000
```

The Python entry point is `fdisbull.disc.inspect_disc_path(path)`. JSON uses
`{"method":"disc-inspect","params":{"path":"/private/disc.cue"}}`.
`rom-inspect` also accepts a CUE path. A bare image's raw Mode 1 sync/header
selects 2352-byte sectors; otherwise the reader attempts cooked 2048-byte
sectors. `--mode MODE1/2048` or `--mode MODE1/2352` selects one explicitly.
The subsequent descriptor parsing establishes whether ISO metadata is present.
The normal output-budget and artifact retrieval interface applies to large
inventories.

## Track layout and provenance

The supported CUE profile has BINARY files, AUDIO, MODE1/2352 and MODE1/2048
tracks, INDEX 00/01 and generated PREGAP/POSTGAP. Stored INDEX 00 pregaps consume
file sectors. Generated gaps consume timeline sectors without corresponding
file bytes. Shared files require a uniform physical sector size and nonoverlapping
track ranges. Sectors before a file's first declared index are refused rather
than silently discarded. Timelines use half-open, zero-based accounting for
the supplied tracks and generated gaps; no physical lead-in or subchannel TOC is inferred.

CUE references must resolve to regular files inside the CUE directory. Absolute,
parent, drive/UNC, ambiguous backslash and escaping symlink references are
refused. File identity captured during layout inspection is checked again when
opening each data track and after reading. The parser records ignored metadata
directives and refuses unsupported structural directives, track modes and
layouts. WAV/MP3 audio, MODE2, compressed images, extra indices, FLAGS and
multisession extensions need separate qualification.

The sector reader validates sync and Mode 1 for every raw sector it reads,
removes the 16-byte framing header and returns exactly 2048 user bytes. It
checks read bounds and budgets before reading. EDC/ECC and subchannel data are
not verified. Extents retain a physical sector offset, physical sector size,
user-data offset and logical byte length; a raw-sector file is never reported
as a contiguous byte range of decoded contents. No CPU address is inferred.
Hashes cover sampled physical sectors only. Whole-track hashes belong to an
independently verified intake receipt.

## ISO profile and limits

The reader scans at most 64 volume descriptors beginning at LBA 16, permitting
a primary descriptor after a boot record. It validates both-endian integers,
2048-byte logical blocks, single-volume fields, the root record, per-sector
directory records, self/parent links, paths, record extents and directory cycles.
It inventories nested primary-tree paths while preserving versions such as
`;1`. It rejects reserved-area or directory overlaps, malformed names and
records, interleaving, extended-attribute extents and multi-extent files. File
aliases/overlaps are advisory; supplementary/Joliet descriptors and nonzero
system-use data are explicitly uninterpreted.

Defaults per data track are 10,000 entries, 8 MiB of declared directory bytes,
depth 32, and 16 MiB/8,192 physical-sector reads. Limits have hard caps.
Missing metadata or a budget stop leaves traversal incomplete and validity
unknown; an invalid or unsupported structure is reported as such.

`complete` refers to the supported primary metadata traversal. File
`available` means its numeric extent fits the supplied data-track range;
`content_verified=false` records that normal inspection does not read file
contents. `volume_extent_fits` separately compares the PVD's declared size with
the data track. Audio sectors are never used to enlarge that filesystem bound.
The outer disc report can therefore have `complete=true`,
`primary_metadata_valid=true`, `all_entry_extents_available=true` and
`valid=false` when the declared volume is larger than the supplied data track.
It is not a whole-image integrity certificate.

## Civilization Saturn result

The original 317-byte CUE in the local intake describes two separate BINARY
files. Track 1 has INDEX 01 at 00:00:00. Track 2 has INDEX 00 at 00:00:00 and
INDEX 01 at 00:02:00; it has no generated PREGAP directive.

| Track | Stored sectors | Stored pregap | Program sectors | Stored timeline |
| --- | ---: | ---: | ---: | --- |
| 1, MODE1/2352 | 35,570 | 0 | 35,570 | `[0, 35570)` |
| 2, AUDIO | 750 | 150 | 600 | `[35570, 36320)` |

Track 2's program begins at timeline sector 35,720. Its 1,764,000 bytes are
exactly 750 raw sectors: 150 sectors of stored pregap and 600 sectors of audio
program. There are no generated gaps. Thus **35,570 + 750 = 36,320**, exactly
the PVD volume-space count. The audio track fully accounts for the numerical
difference. This does not establish the mastering tool's intent or change the
meaning of ISO's volume-space field; the filesystem still uses only Track 1.

The new reader traversed **300 files and one subdirectory**, with every file
extent inside Track 1. The highest file extent ends at LBA **35,420**, below
the track's end at 35,570. The normal metadata inspection read only **11 raw
sectors / 25,872 bytes**. A separate private verification then read each file
through the same validated sector reader and compared it with the pre-existing
intake inventory: **300/300 file sizes and SHA-256 hashes matched**. This
includes the 867,988-byte `CIV.BIN` at LBA 28, SHA-256
`53d23f5e878ad86938aeca2e0701549870b1cbc4f080a6ddb8f49041ea382ebd`.

The independently checked source-track hashes are:

- Track 1: `4556de31764a900831cd213e117c351d4e2a540b0fc9fcec3bc3aeafea8c3dc0`.
- Track 2: `20b149d292750604557b1f1b6c55ef77d4e94694d63775d0f76032efc7c78695`.
- CUE: `7fc9ae1b6d4df1e524d12820ee72e1d838a76cb2c7dc6eb71f4885415c3c7fec`.

This resolves the earlier [descriptor-only pilot](CONSOLE_MEDIA_PARSING.md#civilization-pilot)
at the track-accounting and retained-file boundary. No inventoried file loss
was observed. Playback, physical-disc authenticity, audio correctness and game
execution remain untested. Original files and private verification outputs
stay outside Git and the package.

## Verification

Authored shared/separate-file CUE layouts, stored/generated gaps, path refusal,
raw framing, cooked ISO, nested directories, malformed records, extent bounds,
budget stops, source replacement and existing inspection checks passed locally:
**61 passed, 1 deselected**. The deselected compiler fixture expects Linux ELF
output; this macOS host emits Mach-O. The full suite with local Z3 reported
**2,122 passed, 126 skipped, 12 failed and 23 errors**, in the same Linux ELF
fixture and missing optional managed-dependency groups as the earlier run.
This is not a green full-suite gate. Independent review checked track accounting,
raw-sector backing offsets, identity binding and the stated completion scope.
The private CLI report SHA-256 is
`404c9d4f08cc70173bfed16a6161a7826310423d56114134fec764e36a35b4e1`.

References: [CUE format working specification](https://github.com/libyal/libodraw/blob/main/documentation/CUE%20sheet%20format.asciidoc),
[cdrdao's TOC-to-CUE conversion](https://github.com/cdrdao/cdrdao/blob/master/utils/toc2cue.cc),
[ECMA-119](https://ecma-international.org/publications-and-standards/standards/ecma-119/).
