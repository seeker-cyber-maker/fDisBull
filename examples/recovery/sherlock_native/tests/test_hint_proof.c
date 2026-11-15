/* Authored, bounded supporting-premise tests. These do not establish original
 * DOS hint order/wording or native AppKit behavior. The small-fixture oracle
 * enumerates row permutations independently of the production CSP solver. */
#include "../state/sherlock_hint_proof.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct Oracle {
    const SHHintProof *record;
    unsigned skip;
    uint8_t rows[6][720][6];
    unsigned row_count[6];
    uint8_t answer[6][6];
    unsigned completions, contrary;
} Oracle;

static int oracle_relation(const SherlockClue *clue, const uint8_t places[36]) {
    int a = places[clue->a], b = places[clue->b];
    int distance = a > b ? a - b : b - a;
    switch (clue->type) {
        case SHERLOCK_SAME_COLUMN: return a == b;
        case SHERLOCK_NOT_SAME_COLUMN: return a != b;
        case SHERLOCK_NEXT_TO: return distance == 1;
        case SHERLOCK_NOT_NEXT_TO: return distance != 1;
        case SHERLOCK_LEFT_OF: return a < b;
        case SHERLOCK_BETWEEN:
        case SHERLOCK_NOT_BETWEEN: {
            int c = places[clue->c];
            int outer_distance = a > c ? a - c : c - a;
            return outer_distance == 2 &&
                ((a + c == 2 * b) == (clue->type == SHERLOCK_BETWEEN));
        }
        default: assert(0); return 0;
    }
}

static void oracle_rows(Oracle *oracle, unsigned row, unsigned column,
                         unsigned used, uint8_t cells[6]) {
    unsigned item;
    if (column == 6) {
        assert(oracle->row_count[row] < 720);
        memcpy(oracle->rows[row][oracle->row_count[row]++], cells, 6);
        return;
    }
    for (item = 0; item < 6; ++item) {
        int given = oracle->record->given[row][column];
        if ((used & (1u << item)) ||
            !(oracle->record->candidates[row][column] & (1u << item)) ||
            (given >= 0 && given != (int)item)) continue;
        cells[column] = (uint8_t)item;
        oracle_rows(oracle, row, column + 1, used | (1u << item), cells);
    }
}

static void oracle_join(Oracle *oracle, unsigned row) {
    unsigned i, r, c;
    uint8_t places[36];
    if (row < 6) {
        for (i = 0; i < oracle->row_count[row]; ++i) {
            memcpy(oracle->answer[row], oracle->rows[row][i], 6);
            oracle_join(oracle, row + 1);
        }
        return;
    }
    for (r = 0; r < 6; ++r) for (c = 0; c < 6; ++c)
        places[r * 6 + oracle->answer[r][c]] = (uint8_t)c;
    for (i = 0; i < oracle->record->support_count; ++i)
        if (i != oracle->skip &&
            !oracle_relation(&oracle->record->support[i].clue, places)) return;
    ++oracle->completions;
    {
        const SHHintProofTarget *target = &oracle->record->target;
        int present = oracle->answer[target->row][target->column] == target->item;
        if (present == (target->kind == SH_HINT_REMOVE)) ++oracle->contrary;
    }
}

static void oracle_counts(const SHHintProof *record, unsigned skip,
                            unsigned *completions, unsigned *contrary) {
    Oracle oracle;
    uint8_t cells[6];
    unsigned row, combinations = 1;
    memset(&oracle, 0, sizeof oracle);
    oracle.record = record;
    oracle.skip = skip;
    for (row = 0; row < 6; ++row) {
        oracle_rows(&oracle, row, 0, 0, cells);
        combinations *= oracle.row_count[row];
        assert(combinations <= 100000); /* Keep this independent oracle bounded. */
    }
    oracle_join(&oracle, 0);
    *completions = oracle.completions;
    *contrary = oracle.contrary;
}

