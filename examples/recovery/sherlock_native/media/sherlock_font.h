#ifndef SHERLOCK_FONT_H
#define SHERLOCK_FONT_H

#include <stddef.h>
#include <stdint.h>

/* The owner's recovered font is an external resource. No original glyph data
 * is compiled into the application. Each record is an advance (1..8 pixels)
 * followed by eight bitmap rows, with bit 7 at the left. */
enum {
    SH_FONT_GLYPHS = 256,
    SH_FONT_RECORD_BYTES = 9,
    SH_FONT_BYTES = SH_FONT_GLYPHS * SH_FONT_RECORD_BYTES,
    SH_FONT_HEIGHT = 8,
    SH_FONT_LINE_HEIGHT = 10
};

typedef struct SHFont {
    uint8_t glyphs[SH_FONT_GLYPHS][SH_FONT_RECORD_BYTES];
} SHFont;

/* Exact length and every advance are checked before changing out. */
int sh_font_decode(SHFont *out, const uint8_t *bytes, size_t length);

/* Byte-coded text, not UTF-8. LF starts a new line and CR is ignored. The
 * reported width is the largest line's advance, not an ink bounding box;
 * glyph ink may extend past its advance. Empty text has zero width/height.
 * Outputs are unchanged on invalid input or arithmetic overflow. */
int sh_font_measure(const SHFont *font, const uint8_t *text, size_t length,
                    size_t *width, size_t *height);

/* Draw into an existing, top-to-bottom, byte-per-pixel surface. Unpainted
 * pixels and row padding are preserved. Each set glyph bit replaces a pixel
 * with ink. When shadow is nonzero, a complete shadow pass at (+1,+1) precedes
 * the ink pass. All drawing is clipped, including negative origins.
 *
 * The buffer extent, dimensions and measured text are checked before any
 * mutation. Width/height and measured dimensions must fit int. Zero-area
 * surfaces are valid and need no pixel buffer. Returns 0 on success, -1 with
 * errno=EINVAL/EOVERFLOW on invalid input. */
int sh_font_draw(const SHFont *font, const uint8_t *text, size_t length,
                 uint8_t *pixels, size_t pixel_bytes,
                 size_t width, size_t height, size_t stride,
                 int x, int y, uint8_t ink, int shadow, uint8_t shadow_ink);

#endif
