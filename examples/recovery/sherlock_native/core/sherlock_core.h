#ifndef SHERLOCK_CORE_H
#define SHERLOCK_CORE_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define SHERLOCK_ROWS 6
#define SHERLOCK_COLUMNS 6
#define SHERLOCK_MAX_CLUES 256

typedef enum SherlockClueType {
    SHERLOCK_SAME_COLUMN = 0,
    SHERLOCK_NOT_SAME_COLUMN = 1,
    SHERLOCK_NEXT_TO = 2,
    SHERLOCK_NOT_NEXT_TO = 3,
    SHERLOCK_LEFT_OF = 4,
    SHERLOCK_BETWEEN = 5,
    SHERLOCK_NOT_BETWEEN = 6,
    SHERLOCK_UNUSED = 7
} SherlockClueType;

typedef struct SherlockClue {
    uint8_t type, a, b, c;
} SherlockClue;

typedef struct SherlockPuzzle {
    uint16_t number;
    uint8_t solution[SHERLOCK_ROWS][SHERLOCK_COLUMNS];
    int8_t given[SHERLOCK_ROWS][SHERLOCK_COLUMNS];
    uint16_t clue_count;
    SherlockClue clues[SHERLOCK_MAX_CLUES];
    /* Original DOS display slot: 36..53 vertical, 54..74 horizontal. */
    uint8_t original_slot[SHERLOCK_MAX_CLUES];
} SherlockPuzzle;

/* Load the native semantic table from an application resource. Return 0 on success. */
int sherlock_load_puzzle_table(const char *path);
/* Diagnostic text for the most recent unsuccessful core operation. */
const char *sherlock_core_error(void);
/* Return 0 on success. No approximate or substitute generator is permitted. */
int sherlock_generate(uint16_t seed, SherlockPuzzle *out);
#ifdef __cplusplus
}
#endif
#endif
