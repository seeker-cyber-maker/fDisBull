# Installer layers, image automation and generic DOS capture

## Two deliberately different operations

`fdisbull-unpack` inspects/extracts supported data layers **without executing a
program**. `fdisbull-installer-probe` explicitly runs one DOS target in an owned
headless DOSBox session, exposing only copies of selected files through a
throwaway C drive. These are installed entry points; `python -m fdisbull.unpack`
and `python -m fdisbull.installer_probe` are equivalent. They do not silently
replace existing `fdisbull request` methods.

The generic capture method does not depend on a packer signature. It compares
actually fetched instruction bytes with the initial conventional-memory image,
records changed-code candidates, and can capture at an explicit load-relative
boundary. A relocated unpacker, runtime-generated code and a real unpacked entry
can all change code. Consequently **a candidate is not automatically an OEP**,
and a memory dump is not an unrelocated or runnable EXE. Relocation/import/header
reconstruction for arbitrary packers is not implemented. EXEPACK has its own
bounded static profile and relocation reconstruction.

## Static workflow

```sh
fdisbull-unpack catalog
fdisbull-unpack inspect /private/GAME.GOG
fdisbull-unpack extract /private/setup.exe /private/new-intake --recursive
fdisbull-unpack extract /private/AVATAR.EXE /private/new-analysis --provider exepack
```

Automatic admitted layers:

* Native Inno reader already installed in fDisBull; no external innoextract.
  Supported Inno versions remain that reader's contract, not a new blanket claim.
* Stored/deflated ZIP, independently validated concatenated ZIPs, and SFX ZIPs.
  ZIP64, encryption and spanning are explicit refusals. A valid ZIP nested inside
  a stored member is not misidentified as a concatenated sibling.
* CUE/INS companions and Mode-1 2048/2352 sector images with a complete primary
  ISO9660 tree. Same-stem GOG/BIN companions resolve explicitly; ambiguity refuses.
  A PVD following a boot descriptor is recognized. ISO version suffixes are
  normalized for output, while original paths and physical track identity remain.
* Classic EXEPACK 16/18-byte headers with the admitted skip convention, including
  Ultima IV's verified 35-byte outer entry wrapper. Unsupported variants refuse.

Each source has a hash and each extracted file has a parent-layer edge, source
member identity, size and hash. Segments are not flattened over each other.
Depth, input, member, aggregate-output, file-count and cooperative-time bounds
apply. Paths are checked before writing; case collisions, Windows devices,
links, traversal and file/directory conflicts refuse. Output must be new. Failure
removes only the directory created by the operation. Originals are never deleted.

`complete` concerns admitted layer traversal, not preservation or game readiness.
Opaque executables and unsupported formats keep it false. An EXEPACK result has
`image.bin` and an **analysis-only** reconstructed MZ. The output is never launched.

## Images are not ordinary archives

A .GOG suffix is not a codec. This Dragonsphere `GAME.INS` describes `GAME.GOG`
as a single MODE1/2352 binary track. Data-sector framing and the ISO filesystem
are separate layers. Extracting files is a derived analysis subset, not a copy
of a complete disc. Selected data tracks, unselected/audio tracks, descriptor
hashes and omissions remain in the report. EDC/ECC and audio playback are not
qualified. Multiple data tracks require `--track`; audio cannot be selected as
an ISO filesystem. No host mounts or target-provided DOSBox configurations run.

NRG, MDF/MDS, CCD/IMG/SUB, VCD/VC4, UDF and Mode-2 variants are **not implemented**
by this change. Recognized unsupported filename families cannot silently fall
through to a cooked-ISO guess. Existing floppy readers should connect through
the explicit trusted `Provider` interface, not be duplicated here. A plugin is
installed trusted Python code with `inspect` and bounded `read` callbacks; it is
not discovered or loaded from input content. This contribution supplies no native
floppy plugin or automatic external converter. New providers need their own
representative corpus and loss/companion contracts.

## Native installer observation

```sh
fdisbull-installer-probe /private/INSTALL.EXE /private/new-probe \
  --executable /tools/dosbox-x --max-fetches 50000 --timeout-seconds 30

fdisbull-installer-probe /private/AVATAR.EXE /private/new-capture \
  --executable /tools/dosbox-x --stop-offset 0xe94a \
  --max-fetches 200000 --timeout-seconds 25
```

Use `--companion /private/MPSLABS.IDX` to admit an additional copied file and
`--arguments '["-s"]'` for explicit DOS arguments. No shell is used. File names
must be DOS 8.3. `--fast-forward` is an explicit timing change, not the default.
The load-relative stop is a caller-selected boundary, not inferred proof of an
original entry. The trace is before instruction execution. A service result is
recorded only when its caller's successor address is subsequently fetched.
Unresolved interrupts and port fetches remain unresolved/fetch-only.

