# Civilization DOS media formats and extraction

Status: **implemented, bounded, private-input extraction**. The decoder is
`examples/civ/civ_media.py`; synthetic checks are in
`tests/test_civ_media.py`. No game media is committed.

The original ships its pictures, palettes and fonts as **separate files beside
`CIV.EXE`**. The executable names them; it does not embed the picture bytes.
The extraction command therefore scans `CIV.EXE` for those names and decodes
the matching files in a caller-supplied private asset directory. This
distinction is a result, not an assumption: the name strings are present in
the root/overlays, while the decoded media bytes are not found in the
executable.

Identity used for the first extraction:

| File | Bytes | SHA-256 |
|---|---:|---|
| `CIV.EXE` (474.03 complete install) | 302,982 | `31e35b01f4d00df81685dfcb81e6de196a3876bd2afff6e39cbbfd964f5852ad` |
| `CIV.EXE` (474.05 pinned executable) | 302,982 | `22de2748e3089793644c7e501e2a95b553010ddec34a7ff42f4395cf779c9c2a` |
| `FONTS.CV` (474.03) | 19,123 | `c07a501f3a4a39dc2cd9779208aa4b59eeed823035a8da65919e2bad5f6e51cd` |
| `SP257.PIC` (both sampled) | 12,779 | `569a028b5d3421db48275578074f5f2336c52a65a6776941ac1456d5da92f9b5` |
| `SP256.PAL` (both sampled) | 782 | `c4a48f6d9c37e0d67199c739948aaf5cfc19a024bbe32734c2c1fda3f1c1dcc7` |

The 474.03 tree is used for media extraction because it is the complete
start-up tree available here. The pinned 474.05 executable remains a different
edition identity; do not mix its addresses with 474.03 assets or call the
result byte-identical.

## 1. Pictures and palettes (`*.PIC`, `*.PAL`)

### 1.1 Reader path in the original

| Address | Role |
|---|---|
| `R:1FA1:01A2(page,x,y,name,mode)` | General picture loader. Opens the file, walks chunks with `R:0000:108E`, decodes one row at a time, copies it to the target page; `page < 0` forces a palette-only load. |
| `R:1FA1:0220(page,name)` | `01A2(page,0,0,name,1)`: picture and palette. |
| `R:1FA1:0254(page,name)` | `01A2(page,0,0,name,0)`: picture, palette not applied. |
| `R:1FA1:026C(name)` | `01A2(-1,0,0,name,1)`: palette only. |
| `R:1FA1:0288(name,buffer)` | Palette copied into a caller buffer, not applied. |
| `R:0000:108E(mode)` | Chunk walk and image header. |
| `R:0000:1208(buffer)` | One row: post-LZW 90h-RLE and X1 nibble split. |
| `R:0000:1227`, `R:0000:1270` | LZW start and dictionary reset. |
| `R:0000:1318` | One LZW code. |
| `G:0000:0162` (slot 28) | `M0` palette chunk to the VGA DAC. |
| `G:0000:03DF` (slot 19) | Copy one decoded row to a page. |

The source/listing cross-check is Civ64 `docs/dos/FORMATS.md` section 1,
`docs/dos/PALETTE.md` sections 2.1-2.2 and Civd `FILEIO.C` / `IMAGE.C`.
The decoder is clean-room: it does not execute the DOS program or call a
period toolchain.

The decoder follows the repository's existing media-decoder boundary
(`src/fdisbull/agi_picture.py`): pure caller bytes, explicit pixel/code
budgets, malformed input refused, and no host drawing or execution.

### 1.2 Chunk stream

All multi-byte fields are little-endian.

| Offset | Width | Field |
|---|---:|---|
| +0 | 2 | ASCII tag: `E0`, `M0`, `X0` or `X1` |
| +2 | u16 | Length of the data after the tag/length |
| +4 | length | Data |

| Chunk | Meaning |
|---|---|
| `E0` | EGA mapping: `first`, `last`, then one byte per index. `MGRAPHIC` ignores it; `EGRAPHIC` uses it. The VGA decoder records it as opaque evidence. |
| `M0` | Palette: `first`, `last`, then 3 bytes (`R,G,B`, 6-bit each) per entry `first..last`. In all sampled files `first=0`, `last=255`, so the palette is full. |
| `X0` | 8-bit image: `u16 width`, `u16 height`, `u8 maximum LZW width`, then the LZW code stream to end of file. |
| `X1` | 4-bit image: same header; each decoded RLE byte gives two pixels, **low nibble first**, then high nibble. |

