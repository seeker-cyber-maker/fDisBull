# Sherlock 7 PNG atlas readers

The media adapter decodes three explicitly selected atlas profiles. The image
codec is standard PNG; the game-specific work is recovering named regions,
paired button states and fixed control pixels from the documented layouts.

| Adapter/profile | Supported layout | Output |
| --- | --- | --- |
| `sherlock7-images` | 8 × 10 square cells | 64 puzzle images and 8 surrounding control, background or composite overlay regions |
| `kint6-user-buttons` | 24 units wide; 1–251 rows of 5 units | A normal and pressed image per row, each 12 × 5 units |
| `kint6-user-overlays` | 24 units wide; 1–251 rows of 5 units | A dark and light image per row, each 12 × 5 units |

Profile selection is explicit. Geometry can validate a selected profile, but
cannot prove that an arbitrary PNG belongs to Sherlock or identify a particular
game release. `profile_version: 1` identifies this reader's layout contract.

## Evidence and qualification

Layout facts come from the English help bundled in the owner's Sherlock 7.0
demo, specifically its Graphics and User Buttons sections and labeled image-set
diagram. The private inputs were read without executing the application. No
game art, executable bytes, help text or upstream source is included in this
implementation or its test fixtures.

The supplied `Robin.png` and `EKS_Sherlock.png` atlases are 640 × 800 and
768 × 960 pixels, with 80-pixel and 96-pixel cells. Both produce 72 members. The
supplied `UserButtons.png` has 21 paired rows, and `UserOverlays.png` has 23.
For each of these four sheets, decoding every exported region and reassembling
the original raster reproduced its complete RGBA pixels exactly. This verifies
atlas extraction; it does not establish equivalence to the running game's
compositing, scaling or rendering.

Tests use authored coordinate-coded PNGs with independently specified pixel
values. They cover rectangle placement, complete nonoverlapping coverage,
single-pixel controls, alpha preservation, PNG color types, Adam7 interlace,
CRC and structural failures, malformed or oversized compressed rasters, and
input/output bounds.

## Game image atlas

Coordinates below are in cells, with the origin at the upper-left corner.
Output names have no extension in the inventory; extraction adds `.png`.

| Member | x | y | Width | Height | Meaning |
| --- | ---: | ---: | ---: | ---: | --- |
| `control-area` | 0 | 0 | 1 | 1 | Control colors and layout guide |
| `credits` | 1 | 0 | 4 | 1 | Image creator credits |
| `highlight` | 5 | 0 | 1 | 1 | Hint/find highlighting |
| `empty-clue-vertical` | 6 | 0 | 1 | 1 | Empty vertical clue slot |
| `empty-clue-horizontal` | 7 | 0 | 1 | 1 | Empty horizontal clue slot |
| `tile-rR-iI` | I | R + 1 | 1 | 1 | Category R, item I; both range 0–7 |
| `cell-background` | 0 | 9 | 1 | 1 | Candidate cell background |
| `clue-overlays` | 1 | 9 | 5 | 1 | Composite clue overlay strip |
| `bookmark-overlays` | 6 | 9 | 2 | 1 | Composite clue bookmark strip |

The two composite strips are retained intact. This reader does not assign
undocumented semantics to subregions or recreate the runtime clue drawing
algorithm.

### Control pixels

The first 14 pixels on row zero are metadata. Their coordinates remain literal
pixels `(x, 0)`, even when the cells use a different scale. An atlas cell must be
at least 14 pixels wide so the controls fit its reserved area.

| x | Role |
| ---: | --- |
| 0 | First transparency key |
| 1 | Second transparency key |
| 2 | Unused |
| 3 | Horizontal clue bin fill |
| 4 | Horizontal clue bin frame |
| 5 | Vertical clue bin fill |
| 6 | Vertical clue bin frame |
| 7 | Puzzle fill |
| 8 | Puzzle frame |
| 9 | Selected clue outline |
| 10 | What-if fill |
| 11 | What-if outline |
| 12 | Unused |
| 13 | Clue bookmark outline |

The inventory reports each control's index, role and decoded RGBA value.

## User buttons and overlays

Unit size is the raster width divided by 24 and must be a positive integer.
Each row contains two images, each 12 units wide and 5 units high. The raster
height must be a whole number of rows, from 1 through 251.

| Profile | Left image | Right image | Additional control |
| --- | --- | --- | --- |
| `kint6-user-buttons` | Normal | Pressed | None assigned by this reader |
| `kint6-user-overlays` | Dark | Light | Pixel `(0, 0)` is a transparency key |

Rows map to list entries starting at 6 because the UI skin supplies the first
five entries. Example member names are `button-006-normal`,
`button-006-pressed`, `overlay-006-dark` and `overlay-006-light`. All rows are
retained, including slots that appear blank; appearance is not evidence that a
slot can be removed or renumbered.

## Pixel preservation and provenance

`decode_png_atlas(data, profile=..., max_output_bytes=...)` returns a JSON-safe
report and a mapping from member names to normalized PNG bytes. The adapter
handles secure file output separately. Each member carries its semantic role,
decoded-pixel rectangle, encoded size and SHA-256, and a SHA-256 of its RGBA
pixels. The report also records the original input's size and SHA-256 and the
complete decoded raster's pixel digest.

`source_rect` and `pixel_rect` describe the same pixel coordinates; `offset` is
null because a crop does not have a contiguous byte range in a compressed PNG.
PNG encoding can change output bytes while preserving pixels, so input identity,
encoded-output identity and decoded-pixel identity are distinct fields.

PNG alpha is preserved. Game transparency keys are reported separately and
are **not** converted into alpha by this reader. No gamma correction, color
management, resizing or runtime compositing is applied. Consumers needing the
game's displayed appearance must establish those behaviors separately.

## Bounds and supported PNG variants

- Maximum input: 64 MiB.
- Maximum decoded raster: 16,777,216 pixels; neither dimension may exceed 32,768.
- Maximum PNG chunk count: 4,096.
- Maximum aggregate encoded member output: 64 MiB, with a smaller caller limit
  available. This internal cap is distinct from the media API's selected-export
  output quota.
- Single-image PNG only. APNG, unknown critical chunks, bad CRCs, trailing data,
  nonconsecutive image-data chunks and malformed headers are refused.
- Gray and indexed PNG support 1-, 2-, 4- and 8-bit samples. RGB, gray-alpha and
  RGBA support 8-bit samples. Adam7 interlace is supported. 16-bit samples are
  refused rather than silently reduced.

The filtered raster's exact expected length is computed from its validated
header, including interlace passes. Its zlib stream is checked with a bounded
inflate before Pillow decodes it. Overlong, short, incomplete and concatenated
streams fail. Ancillary metadata is CRC-checked and omitted before pixel
decoding; text, ICC and EXIF content is unnecessary for this operation and is
not decompressed or interpreted. Output encoding stops before exceeding its
remaining aggregate byte allowance. Errors at this boundary use `ValueError`.

## Deliberately unsupported resources

The supplied UI skin sheets use a different, larger layout. Some regions in the
bundled illustration differ from the observed v7 sheets, including a selector
region and controls shown as unused in the older diagram. They need a separate
profile grounded in a matching loader or specification; a generic fixed-grid
crop would mislabel regions.

`PRECALC*` and `TypeBWI` are not classified as images or decoded speculatively.
The KE executable container and KINT instructions belong to the processor
module. Standard standalone PNG, WAV and MIDI resources do not require a new
proprietary codec merely because they ship with this game.
