#import "SHUI.h"
#import "SHBitmapFont.h"
#import "SHClueExplanation.h"
#import "SHVictoryCanvas.h"
#include <math.h>

static void SHText(NSString *text, NSRect rect, CGFloat size,
                   NSColor *color, BOOL centered, NSColor *shadow) {
    SHDrawBitmapText(text, rect, size, color, centered, shadow);
}

static void SHBox(NSRect rect, NSColor *fill, NSColor *border) {
    [fill setFill]; NSRectFill(rect);
    [border setStroke];
    NSBezierPath *path = [NSBezierPath bezierPathWithRect:NSInsetRect(rect, .5, .5)];
    path.lineWidth = 1; [path stroke];
}

static BOOL SHBoardPoint(NSPoint point, unsigned *row, unsigned *column) {
    if (point.x < 12 || point.x >= 324 || point.y < 18 || point.y >= 210)
        return NO;
    if (row) *row = (unsigned)((point.y - 18) / 32);
    if (column) *column = (unsigned)((point.x - 12) / 52);
    return YES;
}

static BOOL SHCluePoint(NSPoint point, unsigned *group, unsigned *slot,
                       unsigned *part) {
    if (point.x >= 331 && point.x < 627 && point.y >= 19 && point.y < 257) {
        unsigned column = (unsigned)((point.x - 331) / 100);
        unsigned row = (unsigned)((point.y - 19) / 34);
        unsigned local = (unsigned)(point.x - 331) % 100;
        if (local >= 96 || row >= 7 || column >= 3) return NO;
        *group = 1; *slot = column * 7 + row; *part = local / 32;
        return YES;
    }
    if (point.x >= 14 && point.x < 624 && point.y >= 267 && point.y < 331) {
        unsigned local = (unsigned)(point.x - 14) % 34;
        if (local >= 32) return NO;
        *group = 0; *slot = (unsigned)((point.x - 14) / 34);
        *part = point.y < 299 ? 0 : 1;
        return YES;
    }
    return NO;
}

static NSRect SHClueRect(unsigned group, unsigned slot) {
    return group ? NSMakeRect(331 + (slot / 7) * 100,
                              19 + (slot % 7) * 34, 96, 32)
                 : NSMakeRect(14 + slot * 34, 267, 32, 64);
}

@implementation SHGameView {
    BOOL _tracking, _right, _dragging;
    NSPoint _down, _current;
    NSInteger _object, _clue;
    unsigned _row, _column, _item;
    BOOL _boardHit;
    NSImage *_pauseImage;
    BOOL _pauseImageChecked;
    NSInteger _explanationClue;
    BOOL _drawingGame, _hasGameBackdrop;
    SHVictoryCanvas *_victoryCanvas;
    NSMutableDictionary<NSString *, NSImage *> *_menuImages;
}

- (instancetype)initWithFrame:(NSRect)frame {
    self = [super initWithFrame:frame];
    if (self) _explanationClue = -1;
    return self;
}

- (void)dismissClueExplanation {
    _explanationClue = -1;
    _tracking = _dragging = NO;
    self.needsDisplay = YES;
}

- (void)prepareForNewPuzzle {
    [self dismissClueExplanation];
    _hasGameBackdrop = YES;
    _victoryCanvas = nil;
}

- (BOOL)beginVictoryWithRandomState:(uint32_t)randomState {
    _victoryCanvas = [[SHVictoryCanvas alloc] initWithTiles:self.app.tilePixels
                                              randomState:randomState];
    _victoryCanvas.soundEnabled = [self.app.activeAppearance[@"sound"] boolValue];
    return _victoryCanvas != nil;
}

- (BOOL)advanceVictory {
    BOOL active = _victoryCanvas && [_victoryCanvas advance];
    self.needsDisplay = YES;
    return active;
}

- (void)skipVictory { [_victoryCanvas requestSkip]; }