A `*.PAL` is an `M0` chunk plus an `X0` chunk with `width=height=0`; the decoder
returns the palette and no pixels. A `*.MAP` (see section 3) is an `X0`
320x200 image with no palette.

### 1.3 Decode order

1. The original reads 16-bit words from a buffered file. The decoder's
   LSB-first bit reader is equivalent to reading the bytes in file order.
2. LZW starts with width 9, mask `0x1FF`, next code `0x100`, and a dictionary
   of 2048 three-byte entries. On a code:
   - `code < next`: output its string;
   - `code == next`: output the previous string plus its first byte;
   - larger: malformed for this format.
   Then add `next = (previous_code, first byte of this string)`.
3. The original adds entry `0x100` even on the first code after a start or
   reset, using the stale previous code. The decoder follows that behavior and
   keeps the previous code across resets. Sampled streams never reference that
   stale entry, but matching it keeps code-width growth aligned with the
   original.
4. When `next > mask`, widen by one bit. When the width would exceed the
   header maximum, reset the dictionary immediately: width 9, mask `0x1FF`,
   next `0x100`; the previous code/string survives.
5. The decoded byte stream goes through the 90h-RLE stage:
   - a normal byte is emitted and becomes the last byte;
   - `90 00` emits a literal `90`;
   - `90 n` with `n > 1` emits the last byte `n-1` more times;
   - `90 01` is the original's 256-copy edge. It does not occur in the sampled
     files; the decoder preserves the documented edge.
6. A row consumes `width` bytes for `X0`, or `(width+1)//2` bytes for `X1`.
   `X1` expands each byte into two pixels, low nibble first. Rows run top to
   bottom. The LZW and RLE state continue across rows.

The decoder requires enough decoded bytes for exactly `width*height`; it
rejects short streams rather than substituting zeros. Extra bytes are ignored
as trailing evidence.

### 1.4 Palette values

The stored components are 6-bit (`0..63`). The VGA DAC displays a linear
value. The extractor's PNG writer uses `round(v*255/63)`; that is a rendering
choice, not a recovery claim. The original does not scale the stored values.
Palette 0..15 often carries the interface colours, but the palette in effect
is scene-dependent; see Civ64 `docs/dos/PALETTE.md` section 5.

## 2. Fonts (`FONTS.CV`)

The graphics driver is loaded with `fonts.cv` directly after its data segment.
`FONTS.CV` is addressed as data offset `0630h + ...` by `MGRAPHIC`; the file
layout is independent of that load base:

| Offset | Width | Field |
|---|---:|---|
| 0 | u16 | Font count `N` (9 in the sampled release) |
| `2n`, n=1..N | u16 | Offset `P(n)` of font n's glyph bitmap |
| `P-8-k .. P-9` | k | Width table, one byte per code `first..last`; present only when fixed advance is 0 |
| `P-8` | u8 | First code |
| `P-7` | u8 | Last code |
| `P-6` | u8 | Bytes per glyph row (1 or 2) |
| `P-5` | u8 | Fixed advance; 0 means proportional |
| `P-4` | u8 | Height (normal rows) |
| `P-3` | u8 | Spacing added to every advance |
| `P-2` | u8 | Extra rows (stored, drawn only in opaque mode) |
| `P-1` | u8 | Reserved/not read |
| `P..` | | Row-major bitmap across all glyphs: row r of glyph i starts at `P + r*k*bytes_per_row + i*bytes_per_row` |

All nine sampled fonts are proportional (`fixed=0`). The draw routine reads a
word with bytes swapped, so bit 7 of the first byte is the leftmost pixel.
`font_sheet()` in the extractor's code is only an inspection aid; it does not
claim the original clipping or the known 1-byte-font 9th-column defect.

## 3. The save-side `.MAP` page-2 image

The original's save path writes **two** files:

- `CIVILn.SVE`: serialized game state (`transfer_game`);
- `CIVILn.MAP`: page 2, written by `image_screen(page=2,file)`.

`load_save` later reloads the `.MAP` with `load_screen(2,file)`. That is a
picture load, not a separate map parser. The `.MAP` bytes are therefore an
`X0` picture of the page-2 data store. For the sampled Russian 475.01 save:

