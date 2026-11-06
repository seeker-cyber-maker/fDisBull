# KINT 6 guest code and Sherlock 7 media

Read this reference for a KINT 6 `.KE` program or the documented Sherlock 7
PNG atlas layouts. Select the adapter explicitly. A matching filename or
rectangle alone does not identify a game edition.

## Contents

- [Research and identity](#research-and-identity)
- [Inspect and decode](#inspect-and-decode)
- [KE container contract](#ke-container-contract)
- [Processor contract](#processor-contract)
- [PNG atlas contracts](#png-atlas-contracts)
- [Continue recovery](#continue-recovery)

## Research and identity

Start with the target's bundled help, an existing reversing project and the
publisher's development documentation before inferring fields from bytes.
The [official KINT page](https://www.kaser.com/kint.html) provides the
[KINT 6.3.0 development kit](https://www.kaser.com/kint/kint_6_3_0.zip).
The implementation uses documented format facts and source-assisted checks;
it is authored analysis tooling, not recovered game source or a clean-room
runtime implementation. Keep the kit, game and all derived artwork private.

Distinguish three versions: the fDisBull adapter contract (`1`), the reference
kit (`6.3.0`, with KASM `6.1.0`), and the target runtime. Sherlock 7.0's bundled
help requires KINT 6.4.0 or newer. That does not establish every later opcode or
runtime effect. Preserve reserved header bytes without interpreting a plausible
version pattern as proof. Record the target's SHA-256 and the exact reference
edition for every comparison.

The Mac application is the native host. `Contents/Resources/MAIN.KE` is a
separate guest program. Use the KINT processor for that program, and a Mach-O
processor when investigating the host. PNG media, puzzle caches and guest
instructions have separate decoders and evidence boundaries.

## Inspect and decode

Use projectless CLI commands or the equivalent JSON methods:

```text
fdisbull media-modules
fdisbull decoder-modules
fdisbull media-inspect /private/MAIN.KE --adapter kint6-ke
fdisbull module-analyze fdisbull.kint6 /private/MAIN.KE --max-instructions 100
fdisbull module-analyze fdisbull.kint6 /private/MAIN.KE --address 512 --max-instructions 40
fdisbull media-inspect /private/images.png --adapter sherlock7-images
fdisbull media-extract /private/images.png /private/new-tiles --adapter sherlock7-images --member all
fdisbull media-extract /private/images.png /private/one-tile --adapter sherlock7-images --member tile-r3-i5
fdisbull media-inspect /private/buttons.png --adapter kint6-user-buttons
fdisbull media-inspect /private/overlays.png --adapter kint6-user-overlays
```

Keep output parents private and outside Git. Extraction creates a fresh
directory; it refuses an existing destination, symlink paths and Git ancestry.
`--max-payload-bytes` bounds the selected payloads before creating output.
The global `--max-output-bytes` bounds the JSON reply separately.
Use only inspected member names. `all` is supported for these three PNG
profiles; it is not a general archive wildcard.

```python
from fdisbull.decoder_modules import builtin_registry, analyze_input
from fdisbull.sherlock7_media import decode_png_atlas

opened = builtin_registry().open("fdisbull.kint6", "/private/MAIN.KE")
listing = analyze_input(opened, max_instructions=100)
# Already bounded immutable PNG bytes; no files are written by this API.
report, png_members = decode_png_atlas(png_bytes, profile="sherlock7-images")
```

## KE container contract

Validate immutable input of 516 bytes through 64 MiB. Integers are little
endian. Check the 64-bit sentinel `0x0123456789abcdef` at offset zero and
`KINT6` followed by NUL at `0xd0`. Reject unsupported byte order, a missing
header, a declared file-size mismatch and guest address-space overflow.

| File offset | Width | Meaning retained by the reader |
| --- | --- | --- |
| `0x000` | 8 | Null-pointer sentinel |
| `0x008..0x0cf` | 200 | Initial CPU/event storage; not an entry-point declaration |
| `0x0d0` | 6 | `KINT6` marker and NUL |
| `0x0d6` | 4 | Build year (`u16`), month and day |
| `0x0da` | 2 | Raw header revision bytes; runtime meaning unqualified |
| `0x0dc` | 4 | Build number |
| `0x0e0` | 8 | CODE length, equal to complete file length |
| `0x0e8` | 8 | ZERO length |
| `0x0f0` | 8 | STACK length |
| `0x0f8` | 8 | HEAP length |
| `0x110` | 8 | Reserved extension preserved as hex, without inferred version semantics |
| `0x200` | Variable | Event entry candidate, followed by intermixed instructions and data |

CODE includes the entire 512-byte header. Its file and guest byte offsets
coincide. ZERO, STACK and HEAP follow CODE in guest memory and have no file
backing. Report their declared extents without allocating or exporting them.
The supported loader bounds the total address space to `0xffffffff` bytes.
There is no format checksum; SHA-256 records identity, not publisher authenticity.

The `kint6-ke` media adapter exposes two original-byte members:
`header = [0, 512)` and `body = [512, file_size)`. The body is not claimed to be
instructions only. Extraction retains the complete segment metadata separately
and writes the chosen member to `payload.bin`.

## Processor contract

`fdisbull.kint6` supplies instruction facts and static successors through the
existing processor/decoder-module interfaces. It captures the complete `.KE`
once, pins its SHA-256 into the address space and starts at guest byte offset
512. Reopen to analyze changed bytes. A source path is not a snapshot identity.

Retain exact encoded bytes and span, instruction/operand facts, signed relative
memory displacements and explicit guest targets. Follow direct calls, jumps and
conditional branches within the initialized image. Keep indirect calls/jumps,
modal/event control and unsupported instructions unresolved. Invalid or
truncated encodings, unknown targets and traversal budgets keep analysis
incomplete. A caller-selected address is a candidate instruction boundary;
successful decoding cannot distinguish data that happens to resemble an opcode.

This module does not execute KINT, simulate system calls, implement a semantic
lifter, or import arbitrary guest processors into the native FDB schema.
`module-lift` refuses this module. A complete bounded static graph does not
prove game behavior, runtime compatibility, termination or an executable port.

## PNG atlas contracts

Pillow supplies PNG decoding. The module supplies the game-specific rectangles
and control-color metadata. Validate chunk framing, CRCs, critical chunks,
palette/transparency ordering and the exact bounded zlib raster length before
decoding. Refuse animation, 16-bit samples, unsupported critical chunks,
truncation and trailing data. Admit supported 1/2/4/8-bit grayscale/indexed PNG
and 8-bit RGB/gray-alpha/RGBA, including Adam7. Ignore ancillary metadata for
pixel decoding, retain its chunk names, and do not apply color management.

Bound input and aggregate encoded output to 64 MiB, decoded pixels to
16 MiPixel, dimensions to 32,768 and chunks to 4,096. Geometry is checked before
inflation. Every crop preserves decoded RGBA values. Report game color keys
without applying their rendering semantics to alpha. Pixel hashes are the
portable comparison: PNG compressor output may differ between library versions.

| Profile | Geometry | Members |
| --- | --- | --- |
| `sherlock7-images` | 8 columns by 10 square cells, cell size at least 14 pixels | 72 members: 64 puzzle tiles plus 8 control/credits/highlight/empty-slot/background/overlay regions |
| `kint6-user-buttons` | Width `24*u`, height `5*u*n`, `1 <= n <= 251` | Two `12*u` by `5*u` states per row: normal and pressed |
| `kint6-user-overlays` | Same geometry | Two states per row: dark and light |

For Sherlock, the 64 tiles occupy columns 0..7 and rows 1..8, with zero-based
names `tile-r<category>-i<item>`. The top row contains the control area, four-cell
credits area, highlight and two empty-clue slots. The bottom row contains the
cell background and composite clue/bookmark strips. Do not split those strips
into guessed rendering primitives. Fourteen control colors occupy literal
pixels `(0..13, 0)`; they do not scale with cell size.

User button/overlay list numbers start at 6 because the UI skin supplies the
first five entries. Preserve empty slots and both states. Overlay color-key
metadata comes from the first pixel. Do not infer button actions from pictures.

The report uses `offset: null` plus `pixel_rect`/`source_rect` for crops. A PNG
rectangle has no contiguous compressed-file byte range. Retain source digest,
rectangle, raw pixel digest, output PNG digest and profile version together.
Extraction writes `<member>.png` and `media-manifest.json`. `extracted` is an
object for one member and a list for `all`. These are private decoded assets.

## Continue recovery

Inspect documented concepts as they appear: clue orientation, adjacency,
same-column relationships, what-if state, clue removal and event dispatch.
Record each concept's source, edition and unresolved semantics before mapping
it to an instruction or UI region. Use a discriminating runtime experiment
where documentation and bytes disagree.

Sherlock 7's supplied UI sheets differ from a bundled help diagram. Preserve
the discrepancy; do not turn stale coordinates into a decoder contract.
`PRECALC`, `TypeBWI`, full UI-sheet semantics, audio scheduling and puzzle rules
remain separate investigations. Standard WAVE/MIDI files do not become decoded
by selecting an unrelated PNG profile. Use the installed media catalog to
select an applicable existing reader or qualify a new bounded module.

For a replica, continue from named guest handlers and source-linked data to
effects, state transitions and a verifier. Keep original runtime observations,
assembler encoding checks, synthetic tests and authored solver behavior as
separate evidence. See [reconstruction](reconstruction.md) and
[media-module extension](media-modules.md) for the next qualification gates.
