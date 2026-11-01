// Native host services for an explicitly supplied memory UIL plan.
// Game transitions and drawing pixels are generated native blocks, not AppKit.
#import <AppKit/AppKit.h>
#import <Carbon/Carbon.h>
#import <CommonCrypto/CommonDigest.h>
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include "memory-runtime.h"

static void FdbCheck(BOOL ok, NSString *message) {
    if (!ok) @throw [NSException exceptionWithName:@"FdbAdapterRefused" reason:message userInfo:nil];
}
static uint32_t FdbUInt(id value) {
    FdbCheck([value isKindOfClass:[NSNumber class]] && CFGetTypeID((__bridge CFTypeRef)value) != CFBooleanGetTypeID(), @"Unsigned integer required");
    double number = [value doubleValue];
    FdbCheck(isfinite(number) && floor(number) == number && number >= 0 && number <= UINT32_MAX, @"Unsigned integer outside range");
    return (uint32_t)number;
}
static NSDictionary *FdbReadJSON(NSString *path, const char *expectedSHA) {
    NSError *error = nil;
    NSData *data = [NSData dataWithContentsOfFile:path options:0 error:&error];
    FdbCheck(data != nil, error.localizedDescription ?: @"JSON input unavailable");
    FdbCheck(data.length <= 16u * 1024u * 1024u, @"Adapter JSON budget exceeded");
    if (expectedSHA) {
        unsigned char hash[CC_SHA256_DIGEST_LENGTH]; char text[CC_SHA256_DIGEST_LENGTH * 2 + 1];
        CC_SHA256(data.bytes,(CC_LONG)data.length,hash);
        for (size_t i = 0; i < CC_SHA256_DIGEST_LENGTH; i++) snprintf(text + i * 2,3,"%02x",hash[i]);
        FdbCheck(strcmp(text,expectedSHA) == 0,@"Native config identity differs");
    }
    id object = [NSJSONSerialization JSONObjectWithData:data options:0 error:&error];
    FdbCheck([object isKindOfClass:[NSDictionary class]], error.localizedDescription ?: @"JSON object required");
    return object;
}
static NSArray *FdbWords(NSData *snapshot) {
    const uint32_t *words = snapshot.bytes;
    NSMutableArray *result = [NSMutableArray arrayWithCapacity:snapshot.length / sizeof(uint32_t)];
    for (size_t i = 0; i < snapshot.length / sizeof(uint32_t); i++) [result addObject:@(words[i])];
    return result;
}
static NSDictionary *FdbKeyCodes(void) {
    static NSDictionary *map;
    if (!map) map = @{
        @"KeyA":@(kVK_ANSI_A), @"KeyB":@(kVK_ANSI_B), @"KeyC":@(kVK_ANSI_C), @"KeyD":@(kVK_ANSI_D),
        @"KeyE":@(kVK_ANSI_E), @"KeyF":@(kVK_ANSI_F), @"KeyG":@(kVK_ANSI_G), @"KeyH":@(kVK_ANSI_H),
        @"KeyI":@(kVK_ANSI_I), @"KeyJ":@(kVK_ANSI_J), @"KeyK":@(kVK_ANSI_K), @"KeyL":@(kVK_ANSI_L),
        @"KeyM":@(kVK_ANSI_M), @"KeyN":@(kVK_ANSI_N), @"KeyO":@(kVK_ANSI_O), @"KeyP":@(kVK_ANSI_P),
        @"KeyQ":@(kVK_ANSI_Q), @"KeyR":@(kVK_ANSI_R), @"KeyS":@(kVK_ANSI_S), @"KeyT":@(kVK_ANSI_T),
        @"KeyU":@(kVK_ANSI_U), @"KeyV":@(kVK_ANSI_V), @"KeyW":@(kVK_ANSI_W), @"KeyX":@(kVK_ANSI_X),
        @"KeyY":@(kVK_ANSI_Y), @"KeyZ":@(kVK_ANSI_Z),
        @"Digit0":@(kVK_ANSI_0), @"Digit1":@(kVK_ANSI_1), @"Digit2":@(kVK_ANSI_2), @"Digit3":@(kVK_ANSI_3),
        @"Digit4":@(kVK_ANSI_4), @"Digit5":@(kVK_ANSI_5), @"Digit6":@(kVK_ANSI_6), @"Digit7":@(kVK_ANSI_7),
        @"Digit8":@(kVK_ANSI_8), @"Digit9":@(kVK_ANSI_9),
        @"ArrowLeft":@(kVK_LeftArrow), @"ArrowRight":@(kVK_RightArrow), @"ArrowDown":@(kVK_DownArrow), @"ArrowUp":@(kVK_UpArrow),
        @"Space":@(kVK_Space), @"Escape":@(kVK_Escape), @"Enter":@(kVK_Return), @"Tab":@(kVK_Tab),
        @"Backspace":@(kVK_Delete), @"Delete":@(kVK_ForwardDelete), @"Home":@(kVK_Home), @"End":@(kVK_End),
        @"PageUp":@(kVK_PageUp), @"PageDown":@(kVK_PageDown),
        @"Minus":@(kVK_ANSI_Minus), @"Equal":@(kVK_ANSI_Equal), @"BracketLeft":@(kVK_ANSI_LeftBracket),
        @"BracketRight":@(kVK_ANSI_RightBracket), @"Backslash":@(kVK_ANSI_Backslash), @"Semicolon":@(kVK_ANSI_Semicolon),
        @"Quote":@(kVK_ANSI_Quote), @"Backquote":@(kVK_ANSI_Grave), @"Comma":@(kVK_ANSI_Comma),
        @"Period":@(kVK_ANSI_Period), @"Slash":@(kVK_ANSI_Slash),
        @"F1":@(kVK_F1), @"F2":@(kVK_F2), @"F3":@(kVK_F3), @"F4":@(kVK_F4), @"F5":@(kVK_F5),
        @"F6":@(kVK_F6), @"F7":@(kVK_F7), @"F8":@(kVK_F8), @"F9":@(kVK_F9), @"F10":@(kVK_F10),
        @"F11":@(kVK_F11), @"F12":@(kVK_F12), @"F13":@(kVK_F13), @"F14":@(kVK_F14), @"F15":@(kVK_F15),
        @"F16":@(kVK_F16), @"F17":@(kVK_F17), @"F18":@(kVK_F18), @"F19":@(kVK_F19), @"F20":@(kVK_F20)
    };
    return map;
}

