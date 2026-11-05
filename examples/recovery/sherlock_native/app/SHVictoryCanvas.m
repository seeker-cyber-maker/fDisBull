#import "SHVictoryCanvas.h"
#import "SHUI.h"
#include "../state/sherlock_victory.h"
#include "../media/shi.h"
#include <string.h>

@implementation SHVictoryCanvas {
    SHVictory _motion;
    NSData *_tiles;
    NSBitmapImageRep *_bitmap;
}

- (instancetype)initWithTiles:(NSData *)tiles randomState:(uint32_t)randomState {
    self = [super init];
    if (!self || tiles.length != 46 * 32 * 32) return nil;
    _tiles = [tiles copy];
    _bitmap = [[NSBitmapImageRep alloc]
        initWithBitmapDataPlanes:NULL pixelsWide:640 pixelsHigh:350
        bitsPerSample:8 samplesPerPixel:4 hasAlpha:YES isPlanar:NO
        colorSpaceName:NSDeviceRGBColorSpace
        bitmapFormat:NSBitmapFormatAlphaNonpremultiplied
        bytesPerRow:640 * 4 bitsPerPixel:32];
    if (!_bitmap || !_bitmap.bitmapData) return nil;
    memset(_bitmap.bitmapData, 0, (size_t)_bitmap.bytesPerRow * 350);
    sh_victory_init(&_motion, randomState);
    return self;
}

- (void)stamp:(unsigned)object at:(SHVictoryPoint)point half:(BOOL)half {
    if (object >= 46) return;
    const uint8_t (*pixels)[32][32] = _tiles.bytes;
    int size = half ? 16 : 32, sample = half ? 2 : 1;
    for (int y = 0; y < size; ++y) {
        int destY = point.y + y;
        if (destY < 0 || destY >= 350) continue;
        for (int x = 0; x < size; ++x) {
            int destX = point.x + x;
            if (destX < 0 || destX >= 640) continue;
            unsigned color = pixels[object][y * sample][x * sample] & 15;
            unsigned char *out = _bitmap.bitmapData +
                (size_t)destY * (size_t)_bitmap.bytesPerRow + (size_t)destX * 4;
            memcpy(out, shi_palette[color], 3);
            out[3] = 255;
        }
    }
}

- (BOOL)advance {
    SHVictoryEvent event;
    enum SHVictoryEventKind kind = sh_victory_next(&_motion, &event);
    if (kind == SH_VICTORY_DONE) return NO;
    if (kind == SH_VICTORY_BURST && event.frame == 0)
        SHPlaySound(@"choose", self.soundEnabled);
    for (unsigned i = 0; i < event.count; ++i)
        [self stamp:kind == SH_VICTORY_CLEAR ? 36u : event.object
                  at:event.points[i] half:kind == SH_VICTORY_BURST];
    return YES;
}

- (void)requestSkip { sh_victory_request_skip(&_motion); }

- (void)draw {
    /* A fresh image avoids a cached CGImage hiding mutations to bitmapData. */
    NSImage *image = [[NSImage alloc] initWithSize:NSMakeSize(640, 350)];
    [image addRepresentation:_bitmap];
    [image drawInRect:NSMakeRect(0, 0, 640, 350) fromRect:NSZeroRect
        operation:NSCompositingOperationSourceOver fraction:1
        respectFlipped:YES hints:nil];
}
@end