- (BOOL)isFlipped { return YES; }
- (BOOL)acceptsFirstResponder { return YES; }

- (CGFloat)canvasScale {
    return MAX(.1, MIN(self.bounds.size.width / 640.0,
                      self.bounds.size.height / 350.0));
}

- (NSPoint)logicalPoint:(NSEvent *)event {
    NSPoint point = [self convertPoint:event.locationInWindow fromView:nil];
    CGFloat scale = [self canvasScale];
    point.x = (point.x - (self.bounds.size.width - 640 * scale) / 2) / scale;
    point.y = (point.y - (self.bounds.size.height - 350 * scale) / 2) / scale;
    return point;
}

- (NSColor *)role:(NSUInteger)role fallback:(NSUInteger)fallback {
    NSDictionary *appearance = (_drawingGame || self.app.showingGame) ? self.app.activeAppearance
                                                   : self.app.profile;
    NSArray *colors = appearance[@"colors"];
    NSUInteger index = role < colors.count ? [colors[role] unsignedIntegerValue]
                                          : fallback;
    return SHColor(index);
}

- (void)frame:(NSRect)rect fill:(NSColor *)fill {
    SHBox(rect, fill, [self role:0 fallback:8]);
    for (unsigned inset = 1; inset <= 2; ++inset) {
        [[self role:inset fallback:(inset == 1 ? 7 : 9)] setStroke];
        NSBezierPath *edge = [NSBezierPath bezierPathWithRect:
            NSInsetRect(rect, inset + .5, inset + .5)];
        edge.lineWidth = 1; [edge stroke];
    }
}

- (void)menuBox:(NSRect)rect {
    SHBox(rect, [self role:6 fallback:1], [self role:7 fallback:7]);
    [[self role:8 fallback:15] setStroke];
    NSBezierPath *edge = [NSBezierPath bezierPath];
    [edge moveToPoint:NSMakePoint(NSMinX(rect) + .5, NSMaxY(rect) - .5)];
    [edge lineToPoint:NSMakePoint(NSMaxX(rect) - .5, NSMaxY(rect) - .5)];
    [edge lineToPoint:NSMakePoint(NSMaxX(rect) - .5, NSMinY(rect) + .5)];
    edge.lineWidth = 1; [edge stroke];
}

- (void)tile:(NSInteger)tile at:(NSRect)rect half:(BOOL)half {
    NSArray<NSImage *> *images = half ? self.app.halfTiles : self.app.fullTiles;
    if (tile < 0 || tile >= (NSInteger)images.count) {
        [SHColor(2) setFill];
        NSRectFill(rect); return;
    }
    [images[(NSUInteger)tile] drawInRect:rect fromRect:NSZeroRect
        operation:NSCompositingOperationCopy fraction:1 respectFlipped:YES hints:nil];
}

- (void)background:(NSDictionary *)appearance {
    NSColor *base = [self role:3 fallback:8];
    [base setFill]; NSRectFill(NSMakeRect(0, 0, 640, 350));
    NSData *pattern = appearance[@"pattern"];
    if (pattern.length != 8) return;
    const uint8_t *rows = pattern.bytes;
    NSArray *colors = SHNormalizedColors(appearance[@"colors"]);
    NSImage *patternImage = SHPatternImage(rows, [colors[3] unsignedIntegerValue],
                                         [colors[4] unsignedIntegerValue]);
    /* Explicit top-first tiles keep the pattern preview, edit grid and canvas
     * on one orientation convention, independent of NSColor pattern phase. */
    for (unsigned y = 0; y < 350; y += 32)
        for (unsigned x = 0; x < 640; x += 32)
            [patternImage drawInRect:NSMakeRect(x, y, 32, 32) fromRect:NSZeroRect
                operation:NSCompositingOperationCopy fraction:1 respectFlipped:YES hints:nil];
}

