/* Exhaustive finite-corpus integration: every recovered puzzle must enter
 * player state without losing a clue, misplacing a reference card, or changing
 * its givens, and its original answer must be accepted by normal selections.
 * This does not claim exhaustive interactive or hint-sequence equivalence. */
#include "../core/sherlock_core.h"
#include "../state/sherlock_state.h"
#include <assert.h>
#include <stdio.h>

int main(int argc, char **argv) {
    SherlockPuzzle puzzle;
    SherlockGame game;
    unsigned number, clues = 0, givens = 0, horizontal_references = 0;
    unsigned max_clues = 0;
    if (argc != 2 || sherlock_load_puzzle_table(argv[1]) != 0) {
        fprintf(stderr, "Table load: %s\n", sherlock_core_error());
        return 1;
    }
    for (number = 0; number < 65536; ++number) {
        unsigned i, row, col, bank, group, slot, visible = 0;
        assert(sherlock_generate((uint16_t)number, &puzzle) == 0);
        sh_game_init(&game, &puzzle, 0);
        assert(game.outcome == SH_PLAYING && game.undo_count == 0);
        for (row = 0; row < 6; ++row) {
            uint8_t available = 63;
            for (col = 0; col < 6; ++col)
                if (puzzle.given[row][col] >= 0)
                    available &= (uint8_t)~(1u << puzzle.given[row][col]);
            for (col = 0; col < 6; ++col) {
                int item = puzzle.given[row][col];
                uint8_t expected = item >= 0 ? (uint8_t)(128u | (1u << item)) : available;
                assert(sh_cell_byte(&game, row, col) == expected);
                givens += item >= 0;
            }
        }
        for (i = 0; i < puzzle.clue_count; ++i) {
            unsigned original = puzzle.original_slot[i];
            unsigned wanted_group = original >= 54;
            unsigned wanted_slot = original - (wanted_group ? 54 : 36);
            assert(original >= 36 && original <= 74);
            assert(sh_puzzle_clue_group(&puzzle, i) == (int)wanted_group);
            assert(sh_clue_location(&game, i, &bank, &group, &slot) == 1);
            assert(bank == 0 && group == wanted_group && slot == wanted_slot);
            if (puzzle.clues[i].type == SHERLOCK_UNUSED && wanted_group) {
                ++horizontal_references;
                assert(sh_archive_clue(&game, i) == 1);
                assert(sh_clue_location(&game, i, &bank, &group, &slot) == 1);
                assert(bank == 1 && group == 1 && slot < SH_HORIZONTAL_SLOTS);
                assert(sh_undo(&game) == 1);
                assert(sh_clue_location(&game, i, &bank, &group, &slot) == 1);
                assert(bank == 0 && group == 1 && slot == wanted_slot);
            }
        }
        for (bank = 0; bank < 2; ++bank)
            for (group = 0; group < 2; ++group)
                for (slot = 0; slot < SH_CLUE_CAPACITY; ++slot) {
                    int index = game.board.clue_slots[bank][group][slot];
                    if (index < 0) continue;
                    assert(bank == 0);
                    assert(slot < (group ? SH_HORIZONTAL_SLOTS : SH_VERTICAL_SLOTS));
                    assert((unsigned)index < puzzle.clue_count);
                    ++visible;
                }
        assert(visible == puzzle.clue_count);
        if (puzzle.clue_count > max_clues) max_clues = puzzle.clue_count;
        clues += puzzle.clue_count;
        for (row = 0; row < 6; ++row)
            for (col = 0; col < 6; ++col)
                if (!game.fixed[row][col])
                    assert(sh_choose(&game, row, col, puzzle.solution[row][col]) == 1);
        assert(game.outcome == SH_WON);
    }
    assert(horizontal_references > 0);
    printf("Corpus integration passed: 65536 initial boards, clue layouts and accepted original answers; "
           "%u clues, %u givens, %u horizontal reference cards, maximum %u clues.\n",
           clues, givens, horizontal_references, max_clues);
    return 0;
}