static void assert_independent_proof(const SHHintProof *record, int minimal) {
    unsigned total, contrary, i;
    oracle_counts(record, SH_CLUE_CAPACITY, &total, &contrary);
    assert(total > 0 && contrary == 0);
    if (minimal) for (i = 0; i < record->support_count; ++i) {
        oracle_counts(record, i, &total, &contrary);
        assert(total > 0 && contrary > 0);
    }
}

static SherlockPuzzle puzzle(void) {
    SherlockPuzzle result;
    memset(&result, 0, sizeof result);
    memset(result.given, -1, sizeof result.given);
    memset(result.solution, 255, sizeof result.solution);
    return result;
}

static void small_game(SherlockGame *game) {
    SherlockPuzzle p = puzzle();
    unsigned row, column;
    sh_game_init(game, &p, 0);
    for (row = 0; row < 6; ++row) for (column = 0; column < 6; ++column)
        game->board.candidates[row][column] = (uint8_t)(1u << column);
}

static void combined_game(SherlockGame *game) {
    unsigned row, column;
    small_game(game);
    for (row = 0; row < 2; ++row) for (column = 0; column < 3; ++column)
        game->board.candidates[row][column] = 7;
    game->puzzle.clue_count = 4;
    game->puzzle.clues[0] = (SherlockClue){ SHERLOCK_LEFT_OF, 0, 6, 255 };
    game->puzzle.clues[1] = (SherlockClue){ SHERLOCK_SAME_COLUMN, 6, 13, 255 };
    game->puzzle.clues[2] = (SherlockClue){ SHERLOCK_LEFT_OF, 18, 29, 255 };
    game->puzzle.clues[3] = (SherlockClue){ SHERLOCK_UNUSED, 35, 255, 255 };
}

static SHHint hint(enum SHHintKind kind, unsigned row, unsigned column,
                    unsigned item) {
    SHHint selected;
    memset(&selected, 0, sizeof selected);
    selected.kind = kind;
    selected.row = (uint8_t)row;
    selected.column = (uint8_t)column;
    selected.item = (uint8_t)item;
    selected.clue_index = -1;
    return selected;
}

static void combined_support_and_invariance(void) {
    SherlockGame game, before, changed;
    SHHint selected = hint(SH_HINT_REMOVE, 0, 1, 0), original;
    SHHintProof proof, other;
    SHHintProofResult report, replay;
    combined_game(&game);
    selected.clue_index = 0;
    original = selected;
    before = game;
    assert(sh_explain_hint(&game, &selected, 10000, &proof, &report) == SH_PROOF_PROVED);
    assert(report.status == SH_PROOF_PROVED && report.reduction_complete);
    assert(report.deletion_checks == 3 && report.nodes_used <= report.node_budget);
    assert(proof.source_clue_count == 4 && proof.support_count == 2);
    assert(proof.support[0].index == 0 && proof.support[1].index == 1);
    assert(proof.selected_clue_index == 0);
    assert(proof.target.kind == selected.kind && proof.target.row == selected.row &&
        proof.target.column == selected.column && proof.target.item == selected.item);
    assert(memcmp(proof.candidates, game.board.candidates, sizeof proof.candidates) == 0);
    assert(memcmp(proof.given, game.puzzle.given, sizeof proof.given) == 0);
    assert(memcmp(&game, &before, sizeof game) == 0);
    assert(memcmp(&selected, &original, sizeof selected) == 0);
    assert_independent_proof(&proof, 1);
    other = proof;
    replay = report; /* Replay must clear the builder's minimality metadata. */
    assert(sh_replay_hint_proof(&proof, 10000, &replay) == SH_PROOF_PROVED);
    assert(!replay.reduction_complete && replay.deletion_checks == 0);
    assert(memcmp(&proof, &other, sizeof proof) == 0);

    changed = game;
    memset(changed.puzzle.solution, 5, sizeof changed.puzzle.solution);
    memset(changed.board.clue_slots, -1, sizeof changed.board.clue_slots);
    memset(changed.board.chosen, 0, sizeof changed.board.chosen);
    changed.elapsed_ms = 987654;
    changed.hint_pending = 1;
    changed.paused = 1;
    assert(sh_explain_hint(&changed, &selected, 10000, &other, &replay) == SH_PROOF_PROVED);
    assert(memcmp(&proof, &other, sizeof proof) == 0);
    assert(memcmp(&report, &replay, sizeof report) == 0);

    selected.kind = SH_HINT_CHOOSE;
    selected.column = 0;
    assert(sh_explain_hint(&game, &selected, 10000, &proof, &report) == SH_PROOF_PROVED);
    assert(proof.target.kind == SH_HINT_CHOOSE && proof.target.column == 0);
    assert(proof.support_count == 2 && report.reduction_complete);
    assert_independent_proof(&proof, 1);
}