- (BOOL)menuImage:(NSString *)name at:(NSRect)rect {
    if (!_menuImages) _menuImages = [NSMutableDictionary dictionary];
    NSImage *image = _menuImages[name];
    if (!image) {
        NSURL *url = [NSBundle.mainBundle URLForResource:name withExtension:@"png"];
        if (url) image = [[NSImage alloc] initWithContentsOfURL:url];
        if (image) _menuImages[name] = image;
    }
    if (!image) return NO;
    [image drawInRect:rect fromRect:NSZeroRect operation:NSCompositingOperationCopy
        fraction:1 respectFlipped:YES hints:nil];
    return YES;
}

- (void)drawMainMenu {
    SHApp *app = self.app;
    NSDictionary *profile = app.profile;
    BOOL originalColors = [SHNormalizedColors(profile[@"colors"])
                          isEqualToArray:SHDefaultColors()];
    BOOL boardBehindMenu = _hasGameBackdrop && !app.tournamentActive && !app.tournamentMode;
    if (boardBehindMenu) {
        /* Original menu overlays the board; the separate TIME pause screen
         * conceals it. Never reveal a board between tournament participants. */
        _drawingGame = YES;
        [self drawGameWithPauseScreen:NO];
        _drawingGame = NO;
    } else {
        [[self role:5 fallback:0] setFill]; NSRectFill(NSMakeRect(0, 0, 640, 350));
        if (!originalColors || ![self menuImage:@"MenuInformation" at:NSMakeRect(320, 38, 301, 210)]) {
            [self frame:NSMakeRect(320, 38, 301, 210) fill:[self role:6 fallback:1]];
            if (![self menuImage:@"MenuTitle" at:NSMakeRect(324, 44, 291, 101)])
                SHText(@"Sherlock", NSMakeRect(330, 67, 282, 60), 40,
                       SHColor(12), YES, SHColor(0));
            SHText(@"Revision 1.5 UK\nEverett Kaser\nNative macOS reconstruction",
                   NSMakeRect(330, 157, 282, 70), 8, [self role:9 fallback:14], YES,
                   [self role:10 fallback:0]);
        }
        if (!originalColors || ![self menuImage:@"MenuFooter" at:NSMakeRect(30, 260, 591, 90)]) {
            [self frame:NSMakeRect(30, 260, 591, 90) fill:[self role:6 fallback:1]];
            SHText(@"Sherlock by Everett Kaser.\nYour original images and numbered puzzles run in a native macOS application.",
                   NSMakeRect(40, 270, 570, 70), 8, [self role:9 fallback:14], NO,
                   [self role:10 fallback:0]);
        }
    }
    if (!originalColors || ![self menuImage:@"MenuFrame" at:NSMakeRect(30, 38, 276, 210)])
        [self frame:NSMakeRect(30, 38, 276, 210) fill:[self role:5 fallback:0]];
    NSString *number = [NSString stringWithFormat:@"%u", app.tournamentMode ?
        app.pendingTournamentNumber : (uint16_t)[profile[@"puzzle"] unsignedIntValue]];
    NSString *time = [profile[@"countDown"] boolValue]
        ? SHTime([profile[@"limit"] unsignedLongLongValue] * 1000) : @"No Limit";
    NSArray<NSArray<NSString *> *> *lines = @[
        @[@"", [app canResume] ? @"RESUME" : @"PLAY"],
        @[@"", [app canResume] ? @"RESTART" : @""],
        @[@"PUZZLE", @"NUMBER", @"", number],
        @[@"", @"PLAYER", @"", app.tournamentMode ? @"TOURNEY" : @"SINGLE"],
        @[@"", @"TIME", @"", time], @[@"", @"COLORS"],
        @[@"BACK", @"GROUND", @"", @"PATTERN"], @[@"", @"IMAGES"],
        @[@"", @"SOUND", @"", [profile[@"sound"] boolValue] ? @"YES" : @"NO"],
        @[], @[@"", @"HELP!"], @[@"", @"EXIT"]
    ];
    for (NSUInteger index = 0; index < lines.count; ++index) {
        NSRect rect = NSMakeRect(42 + (index % 4) * 64,
                                 49 + (index / 4) * 64, 61, 61);
        if (!originalColors || ![self menuImage:@"MenuButton" at:rect]) [self menuBox:rect];
        for (NSUInteger line = 0; line < lines[index].count; ++line) {
            BOOL value = line == 3 && (index == 2 || index == 3 || index == 4 || index == 8);
            SHText(lines[index][line], NSMakeRect(rect.origin.x, rect.origin.y + 10 + line * 10, 60, 9),
                   8, value ? SHColor(7) : [self role:9 fallback:14], YES,
                   value ? nil : [self role:10 fallback:0]);
        }
    }
}

