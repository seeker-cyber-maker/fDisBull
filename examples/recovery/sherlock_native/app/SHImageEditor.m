#import "SHUI.h"
#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Native editor transactions are explicit: a pixel editor has its own entry
 * snapshot; the overview has another. File Save writes atomically and is not
 * undone by cancelling a later edit dialog. No bundled resource is overwritten
 * merely by accepting an edit: accepted artwork lives in the player's profile. */

@class SHPixelEditor;
@interface SHPixelCanvas : NSView
@property(nonatomic, weak) SHPixelEditor *editor;
@end
@interface SHPixelPreview : NSView
@property(nonatomic, weak) SHPixelEditor *editor;
@end

@interface SHPixelEditor : SHModalEditor <SHColorChoice> {
@public
    uint8_t pixels[32][32];
    uint8_t entry[32][32];
    BOOL linePreview;
    int lineX0, lineY0, lineX1, lineY1;
}
@property(nonatomic) NSUInteger color;
@property(nonatomic) NSUInteger replacePhase;
@property(nonatomic) NSUInteger replaceSource;
@property(nonatomic, strong) SHPixelCanvas *canvas;
@property(nonatomic, strong) SHPixelPreview *preview;
@property(nonatomic, strong) SHPaletteView *palette;
@property(nonatomic, strong) NSTextField *status;
- (instancetype)initWithData:(NSData *)data;
- (void)refresh;
- (void)sampleColor:(NSUInteger)color;
@end

static void SHRasterLine(uint8_t image[32][32], int x0, int y0, int x1, int y1,
                         uint8_t color) {
    int dx = abs(x1 - x0), sx = x0 < x1 ? 1 : -1;
    int dy = -abs(y1 - y0), sy = y0 < y1 ? 1 : -1;
    int error = dx + dy;
    for (;;) {
        if (x0 >= 0 && x0 < 32 && y0 >= 0 && y0 < 32) image[y0][x0] = color;
        if (x0 == x1 && y0 == y1) break;
        int twice = 2 * error;
        if (twice >= dy) { error += dy; x0 += sx; }
        if (twice <= dx) { error += dx; y0 += sy; }
    }
}

