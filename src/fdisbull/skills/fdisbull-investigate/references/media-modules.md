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
- [Castles II BOB image adapter](#castles-ii-bob-image-adapter)
- [Westwood Kyra-family media and EMC2](#westwood-kyra-family-media-and-emc2)
- [MADS conversations and containers](#mads-conversations-and-containers)
- [KINT 6 and Sherlock 7](#kint-6-and-sherlock-7)
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
and member names/input roles/offsets/sizes/SHA-256. Decoded PNG members use
`offset: null` and an explicit pixel rectangle. It does not inline complete
member payloads or previews. PNG profiles expose fixed control-color values;
KINT exposes selected header fields, including raw reserved extension bytes.
MZ/AGI extraction adds the selected member's mapping to fixed output
`payload.bin` and `media-manifest.json`. Their manifest remains structural-only;
it does not supply runtime addresses, source mappings or semantic claims.
For AGI, both directory and volume identities and the resource number are retained.

Sources stay unchanged. `media-extract` requires an existing private parent owned by
the caller (0700), creates an exclusive 0700 destination and 0600 files, refuses
Git/worktree ancestry and symlink output paths, and accepts only listed member
names. Never publish payloads or private originals, including modified game
assets. Reports contain structural/pixel metadata rather than complete payloads;
review that metadata and provenance before publication. No new FDB writes are made: parser output does not bypass the
external-target storage boundary or grant permission to bind/import bytes.

The original MZ and AGI adapters cap each source volume/container at 64 MiB. `max_output_bytes`
limits the selected payload to 1..64 MiB before creating output (default 64 MiB).
The CLI uses `--max-payload-bytes` for this limit. The global
`--max-output-bytes` before the command controls the JSON reply budget instead;
it never changes the extracted payload limit.
The MZ and AGI adapters perform no decompression and have fixed/small member counts.
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

## KINT 6 and Sherlock 7

Use `kint6-ke` for original header/body ranges and virtual memory declarations,
and `fdisbull.kint6` through `module-analyze` for guest instruction facts.
Use `sherlock7-images`, `kint6-user-buttons` and `kint6-user-overlays` for
documented PNG atlas layouts. They preserve RGBA pixels, report color keys
separately and support one named crop or `--member all`. PNG payload names,
aggregate limits and pixel provenance extend the byte-container contract above.
Read [KINT 6 and Sherlock 7](kint6-sherlock7.md) for the complete specification,
commands, research provenance and explicit runtime/version gaps.
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
  Uses fDisBull's built-in Inno Setup 5.6.2 Unicode reader; no external
  `innoextract`, Wine or subprocess is required. Versions/filters/part hashes
  and output hashes are retained by its manifest. Multipart parts are provenance
  candidates, not per-part consumption proof. Installer code is never launched.
  The bounded native decoder checks header, chunk and payload checksums and
  refuses unsupported versions, external slices, encryption and malformed data;
  its timeout covers parsing, hashing and extraction. Use its listing/extraction
  contract; do not mistake it for a general disk reader or runtime qualification.
- `gog-galaxy-upx`: `fdisbull.gog_galaxy.rebuild_galaxy_capture/files`, or
  `python -m fdisbull.gog_galaxy_cli`. Accepts an unchanged wrapper, caller-captured mapped PE,
  source-free process/thread/OEP receipt and export map. CHimpREC preserves
  original IAT slots and rebuilds PE32/PE32+ import structures. It never downloads,
  attaches to, launches or authenticates Galaxy; reconstructed executables stay
  private and still require separate Windows/Wine execution qualification.
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

## Westwood Kyra-family media and EMC2

The add-on `westwood-pak`, `westwood-cps`, `westwood-wsa` and `westwood-emc2`
readers are registered through the same `media-inspect`/`media-extract`
interfaces. Read `docs/WESTWOOD_MEDIA_DECODERS.md` in a source checkout for
format profiles, supported compression, per-file bounds and provenance. The
`fdisbull.westwood.emc2` guest processor exposes 19 bounded core opcodes via
`module-analyze --profile kyrandia1-dos|lol1-dos --function-index N`, not a
qualified script interpreter or UIL lifter. Never infer a shared game syscall
ABI simply because the underlying EMC2 bytecode is the same.

A first WSA frame may depend on a prior animation state: a zero initial offset
is a hard refusal without an explicitly bound prior frame, not permission to
zero-fill. Duplicate PAK names require an exact indexed member selector. For
CPS graphics lacking their own palette, export indexed bytes but do not guess
color; source-embedded 320x200 palettes permit a derived PNG preview. Archive
member extraction and media decoding are distinct steps.

## MADS conversations and containers

Use `decoder-modules` to confirm `fdisbull.mads.conversation` is installed.
This is a static conversation processor, not a playable MADS engine or a live
ScummVM debugger. It uses the same decoder registry as AGI and Westwood EMC2.

### Choose the correct layer

1. Inspect original DOS executables with the native loader. `SPHERE.EXE` is a
   separate x86/RTLink investigation; do not send it to the CNV processor.
2. Preserve the launch recipe, working directory, arguments and mounted CD.
   Local IDX files can be indexes for HAG resources on that disc.
3. Inspect HAG resources, then select the actual `CONVnnn.CNV` entry. This reader
   supports MADSCONCAT 1.0 and MADSPACK 2.0 stored/FAB data. Unknown variants refuse.
4. Inspect the CNV's dialog table and choose `function_index` (the dialog index).
   Pair CND metadata separately when imported variables or initial flags matter.

```sh
python -m fdisbull.mads_processor inspect /private/GLOBAL.HAG --kind hag
python -m fdisbull.mads_processor inspect /private/GLOBAL.HAG --member CONV001.CNV
fdisbull request '{"method":"module-analyze","params":{"module":"fdisbull.mads.conversation","path":"/private/GLOBAL.HAG","member":"CONV001.CNV","function_index":3,"max_instructions":80}}'
```

The command is projectless. It does not require ScummVM, Capstone or a running
emulator. The stock `module-analyze` positional CLI works on a loose CNV for
its first dialog. JSON/Python supports explicit archive member and dialog selection.

### Evidence rules

Retain the source hash, HAG occurrence/index, compression section, selected dialog
and exact decoded instruction spans. A decompressed section-6 byte offset is not
an EXE offset or a native breakpoint address. GOTO targets must be actual instruction
boundaries in the selected dialog. A different dialog or operand is unresolved,
not automatically another entry point.

Conditional operation IDs and variable references are retained without evaluation.
Do not turn old upstream enum names into verified original-game semantics. Unknown
instructions fail; DIALOG_END retains an opaque engine edge. A bounded stop is not
complete coverage. `complete` is scoped to static edges, never gameplay equivalence.
CND pointer-looking fields and runtime workspace are not live host state.

Keep CNV/CND/HAG payloads, decoded text, instruction bytes and private state out of
Git. Publish authored scripts and aggregate/hashing receipts only. Read the full
repository guide `docs/MADS_PROCESSOR.md` for API contracts, limits and provenance.
The next semantic gate is a native interpreter trace, not another parse count.

## Castles II BOB image adapter

Use the existing inspect/extract API for the explicitly selected original Castles II CD variant:

    fdisbull media-inspect /private/game/ANIM.BOB --adapter castles2-bob
    fdisbull media-extract /private/game/ANIM.BOB /private/new-bob-output --adapter castles2-bob --member preview-png

The generic extractor writes PNG bytes to "payload.bin"; rename that private
file to ".png" for viewing. "palette-rgb" and "indices" preserve original
byte spans at file offsets 4 and 772.

This is a narrow adapter using the existing MADS IndexedImage and PNG encoder,
not a new graphics framework. Layout is width:u16le, height:u16le,
256 RGB888 triplets, and width*height row-major u8 indices; source length is
exactly 772+width*height, with 1..4096 dimensions and <=4 MiB pixels.
BOB has no magic: never select by ".BOB" suffix alone.

A magenta-looking background at palette index 255 in some portraits does
not prove transparency. The parser does not infer a color key, alpha,
in-game blit/compositing, palette cycling or animation timing; C2INTRNN
files are independent source frames. Keep game bytes and derived PNGs private.
The 97-file source-specific acceptance and feature-investment record is in
docs/CASTLES2_BOB_DECISION.md.

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


## Shared format-module catalog and SMK2 framing

Use `format-modules` and `file-identify` before format-specific research. Their
SQLite catalog keeps minimal signature/header facts and links to the shipped
reader seams without storing inspected payloads. The legacy adapters above keep
their existing contracts. `media-inspect --adapter smacker` and `smk-frame` add
bounded native SMK2 inspection/framing, with complete independent video/audio
decoding and a separate original-game integration gate. See
[format modules](file-formats.md) for commands and claim limits.


For a single game or a batch, run `intake-inventory` through the common format
catalog before selecting adapters. Read the bounded recovery queue and preserve
partial enumeration, I/O errors, unexpanded containers and embedded media as
separate observations. `media-inspect --adapter flic` inventories standard,
Bullfrog and TFTD VID packet structures; an explicit `--index-path` checks a
selected TFTD companion. It does not decode or frame FLIC. DinoPark UNC2/UNCS,
UNCP and ABT formats require their own consumers, despite familiar suffixes.
The format-modules reference above records the full routing contract.


## Independent MADS media and conversation execution model

The media family is reusable **without ScummVM or the MADS processor**. Discover
`fab`, `pkware-dcl`, `mads-hag`, `mads-pack`, `mads-sprite`, `mads-tiles`,
`mads-depth`, `mads-background`, `mads-depth-map`, `mads-mask`, `mads-font`,
`mads-dsr` and `mads-animation` in `media-modules`. Use the shared JSON
`media-inspect` / `media-extract` APIs or the installed standalone CLI:

```sh
python -m fdisbull.mads_media_adapters catalog
python -m fdisbull.mads_media_adapters inspect /private/SCENE.SS --adapter mads-sprite --number 0
python -m fdisbull.mads_media_adapters extract /private/SCENE.SS --adapter mads-sprite --number 0 --member preview-png --output /private/new-image
```

The ordinary CLI derives adapter choices from the shared catalog. Use
`fdisbull media-inspect` / `media-extract`, `fdisbull request`, or the module CLI.
`source_member` selects a resource in a HAG; `member` selects its decoded output.
Duplicate HAG names require an integer source index (CLI: `--source-index`).
Backgrounds require an explicit `map_path` and optional `map_member` or CLI
`--map-index`. Raw FAB requires `expected_size`;
DCL can infer its terminated output up to the declared budget. MADSPACK 1.0
compression ID 1 is DCL, whereas 2.0 ID 1 is FAB. Do not guess from a suffix.

PNG uses a resource-local palette, not the live game's palette allocation.
Depth/mask/font planes have no invented colors. WAV preserves unsigned-eight-bit
mono PCM. AA produces timeline/reference records, not a fully rendered movie.
An empty sprite or zero-tile set is an explicit empty result, not a synthetic
image. Media paths never execute the processor or target code.

`fdisbull.mads_runtime.ConversationRuntime` separately offers bounded model
execution, instruction breakpoints, explicit imports/RNG and source-bound
checkpoint replay. It does not promote the static decoder to verified native
execution or executable UIL. Commands 0, 6 and 255 remain refused at runtime
because historical implementations disagree. Native scene code, a live MADS
sidecar, animation scheduling, music synthesis and original-runtime parity
remain separate gates. Read `docs/MADS_MEDIA_RUNTIME.md` in the source tree.

Use only authored fixtures and sanitized aggregate receipts in Git. Original
media, decoded fonts, instruction payloads, model checkpoints and source-bound
private traces remain outside the repository and delivery archives. Do not
reuse a prior test count when recovered source is absent. Verify source and
tests are physically present in the final package and test the installed wheel.


### Independent codec discovery and installed validation

`file-identify` routes FAB, MADSCONCAT and MADSPACK headers to their separate
readers without decompressing during identification. DCL is cataloged but has
no reliable magic; two plausible option bytes must not be treated as detection.
MADSPACK is a container, not automatically conversation code or a sprite.

`fdisbull.codec_fab.decode_fab` and `fdisbull.codec_dcl.decode_dcl` import only
the standard library and can be reused without any MADS modules. Resource/media
readers depend on those codecs, never on the conversation processor or ScummVM.

Use `python -m fdisbull.mads_validation --resources /private/resources
--synthetic-model --output /private/new-receipt.json` for an installed corpus
check. Model inputs are explicitly synthetic; replay is not native equivalence.
The helper is packaged under `src/fdisbull`, not a pruned example dependency.
The example path remains a convenience wrapper only.
