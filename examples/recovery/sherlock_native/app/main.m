#import "SHUI.h"
#import "SHBitmapFont.h"
#include "../cli/sherlock_cli.h"
#include "../core/sherlock_logic.h"
#include <dispatch/dispatch.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

static NSMutableDictionary *SHNewProfile(NSString *name) {
    /* Clean no-CFG original launch selected preset index 2. */
    NSData *pattern = SHDefaultPattern();
    return [@{
        @"id":NSUUID.UUID.UUIDString, @"name":name ?: @"Player", @"puzzle":@0,
        @"countDown":@NO, @"limit":@600, @"sound":@NO,
        @"colors":SHDefaultColors(),
        @"pattern":pattern ?: [NSMutableData dataWithLength:8]
    } mutableCopy];
}

static NSMenuItem *SHMenuItem(NSString *title, SEL action, NSString *key, id target) {
    NSMenuItem *item = [[NSMenuItem alloc] initWithTitle:title action:action keyEquivalent:key];
    item.target = target;
    return item;
}

@implementation SHApp {
    SherlockGame _game;
    NSMutableDictionary *_activeProfile;
    NSURL *_preferencesURL;
    NSTimer *_timer;
    NSTimeInterval _lastTick;
    double _fractionalMilliseconds;
    uint32_t _initialTimeLimit;
    BOOL _reportedOutcome;
    NSMutableArray<NSMutableDictionary *> *_tournamentRows;
    NSUInteger _tournamentTurn;
    SherlockPuzzle _tournamentPuzzle;
    uint32_t _tournamentLimit;
    BOOL _randomGame;
    BOOL _generatingRandom;
    uint64_t _randomSeed;
    uint16_t _randomProfileNumber;
}

- (SherlockGame *)game { return &_game; }

- (NSString *)puzzleLabel {
    return _randomGame ? @"NATIVE RANDOM" :
        [NSString stringWithFormat:@"PUZZLE: %u", _game.puzzle.number];
}

- (NSString *)puzzleIdentity {
    return _randomGame ? [NSString stringWithFormat:@"Native random v%u, seed %llu",
        SHERLOCK_NATIVE_GENERATOR_VERSION, (unsigned long long)_randomSeed] :
        [NSString stringWithFormat:@"Puzzle %u", _game.puzzle.number];
}

- (BOOL)canResume {
    /* Original observation: changing the selected number changes RESUME to
     * PLAY and hides RESTART; selecting the active number again restores both.
     * A different player or mode starts a separate game in this native app. */
    return self.hasGame && _game.outcome == SH_PLAYING &&
           !self.tournamentMode && !self.tournamentActive &&
           _activeProfile == self.profile &&
           (_randomGame ? _randomProfileNumber : _game.puzzle.number) ==
               (uint16_t)[self.profile[@"puzzle"] unsignedIntValue];
}

- (NSMutableDictionary *)profile {
    if (!self.profiles.count) return SHNewProfile(@"Player");
    if (self.selectedProfile < 0 || self.selectedProfile >= (NSInteger)self.profiles.count)
        self.selectedProfile = 0;
    return self.profiles[(NSUInteger)self.selectedProfile];
}

- (void)loadProfiles {
    NSURL *support = [NSFileManager.defaultManager URLsForDirectory:NSApplicationSupportDirectory
                                                         inDomains:NSUserDomainMask].firstObject;
    _preferencesURL = [[support URLByAppendingPathComponent:@"Sherlock Native" isDirectory:YES]
                       URLByAppendingPathComponent:@"Profiles.plist"];
    self.profiles = [NSMutableArray array];
    self.participants = [NSMutableIndexSet indexSet];
    NSData *bytes = [NSData dataWithContentsOfURL:_preferencesURL];
    NSDictionary *root = bytes ? [NSPropertyListSerialization propertyListWithData:bytes
                options:NSPropertyListMutableContainersAndLeaves format:NULL error:NULL] : nil;
    if (![root isKindOfClass:NSDictionary.class] ||
        ![root[@"version"] isKindOfClass:NSNumber.class] ||
        ([root[@"version"] integerValue] != 1 && [root[@"version"] integerValue] != 2))
        return;
    NSArray *records = root[@"players"];
    if (![records isKindOfClass:NSArray.class]) return;
    for (id candidate in records) {
        if (![candidate isKindOfClass:NSDictionary.class])
            continue;
        NSString *name = candidate[@"name"];
        if (![name isKindOfClass:NSString.class] || !name.length) continue;
        NSMutableDictionary *profile = SHNewProfile(name);
        for (NSString *key in @[@"id", @"imagePath"])
            if ([candidate[key] isKindOfClass:NSString.class]) profile[key] = candidate[key];
        for (NSString *key in @[@"puzzle", @"countDown", @"limit", @"sound"])
            if ([candidate[key] isKindOfClass:NSNumber.class]) profile[key] = candidate[key];
        profile[@"puzzle"] = @((uint16_t)[profile[@"puzzle"] unsignedIntValue]);
        if ([profile[@"limit"] unsignedLongLongValue] > 359999)
            profile[@"limit"] = @600;
        profile[@"colors"] = SHNormalizedColors(candidate[@"colors"]);
        NSData *pattern = candidate[@"pattern"];
        if ([pattern isKindOfClass:NSData.class] && pattern.length == 8)
            profile[@"pattern"] = pattern;
        /* Version 1 silently persisted accepted editor pixels. Preserve that
         * existing artwork as a migration fallback; newly accepted pixels are
         * session state and never enter the version-2 preferences document. */
        NSData *legacy = candidate[[root[@"version"] integerValue] == 1 ?
                                    @"images" : @"legacyImages"];
        if ([legacy isKindOfClass:NSData.class] && legacy.length == 46 * 32 * 32)
            profile[@"legacyImages"] = legacy;
        [self.profiles addObject:profile];
    }
    if ([root[@"selected"] isKindOfClass:NSNumber.class])
        self.selectedProfile = [root[@"selected"] integerValue];
    if (self.selectedProfile < 0 || self.selectedProfile >= (NSInteger)self.profiles.count)
        self.selectedProfile = 0;
    if (self.profiles.count) [self.participants addIndex:(NSUInteger)self.selectedProfile];
}

