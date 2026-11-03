# Snake runtime font provenance

The 2048-byte live INT43 font reported at `C000:01E9` is an exact match for
`int10_font_08[256 * 8]` in DOSBox-X `src/ints/int10_memory.cpp`, pinned commit
`029bd65c5dcc7cdc7f2e14e35278620d9707d969`.

Font SHA-256: `75c79a7e7fa423dda67ec6d6d76cec86b63f85677726368750c75b0920ddf319`.

The source file's opening notice identifies Copyright (C) 2002-2021 The DOSBox
Team and GPL version 2 or any later version. No separate exception for this
array was found in that file. The [pinned upstream source](https://raw.githubusercontent.com/joncampbell123/dosbox-x/029bd65c5dcc7cdc7f2e14e35278620d9707d969/src/ints/int10_memory.cpp)
and [COPYING](https://raw.githubusercontent.com/joncampbell123/dosbox-x/029bd65c5dcc7cdc7f2e14e35278620d9707d969/COPYING) were fetched and are byte-identical to the
installed backend's pinned upstream source companion. This identifies a stated
upstream license and corresponding source for the exact font; it is not a claim
that this font is CC0 or that the DOSBox application forms part of the game.

`int10_font_08-source.h` preserves the upstream copyright/license notice and the
unchanged array data, with a prominent extraction notice. Its only declaration
change is `uint8_t` to `unsigned char` for a standalone source definition.
Extracting its hex values reproduces `int10_font_08.bin` exactly. Preserve that
source, attribution, and `COPYING-GPL-2.0.txt` with redistributed font copies.
The complete original source file is identified by its pinned upstream URL and
SHA-256 in the provenance receipt. This corpus ships the font-only source and
COPYING; it does not bundle the emulator or SDK.

The authored Snake source/license remains a separate CC0 component. Its
`text_char` routine calls BIOS INT10/AH=0E; the original 3851-byte `SNAKE.EXE`
does not embed this complete 2048-byte array. Generated browser/native initial
memory does copy the runtime font, so those copied bytes need their own source
and license notice. This report makes no broad whole-product licensing opinion.

See `font-provenance.json` for source-companion identity, primary-source hashes,
byte comparisons, redacted provenance paths, and retained artifact hashes.
