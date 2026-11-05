/* These are synthetic player-state/constraint tests. They do not qualify the
 * recovered generator, original puzzle identity or native AppKit behavior. */
#include "../state/sherlock_state.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static SherlockPuzzle fixture(void) {
    SherlockPuzzle puzzle;
    unsigned r, c;
    memset(&puzzle, 0, sizeof puzzle);
    memset(puzzle.given, -1, sizeof puzzle.given);
    for (r = 0; r < 6; ++r) for (c = 0; c < 6; ++c)
        puzzle.solution[r][c] = (uint8_t)c;
    return puzzle;
}

static void original_board_contract(void) {
    SherlockPuzzle p = fixture();
    SherlockGame g;
    unsigned c;
    const uint8_t initial[] = { 59, 59, 59, 59, 132, 59 };
    const uint8_t chosen[] = { 66, 57, 57, 57, 132, 57 };
    p.given[0][4] = 2;
    sh_game_init(&g, &p, 0);
    for (c = 0; c < 6; ++c) assert(sh_cell_byte(&g, 0, c) == initial[c]);
    assert(sh_remove(&g, 0, 0, 0) == 1);
    assert(sh_cell_byte(&g, 0, 0) == 58);
    assert(sh_choose(&g, 0, 0, 1) == 1);
    for (c = 0; c < 6; ++c) assert(sh_cell_byte(&g, 0, c) == chosen[c]);
    assert(sh_remove(&g, 0, 0, 1) == 1);
    assert(sh_cell_byte(&g, 0, 0) == 0);
    for (c = 1; c < 6; ++c) assert(sh_cell_byte(&g, 0, c) == chosen[c]);
    assert(sh_undo(&g) == 1);
    for (c = 0; c < 6; ++c) assert(sh_cell_byte(&g, 0, c) == chosen[c]);
    assert(sh_remove(&g, 0, 4, 2) == 0);
    assert(sh_restore(&g, 0, 4, 1) == 0);
    assert(sh_choose(&g, 0, 4, 1) == 0);
    assert(sh_restore(&g, 0, 0, 0) == 1);
    assert(sh_cell_byte(&g, 0, 0) == 3);
    assert(g.board.chosen[0][0] == -1);
}

static void explicit_selection_and_verdict(void) {
    SherlockPuzzle p = fixture();
    SherlockGame g;
    unsigned r, c, i;
    /* Rejection must follow a visible rule, not a hidden stored answer. */
    p.clue_count = 1;
    p.clues[0] = (SherlockClue){SHERLOCK_LEFT_OF, 0, 5, 255};
    memset(p.solution, 255, sizeof p.solution); /* The game must ignore this. */
    sh_game_init(&g, &p, 0);
    for (i = 1; i < 6; ++i) assert(sh_remove(&g, 0, 0, i) == 1);
    assert(g.board.candidates[0][0] == 1);
    assert(g.board.chosen[0][0] == -1); /* No automatic singleton selection. */
    for (r = 0; r < 6; ++r) for (c = 0; c < 6; ++c) {
        assert(g.outcome == SH_PLAYING);
        assert(sh_choose(&g, r, c, c) == 1);
    }
    assert(g.outcome == SH_WON);
    sh_game_init(&g, &p, 0);
    for (r = 0; r < 6; ++r) for (c = 0; c < 6; ++c) {
        assert(g.outcome == SH_PLAYING); /* Mistakes are not rejected early. */
        assert(sh_choose(&g, r, c, (c + 1) % 6) == 1);
    }
    assert(g.outcome == SH_WRONG);
}

static void clue_relations(void) {
    assert(sh_relation_holds(0, 2, 2, 0));
    assert(!sh_relation_holds(0, 2, 3, 0));
    assert(sh_relation_holds(1, 2, 3, 0));
    assert(!sh_relation_holds(1, 2, 2, 0));
    assert(sh_relation_holds(2, 1, 2, 0));
    assert(sh_relation_holds(2, 2, 1, 0));
    assert(!sh_relation_holds(2, 0, 5, 0));
    assert(sh_relation_holds(3, 2, 2, 0));
    assert(!sh_relation_holds(3, 2, 3, 0));
    assert(sh_relation_holds(4, 0, 5, 0));
    assert(!sh_relation_holds(4, 2, 2, 0));
    assert(sh_relation_holds(5, 1, 2, 3));
    assert(sh_relation_holds(5, 3, 2, 1));
    assert(!sh_relation_holds(5, 0, 2, 4));
    assert(sh_relation_holds(6, 1, 0, 3));
    assert(!sh_relation_holds(6, 1, 2, 3));
    assert(!sh_relation_holds(6, 0, 2, 4)); /* Not merely !BETWEEN. */
}