- (void)saveProfiles {
    if (!_preferencesURL || !self.profiles.count) return;
    NSError *error = nil;
    NSMutableArray *records = [NSMutableArray arrayWithCapacity:self.profiles.count];
    for (NSDictionary *profile in self.profiles) {
        NSMutableDictionary *record = [profile mutableCopy];
        [record removeObjectForKey:@"images"];
        [records addObject:record];
    }
    NSDictionary *root = @{@"version":@2, @"players":records,
                           @"selected":@(self.selectedProfile)};
    NSData *data = [NSPropertyListSerialization dataWithPropertyList:root
                  format:NSPropertyListBinaryFormat_v1_0 options:0 error:&error];
    NSURL *directory = [_preferencesURL URLByDeletingLastPathComponent];
    BOOL directoryReady = [NSFileManager.defaultManager createDirectoryAtURL:directory
                 withIntermediateDirectories:YES attributes:nil error:&error];
    if (!data || !directoryReady || ![data writeToURL:_preferencesURL
                                            options:NSDataWritingAtomic error:&error])
        SHMessage(@"Configuration was not saved", error.localizedDescription ?: @"The file could not be written.");
}

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    (void)notification;
    NSString *resources = NSBundle.mainBundle.resourcePath;
    if (!SHBitmapFontIsAvailable()) {
        SHMessage(@"The original font could not be loaded",
                  @"Extract the complete source package, including Resources/SherlockFont.bin, before building.");
        [NSApp terminate:nil];
        return;
    }
    if ([SHPresetPatterns() length] != 16 * 8) {
        SHMessage(@"Pattern resources could not be loaded",
                  @"The private resource pack must include a 128-byte PatternPresets.bin file.");
        [NSApp terminate:nil];
        return;
    }
    [self loadProfiles];
    NSString *tablePath = [resources stringByAppendingPathComponent:@"sherlock_puzzles.bin"];
    if (!tablePath || sherlock_load_puzzle_table(tablePath.fileSystemRepresentation) != 0) {
        SHMessage(@"Puzzle data could not be loaded",
            [NSString stringWithFormat:@"%@\n\n%s", tablePath ?: @"Missing application resources",
                                       sherlock_core_error()]);
        [NSApp terminate:nil];
        return;
    }
    self.defaultImagePath = [resources stringByAppendingPathComponent:@"Images/ORGINAL.SHI"];
    if (![NSFileManager.defaultManager fileExistsAtPath:self.defaultImagePath])
        self.defaultImagePath = [resources stringByAppendingPathComponent:@"ORGINAL.SHI"];
    self.factoryImagePath = [resources stringByAppendingPathComponent:@"Images/ORGINAL.SHI"];
    if (![NSFileManager.defaultManager fileExistsAtPath:self.factoryImagePath])
        self.factoryImagePath = [resources stringByAppendingPathComponent:@"ORGINAL.SHI"];
    NSRect screen = NSScreen.mainScreen.visibleFrame;
    CGFloat width = MIN(1280.0, screen.size.width - 80);
    CGFloat height = width * 350.0 / 640.0;
    if (height > screen.size.height - 100) {
        height = screen.size.height - 100; width = height * 640.0 / 350.0;
    }
    self.window = [[NSWindow alloc] initWithContentRect:NSMakeRect(80, 80, width, height)
        styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                  NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable
        backing:NSBackingStoreBuffered defer:NO];
    self.window.title = @"Sherlock — native macOS";
    self.window.delegate = self;
    self.window.contentMinSize = NSMakeSize(640, 350);
    self.window.contentAspectRatio = NSMakeSize(640, 350);
    self.gameView = [[SHGameView alloc] initWithFrame:NSMakeRect(0, 0, width, height)];
    self.gameView.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
    self.gameView.app = self;
    self.window.contentView = self.gameView;
    [self.window makeFirstResponder:self.gameView];
    [self makeMenus];
    [self.window center]; [self.window makeKeyAndOrderFront:nil];
    [NSApp activateIgnoringOtherApps:YES];
    if (!self.profiles.count) {
        NSString *name = nil;
        while (!name.length) {
            name = SHAsk(@"New player", @"Enter a player name to begin.", @"Player");
            if (!name) { [NSApp terminate:nil]; return; }
        }
        [self.profiles addObject:SHNewProfile(name)];
        [self.participants addIndex:0];
        [self saveProfiles];
    }
    uint8_t initialImages[46][32][32];
    if (SHLoadProfileImages(self.profile, self.defaultImagePath, initialImages))
        self.profile[@"images"] = [NSData dataWithBytes:initialImages length:sizeof initialImages];
    _lastTick = NSProcessInfo.processInfo.systemUptime;
    _timer = [NSTimer timerWithTimeInterval:1.0 / 60.0 target:self selector:@selector(timerFired:)
                                 userInfo:nil repeats:YES];
    [NSRunLoop.mainRunLoop addTimer:_timer forMode:NSRunLoopCommonModes];
    [self changed];
}

- (void)makeMenus {
    NSMenu *bar = [[NSMenu alloc] init];
    NSMenuItem *application = [[NSMenuItem alloc] init];
    [bar addItem:application];
    NSMenu *menu = [[NSMenu alloc] initWithTitle:@"Sherlock"];
    [menu addItem:SHMenuItem(@"About Sherlock", @selector(about:), @"", self)];
    [menu addItem:NSMenuItem.separatorItem];
    [menu addItem:SHMenuItem(@"Quit Sherlock", @selector(terminate:), @"q", NSApp)];
    application.submenu = menu;
    NSMenuItem *game = [[NSMenuItem alloc] initWithTitle:@"Game" action:NULL keyEquivalent:@""];
    [bar addItem:game];
    NSMenu *commands = [[NSMenu alloc] initWithTitle:@"Game"];
    [commands addItem:SHMenuItem(@"Play / Resume", @selector(play:), @"n", self)];
    [commands addItem:SHMenuItem(@"New Random Puzzle", @selector(newRandomPuzzle:), @"r", self)];
    [commands addItem:SHMenuItem(@"Copy Puzzle Identity", @selector(copyPuzzleIdentity:), @"", self)];
    [commands addItem:NSMenuItem.separatorItem];
    [commands addItem:SHMenuItem(@"Undo", @selector(undoMove:), @"z", self)];
    NSMenuItem *hint = SHMenuItem(@"Hint", @selector(requestHint:), @"h", self);
    hint.keyEquivalentModifierMask = NSEventModifierFlagCommand | NSEventModifierFlagShift;
    [commands addItem:hint];
    [commands addItem:SHMenuItem(@"Pause", @selector(togglePause:), @"p", self)];
    [commands addItem:SHMenuItem(@"Show Other Clues", @selector(toggleClueBank:), @"b", self)];
    [commands addItem:SHMenuItem(@"Return to Main Menu", @selector(returnToMenu:), @"", self)];
    [commands addItem:NSMenuItem.separatorItem];
    [commands addItem:SHMenuItem(@"Players…", @selector(players:), @"", self)];
    [commands addItem:SHMenuItem(@"Images…", @selector(images:), @"", self)];
    [commands addItem:SHMenuItem(@"Help", @selector(help:), @"?", self)];
    [commands addItem:SHMenuItem(@"Original manual…", @selector(originalManual:), @"", self)];
    game.submenu = commands;
    NSApp.mainMenu = bar;
}

