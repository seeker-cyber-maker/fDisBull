#include "sherlock_hint_proof.h"

#include <stdio.h>
#include <string.h>

/* UINT16 support counts represent all 256 clues; indices remain 0..255. No
 * full SherlockGame or stored answer is copied into an explanation workspace.
 */
static SHHintProofResult *begin_report(SHHintProofResult *report,
                                        SHHintProofResult *local,
                                        unsigned node_budget) {
    if (!report) report = local;
    memset(report, 0, sizeof *report);
    report->status = SH_PROOF_INVALID;
    report->node_budget = node_budget;
    return report;
}

static SHHintProofStatus finish(SHHintProofResult *report,
                                SHHintProofStatus status,
                                unsigned remaining, const char *reason) {
    report->status = status;
    report->nodes_used = report->node_budget - remaining;
    snprintf(report->reason, sizeof report->reason, "%s", reason);
    return status;
}

static int valid_target(const SHHintProof *record) {
    const SHHintProofTarget *target = &record->target;
    return (target->kind == SH_HINT_REMOVE || target->kind == SH_HINT_CHOOSE) &&
        target->row < SH_SIZE && target->column < SH_SIZE &&
        target->item < SH_SIZE &&
        (record->candidates[target->row][target->column] & (1u << target->item));
}

static void premise_puzzle(const SHHintProof *record, unsigned skip,
                           SherlockPuzzle *puzzle) {
    unsigned i;
    memset(puzzle, 0, sizeof *puzzle);
    memcpy(puzzle->given, record->given, sizeof puzzle->given);
    for (i = 0; i < record->support_count; ++i)
        if (i != skip) puzzle->clues[puzzle->clue_count++] = record->support[i].clue;
}

static void contrary_candidates(const SHHintProof *record,
                                 uint8_t contrary[SH_SIZE][SH_SIZE]) {
    const SHHintProofTarget *target = &record->target;
    uint8_t bit = (uint8_t)(1u << target->item);
    memcpy(contrary, record->candidates, sizeof record->candidates);
    /* REMOVE asserts that this item cannot be here; test it being here.
     * CHOOSE asserts that it must be here; test it being absent. */
    if (target->kind == SH_HINT_REMOVE)
        contrary[target->row][target->column] &= bit;
    else
        contrary[target->row][target->column] &= (uint8_t)~bit;
}

static int valid_record(const SHHintProof *record) {
    SherlockPuzzle puzzle;
    uint8_t seen[SH_CLUE_CAPACITY] = { 0 };
    unsigned i, validation_budget = 0;
    if (!record || record->version != SH_HINT_PROOF_VERSION ||
        record->background_rules != SH_HINT_RULE_ROWS_ARE_PERMUTATIONS ||
        record->source_clue_count > SH_CLUE_CAPACITY ||
        record->support_count > record->source_clue_count ||
        record->selected_clue_index < -1 ||
        record->selected_clue_index >= (int)record->source_clue_count ||
        !valid_target(record)) return 0;
    for (i = 0; i < record->support_count; ++i) {
        const SHHintProofClue *support = &record->support[i];
        if (support->index >= record->source_clue_count ||
            seen[support->index] || support->clue.type >= SHERLOCK_UNUSED)
            return 0;
        seen[support->index] = 1;
    }
    premise_puzzle(record, SH_CLUE_CAPACITY, &puzzle);
    return sh_check_candidates(&puzzle, record->candidates, &validation_budget)
        != SH_CONSTRAINT_INVALID;
}

static SHHintProofStatus decide(const SHHintProof *record, unsigned *remaining,
                                 const char **reason) {
    SherlockPuzzle puzzle;
    uint8_t contrary[SH_SIZE][SH_SIZE];
    enum SHConstraintStatus status;
    premise_puzzle(record, SH_CLUE_CAPACITY, &puzzle);
    status = sh_check_candidates(&puzzle, record->candidates, remaining);
    if (status == SH_CONSTRAINT_INVALID) {
        *reason = "The stated premises are malformed.";
        return SH_PROOF_INVALID;
    }
    if (status == SH_CONSTRAINT_UNKNOWN) {
        *reason = "The node budget ended before premise consistency was established.";
        return SH_PROOF_UNRESOLVED;
    }
    if (status == SH_CONSTRAINT_UNSAT) {
        *reason = "The frozen candidates, givens, clues and row rules have no completion; no move is certified.";
        return SH_PROOF_INCONSISTENT;
    }
    contrary_candidates(record, contrary);
    status = sh_check_candidates(&puzzle,
        (const uint8_t (*)[SH_SIZE])contrary, remaining);
    if (status == SH_CONSTRAINT_INVALID) {
        *reason = "The contrary-move constraints are malformed.";
        return SH_PROOF_INVALID;
    }
    if (status == SH_CONSTRAINT_UNKNOWN) {
        *reason = "The premises are consistent, but the node budget ended before the exact move was decided.";
        return SH_PROOF_UNRESOLVED;
    }
    if (status == SH_CONSTRAINT_SAT) {
        *reason = "A completion satisfies the stated premises and contradicts this move; the move is not forced.";
        return SH_PROOF_REFUTED;
    }
    *reason = "The stated premises are consistent and the exact contrary move has no completion. Minimality was not checked.";
    return SH_PROOF_PROVED;
}

