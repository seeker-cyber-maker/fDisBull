# File identification and format modules

`file-identify` answers what a supplied file's headers establish, which
architecture or container views are available, and which implemented format
modules can inspect it further. It does not execute the input. The older
`identify` command and `identify_header` API retain their existing contracts.

The Python entry points are:

```python
from fdisbull.format_registry import identify_file, format_catalog

report = identify_file("/private/input", catalog_path="/private/formats.sqlite")
catalog = format_catalog(catalog_path="/private/formats.sqlite")
```

The catalog path is optional. Omitting it uses an in-memory SQLite database;
the tool creates no global home-directory cache. An explicit path must have an
existing parent and be a dedicated format catalog, separate from the input or
an existing project database. Source symlinks are accepted through a regular
opened descriptor. Catalog symlinks, special source files and changing inputs
are refused.

## Evidence and support

Each identification reports `recognized`, `status`, `header_valid`, a named
`validation_scope`, architecture, header facts, linked modules, and limitations.
The important distinctions are:

- `unknown`: no supported header was established. A suffix is never proof.
  Signatureless DOS COM files require explicit selection through the existing
  COM loader; this identifier does not guess that arbitrary bytes are x86 code.
- `recognized-header`: the reported header and stated bounded checks passed.
  It does not mean a codec payload is decodable or a program is executable.
- `recognized-invalid`: a known signature was found but its required header or
  declared extents failed the implemented checks.
- `recognized-unsupported-size`: a native signature was found beyond the full
  native-reader budget. Full image views are not fabricated from a prefix.
- `recognized-unsupported-layout` / `recognized-header-limit`: a known image
  container has an unsupported header variant or its geometry was not reached
  within the bounded marker walk. Unknown geometry stays unknown.

`full_decode` and `native_runtime_tested` are false: identification does neither.
The linked module's capabilities identify the next implemented operation. A
module which only recognizes a header is still a useful reader, but is not a
complete video decoder. A database-provided API string is descriptive text;
the tool never imports or evaluates it. Only current, statically shipped module
records receive `binding_verified: true`. Future/custom rows are preserved and
their implementation claims remain unverified.

## Current coverage

Native executable and console identification reuses existing readers:
`inspection.identify_header`, `image_views`, `roms.probe_rom`, and the bounded
ISO primary-volume reader. MZ/PE/LE/NE views retain their independent loadability
and errors. In particular, a valid 16-bit MZ stub does not qualify an unsupported
32-bit LE engine. Universal Mach-O slices retain their explicit architectures.

For a structurally bounded MZ, the report also records the DOS-declared image
end and the trailing byte range. The range remains opaque. A secondary PE/NE/LE
header can explain part of that range; the tool does not turn the entire tail
into a recovered overlay directory or disposable padding.

Additional minimal header readers recognize:

- SMK2/SMK4: geometry, rate, logical/physical frame counts, audio rate flags,
  compressed-tree size and bounded frame-size-table extents. SMK4 recognition
  does not enable the restricted SMK2 framing writer.
- Groovie VDX and RoQ: their actual header markers and initial resource/rate
  facts. No game archive traversal, delta/video or audio decode is implemented
  by this header reader.
- Autodesk FLI/FLC: declared size, frame count, geometry and depth. A custom
  VID file with an FLC signature remains a custom layout until its companions
  and packet semantics are recovered.
- Bullfrog compact FLIC: the source-referenced 12-byte header followed directly
  by a `0xf1fa` frame chunk. This profile has no color-depth field: bytes12–15
  are the first frame's length. The legacy `Size` field is recorded without
  assuming it describes the whole file. Only header facts and the first frame's
  extent are checked; frame/subchunk decoding and complete frame-count validation
  remain unsupported. The catalog pins the packed header and reader source.
- RIFF AVI/WAVE: the form and declared RIFF envelope; stream/index/sample
  validity requires the respective reader. Unknown RIFF forms remain explicit.
- MP3: two consistent MPEG Layer III frame headers, after an optional bounded
  ID3v2 metadata tag. An ID3 marker alone establishes metadata, not MPEG audio.
- ISO9660 in cooked 2048-byte or raw Mode1/2352 sectors: the primary volume
  descriptor at sector16 and bounded root extents, without reading directories
  or file payloads. CD-audio tracks, CUE/TOC and complete filesystem integrity
  are separate operations.
