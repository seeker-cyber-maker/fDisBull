#import <Cocoa/Cocoa.h>
#include <stdint.h>

/* A transparent native canvas accumulates the original tile trails. The game
 * board remains underneath it; no original program executes in this adapter. */
@interface SHVictoryCanvas : NSObject
- (instancetype)initWithTiles:(NSData *)tiles randomState:(uint32_t)randomState;
- (BOOL)advance;
- (void)requestSkip;
- (void)draw;
@property(nonatomic) BOOL soundEnabled;
@end
