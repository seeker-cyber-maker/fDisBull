#ifndef SHERLOCK_STATE_H
#define SHERLOCK_STATE_H

/* Portable player-facing state. Candidate edits, hints and completed-answer
 * acceptance use the visible board, givens and clue constraints. The stored
 * solution is not consulted by these player-state operations. */
#include <stdint.h>
#include "../core/sherlock_core.h"

#define SH_SIZE 6
#define SH_UNDO_LIMIT 25
#define SH_CLUE_CAPACITY 256
#define SH_VERTICAL_SLOTS 18
#define SH_HORIZONTAL_SLOTS 21

enum SHOutcome {
    SH_PLAYING = 0, SH_WON, SH_WRONG, SH_TIMED_OUT, SH_QUIT
};
enum SHHintKind {
    SH_HINT_NONE = 0, SH_HINT_REMOVE, SH_HINT_CHOOSE,
    SH_HINT_CONTRADICTION, SH_HINT_UNRESOLVED
};

typedef struct SHBoard {
    uint8_t candidates[SH_SIZE][SH_SIZE]; /* Six low bits; zero is legal. */
    int8_t chosen[SH_SIZE][SH_SIZE];      /* -1, or explicitly chosen item. */
    /* [bank: game/other][group: vertical/horizontal][slot]. Empty slots remain
     * empty after archiving: the original does not compact these grids. */
    int16_t clue_slots[2][2][SH_CLUE_CAPACITY];
} SHBoard;

typedef struct SHHint {
    enum SHHintKind kind;
    uint8_t row, column, item;
    int16_t clue_index; /* -1 for a row/column deduction. */
    char explanation[256];
} SHHint;

typedef struct SherlockGame {
    SherlockPuzzle puzzle;
    SHBoard board;
    SHBoard undo[SH_UNDO_LIMIT];
    unsigned undo_count;
    uint8_t fixed[SH_SIZE][SH_SIZE];
    enum SHOutcome outcome;
    uint64_t elapsed_ms;
    uint64_t limit_ms; /* Zero means count upward. */
    int paused;
    int hint_pending;
    SHHint pending_hint;
} SherlockGame;

/* Mutation results: 1 means changed, 0 means a harmless no-op, -1 invalid input.
 * Structural mistakes such as empty candidate cells are allowed, just as in the
 * original. A candidate's true solution position is never an edit guard. */
void sh_game_init(SherlockGame *game, const SherlockPuzzle *puzzle,
                  uint32_t time_limit_seconds);
uint8_t sh_cell_byte(const SherlockGame *game, unsigned row, unsigned column);
int sh_remove(SherlockGame *game, unsigned row, unsigned column, unsigned item);
int sh_restore(SherlockGame *game, unsigned row, unsigned column, unsigned item);
int sh_choose(SherlockGame *game, unsigned row, unsigned column, unsigned item);
int sh_undo(SherlockGame *game);
int sh_clue_group(const SherlockClue *clue);
/* Original slot is authoritative: UNUSED reference cards can be horizontal. */
int sh_puzzle_clue_group(const SherlockPuzzle *puzzle, unsigned clue);
int sh_clue_location(const SherlockGame *game, unsigned clue,
                     unsigned *bank, unsigned *group, unsigned *slot);
int sh_archive_clue(SherlockGame *game, unsigned clue);
int sh_move_clue(SherlockGame *game, unsigned clue, unsigned destination_slot);
void sh_tick(SherlockGame *game, uint64_t milliseconds);
void sh_set_paused(SherlockGame *game, int paused);
uint64_t sh_display_time_ms(const SherlockGame *game);
void sh_quit(SherlockGame *game);

/* Read-only predicate useful for independent acceptance vectors. a/b/c are
 * column numbers; BETWEEN and NOT_BETWEEN use a/c as outer items, b as middle. */
int sh_relation_holds(unsigned type, int a, int b, int c);

/* The hint routine first uses single-cell/single-item deductions, each clue's
 * supported tuples and row Hall sets. If necessary it performs a bounded CSP
 * contradiction search using only clues and current candidates. Unknown is
 * returned explicitly if the shared node budget is exhausted. The hint order
 * and prose are this implementation's logical presentation, not a claim to
 * reproduce the DOS hint engine's exact wording/order. */
int sh_find_hint(const SherlockGame *game, SHHint *hint, unsigned search_budget);
int sh_request_hint(SherlockGame *game, unsigned search_budget);
int sh_accept_hint(SherlockGame *game);

#endif