- (void)notSymbolAt:(NSRect)rect {
    NSRect circle = NSInsetRect(rect, 3, 3);
    [SHColor(3) setStroke];
    NSBezierPath *path = [NSBezierPath bezierPathWithOvalInRect:circle];
    path.lineWidth = 2; [path stroke];
    path = [NSBezierPath bezierPath];
    [path moveToPoint:NSMakePoint(NSMinX(circle) + 3, NSMaxY(circle) - 3)];
    [path lineToPoint:NSMakePoint(NSMaxX(circle) - 3, NSMinY(circle) + 3)];
    path.lineWidth = 2; [path stroke];
}

- (void)betweenArrow:(NSRect)rect {
    CGFloat y = rect.origin.y + 2;
    [SHColor(15) setStroke];
    NSBezierPath *line = [NSBezierPath bezierPath];
    [line moveToPoint:NSMakePoint(rect.origin.x + 2, y)];
    [line lineToPoint:NSMakePoint(NSMaxX(rect) - 2, y)];
    [line moveToPoint:NSMakePoint(rect.origin.x + 7, y - 2)];
    [line lineToPoint:NSMakePoint(rect.origin.x + 2, y)];
    [line lineToPoint:NSMakePoint(rect.origin.x + 7, y + 3)];
    [line moveToPoint:NSMakePoint(NSMaxX(rect) - 7, y - 2)];
    [line lineToPoint:NSMakePoint(NSMaxX(rect) - 2, y)];
    [line lineToPoint:NSMakePoint(NSMaxX(rect) - 7, y + 3)];
    line.lineWidth = 1; [line stroke];
}

- (void)drawClue:(NSInteger)index group:(unsigned)group slot:(unsigned)slot {
    SherlockGame *game = self.app.game;
    NSRect rect = SHClueRect(group, slot);
    if (index < 0 || index >= game->puzzle.clue_count) {
        for (unsigned i = 0; i < (group ? 3u : 2u); ++i)
            [self tile:36 at:NSMakeRect(rect.origin.x + (group ? i * 32 : 0),
                                        rect.origin.y + (group ? 0 : i * 32),
                                        32, 32) half:NO];
        return;
    }
    SherlockClue *clue = &game->puzzle.clues[index];
    if (index < (NSInteger)self.app.clueImages.count) {
        [self.app.clueImages[(NSUInteger)index] drawInRect:rect fromRect:NSZeroRect
           operation:NSCompositingOperationCopy fraction:1 respectFlipped:YES hints:nil];
        return;
    }
    NSInteger objects[3] = { clue->a, clue->b, clue->c };
    if (group && (clue->type == 2 || clue->type == 3)) objects[2] = clue->a;
    if (clue->type == 4) { objects[1] = 45; objects[2] = clue->b; }
    if (clue->type == 7) objects[1] = objects[2] = 36;
    for (unsigned i = 0; i < (group ? 3u : 2u); ++i)
        [self tile:objects[i] at:NSMakeRect(rect.origin.x + (group ? i * 32 : 0),
                                          rect.origin.y + (group ? 0 : i * 32),
                                          32, 32) half:NO];
    if (clue->type == 1)
        [self notSymbolAt:NSMakeRect(rect.origin.x, rect.origin.y + 16, 32, 32)];
    if (clue->type == 3 || clue->type == 6)
        [self notSymbolAt:NSMakeRect(rect.origin.x + 32, rect.origin.y, 32, 32)];
    if (clue->type == 5 || clue->type == 6) [self betweenArrow:rect];
}

