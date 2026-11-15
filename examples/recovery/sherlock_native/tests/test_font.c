#include "../media/sherlock_font.h"

#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>

/* Deliberately artificial glyphs exercise the renderer without redistributing
 * a historical font. Original-pixel qualification uses the owner's private
 * font and independent captured screen rectangles in the research package. */
static void fixture(uint8_t bytes[SH_FONT_BYTES])
{
    memset(bytes, 0, SH_FONT_BYTES);
    for (unsigned c = 0; c < SH_FONT_GLYPHS; ++c)
        bytes[c * SH_FONT_RECORD_BYTES] = 6;
    bytes['A' * SH_FONT_RECORD_BYTES + 1] = 0x81;
    bytes['A' * SH_FONT_RECORD_BYTES + 2] = 0x42;
    bytes['A' * SH_FONT_RECORD_BYTES + 8] = 0x18;
    bytes['B' * SH_FONT_RECORD_BYTES] = 3;
    bytes['B' * SH_FONT_RECORD_BYTES + 1] = 0xc0;
    bytes['B' * SH_FONT_RECORD_BYTES + 2] = 0x40;
    bytes[255 * SH_FONT_RECORD_BYTES + 8] = 1;
}

int main(void)
{
    uint8_t bytes[SH_FONT_BYTES], pixels[10 * 14], expected[sizeof(pixels)];
    SHFont font, before;
    size_t width = 999, height = 999;
    fixture(bytes);
    assert(sh_font_decode(&font, bytes, sizeof(bytes)) == 0);
    assert(sh_font_measure(&font, (const uint8_t *)"AB\nB\rA", 6,
                           &width, &height) == 0 && width == 9 && height == 18);
    assert(sh_font_measure(&font, NULL, 0, &width, &height) == 0 &&
           width == 0 && height == 0);

    memset(pixels, 17, sizeof(pixels));
    memset(expected, 17, sizeof(expected));
    assert(sh_font_draw(&font, (const uint8_t *)"A", 1, pixels, sizeof(pixels),
                        10, 10, 14, 1, 1, 9, 0, 3) == 0);
    expected[1 * 14 + 1] = expected[1 * 14 + 8] = 9;
    expected[2 * 14 + 2] = expected[2 * 14 + 7] = 9;
    expected[8 * 14 + 4] = expected[8 * 14 + 5] = 9;
    assert(memcmp(pixels, expected, sizeof(pixels)) == 0);

    /* All four edges clip, and shadow is drawn before foreground: the B
     * foreground at (1,1) replaces the first row's shadow at that position. */
    memset(pixels, 17, sizeof(pixels));
    memset(expected, 17, sizeof(expected));
    assert(sh_font_draw(&font, (const uint8_t *)"B", 1, pixels, sizeof(pixels),
                        2, 2, 14, 0, 0, 9, 1, 3) == 0);
    expected[0] = expected[1] = expected[14 + 1] = 9;
    assert(memcmp(pixels, expected, sizeof(pixels)) == 0);
    memset(pixels, 17, sizeof(pixels));
    memset(expected, 17, sizeof(expected));
    assert(sh_font_draw(&font, (const uint8_t *)"A", 1, pixels, sizeof(pixels),
                        10, 10, 14, -1, -1, 9, 1, 3) == 0);
    expected[0] = expected[5] = 9;
    expected[7] = expected[1 * 14 + 1] = expected[1 * 14 + 6] = 3;
    expected[6 * 14 + 2] = expected[6 * 14 + 3] = 9;
    expected[7 * 14 + 3] = expected[7 * 14 + 4] = 3;
    assert(memcmp(pixels, expected, sizeof(pixels)) == 0);

    /* Newline, variable advance, and unsigned character 255. */
    memset(pixels, 17, sizeof(pixels));
    memset(expected, 17, sizeof(expected));
    const uint8_t text[] = {'B', 'A', '\n', 255};
    assert(sh_font_draw(&font, text, sizeof(text), pixels, sizeof(pixels),
                        10, 10, 14, 0, -8, 9, 0, 3) == 0);
    expected[9 * 14 + 7] = 9;
    assert(memcmp(pixels, expected, sizeof(pixels)) == 0);

    before = font;
    bytes[255 * SH_FONT_RECORD_BYTES] = 0;
    assert(sh_font_decode(&font, bytes, sizeof(bytes)) == -1 && errno == EINVAL);
    assert(memcmp(&font, &before, sizeof(font)) == 0);
    bytes[255 * SH_FONT_RECORD_BYTES] = 9;
    assert(sh_font_decode(&font, bytes, sizeof(bytes)) == -1 && errno == EINVAL);
    fixture(bytes);
    assert(sh_font_decode(&font, bytes, sizeof(bytes) - 1) == -1);
    assert(sh_font_decode(&font, bytes, sizeof(bytes) + 1) == -1);
    assert(sh_font_decode(NULL, bytes, sizeof(bytes)) == -1);
    assert(sh_font_decode(&font, NULL, sizeof(bytes)) == -1);
    assert(memcmp(&font, &before, sizeof(font)) == 0);

    /* Bad extents fail before touching any pixel or padding. Extremely
     * distant origins must remain safe and leave the complete surface alone. */
    memset(pixels, 17, sizeof(pixels));
    memcpy(expected, pixels, sizeof(pixels));
    assert(sh_font_draw(&font, text, sizeof(text), pixels, 1,
                        10, 10, 14, 0, 0, 9, 1, 3) == -1);
    assert(sh_font_draw(&font, text, sizeof(text), pixels, sizeof(pixels),
                        10, 10, 9, 0, 0, 9, 1, 3) == -1);
    assert(sh_font_draw(&font, text, sizeof(text), pixels, SIZE_MAX,
                        10, 3, SIZE_MAX, 0, 0, 9, 1, 3) == -1);
    assert(sh_font_draw(&font, text, sizeof(text), pixels, SIZE_MAX,
                        SIZE_MAX, 1, SIZE_MAX, 0, 0, 9, 1, 3) == -1);
    assert(sh_font_draw(&font, NULL, 1, pixels, sizeof(pixels),
                        10, 10, 14, 0, 0, 9, 1, 3) == -1);
    assert(sh_font_draw(&font, text, sizeof(text), NULL, sizeof(pixels),
                        10, 10, 14, 0, 0, 9, 1, 3) == -1);
    for (unsigned i = 0; i < 4; ++i) {
        int x = (i & 1) ? INT_MAX : INT_MIN;
        int y = (i & 2) ? INT_MAX : INT_MIN;
        assert(sh_font_draw(&font, text, sizeof(text), pixels, sizeof(pixels),
                            10, 10, 14, x, y, 9, 1, 3) == 0);
    }
    assert(memcmp(pixels, expected, sizeof(pixels)) == 0);
    assert(sh_font_draw(&font, text, sizeof(text), NULL, 0,
                        0, 0, 0, 0, 0, 9, 1, 3) == 0);
    width = height = 999;
    assert(sh_font_measure(NULL, text, sizeof(text), &width, &height) == -1);
    assert(width == 999 && height == 999);
    font.glyphs['B'][0] = 0;
    assert(sh_font_measure(&font, text, sizeof(text), &width, &height) == -1);
    assert(width == 999 && height == 999);
    puts("FONT: synthetic glyphs, spacing, multiline, shadows, clipping, padding, malformed resources, and bounds: PASS");
    return 0;
}