@class FdbHost;
@interface FdbGameView : NSView
@property(nonatomic, weak) FdbHost *host;
@property(nonatomic, strong) NSTrackingArea *pointerTracking;
@end
@interface FdbControlsView : NSView
@end
@implementation FdbControlsView
- (BOOL)isFlipped { return YES; }
@end

@interface FdbHost : NSObject <NSApplicationDelegate, NSWindowDelegate>
@property(nonatomic, strong) NSDictionary *config;
@property(nonatomic, strong) NSDictionary *plan;
@property(nonatomic, strong) NSDictionary *events;
@property(nonatomic, strong) NSDictionary *frame;
@property(nonatomic, strong) NSDictionary *physicalKeys;
@property(nonatomic, strong) NSArray *regions;
@property(nonatomic, strong) NSMutableArray<NSPopUpButton *> *selectors;
@property(nonatomic, strong) NSWindow *window;
@property(nonatomic, strong) FdbGameView *view;
@property(nonatomic, strong) NSTextField *status;
@property(nonatomic, strong) NSTimer *timer;
@property(nonatomic, strong) NSData *snapshot;
@property(nonatomic, strong) NSDictionary *script;
@property(nonatomic, copy) NSString *resultPath;
@property(nonatomic) NSInteger scriptClock;
@property(nonatomic) BOOL diagnostic;
@property(nonatomic) BOOL stopped;
@property(nonatomic) BOOL accepted;
@property(nonatomic) BOOL committed;
@property(nonatomic) uint32_t mouseX;
@property(nonatomic) uint32_t mouseY;
@property(nonatomic) uint32_t buttons;
@property(nonatomic) NSUInteger commits;
@property(nonatomic) int resultCode;
- (instancetype)initWithConfig:(NSDictionary *)config;
- (uint32_t)clock;
- (void)copyCommittedWords;
- (NSRect)gameRect;
- (NSBitmapImageRep *)frameRep;
- (void)key:(NSEvent *)event;
- (void)pointer:(NSEvent *)event phase:(NSString *)phase;
- (void)releasePointer;
- (void)runScript;
@end

@implementation FdbGameView
- (BOOL)isFlipped { return YES; }
- (BOOL)acceptsFirstMouse:(NSEvent *)event { (void)event; return YES; }
- (BOOL)acceptsFirstResponder { return !self.host.stopped; }
- (void)updateTrackingAreas {
    [super updateTrackingAreas];
    if (self.pointerTracking) [self removeTrackingArea:self.pointerTracking];
    self.pointerTracking = [[NSTrackingArea alloc] initWithRect:NSZeroRect options:NSTrackingMouseMoved | NSTrackingActiveInKeyWindow | NSTrackingInVisibleRect owner:self userInfo:nil];
    [self addTrackingArea:self.pointerTracking];
}
- (BOOL)resignFirstResponder { [self.host releasePointer]; return [super resignFirstResponder]; }
- (void)drawRect:(NSRect)dirtyRect {
    (void)dirtyRect;
    [[NSColor blackColor] setFill]; NSRectFill(self.bounds);
    NSBitmapImageRep *rep = [self.host frameRep];
    NSImage *image = [[NSImage alloc] initWithSize:NSMakeSize(rep.pixelsWide, rep.pixelsHigh)];
    [image addRepresentation:rep];
    [NSGraphicsContext currentContext].imageInterpolation = NSImageInterpolationNone;
    [image drawInRect:[self.host gameRect] fromRect:NSZeroRect operation:NSCompositingOperationCopy fraction:1.0 respectFlipped:YES hints:@{NSImageHintInterpolation:@(NSImageInterpolationNone)}];
}
- (void)keyDown:(NSEvent *)event { [self.host key:event]; }
- (void)mouseDown:(NSEvent *)event { [self.window makeFirstResponder:self]; [self.host pointer:event phase:@"down"]; }
- (void)rightMouseDown:(NSEvent *)event { [self mouseDown:event]; }
- (void)otherMouseDown:(NSEvent *)event { [self mouseDown:event]; }
- (void)mouseUp:(NSEvent *)event { [self.host pointer:event phase:@"up"]; }
- (void)rightMouseUp:(NSEvent *)event { [self mouseUp:event]; }
- (void)otherMouseUp:(NSEvent *)event { [self mouseUp:event]; }
- (void)mouseDragged:(NSEvent *)event { [self.host pointer:event phase:@"drag"]; }
- (void)rightMouseDragged:(NSEvent *)event { [self mouseDragged:event]; }
- (void)otherMouseDragged:(NSEvent *)event { [self mouseDragged:event]; }
- (void)mouseMoved:(NSEvent *)event { [self.host pointer:event phase:@"move"]; }
@end