static void undo_capacity_and_clue_holes(void) {
    SherlockPuzzle p = fixture();
    SherlockGame g;
    unsigned i, bank, group, slot;
    p.clue_count = 4;
    p.clues[0] = (SherlockClue){ 2, 0, 6, 0 };
    p.clues[1] = (SherlockClue){ 4, 1, 7, 0 };
    p.clues[2] = (SherlockClue){ 5, 2, 8, 14 };
    p.clues[3] = (SherlockClue){ 0, 3, 9, 0 };
    sh_game_init(&g, &p, 0);
    assert(sh_archive_clue(&g, 0) == 1);
    assert(g.board.clue_slots[0][1][0] == -1);
    assert(g.board.clue_slots[0][1][1] == 1);
    assert(g.board.clue_slots[0][1][2] == 2);
    assert(sh_clue_location(&g, 0, &bank, &group, &slot));
    assert(bank == 1 && group == 1 && slot == 0);
    assert(sh_undo(&g) == 1);
    assert(g.board.clue_slots[0][1][0] == 0);
    assert(sh_move_clue(&g, 0, 1) == 1);
    assert(g.board.clue_slots[0][1][0] == -1);
    assert(g.board.clue_slots[0][1][1] == 0);
    assert(g.board.clue_slots[0][1][2] == 1);
    assert(g.board.clue_slots[0][1][3] == 2);
    assert(sh_undo(&g) == 1);
    assert(sh_move_clue(&g, 2, 0) == 1);
    assert(g.board.clue_slots[0][1][0] == 2);
    assert(g.board.clue_slots[0][1][1] == 0);
    assert(g.board.clue_slots[0][1][2] == 1);
    sh_game_init(&g, &p, 0);
    for (i = 0; i < 26; ++i)
        assert(sh_remove(&g, i / 6, i % 6, 0) == 1);
    assert(g.undo_count == 25);
    for (i = 0; i < 25; ++i) assert(sh_undo(&g) == 1);
    assert(sh_undo(&g) == 0);
    assert(g.board.candidates[0][0] == 62);
    assert(g.board.candidates[0][1] == 63);
}

static void two_phase_hint_and_time(void) {
    SherlockPuzzle p = fixture();
    SherlockGame g, other;
    SHHint hint, other_hint;
    SHBoard before;
    p.given[1][2] = 0;
    p.clue_count = 1;
    p.clues[0] = (SherlockClue){ 0, 0, 6, 0 };
    sh_game_init(&g, &p, 0);
    sh_tick(&g, 1000);
    before = g.board;
    assert(sh_find_hint(&g, &hint, 1000) == 1);
    assert(hint.kind == SH_HINT_REMOVE);
    assert(hint.row == 0 && hint.column == 0 && hint.item == 0);
    other = g;
    memset(other.puzzle.solution, 5, sizeof other.puzzle.solution);
    assert(sh_find_hint(&other, &other_hint, 1000) == 1);
    assert(memcmp(&hint, &other_hint, sizeof hint) == 0);
    assert(sh_request_hint(&g, 1000) == 1);
    assert(g.hint_pending && g.elapsed_ms == 31000);
    assert(memcmp(&before, &g.board, sizeof before) == 0);
    assert(sh_request_hint(&g, 1000) == 0); /* No double charge. */
    sh_tick(&g, 2000); /* The logical clock does not freeze at the hint. */
    assert(g.elapsed_ms == 33000);
    assert(sh_accept_hint(&g) == 1);
    assert(!g.hint_pending && g.board.candidates[0][0] == 62);
    assert(sh_undo(&g) == 1);
    assert(memcmp(&before, &g.board, sizeof before) == 0);
    assert(g.elapsed_ms == 33000); /* Undo never refunds the penalty. */
    sh_game_init(&g, &p, 3601);
    sh_tick(&g, 1000);
    assert(sh_display_time_ms(&g) == 3600000);
    assert(g.outcome == SH_PLAYING); /* Regression: crossing one hour. */
    sh_set_paused(&g, 1);
    sh_tick(&g, 50000);
    assert(g.elapsed_ms == 1000);
    sh_set_paused(&g, 0);
    sh_tick(&g, 3600000);
    assert(g.outcome == SH_TIMED_OUT && sh_display_time_ms(&g) == 0);
    sh_game_init(&g, &p, 0);
    g.board.candidates[0][0] = 0;
    assert(sh_find_hint(&g, &hint, 1000) == 0);
    assert(hint.kind == SH_HINT_CONTRADICTION);
}