@implementation SHPixelCanvas {
    BOOL _drawing;
    BOOL _line;
    int _lastX, _lastY;
}
- (BOOL)isFlipped { return YES; }
- (void)drawRect:(NSRect)dirtyRect {
    (void)dirtyRect;
    uint8_t display[32][32];
    memcpy(display, self.editor->pixels, sizeof display);
    if (self.editor->linePreview)
        SHRasterLine(display, self.editor->lineX0, self.editor->lineY0,
                     self.editor->lineX1, self.editor->lineY1,
                     (uint8_t)self.editor.color);
    CGFloat cell = self.bounds.size.width / 32;
    for (int y = 0; y < 32; ++y) for (int x = 0; x < 32; ++x) {
        [SHColor(display[y][x]) setFill];
        NSRectFill(NSMakeRect(x * cell, y * cell, cell, cell));
    }
    [[NSColor grayColor] setStroke];
    NSBezierPath *grid = [NSBezierPath bezierPath];
    for (unsigned i = 0; i <= 32; ++i) {
        [grid moveToPoint:NSMakePoint(i * cell, 0)];
        [grid lineToPoint:NSMakePoint(i * cell, 32 * cell)];
        [grid moveToPoint:NSMakePoint(0, i * cell)];
        [grid lineToPoint:NSMakePoint(32 * cell, i * cell)];
    }
    grid.lineWidth = .35; [grid stroke];
}
- (NSPoint)pixelPoint:(NSEvent *)event {
    NSPoint point = [self convertPoint:event.locationInWindow fromView:nil];
    point.x = MIN(31, MAX(0, floor(point.x * 32 / self.bounds.size.width)));
    point.y = MIN(31, MAX(0, floor(point.y * 32 / self.bounds.size.height)));
    return point;
}
- (void)begin:(NSEvent *)event line:(BOOL)line {
    NSPoint point = [self pixelPoint:event];
    int x = (int)point.x, y = (int)point.y;
    if (self.editor.replacePhase) {
        [self.editor sampleColor:self.editor->pixels[y][x]]; return;
    }
    _drawing = YES; _line = line;
    _lastX = x; _lastY = y;
    if (line) {
        self.editor->linePreview = YES;
        self.editor->lineX0 = self.editor->lineX1 = x;
        self.editor->lineY0 = self.editor->lineY1 = y;
    } else self.editor->pixels[y][x] = (uint8_t)self.editor.color;
    [self.editor refresh];
}
- (void)mouseDown:(NSEvent *)event { [self begin:event line:NO]; }
- (void)rightMouseDown:(NSEvent *)event { [self begin:event line:YES]; }
- (void)mouseDragged:(NSEvent *)event {
    if (!_drawing) return;
    NSPoint point = [self pixelPoint:event];
    if (_line) {
        self.editor->lineX1 = (int)point.x; self.editor->lineY1 = (int)point.y;
    } else {
        SHRasterLine(self.editor->pixels, _lastX, _lastY,
                     (int)point.x, (int)point.y, (uint8_t)self.editor.color);
        _lastX = (int)point.x; _lastY = (int)point.y;
    }
    [self.editor refresh];
}
- (void)rightMouseDragged:(NSEvent *)event { [self mouseDragged:event]; }
- (void)mouseUp:(NSEvent *)event {
    if (!_drawing) return;
    if (_line) {
        NSPoint point = [self pixelPoint:event];
        SHRasterLine(self.editor->pixels, self.editor->lineX0, self.editor->lineY0,
                     (int)point.x, (int)point.y, (uint8_t)self.editor.color);
    } else {
        NSPoint point = [self pixelPoint:event];
        SHRasterLine(self.editor->pixels, _lastX, _lastY,
                     (int)point.x, (int)point.y, (uint8_t)self.editor.color);
    }
    _drawing = NO; self.editor->linePreview = NO;
    [self.editor refresh];
}
- (void)rightMouseUp:(NSEvent *)event { [self mouseUp:event]; }
@end

@implementation SHPixelPreview
- (BOOL)isFlipped { return YES; }
- (void)drawRect:(NSRect)dirtyRect {
    (void)dirtyRect;
    NSGraphicsContext.currentContext.imageInterpolation = NSImageInterpolationNone;
    NSImage *full = SHImage(self.editor->pixels, NO);
    NSImage *half = SHImage(self.editor->pixels, YES);
    [full drawInRect:NSMakeRect(26, 18, 32, 32) fromRect:NSZeroRect
          operation:NSCompositingOperationCopy fraction:1 respectFlipped:YES hints:nil];
    [half drawInRect:NSMakeRect(109, 26, 16, 16) fromRect:NSZeroRect
          operation:NSCompositingOperationCopy fraction:1 respectFlipped:YES hints:nil];
    [@"Full 32×32" drawAtPoint:NSMakePoint(10, 61) withAttributes:nil];
    [@"Half 16×16" drawAtPoint:NSMakePoint(88, 61) withAttributes:nil];
}
@end