- ZIP: a first local entry, empty/end-directory header or data descriptor.
  No full directory search, ZIP64, CRC, extraction or member-path safety claim.
- PNG/GIF/BMP/JPEG: essential header geometry, with a bounded JPEG marker walk
  and explicit unsupported BMP variants. PNG CRC, image pixels, GIF animation,
  BMP compression and JPEG entropy data are not validated. When installed,
  Pillow's real `Image.open` API is linked as a separate image-reader module;
  identification does not invoke it or claim full decoding.

Files are sampled through bounded reads. Complete native/cartridge bytes are
passed to existing readers only within the caller's `max_binary_bytes` budget
(at most64MiB). The result states whether its SHA-256 covers the entire opened
file or only sampled regions. A large disc's prefix hash must not be presented
as the disc's identity.

## Persistent catalog

Schema version1 uses four metadata-only tables:

| Table | Records |
|---|---|
| `format_catalog_meta` | Supported schema version |
| `format_definitions` | Immutable `(format_id, revision)` descriptions, magic offsets, field types, endianness, limitations and provenance |
| `format_decoder_modules` | Immutable `(module_id, revision)` API/capability descriptions |
| `format_decoder_links` | Versioned format-to-module bindings |

Initialization and reopen are idempotent. Built-in conflicts under the same
identifier and revision fail explicitly; future/custom rows are not overwritten.
SQLite cell/row length limits are installed immediately when the connection is
opened. Before retrieving JSON, the tool checks combined record count, maximum
record bytes and total bytes inside the same transaction as the subsequent
read. Identifier/document types and positive integer revision types are checked
as scalars too: SQLite's INTEGER affinity alone does not exclude large text in
a revision column. Definitions and module records share a 4,096-record / 4 MiB budget, with
64 KiB per record including its identifier. Links have a separate 16,384-row /
4 MiB budget and the same per-row bound. Oversized existing content is refused
without being rewritten, including a conflicting row under a shipped identifier.
Unsupported schema versions and databases belonging to another application are
refused before schema changes. Adding support means implementing a bounded
reader and meaningful tests, adding or revising its descriptive record, linking
the actual module, and documenting its precise limits. Merely adding a signature
or an API name never implements a decoder.

The tool writes shipped descriptive records, not inspected target byte ranges,
source paths, screenshots, movie/audio payloads or per-file analysis. The explicit
`inspected_source_bytes_persisted: false` field reports that tool-written scope.
`contains_file_payloads: false` is reported only when the catalog consists of
exact shipped definitions, modules and bindings. If custom/future records are
present, that field is `null`: their content has not been verified as payload-free.
They are preserved within the metadata bounds and remain inert. JSON identification
results can be attached to a private analysis as evidence under the repository's
ordinary target-storage rules. This separate catalog does not migrate or change
existing FDB schemas.

## Intake integration and observed media

`intake-inventory` uses one qualified catalog snapshot and one bounded probe
kernel across all explicitly supplied game roots. `identify_file` also accepts
`max_read_bytes`; `_Reader` admits each read before issuing it and exceptions
retain already consumed byte accounting. File limits, directory-entry/depth
limits and aggregate read limits have explicit partial outcomes.

The opened descriptor's device/inode/time identity binds observations to the
actual file, separately from a requested or resolved symlink path. Persistent
catalogs must not alias source files or lie within input roots. Complete
enumeration and alias preflight precede catalog seeding; incomplete enumeration
uses an in-memory catalog with an explicit not-written persistence result.

[Media coverage](INTAKE_MEDIA_COVERAGE.md) distinguishes strong IFF/MIDI/VOC/PCX,
MADSPACK and DinoPark headers from 96 observed consumer-context resource cohorts.
The latter have no global magic and only suggest recovery tasks. All custom
context fields remain inert, optional and bounded. A verified module's
`decoder_role` is runtime metadata bound by shipped code, rather than an
implementation claim supplied by the database. It distinguishes available
container/pixel/media readers from recognition-only modules and never means
intake has executed a decoder.

The [FLIC structural reader](INTAKE_MEDIA_COVERAGE.md#fliflc-structural-reader)
adds complete bounded packet/subchunk inventory and explicit TFTD IDX checks.
A speed value matching a frame magic does not select the compact envelope:
Bullfrog compact recognition also requires its qualified AF12/12-byte-size
profile. Header recognition and structural inventory remain separate from
pixel/audio decoding, safe movie edits and original consumer playback.
