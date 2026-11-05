#include "sherlock_explain.h"

#include <string.h>

int sh_explain_clue(const SherlockPuzzle *puzzle, unsigned clue_index,
                    SHClueExplanation *out) {
    const SherlockClue *clue;
    SHClueExplanation description;
    unsigned arity;
    static const char *const titles[] = {
        "Same column",
        "Different columns",
        "Next to each other",
        "Not neighbors",
        "Left of",
        "Between two neighbors",
        "Not in the middle",
        "Reference picture"
    };
    static const char *const rules[] = {
        "A and B belong in the same column.",
        "A and B belong in different columns.",
        "A and B occupy neighboring columns. Either item can be on the left.",
        "A and B are not in neighboring columns. This clue alone allows them to share a column.",
        "A is somewhere to the left of B. They do not have to be neighbors.",
        "B is directly between A and C, next to both. The order can be A-B-C or C-B-A.",
        "A and C are exactly two columns apart, in either order. B is not in the column between them.",
        "A is a reference picture, not a relationship clue. It adds no constraint on A's column."
    };

    if (!puzzle || !out || puzzle->clue_count > SHERLOCK_MAX_CLUES ||
        clue_index >= puzzle->clue_count) return -1;
    clue = &puzzle->clues[clue_index];
    if (clue->type > SHERLOCK_UNUSED) return -1;
    arity = clue->type == SHERLOCK_UNUSED ? 1u :
        (clue->type == SHERLOCK_BETWEEN || clue->type == SHERLOCK_NOT_BETWEEN)
        ? 3u : 2u;
    if (clue->a >= SHERLOCK_ROWS * SHERLOCK_COLUMNS ||
        (arity >= 2 && clue->b >= SHERLOCK_ROWS * SHERLOCK_COLUMNS) ||
        (arity == 3 && clue->c >= SHERLOCK_ROWS * SHERLOCK_COLUMNS)) return -1;

    memset(&description, 0, sizeof description);
    description.type = (SherlockClueType)clue->type;
    description.arity = arity;
    description.objects[0] = clue->a;
    description.objects[1] = arity >= 2 ? clue->b : UINT8_MAX;
    description.objects[2] = arity == 3 ? clue->c : UINT8_MAX;
    description.title = titles[clue->type];
    description.rule = rules[clue->type];
    *out = description;
    return 0;
}
