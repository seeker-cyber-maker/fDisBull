#import <Cocoa/Cocoa.h>
#include "../state/sherlock_explain.h"

#define SH_CLUE_EXPLANATION_WIDTH 290.0
#define SH_CLUE_EXPLANATION_HEIGHT 230.0

/* Draw a non-modal clue inspector in the game's flipped logical coordinates.
 * The caller owns dismissal, selected-clue highlighting and normal clock
 * updates. fullTiles uses semantic SHI object order; missing thumbnails fall
 * back to the item's stable numeric identity. No game state is changed.
 * Returns NO without drawing for an invalid public clue.
 */
BOOL SHDrawClueExplanation(const SherlockPuzzle *puzzle, unsigned clueIndex,
                           NSArray<NSImage *> *fullTiles, NSPoint origin);
