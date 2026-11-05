#include "../state/sherlock_explain.h"

#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>

static void reject_unchanged(const SherlockPuzzle *puzzle, unsigned clue_index) {
    SHClueExplanation explanation;
    unsigned char before[sizeof explanation];
    memset(&explanation, 0xa5, sizeof explanation);
    memcpy(before, &explanation, sizeof before);
    assert(sh_explain_clue(puzzle, clue_index, &explanation) == -1);
    assert(memcmp(before, &explanation, sizeof before) == 0);
}

static void same_explanation(const SHClueExplanation *a, const SHClueExplanation *b) {
    assert(a->type == b->type && a->arity == b->arity);
    assert(memcmp(a->objects, b->objects, sizeof a->objects) == 0);
    assert(strcmp(a->title, b->title) == 0);
    assert(strcmp(a->rule, b->rule) == 0);
}

int main(void) {
    SherlockPuzzle puzzle, snapshot;
    SHClueExplanation explanation[8], other;
    unsigned type;
    const unsigned expected_arity[] = {2, 2, 2, 2, 2, 3, 3, 1};

    memset(&puzzle, 0, sizeof puzzle);
    puzzle.clue_count = 8;
    for (type = 0; type < 8; ++type)
        puzzle.clues[type] = (SherlockClue){(uint8_t)type, 35, 0, 17};
    memcpy(&snapshot, &puzzle, sizeof puzzle);
    for (type = 0; type < 8; ++type) {
        assert(sh_explain_clue(&puzzle, type, &explanation[type]) == 0);
        assert(explanation[type].type == (SherlockClueType)type);
        assert(explanation[type].arity == expected_arity[type]);
        assert(explanation[type].objects[0] == 35);
        assert(explanation[type].objects[1] == (type == SHERLOCK_UNUSED ? 255 : 0));
        assert(explanation[type].objects[2] == (expected_arity[type] == 3 ? 17 : 255));
        assert(explanation[type].title && explanation[type].title[0]);
        assert(explanation[type].rule && explanation[type].rule[0]);
        /* Keep every description short enough for the bounded inspector. */
        assert(strlen(explanation[type].title) <= 30);
        assert(strlen(explanation[type].rule) <= 180);
    }
    assert(memcmp(&puzzle, &snapshot, sizeof puzzle) == 0);

    /* Regression guard for distinctions that can change a player's reading:
     * next-to is reversible; not-next-to does not mean different columns;
     * left-of is not immediate; between is adjacent in either direction;
     * not-between retains positive outer spacing; reference adds no rule. */
    assert(strstr(explanation[SHERLOCK_NEXT_TO].rule, "Either item") != NULL);
    assert(strstr(explanation[SHERLOCK_NOT_NEXT_TO].rule, "share a column") != NULL);
    assert(strstr(explanation[SHERLOCK_LEFT_OF].rule, "do not have to be neighbors") != NULL);
    assert(strstr(explanation[SHERLOCK_BETWEEN].rule, "next to both") != NULL);
    assert(strstr(explanation[SHERLOCK_BETWEEN].rule, "C-B-A") != NULL);
    assert(strstr(explanation[SHERLOCK_NOT_BETWEEN].rule, "exactly two columns apart") != NULL);
    assert(strstr(explanation[SHERLOCK_NOT_BETWEEN].rule, "either order") != NULL);
    assert(strstr(explanation[SHERLOCK_NOT_BETWEEN].rule, "B is not") != NULL);
    assert(strstr(explanation[SHERLOCK_UNUSED].rule, "no constraint") != NULL);

    /* Descriptions cannot depend on, validate, or expose stored answers or
     * board setup. Even deliberately poisoned non-clue data is immaterial. */
    memset(puzzle.solution, 0xff, sizeof puzzle.solution);
    memset(puzzle.given, 0x7f, sizeof puzzle.given);
    memset(puzzle.original_slot, 0xff, sizeof puzzle.original_slot);
    puzzle.number = UINT16_MAX;
    memcpy(&snapshot, &puzzle, sizeof puzzle);
    for (type = 0; type < 8; ++type) {
        assert(sh_explain_clue(&puzzle, type, &other) == 0);
        same_explanation(&explanation[type], &other);
    }
    assert(memcmp(&puzzle, &snapshot, sizeof puzzle) == 0);

    /* An unused c in a binary clue, and both unused fields in a reference
     * card, are deliberately outside the object-ID range. */
    for (type = 0; type < 8; ++type) {
        if (expected_arity[type] < 3) puzzle.clues[type].c = UINT8_MAX;
        if (type == SHERLOCK_UNUSED) puzzle.clues[type].b = UINT8_MAX;
        assert(sh_explain_clue(&puzzle, type, &other) == 0);
        same_explanation(&explanation[type], &other);
    }

    reject_unchanged(NULL, 0);
    assert(sh_explain_clue(&puzzle, 0, NULL) == -1);
    reject_unchanged(&puzzle, 8);
    reject_unchanged(&puzzle, UINT_MAX);
    puzzle.clue_count = 0; reject_unchanged(&puzzle, 0);
    puzzle.clue_count = SHERLOCK_MAX_CLUES + 1; reject_unchanged(&puzzle, 0);
    puzzle.clue_count = UINT16_MAX; reject_unchanged(&puzzle, 0);

    puzzle.clue_count = SHERLOCK_MAX_CLUES;
    puzzle.clues[SHERLOCK_MAX_CLUES - 1] = (SherlockClue){SHERLOCK_UNUSED, 0, 255, 255};
    assert(sh_explain_clue(&puzzle, SHERLOCK_MAX_CLUES - 1, &other) == 0);
    assert(other.arity == 1 && other.objects[0] == 0);
    reject_unchanged(&puzzle, SHERLOCK_MAX_CLUES);

    puzzle.clue_count = 1;
    puzzle.clues[0] = (SherlockClue){8, 0, 6, 12};
    reject_unchanged(&puzzle, 0);
    puzzle.clues[0].type = UINT8_MAX; reject_unchanged(&puzzle, 0);
    for (type = 0; type < 8; ++type) {
        puzzle.clues[0] = (SherlockClue){(uint8_t)type, 36, 6, 12};
        reject_unchanged(&puzzle, 0);
        puzzle.clues[0].a = 0;
        if (expected_arity[type] >= 2) {
            puzzle.clues[0].b = 36; reject_unchanged(&puzzle, 0);
            puzzle.clues[0].b = 6;
        }
        if (expected_arity[type] == 3) {
            puzzle.clues[0].c = 36; reject_unchanged(&puzzle, 0);
        }
    }
    puts("Clue explanations: all eight types, semantic wording, immutable input, hidden-answer independence, ignored unused fields, malformed/boundary rejection: PASS");
    return 0;
}