- (void)sampleGameClock {
    NSTimeInterval now = NSProcessInfo.processInfo.systemUptime;
    double delta = MAX(0, now - _lastTick) * 1000 + _fractionalMilliseconds;
    uint64_t whole = (uint64_t)floor(delta);
    _fractionalMilliseconds = delta - whole;
    _lastTick = now;
    if (self.hasGame) sh_tick(&_game, whole);
}

- (void)timerFired:(NSTimer *)timer {
    (void)timer;
    NSTimeInterval previousTick = _lastTick;
    uint64_t previousDisplay = sh_display_time_ms(&_game) / 1000;
    [self sampleGameClock];
    NSTimeInterval now = _lastTick;
    if (self.celebrating) {
        /* Native presentation cadence: four bounded motion events per refresh.
         * Original movement is qualified independently of DOS CPU pacing. */
        for (unsigned i = 0; i < 4; ++i) {
            if (![self.gameView advanceVictory]) {
                self.celebrating = NO;
                self.hasGame = NO;
                self.showingGame = NO;
                break;
            }
        }
    }
    if (self.showingGame &&
        (previousDisplay != sh_display_time_ms(&_game) / 1000 ||
         (_game.hint_pending && floor(now * 2) != floor(previousTick * 2))))
        self.gameView.needsDisplay = YES;
    [self finishIfNeeded];
}

- (BOOL)loadImagesForGame:(NSMutableDictionary *)profile puzzle:(const SherlockPuzzle *)puzzle {
    uint8_t pixels[46][32][32];
    if (!SHLoadProfileImages(profile, self.defaultImagePath, pixels)) {
        SHMessage(@"Choose an image set", @"The selected image set was not found or could not be decoded. Select one of your original Sherlock .SHI files.");
        NSOpenPanel *panel = NSOpenPanel.openPanel;
        panel.allowedFileTypes = @[@"shi"];
        panel.allowsMultipleSelection = NO;
        NSString *path = [profile[@"imagePath"] length] ? profile[@"imagePath"] : self.defaultImagePath;
        if (path.length) panel.directoryURL = [NSURL fileURLWithPath:path.stringByDeletingLastPathComponent
                                                        isDirectory:YES];
        if ([panel runModal] != NSModalResponseOK ||
            shi_load(panel.URL.fileSystemRepresentation, pixels) != 0) return NO;
        profile[@"imagePath"] = panel.URL.path;
        [profile removeObjectForKey:@"images"];
        [profile removeObjectForKey:@"legacyImages"];
        [self saveProfiles];
    }
    NSArray<NSImage *> *full = SHImages(pixels, NO);
    NSArray<NSImage *> *half = SHImages(pixels, YES);
    NSArray<NSImage *> *clues = SHClueImages(puzzle, pixels);
    if (full.count != 46 || half.count != 46 || clues.count != puzzle->clue_count) {
        SHMessage(@"Puzzle images could not be prepared",
                  @"The puzzle or its image resources could not be rendered. The current game has been retained.");
        return NO;
    }
    self.fullTiles = full;
    self.halfTiles = half;
    self.clueImages = clues;
    self.tilePixels = [NSData dataWithBytes:pixels length:sizeof pixels];
    profile[@"images"] = self.tilePixels;
    return YES;
}

- (BOOL)beginPuzzle:(const SherlockPuzzle *)puzzle
           profile:(NSMutableDictionary *)profile limit:(uint32_t)limit {
    if (![self loadImagesForGame:profile puzzle:puzzle]) return NO;
    sh_game_init(&_game, puzzle, limit);
    _randomGame = NO;
    self.window.title = @"Sherlock Native";
    _activeProfile = profile;
    self.activeAppearance = [profile copy];
    self.activePlayerName = [profile[@"name"] copy];
    _initialTimeLimit = limit;
    _reportedOutcome = NO;
    self.awaitingWinAcknowledgement = NO;
    self.celebrating = NO;
    self.visibleBank = 0;
    self.hasGame = YES;
    self.showingGame = YES;
    [self.gameView prepareForNewPuzzle];
    _lastTick = NSProcessInfo.processInfo.systemUptime;
    _fractionalMilliseconds = 0;
    self.gameView.needsDisplay = YES;
    return YES;
}

- (void)startSingleGame {
    if (_generatingRandom) return;
    SherlockPuzzle puzzle;
    NSMutableDictionary *profile = self.profile;
    uint16_t number = (uint16_t)[profile[@"puzzle"] unsignedIntValue];
    if (sherlock_generate(number, &puzzle) != 0) {
        SHMessage(@"The puzzle could not be loaded",
                  [NSString stringWithUTF8String:sherlock_core_error()]);
        return;
    }
    uint32_t limit = [profile[@"countDown"] boolValue]
                    ? [profile[@"limit"] unsignedIntValue] : 0;
    self.tournamentActive = NO;
    [self beginPuzzle:&puzzle profile:profile limit:limit];
}