@implementation FdbHost
- (instancetype)initWithConfig:(NSDictionary *)config {
    self = [super init]; if (!self) return nil;
    self.config = config; self.plan = config[@"plan"] ?: config;
    self.events = self.plan[@"events"]; self.frame = self.plan[@"frame"];
    FdbCheck([self.events isKindOfClass:[NSDictionary class]] && [self.frame isKindOfClass:[NSDictionary class]], @"Adapter plan missing events/frame");
    uint32_t width = FdbUInt(self.frame[@"width"]), height = FdbUInt(self.frame[@"height"]), offset = FdbUInt(self.frame[@"offset"]);
    FdbCheck(width > 0 && width <= 1024 && height > 0 && height <= 1024 && (uint64_t)offset + (uint64_t)width * height <= fdb_word_count(), @"Frame outside native arena");
    for (NSString *name in @[@"kind",@"ascii",@"scan",@"x",@"y",@"buttons",@"clock",@"quit_index"])
        FdbCheck(FdbUInt(self.events[name]) < fdb_word_count(), @"Event index outside native arena");
    for (NSString *name in @[@"keyboard_kind",@"pointer_kind",@"clock_kind"]) FdbUInt(self.events[name]);
    double tick = [self.events[@"tick_ms"] doubleValue];
    FdbCheck(isfinite(tick) && tick >= 1 && tick <= 1000, @"Invalid clock adapter interval");
    NSMutableDictionary *keys = [NSMutableDictionary dictionary];
    NSDictionary *keymap = self.plan[@"keymap"];
    FdbCheck([keymap isKindOfClass:[NSDictionary class]], @"Missing physical key map");
    for (NSString *code in keymap) {
        NSNumber *physical = FdbKeyCodes()[code];
        FdbCheck(physical != nil, [@"Unsupported native physical key: " stringByAppendingString:code]);
        FdbUInt(keymap[code][@"ascii"]); FdbUInt(keymap[code][@"scan"]);
        keys[physical] = keymap[code];
    }
    self.physicalKeys = keys;
    self.regions = config[@"region_controls"] ?: @[];
    FdbCheck([self.regions isKindOfClass:[NSArray class]], @"Invalid region controls");
    self.selectors = [NSMutableArray array]; self.scriptClock = -1;
    [self copyCommittedWords];
    // Validate the complete palette and current frame before opening a window.
    [self frameRep];
    return self;
}
- (uint32_t)clock {
    if (self.scriptClock >= 0) return (uint32_t)self.scriptClock;
    return (uint32_t)((uint64_t)floor(NSProcessInfo.processInfo.systemUptime * 1000.0 / [self.events[@"tick_ms"] doubleValue]) & 65535u);
}
- (void)copyCommittedWords {
    self.snapshot = [NSData dataWithBytes:fdb_words() length:fdb_word_count() * sizeof(uint32_t)];
}
- (NSRect)gameRect {
    NSRect bounds = self.view.bounds;
    CGFloat width = [self.frame[@"width"] doubleValue], height = [self.frame[@"height"] doubleValue];
    CGFloat scale = MIN(bounds.size.width / width, bounds.size.height / height);
    return NSMakeRect(bounds.origin.x + (bounds.size.width - width * scale) / 2,
                      bounds.origin.y + (bounds.size.height - height * scale) / 2, width * scale, height * scale);
}
- (NSBitmapImageRep *)frameRep {
    uint32_t width = FdbUInt(self.frame[@"width"]), height = FdbUInt(self.frame[@"height"]), offset = FdbUInt(self.frame[@"offset"]);
    NSDictionary *colors = self.frame[@"palette"];
    FdbCheck([colors isKindOfClass:[NSDictionary class]] && colors[@"0"] != nil, @"Missing palette");
    uint8_t palette[256][4] = {{0}}; BOOL valid[256] = {NO};
    for (NSString *key in colors) {
        NSScanner *scanner = [NSScanner scannerWithString:key]; unsigned long long index;
        FdbCheck([scanner scanUnsignedLongLong:&index] && scanner.isAtEnd && index <= 255 && [[NSString stringWithFormat:@"%llu",index] isEqualToString:key], @"Invalid palette index");
        NSArray *rgb = colors[key]; FdbCheck([rgb isKindOfClass:[NSArray class]] && rgb.count == 3, @"Invalid palette color");
        for (int channel = 0; channel < 3; channel++) { uint32_t value = FdbUInt(rgb[channel]); FdbCheck(value <= 255, @"Palette channel outside byte range"); palette[index][channel] = (uint8_t)value; }
        palette[index][3] = 255; valid[index] = YES;
    }
    NSBitmapImageRep *rep = [[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL pixelsWide:width pixelsHigh:height bitsPerSample:8 samplesPerPixel:4 hasAlpha:YES isPlanar:NO colorSpaceName:NSDeviceRGBColorSpace bitmapFormat:NSBitmapFormatAlphaNonpremultiplied bytesPerRow:width * 4 bitsPerPixel:32];
    FdbCheck(rep != nil && self.snapshot.length == fdb_word_count() * sizeof(uint32_t), @"Frame allocation or stored state invalid");
    const uint32_t *words = self.snapshot.bytes;
    for (size_t i = 0; i < (size_t)width * height; i++) {
        uint32_t color = words[offset + i]; FdbCheck(color <= 255 && valid[color], @"Stored frame has unknown palette index");
        memcpy(rep.bitmapData + i * 4, palette[color], 4);
    }
    return rep;
}
- (BOOL)dispatch:(NSDictionary *)patch {
    self.accepted = YES; self.committed = NO;
    if (self.stopped || fdb_closed()) return NO;
    FdbCheck(patch.count <= 16, @"Input patch exceeds adapter capacity");
    uint32_t indices[16], values[16]; size_t count = 0;
    for (NSString *name in patch) { indices[count] = FdbUInt(self.events[name]); values[count] = FdbUInt(patch[name]); count++; }
    int result = fdb_dispatch(indices, values, count, 1);
    if (result != 0) { self.status.stringValue = [NSString stringWithUTF8String:fdb_last_error()] ?: @"Input refused"; return NO; }
    self.committed = YES; self.commits++; [self copyCommittedWords]; self.view.needsDisplay = YES;
    const uint32_t *words = self.snapshot.bytes;
    if (words[FdbUInt(self.events[@"quit_index"])]) {
        self.stopped = YES; [self.timer invalidate]; self.timer = nil;
        for (NSPopUpButton *selector in self.selectors) selector.enabled = NO;
        self.status.stringValue = @"Exited. Open again to start a new session.";
        fdb_close();
        if (!self.diagnostic) [NSApp performSelector:@selector(terminate:) withObject:nil afterDelay:0];
    } else self.status.stringValue = @"Ready";
    return YES;
}
- (void)key:(NSEvent *)event {
    self.accepted = self.committed = NO;
    if (self.stopped || self.window.firstResponder != self.view || (event.modifierFlags & (NSEventModifierFlagCommand | NSEventModifierFlagControl | NSEventModifierFlagOption))) return;
    NSDictionary *key = self.physicalKeys[@(event.keyCode)]; if (!key) return;
    [self dispatch:@{@"kind":self.events[@"keyboard_kind"],@"ascii":key[@"ascii"],@"scan":key[@"scan"],@"clock":@([self clock])}];
}
- (void)pointer:(NSEvent *)event phase:(NSString *)phase {
    self.accepted = self.committed = NO; if (self.stopped) return;
    NSPoint point = [self.view convertPoint:event.locationInWindow fromView:nil]; NSRect rect = [self gameRect];
    BOOL inside = point.x >= NSMinX(rect) && point.x < NSMaxX(rect) && point.y >= NSMinY(rect) && point.y < NSMaxY(rect);
    if (!inside && self.buttons == 0) return;
    uint32_t width = FdbUInt(self.frame[@"width"]), height = FdbUInt(self.frame[@"height"]);
    self.mouseX = (uint32_t)MAX(0,MIN((double)width - 1,floor((point.x - NSMinX(rect)) * width / rect.size.width)));
    self.mouseY = (uint32_t)MAX(0,MIN((double)height - 1,floor((point.y - NSMinY(rect)) * height / rect.size.height)));
    uint32_t bit = event.buttonNumber >= 0 && event.buttonNumber < 3 ? 1u << event.buttonNumber : 0;
    if ([phase isEqualToString:@"down"]) self.buttons |= bit;
    if ([phase isEqualToString:@"up"]) self.buttons &= ~bit;
    [self dispatch:@{@"kind":self.events[@"pointer_kind"],@"x":@(self.mouseX),@"y":@(self.mouseY),@"buttons":@(self.buttons & 7),@"clock":@([self clock])}];
}
- (void)releasePointer {
    if (self.buttons == 0 || self.stopped) return; self.buttons = 0;
    [self dispatch:@{@"kind":self.events[@"pointer_kind"],@"x":@(self.mouseX),@"y":@(self.mouseY),@"buttons":@0,@"clock":@([self clock])}];
}
- (void)selectRegion:(NSPopUpButton *)sender {
    self.accepted = YES; self.committed = NO;
    int result = fdb_select_region((size_t)sender.tag, (size_t)sender.indexOfSelectedItem);
    if (result != 0) { [sender selectItemAtIndex:fdb_selected_region((size_t)sender.tag)]; self.status.stringValue = [NSString stringWithUTF8String:fdb_last_error()] ?: @"Selection refused"; return; }
    [self releasePointer]; self.status.stringValue = @"Selection applied. Current game state retained.";
}
- (void)tick:(NSTimer *)timer { (void)timer; [self dispatch:@{@"kind":self.events[@"clock_kind"],@"clock":@([self clock])}]; }
- (void)windowDidResignKey:(NSNotification *)notification { (void)notification; [self releasePointer]; }
- (BOOL)windowShouldClose:(NSWindow *)sender { (void)sender; [self releasePointer]; [self.timer invalidate]; self.stopped = YES; fdb_close(); [NSApp terminate:nil]; return YES; }
- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender { (void)sender; return YES; }
- (void)applicationWillTerminate:(NSNotification *)notification { (void)notification; [self.timer invalidate]; fdb_close(); }
- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    (void)notification;
    NSRect content = NSMakeRect(0,0,900,760);
    self.window = [[NSWindow alloc] initWithContentRect:content styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable backing:NSBackingStoreBuffered defer:NO];
    self.window.releasedWhenClosed = NO;
    self.window.title = self.plan[@"title"] ?: @"Recovered program"; self.window.delegate = self; self.window.acceptsMouseMovedEvents = YES;
    self.window.minSize = NSMakeSize(420,400);
    NSView *container = self.window.contentView;
    NSTextField *help = [NSTextField wrappingLabelWithString:self.plan[@"help"] ?: @""];
    help.frame = NSMakeRect(16,678,868,66); help.autoresizingMask = NSViewWidthSizable | NSViewMinYMargin; [container addSubview:help];
    NSScrollView *controls = [[NSScrollView alloc] initWithFrame:NSMakeRect(16,604,868,68)];
    controls.hasVerticalScroller = self.regions.count > 2; controls.drawsBackground = NO;
    controls.autoresizingMask = NSViewWidthSizable | NSViewMinYMargin;
    FdbControlsView *controlRows = [[FdbControlsView alloc] initWithFrame:NSMakeRect(0,0,868,MAX(68,self.regions.count * 34))];
    controlRows.autoresizingMask = NSViewWidthSizable; controls.documentView = controlRows; [container addSubview:controls];
    for (NSUInteger index = 0; index < self.regions.count; index++) {
        NSDictionary *region = self.regions[index]; NSArray *variants = region[@"variants"];
        FdbCheck([variants isKindOfClass:[NSArray class]] && variants.count > 0, @"Region variants missing");
        NSTextField *label = [NSTextField labelWithString:region[@"label"] ?: region[@"name"] ?: @"Implementation"];
        label.frame = NSMakeRect(0,index * 34 + 4,160,22); [controlRows addSubview:label];
        NSPopUpButton *selector = [[NSPopUpButton alloc] initWithFrame:NSMakeRect(170,index * 34,680,28) pullsDown:NO];
        for (NSDictionary *variant in variants) [selector addItemWithTitle:variant[@"label"] ?: variant[@"name"]];
        NSInteger selected = fdb_selected_region(index); FdbCheck(selected >= 0 && (NSUInteger)selected < variants.count, @"Region default outside control");
        [selector selectItemAtIndex:selected]; selector.tag = (NSInteger)index; selector.target = self; selector.action = @selector(selectRegion:); selector.autoresizingMask = NSViewWidthSizable;
        [controlRows addSubview:selector]; [self.selectors addObject:selector];
    }
    self.view = [[FdbGameView alloc] initWithFrame:NSMakeRect(16,58,868,530)]; self.view.host = self;
    self.view.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable; [container addSubview:self.view];
    self.status = [NSTextField labelWithString:@"Ready"]; self.status.frame = NSMakeRect(16,20,868,24); self.status.autoresizingMask = NSViewWidthSizable | NSViewMaxYMargin; [container addSubview:self.status];
    [self.window center]; [self.window makeKeyAndOrderFront:nil]; [self.window makeFirstResponder:self.view]; [NSApp activateIgnoringOtherApps:YES];
    if (self.diagnostic) [self performSelector:@selector(runScript) withObject:nil afterDelay:0.01];
    else self.timer = [NSTimer scheduledTimerWithTimeInterval:[self.events[@"tick_ms"] doubleValue] / 1000.0 target:self selector:@selector(tick:) userInfo:nil repeats:YES];
}
- (NSDictionary *)scriptRow:(NSDictionary *)command {
    NSMutableArray *selected = [NSMutableArray array];
    for (NSUInteger index = 0; index < self.regions.count; index++) [selected addObject:@(fdb_selected_region(index))];
    NSMutableDictionary *row = [@{@"kind":command[@"kind"] ?: @"snapshot",@"accepted":@(self.accepted),@"committed":@(self.committed),@"closed":@(self.stopped),@"revision":@(fdb_revision()),@"selected":selected,@"words":FdbWords(self.snapshot),@"pointer":@{@"x":@(self.mouseX),@"y":@(self.mouseY),@"buttons":@(self.buttons)}} mutableCopy];
    if (command[@"id"]) row[@"id"] = command[@"id"];
    if ([command[@"capture_frame"] boolValue]) {
        NSBitmapImageRep *rep = [self frameRep];
        row[@"frame_rgba_base64"] = [[NSData dataWithBytes:rep.bitmapData length:rep.bytesPerRow * rep.pixelsHigh] base64EncodedStringWithOptions:0];
    }
    if (command[@"frame_png"]) {
        NSData *png = [[self frameRep] representationUsingType:NSBitmapImageFileTypePNG properties:@{}];
        FdbCheck([png writeToFile:command[@"frame_png"] options:NSDataWritingWithoutOverwriting error:nil], @"Cannot write frame export");
    }
    if ([command[@"capture_view"] boolValue]) {
        NSRect bounds = self.view.bounds; NSInteger width = (NSInteger)ceil(bounds.size.width), height = (NSInteger)ceil(bounds.size.height);
        FdbCheck(width > 0 && height > 0 && width <= 4096 && height <= 4096, @"Offscreen view budget exceeded");
        NSBitmapImageRep *rep = [[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL pixelsWide:width pixelsHigh:height bitsPerSample:8 samplesPerPixel:4 hasAlpha:YES isPlanar:NO colorSpaceName:NSDeviceRGBColorSpace bitmapFormat:NSBitmapFormatAlphaNonpremultiplied bytesPerRow:width * 4 bitsPerPixel:32];
        FdbCheck(rep != nil,@"Cannot allocate offscreen view");
        CGColorSpaceRef colorSpace = CGColorSpaceCreateDeviceRGB();
        CGContextRef bitmap = CGBitmapContextCreate(rep.bitmapData,width,height,8,rep.bytesPerRow,colorSpace,kCGImageAlphaPremultipliedLast | kCGBitmapByteOrder32Big);
        FdbCheck(bitmap != NULL,@"Cannot create stored-state drawing context");
        CGContextTranslateCTM(bitmap,0,height); CGContextScaleCTM(bitmap,1,-1);
        NSGraphicsContext *context = [NSGraphicsContext graphicsContextWithCGContext:bitmap flipped:YES];
        [NSGraphicsContext saveGraphicsState]; NSGraphicsContext.currentContext = context;
        [self.view drawRect:bounds]; [context flushGraphics]; [NSGraphicsContext restoreGraphicsState];
        CGContextRelease(bitmap); CGColorSpaceRelease(colorSpace);
        row[@"view_size"] = @[@(width),@(height)];
        row[@"view_rgba_base64"] = [[NSData dataWithBytes:rep.bitmapData length:rep.bytesPerRow * rep.pixelsHigh] base64EncodedStringWithOptions:0];
        NSRect game = [self gameRect]; row[@"game_rect"] = @[@(game.origin.x),@(game.origin.y),@(game.size.width),@(game.size.height)];
    }
    return row;
}
- (void)runScript {
    NSMutableArray *rows = [NSMutableArray array]; NSString *failure = nil;
    @try {
        FdbCheck([self.script[@"format"] isEqual:@"fdisbull-native-adapter-study-1"] && [self.script[@"commands"] isKindOfClass:[NSArray class]] && [self.script[@"commands"] count] <= 4096, @"Invalid native adapter study");
        for (NSDictionary *command in self.script[@"commands"]) {
            @autoreleasepool {
                self.accepted = self.committed = NO;
                if (command[@"clock"]) { uint32_t clock = FdbUInt(command[@"clock"]); FdbCheck(clock <= 65535, @"Clock outside adapter domain"); self.scriptClock = clock; }
                NSString *kind = command[@"kind"];
                if ([kind isEqual:@"key"]) {
                    if ([command[@"focus"] isEqual:@"window"]) [self.window makeFirstResponder:nil]; else [self.window makeFirstResponder:self.view];
                    NSNumber *key = command[@"key_code"] ?: FdbKeyCodes()[command[@"code"]]; FdbCheck(key != nil && FdbUInt(key) <= 65535, @"Unknown diagnostic physical key");
                    NSEventModifierFlags flags = 0;
                    NSDictionary *flagMap = @{@"command":@(NSEventModifierFlagCommand),@"control":@(NSEventModifierFlagControl),@"option":@(NSEventModifierFlagOption),@"shift":@(NSEventModifierFlagShift),@"caps":@(NSEventModifierFlagCapsLock)};
                    for (NSString *name in command[@"modifiers"] ?: @[]) { FdbCheck(flagMap[name] != nil,@"Unknown modifier"); flags |= [flagMap[name] unsignedLongLongValue]; }
                    NSEvent *event = [NSEvent keyEventWithType:NSEventTypeKeyDown location:NSZeroPoint modifierFlags:flags timestamp:0 windowNumber:self.window.windowNumber context:nil characters:@"" charactersIgnoringModifiers:@"" isARepeat:NO keyCode:(unsigned short)FdbUInt(key)];
                    [self.window sendEvent:event];
                } else if ([kind isEqual:@"pointer"]) {
                    NSString *phase = command[@"phase"]; uint32_t button = command[@"button"] ? FdbUInt(command[@"button"]) : 0; FdbCheck(button <= 2,@"Only three pointer buttons supported");
                    NSEventType type = NSEventTypeMouseMoved;
                    if ([phase isEqual:@"down"]) type = button == 0 ? NSEventTypeLeftMouseDown : button == 1 ? NSEventTypeRightMouseDown : NSEventTypeOtherMouseDown;
                    else if ([phase isEqual:@"up"]) type = button == 0 ? NSEventTypeLeftMouseUp : button == 1 ? NSEventTypeRightMouseUp : NSEventTypeOtherMouseUp;
                    else if ([phase isEqual:@"drag"]) type = button == 0 ? NSEventTypeLeftMouseDragged : button == 1 ? NSEventTypeRightMouseDragged : NSEventTypeOtherMouseDragged;
                    else FdbCheck([phase isEqual:@"move"],@"Unknown pointer phase");
                    NSPoint point = NSMakePoint([command[@"x"] doubleValue],[command[@"y"] doubleValue]);
                    FdbCheck(isfinite(point.x) && isfinite(point.y),@"Invalid pointer coordinate");
                    if (![command[@"space"] isEqual:@"view"]) {
                        NSRect game = [self gameRect]; point = NSMakePoint(game.origin.x + (point.x + 0.5) * game.size.width / [self.frame[@"width"] doubleValue],game.origin.y + (point.y + 0.5) * game.size.height / [self.frame[@"height"] doubleValue]);
                    }
                    point = [self.view convertPoint:point toView:nil];
                    NSEvent *event = [NSEvent mouseEventWithType:type location:point modifierFlags:0 timestamp:0 windowNumber:self.window.windowNumber context:nil eventNumber:0 clickCount:1 pressure:[phase isEqual:@"up"] ? 0 : 1];
                    // The NSEvent convenience constructor initializes every
                    // button number to zero. Its CGEvent round trip preserves
                    // window/point identity while explicitly setting the real
                    // button field; this does not post a global OS event.
                    CGEventRef cg = CGEventCreateCopy(event.CGEvent); FdbCheck(cg != NULL,@"Cannot construct pointer event");
                    CGEventSetIntegerValueField(cg,kCGMouseEventButtonNumber,button);
                    event = [NSEvent eventWithCGEvent:cg]; CFRelease(cg);
                    FdbCheck(event != nil && event.buttonNumber == button && event.windowNumber == self.window.windowNumber && fabs(event.locationInWindow.x - point.x) < 1e-7 && fabs(event.locationInWindow.y - point.y) < 1e-7,@"Pointer event round trip differs");
                    if ([phase isEqual:@"move"]) [self.view mouseMoved:event];
                    else if ([phase isEqual:@"drag"]) [self.view mouseDragged:event];
                    else if ([phase isEqual:@"up"]) [self.view mouseUp:event];
                    else [self.view mouseDown:event];
                } else if ([kind isEqual:@"select"]) {
                    uint32_t slot = FdbUInt(command[@"slot"]), variant = FdbUInt(command[@"variant"]);
                    FdbCheck(slot < self.selectors.count && variant < self.selectors[slot].numberOfItems,@"Selector outside control domain");
                    NSPopUpButton *selector = self.selectors[slot]; [selector selectItemAtIndex:variant]; [selector sendAction:selector.action to:selector.target];
                } else if ([kind isEqual:@"replace"]) {
                    BOOL prefix = command[@"prefix_words"] != nil;
                    NSArray *values = prefix ? command[@"prefix_words"] : command[@"words"];
                    FdbCheck([values isKindOfClass:[NSArray class]] && (prefix ? (command[@"words"] == nil && values.count > 0 && values.count <= fdb_word_count()) : values.count == fdb_word_count()),@"Replacement arena length or mutually exclusive mode differs");
                    NSMutableData *data = prefix ? [self.snapshot mutableCopy] : [NSMutableData dataWithLength:fdb_word_count() * 4]; uint32_t *words = data.mutableBytes;
                    for (NSUInteger index = 0; index < values.count; index++) words[index] = FdbUInt(values[index]);
                    FdbCheck(fdb_replace_words(words,fdb_word_count()) == 0,[NSString stringWithUTF8String:fdb_last_error()] ?: @"Replacement refused"); [self copyCommittedWords];
                } else if ([kind isEqual:@"initialize"]) {
                    FdbCheck(fdb_initialize([self clock]) == 0,[NSString stringWithUTF8String:fdb_last_error()] ?: @"Initialization refused"); [self copyCommittedWords];
                } else if ([kind isEqual:@"clock"]) [self tick:nil];
                else if ([kind isEqual:@"focus-loss"]) { [self releasePointer]; [self.window makeFirstResponder:nil]; }
                else if ([kind isEqual:@"resize"]) {
                    double width = [command[@"width"] doubleValue], height = [command[@"height"] doubleValue];
                    FdbCheck(isfinite(width) && isfinite(height) && width >= 1 && height >= 1 && width <= 4096 && height <= 4096,@"Invalid diagnostic view size");
                    [self.view setFrameSize:NSMakeSize(width,height)];
                } else FdbCheck([kind isEqual:@"snapshot"],@"Unknown adapter command");
                [rows addObject:[self scriptRow:command]];
            }
        }
    } @catch (NSException *exception) { failure = exception.reason ?: exception.name; }
    NSMutableDictionary *result = [@{@"format":@"fdisbull-native-adapter-result-1",@"status":failure ? @"failed" : @"passed",@"rows":rows,@"scope":@"Programmatic NSEvent delivery through native window-key/production-view-pointer responders and controlled flipped drawRect context; not physical hardware or window hit-testing evidence",@"commits":@(self.commits)} mutableCopy];
    if (failure) result[@"error"] = failure;
    NSError *error = nil; NSData *data = [NSJSONSerialization dataWithJSONObject:result options:0 error:&error];
    self.resultCode = failure ? 2 : 0;
    if (!data || ![data writeToFile:self.resultPath options:NSDataWritingWithoutOverwriting error:&error]) { fprintf(stderr,"%s\n",(error.localizedDescription ?: @"Cannot write adapter result").UTF8String); self.resultCode = 2; }
    [self.timer invalidate]; [self.window orderOut:nil]; fdb_close(); [NSApp stop:nil];
}
@end

int main(int argc, const char **argv) {
    @autoreleasepool {
        @try {
            int optionIndex = 1;
            NSString *configPath = nil;
            if (argc > 1 && argv[1][0] != '-') { configPath = [NSString stringWithUTF8String:argv[1]]; optionIndex = 2; }
            else configPath = [NSBundle.mainBundle pathForResource:@"native-config" ofType:@"json"];
            int remaining = argc - optionIndex;
            BOOL diagnostic = remaining == 3 && strcmp(argv[optionIndex],"--adapter-test") == 0;
            BOOL exportFrame = remaining == 2 && strcmp(argv[optionIndex],"--export-frame") == 0;
            FdbCheck(remaining == 0 || diagnostic || exportFrame,@"Invalid native shell arguments");
            FdbCheck(configPath != nil,@"Usage: APP [CONFIG.json] [--adapter-test SCRIPT.json RESULT.json | --export-frame FRAME.png]");
            NSDictionary *config = FdbReadJSON(configPath,fdb_config_sha256()), *script = nil;
            if (diagnostic) script = FdbReadJSON([NSString stringWithUTF8String:argv[optionIndex + 1]],NULL);
            uint32_t clock = script[@"initial_clock"] ? FdbUInt(script[@"initial_clock"]) : 0;
            FdbCheck(clock <= 65535,@"Initial clock outside domain");
            if (script[@"initial_words"]) {
                NSArray *values = script[@"initial_words"]; FdbCheck([values isKindOfClass:[NSArray class]] && values.count == fdb_word_count(),@"Initial arena length differs");
                NSMutableData *data = [NSMutableData dataWithLength:values.count * 4]; uint32_t *words = data.mutableBytes;
                for (NSUInteger index = 0; index < values.count; index++) words[index] = FdbUInt(values[index]);
                FdbCheck(fdb_replace_words(words,values.count) == 0,@"Initial diagnostic replacement refused");
            }
            FdbHost *host = [[FdbHost alloc] initWithConfig:config]; host.diagnostic = diagnostic; host.script = script;
            if (script[@"initial_pointer"]) {
                NSDictionary *pointer = script[@"initial_pointer"];
                FdbCheck([pointer isKindOfClass:[NSDictionary class]],@"Initial pointer object required");
                host.mouseX = FdbUInt(pointer[@"x"]); host.mouseY = FdbUInt(pointer[@"y"]); host.buttons = FdbUInt(pointer[@"buttons"]);
                FdbCheck(host.mouseX < FdbUInt(host.frame[@"width"]) && host.mouseY < FdbUInt(host.frame[@"height"]) && host.buttons <= 7,@"Initial pointer outside declared domain");
            }
            if (diagnostic) { host.scriptClock = clock; host.resultPath = [NSString stringWithUTF8String:argv[optionIndex + 2]]; }
            else if (!exportFrame) clock = [host clock];
            FdbCheck(fdb_initialize(clock) == 0,[NSString stringWithUTF8String:fdb_last_error()] ?: @"Native initialization refused"); [host copyCommittedWords];
            if (exportFrame) {
                NSData *png = [[host frameRep] representationUsingType:NSBitmapImageFileTypePNG properties:@{}];
                FdbCheck([png writeToFile:[NSString stringWithUTF8String:argv[optionIndex + 1]] options:NSDataWritingWithoutOverwriting error:nil],@"Cannot write stored-state PNG"); fdb_close(); return 0;
            }
            NSApplication *app = NSApplication.sharedApplication; [app setActivationPolicy:NSApplicationActivationPolicyRegular]; app.delegate = host;
            NSMenu *menu = [[NSMenu alloc] initWithTitle:@"Main"];
            NSMenuItem *application = [[NSMenuItem alloc] initWithTitle:@"Application" action:nil keyEquivalent:@""];
            NSMenu *applicationMenu = [[NSMenu alloc] initWithTitle:@"Application"];
            [applicationMenu addItemWithTitle:@"Quit" action:@selector(terminate:) keyEquivalent:@"q"];
            application.submenu = applicationMenu; [menu addItem:application]; app.mainMenu = menu;
            [app run]; return host.resultCode;
        } @catch (NSException *exception) { fprintf(stderr,"%s\n",(exception.reason ?: exception.name).UTF8String); fdb_close(); return 2; }
    }
}
