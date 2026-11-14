#import "SHUI.h"
#include <dispatch/dispatch.h>
#include <string.h>

/* Pixel data belongs to the owner's private resource pack. This fixed profile
 * has sixteen eight-row patterns, stored in bit-0-at-left editor order. */
NSData *SHPresetPatterns(void) {
    static NSData *patterns;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        NSString *path = [NSBundle.mainBundle.resourcePath
                           stringByAppendingPathComponent:@"PatternPresets.bin"];
        NSData *data = path ? [NSData dataWithContentsOfFile:path] : nil;
        if (data.length == 16 * 8) patterns = data;
    });
    return patterns;
}

NSData *SHDefaultPattern(void) {
    NSData *patterns = SHPresetPatterns();
    return patterns.length == 16 * 8 ?
        [patterns subdataWithRange:NSMakeRange(2 * 8, 8)] : nil;
}

@implementation SHModalEditor
- (instancetype)initWithTitle:(NSString *)title size:(NSSize)size {
    if ((self = [super init])) {
        self.panel = [[NSPanel alloc] initWithContentRect:NSMakeRect(0, 0, size.width, size.height)
            styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
            backing:NSBackingStoreBuffered defer:NO];
        self.panel.title = title;
        self.panel.delegate = self;
        self.panel.releasedWhenClosed = NO;
    }
    return self;
}
- (BOOL)run {
    [self.panel center]; [self.panel makeKeyAndOrderFront:nil];
    [NSApp runModalForWindow:self.panel];
    [self.panel orderOut:nil];
    return self.accepted;
}
- (void)done:(id)sender { (void)sender; self.accepted = YES; [NSApp stopModal]; }
- (void)abort:(id)sender { (void)sender; self.accepted = NO; [NSApp stopModal]; }
- (BOOL)windowShouldClose:(NSWindow *)sender {
    (void)sender; [self abort:nil]; return NO;
}
@end

@implementation SHPaletteView
- (BOOL)isFlipped { return YES; }
- (void)drawRect:(NSRect)dirtyRect {
    (void)dirtyRect;
    CGFloat width = self.bounds.size.width / 4;
    CGFloat height = self.bounds.size.height / 4;
    for (NSUInteger index = 0; index < 16; ++index) {
        NSRect cell = NSMakeRect((index % 4) * width, (index / 4) * height, width, height);
        [SHColor(index) setFill]; NSRectFill(NSInsetRect(cell, 1, 1));
        if (index == self.currentColor) {
            [NSColor.whiteColor setStroke];
            NSBezierPath *outline = [NSBezierPath bezierPathWithRect:NSInsetRect(cell, 3, 3)];
            outline.lineWidth = 3; [outline stroke];
            [NSColor.blackColor setStroke];
            outline = [NSBezierPath bezierPathWithRect:NSInsetRect(cell, 1, 1)];
            outline.lineWidth = 1; [outline stroke];
        }
    }
}
- (void)mouseDown:(NSEvent *)event {
    NSPoint p = [self convertPoint:event.locationInWindow fromView:nil];
    if (!NSPointInRect(p, self.bounds)) return;
    NSUInteger index = (NSUInteger)(p.x / (self.bounds.size.width / 4)) +
                       (NSUInteger)(p.y / (self.bounds.size.height / 4)) * 4;
    self.currentColor = MIN(index, 15);
    [self.receiver pickColor:self.currentColor];
    self.needsDisplay = YES;
}
- (void)rightMouseDown:(NSEvent *)event { [self mouseDown:event]; }
@end

@interface SHColorEditor : SHModalEditor <SHColorChoice>
@property(nonatomic, strong) NSMutableArray<NSNumber *> *colors;
@property(nonatomic, strong) NSPopUpButton *roles;
@property(nonatomic, strong) SHPaletteView *palette;
@property(nonatomic, strong) NSTextField *preview;
@end

