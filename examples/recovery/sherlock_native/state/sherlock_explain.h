#ifndef SHERLOCK_EXPLAIN_H
#define SHERLOCK_EXPLAIN_H

#include "../core/sherlock_core.h"

#ifdef __cplusplus
extern "C" {
#endif

/* A description of a public clue, not a deduction about the current board.
 * A, B and C refer to objects[0], objects[1] and objects[2]. Object identities
 * are row * 6 + item; the caller supplies the currently selected artwork.
 * title and rule point to immutable static strings and need no deallocation.
 * Unused object entries are 255. A reference card has arity 1 and no relation.
 */
typedef struct SHClueExplanation {
    SherlockClueType type;
    unsigned arity;
    uint8_t objects[3];
    const char *title;
    const char *rule;
} SHClueExplanation;

/* Return 0 on success, -1 for a null argument, invalid index/count, unsupported
 * relation, or out-of-range relevant object. Failure leaves *out unchanged.
 * Only the selected public clue and its container bounds are inspected.
 * Stored answers, givens, display slots and unused b/c fields are not read.
 * There is no board mutation, hint generation, solver call or time penalty.
 */
int sh_explain_clue(const SherlockPuzzle *puzzle, unsigned clue_index,
                    SHClueExplanation *out);

#ifdef __cplusplus
}
#endif
#endif