- (void)newRandomPuzzle:(id)sender {
    (void)sender;
    if (_generatingRandom) return;
    if (self.tournamentActive) {
        SHMessage(@"Tournament in progress", @"Finish this tournament before starting a random puzzle.");
        return;
    }
    uint64_t seed;
    arc4random_buf(&seed, sizeof seed);
    NSMutableDictionary *profile = self.profile;
    uint32_t limit = [profile[@"countDown"] boolValue]
                    ? [profile[@"limit"] unsignedIntValue] : 0;
    BOOL wasPaused = _game.paused;
    if (self.hasGame) sh_set_paused(&_game, 1);
    _generatingRandom = YES;
    NSPanel *progress = [[NSPanel alloc] initWithContentRect:NSMakeRect(0, 0, 390, 100)
        styleMask:NSWindowStyleMaskTitled backing:NSBackingStoreBuffered defer:NO];
    progress.title = @"Generating a unique puzzle";
    NSTextField *label = [NSTextField labelWithString:@"The solver is checking that only one answer is valid."];
    label.frame = NSMakeRect(20, 55, 350, 24);
    [progress.contentView addSubview:label];
    NSProgressIndicator *indicator = [[NSProgressIndicator alloc] initWithFrame:NSMakeRect(20, 25, 350, 16)];
    indicator.indeterminate = YES;
    [progress.contentView addSubview:indicator];
    [indicator startAnimation:nil];
    [self.window beginSheet:progress completionHandler:nil];
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        SherlockPuzzle puzzle = {0};
        SherlockGenerateResult result = {0};
        SherlockGenerateStatus status = sherlock_generate_random(seed, NULL, &puzzle, &result);
        dispatch_async(dispatch_get_main_queue(), ^{
            [self.window endSheet:progress];
            [progress orderOut:nil];
            self->_generatingRandom = NO;
            if (status == SH_GENERATE_OK &&
                [self beginPuzzle:&puzzle profile:profile limit:limit]) {
                self->_randomGame = YES;
                self->_randomSeed = seed;
                self->_randomProfileNumber = (uint16_t)[profile[@"puzzle"] unsignedIntValue];
                self.tournamentMode = NO;
                self.tournamentActive = NO;
                self.window.title = [@"Sherlock Native — " stringByAppendingString:self.puzzleIdentity];
            } else {
                if (self.hasGame) sh_set_paused(&self->_game, wasPaused);
                if (status != SH_GENERATE_OK)
                    SHMessage(@"A unique puzzle was not certified",
                              [NSString stringWithUTF8String:result.reason]);
            }
            self->_lastTick = NSProcessInfo.processInfo.systemUptime;
            [self changed];
        });
    });
}

- (void)copyPuzzleIdentity:(id)sender {
    (void)sender;
    if (!self.hasGame) return;
    char buffer[192];
    if (sh_cli_format_challenge_id(&_game.puzzle, _randomGame, _randomSeed,
                                   buffer, sizeof buffer) != 0) return;
    NSPasteboard *pasteboard = NSPasteboard.generalPasteboard;
    [pasteboard clearContents];
    [pasteboard setString:[NSString stringWithUTF8String:buffer]
                 forType:NSPasteboardTypeString];
}

- (BOOL)validateMenuItem:(NSMenuItem *)item {
    if (_generatingRandom) return item.action == @selector(terminate:);
    if (self.awaitingWinAcknowledgement || self.celebrating)
        return item.action == @selector(copyPuzzleIdentity:) || item.action == @selector(terminate:);
    if (self.hasGame && _game.hint_pending)
        return item.action == @selector(copyPuzzleIdentity:) || item.action == @selector(terminate:);
    BOOL playing = self.hasGame && self.showingGame && _game.outcome == SH_PLAYING;
    BOOL editable = playing && !_game.paused && !_game.hint_pending && !NSApp.modalWindow;
    if (item.action == @selector(undoMove:)) return editable && _game.undo_count > 0;
    if (item.action == @selector(requestHint:)) return editable;
    if (item.action == @selector(togglePause:)) {
        item.title = playing && _game.paused ? @"Resume Puzzle" : @"Pause";
        return playing && !_game.hint_pending && !NSApp.modalWindow;
    }
    if (item.action == @selector(toggleClueBank:)) {
        item.title = self.visibleBank ? @"Show Game Clues" : @"Show Other Clues";
        return editable;
    }
    if (item.action == @selector(returnToMenu:)) {
        item.title = self.tournamentActive ? @"Quit Tournament Turn" : @"Return to Main Menu";
        return playing && !_game.hint_pending && !NSApp.modalWindow;
    }
    if (item.action == @selector(copyPuzzleIdentity:)) return self.hasGame;
    if (item.action == @selector(newRandomPuzzle:)) return !self.tournamentActive;
    return YES;
}

- (void)startTournament {
    if (_generatingRandom) return;
    if (!self.participants.count) {
        SHMessage(@"Select tournament players", @"Choose one or more participants in the PLAYER menu.");
        return;
    }
    if (sherlock_generate(self.pendingTournamentNumber, &_tournamentPuzzle) != 0) {
        SHMessage(@"The tournament puzzle could not be loaded",
                  [NSString stringWithUTF8String:sherlock_core_error()]);
        return;
    }
    _tournamentRows = [NSMutableArray array];
    [self.participants enumerateIndexesUsingBlock:^(NSUInteger index, BOOL *stop) {
        (void)stop;
        if (index < self.profiles.count)
            [self->_tournamentRows addObject:[@{
                @"profile":self.profiles[index], @"state":@"WAITING",
                @"outcome":@(SH_PLAYING), @"elapsed":@0
            } mutableCopy]];
    }];
    if (!_tournamentRows.count) return;
    _tournamentTurn = 0;
    _tournamentLimit = [self.profile[@"countDown"] boolValue]
                      ? [self.profile[@"limit"] unsignedIntValue] : 0;
    self.tournamentActive = YES;
    [self advanceTournament];
}

- (NSString *)standingsText:(NSArray<NSDictionary *> *)rows {
    NSMutableString *text = [NSMutableString stringWithFormat:@"Puzzle %u\n\n", _tournamentPuzzle.number];
    for (NSDictionary *row in rows) {
        NSDictionary *profile = row[@"profile"];
        [text appendFormat:@"%@ — %@%@\n", profile[@"name"], row[@"state"],
            [row[@"outcome"] intValue] == SH_PLAYING ? @"" :
            [@" — " stringByAppendingString:SHTime([row[@"elapsed"] unsignedLongLongValue])]];
    }
    return text;
}