```text
CIVIL0.MAP: X0, 320x200, 13,128 bytes,
SHA-256 ea82bbca9ee1e6c87cc7ed17fa153ab7251c5e94968f35d8eb3bc1f0fff0b922
```

Page 2 carries the play-map projection used by Civ64 `SCENES-PLAY.md` 1.1:

| Page-2 area | Extracted field |
|---|---|
| `(x,y)`, x 0..79, y 0..49 | terrain colour `0..15`; `Civd MAP.C:385` maps it to type `-1,10,3,8,-1,-1,1,6,-1,11,2,9,4,5,0,7` |
| `(x+160,y)` | unit layer: bit 3 present, bits 0..2 owner |
| `(x,y+100)` | improvement low nibble |
| `(x,y+150)` | improvement high nibble |
| `(x+80,y+100)` | known-improvement low nibble |
| `(x+80,y+150)` | known-improvement high nibble |
| `(240..319,0..49)` | the 80x50 minimap image (one pixel per square) |

Improvement bits: `1` city, `2` irrigation, `4` mine, `8` road, `10h`
railroad, `20h` fortress, `40h` pollution. The labels are the Civ64/SPRITES
and Civd source labels; this extractor does not prove gameplay semantics.

`extract_world_map()` produces 4,000 cells plus 50 ASCII rows. An uppercase
terrain glyph marks a unit present; that uppercase convention is a **reduced
Z/ASCII projection**, not an original screen rule. The terrain glyphs are
`d P g F h M t A s J ~ r` for Desert, Plains, Grassland, Forest, Hills,
Mountains, Tundra, Arctic, Swamp, Jungle, Ocean, River.

This is the reduced representation used by `examples/civ/civ_world_uil.py`
and [UIL_RECORD.md](UIL_RECORD.md): it preserves terrain, terrain colour, unit owner,
unit presence, improvements and known improvements as indexed arrays, while
the 50 row strings give a bounded text view.

## 4. Extraction

The command writes only to a new/empty private output directory. It does not
write beside the game files or publish decoded bytes.

```sh
PYTHONPATH=src:. python3 -m examples.civ.civ_media \
  --exe /private/civ47403/CIV.EXE \
  --assets /private/civ47403 \
  --out /private/civ-media-out \
  --all-assets
```

`--all-assets` decodes every `PIC/PAL/CV` in the directory; without it the
decoder uses only names found in the executable. `--include-saves` also
decodes `CIVILn.MAP` page-2 images.

Observed on the 474.03 tree:

| Result | Count |
|---|---:|
| Media names found in `CIV.EXE` | 68 distinct resolved names |
| Present named assets (default) | 64 |
| Named references absent from this tree | 4 (`CBACKS0.PIC`, `CIVIL0.SVE`, `NSOUND.CV`, `REPLAY.TXT`) |
| Decoded with `--all-assets` | 154 assets |
| PNG files | 107 |
| Font files | `FONTS.CV` with 9 fonts |
| Decode errors | 0 |

All 145 picture/palette files in the 474.03 runtime decoded (107 `PIC`, 38
`PAL`) with no errors; the `--all-assets` count adds texts/CVs and the save
`.MAP`. The manifest records the executable SHA-256, every resolved asset SHA,
dimensions, chunks, palette presence, font tables and, for `.MAP`, the reduced
map rows and terrain hash.

`CIV.EXE` has a few false textual neighbours such as the color-prefixed
`1fonts.cv`; the extractor resolves a leading digit by dropping it only when
the shorter name is a real file. `CBACKS0.PIC`, `NSOUND.CV` and `REPLAY.TXT`
are genuinely absent from this tree rather than silently invented.

## 5. Boundaries

- The extractor does not execute `CIV.EXE`, run DOSBox, or prove that a
  decoded page is what a particular release displayed.
- Pictures are decoded with their embedded palette when present. A picture
  without `M0` (notably `.MAP`) is returned as indices; the PNG is grayscale
  unless a caller supplies a palette.
- `FONTS.CV` glyph sheets are inspection images. The original's 1-byte-font
  word read can borrow the next glyph byte; that defect is documented, not
  reproduced as a game rule.
- `.MAP` is a save-side page-2 image, not a save parser. It is an observation
  of the serialized image; live map fields still need a runtime or save-layout
  proof.
- Sound (`*.CVL`) and archive forms are inventoried only; no audio decoder is
  claimed.
- The 474.03 media identity and the pinned 474.05 executable identity remain
  separate. A later edition's assets need their own hashes and decode check.