static void row_rules_givens_and_user_assumptions(void) {
    SherlockGame game;
    SHHint selected = hint(SH_HINT_REMOVE, 0, 0, 2);
    SHHintProof proof;
    SHHintProofResult report;
    unsigned total, contrary;
    small_game(&game);
    game.board.candidates[0][0] = game.board.candidates[0][1] = 15;
    game.board.candidates[0][2] = game.board.candidates[0][3] = 12;
    game.board.candidates[0][4] = game.board.candidates[0][5] = 48;
    assert(sh_explain_hint(&game, &selected, 1000, &proof, &report) == SH_PROOF_PROVED);
    assert(proof.background_rules == SH_HINT_RULE_ROWS_ARE_PERMUTATIONS);
    assert(proof.support_count == 0 && report.reduction_complete);
    assert_independent_proof(&proof, 1);
    /* Relax one recorded player assumption. The Hall-based move no longer
     * follows, even though the original reduced clue set was empty. */
    proof.candidates[0][2] |= 1;
    assert(sh_replay_hint_proof(&proof, 1000, &report) == SH_PROOF_REFUTED);
    oracle_counts(&proof, SH_CLUE_CAPACITY, &total, &contrary);
    assert(total > 0 && contrary > 0);

    small_game(&game);
    game.board.candidates[0][0] = game.board.candidates[0][1] = 3;
    game.puzzle.given[0][0] = 0; /* Do not pre-encode this given in the masks. */
    selected = hint(SH_HINT_CHOOSE, 0, 0, 0);
    assert(sh_explain_hint(&game, &selected, 1000, &proof, &report) == SH_PROOF_PROVED);
    assert(proof.support_count == 0 && proof.given[0][0] == 0);
    assert_independent_proof(&proof, 1);
    proof.given[0][0] = -1;
    assert(sh_replay_hint_proof(&proof, 1000, &report) == SH_PROOF_REFUTED);
    oracle_counts(&proof, SH_CLUE_CAPACITY, &total, &contrary);
    assert(total == 2 && contrary == 1);

    game.puzzle.given[0][0] = -1;
    selected = hint(SH_HINT_REMOVE, 0, 0, 0);
    assert(sh_explain_hint(&game, &selected, 1000, &proof, &report) == SH_PROOF_REFUTED);
    assert(!report.reduction_complete && report.deletion_checks == 0);
    game.board.candidates[5][5] = 0;
    assert(sh_explain_hint(&game, &selected, 1000, &proof, &report) == SH_PROOF_INCONSISTENT);
    assert(!report.reduction_complete && report.deletion_checks == 0);
    oracle_counts(&proof, SH_CLUE_CAPACITY, &total, &contrary);
    assert(total == 0 && contrary == 0);
    assert(sh_replay_hint_proof(&proof, 1000, &report) == SH_PROOF_INCONSISTENT);
}

