#ifndef SHERLOCK_HINT_PROOF_H
#define SHERLOCK_HINT_PROOF_H

#include "sherlock_state.h"

#ifdef __cplusplus
extern "C" {
#endif

#define SH_HINT_PROOF_VERSION 1u
#define SH_HINT_RULE_ROWS_ARE_PERMUTATIONS 1u

typedef enum SHHintProofStatus {
    SH_PROOF_INVALID = -1,
    SH_PROOF_UNRESOLVED = 0,
    SH_PROOF_PROVED = 1,
    SH_PROOF_REFUTED = 2,
    SH_PROOF_INCONSISTENT = 3
} SHHintProofStatus;

typedef struct SHHintProofTarget {
    enum SHHintKind kind; /* REMOVE or CHOOSE only. */
    uint8_t row, column, item; /* Zero-based, exactly as selected. */
} SHHintProofTarget;

typedef struct SHHintProofClue {
    uint16_t index; /* Index in the source puzzle, not in the reduced set. */
    SherlockClue clue;
} SHHintProofClue;

/* A replayable supporting-premise record, not a step-by-step proof certificate.
 * All six rows contain each item exactly once. Givens and ALL frozen candidate
 * masks are background premises, not claims that the player's edits were right.
 * Those premises are never reduced. Only active clues are eligible for removal;
 * each retained clue has a unique source index below source_clue_count.
 *
 * Neither the stored solution nor a solver completion is included. chosen,
 * fixed, clue layout, archive state, time, outcome and undo are presentation or
 * interaction state and are not logical premises. selected_clue_index preserves
 * the selector's advisory provenance. The builder tries other clues in source
 * order before this clue, favoring a direct explanation when available; it may
 * still remove the selected clue if redundant. The target records the exact
 * move, not the selector's explanation prose.
 *
 * Replay verifies these stated premises. A caller accepting an external record
 * must also bind its target, masks, givens and indexed clues to the intended
 * challenge/current board; standalone replay does not authenticate their origin.
 */
typedef struct SHHintProof {
    uint32_t version;
    uint32_t background_rules;
    SHHintProofTarget target;
    int16_t selected_clue_index;
    uint8_t candidates[SH_SIZE][SH_SIZE];
    int8_t given[SH_SIZE][SH_SIZE];
    uint16_t source_clue_count;
    uint16_t support_count;
    SHHintProofClue support[SH_CLUE_CAPACITY];
} SHHintProof;

/* Outcome/effort are separate from the premises and cannot certify themselves.
 * PROVED means consistent premises and an impossible contrary move. REFUTED
 * means a completion contradicting the move exists. INCONSISTENT is never a
 * proof by vacuity. INVALID is malformed input; UNRESOLVED is budget exhaustion
 * before consistency or the move was decided.
 *
 * The builder can remain PROVED when reduction runs out of budget. Only PROVED
 * plus reduction_complete establishes deletion-minimal supporting clues,
 * relative to the frozen background and eligible clues. This does not mean
 * minimum cardinality, the easiest explanation, or original DOS fidelity.
 * Replay never checks minimality and always leaves reduction_complete zero.
 */
typedef struct SHHintProofResult {
    SHHintProofStatus status;
    unsigned node_budget;
    unsigned nodes_used;
    unsigned deletion_checks;
    int reduction_complete;
    char reason[192];
} SHHintProofResult;

/* Read-only: no move, clock charge, pending-hint change, or hidden-answer read.
 * The selected target must be REMOVE/CHOOSE, in range, and currently possible.
 * Interaction eligibility (paused, already chosen, etc.) belongs to the caller.
 * All searches share node_budget; zero validates input but cannot establish a
 * logical outcome. The output record is initialized even on failure, but only
 * a PROVED result certifies its support. report may be NULL; record may not.
 */
SHHintProofStatus sh_explain_hint(const SherlockGame *game,
                                 const SHHint *selected,
                                 unsigned node_budget,
                                 SHHintProof *record,
                                 SHHintProofResult *report);

/* Reconstruct the stated constraints and check consistency plus the exact
 * contrary move. No builder outcome or minimality flag is accepted as evidence.
 * The record is unchanged and report may be NULL.
 */
SHHintProofStatus sh_replay_hint_proof(const SHHintProof *record,
                                      unsigned node_budget,
                                      SHHintProofResult *report);

#ifdef __cplusplus
}
#endif

#endif