- (void)drawGameWithPauseScreen:(BOOL)showPause {
    SHApp *app = self.app;
    SherlockGame *game = app.game;
    if (showPause && game->paused) {
        /* Original observation: pause conceals the entire puzzle and every
         * clue. Never draw the game behind a smaller pause notice. */
        [SHColor(0) setFill]; NSRectFill(NSMakeRect(0, 0, 640, 350));
        if (!_pauseImageChecked) {
            _pauseImageChecked = YES;
            NSURL *url = [NSBundle.mainBundle URLForResource:@"Pause" withExtension:@"png"];
            if (url) _pauseImage = [[NSImage alloc] initWithContentsOfURL:url];
        }
        if (_pauseImage)
            [_pauseImage drawInRect:NSMakeRect(0, 0, 640, 350) fromRect:NSZeroRect
                  operation:NSCompositingOperationCopy fraction:1 respectFlipped:YES hints:nil];
        else {
            SHText(@"PAUSED", NSMakeRect(40, 125, 560, 50), 27, SHColor(15), YES, nil);
            SHText(@"Click to continue", NSMakeRect(40, 187, 560, 30), 13, SHColor(15), YES, nil);
        }
        return;
    }
    NSColor *panel = [self role:6 fallback:1];
    NSColor *ink = [self role:9 fallback:14];
    NSColor *shadow = [self role:10 fallback:0];
    [self background:app.activeAppearance];
    [self frame:NSMakeRect(7, 8, 626, 334) fill:[self role:5 fallback:0]];
    [self frame:NSMakeRect(10, 16, 316, 198) fill:SHColor(0)];
    for (unsigned row = 0; row < 6; ++row) for (unsigned column = 0; column < 6; ++column) {
        CGFloat x = 12 + column * 52, y = 18 + row * 32;
        SHBox(NSMakeRect(x, y, 52, 32), SHColor(0), SHColor(15));
        int selected = game->board.chosen[row][column];
        if (selected >= 0) {
            [self tile:row * 6 + selected at:NSMakeRect(x + 10, y, 32, 32) half:NO];
        } else {
            for (unsigned item = 0; item < 6; ++item) {
                NSInteger image = (game->board.candidates[row][column] & (1u << item))
                                ? (NSInteger)(row * 6 + item) : 36;
                [self tile:image at:NSMakeRect(x + 2 + (item % 3) * 16,
                                               y + (item / 3) * 16, 16, 16) half:YES];
            }
        }
    }
    [self frame:NSMakeRect(330, 16, 300, 243) fill:SHColor(0)];
    for (unsigned slot = 0; slot < 21; ++slot)
        [self drawClue:game->board.clue_slots[app.visibleBank][1][slot]
                  group:1 slot:slot];
    [self frame:NSMakeRect(10, 263, 620, 72) fill:SHColor(0)];
    for (unsigned slot = 0; slot < 18; ++slot)
        [self drawClue:game->board.clue_slots[app.visibleBank][0][slot]
                  group:0 slot:slot];
    NSArray *names = @[app.tournamentActive ? @"QUIT" : @"MENU",
                       app.visibleBank ? @"GAME CLUES" : @"OTHER CLUES", @"UNDO", @"HINT"];
    NSRect buttons[] = {NSMakeRect(13, 217, 89, 21), NSMakeRect(107, 217, 87, 21),
                         NSMakeRect(13, 241, 89, 19), NSMakeRect(107, 241, 87, 19)};
    for (unsigned i = 0; i < 4; ++i) {
        [self menuBox:buttons[i]];
        SHText(names[i], NSMakeRect(i % 2 ? 105 : 12, i < 2 ? 223 : 246, 88, 9),
               8, ink, YES, shadow);
    }
    [self menuBox:NSMakeRect(198, 217, 126, 14)];
    [self menuBox:NSMakeRect(198, 231, 126, 14)];
    [self menuBox:NSMakeRect(198, 245, 126, 15)];
    SHText([@"NAME: " stringByAppendingString:app.activePlayerName ?: @"Player"],
           NSMakeRect(201, 219, 121, 12), 8, ink, NO, shadow);
    SHText([@"TIME: " stringByAppendingString:SHTime(sh_display_time_ms(game))],
           NSMakeRect(201, 233, 121, 12), 8, ink, NO, shadow);
    SHText(app.puzzleLabel,
           NSMakeRect(201, 247, 121, 12), 8, ink, NO, shadow);
    if (game->outcome == SH_WON) {
        SHBox(NSMakeRect(28, 272, 139, 21), SHColor(14), SHColor(0));
        [SHColor(15) setFill]; NSRectFill(NSMakeRect(30, 274, 135, 1));
        SHText(@"Elementary, Watson!", NSMakeRect(42, 278, 120, 9),
               8, SHColor(9), NO, nil);
    }
    if (game->hint_pending) {
        SHHint hint = game->pending_hint;
        unsigned bank, group, slot;
        if (hint.clue_index >= 0 &&
            sh_clue_location(game, (unsigned)hint.clue_index, &bank, &group, &slot) &&
            bank == (unsigned)app.visibleBank &&
            fmod(NSProcessInfo.processInfo.systemUptime, 1) < .5) {
            [SHColor(5) setStroke];
            NSBezierPath *highlight = [NSBezierPath bezierPathWithRect:
                                       NSInsetRect(SHClueRect(group, slot), -1, -1)];
            highlight.lineWidth = 2; [highlight stroke];
        }
        NSRect target = NSMakeRect(14 + hint.column * 52 + (hint.item % 3) * 16,
                                   18 + hint.row * 32 + (hint.item / 3) * 16, 16, 16);
        [SHColor(5) setStroke];
        NSBezierPath *highlight = [NSBezierPath bezierPathWithRect:NSInsetRect(target, 1, 1)];
        highlight.lineWidth = 2; [highlight stroke];
        NSPoint tip = NSMakePoint(NSMidX(target), NSMinY(target) + 5);
        NSBezierPath *arrow = [NSBezierPath bezierPath];
        [arrow moveToPoint:NSMakePoint(tip.x, tip.y - 14)];
        [arrow lineToPoint:tip];
        [arrow moveToPoint:NSMakePoint(tip.x - 3, tip.y - 5)];
        [arrow lineToPoint:tip];
        [arrow lineToPoint:NSMakePoint(tip.x + 3, tip.y - 5)];
        arrow.lineWidth = 2; [arrow stroke];
        SHBox(NSMakeRect(353, 1, 286, 126), panel, SHColor(5));
        SHText(@"HINT", NSMakeRect(363, 5, 266, 16), 10, SHColor(5), YES, shadow);
        SHText([NSString stringWithUTF8String:hint.explanation],
               NSMakeRect(363, 24, 266, 71), 9, ink, NO, shadow);
        SHText(@"Click to apply. 30 seconds added.",
               NSMakeRect(363, 104, 266, 17), 8, ink, YES, shadow);
    }
    if (_tracking && _dragging && _object >= 0) {
        CGFloat size = _right ? 16 : 32;
        [self tile:_object at:NSMakeRect(_current.x - size / 2,
                                         _current.y - size / 2, size, size) half:_right];
    }
    [_victoryCanvas draw];
    if (self.app.showingGame && game->outcome == SH_PLAYING &&
        !game->paused && !game->hint_pending && _explanationClue >= 0) {
        unsigned bank, group, slot;
        if (sh_clue_location(game, (unsigned)_explanationClue, &bank, &group, &slot) &&
            bank == (unsigned)app.visibleBank) {
            [SHColor(5) setStroke];
            NSBezierPath *border = [NSBezierPath bezierPathWithRect:
                NSInsetRect(SHClueRect(group, slot), -1, -1)];
            border.lineWidth = 2; [border stroke];
            SHDrawClueExplanation(&game->puzzle, (unsigned)_explanationClue,
                                 app.fullTiles, NSMakePoint(337, 23));
        }
    }
}