@implementation SHPixelEditor
- (instancetype)initWithData:(NSData *)data {
    if ((self = [super initWithTitle:@"Edit image" size:NSMakeSize(760, 565)])) {
        if (data.length == sizeof pixels) [data getBytes:pixels length:sizeof pixels];
        memcpy(entry, pixels, sizeof entry);
        self.color = 3;
        NSView *view = self.panel.contentView;
        self.canvas = [[SHPixelCanvas alloc] initWithFrame:NSMakeRect(18, 90, 448, 448)];
        self.canvas.editor = self; [view addSubview:self.canvas];
        self.palette = [[SHPaletteView alloc] initWithFrame:NSMakeRect(500, 355, 216, 176)];
        self.palette.receiver = self; self.palette.currentColor = self.color;
        [view addSubview:self.palette];
        self.preview = [[SHPixelPreview alloc] initWithFrame:NSMakeRect(525, 238, 160, 105)];
        self.preview.editor = self; [view addSubview:self.preview];
        NSArray *names = @[@"Replace color", @"H flip", @"V flip", @"Clear to color"];
        SEL actions[] = {@selector(replace:), @selector(horizontalFlip:),
                         @selector(verticalFlip:), @selector(clear:)};
        for (NSUInteger i = 0; i < names.count; ++i)
            [view addSubview:SHButton(names[i], NSMakeRect(490 + (i % 2) * 125,
                                                           195 - (i / 2) * 37, 122, 32),
                                      self, actions[i])];
        [view addSubview:SHLabel(@"Shift one pixel (black fill)", NSMakeRect(500, 127, 225, 23))];
        NSArray *arrows = @[@"←", @"↑", @"↓", @"→"];
        for (NSUInteger i = 0; i < 4; ++i) {
            NSButton *button = SHButton(arrows[i], NSMakeRect(495 + i * 59, 91, 54, 32),
                                         self, @selector(shift:));
            button.tag = (NSInteger)i; [view addSubview:button];
        }
        self.status = SHLabel(@"Left drag paints. Right drag previews a line until release.",
                               NSMakeRect(18, 52, 724, 30));
        [view addSubview:self.status];
        [view addSubview:SHButton(@"Abort", NSMakeRect(18, 10, 120, 32), self, @selector(abort:))];
        [view addSubview:SHButton(@"INIT: entry image", NSMakeRect(292, 10, 170, 32), self, @selector(reset:))];
        [view addSubview:SHButton(@"Done", NSMakeRect(622, 10, 120, 32), self, @selector(done:))];
    }
    return self;
}
- (void)refresh {
    self.canvas.needsDisplay = YES; self.preview.needsDisplay = YES;
    self.palette.currentColor = self.color; self.palette.needsDisplay = YES;
}
- (void)pickColor:(NSUInteger)index {
    if (self.replacePhase) [self sampleColor:index];
    else { self.color = index; [self refresh]; }
}
- (void)sampleColor:(NSUInteger)color {
    if (self.replacePhase == 1) {
        self.replaceSource = color; self.replacePhase = 2;
        self.status.stringValue = @"Choose the replacement color from the palette or image.";
    } else if (self.replacePhase == 2) {
        for (unsigned y = 0; y < 32; ++y) for (unsigned x = 0; x < 32; ++x)
            if (pixels[y][x] == self.replaceSource) pixels[y][x] = (uint8_t)color;
        self.replacePhase = 0; self.color = color;
        self.status.stringValue = @"Color replaced. Left drag paints; right drag draws a line.";
        [self refresh];
    }
}
- (void)replace:(id)sender {
    (void)sender; self.replacePhase = 1;
    self.status.stringValue = @"Choose the color to replace, from the palette or image.";
}
- (void)horizontalFlip:(id)sender {
    (void)sender; self.replacePhase = 0;
    for (unsigned y = 0; y < 32; ++y) for (unsigned x = 0; x < 16; ++x) {
        uint8_t saved = pixels[y][x]; pixels[y][x] = pixels[y][31 - x];
        pixels[y][31 - x] = saved;
    }
    [self refresh];
}
- (void)verticalFlip:(id)sender {
    (void)sender; self.replacePhase = 0;
    for (unsigned y = 0; y < 16; ++y) for (unsigned x = 0; x < 32; ++x) {
        uint8_t saved = pixels[y][x]; pixels[y][x] = pixels[31 - y][x];
        pixels[31 - y][x] = saved;
    }
    [self refresh];
}
- (void)clear:(id)sender {
    (void)sender; self.replacePhase = 0;
    memset(pixels, (int)self.color, sizeof pixels); [self refresh];
}
- (void)reset:(id)sender {
    (void)sender; self.replacePhase = 0;
    memcpy(pixels, entry, sizeof pixels); [self refresh];
}
- (void)shift:(NSButton *)button {
    uint8_t old[32][32];
    self.replacePhase = 0; memcpy(old, pixels, sizeof old);
    int dx = button.tag == 0 ? -1 : button.tag == 3 ? 1 : 0;
    int dy = button.tag == 1 ? -1 : button.tag == 2 ? 1 : 0;
    for (int y = 0; y < 32; ++y) for (int x = 0; x < 32; ++x) {
        int sourceX = x - dx, sourceY = y - dy;
        /* Distinct edge sentinels qualified discard/black-fill independently
         * for all four original shifts. */
        pixels[y][x] = sourceX >= 0 && sourceX < 32 && sourceY >= 0 && sourceY < 32
                     ? old[sourceY][sourceX] : 0;
    }
    [self refresh];
}
@end

