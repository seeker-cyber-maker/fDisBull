#import "SHUI.h"

/* The private original comparison qualified these image-slot compositions for
 * all 39 visible cards of puzzle 0. See research/clue-format.md. The AppKit
 * bitmap upload and display still require execution on macOS. */
static void SHCopyClueTile(uint8_t *destination, unsigned width,
                           unsigned left, unsigned top,
                           const uint8_t source[32][32]) {
    for (unsigned y = 0; y < 32; ++y)
        for (unsigned x = 0; x < 32; ++x)
            destination[(top + y) * width + left + x] = source[y][x] & 15;
}

static void SHClueMaskAndInk(uint8_t *destination, unsigned width,
                             unsigned left, unsigned top,
                             const uint8_t mask[32][32],
                             const uint8_t ink[32][32]) {
    for (unsigned y = 0; y < 32; ++y) {
        for (unsigned x = 0; x < 32; ++x) {
            unsigned offset = (top + y) * width + left + x;
            destination[offset] =
                (uint8_t)(((destination[offset] & mask[y][x]) | ink[y][x]) & 15);
        }
    }
}

NSArray<NSImage *> *SHClueImages(const SherlockPuzzle *puzzle,
                               const uint8_t pixels[46][32][32]) {
    if (!puzzle || !pixels || puzzle->clue_count > SHERLOCK_MAX_CLUES)
        return @[];

    NSMutableArray<NSImage *> *images =
        [NSMutableArray arrayWithCapacity:puzzle->clue_count];
    for (unsigned index = 0; index < puzzle->clue_count; ++index) {
        const SherlockClue *clue = &puzzle->clues[index];
        if (clue->type > SHERLOCK_UNUSED || clue->a >= 36 ||
            (clue->type != SHERLOCK_UNUSED && clue->b >= 36) ||
            ((clue->type == SHERLOCK_BETWEEN ||
              clue->type == SHERLOCK_NOT_BETWEEN) && clue->c >= 36))
            return @[];

        /* Reference-only cards occasionally occur in a horizontal original
         * slot (for example seed 1465, slot 63). Type alone cannot determine
         * orientation. The portable state helper retains a synthetic fallback. */
        BOOL horizontal = sh_puzzle_clue_group(puzzle, index) == 1;
        if ((horizontal && clue->type <= SHERLOCK_NOT_SAME_COLUMN) ||
            (!horizontal && clue->type >= SHERLOCK_NEXT_TO &&
             clue->type <= SHERLOCK_NOT_BETWEEN)) return @[];
        unsigned width = horizontal ? 96u : 32u;
        unsigned height = horizontal ? 32u : 64u;
        unsigned slots[3] = {clue->a, clue->b, clue->c};
        uint8_t indices[96 * 64];

        if (clue->type == SHERLOCK_NEXT_TO ||
            clue->type == SHERLOCK_NOT_NEXT_TO) slots[2] = clue->a;
        if (clue->type == SHERLOCK_LEFT_OF) {
            slots[1] = 45; /* The three-dot image is not a semantic object. */
            slots[2] = clue->b;
        }
        if (clue->type == SHERLOCK_UNUSED) slots[1] = slots[2] = 36;

        for (unsigned part = 0; part < (horizontal ? 3u : 2u); ++part)
            SHCopyClueTile(indices, width, horizontal ? part * 32 : 0,
                           horizontal ? 0 : part * 32, pixels[slots[part]]);

        if (clue->type == SHERLOCK_BETWEEN ||
            clue->type == SHERLOCK_NOT_BETWEEN) {
            for (unsigned part = 0; part < 3; ++part)
                SHClueMaskAndInk(indices, width, part * 32, 0,
                                 pixels[39 + part * 2], pixels[40 + part * 2]);
        }
        if (clue->type == SHERLOCK_NOT_SAME_COLUMN)
            SHClueMaskAndInk(indices, width, 0, 16, pixels[37], pixels[38]);
        if (clue->type == SHERLOCK_NOT_NEXT_TO ||
            clue->type == SHERLOCK_NOT_BETWEEN)
            SHClueMaskAndInk(indices, width, 32, 0, pixels[37], pixels[38]);

        NSBitmapImageRep *bitmap = [[NSBitmapImageRep alloc]
            initWithBitmapDataPlanes:NULL pixelsWide:width pixelsHigh:height
            bitsPerSample:8 samplesPerPixel:4 hasAlpha:YES isPlanar:NO
            colorSpaceName:NSDeviceRGBColorSpace bytesPerRow:width * 4
            bitsPerPixel:32];
        if (!bitmap || !bitmap.bitmapData) return @[];
        unsigned char *rgba = bitmap.bitmapData;
        for (unsigned y = 0; y < height; ++y) {
            for (unsigned x = 0; x < width; ++x) {
                unsigned color = indices[y * width + x];
                unsigned offset = y * (unsigned)bitmap.bytesPerRow + x * 4;
                rgba[offset] = shi_palette[color][0];
                rgba[offset + 1] = shi_palette[color][1];
                rgba[offset + 2] = shi_palette[color][2];
                rgba[offset + 3] = 255;
            }
        }

        /* Bitmap rows above are top-to-bottom. Callers draw with
         * respectFlipped:YES in their flipped game view. */
        NSImage *image = [[NSImage alloc] initWithSize:NSMakeSize(width, height)];
        if (!image) return @[];
        [image addRepresentation:bitmap];
        [images addObject:image];
    }
    return images;
}