- (void)drawRect:(NSRect)dirtyRect {
    (void)dirtyRect;
    [NSColor.blackColor setFill]; NSRectFill(self.bounds);
    [NSGraphicsContext saveGraphicsState];
    CGFloat scale = [self canvasScale];
    NSAffineTransform *transform = [NSAffineTransform transform];
    [transform translateXBy:(self.bounds.size.width - 640 * scale) / 2
                        yBy:(self.bounds.size.height - 350 * scale) / 2];
    [transform scaleBy:scale]; [transform concat];
    NSRectClip(NSMakeRect(0, 0, 640, 350));
    NSGraphicsContext.currentContext.imageInterpolation = NSImageInterpolationNone;
    if (self.app.showingGame) {
        _drawingGame = YES;
        [self drawGameWithPauseScreen:YES];
        _drawingGame = NO;
    } else [self drawMainMenu];
    [NSGraphicsContext restoreGraphicsState];
}

- (NSInteger)objectForClue:(NSInteger)index part:(unsigned)part {
    SherlockGame *game = self.app.game;
    if (index < 0 || index >= game->puzzle.clue_count) return -1;
    SherlockClue *clue = &game->puzzle.clues[index];
    if (part == 0) return clue->a;
    if (clue->type == 7) return -1;
    if (clue->type == 4) return part == 1 ? -1 : clue->b;
    if (part == 1) return clue->b;
    if (clue->type == 2 || clue->type == 3) return clue->a;
    return clue->c;
}