static void direct_clue_preferred_to_alternative_chain(void) {
    SherlockGame game;
    SherlockPuzzle no_clues = puzzle();
    SHHint selected = hint(SH_HINT_REMOVE, 0, 1, 0);
    SHHintProof proof;
    SHHintProofResult report;
    uint8_t contrary_candidates[6][6];
    unsigned total, contrary, complete_nodes, last_budget = 1000, before_last;
    small_game(&game);
    game.board.candidates[0][0] = game.board.candidates[0][1] = 3;
    game.board.candidates[1][0] = game.board.candidates[1][1] = 3;
    game.puzzle.clue_count = 3;
    game.puzzle.clues[0] = (SherlockClue){ SHERLOCK_SAME_COLUMN, 0, 12, 255 };
    game.puzzle.clues[1] = (SherlockClue){ SHERLOCK_SAME_COLUMN, 0, 6, 255 };
    game.puzzle.clues[2] = (SherlockClue){ SHERLOCK_SAME_COLUMN, 6, 12, 255 };
    /* With no selector preference, deleting clue 0 first yields the longer
     * but still deletion-minimal chain 1+2. Check both supports independently. */
    assert(sh_explain_hint(&game, &selected, 1000, &proof, &report) == SH_PROOF_PROVED);
    assert(report.reduction_complete && proof.support_count == 2);
    assert(proof.support[0].index == 1 && proof.support[1].index == 2);
    assert_independent_proof(&proof, 1);
    selected.clue_index = 0;
    assert(sh_explain_hint(&game, &selected, 1000, &proof, &report) == SH_PROOF_PROVED);
    assert(report.reduction_complete && report.deletion_checks == 3);
    assert(proof.support_count == 1 && proof.support[0].index == 0);
    assert(proof.target.kind == selected.kind && proof.target.row == selected.row &&
        proof.target.column == selected.column && proof.target.item == selected.item);
    assert_independent_proof(&proof, 1);
    complete_nodes = report.nodes_used;
    memcpy(contrary_candidates, game.board.candidates, sizeof contrary_candidates);
    contrary_candidates[0][1] = 1;
    assert(sh_check_candidates(&no_clues,
        (const uint8_t (*)[6])contrary_candidates, &last_budget) == SH_CONSTRAINT_SAT);
    before_last = complete_nodes - (1000 - last_budget);
    /* Exhaustion between the two priority passes must not mark the remaining
     * selected clue necessary without actually checking its deletion. */
    assert(sh_explain_hint(&game, &selected, before_last, &proof, &report) == SH_PROOF_PROVED);
    assert(!report.reduction_complete && report.deletion_checks == 2);
    assert(proof.support_count == 1 && proof.support[0].index == 0);
    assert(report.nodes_used == before_last);
    assert_independent_proof(&proof, 0);
    assert(sh_replay_hint_proof(&proof, 1000, &report) == SH_PROOF_PROVED);
    /* The selected clue is still eligible for deletion when frozen user
     * premises already establish the target without any clues. */
    game.board.candidates[0][0] = 1;
    selected = hint(SH_HINT_CHOOSE, 0, 0, 0);
    selected.clue_index = 0;
    assert(sh_explain_hint(&game, &selected, 1000, &proof, &report) == SH_PROOF_PROVED);
    assert(report.reduction_complete && proof.support_count == 0);
    assert(proof.selected_clue_index == 0);
    oracle_counts(&proof, SH_CLUE_CAPACITY, &total, &contrary);
    assert(total > 0 && contrary == 0);
}