- (void)advanceTournament {
    [self.gameView dismissClueExplanation];
    self.hasGame = NO;
    self.showingGame = NO; /* Do not reveal the puzzle between participants. */
    self.gameView.needsDisplay = YES;
    [self.gameView displayIfNeeded];
    if (_tournamentTurn >= _tournamentRows.count) {
        NSArray *ordered = [_tournamentRows sortedArrayUsingComparator:
            ^NSComparisonResult(NSDictionary *a, NSDictionary *b) {
                int oa = [a[@"outcome"] intValue], ob = [b[@"outcome"] intValue];
                int ra = oa == SH_WON ? 0 : oa == SH_WRONG ? 1 : oa == SH_TIMED_OUT ? 2 : 3;
                int rb = ob == SH_WON ? 0 : ob == SH_WRONG ? 1 : ob == SH_TIMED_OUT ? 2 : 3;
                if (ra != rb) return ra < rb ? NSOrderedAscending : NSOrderedDescending;
                return [a[@"elapsed"] compare:b[@"elapsed"]];
            }];
        self.tournamentActive = NO;
        SHMessage(@"Tournament standings", [self standingsText:ordered]);
        self.pendingTournamentNumber = (uint16_t)arc4random_uniform(65536);
        [self changed];
        return;
    }
    NSMutableDictionary *row = _tournamentRows[_tournamentTurn];
    NSMutableDictionary *profile = row[@"profile"];
    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = @"Tournament standings";
    alert.informativeText = [[self standingsText:_tournamentRows]
        stringByAppendingFormat:@"\nNext player: %@", profile[@"name"]];
    [alert addButtonWithTitle:[@"Start " stringByAppendingString:profile[@"name"]]];
    [alert runModal];
    [self beginPuzzle:&_tournamentPuzzle profile:profile limit:_tournamentLimit];
    if (!self.hasGame) {
        row[@"state"] = @"Could not load images";
        row[@"outcome"] = @(SH_QUIT);
        ++_tournamentTurn;
        [self advanceTournament];
    }
}

- (void)finishIfNeeded {
    if (!self.hasGame || _reportedOutcome || _game.outcome == SH_PLAYING) return;
    /* The clock may expire inside a native help/error dialog. Defer the next
     * outcome/participant dialog until that modal loop returns. */
    if (NSApp.modalWindow) return;
    _reportedOutcome = YES;
    NSString *result = _game.outcome == SH_WON ? @"Correct" :
                       _game.outcome == SH_WRONG ? @"Incorrect" :
                       _game.outcome == SH_TIMED_OUT ? @"Time out" : @"Quit";
    SHPlaySound(_game.outcome == SH_WON ? @"choose" : @"error",
                [self.activeAppearance[@"sound"] boolValue]);
    if (self.tournamentActive) {
        NSMutableDictionary *row = _tournamentRows[_tournamentTurn];
        row[@"state"] = result;
        row[@"outcome"] = @(_game.outcome);
        row[@"elapsed"] = @(_game.elapsed_ms);
        ++_tournamentTurn;
        [self advanceTournament];
        return;
    }
    if (_game.outcome == SH_WON && !_randomGame)
        _activeProfile[@"puzzle"] = @((uint16_t)(_game.puzzle.number + 1));
    [self saveProfiles];
    [self.gameView dismissClueExplanation];
    if (_game.outcome == SH_WON) {
        self.awaitingWinAcknowledgement = YES;
        self.gameView.needsDisplay = YES;
        return;
    }
    SHMessage(_game.outcome == SH_WON ? @"You solved the puzzle!" : result,
              [NSString stringWithFormat:@"%@\nTime: %@", self.puzzleIdentity,
                SHTime(_game.elapsed_ms)]);
    self.hasGame = NO; self.showingGame = NO;
    [self changed];
}

- (void)acknowledgeWin {
    if (self.celebrating) { [self.gameView skipVictory]; return; }
    if (!self.awaitingWinAcknowledgement) return;
    self.awaitingWinAcknowledgement = NO;
    /* The original's post-generation RNG state is outside the recovered puzzle
     * table. Use a stable native starting state; keep this adapter explicit. */
    uint32_t state = _randomGame ? (uint32_t)(_randomSeed ^ (_randomSeed >> 32))
                                : (uint32_t)_game.puzzle.number;
    self.celebrating = [self.gameView beginVictoryWithRandomState:state];
    if (!self.celebrating) { self.hasGame = NO; self.showingGame = NO; }
    [self changed];
}

- (void)changed {
    self.gameView.needsDisplay = YES;
    [self finishIfNeeded];
}

- (void)menuAction:(NSUInteger)action {
    if (_generatingRandom || self.awaitingWinAcknowledgement || self.celebrating) return;
    switch (action) {
        case 0:
            if (self.tournamentActive) break;
            if (self.hasGame && self.showingGame) break;
            if ([self canResume]) {
                if (![self loadImagesForGame:self.profile puzzle:&_game.puzzle]) break;
                self.showingGame = YES; sh_set_paused(&_game, 0);
                _lastTick = NSProcessInfo.processInfo.systemUptime;
            } else if (self.tournamentMode) [self startTournament];
            else [self startSingleGame];
            break;
        case 1:
            if ([self canResume]) {
                if (![self loadImagesForGame:self.profile puzzle:&_game.puzzle]) break;
                sh_game_init(&_game, &_game.puzzle, _initialTimeLimit);
                [self.gameView prepareForNewPuzzle];
                self.visibleBank = 0; self.showingGame = YES; _reportedOutcome = NO;
                _lastTick = NSProcessInfo.processInfo.systemUptime;
                _fractionalMilliseconds = 0;
            }
            break;
        case 2: [self choosePuzzle]; break;
        case 3: [self players:nil]; break;
        case 4: [self chooseTime]; break;
        case 5: if (SHShowColorEditor(self.profile)) [self saveProfiles]; break;
        case 6: if (SHShowPatternEditor(self.profile)) [self saveProfiles]; break;
        case 7: [self images:nil]; break;
        case 8: {
            BOOL value = ![self.profile[@"sound"] boolValue];
            self.profile[@"sound"] = @(value);
            if (self.hasGame) {
                NSMutableDictionary *appearance = [self.activeAppearance mutableCopy];
                appearance[@"sound"] = @(value); self.activeAppearance = appearance;
            }
            if (!value) SHPlaySound(nil, NO);
            [self saveProfiles]; break;
        }
        case 10: [self help:nil]; break;
        case 11: [NSApp terminate:nil]; break;
        default: break;
    }
    [self changed];
}