- (void)begin:(NSEvent *)event right:(BOOL)right {
    [self.window makeFirstResponder:self];
    _tracking = NO;
    _right = right;
    _down = _current = [self logicalPoint:event];
    SherlockGame *game = self.app.game;
    if (self.app.awaitingWinAcknowledgement || self.app.celebrating) {
        [self.app acknowledgeWin]; return;
    }
    if (_explanationClue >= 0 && self.app.showingGame && !game->paused &&
        game->outcome == SH_PLAYING) {
        [self dismissClueExplanation]; return;
    }
    _explanationClue = -1; /* A hidden inspector must never eat a menu click. */
    if (self.app.showingGame && game->hint_pending) {
        enum SHHintKind kind = game->pending_hint.kind;
        if (sh_accept_hint(game) == 1)
            SHPlaySound(kind == SH_HINT_CHOOSE ? @"choose" : @"remove",
                        [self.app.activeAppearance[@"sound"] boolValue]);
        [self.app changed]; return;
    }
    if (self.app.showingGame && game->paused) {
        sh_set_paused(game, 0); [self.app changed]; return;
    }
    _tracking = YES; _dragging = NO; _object = -1; _clue = -1; _boardHit = NO;
    if (!self.app.showingGame) return;
    if (SHBoardPoint(_down, &_row, &_column)) {
        int chosen = game->board.chosen[_row][_column];
        CGFloat x = _down.x - (12 + _column * 52);
        CGFloat y = _down.y - (18 + _row * 32);
        if (chosen >= 0) {
            if (x >= 10 && x < 42) { _item = (unsigned)chosen; _boardHit = YES; }
        } else if (x >= 2 && x < 50) {
            _item = (unsigned)((x - 2) / 16) + (unsigned)(y / 16) * 3;
            _boardHit = (game->board.candidates[_row][_column] & (1u << _item)) != 0;
        }
        if (_boardHit) _object = _row * 6 + _item;
        return;
    }
    unsigned group, slot, part;
    if (SHCluePoint(_down, &group, &slot, &part)) {
        _clue = game->board.clue_slots[self.app.visibleBank][group][slot];
        _object = [self objectForClue:_clue part:part];
    }
}