@class SHImageEditor;
@interface SHImageOverview : NSView
@property(nonatomic, weak) SHImageEditor *editor;
@end

@interface SHImageEditor : SHModalEditor {
@public uint8_t images[46][32][32];
}
@property(nonatomic, strong) SHImageOverview *overview;
@property(nonatomic, strong) NSArray<NSImage *> *tiles;
@property(nonatomic, copy) NSString *path;
@property(nonatomic, copy) NSString *defaultPath;
@property(nonatomic, copy) NSString *factoryPath;
@property(nonatomic, strong) NSTextField *filename;
@property(nonatomic) BOOL validImages;
- (instancetype)initWithProfile:(NSDictionary *)profile defaultPath:(NSString *)defaultPath
                     factoryPath:(NSString *)factoryPath;
- (void)refresh;
- (void)editImage:(NSUInteger)index;
@end

@implementation SHImageOverview {
    NSInteger _source;
    NSPoint _down;
    BOOL _dragged;
}
- (BOOL)isFlipped { return YES; }
- (NSInteger)indexAt:(NSPoint)point {
    if (point.x < 0 || point.x >= 384 || point.y < 0 || point.y >= 448) return -1;
    NSInteger index = (NSInteger)(point.x / 64) + (NSInteger)(point.y / 64) * 6;
    return index <= 36 ? index : -1;
}
- (void)drawRect:(NSRect)dirtyRect {
    (void)dirtyRect;
    NSGraphicsContext.currentContext.imageInterpolation = NSImageInterpolationNone;
    for (NSUInteger i = 0; i < MIN((NSUInteger)37, self.editor.tiles.count); ++i) {
        NSRect cell = NSMakeRect((i % 6) * 64, (i / 6) * 64, 64, 64);
        [NSColor.controlBackgroundColor setFill]; NSRectFill(cell);
        [self.editor.tiles[i] drawInRect:NSInsetRect(cell, 8, 8) fromRect:NSZeroRect
               operation:NSCompositingOperationCopy fraction:1 respectFlipped:YES hints:nil];
    }
    [@"Empty image" drawAtPoint:NSMakePoint(76, 405) withAttributes:nil];
}
- (void)mouseDown:(NSEvent *)event {
    _down = [self convertPoint:event.locationInWindow fromView:nil];
    _source = [self indexAt:_down]; _dragged = NO;
}
- (void)rightMouseDown:(NSEvent *)event { [self mouseDown:event]; }
- (void)mouseDragged:(NSEvent *)event {
    NSPoint point = [self convertPoint:event.locationInWindow fromView:nil];
    if (hypot(point.x - _down.x, point.y - _down.y) > 4) _dragged = YES;
}
- (void)rightMouseDragged:(NSEvent *)event { [self mouseDragged:event]; }
- (void)mouseUp:(NSEvent *)event {
    if (_source < 0) return;
    NSPoint point = [self convertPoint:event.locationInWindow fromView:nil];
    NSInteger destination = [self indexAt:point];
    if (_dragged && destination >= 0 && destination != _source) {
        memcpy(self.editor->images[destination], self.editor->images[_source], 32 * 32);
        [self.editor refresh];
    } else if (!_dragged && destination == _source) {
        [self.editor editImage:(NSUInteger)_source];
    }
    _source = -1;
}
- (void)rightMouseUp:(NSEvent *)event { [self mouseUp:event]; }
@end