@implementation SHColorEditor
- (instancetype)initWithColors:(NSArray *)colors {
    if ((self = [super initWithTitle:@"Colors" size:NSMakeSize(500, 320)])) {
        self.colors = [SHNormalizedColors(colors) mutableCopy];
        NSView *view = self.panel.contentView;
        self.roles = [[SHActionPopUp alloc] initWithFrame:NSMakeRect(25, 265, 240, 28) pullsDown:NO];
        [self.roles addItemsWithTitles:@[@"Border primary", @"Border secondary", @"Border outline",
            @"Background fill", @"Background mask", @"Menu background", @"Menu box bgnd",
            @"Menu border 1", @"Menu border 2", @"Menu text", @"Menu text shadow"]];
        self.roles.target = self; self.roles.action = @selector(roleChanged:);
        [view addSubview:self.roles];
        self.palette = [[SHPaletteView alloc] initWithFrame:NSMakeRect(285, 85, 180, 180)];
        self.palette.receiver = self; [view addSubview:self.palette];
        self.preview = SHLabel(@"Selected display color", NSMakeRect(25, 110, 235, 125));
        self.preview.drawsBackground = YES; self.preview.bordered = YES;
        self.preview.alignment = NSTextAlignmentCenter;
        [view addSubview:self.preview];
        [view addSubview:SHLabel(@"Select a display role, then a color.", NSMakeRect(25, 63, 440, 24))];
        [view addSubview:SHButton(@"Abort", NSMakeRect(25, 15, 110, 32), self, @selector(abort:))];
        [view addSubview:SHButton(@"Defaults", NSMakeRect(190, 15, 110, 32), self, @selector(defaults:))];
        [view addSubview:SHButton(@"Done", NSMakeRect(355, 15, 110, 32), self, @selector(done:))];
        [self roleChanged:nil];
    }
    return self;
}
- (void)roleChanged:(id)sender {
    (void)sender;
    NSUInteger role = (NSUInteger)self.roles.indexOfSelectedItem;
    self.palette.currentColor = [self.colors[role] unsignedIntegerValue];
    self.palette.needsDisplay = YES;
    self.preview.backgroundColor = SHColor(self.palette.currentColor);
    const uint8_t *rgb = shi_palette[self.palette.currentColor & 15];
    unsigned luminance = rgb[0] * 299u + rgb[1] * 587u + rgb[2] * 114u;
    self.preview.textColor = luminance < 128000 ? NSColor.whiteColor : NSColor.blackColor;
    self.preview.stringValue = self.roles.titleOfSelectedItem;
}
- (void)pickColor:(NSUInteger)index {
    self.colors[(NSUInteger)self.roles.indexOfSelectedItem] = @(index);
    [self roleChanged:nil];
}
- (void)defaults:(id)sender {
    (void)sender; self.colors = [SHDefaultColors() mutableCopy];
    [self roleChanged:nil];
}
@end

BOOL SHShowColorEditor(NSMutableDictionary *profile) {
    SHColorEditor *editor = [[SHColorEditor alloc] initWithColors:profile[@"colors"]];
    if (![editor run]) return NO;
    profile[@"colors"] = [editor.colors copy];
    return YES;
}

@class SHPatternEditor;
@interface SHPatternView : NSView
@property(nonatomic, weak) SHPatternEditor *editor;
@end

@interface SHPatternEditor : SHModalEditor {
@public uint8_t pattern[8];
}
@property(nonatomic, strong) SHPatternView *grid;
@property(nonatomic, strong) NSView *preview;
@property(nonatomic, strong) NSPopUpButton *presets;
@property(nonatomic, strong) NSColor *onColor;
@property(nonatomic, strong) NSColor *offColor;
@property(nonatomic) NSUInteger fillIndex;
@property(nonatomic) NSUInteger maskIndex;
- (void)refresh;
@end

@interface SHPatternPreview : NSView
@property(nonatomic, weak) SHPatternEditor *editor;
@end

@implementation SHPatternPreview
- (BOOL)isFlipped { return YES; }
- (void)drawRect:(NSRect)dirtyRect {
    (void)dirtyRect;
    NSGraphicsContext.currentContext.imageInterpolation = NSImageInterpolationNone;
    NSImage *image = SHPatternImage(self.editor->pattern, self.editor.fillIndex,
                                    self.editor.maskIndex);
    NSRectClip(self.bounds);
    for (CGFloat y = 0; y < self.bounds.size.height; y += 32)
        for (CGFloat x = 0; x < self.bounds.size.width; x += 32)
            [image drawInRect:NSMakeRect(x, y, 32, 32) fromRect:NSZeroRect
                operation:NSCompositingOperationCopy fraction:1 respectFlipped:YES hints:nil];
}
@end