The classifier identifies DOS version/drive/free-space/device/memory/file and
child-launch requests, BIOS equipment/memory/video/disk interfaces, mouse, EMS,
MSCDEX/XMS multiplex calls and ordinary 8/16-bit IN/OUT instructions. Raw input
and observed-return registers are retained. It does **not** exhaustively cover
BDA/ROM memory reads, prefixed/wide port access, far-call driver interfaces,
network activity or unreached branches. A string naming a device is not proof
of a probe. Emulated hardware results are not host hardware inventory, and the
probe is not a privacy/telemetry clearance tool.

The owned process is reaped on normal completion and handled failures; uncertain
RPCs are never replayed. A cooperative/transport deadline produces `incomplete`,
not a successful unpack. Captures, input files, raw traces and saves are private.
DOSBox is not a host-security sandbox for deliberately hostile executable code;
use an additional isolation boundary for such targets.

## Fresh target evidence, 7 November 2026

The owner's Dragonsphere GOG installer was extracted recursively through Inno,
GAME.INS/GAME.GOG, ISO9660 and all three MPSLABS.001 ZIPs. The fresh run wrote
256 derived files / 168,694,179 bytes; opaque executable leaves remain reported.
All 44 ZIP outputs match GOG's installed DRAGON copies byte-for-byte:

| Group | Offset | Archive bytes | Files | Content grouping |
| --- | ---: | ---: | ---: | --- |
| 0 | 0 | 314345 | 38 | Batch launcher, indexes and sound drivers |
| 1 | 314345 | 402526 | 3 | SPHERE, MAINMENU, ANIMVIEW executables |
| 2 | 716871 | 54349 | 3 | TEXTVIEW, DRAGON.RES, DIGITAL.AGA |

The companion IDX begins with 0xffff, 44 and 3. Its 4,636 bytes fit a 30-byte
header plus 47 records of 98 bytes. The last three records name MPS!000.WAD,
MPS!001.WAD and MPS!002.WAD; their offsets and lengths exactly match the ZIP
boundaries. WAD here is a label, not evidence of the Doom WAD format. This
supports archive grouping, not a three-floppy history. MAME catalogs a distinct
Dragonsphere Version 2.0C release on **seven** 1.44 MB disks. We did not compare
that physical release with the supplied CD; mastering lineage remains unknown.

A fresh 50,000-fetch INSTALL.EXE run observed DOS-version, default-drive,
character-device IOCTL, video-state, mouse reset and EMS calls with observed
returns. It did not establish sound-card detection, a complete installation,
all hardware checks or host-machine information gathering. MPSCOPY's first
300,000 fetches expose changed-code in two relocated arena pages, not a proven
original entry. A longer capped run reached its deadline and is explicitly
incomplete, with child cleanup recorded.

For AVATAR.EXE, the original unpacker was stopped at relative 0000:E94A after
26,221 fetch records. The static 98,832-byte image, after applying its three
relocations for the observed load segment, matches all captured runtime bytes.
That qualifies this unpacking boundary, not subsequent gameplay or execution of
the reconstructed analysis MZ.

## Verification and provenance

Tests use authored archives, ISO fixtures, malformed cases and real authored
COM execution when an explicitly selected agent is supplied. Native-required
cases must not be reported passed when skipped. The source tree used here is
the uploaded c80 snapshot with the relevant newer Inno provider and the narrow
new changes; it is not a full current-release checkout. Shared CUE and build
metadata preimages were checked against release/0.33.0. Exact combined-tree,
macOS and full release qualification remain integration gates.

The EXEPACK format and Ultima wrapper were source-assisted by the prior xu4
investigation. Record that provenance and review distribution compatibility;
no clean-room or legal-clearance claim is made. No third-party implementation
or game payload is bundled in this contribution.

References (primary format/implementation references, not runtime evidence):

- PKWARE ZIP specification: https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT
- EXEPACK implementation/format study: https://www.bamsoftware.com/software/exepack/
- Ultima wrapper reference: https://github.com/xu4-engine/u4/blob/master/src/util/u4unpackexe.c
- MAME disk catalog: https://github.com/mamedev/mame/blob/master/hash/ibm5170.xml (drgsphere)
- RBIL DOS version: https://fd.lod.bz/rbil/interrup/dos_kernel/2130.html
- RBIL mouse status: https://fd.lod.bz/rbil/interrup/io_mouse/330000.html