@implementation SHImageEditor
- (instancetype)initWithProfile:(NSDictionary *)profile defaultPath:(NSString *)defaultPath
                     factoryPath:(NSString *)factoryPath {
    if ((self = [super initWithTitle:@"Images" size:NSMakeSize(650, 545)])) {
        self.defaultPath = defaultPath;
        self.factoryPath = factoryPath;
        self.path = profile[@"imagePath"];
        self.validImages = SHLoadProfileImages(profile, defaultPath, images);
        self.overview = [[SHImageOverview alloc] initWithFrame:NSMakeRect(20, 65, 384, 448)];
        self.overview.editor = self; [self.panel.contentView addSubview:self.overview];
        NSArray *names = @[@"Load…", @"Save…", @"Merge row…", @"Defaults"];
        SEL actions[] = {@selector(load:), @selector(save:), @selector(merge:), @selector(defaults:)};
        for (NSUInteger i = 0; i < names.count; ++i)
            [self.panel.contentView addSubview:SHButton(names[i], NSMakeRect(440, 465 - i * 48, 175, 36),
                                                        self, actions[i])];
        NSTextField *note = SHLabel(@"Click an image to edit.\n\nDrag one image onto another to copy it.\n\nSave writes a .SHI file. Done retains your edits for this player.",
                                    NSMakeRect(435, 135, 195, 135));
        [self.panel.contentView addSubview:note];
        self.filename = SHLabel(@"", NSMakeRect(20, 37, 610, 24));
        [self.panel.contentView addSubview:self.filename];
        [self.panel.contentView addSubview:SHButton(@"Abort", NSMakeRect(20, 2, 120, 32), self, @selector(abort:))];
        [self.panel.contentView addSubview:SHButton(@"Done", NSMakeRect(510, 2, 120, 32), self, @selector(done:))];
        [self refresh];
    }
    return self;
}
- (void)refresh {
    self.tiles = self.validImages ? SHImages(images, NO) : @[];
    self.filename.stringValue = self.path.length ? self.path.lastPathComponent : @"Working image set — no separate saved file";
    self.overview.needsDisplay = YES;
}
- (void)editImage:(NSUInteger)index {
    if (!self.validImages || index > 36) return;
    SHPixelEditor *editor = [[SHPixelEditor alloc]
        initWithData:[NSData dataWithBytes:images[index] length:32 * 32]];
    if ([editor run]) { memcpy(images[index], editor->pixels, 32 * 32); [self refresh]; }
}
- (NSOpenPanel *)filePanel {
    NSOpenPanel *panel = NSOpenPanel.openPanel;
    panel.allowedFileTypes = @[@"shi"];
    panel.allowsMultipleSelection = NO;
    panel.canChooseDirectories = NO;
    if (self.path.length) panel.directoryURL = [[NSURL fileURLWithPath:self.path] URLByDeletingLastPathComponent];
    else if (self.defaultPath.length) panel.directoryURL = [[NSURL fileURLWithPath:self.defaultPath] URLByDeletingLastPathComponent];
    return panel;
}
- (void)load:(id)sender {
    (void)sender;
    NSOpenPanel *panel = [self filePanel];
    if ([panel runModal] != NSModalResponseOK) return;
    uint8_t loaded[46][32][32];
    if (shi_load(panel.URL.fileSystemRepresentation, loaded) != 0) {
        SHMessage(@"Image set was not loaded", [NSString stringWithFormat:@"%@\n%s", panel.URL.lastPathComponent, strerror(errno)]);
        return;
    }
    memcpy(images, loaded, sizeof images);
    self.path = panel.URL.path; self.validImages = YES; [self refresh];
}
- (void)save:(id)sender {
    (void)sender;
    if (!self.validImages) { SHMessage(@"No images to save", @"Load an image set first."); return; }
    NSSavePanel *panel = NSSavePanel.savePanel;
    panel.allowedFileTypes = @[@"shi"];
    panel.canCreateDirectories = YES;
    panel.nameFieldStringValue = self.path.length ? self.path.lastPathComponent : @"My-images.SHI";
    panel.directoryURL = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory
                                                             inDomains:NSUserDomainMask].firstObject;
    if ([panel runModal] != NSModalResponseOK) return;
    NSURL *target = panel.URL;
    NSString *temporaryName = [NSString stringWithFormat:@".sherlock-%@.shi", NSUUID.UUID.UUIDString];
    NSURL *temporary = [[target URLByDeletingLastPathComponent] URLByAppendingPathComponent:temporaryName];
    if (shi_save(temporary.fileSystemRepresentation, images) != 0 ||
        rename(temporary.fileSystemRepresentation, target.fileSystemRepresentation) != 0) {
        int savedError = errno;
        [NSFileManager.defaultManager removeItemAtURL:temporary error:NULL];
        SHMessage(@"Image set was not saved", [NSString stringWithFormat:@"%@\n%s", target.lastPathComponent, strerror(savedError)]);
        return;
    }
    self.path = target.path; [self refresh];
}
- (void)merge:(id)sender {
    (void)sender;
    NSOpenPanel *panel = [self filePanel];
    if ([panel runModal] != NSModalResponseOK) return;
    uint8_t source[46][32][32];
    if (shi_load(panel.URL.fileSystemRepresentation, source) != 0) {
        SHMessage(@"Image row was not loaded", [NSString stringWithUTF8String:strerror(errno)]); return;
    }
    NSAlert *ask = [[NSAlert alloc] init];
    ask.messageText = @"Merge a row";
    ask.informativeText = @"Choose the source row and the destination row to replace. Other rows and the empty image are preserved.";
    NSView *controls = [[NSView alloc] initWithFrame:NSMakeRect(0, 0, 400, 75)];
    NSPopUpButton *from = [[SHActionPopUp alloc] initWithFrame:NSMakeRect(0, 5, 190, 30) pullsDown:NO];
    NSPopUpButton *to = [[SHActionPopUp alloc] initWithFrame:NSMakeRect(210, 5, 190, 30) pullsDown:NO];
    for (unsigned i = 1; i <= 6; ++i) {
        [from addItemWithTitle:[NSString stringWithFormat:@"Source row %u", i]];
        [to addItemWithTitle:[NSString stringWithFormat:@"Destination row %u", i]];
    }
    [controls addSubview:from]; [controls addSubview:to]; ask.accessoryView = controls;
    [ask addButtonWithTitle:@"Merge"]; [ask addButtonWithTitle:@"Cancel"];
    if ([ask runModal] != NSAlertFirstButtonReturn) return;
    if (!self.validImages) {
        if (!self.factoryPath.length || shi_load(self.factoryPath.fileSystemRepresentation, images) != 0) {
            SHMessage(@"Load a destination set first", @"The default set is unavailable. Load the image set that should receive this row."); return;
        }
        self.validImages = YES;
    }
    memcpy(&images[to.indexOfSelectedItem * 6], &source[from.indexOfSelectedItem * 6], 6 * 32 * 32);
    [self refresh];
}
- (void)defaults:(id)sender {
    (void)sender;
    if (!self.factoryPath.length || shi_load(self.factoryPath.fileSystemRepresentation, images) != 0) {
        SHMessage(@"Factory images unavailable", @"The supplied ORGINAL.SHI could not be loaded. Your working set is unchanged."); return;
    }
    self.validImages = YES; self.path = nil; [self refresh];
}
- (void)done:(id)sender {
    if (!self.validImages) { SHMessage(@"Load an image set", @"Choose a valid .SHI file before accepting the images."); return; }
    [super done:sender];
}
@end

BOOL SHShowImageEditor(NSMutableDictionary *profile, NSString *defaultPath,
                        NSString *factoryPath) {
    SHImageEditor *editor = [[SHImageEditor alloc] initWithProfile:profile
        defaultPath:defaultPath factoryPath:factoryPath];
    if (![editor run]) return NO;
    profile[@"images"] = [NSData dataWithBytes:editor->images length:sizeof editor->images];
    if (editor.path.length) profile[@"imagePath"] = editor.path;
    else [profile removeObjectForKey:@"imagePath"];
    return YES;
}
