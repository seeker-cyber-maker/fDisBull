#include "sherlock_font.h"

#include <errno.h>
#include <limits.h>
#include <string.h>

static int invalid(void)
{
    errno = EINVAL;
    return -1;
}

static int overflow(void)
{
    errno = EOVERFLOW;
    return -1;
}

int sh_font_decode(SHFont *out, const uint8_t *bytes, size_t length)
{
    if (!out || !bytes || length != SH_FONT_BYTES) return invalid();
    for (unsigned i = 0; i < SH_FONT_GLYPHS; ++i) {
        unsigned advance = bytes[i * SH_FONT_RECORD_BYTES];
        if (advance < 1 || advance > 8) return invalid();
    }
    memmove(out->glyphs, bytes, SH_FONT_BYTES);
    return 0;
}

int sh_font_measure(const SHFont *font, const uint8_t *text, size_t length,
                    size_t *width, size_t *height)
{
    size_t line = 0, widest = 0, total_height = length ? SH_FONT_HEIGHT : 0;
    if (!font || (!text && length) || !width || !height) return invalid();
    for (size_t i = 0; i < length; ++i) {
        unsigned character = text[i];
        if (character == '\r') continue;
        if (character == '\n') {
            if (line > widest) widest = line;
            line = 0;
            if (total_height > SIZE_MAX - SH_FONT_LINE_HEIGHT) return overflow();
            total_height += SH_FONT_LINE_HEIGHT;
        } else {
            unsigned advance = font->glyphs[character][0];
            if (advance < 1 || advance > 8) return invalid();
            if (line > SIZE_MAX - advance) return overflow();
            line += advance;
        }
    }
    if (line > widest) widest = line;
    *width = widest;
    *height = total_height;
    return 0;
}

static void draw_pass(const SHFont *font, const uint8_t *text, size_t length,
                      uint8_t *pixels, size_t width, size_t height, size_t stride,
                      int64_t x, int64_t y, uint8_t ink)
{
    const int64_t initial_x = x;
    for (size_t i = 0; i < length; ++i) {
        unsigned character = text[i];
        if (character == '\r') continue;
        if (character == '\n') {
            x = initial_x;
            y += SH_FONT_LINE_HEIGHT;
            continue;
        }
        const uint8_t *glyph = font->glyphs[character];
        for (unsigned row = 0; row < SH_FONT_HEIGHT; ++row) {
            int64_t py = y + row;
            if (py < 0 || py >= (int64_t)height) continue;
            for (unsigned column = 0; column < 8; ++column) {
                int64_t px = x + column;
                if (px >= 0 && px < (int64_t)width &&
                    (glyph[row + 1] & (0x80u >> column)))
                    pixels[(size_t)py * stride + (size_t)px] = ink;
            }
        }
        x += glyph[0];
    }
}

int sh_font_draw(const SHFont *font, const uint8_t *text, size_t length,
                 uint8_t *pixels, size_t pixel_bytes,
                 size_t width, size_t height, size_t stride,
                 int x, int y, uint8_t ink, int shadow, uint8_t shadow_ink)
{
    size_t text_width, text_height;
    if (sh_font_measure(font, text, length, &text_width, &text_height) != 0)
        return -1;
    if (width > INT_MAX || height > INT_MAX ||
        text_width > INT_MAX || text_height > INT_MAX) return overflow();
    if (!width || !height) return 0;
    if (!pixels || stride < width) return invalid();
    if (height - 1 > (SIZE_MAX - width) / stride) return overflow();
    if ((height - 1) * stride + width > pixel_bytes) return invalid();
    if (shadow)
        draw_pass(font, text, length, pixels, width, height, stride,
                  (int64_t)x + 1, (int64_t)y + 1, shadow_ink);
    draw_pass(font, text, length, pixels, width, height, stride, x, y, ink);
    return 0;
}