static void budgets_do_not_certify_unknown_or_minimality(void) {
    SherlockGame game;
    SHHint selected = hint(SH_HINT_REMOVE, 0, 1, 0);
    SHHintProof proof, full;
    SHHintProofResult report;
    unsigned remaining = 10000, consistency_nodes, proof_nodes;
    combined_game(&game);
    assert(sh_explain_hint(&game, &selected, 0, &full, &report) == SH_PROOF_UNRESOLVED);
    assert(report.nodes_used == 0 && !report.reduction_complete);
    assert(full.support_count == 3);
    assert(sh_check_candidates(&game.puzzle,
        (const uint8_t (*)[6])game.board.candidates, &remaining) == SH_CONSTRAINT_SAT);
    consistency_nodes = 10000 - remaining;
    assert(consistency_nodes > 1);
    assert(sh_explain_hint(&game, &selected, consistency_nodes - 1,
        &proof, &report) == SH_PROOF_UNRESOLVED);
    assert(report.nodes_used == consistency_nodes - 1 && !report.reduction_complete);
    assert(sh_explain_hint(&game, &selected, consistency_nodes,
        &proof, &report) == SH_PROOF_UNRESOLVED);
    assert(report.nodes_used == consistency_nodes && !report.reduction_complete);
    assert(sh_replay_hint_proof(&full, 10000, &report) == SH_PROOF_PROVED);
    proof_nodes = report.nodes_used;
    assert(proof_nodes > consistency_nodes && !report.reduction_complete);
    assert(sh_explain_hint(&game, &selected, proof_nodes,
        &proof, &report) == SH_PROOF_PROVED);
    assert(report.nodes_used == proof_nodes && report.deletion_checks == 0);
    assert(!report.reduction_complete && proof.support_count == 3);
    assert_independent_proof(&proof, 0);
    assert(sh_explain_hint(&game, &selected, proof_nodes + 1,
        &proof, &report) == SH_PROOF_PROVED);
    assert(report.nodes_used == proof_nodes + 1 && report.deletion_checks == 1);
    assert(!report.reduction_complete && proof.support_count == 3);
    assert_independent_proof(&proof, 0);
    assert(sh_replay_hint_proof(&proof, 0, &report) == SH_PROOF_UNRESOLVED);
    assert(report.nodes_used == 0 && !report.reduction_complete);
}

static void malformed_and_tampered_records(void) {
    SherlockGame game;
    SHHint selected = hint(SH_HINT_REMOVE, 0, 1, 0);
    SHHintProof proof, changed;
    SHHintProofResult report;
    unsigned remaining;
    combined_game(&game);
    assert(sh_explain_hint(&game, &selected, 10000, &proof, NULL) == SH_PROOF_PROVED);
    changed = proof;
    changed.support_count = 1; /* An essential premise was dropped. */
    assert(sh_replay_hint_proof(&changed, 10000, &report) == SH_PROOF_REFUTED);
    changed = proof;
    changed.target.column = 0; /* A different move cannot inherit the proof. */
    assert(sh_replay_hint_proof(&changed, 10000, &report) == SH_PROOF_REFUTED);

#define EXPECT_INVALID(change) do { \
    changed = proof; change; \
    assert(sh_replay_hint_proof(&changed, 1000, &report) == SH_PROOF_INVALID); \
    assert(report.nodes_used == 0 && !report.reduction_complete); \
} while (0)
    EXPECT_INVALID(changed.version = 2);
    EXPECT_INVALID(changed.background_rules = 0);
    EXPECT_INVALID(changed.background_rules |= 2);
    EXPECT_INVALID(changed.target.kind = SH_HINT_CONTRADICTION);
    EXPECT_INVALID(changed.target.row = 6);
    EXPECT_INVALID(changed.target.column = 6);
    EXPECT_INVALID(changed.target.item = 6);
    EXPECT_INVALID(changed.candidates[0][1] &= (uint8_t)~1u);
    EXPECT_INVALID(changed.candidates[5][5] |= 0x80);
    EXPECT_INVALID(changed.given[5][5] = 6);
    EXPECT_INVALID(changed.given[5][5] = -2);
    EXPECT_INVALID(changed.source_clue_count = 257);
    EXPECT_INVALID(changed.support_count = 257);
    EXPECT_INVALID(changed.selected_clue_index = -2);
    EXPECT_INVALID(changed.selected_clue_index = 4);
    EXPECT_INVALID(changed.support[1].index = changed.support[0].index);
    EXPECT_INVALID(changed.support[1].index = 4);
    EXPECT_INVALID(changed.support[0].clue.type = 8);
    EXPECT_INVALID(changed.support[0].clue.type = SHERLOCK_UNUSED);
    EXPECT_INVALID(changed.support[0].clue.a = 36);
    EXPECT_INVALID(changed.support[0].clue.b = 36);
    EXPECT_INVALID(changed.support[0].clue.type = SHERLOCK_BETWEEN);