static void full_clue_grid_stays_visible(void) {
    SherlockPuzzle p = fixture();
    SherlockGame g;
    unsigned group, capacity, i;
    for (group = 0; group < 2; ++group) {
        capacity = group ? SH_HORIZONTAL_SLOTS : SH_VERTICAL_SLOTS;
        p.clue_count = (uint16_t)capacity;
        for (i = 0; i < capacity; ++i) {
            p.clues[i] = (SherlockClue){ (uint8_t)(group ? 2 : 0), 0, 6, 0 };
            p.original_slot[i] = (uint8_t)((group ? 54 : 36) + i);
        }
        sh_game_init(&g, &p, 0);
        assert(sh_move_clue(&g, 0, capacity - 1) == 1);
        for (i = 0; i < capacity - 1; ++i)
            assert(g.board.clue_slots[0][group][i] == (int16_t)(i + 1));
        assert(g.board.clue_slots[0][group][capacity - 1] == 0);
        assert(g.board.clue_slots[0][group][capacity] == -1);
        assert(sh_move_clue(&g, 0, capacity) == -1);
        assert(sh_undo(&g) == 1);
        for (i = 0; i < capacity; ++i)
            assert(g.board.clue_slots[0][group][i] == (int16_t)i);
    }
    p = fixture();
    p.clue_count = 2;
    p.clues[0] = (SherlockClue){ 2, 0, 6, 0 };
    p.clues[1] = (SherlockClue){ 2, 1, 7, 0 };
    p.original_slot[0] = 54;
    p.original_slot[1] = 60;
    sh_game_init(&g, &p, 0);
    assert(g.board.clue_slots[0][1][0] == 0);
    assert(g.board.clue_slots[0][1][1] == -1);
    assert(g.board.clue_slots[0][1][6] == 1);
}

static void unused_references_follow_original_slot(void) {
    SherlockPuzzle p = fixture();
    SherlockGame g;
    unsigned bank, group, slot;
    /* Seed 1465's extracted table has a reference in original slot 63. This
     * focused fixture tests placement, not that seed's full puzzle identity. */
    p.clue_count = 2;
    p.clues[0] = (SherlockClue){ SHERLOCK_UNUSED, 0, 255, 255 };
    p.clues[1] = (SherlockClue){ SHERLOCK_UNUSED, 6, 255, 255 };
    p.original_slot[0] = 63;
    p.original_slot[1] = 36;
    assert(sh_puzzle_clue_group(&p, 0) == 1);
    assert(sh_puzzle_clue_group(&p, 1) == 0);
    assert(sh_puzzle_clue_group(&p, 2) == -1);
    sh_game_init(&g, &p, 0);
    assert(g.board.clue_slots[0][1][9] == 0);
    assert(g.board.clue_slots[0][0][0] == 1);
    assert(sh_archive_clue(&g, 0) == 1);
    assert(sh_clue_location(&g, 0, &bank, &group, &slot) == 1);
    assert(bank == 1 && group == 1 && slot == 0);
    assert(sh_move_clue(&g, 0, 20) == 1);
    assert(g.board.clue_slots[1][1][20] == 0);
    assert(sh_undo(&g) == 1);
    assert(sh_undo(&g) == 1);
    assert(g.board.clue_slots[0][1][9] == 0);
    assert(g.board.clue_slots[0][0][0] == 1);
}

int main(void) {
    original_board_contract();
    explicit_selection_and_verdict();
    clue_relations();
    undo_capacity_and_clue_holes();
    two_phase_hint_and_time();
    full_clue_grid_stays_visible();
    unused_references_follow_original_slot();
    puts("Player state: synthetic constraints and retained original board/undo witnesses passed.");
    return 0;
}