SHHintProofStatus sh_replay_hint_proof(const SHHintProof *record,
                                      unsigned node_budget,
                                      SHHintProofResult *report) {
    SHHintProofResult local;
    SHHintProofStatus status;
    const char *reason;
    unsigned remaining = node_budget;
    report = begin_report(report, &local, node_budget);
    if (!valid_record(record))
        return finish(report, SH_PROOF_INVALID, remaining,
            "The record has invalid version, rules, target, premise bounds, or source clue indices.");
    status = decide(record, &remaining, &reason);
    return finish(report, status, remaining, reason);
}

SHHintProofStatus sh_explain_hint(const SherlockGame *game,
                                 const SHHint *selected,
                                 unsigned node_budget,
                                 SHHintProof *record,
                                 SHHintProofResult *report) {
    SHHintProofResult local;
    SHHintProofStatus status;
    const char *reason;
    unsigned remaining = node_budget, validation_budget = 0, i, pass;
    uint8_t contrary[SH_SIZE][SH_SIZE];
    report = begin_report(report, &local, node_budget);
    if (record) memset(record, 0, sizeof *record);
    if (!game || !selected || !record)
        return finish(report, SH_PROOF_INVALID, remaining,
            "A game, selected hint and output record are required.");
    /* Validation includes inactive reference cards before those nonconstraints
     * are omitted. It consumes no search node and reads no stored solution. */
    if (sh_check_candidates(&game->puzzle, game->board.candidates,
            &validation_budget) == SH_CONSTRAINT_INVALID)
        return finish(report, SH_PROOF_INVALID, remaining,
            "The source puzzle or current candidate masks are malformed.");
    record->version = SH_HINT_PROOF_VERSION;
    record->background_rules = SH_HINT_RULE_ROWS_ARE_PERMUTATIONS;
    record->target.kind = selected->kind;
    record->target.row = selected->row;
    record->target.column = selected->column;
    record->target.item = selected->item;
    record->selected_clue_index = selected->clue_index;
    memcpy(record->candidates, game->board.candidates, sizeof record->candidates);
    memcpy(record->given, game->puzzle.given, sizeof record->given);
    record->source_clue_count = game->puzzle.clue_count;
    for (i = 0; i < game->puzzle.clue_count; ++i) {
        SHHintProofClue *support;
        if (game->puzzle.clues[i].type == SHERLOCK_UNUSED) continue;
        support = &record->support[record->support_count++];
        support->index = (uint16_t)i;
        support->clue = game->puzzle.clues[i];
    }
    if (!valid_record(record))
        return finish(report, SH_PROOF_INVALID, remaining,
            "The selected hint must name a currently possible remove/choose target and a valid source clue index.");
    status = decide(record, &remaining, &reason);
    if (status != SH_PROOF_PROVED) return finish(report, status, remaining, reason);

    contrary_candidates(record, contrary);
    /* Try non-selected clues in source order first, then the selector's own
     * clue. Otherwise a direct one-clue explanation can be discarded in favor
     * of a longer alternative chain. This preference is not an optimization
     * for minimum cardinality; every retained clue still needs a decided test. */
    for (pass = 0; pass < 2; ++pass) {
        i = 0;
        while (i < record->support_count) {
            SherlockPuzzle reduced;
            enum SHConstraintStatus trial;
            int selected_clue = record->support[i].index == record->selected_clue_index;
            if (selected_clue != (pass == 1)) { ++i; continue; }
            if (!remaining) goto reduction_done;
            premise_puzzle(record, i, &reduced);
            ++report->deletion_checks;
            /* Full-premise consistency was already proved. Removing clues
             * cannot invalidate that completion, so test only the contrary. */
            trial = sh_check_candidates(&reduced,
                (const uint8_t (*)[SH_SIZE])contrary, &remaining);
            if (trial == SH_CONSTRAINT_UNKNOWN) goto reduction_done;
            if (trial == SH_CONSTRAINT_INVALID)
                return finish(report, SH_PROOF_INVALID, remaining,
                    "A reduced premise set failed validation.");
            if (trial == SH_CONSTRAINT_UNSAT) {
                --record->support_count;
                memmove(&record->support[i], &record->support[i + 1],
                    (record->support_count - i) * sizeof record->support[0]);
                memset(&record->support[record->support_count], 0,
                    sizeof record->support[0]);
            } else {
                ++i;
            }
        }
    }
    report->reduction_complete = 1;
reduction_done:
    return finish(report, SH_PROOF_PROVED, remaining,
        report->reduction_complete ?
        "Consistent premises prove this exact move. The completed deletion pass gives deletion-minimal clues relative to all frozen candidates, givens and row rules." :
        "Consistent premises prove this exact move. Support reduction exhausted its budget; the retained clues are sufficient, with no minimality claim.");
}