#undef EXPECT_INVALID

    assert(sh_replay_hint_proof(NULL, 1, NULL) == SH_PROOF_INVALID);
    assert(sh_explain_hint(NULL, &selected, 1, &changed, &report) == SH_PROOF_INVALID);
    assert(sh_explain_hint(&game, NULL, 1, &changed, NULL) == SH_PROOF_INVALID);
    assert(sh_explain_hint(&game, &selected, 1, NULL, NULL) == SH_PROOF_INVALID);
    game.puzzle.clue_count = 257;
    remaining = 123;
    assert(sh_check_candidates(&game.puzzle,
        (const uint8_t (*)[6])game.board.candidates, &remaining) == SH_CONSTRAINT_INVALID);
    assert(remaining == 123);
    assert(sh_explain_hint(&game, &selected, 123, &changed, &report) == SH_PROOF_INVALID);
    assert(report.nodes_used == 0);
    combined_game(&game);
    game.puzzle.clues[3].a = 36; /* Even inactive source cards must be valid. */
    assert(sh_explain_hint(&game, &selected, 123, &changed, &report) == SH_PROOF_INVALID);
    assert(report.nodes_used == 0);
    combined_game(&game);
    game.puzzle.given[0][0] = game.puzzle.given[0][1] = 0;
    assert(sh_explain_hint(&game, &selected, 1000, &changed, &report) == SH_PROOF_INCONSISTENT);
}

static void all_256_clue_indices_and_selected_hint(void) {
    SherlockGame game;
    SherlockPuzzle p;
    SHHint selected = hint(SH_HINT_CHOOSE, 0, 0, 0);
    SHHintProof proof;
    SHHintProofResult report;
    unsigned i;
    small_game(&game);
    game.board.candidates[0][0] = game.board.candidates[0][1] = 3;
    game.puzzle.clue_count = SH_CLUE_CAPACITY;
    for (i = 0; i < SH_CLUE_CAPACITY - 1; ++i)
        game.puzzle.clues[i] = (SherlockClue){ SHERLOCK_SAME_COLUMN, 0, 0, 255 };
    game.puzzle.clues[255] = (SherlockClue){ SHERLOCK_LEFT_OF, 0, 1, 255 };
    selected.clue_index = 255;
    assert(sh_explain_hint(&game, &selected, 0, &proof, &report) == SH_PROOF_UNRESOLVED);
    assert(proof.source_clue_count == 256 && proof.support_count == 256);
    assert(proof.support[255].index == 255);
    assert(sh_explain_hint(&game, &selected, 10000, &proof, &report) == SH_PROOF_PROVED);
    assert(report.deletion_checks == 256 && report.reduction_complete);
    assert(proof.support_count == 1 && proof.support[0].index == 255);
    assert(proof.selected_clue_index == 255);
    assert_independent_proof(&proof, 1);
    assert(sh_replay_hint_proof(&proof, 10000, NULL) == SH_PROOF_PROVED);

    /* Exercise the boundary with a real selector result too; do not assert
     * historical hint order here, since that is a separate fidelity contract. */
    p = puzzle();
    p.given[1][2] = 0;
    p.clue_count = 1;
    p.clues[0] = (SherlockClue){ SHERLOCK_SAME_COLUMN, 0, 6, 255 };
    sh_game_init(&game, &p, 0);
    assert(sh_find_hint(&game, &selected, 1000) == 1);
    assert(sh_explain_hint(&game, &selected, 10000, &proof, &report) == SH_PROOF_PROVED);
    assert(proof.target.kind == selected.kind && proof.target.row == selected.row &&
        proof.target.column == selected.column && proof.target.item == selected.item);
    assert(sh_replay_hint_proof(&proof, 10000, &report) == SH_PROOF_PROVED);
}

int main(void) {
    combined_support_and_invariance();
    row_rules_givens_and_user_assumptions();
    direct_clue_preferred_to_alternative_chain();
    budgets_do_not_certify_unknown_or_minimality();
    malformed_and_tampered_records();
    all_256_clue_indices_and_selected_hint();
    puts("Hint support: independent replay, conditional premises, strict bounds and budget outcomes passed.");
    return 0;
}
