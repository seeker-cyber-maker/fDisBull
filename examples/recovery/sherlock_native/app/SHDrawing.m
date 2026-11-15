#import "SHUI.h"

@implementation SHActionButton
- (void)rightMouseDown:(NSEvent *)event { (void)event; [self performClick:nil]; }
@end

@implementation SHActionPopUp
- (void)rightMouseDown:(NSEvent *)event { (void)event; [self performClick:nil]; }
@end

NSArray<NSNumber *> *SHDefaultColors(void) {
    /* Both original 11-word arrays and all visible role swatches agree.
     * See research/preferences-recovery.json for addresses and receipts. */
    return @[@8, @7, @9, @8, @15, @0, @1, @7, @15, @14, @0];
}

NSArray<NSNumber *> *SHNormalizedColors(id colors) {
    if (![colors isKindOfClass:NSArray.class] ||
        ([colors count] != 11 && [colors count] != 6)) return SHDefaultColors();
    for (id value in colors)
        if (![value isKindOfClass:NSNumber.class] || [value unsignedIntegerValue] > 15)
            return SHDefaultColors();
    if ([colors count] == 11) return [colors copy];
    /* Migrate the initial native six-role prototype without collapsing player
     * identity. Empty-image colors now come from SHI record 36. */
    return @[colors[0], colors[0], @0, colors[4], colors[0], colors[4],
             colors[2], colors[1], @0, colors[1], @0];
}

NSColor *SHColor(NSUInteger index) {
    index &= 15;
    return [NSColor colorWithSRGBRed:shi_palette[index][0] / 255.0
                              green:shi_palette[index][1] / 255.0
                               blue:shi_palette[index][2] / 255.0 alpha:1.0];
}

NSImage *SHImage(const uint8_t pixels[32][32], BOOL halfSize) {
    NSInteger size = halfSize ? 16 : 32;
    NSBitmapImageRep *bitmap = [[NSBitmapImageRep alloc]
        initWithBitmapDataPlanes:NULL pixelsWide:size pixelsHigh:size
        bitsPerSample:8 samplesPerPixel:4 hasAlpha:YES isPlanar:NO
        colorSpaceName:NSDeviceRGBColorSpace bytesPerRow:size * 4 bitsPerPixel:32];
    if (!bitmap || !bitmap.bitmapData) return nil;
    unsigned char *data = bitmap.bitmapData;
    for (NSInteger y = 0; y < size; ++y) {
        for (NSInteger x = 0; x < size; ++x) {
            unsigned color = pixels[y * (halfSize ? 2 : 1)]
                                   [x * (halfSize ? 2 : 1)] & 15;
            NSUInteger at = (NSUInteger)(y * size + x) * 4;
            data[at] = shi_palette[color][0];
            data[at + 1] = shi_palette[color][1];
            data[at + 2] = shi_palette[color][2];
            data[at + 3] = 255;
        }
    }
    NSImage *image = [[NSImage alloc] initWithSize:NSMakeSize(size, size)];
    [image addRepresentation:bitmap];
    return image;
}

NSImage *SHPatternImage(const uint8_t rows[8], NSUInteger fill, NSUInteger mask) {
    uint8_t pixels[32][32];
    for (unsigned y = 0; y < 32; ++y) for (unsigned x = 0; x < 32; ++x)
        pixels[y][x] = (uint8_t)((rows[y % 8] & (1u << (x % 8))) ? mask : fill);
    return SHImage(pixels, NO);
}

NSArray<NSImage *> *SHImages(const uint8_t pixels[46][32][32], BOOL halfSize) {
    NSMutableArray<NSImage *> *images = [NSMutableArray arrayWithCapacity:46];
    for (unsigned i = 0; i < 46; ++i) {
        NSImage *image = SHImage(pixels[i], halfSize);
        if (!image) return @[];
        [images addObject:image];
    }
    return images;
}

void SHMessage(NSString *title, NSString *message) {
    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = title ?: @"Sherlock";
    alert.informativeText = message ?: @"";
    [alert addButtonWithTitle:@"OK"];
    [alert runModal];
}

NSString *SHAsk(NSString *title, NSString *message, NSString *initial) {
    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = title;
    alert.informativeText = message;
    NSTextField *entry = [[NSTextField alloc] initWithFrame:NSMakeRect(0, 0, 360, 26)];
    entry.stringValue = initial ?: @"";
    alert.accessoryView = entry;
    [alert addButtonWithTitle:@"OK"];
    [alert addButtonWithTitle:@"Cancel"];
    alert.window.initialFirstResponder = entry;
    if ([alert runModal] != NSAlertFirstButtonReturn) return nil;
    return [entry.stringValue stringByTrimmingCharactersInSet:
            [NSCharacterSet whitespaceAndNewlineCharacterSet]];
}

NSButton *SHButton(NSString *title, NSRect frame, id target, SEL action) {
    NSButton *button = [[SHActionButton alloc] initWithFrame:frame];
    button.title = title;
    button.bezelStyle = NSBezelStyleRounded;
    button.target = target;
    button.action = action;
    return button;
}

NSTextField *SHLabel(NSString *text, NSRect frame) {
    NSTextField *label = [[NSTextField alloc] initWithFrame:frame];
    label.stringValue = text;
    label.editable = NO;
    label.selectable = NO;
    label.bordered = NO;
    label.drawsBackground = NO;
    label.maximumNumberOfLines = 0;
    label.cell.wraps = YES;
    label.cell.scrollable = NO;
    return label;
}

NSString *SHTime(uint64_t milliseconds) {
    unsigned long long seconds = milliseconds / 1000;
    return [NSString stringWithFormat:@"%02llu:%02llu:%02llu",
            seconds / 3600, (seconds / 60) % 60, seconds % 60];
}

BOOL SHLoadProfileImages(NSDictionary *profile, NSString *defaultPath,
                         uint8_t pixels[46][32][32]) {
    NSData *stored = profile[@"images"];
    if (!stored) stored = profile[@"legacyImages"];
    if ([stored isKindOfClass:[NSData class]] && stored.length == 46 * 32 * 32) {
        [stored getBytes:pixels length:stored.length];
        const uint8_t *flat = (const uint8_t *)pixels;
        for (NSUInteger i = 0; i < stored.length; ++i)
            if (flat[i] > 15) return NO;
        return YES;
    }
    NSString *path = profile[@"imagePath"];
    if (path.length) return shi_load(path.fileSystemRepresentation, pixels) == 0;
    return defaultPath.length &&
           shi_load(defaultPath.fileSystemRepresentation, pixels) == 0;
}