- (void)gameAction:(NSUInteger)action {
    if (!self.hasGame || !self.showingGame || _game.outcome != SH_PLAYING ||
        _generatingRandom || _game.hint_pending) return;
    if (_game.paused && action != 0 && action != 4) return;
    [self.gameView dismissClueExplanation];
    switch (action) {
        case 0:
            if (self.tournamentActive) sh_quit(&_game);
            else { sh_set_paused(&_game, 1); self.showingGame = NO; }
            break;
        case 1: self.visibleBank = 1 - self.visibleBank; break;
        case 2:
            if (!sh_undo(&_game)) {
                SHPlaySound(@"error", [self.activeAppearance[@"sound"] boolValue]);
                SHMessage(@"Out of UNDOs", @"There are no earlier actions in the 25-action history.");
            }
            break;
        case 3:
            if (sh_request_hint_in_bank(&_game, (unsigned)self.visibleBank, 20000) == 1 &&
                _game.hint_pending) {
                if (![self.gameView prepareHintExplanation]) {
                    /* The selected target stays fixed during proof. An
                     * inconsistent or unresolved premise set offers no move
                     * and has not incurred an acknowledgement penalty. */
                    _game.hint_pending = 0;
                    SHMessage(@"Hint", [self.gameView hintExplanationFailure]);
                    break;
                }
                unsigned bank;
                if (_game.pending_hint.clue_index >= 0 &&
                    sh_clue_location(&_game, (unsigned)_game.pending_hint.clue_index,
                                     &bank, NULL, NULL)) self.visibleBank = bank;
            } else if (_game.outcome == SH_PLAYING) {
                SHMessage(@"Hint", [NSString stringWithUTF8String:_game.pending_hint.explanation]);
            }
            break;
        case 4:
            sh_set_paused(&_game, !_game.paused);
            _lastTick = NSProcessInfo.processInfo.systemUptime;
            _fractionalMilliseconds = 0;
            break;
        default: break;
    }
    [self changed];
}

- (void)choosePuzzle {
    uint16_t current = self.tournamentMode ? self.pendingTournamentNumber :
                       (uint16_t)[self.profile[@"puzzle"] unsignedIntValue];
    NSString *answer = SHAsk(@"Puzzle number", @"Choose the number for the next puzzle (0–65535).",
                             [NSString stringWithFormat:@"%u", current]);
    if (!answer) return;
    NSScanner *scanner = [NSScanner scannerWithString:answer];
    NSInteger value;
    if (![scanner scanInteger:&value] || !scanner.isAtEnd || value < 0 || value > 65535) {
        SHMessage(@"Puzzle unchanged", @"Enter a whole number from 0 to 65535."); return;
    }
    if (self.tournamentMode) self.pendingTournamentNumber = (uint16_t)value;
    else self.profile[@"puzzle"] = @(value);
    [self saveProfiles];
}

- (void)chooseTime {
    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = @"Time";
    alert.informativeText = @"Choose no limit or enter a countdown in HH:MM:SS. This applies to the next puzzle.";
    NSView *controls = [[NSView alloc] initWithFrame:NSMakeRect(0, 0, 360, 70)];
    NSPopUpButton *mode = [[SHActionPopUp alloc] initWithFrame:NSMakeRect(0, 39, 210, 28) pullsDown:NO];
    [mode addItemsWithTitles:@[@"No limit — count upward", @"Count down"]];
    [mode selectItemAtIndex:[self.profile[@"countDown"] boolValue] ? 1 : 0];
    NSTextField *time = [[NSTextField alloc] initWithFrame:NSMakeRect(0, 3, 210, 26)];
    time.stringValue = SHTime([self.profile[@"limit"] unsignedLongLongValue] * 1000);
    [controls addSubview:mode]; [controls addSubview:time];
    alert.accessoryView = controls;
    [alert addButtonWithTitle:@"Done"]; [alert addButtonWithTitle:@"Cancel"];
    if ([alert runModal] != NSAlertFirstButtonReturn) return;
    if (mode.indexOfSelectedItem == 0) self.profile[@"countDown"] = @NO;
    else {
        NSArray<NSString *> *parts = [time.stringValue componentsSeparatedByString:@":"];
        NSCharacterSet *nonDigits = [NSCharacterSet characterSetWithCharactersInString:@"0123456789"].invertedSet;
        BOOL valid = parts.count == 3;
        for (NSString *part in parts)
            if (part.length != 2 || [part rangeOfCharacterFromSet:nonDigits].location != NSNotFound)
                valid = NO;
        NSInteger hours = parts.count == 3 ? parts[0].integerValue : 0;
        NSInteger minutes = parts.count == 3 ? parts[1].integerValue : 0;
        NSInteger seconds = parts.count == 3 ? parts[2].integerValue : 0;
        NSInteger limit = hours * 3600 + minutes * 60 + seconds;
        if (!valid || minutes >= 60 || seconds >= 60 || limit <= 0) {
            SHMessage(@"Time unchanged", @"Use HH:MM:SS with hours 00–99, minutes/seconds 00–59 and a nonzero total."); return;
        }
        self.profile[@"countDown"] = @YES; self.profile[@"limit"] = @(limit);
    }
    [self saveProfiles];
}

