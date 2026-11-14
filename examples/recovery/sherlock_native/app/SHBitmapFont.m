#import "SHBitmapFont.h"
#include "../media/sherlock_font.h"
#include <math.h>
#include <string.h>

static SHFont SHCanvasFont;

BOOL SHBitmapFontIsAvailable(void)
{
    static dispatch_once_t once;
    static BOOL available = NO;
    dispatch_once(&once, ^{
        NSString *path = [NSBundle.mainBundle pathForResource:@"SherlockFont"
                                                      ofType:@"bin"];
        NSData *data = path ? [NSData dataWithContentsOfFile:path] : nil;
        available = data && sh_font_decode(&SHCanvasFont, data.bytes, data.length) == 0;
    });
    return available;
}

static void SHNativeText(NSString *text, NSRect rect, CGFloat size,
                          NSColor *color, BOOL centered, NSColor *shadow)
{
    NSMutableParagraphStyle *paragraph = [[NSMutableParagraphStyle alloc] init];
    paragraph.alignment = centered ? NSTextAlignmentCenter : NSTextAlignmentLeft;
    paragraph.lineBreakMode = NSLineBreakByWordWrapping;
    NSMutableDictionary *attributes = [@{
        NSFontAttributeName:[NSFont monospacedSystemFontOfSize:size
                                                     weight:NSFontWeightRegular],
        NSForegroundColorAttributeName:shadow ?: color,
        NSParagraphStyleAttributeName:paragraph
    } mutableCopy];
    if (shadow) [text drawInRect:NSOffsetRect(rect, 1, 1) withAttributes:attributes];
    attributes[NSForegroundColorAttributeName] = color;
    [text drawInRect:rect withAttributes:attributes];
}

static NSArray<NSData *> *SHWrappedLines(NSString *text, NSUInteger width,
                                          NSUInteger maxLines)
{
    NSString *normalized = [[text stringByReplacingOccurrencesOfString:@"\r\n"
                                                            withString:@"\n"]
        stringByReplacingOccurrencesOfString:@"\r" withString:@"\n"];
    NSMutableArray<NSData *> *lines = [NSMutableArray array];
    for (NSString *paragraph in [normalized componentsSeparatedByString:@"\n"]) {
        NSData *data = [paragraph dataUsingEncoding:NSASCIIStringEncoding];
        const uint8_t *bytes = data.bytes;
        NSUInteger start = 0;
        if (!data.length) [lines addObject:[NSData data]];
        while (start < data.length && lines.count < maxLines) {
            NSUInteger end = start, advance = 0, space = NSNotFound;
            while (end < data.length) {
                NSUInteger next = SHCanvasFont.glyphs[bytes[end]][0];
                if (advance + next > width) break;
                advance += next;
                if (bytes[end] == ' ') space = end;
                ++end;
            }
            NSUInteger nextStart = end;
            if (end == start) { /* A narrow rectangle clips one glyph. */
                end = start + 1;
                nextStart = end;
            } else if (end < data.length && space != NSNotFound && space > start) {
                end = space;
                nextStart = space + 1;
                while (nextStart < data.length && bytes[nextStart] == ' ')
                    ++nextStart;
            }
            [lines addObject:[data subdataWithRange:NSMakeRange(start, end - start)]];
            start = nextStart;
        }
        if (lines.count >= maxLines) break;
    }
    return lines;
}

void SHDrawBitmapText(NSString *text, NSRect rect, CGFloat size,
                       NSColor *color, BOOL centered, NSColor *shadow)
{
    if (!text.length || !color || !isfinite(size) || size <= 0 || !isfinite(rect.origin.x) ||
        !isfinite(rect.origin.y) || !isfinite(rect.size.width) ||
        !isfinite(rect.size.height) || rect.size.width <= 0 || rect.size.height <= 0)
        return;
    NSData *ascii = [text dataUsingEncoding:NSASCIIStringEncoding
                     allowLossyConversion:NO];
    if (size > 16 || !ascii || !SHBitmapFontIsAvailable() ||
        rect.size.width > 4096 || rect.size.height > 4096) {
        SHNativeText(text, rect, size, color, centered, shadow);
        return;
    }
    NSUInteger width = (NSUInteger)ceil(rect.size.width);
    NSUInteger height = (NSUInteger)ceil(rect.size.height);
    NSMutableData *mask = [NSMutableData dataWithLength:width * height];
    if (!mask) { SHNativeText(text, rect, size, color, centered, shadow); return; }
    NSArray<NSData *> *lines = SHWrappedLines(text, width,
        (height + SH_FONT_LINE_HEIGHT - 1) / SH_FONT_LINE_HEIGHT);
    for (NSUInteger row = 0; row < lines.count; ++row) {
        NSData *line = lines[row];
        size_t advance = 0, ignored = 0;
        if (sh_font_measure(&SHCanvasFont, line.bytes, line.length,
                             &advance, &ignored) != 0) return;
        int x = centered ? (int)floor(((double)width - advance) / 2.0) : 0;
        if (sh_font_draw(&SHCanvasFont, line.bytes, line.length, mask.mutableBytes,
                          mask.length, width, height, width, x,
                          (int)(row * SH_FONT_LINE_HEIGHT), 2, shadow != nil, 1) != 0)
            return;
    }
    NSColor *colors[3] = {nil, shadow, color};
    uint8_t rgba[3][4] = {{0}};
    for (unsigned i = 1; i < 3; ++i) {
        if (!colors[i]) continue;
        NSColor *rgb = [colors[i] colorUsingColorSpace:NSColorSpace.sRGBColorSpace];
        if (!rgb) { SHNativeText(text, rect, size, color, centered, shadow); return; }
        CGFloat r, g, b, a;
        [rgb getRed:&r green:&g blue:&b alpha:&a];
        rgba[i][0] = (uint8_t)lround(r * 255);
        rgba[i][1] = (uint8_t)lround(g * 255);
        rgba[i][2] = (uint8_t)lround(b * 255);
        rgba[i][3] = (uint8_t)lround(a * 255);
    }
    NSBitmapImageRep *bitmap = [[NSBitmapImageRep alloc]
        initWithBitmapDataPlanes:NULL pixelsWide:width pixelsHigh:height
        bitsPerSample:8 samplesPerPixel:4 hasAlpha:YES isPlanar:NO
        colorSpaceName:NSDeviceRGBColorSpace
        bitmapFormat:NSBitmapFormatAlphaNonpremultiplied
        bytesPerRow:width * 4 bitsPerPixel:32];
    if (!bitmap || !bitmap.bitmapData) {
        SHNativeText(text, rect, size, color, centered, shadow);
        return;
    }
    const uint8_t *indices = mask.bytes;
    for (NSUInteger y = 0; y < height; ++y)
        for (NSUInteger x = 0; x < width; ++x)
            memcpy(bitmap.bitmapData + y * (NSUInteger)bitmap.bytesPerRow + x * 4,
                   rgba[indices[y * width + x]], 4);
    NSImage *image = [[NSImage alloc] initWithSize:NSMakeSize(width, height)];
    [image addRepresentation:bitmap];
    [NSGraphicsContext saveGraphicsState];
    NSRectClip(rect);
    NSGraphicsContext.currentContext.imageInterpolation = NSImageInterpolationNone;
    NSGraphicsContext.currentContext.shouldAntialias = NO;
    [image drawInRect:NSMakeRect(floor(rect.origin.x), floor(rect.origin.y), width, height)
            fromRect:NSZeroRect operation:NSCompositingOperationSourceOver fraction:1
       respectFlipped:YES hints:nil];
    [NSGraphicsContext restoreGraphicsState];
}
