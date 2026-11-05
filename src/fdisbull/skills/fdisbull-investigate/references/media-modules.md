# Reusable media modules and missing-tool recovery

Read this guide when a reader/unpacker is missing, an input has unmapped tails,
or a parser must be preserved for another investigator. This is a bounded
capability contract; successful parsing establishes structure, not behavior.

## Contents

- [Classify the next obstacle](#classify-the-next-obstacle)
- [Reuse the shipped modules](#reuse-the-shipped-modules)
- [MZ envelope version 1](#mz-envelope-version-1)
- [AGI v2 resource version 1](#agi-v2-resource-version-1)
- [Sherlock SHI version 1](#sherlock-shi-version-1)
- [Existing readers and decoders](#existing-readers-and-decoders)
- [Extend and qualify a module](#extend-and-qualify-a-module)

## Classify the next obstacle

Record the exact operation, target, available evidence and one of these states
in the investigation ledger (descriptive states, not new database enums):

| State | Action |
| --- | --- |
| Missing original input or permission | Identify the exact absent file/part, identity or denied action. Ask only for that prerequisite; continue independent authorized work. Never reconstruct withheld bytes or bypass a denial. |
| Unsupported format or missing tooling | Discover shipped modules/specifications first. Inspect signatures and available documentation under the information policy. If authorized and evidenced, implement the smallest useful non-executing reader/unpacker, document its supported variant and preserve authored tests for reuse. |
| Incomplete analysis or recovery | Continue the next bounded discriminator: locate the loader, compression stream, overlay index, references or effects. An unpacked executable, source/effect map or recovered semantics is an investigation output unless the task explicitly supplies it as an input. A traversal budget is not proof of impossibility. |
| Environment-only verification gap | Run applicable structural checks and qualify platform-specific execution on the matching host. Report unrun checks separately; do not disable meaningful tests or claim native qualification from parsing. |

Set a scope/work budget and a stopping condition. On exhaustion report partial,
unknown, unsupported or refused explicitly, with the next useful probe. No
obligation to solve every unknown format or implement an entire toolchain is
implied. A tool's absence is a reason to build the bounded adapter when feasible,
not automatically a reason to demand the user's reverse-engineering results.

Select independent binary, notes/source-assisted or documented-results-derived
UDP work before reading outside findings. Preserve the lanes through recovery,
generation and verification. Missing private source/symbols blocks reproducing
that exact implementation, but need not block generating a module from admitted
documented results and validating it against authorized inputs. Mark generated
code as generated; do not call it recovered source. Parsing and field names
alone never establish a semantic contract or equivalence.

## Reuse the shipped modules

Discover installed capabilities without a project or target execution:

```text
fdisbull media-modules
fdisbull media-inspect /private/program --adapter mz-envelope
fdisbull media-extract /private/program /private/new-tail --adapter mz-envelope --member tail --max-payload-bytes 1048576
fdisbull media-inspect /private/PICDIR --adapter agi-v2 --volume-root /private/game --number 0
fdisbull media-extract /private/PICDIR /private/new-resource --adapter agi-v2 --volume-root /private/game --number 0 --member resource
fdisbull media-inspect /private/images.shi --adapter sherlock-shi
fdisbull media-extract /private/images.shi /private/new-images --adapter sherlock-shi --member all
```

Python equivalents are `fdisbull.media.media_modules()`,
`inspect_media(path, adapter=..., volume_root=..., number=...)` and
`extract_media(path, output, adapter=..., member=..., max_output_bytes=...)`.
JSON methods `media-modules`, `media-inspect` and `media-extract` accept the same
parameters, without a project. Adapter selection is explicit: no suffix-based
fallback guesses. The catalog routes GOG and picture work to existing APIs
rather than wrapping or rebuilding those readers.

`fdisbull-media-members-1` inventories adapter/version, input roles/sizes/SHA-256,
and member names/input roles/absolute offsets/sizes/SHA-256. It contains no raw
payload, preview, hex or base64. MZ/AGI extraction adds the selected member's
mapping to fixed output `payload.bin` and `media-manifest.json`; SHI extracts
indexed PNGs and the same manifest name as specified below. The manifest remains
structural-only; it does not supply addresses, source mappings or semantic claims.
For AGI, both directory and volume identities and the resource number are retained.

Sources stay unchanged. `media-extract` requires an existing private parent owned by
the caller (0700), creates an exclusive 0700 destination and 0600 files, refuses
Git/worktree ancestry and symlink output paths, and accepts only listed member
names. Never publish payloads or private originals, including modified game
assets. Reports contain hashes and sizes only, but still review provenance before
publication. No new FDB writes are made: parser output does not bypass the
external-target storage boundary or grant permission to bind/import bytes.

MZ/AGI adapters cap each source volume/container at 64 MiB; the SHI profile
requires exactly 23,920 bytes. `max_output_bytes` limits the selected payload
(SHI: sum of PNG file bytes, excluding the manifest) to 1..64 MiB before creating
output (default 64 MiB).
The CLI uses `--max-payload-bytes` for this limit. The global
`--max-output-bytes` before the command controls the JSON reply budget instead;
it never changes the extracted payload limit.
These adapters perform no decompression and have fixed/small member counts.
Filesystem operations assume the caller controls the private parent; this is
not a sandbox against a hostile concurrent process running as the same user.

## MZ envelope version 1

Provenance: this adapter reuses the repository's canonical `dos.load_mz`
validator at DOS load segment 0x10. Its contract is the implemented classic MZ
subset, exercised with independently authored envelopes; it is not evidence
that any particular packed game or overlay format has been recovered.

All fixed fields are unsigned little-endian 16-bit words. Signature bytes at
0 are `4d 5a`; offset 2 is `e_cblp`, 4 `e_cp`, 6 relocation count,
8 header size in paragraphs, 10 minimum and 12 maximum allocation,
14 SS, 16 SP, 18 checksum, 20 IP, 22 CS, 24 relocation table offset,
26 overlay number. The fixed header is 28 bytes. Checksum is retained by the
underlying loader but not used as an authenticity check.

Declared image end = `e_cp * 512` when `e_cblp == 0`; otherwise
`(e_cp - 1) * 512 + e_cblp`. Require nonzero page count, last-page count
0..511, end within the source, and a paragraph header covering the fixed header
while leaving a nonempty module. Relocation records are little-endian
`offset:u16, segment:u16`; the table must fit inside the header and each target
`segment * 16 + offset` must cover a full module word. Canonical loader
allocation, entry/stack and 1 MiB/no-A20-wrap checks also apply. Recognized
PE/NE/LE/LX secondary headers are refused by the canonical loader; malformed
inputs are errors, not fallback COM images. No packer signature is interpreted.

Members are exactly `header = [0, header_size)`,
`module = [header_size, declared_end)`, and optional
`tail = [declared_end, source_size)`. A member copies ORIGINAL file bytes;
relocation validation does not substitute relocated memory in the output.
Tail offsets refer to the whole original container. No tail exists at EOF.

The tail is opaque: it may be overlays, resources, debug information or another
format. Neither `e_ovno` nor a tail hash proves overlay membership. There is no
LZEXE/EXEPACK/PKLITE/CIV_UNP decoder, chained-overlay parser or city-production
mapping in this adapter. Packed programs outside the canonical loader subset
are refused; continue a separately bounded packer/overlay investigation.

## AGI v2 resource version 1

Provenance: reuse `agi_picture.extract_v2_resource` with whole-input hashes,
bounded reads and before/after identity checks. The upstream format reference
used by the existing decoder is `peterkelly.github.io/agi-re/spec/`.
This adapter is for uncompressed v2 resources; it does not infer their type.

The directory has no magic: it is at most 768 bytes and its length is divisible
by three. Resource `n` (0..255) selects the triple at `3*n`.
`ff ff ff` means absent. For bytes `a,b,c`, the volume is `a >> 4` and
absolute volume offset is `((a & 15) << 16) | (b << 8) | c` (big-endian
20-bit packed address). Exactly one case-insensitive `VOL.<volume>` must exist.

At that offset the five-byte header is `12 34`, one volume byte matching the
directory, then unsigned LITTLE-endian payload length. The complete payload
must fit in the selected volume. `resource` begins at header offset + 5 and
has the declared length (0..65535); empty resources are structurally permitted.
No header bytes enter the emitted payload. AGI v3 combined directories,
compressed headers, LZW and alternate codecs are unsupported; the caller must
select the v2 variant from evidence rather than treat acceptance as detection.

## Sherlock SHI version 1

Adapter `sherlock-shi` implements only the observed Sherlock 1.50 profile,
`sherlock-1.50-46x32x32`. Its independently authored codec follows the recovered
structure of four privately supplied image sets. The record roles, palette and
indexed overlay operation were separately qualified against this game's
rendering; they are not fields embedded in SHI. Repository tests contain only
authored planar vectors. Original images and captures are not distributed.

The file has exactly 46 records of 520 bytes (23,920 bytes total), with no
file-level header, directory, compression, trailer or variable-length records.
Image IDs are the stable zero-based record numbers 0..45. Every record starts
with four little-endian 16-bit words `[4, 1, 32, 32]`; all eight header bytes
must match. The first two words are fixed profile markers whose broader field
semantics remain unqualified. The admitted dimensions are always 32 by 32.
Reject every other header or size, including a valid prefix with trailing bytes.

For image `i`, the record offset is `520*i`, and its 512-byte pixel payload starts
at `520*i + 8`. Each of 32 rows holds four consecutive planes of four bytes
each. Within a plane, the first pixel is the high bit; plane 0 is the low color
bit. For `x,y` in 0..31, relative to the start of this record's payload:

```text
index(x,y) = sum(((payload[16*y + 4*p + x//8] >> (7 - x%8)) & 1) << p
                 for p in 0..3)
```

`fdisbull.shi.decode_shi(payload)` accepts bytes, bytearray or memoryview with
the exact file size, validates every record, and returns a tuple of 46 immutable
1024-byte images: row-major pixels, one index 0..15 per byte. It never returns a
partially decoded prefix. `encode_shi(images)` accepts a list/tuple of exactly
46 such bytes-like images, rejects every wrong size or index above 15, and
returns the exact planar encoding with fixed headers. It does not quantize RGB
artwork, change inputs or write files. Encoding a complete decoded supported
file reproduces its original bytes.

| Image IDs | Qualified role |
| --- | --- |
| 0..35 | Game items: category row `id//6`, item `id%6`; this is not a solution column |
| 36 | Empty tile |
| 37 / 38 | NOT mask / ink |
| 39 / 40 | BETWEEN-left mask / ink |
| 41 / 42 | BETWEEN-middle mask / ink |
| 43 / 44 | BETWEEN-right mask / ink |
| 45 | Three-dot LEFT_OF separator |

Marker composition is `(destination & mask) | ink` on four-bit palette indices.
Do not replace it with PNG alpha compositing. The profile's 16 RGB triples are
available in `fdisbull.shi.PALETTE` and the manifest's `palette.colors`; the
manifest explicitly records `embedded: false` and their game-profile source.
Color values are not inferred from the image data or from a generic EGA palette.
The qualified 16x16 candidate reduction samples source coordinate `(2*x, 2*y)`
without interpolation. Extraction preserves the original 32x32 indices and does
not perform this reduction or combine mask/ink pairs.

`media-inspect` returns all 46 source members named `image-00` through `image-45`.
Each member retains its record offset/size/SHA-256, absolute payload offset/size,
stable `image_id`, dimensions, decoded pixel SHA-256 and role. Decoded pixels are
not included in JSON. The ordinary top-level input identity is the whole SHI
file. The declared palette, mask/ink pair IDs and half-size sampling are profile
metadata; `qualification` remains `structural-only` for the supplied file.

`media-extract --member image-37` exports just `image-37.png`; `--member all`
exports all 46 records. The latter selector is advertised by `extract_all_member`.
Every PNG uses four-bit indexed color, preserves index order and contains no
transparency. The manifest's `extracted.images` maps each PNG path/size/SHA-256
back to a `source_member` and `image_id`; the retained `members` list supplies
source offsets and decoded hashes. PNG encoding hashes may depend on Pillow/zlib
versions; decoded index hashes provide the stable pixel identity. The complete
PNG set is prepared and its summed byte budget checked before output creation.
All existing private-path, exclusive-directory and 0600-file rules still apply.
SHI rejects AGI-only `volume_root` and `number` parameters. Parsing does not
detect another SHI edition, prove a file's provenance, or qualify game behavior.

## Existing readers and decoders

- `gog-inno`: `fdisbull.gog_unpack.list_gog/unpack_gog`, or `gog-list/gog-unpack`.
  Requires native `innoextract`; versions/filters/part hashes and output hashes
  are retained by its existing manifest. Multipart parts are provenance candidates,
  not per-part consumption proof. Installer code is never launched. Native
  reader support, filesystem inventory checks and per-process timeout apply;
  this module does not provide a hard decompression byte quota. Use its existing
  listing/extraction contract; do not mistake it for a general disk reader.
- `agi-picture`: `fdisbull.agi_picture.decode_picture(payload)` accepts prepared
  AGI 2.915/2.917 EGA streams, with 160x168 visual/priority planes, 2 MiB input
  and 20 million work-unit limits. Commands F0..FA control colors, planes, lines,
  fills and brushes; FF terminates. See the implementation's cited picture-resource
  specification for the full opcode/brush rules. Decoder success is not evidence
  of runtime walkability or original interpreter reachability.

Keep archive/disk extraction, executable unpacking/overlay recovery, asset
codecs, ISA loading and semantic analysis separate. Existing `dos.load_mz`,
`agi.inspect_logic` and project loaders serve their own layers, not universal
media recovery. Catalog entries describe real APIs, not promised format coverage.

## Extend and qualify a module

Before building, check `media-modules`, the indexed specifications and permitted
upstream implementations. Record the missing variant and why existing readers
are insufficient. Recover enough structure from authorized evidence to write a
small bounded parser; preserve unknown fields rather than invent their meaning.

Ship the adapter in `src/fdisbull`, wire the normal Python/CLI/JSON seams, add a
catalog entry, and extend the packaged specification/index and distribution gates.
Document signatures/versions, fields/offset bases/endianness, counts/alignment,
codec/compression and termination rules, bounds, unsupported encodings, provenance,
and container/member-to-output mappings. For a decompressor, impose output/work
limits before allocation, not merely an input-size limit. Do not execute inputs
or load plugins from target-controlled text.

Use authored fixtures with independently derived outputs: positive ranges and
bytes, malformed/truncated headers, unsupported variants and budget refusal.
Test paths/collisions, unchanged originals, provenance and installed-wheel reuse
from outside the checkout. Keep targets and raw private evidence outside Git and
packages. Re-run the skill index/link gates after adding a reference. Preserve
explicit errors/partial states; do not silently decode only a convenient prefix.
Publish code, specifications and synthetic fixtures only within the user's
publication authorization. Qualify consumer behavior in a separate experiment.
