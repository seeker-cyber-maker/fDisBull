#import <Cocoa/Cocoa.h>
#include "../state/sherlock_state.h"
#include "../media/shi.h"

/* Shared native presentation helpers. Every image is loaded from the owner's
 * SHI resources. No game pixels are embedded in the authored source. */
NSColor *SHColor(NSUInteger index);
NSArray<NSNumber *> *SHDefaultColors(void);
NSArray<NSNumber *> *SHNormalizedColors(id colors);
NSImage *SHImage(const uint8_t pixels[32][32], BOOL halfSize);
NSImage *SHPatternImage(const uint8_t rows[8], NSUInteger fill, NSUInteger mask);
NSData *SHPresetPatterns(void);
NSData *SHDefaultPattern(void);
NSArray<NSImage *> *SHImages(const uint8_t pixels[46][32][32], BOOL halfSize);
NSArray<NSImage *> *SHClueImages(const SherlockPuzzle *puzzle,
                               const uint8_t pixels[46][32][32]);
void SHMessage(NSString *title, NSString *message);
NSString *SHAsk(NSString *title, NSString *message, NSString *initial);
NSButton *SHButton(NSString *title, NSRect frame, id target, SEL action);
NSTextField *SHLabel(NSString *text, NSRect frame);
NSString *SHTime(uint64_t milliseconds);
void SHPlaySound(NSString *name, BOOL enabled);
BOOL SHLoadProfileImages(NSDictionary *profile, NSString *defaultPath,
                         uint8_t pixels[46][32][32]);
BOOL SHShowImageEditor(NSMutableDictionary *profile, NSString *defaultPath,
                        NSString *factoryPath);
BOOL SHShowColorEditor(NSMutableDictionary *profile);
BOOL SHShowPatternEditor(NSMutableDictionary *profile);

/* Custom editors retain the DOS convention that either mouse button operates
 * controls. Standard system alerts/file dialogs retain normal macOS behavior. */
@interface SHActionButton : NSButton
@end
@interface SHActionPopUp : NSPopUpButton
@end

@protocol SHColorChoice <NSObject>
- (void)pickColor:(NSUInteger)index;
@end

@interface SHPaletteView : NSView
@property(nonatomic, weak) id<SHColorChoice> receiver;
@property(nonatomic) NSUInteger currentColor;
@end

@interface SHModalEditor : NSObject <NSWindowDelegate>
@property(nonatomic, strong) NSPanel *panel;
@property(nonatomic) BOOL accepted;
- (instancetype)initWithTitle:(NSString *)title size:(NSSize)size;
- (BOOL)run;
- (void)done:(id)sender;
- (void)abort:(id)sender;
@end

@class SHGameView;

@interface SHApp : NSObject <NSApplicationDelegate, NSWindowDelegate>
@property(nonatomic, strong) NSWindow *window;
@property(nonatomic, strong) SHGameView *gameView;
@property(nonatomic, strong) NSMutableArray<NSMutableDictionary *> *profiles;
@property(nonatomic) NSInteger selectedProfile;
@property(nonatomic) BOOL tournamentMode;
@property(nonatomic) BOOL tournamentActive;
@property(nonatomic, strong) NSMutableIndexSet *participants;
@property(nonatomic) BOOL showingGame;
@property(nonatomic) BOOL hasGame;
@property(nonatomic) NSInteger visibleBank;
@property(nonatomic, strong) NSArray<NSImage *> *fullTiles;
@property(nonatomic, strong) NSArray<NSImage *> *halfTiles;
@property(nonatomic, strong) NSArray<NSImage *> *clueImages;
@property(nonatomic, strong) NSData *tilePixels;
@property(nonatomic) BOOL awaitingWinAcknowledgement;
@property(nonatomic) BOOL celebrating;
@property(nonatomic, strong) NSDictionary *activeAppearance;
@property(nonatomic, copy) NSString *activePlayerName;
@property(nonatomic, copy) NSString *defaultImagePath;
@property(nonatomic, copy) NSString *factoryImagePath;
@property(nonatomic) uint16_t pendingTournamentNumber;
- (SherlockGame *)game;
- (NSString *)puzzleLabel;
- (NSMutableDictionary *)profile;
- (BOOL)canResume;
- (void)menuAction:(NSUInteger)action;
- (void)gameAction:(NSUInteger)action;
- (void)changed;
- (void)sampleGameClock;
- (void)finishIfNeeded;
- (void)acknowledgeWin;
- (void)saveProfiles;
@end

@interface SHGameView : NSView
@property(nonatomic, weak) SHApp *app;
- (void)prepareForNewPuzzle;
- (void)dismissClueExplanation;
- (BOOL)prepareHintExplanation;
- (NSString *)hintExplanationFailure;
- (BOOL)beginVictoryWithRandomState:(uint32_t)randomState;
- (BOOL)advanceVictory;
- (void)skipVictory;
@end
