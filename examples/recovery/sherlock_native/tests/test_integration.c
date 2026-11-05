/* Integration checks against the recovered original puzzle semantics.
 * Hints must never eliminate the original solution or select another item.
 * The test oracle reads the solution; the production hint path does not.
 */
#include "../core/sherlock_core.h"
#include "../state/sherlock_state.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const uint8_t original_zero[6][6] = {
    {5,3,0,1,2,4},{4,5,1,0,3,2},{5,0,3,2,1,4},
    {3,2,4,1,5,0},{2,1,0,3,4,5},{3,4,5,1,0,2}
};
static const uint8_t original_one[6][6] = {
    {2,4,3,5,1,0},{4,0,2,3,5,1},{4,5,2,1,0,3},
    {1,0,4,3,5,2},{5,4,1,3,2,0},{0,5,2,3,1,4}
};

static unsigned hint_solve(const SherlockPuzzle *puzzle) {
    SherlockGame game;
    unsigned moves = 0;
    sh_game_init(&game, puzzle, 0);
    while (game.outcome == SH_PLAYING && moves < 512) {
        SHHint h;
        int found = sh_find_hint(&game, &h, 20000);
        if (found != 1) {
            fprintf(stderr,"Puzzle %u stopped after %u hints: %s\n",
                    puzzle->number,moves,h.explanation);
            return 0;
        }
        assert(h.row < 6 && h.column < 6 && h.item < 6);
        if (h.kind == SH_HINT_REMOVE) {
            assert(puzzle->solution[h.row][h.column] != h.item);
        } else {
            assert(h.kind == SH_HINT_CHOOSE);
            assert(puzzle->solution[h.row][h.column] == h.item);
        }
        assert(sh_request_hint(&game, 20000) == 1);
        assert(game.pending_hint.kind == h.kind);
        assert(game.pending_hint.row == h.row);
        assert(game.pending_hint.column == h.column);
        assert(game.pending_hint.item == h.item);
        assert(sh_accept_hint(&game) == 1);
        ++moves;
    }
    assert(game.outcome == SH_WON);
    assert(game.elapsed_ms == (uint64_t)moves * 30000u);
    return moves;
}

static void explicit_completion(const SherlockPuzzle *puzzle) {
    SherlockGame game;
    unsigned row, column;
    sh_game_init(&game, puzzle, 0);
    for (row = 0; row < 6; ++row)
        for (column = 0; column < 6; ++column)
            if (!game.fixed[row][column])
                assert(sh_choose(&game,row,column,puzzle->solution[row][column]) == 1);
    assert(game.outcome == SH_WON);
}

int main(int argc, char **argv) {
    SherlockPuzzle puzzle;
    unsigned n, found = 0, solved = 0, hint_count = 0;
    unsigned requested = argc > 2 ? (unsigned)strtoul(argv[2],NULL,10) : 64;
    if (argc < 2 || sherlock_load_puzzle_table(argv[1]) != 0) {
        fprintf(stderr,"Table load: %s\n",sherlock_core_error()); return 1;
    }
    assert(sherlock_generate(0,&puzzle) == 0);
    assert(memcmp(puzzle.solution,original_zero,sizeof original_zero) == 0);
    assert(puzzle.given[0][4] == 2 && puzzle.given[3][0] == 3 &&
           puzzle.given[4][4] == 4 && puzzle.clue_count == 25);
    assert(sherlock_generate(1,&puzzle) == 0);
    assert(memcmp(puzzle.solution,original_one,sizeof original_one) == 0);
    /* Fixed witnesses include the version-specific puzzle235 and upper bound. */
    { const uint16_t witnesses[] = {0,1,235,11656,65535};
      for (n = 0; n < sizeof witnesses/sizeof witnesses[0]; ++n) {
        assert(sherlock_generate(witnesses[n],&puzzle) == 0);
        explicit_completion(&puzzle);
        { unsigned moves = hint_solve(&puzzle); assert(moves); hint_count += moves; ++solved; }
      }
    }
    /* A large stride spans the whole uint16_t range even on a partial build. */
    for (n = 0; n < 65536 && found < requested; ++n) {
        uint16_t seed = (uint16_t)(n * 997u);
        if (sherlock_generate(seed,&puzzle) != 0) continue;
        explicit_completion(&puzzle);
        { unsigned moves = hint_solve(&puzzle); assert(moves); hint_count += moves; ++solved; }
        ++found;
    }
    assert(found == requested);
    printf("Integration passed: %u complete hint-solved games, %u sound deductions; original witnesses 0/1/235/11656/65535.\n",solved,hint_count);
    return 0;
}