- (void)mouseDown:(NSEvent *)event { [self begin:event right:NO]; }
- (void)rightMouseDown:(NSEvent *)event { [self begin:event right:YES]; }
- (void)mouseDragged:(NSEvent *)event {
    if (!_tracking) return;
    _current = [self logicalPoint:event];
    if (hypot(_current.x - _down.x, _current.y - _down.y) > 3) _dragging = YES;
    self.needsDisplay = YES;
}
- (void)rightMouseDragged:(NSEvent *)event { [self mouseDragged:event]; }

- (void)mouseUp:(NSEvent *)event {
    if (!_tracking) return;
    _tracking = NO;
    NSPoint point = [self logicalPoint:event];
    if (!self.app.showingGame) {
        if (!_dragging) for (NSUInteger i = 0; i < 12; ++i)
            if (NSPointInRect(point, NSMakeRect(42 + (i % 4) * 64,
                                              49 + (i / 4) * 64, 61, 61))) {
                [self.app menuAction:i]; break;
            }
        return;
    }
    SherlockGame *game = self.app.game;
    int mutation = 0;
    NSString *cue = nil;
    if (_dragging) {
        unsigned row, column, group, slot, part;
        if (_right && _object >= 0 && SHBoardPoint(point, &row, &column) &&
            row == (unsigned)_object / 6) {
            mutation = sh_restore(game, row, column, (unsigned)_object % 6);
            cue = mutation == 1 ? @"restore" : @"error";
        } else if (_clue >= 0 && SHCluePoint(point, &group, &slot, &part) &&
                   group == (unsigned)sh_puzzle_clue_group(&game->puzzle, (unsigned)_clue)) {
            mutation = sh_move_clue(game, (unsigned)_clue, slot);
            if (mutation == 1) cue = @"move";
        }
    } else if (_boardHit) {
        if (_right) mutation = sh_remove(game, _row, _column, _item);
        else mutation = sh_choose(game, _row, _column, _item);
        cue = mutation == 1 ? (_right ? @"remove" : @"choose") : @"error";
    } else if (_clue >= 0 && _right) {
        mutation = sh_archive_clue(game, (unsigned)_clue);
        cue = mutation == 1 ? @"archive" : @"error";
    } else if (_clue >= 0 && !_right && game->outcome == SH_PLAYING) {
        _explanationClue = _clue;
    } else {
        NSRect controls[] = {NSMakeRect(13, 217, 89, 21), NSMakeRect(107, 217, 87, 21),
                             NSMakeRect(13, 241, 89, 19), NSMakeRect(107, 241, 87, 19),
                             NSMakeRect(198, 231, 126, 14)};
        for (NSUInteger i = 0; i < 5; ++i)
            if (NSPointInRect(point, controls[i])) { [self.app gameAction:i]; break; }
    }
    if (cue) SHPlaySound(cue, [self.app.activeAppearance[@"sound"] boolValue]);
    [self.app changed];
}
- (void)rightMouseUp:(NSEvent *)event { [self mouseUp:event]; }

- (void)keyDown:(NSEvent *)event {
    if (self.app.awaitingWinAcknowledgement || self.app.celebrating)
        [self.app acknowledgeWin];
    else if (event.keyCode == 53 && _explanationClue >= 0) [self dismissClueExplanation];
    else if (event.keyCode == 53 && self.app.showingGame) [self.app gameAction:0];
    else [super keyDown:event];
}
@end