@implementation SHPatternView {
    BOOL _painting;
    BOOL _value;
}
- (BOOL)isFlipped { return YES; }
- (void)drawRect:(NSRect)dirtyRect {
    (void)dirtyRect;
    CGFloat cell = self.bounds.size.width / 8;
    for (unsigned y = 0; y < 8; ++y) for (unsigned x = 0; x < 8; ++x) {
        NSColor *color = (self.editor->pattern[y] & (1u << x))
                      ? self.editor.onColor : self.editor.offColor;
        [color setFill];
        NSRectFill(NSMakeRect(x * cell, y * cell, cell, cell));
        [NSColor.grayColor setStroke];
        [[NSBezierPath bezierPathWithRect:NSMakeRect(x * cell, y * cell, cell, cell)] stroke];
    }
}
- (void)paint:(NSEvent *)event begin:(BOOL)begin {
    NSPoint p = [self convertPoint:event.locationInWindow fromView:nil];
    if (!NSPointInRect(p, self.bounds)) return;
    unsigned x = (unsigned)(p.x / (self.bounds.size.width / 8));
    unsigned y = (unsigned)(p.y / (self.bounds.size.height / 8));
    if (begin) _value = !(self.editor->pattern[y] & (1u << x));
    if (_value) self.editor->pattern[y] |= (uint8_t)(1u << x);
    else self.editor->pattern[y] &= (uint8_t)~(1u << x);
    [self.editor refresh];
}
- (void)mouseDown:(NSEvent *)event { _painting = YES; [self paint:event begin:YES]; }
- (void)mouseDragged:(NSEvent *)event { if (_painting) [self paint:event begin:NO]; }
- (void)mouseUp:(NSEvent *)event { (void)event; _painting = NO; }
- (void)rightMouseDown:(NSEvent *)event { [self mouseDown:event]; }
- (void)rightMouseDragged:(NSEvent *)event { [self mouseDragged:event]; }
- (void)rightMouseUp:(NSEvent *)event { [self mouseUp:event]; }
@end

@implementation SHPatternEditor
- (instancetype)initWithProfile:(NSDictionary *)profile {
    NSData *presets = SHPresetPatterns();
    if (presets.length != 16 * 8) return nil;
    if ((self = [super initWithTitle:@"Background pattern" size:NSMakeSize(500, 360)])) {
        NSData *data = profile[@"pattern"];
        if (data.length == 8) [data getBytes:pattern length:8];
        NSArray *colors = SHNormalizedColors(profile[@"colors"]);
        self.fillIndex = [colors[3] unsignedIntegerValue];
        self.maskIndex = [colors[4] unsignedIntegerValue];
        self.onColor = SHColor(self.maskIndex);
        self.offColor = SHColor(self.fillIndex);
        self.grid = [[SHPatternView alloc] initWithFrame:NSMakeRect(20, 70, 256, 256)];
        self.grid.editor = self; [self.panel.contentView addSubview:self.grid];
        self.presets = [[SHActionPopUp alloc] initWithFrame:NSMakeRect(300, 290, 180, 30) pullsDown:NO];
        [self.presets addItemWithTitle:@"Current pattern"];
        for (unsigned preset = 0; preset < 16; ++preset) {
            [self.presets addItemWithTitle:[NSString stringWithFormat:@"Pattern %u", preset + 1]];
            const uint8_t *rows = presets.bytes;
            NSImage *sample = SHPatternImage(rows + preset * 8, self.fillIndex, self.maskIndex);
            [[self.presets itemAtIndex:(NSInteger)preset + 1] setImage:sample];
        }
        self.presets.target = self; self.presets.action = @selector(preset:);
        [self.panel.contentView addSubview:self.presets];
        SHPatternPreview *preview = [[SHPatternPreview alloc] initWithFrame:NSMakeRect(300, 110, 180, 155)];
        preview.editor = self; self.preview = preview;
        [self.panel.contentView addSubview:self.preview];
        [self.panel.contentView addSubview:SHLabel(@"Click or drag squares to paint.", NSMakeRect(20, 40, 300, 24))];
        [self.panel.contentView addSubview:SHButton(@"Abort", NSMakeRect(20, 5, 110, 32), self, @selector(abort:))];
        [self.panel.contentView addSubview:SHButton(@"Done", NSMakeRect(370, 5, 110, 32), self, @selector(done:))];
        [self refresh];
    }
    return self;
}
- (void)preset:(id)sender {
    (void)sender;
    NSInteger selection = self.presets.indexOfSelectedItem;
    if (selection < 1 || selection > 16) return;
    NSData *presets = SHPresetPatterns();
    if (presets.length != 16 * 8) return;
    const uint8_t *rows = presets.bytes;
    memcpy(pattern, rows + (selection - 1) * 8, sizeof pattern);
    [self refresh];
}
- (void)refresh {
    self.grid.needsDisplay = YES;
    self.preview.needsDisplay = YES;
}
@end

BOOL SHShowPatternEditor(NSMutableDictionary *profile) {
    SHPatternEditor *editor = [[SHPatternEditor alloc] initWithProfile:profile];
    if (![editor run]) return NO;
    profile[@"pattern"] = [NSData dataWithBytes:editor->pattern length:8];
    return YES;
}