- (void)players:(id)sender {
    (void)sender;
    [self.gameView dismissClueExplanation];
    if (self.tournamentActive) {
        SHMessage(@"Tournament in progress", @"Finish the current tournament before changing its participant list."); return;
    }
    if (self.showingGame) { sh_set_paused(&_game, 1); self.showingGame = NO; }
    uint8_t currentImages[46][32][32];
    NSData *workingImages = SHLoadProfileImages(self.profile, self.defaultImagePath, currentImages) ?
        [NSData dataWithBytes:currentImages length:sizeof currentImages] : nil;
    for (;;) {
        NSAlert *alert = [[NSAlert alloc] init];
        alert.messageText = @"Players";
        alert.informativeText = @"Single: choose the current player. Tournament: tick every participant. Each player retains separate preferences and puzzle progress.";
        NSView *content = [[NSView alloc] initWithFrame:NSMakeRect(0, 0, 420, 300)];
        NSPopUpButton *mode = [[SHActionPopUp alloc] initWithFrame:NSMakeRect(0, 265, 200, 28) pullsDown:NO];
        [mode addItemsWithTitles:@[@"SINGLE", @"TOURNEY"]];
        [mode selectItemAtIndex:self.tournamentMode ? 1 : 0];
        mode.tag = mode.indexOfSelectedItem;
        mode.target = self; mode.action = @selector(modeSelected:);
        NSPopUpButton *current = [[SHActionPopUp alloc] initWithFrame:NSMakeRect(210, 265, 210, 28) pullsDown:NO];
        /* Add menu items directly so duplicate display names remain distinct
         * profiles and retain the array's exact index ordering. */
        [current removeAllItems];
        if (!current.menu) current.menu = [[NSMenu alloc] initWithTitle:@"Players"];
        for (NSDictionary *profile in self.profiles) {
            NSMenuItem *item = [[NSMenuItem alloc] initWithTitle:profile[@"name"]
                                              action:@selector(selectItem:) keyEquivalent:@""];
            item.target = current;
            [current.menu addItem:item];
        }
        [current selectItemAtIndex:self.selectedProfile];
        [content addSubview:mode]; [content addSubview:current];
        NSScrollView *scroll = [[NSScrollView alloc] initWithFrame:NSMakeRect(0, 0, 420, 255)];
        scroll.hasVerticalScroller = YES;
        NSView *list = [[NSView alloc] initWithFrame:NSMakeRect(0, 0, 400, MAX(250, self.profiles.count * 27))];
        NSMutableArray<NSButton *> *checks = [NSMutableArray array];
        for (NSUInteger i = 0; i < self.profiles.count; ++i) {
            NSButton *check = [[SHActionButton alloc] initWithFrame:
                NSMakeRect(5, list.frame.size.height - (i + 1) * 27, 385, 24)];
            [check setButtonType:NSButtonTypeSwitch];
            check.title = self.profiles[i][@"name"];
            check.state = [self.participants containsIndex:i] ? NSControlStateValueOn : NSControlStateValueOff;
            [checks addObject:check]; [list addSubview:check];
        }
        scroll.documentView = list; [content addSubview:scroll];
        alert.accessoryView = content;
        for (NSString *title in @[@"Done", @"New", @"Rename", @"Remove"])
            [alert addButtonWithTitle:title];
        NSModalResponse answer = [alert runModal];
        BOOL wasTournament = self.tournamentMode;
        self.tournamentMode = mode.indexOfSelectedItem == 1;
        self.selectedProfile = current.indexOfSelectedItem;
        [self.participants removeAllIndexes];
        for (NSUInteger i = 0; i < checks.count; ++i)
            if (checks[i].state == NSControlStateValueOn) [self.participants addIndex:i];
        if (self.tournamentMode && !wasTournament)
            self.pendingTournamentNumber = (uint16_t)arc4random_uniform(65536);
        if (answer == NSAlertFirstButtonReturn) break;
        if (answer == NSAlertSecondButtonReturn) {
            NSString *name = SHAsk(@"New player", @"Enter a player name.", @"Player");
            if (name.length) {
                NSMutableDictionary *created = SHNewProfile(name);
                /* The observed NEW operation keeps the current working
                 * pattern/images, starts at number 0 with no limit/sound off,
                 * leaves its image filename empty, and does not select it. */
                created[@"pattern"] = [self.profile[@"pattern"] copy];
                if (workingImages) created[@"images"] = workingImages;
                [self.profiles addObject:created];
            }
        } else if (answer == NSAlertThirdButtonReturn) {
            NSString *name = SHAsk(@"Rename player", @"Puzzle progress and preferences remain with this player.", self.profile[@"name"]);
            if (name.length) self.profile[@"name"] = name;
        } else {
            if (self.profiles.count <= 1) {
                SHMessage(@"Keep one player", @"Create another player before removing the last one.");
            } else {
                NSAlert *confirm = [[NSAlert alloc] init];
                confirm.messageText = [@"Remove " stringByAppendingString:self.profile[@"name"]];
                confirm.informativeText = @"This removes that player's saved preferences and puzzle progress.";
                [confirm addButtonWithTitle:@"Remove"]; [confirm addButtonWithTitle:@"Cancel"];
                if ([confirm runModal] == NSAlertFirstButtonReturn) {
                    [self.profiles removeObjectAtIndex:(NSUInteger)self.selectedProfile];
                    self.selectedProfile = 0;
                    [self.participants removeAllIndexes]; [self.participants addIndex:0];
                }
            }
        }
    }
    /* Players Done reloads the selected file even without changing players.
     * Empty filenames keep working artwork. Migrated artwork remains protected
     * until the owner accepts explicit Load/Save/Defaults. */
    NSString *imagePath = self.profile[@"imagePath"];
    if (!self.profile[@"legacyImages"]) {
        if (workingImages) self.profile[@"images"] = workingImages;
        if (imagePath.length) {
            uint8_t reloaded[46][32][32];
            if (shi_load(imagePath.fileSystemRepresentation, reloaded) == 0)
                self.profile[@"images"] = [NSData dataWithBytes:reloaded length:sizeof reloaded];
            else
                SHMessage(@"The selected image file could not be reloaded",
                          @"The current working images have been retained. Use Images > Load to choose a valid SHI file.");
        }
    }
    [self saveProfiles]; [self changed];
}

- (void)modeSelected:(NSPopUpButton *)mode {
    if (mode.indexOfSelectedItem == mode.tag)
        SHPlaySound(@"error", [self.profile[@"sound"] boolValue]);
    mode.tag = mode.indexOfSelectedItem;
}

- (void)images:(id)sender {
    (void)sender;
    [self.gameView dismissClueExplanation];
    if (self.tournamentActive) {
        SHMessage(@"Tournament in progress", @"Change image sets between tournaments."); return;
    }
    if (self.showingGame) { sh_set_paused(&_game, 1); self.showingGame = NO; }
    if (SHShowImageEditor(self.profile, self.defaultImagePath, self.factoryImagePath))
        [self saveProfiles];
    [self changed];
}

- (void)help:(id)sender {
    (void)sender;
    [self.gameView dismissClueExplanation];
    if (self.showingGame && !self.tournamentActive) {
        sh_set_paused(&_game, 1); self.showingGame = NO;
    }
    NSString *instructions =
    @"GOAL\nLocate all 36 items. Each row contains each of its six items once. Small pictures are possibilities. Large pictures are chosen positions. Initial large givens cannot be changed.\n\n"
     "BOARD\nLeft-click a possibility to choose it. Right-click to remove it. A final remaining small possibility still needs a left click. Mistakes are checked only when the board is fully chosen. Right-drag an item from a clue or the board to restore a missing possibility in that item's row. UNDO reverses up to 25 actions; it does not refund time.\n\n"
     "CLUES\nLeft-click a clue to explain its relationship using your current pictures. Click again or press Escape to close the explanation. The clock keeps running and no hint penalty is charged. Vertical pairs mean same column; a red prohibition mark means different columns. A single reference picture is an item appearing in no clue.\n\n"
     "Horizontal A–B–A means neighboring columns in either order. A prohibition mark over B means they are not neighbors. A…B means A is somewhere left of B.\n\n"
     "A↔B↔C means B is between A and C with both immediately adjacent; the order of A and C may be reversed. With B crossed out, A and C are still exactly two columns apart, but B is not in their intervening column.\n\n"
     "ORGANIZE\nDrag clues within their horizontal or vertical area. Right-click a clue to put it in the other bin. OTHER CLUES / GAME CLUES switches bins.\n\n"
     "HINT AND TIME\nHINT shows a verified logical deduction using your current candidate marks as assumptions. Show why displays its supporting clues and row rules without applying the move. In the summary, click outside Show why to apply; in the details, use Apply hint. Acceptance costs 30 seconds. Elapsed time still counts while the hint is open; its clock display and timeout wait until acknowledgment. Click the time display to pause, and click again to continue. Without a limit the timer counts upward; with a limit it counts down. The Game menu also provides Undo (Command-Z), Hint (Command-Shift-H), Pause/Resume (Command-P), and the clue-bin switch (Command-B).\n\n"
     "PLAYERS AND TOURNAMENTS\nEach player has a puzzle number, image set, colors, pattern, time and sound preferences. A tournament gives every participant the same puzzle, hides it between turns and ranks the results. In a tournament QUIT ends your turn.\n\n"
     "RANDOM PUZZLES\nGame > New Random Puzzle creates a new puzzle with exactly one valid answer. Its seed and version appear in the window title; Game > Copy Puzzle Identity copies the identifier used by the JSON CLI. Solving it does not advance your numbered puzzle progress.\n\n"
     "IMAGES\nThe image editor can copy tiles, paint pixels, draw lines, replace colors, flip, shift and clear. It imports/exports the original .SHI format and merges a row or just the empty image. Pixel-editor INIT restores that editor's entry image; the overview's Defaults restores the supplied default set.\n\n"
     "Done keeps working images for this session. Use Save to write a .SHI file, then Done to remember that file for this player. Players > Done reloads the selected SHI file, even if the player stays the same. Save edits before that reload or before quitting. Abort restores the overview's entry images and filename; it cannot undo a completed file Save. Artwork retained by an earlier native version remains available until you accept a replacement set or explicitly save it.\n\n"
     "FINISH\nA correct board stays visible with Elementary, Watson! Click or press a key to start the tile celebration. Click or press a key again to skip after the current burst.\n\n"
     "RESUME\nMENU preserves the current game within this session. Selecting a different puzzle number changes RESUME to PLAY; selecting the active number again restores RESUME and RESTART. RESTART begins that puzzle again. Edited images and SOUND also update the resumed game. Other setting changes apply to future puzzles. Profiles and selected SHI filenames persist when the app exits; working image edits and in-progress boards are not saved across application restarts.";
    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = @"Sherlock help";
    NSScrollView *scroll = [[NSScrollView alloc] initWithFrame:NSMakeRect(0, 0, 550, 420)];
    scroll.hasVerticalScroller = YES;
    NSTextView *text = [[NSTextView alloc] initWithFrame:NSMakeRect(0, 0, 530, 1400)];
    text.editable = NO; text.string = instructions;
    text.font = [NSFont systemFontOfSize:13];
    text.textContainerInset = NSMakeSize(12, 12);
    text.verticallyResizable = YES;
    text.textContainer.widthTracksTextView = YES;
    scroll.documentView = text; alert.accessoryView = scroll;
    [alert addButtonWithTitle:@"Done"];
    [alert addButtonWithTitle:@"Original manual…"];
    if ([alert runModal] == NSAlertSecondButtonReturn) [self originalManual:nil];
    [self changed];
}

- (void)originalManual:(id)sender {
    (void)sender;
    [self.gameView dismissClueExplanation];
    if (self.showingGame && !self.tournamentActive) {
        sh_set_paused(&_game, 1); self.showingGame = NO; [self changed];
    }
    NSString *path = [NSBundle.mainBundle.resourcePath
                      stringByAppendingPathComponent:@"Manual-Sherlock-1.50.txt"];
    if (![NSFileManager.defaultManager fileExistsAtPath:path] ||
        ![NSWorkspace.sharedWorkspace openURL:[NSURL fileURLWithPath:path]])
        SHMessage(@"Manual could not be opened", @"The supplied Manual-Sherlock-1.50.txt resource could not be opened by the default text application.");
}

- (void)play:(id)sender { (void)sender; [self menuAction:0]; }
- (void)undoMove:(id)sender { (void)sender; [self gameAction:2]; }
- (void)requestHint:(id)sender { (void)sender; [self gameAction:3]; }
- (void)togglePause:(id)sender { (void)sender; [self gameAction:4]; }
- (void)toggleClueBank:(id)sender { (void)sender; [self gameAction:1]; }
- (void)returnToMenu:(id)sender { (void)sender; [self gameAction:0]; }
- (void)about:(id)sender {
    (void)sender;
    SHMessage(@"Sherlock Native", @"A native macOS reconstruction of Everett Kaser's Sherlock 1.50. The game uses your supplied original SHI images and a recovered table of numbered puzzles. Native window, settings, editor and file-dialog presentation is adapted for macOS.");
}

- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender {
    (void)sender; return YES;
}
- (NSApplicationTerminateReply)applicationShouldTerminate:(NSApplication *)sender {
    (void)sender;
    [self saveProfiles]; [_timer invalidate]; return NSTerminateNow;
}
@end

int main(int argc, char *argv[]) {
    @autoreleasepool {
        if (argc > 1 && strcmp(argv[1], "--cli") == 0)
            return sh_cli_main(argc - 1, argv + 1,
                               NSBundle.mainBundle.resourcePath.fileSystemRepresentation);
        NSApplication *application = NSApplication.sharedApplication;
        [application setActivationPolicy:NSApplicationActivationPolicyRegular];
        /* NSApplication's delegate is not a lifetime owner under ARC. */
        static SHApp *delegate;
        delegate = [[SHApp alloc] init];
        application.delegate = delegate;
        [application run];
    }
    return 0;
}
