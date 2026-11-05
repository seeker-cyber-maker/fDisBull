#include "sherlock_state.h"
#include "../core/sherlock_logic.h"

#include <limits.h>
#include <stdio.h>
#include <string.h>

static int valid_cell(unsigned row, unsigned column, unsigned item) {
    return row < SH_SIZE && column < SH_SIZE && item < SH_SIZE;
}

static unsigned bits(uint8_t value) {
    unsigned count = 0;
    while (value) { count += value & 1u; value >>= 1; }
    return count;
}

static unsigned first_bit(uint8_t value) {
    unsigned bit = 0;
    while (bit < SH_SIZE && !(value & (1u << bit))) ++bit;
    return bit;
}

/* Undo intentionally does not snapshot the clock. Original-DOS observations
 * confirmed that undoing a hint restores candidates without refunding time. */
static void remember(SherlockGame *game) {
    if (game->undo_count == SH_UNDO_LIMIT) {
        memmove(&game->undo[0], &game->undo[1],
                (SH_UNDO_LIMIT - 1) * sizeof game->undo[0]);
        --game->undo_count;
    }
    game->undo[game->undo_count++] = game->board;
}

static void final_verdict(SherlockGame *game) {
    unsigned row, column;
    uint8_t answer[SH_SIZE][SH_SIZE];
    for (row = 0; row < SH_SIZE; ++row)
        for (column = 0; column < SH_SIZE; ++column) {
            if (game->board.chosen[row][column] < 0) return;
            answer[row][column] = (uint8_t)game->board.chosen[row][column];
        }
    game->outcome = sherlock_verify_answer(&game->puzzle,
        (const uint8_t (*)[SH_SIZE])answer, NULL) == SH_VERIFY_ACCEPTED ?
        SH_WON : SH_WRONG;
}

int sh_clue_group(const SherlockClue *clue) {
    return clue && clue->type >= 2 && clue->type <= 6 ? 1 : 0;
}

int sh_puzzle_clue_group(const SherlockPuzzle *puzzle, unsigned clue) {
    unsigned slot;
    if (!puzzle || clue >= puzzle->clue_count) return -1;
    slot = puzzle->original_slot[clue];
    if (slot >= 36 && slot <= 53) return 0;
    if (slot >= 54 && slot <= 74) return 1;
    return sh_clue_group(&puzzle->clues[clue]);
}

void sh_game_init(SherlockGame *game, const SherlockPuzzle *puzzle,
                  uint32_t time_limit_seconds) {
    SherlockPuzzle snapshot;
    unsigned row, column, other, i;
    unsigned next[2] = { 0, 0 };
    if (!game || !puzzle) return;
    snapshot = *puzzle; /* Permit restarting from &game->puzzle. */
    memset(game, 0, sizeof *game);
    game->puzzle = snapshot;
    puzzle = &game->puzzle;
    memset(game->board.chosen, -1, sizeof game->board.chosen);
    memset(game->board.clue_slots, -1, sizeof game->board.clue_slots);
    game->limit_ms = (uint64_t)time_limit_seconds * 1000u;
    for (row = 0; row < SH_SIZE; ++row)
        for (column = 0; column < SH_SIZE; ++column)
            game->board.candidates[row][column] = 63;
    for (row = 0; row < SH_SIZE; ++row) {
        for (column = 0; column < SH_SIZE; ++column) {
            int item = puzzle->given[row][column];
            if (item < 0 || item >= SH_SIZE) continue;
            game->fixed[row][column] = 1;
            game->board.chosen[row][column] = (int8_t)item;
            game->board.candidates[row][column] = (uint8_t)(1u << item);
            for (other = 0; other < SH_SIZE; ++other)
                if (other != column)
                    game->board.candidates[row][other] &=
                        (uint8_t)~(1u << item);
        }
    }
    if (puzzle->clue_count > SH_CLUE_CAPACITY) {
        game->outcome = SH_WRONG;
        return;
    }
    for (i = 0; i < puzzle->clue_count; ++i) {
        unsigned group = (unsigned)sh_puzzle_clue_group(puzzle, i);
        unsigned raw = puzzle->original_slot[i];
        unsigned capacity = group ? SH_HORIZONTAL_SLOTS : SH_VERTICAL_SLOTS;
        unsigned slot = next[group];
        if (!group && raw >= 36 && raw <= 53) slot = raw - 36;
        if (group && raw >= 54 && raw <= 74) slot = raw - 54;
        while (slot < capacity && game->board.clue_slots[0][group][slot] >= 0)
            ++slot;
        if (slot >= capacity) { game->outcome = SH_WRONG; return; }
        game->board.clue_slots[0][group][slot] = (int16_t)i;
        while (next[group] < capacity &&
               game->board.clue_slots[0][group][next[group]] >= 0) ++next[group];
    }
}

uint8_t sh_cell_byte(const SherlockGame *game, unsigned row, unsigned column) {
    uint8_t value;
    if (!game || row >= SH_SIZE || column >= SH_SIZE) return 0;
    value = game->board.candidates[row][column] & 63;
    if (game->fixed[row][column]) value |= 0x80;
    else if (game->board.chosen[row][column] >= 0) value |= 0x40;
    return value;
}

int sh_remove(SherlockGame *game, unsigned row, unsigned column, unsigned item) {
    uint8_t bit;
    if (!game || !valid_cell(row, column, item)) return -1;
    if (game->outcome != SH_PLAYING || game->paused || game->hint_pending ||
        game->fixed[row][column]) return 0;
    bit = (uint8_t)(1u << item);
    if (!(game->board.candidates[row][column] & bit)) return 0;
    remember(game);
    game->board.candidates[row][column] &= (uint8_t)~bit;
    /* The original permits removing a full chosen tile to an empty cell. It
     * does not restore that item's earlier eliminations elsewhere in the row. */
    game->board.chosen[row][column] = -1;
    return 1;
}

int sh_restore(SherlockGame *game, unsigned row, unsigned column, unsigned item) {
    uint8_t bit;
    if (!game || !valid_cell(row, column, item)) return -1;
    if (game->outcome != SH_PLAYING || game->paused || game->hint_pending ||
        game->fixed[row][column]) return 0;
    bit = (uint8_t)(1u << item);
    if (game->board.candidates[row][column] & bit) return 0;
    remember(game);
    game->board.candidates[row][column] |= bit;
    game->board.chosen[row][column] = -1;
    return 1;
}

int sh_choose(SherlockGame *game, unsigned row, unsigned column, unsigned item) {
    unsigned other;
    uint8_t bit;
    if (!game || !valid_cell(row, column, item)) return -1;
    if (game->outcome != SH_PLAYING || game->paused || game->hint_pending ||
        game->fixed[row][column]) return 0;
    bit = (uint8_t)(1u << item);
    if (!(game->board.candidates[row][column] & bit) ||
        game->board.chosen[row][column] == (int8_t)item) return 0;
    remember(game);
    game->board.candidates[row][column] = bit;
    game->board.chosen[row][column] = (int8_t)item;
    for (other = 0; other < SH_SIZE; ++other) {
        if (other == column || game->fixed[row][other]) continue;
        game->board.candidates[row][other] &= (uint8_t)~bit;
        if (game->board.chosen[row][other] == (int8_t)item)
            game->board.chosen[row][other] = -1;
    }
    final_verdict(game);
    return 1;
}

int sh_undo(SherlockGame *game) {
    if (!game) return -1;
    if (!game->undo_count || game->hint_pending || game->paused ||
        game->outcome != SH_PLAYING) return 0;
    game->board = game->undo[--game->undo_count];
    return 1;
}

int sh_clue_location(const SherlockGame *game, unsigned clue,
                     unsigned *bank, unsigned *group, unsigned *slot) {
    unsigned b, g, s;
    if (!game || clue >= game->puzzle.clue_count) return 0;
    for (b = 0; b < 2; ++b) for (g = 0; g < 2; ++g)
        for (s = 0; s < SH_CLUE_CAPACITY; ++s)
            if (game->board.clue_slots[b][g][s] == (int16_t)clue) {
                if (bank) *bank = b;
                if (group) *group = g;
                if (slot) *slot = s;
                return 1;
            }
    return 0;
}

int sh_archive_clue(SherlockGame *game, unsigned clue) {
    unsigned bank, group, source, destination, capacity;
    if (!game || clue >= game->puzzle.clue_count) return -1;
    if (game->outcome != SH_PLAYING || game->paused || game->hint_pending)
        return 0;
    if (!sh_clue_location(game, clue, &bank, &group, &source)) return -1;
    capacity = group ? SH_HORIZONTAL_SLOTS : SH_VERTICAL_SLOTS;
    for (destination = 0; destination < capacity; ++destination)
        if (game->board.clue_slots[1 - bank][group][destination] < 0) break;
    if (destination == capacity) return -1;
    remember(game);
    game->board.clue_slots[bank][group][source] = -1;
    game->board.clue_slots[1 - bank][group][destination] = (int16_t)clue;
    return 1;
}

int sh_move_clue(SherlockGame *game, unsigned clue, unsigned destination) {
    unsigned bank, group, source, free_slot, capacity, i;
    int16_t *slots;
    if (!game || clue >= game->puzzle.clue_count ||
        destination >= SH_CLUE_CAPACITY) return -1;
    if (game->outcome != SH_PLAYING || game->paused || game->hint_pending)
        return 0;
    if (!sh_clue_location(game, clue, &bank, &group, &source)) return -1;
    capacity = group ? SH_HORIZONTAL_SLOTS : SH_VERTICAL_SLOTS;
    if (destination >= capacity || source >= capacity) return -1;
    if (source == destination) return 0;
    slots = game->board.clue_slots[bank][group];
    free_slot = destination;
    while (free_slot < capacity && slots[free_slot] >= 0 &&
           free_slot != source) ++free_slot;
    remember(game);
    if (free_slot == capacity) {
        /* The destination's suffix is full. Reuse the source vacancy by moving
         * the intervening cards left, keeping every clue inside the visible
         * grid. Never create an invisible 19th/22nd clue slot. */
        for (i = source; i < destination; ++i) slots[i] = slots[i + 1];
        slots[destination] = (int16_t)clue;
        return 1;
    }
    slots[source] = -1;
    while (free_slot > destination) {
        slots[free_slot] = slots[free_slot - 1];
        --free_slot;
    }
    slots[destination] = (int16_t)clue;
    return 1;
}

static void advance_elapsed(SherlockGame *game, uint64_t milliseconds) {
    if (UINT64_MAX - game->elapsed_ms < milliseconds)
        game->elapsed_ms = UINT64_MAX;
    else game->elapsed_ms += milliseconds;
}

void sh_tick(SherlockGame *game, uint64_t milliseconds) {
    if (!game || game->paused || game->outcome != SH_PLAYING) return;
    advance_elapsed(game, milliseconds);
    /* The original modal defers expiration until its acknowledgement. Elapsed
     * wall time still counts; closing the hint must not create a free pause. */
    if (!game->hint_pending && game->limit_ms &&
        game->elapsed_ms >= game->limit_ms) {
        game->outcome = SH_TIMED_OUT;
        game->hint_pending = 0;
    }
}

void sh_set_paused(SherlockGame *game, int paused) {
    if (game) game->paused = !!paused;
}

uint64_t sh_display_time_ms(const SherlockGame *game) {
    if (!game) return 0;
    if (!game->limit_ms) return game->elapsed_ms;
    return game->elapsed_ms >= game->limit_ms ? 0 :
           game->limit_ms - game->elapsed_ms;
}

void sh_quit(SherlockGame *game) {
    if (game && game->outcome == SH_PLAYING) {
        game->outcome = SH_QUIT;
        game->hint_pending = 0;
    }
}

int sh_relation_holds(unsigned type, int a, int b, int c) {
    return sherlock_relation_holds(type, a, b, c);
}

static void visible_domains(const SherlockGame *game, uint8_t domains[36]) {
    unsigned row, item, column;
    memset(domains, 0, 36);
    for (row = 0; row < 6; ++row) for (item = 0; item < 6; ++item)
        for (column = 0; column < 6; ++column)
            if (game->board.candidates[row][column] & (1u << item))
                domains[row * 6 + item] |= (uint8_t)(1u << column);
}

static int consistent_pair(unsigned a, unsigned b, unsigned ca, unsigned cb) {
    if (a == b) return ca == cb;
    return a / 6 != b / 6 || ca != cb;
}

static unsigned clue_arity(const SherlockClue *clue) {
    return clue->type == 5 || clue->type == 6 ? 3u : 2u;
}

/* Does this candidate participate in any legal tuple of this one clue? This
 * checks row identity too: distinct items from one row cannot share a column. */
static int has_support(const SherlockClue *clue, const uint8_t domains[36],
                       unsigned object, unsigned column) {
    unsigned a, b, c;
    unsigned arity = clue_arity(clue);
    if (clue->type == 7) return 1;
    if (clue->a >= 36 || clue->b >= 36 || (arity == 3 && clue->c >= 36))
        return 0;
    for (a = 0; a < 6; ++a) {
        if (!(domains[clue->a] & (1u << a)) ||
            (clue->a == object && a != column)) continue;
        for (b = 0; b < 6; ++b) {
            if (!(domains[clue->b] & (1u << b)) ||
                (clue->b == object && b != column) ||
                !consistent_pair(clue->a, clue->b, a, b)) continue;
            for (c = 0; c < (arity == 3 ? 6u : 1u); ++c) {
                if (arity == 3 &&
                    (!(domains[clue->c] & (1u << c)) ||
                     (clue->c == object && c != column) ||
                     !consistent_pair(clue->a, clue->c, a, c) ||
                     !consistent_pair(clue->b, clue->c, b, c))) continue;
                if (sh_relation_holds(clue->type, (int)a, (int)b, (int)c))
                    return 1;
            }
        }
    }
    return 0;
}

/* Generalized arc consistency plus each row's small all-different constraint.
 * Returns false on a contradiction. No solution image or generator state is
 * read; the same routine can verify candidate assumptions during a hint. */
static int propagate(const SherlockPuzzle *puzzle, uint8_t domains[36]) {
    int changed;
    unsigned i, row, subset, item, column;
    do {
        changed = 0;
        for (i = 0; i < 36; ++i) if (!domains[i]) return 0;
        for (row = 0; row < 6; ++row) {
            for (subset = 1; subset < 64; ++subset) {
                uint8_t places = 0;
                unsigned count = bits((uint8_t)subset);
                for (item = 0; item < 6; ++item)
                    if (subset & (1u << item)) places |= domains[row * 6 + item];
                if (bits(places) < count) return 0;
                if (bits(places) != count) continue;
                for (item = 0; item < 6; ++item) if (!(subset & (1u << item))) {
                    unsigned object = row * 6 + item;
                    uint8_t old = domains[object];
                    domains[object] &= (uint8_t)~places;
                    if (!domains[object]) return 0;
                    if (domains[object] != old) changed = 1;
                }
            }
        }
        for (i = 0; i < puzzle->clue_count; ++i) {
            const SherlockClue *clue = &puzzle->clues[i];
            unsigned k, objects[3] = { clue->a, clue->b, clue->c };
            if (clue->type == 7) continue;
            for (k = 0; k < clue_arity(clue); ++k) {
                unsigned object = objects[k];
                if (object >= 36) return 0;
                for (column = 0; column < 6; ++column)
                    if ((domains[object] & (1u << column)) &&
                        !has_support(clue, domains, object, column)) {
                        domains[object] &= (uint8_t)~(1u << column);
                        changed = 1;
                    }
                if (!domains[object]) return 0;
            }
        }
    } while (changed);
    return 1;
}

/* 1: at least one completion; 0: proven impossible; -1: budget exhausted. */
static int satisfiable(const SherlockPuzzle *puzzle, uint8_t domains[36],
                       unsigned *budget) {
    unsigned object = 36, smallest = 7, i, column;
    int unknown = 0;
    if (!*budget) return -1;
    --*budget;
    if (!propagate(puzzle, domains)) return 0;
    for (i = 0; i < 36; ++i) {
        unsigned count = bits(domains[i]);
        if (count > 1 && count < smallest) { object = i; smallest = count; }
    }
    if (object == 36) return 1;
    for (column = 0; column < 6; ++column) {
        uint8_t child[36];
        int result;
        if (!(domains[object] & (1u << column))) continue;
        memcpy(child, domains, sizeof child);
        child[object] = (uint8_t)(1u << column);
        result = satisfiable(puzzle, child, budget);
        if (result == 1) return 1;
        if (result < 0) unknown = 1;
    }
    return unknown ? -1 : 0;
}

enum SHConstraintStatus sh_check_candidates(const SherlockPuzzle *puzzle,
    const uint8_t candidates[SH_SIZE][SH_SIZE], unsigned *remaining_nodes) {
    uint8_t domains[36] = { 0 };
    unsigned row, column, item, i;
    if (!puzzle || !candidates || !remaining_nodes ||
        puzzle->clue_count > SH_CLUE_CAPACITY) return SH_CONSTRAINT_INVALID;
    for (row = 0; row < SH_SIZE; ++row)
        for (column = 0; column < SH_SIZE; ++column) {
            int given = puzzle->given[row][column];
            if (given < -1 || given >= SH_SIZE ||
                (candidates[row][column] & (uint8_t)~63u))
                return SH_CONSTRAINT_INVALID;
        }
    for (i = 0; i < puzzle->clue_count; ++i) {
        const SherlockClue *clue = &puzzle->clues[i];
        if (clue->type > SHERLOCK_UNUSED || clue->a >= 36 ||
            (clue->type != SHERLOCK_UNUSED && clue->b >= 36) ||
            ((clue->type == SHERLOCK_BETWEEN ||
              clue->type == SHERLOCK_NOT_BETWEEN) && clue->c >= 36))
            return SH_CONSTRAINT_INVALID;
    }
    for (row = 0; row < SH_SIZE; ++row)
        for (column = 0; column < SH_SIZE; ++column)
            for (item = 0; item < SH_SIZE; ++item)
                if (candidates[row][column] & (1u << item))
                    domains[row * SH_SIZE + item] |= (uint8_t)(1u << column);
    for (row = 0; row < SH_SIZE; ++row)
        for (column = 0; column < SH_SIZE; ++column) {
            int given = puzzle->given[row][column];
            if (given >= 0)
                domains[row * SH_SIZE + (unsigned)given] &=
                    (uint8_t)(1u << column);
        }
    return (enum SHConstraintStatus)satisfiable(puzzle, domains, remaining_nodes);
}

static void hint_at(SHHint *hint, enum SHHintKind kind, unsigned object,
                    unsigned column, int clue, const char *reason) {
    hint->kind = kind;
    hint->row = (uint8_t)(object / 6);
    hint->item = (uint8_t)(object % 6);
    hint->column = (uint8_t)column;
    hint->clue_index = (int16_t)clue;
    snprintf(hint->explanation, sizeof hint->explanation,
             "%s\nRow %u, column %u, item %u.", reason,
             object / 6 + 1, column + 1, object % 6 + 1);
}

/* Recovered local ordering for the two vertical relations and LEFT_OF. The
 * original inspects columns before directions, and can choose a SAME partner
 * immediately. Keep these choices separate from the stronger native fallback.
 * No stored answer or inferred completion is consulted here. */
static int ordered_clue_hint(const SherlockGame *game, unsigned index,
                              const uint8_t domains[36], SHHint *hint) {
    const SherlockClue *clue = &game->puzzle.clues[index];
    unsigned a = clue->a, b = clue->b, column;
    if (clue->type == SHERLOCK_SAME_COLUMN ||
        clue->type == SHERLOCK_NOT_SAME_COLUMN) {
        uint8_t abit = (uint8_t)(1u << (a % 6));
        uint8_t bbit = (uint8_t)(1u << (b % 6));
        for (column = 0; column < SH_SIZE; ++column) {
            uint8_t amask = game->board.candidates[a / 6][column];
            uint8_t bmask = game->board.candidates[b / 6][column];
            if (clue->type == SHERLOCK_SAME_COLUMN) {
                if (amask == abit && (bmask & bbit) &&
                    game->board.chosen[b / 6][column] < 0) {
                    hint_at(hint, SH_HINT_CHOOSE, b, column, (int)index,
                            "The partner is in this column. These pictures share a column, so select this one here.");
                    return 1;
                }
                if (bmask == bbit && (amask & abit) &&
                    game->board.chosen[a / 6][column] < 0) {
                    hint_at(hint, SH_HINT_CHOOSE, a, column, (int)index,
                            "The partner is in this column. These pictures share a column, so select this one here.");
                    return 1;
                }
                if (!(amask & abit) && (bmask & bbit)) {
                    hint_at(hint, SH_HINT_REMOVE, b, column, (int)index,
                            "The partner is absent from this column. These pictures share a column, so remove this one here.");
                    return 1;
                }
                if (!(bmask & bbit) && (amask & abit)) {
                    hint_at(hint, SH_HINT_REMOVE, a, column, (int)index,
                            "The partner is absent from this column. These pictures share a column, so remove this one here.");
                    return 1;
                }
            } else {
                if (amask == abit && (bmask & bbit)) {
                    hint_at(hint, SH_HINT_REMOVE, b, column, (int)index,
                            "The partner is in this column. These pictures belong in different columns, so remove this one here.");
                    return 1;
                }
                if (bmask == bbit && (amask & abit)) {
                    hint_at(hint, SH_HINT_REMOVE, a, column, (int)index,
                            "The partner is in this column. These pictures belong in different columns, so remove this one here.");
                    return 1;
                }
            }
        }
    } else if (clue->type == SHERLOCK_LEFT_OF) {
        unsigned first_a = first_bit(domains[a]);
        unsigned last_b = SH_SIZE;
        for (column = 0; column <= first_a && column < SH_SIZE; ++column)
            if (domains[b] & (1u << column)) {
                hint_at(hint, SH_HINT_REMOVE, b, column, (int)index,
                        "This picture must be to the right of its partner, which has no possible column to its left here.");
                return 1;
            }
        while (last_b && !(domains[b] & (1u << (last_b - 1)))) --last_b;
        if (last_b) for (column = SH_SIZE; column-- > last_b - 1;)
            if (domains[a] & (1u << column)) {
                hint_at(hint, SH_HINT_REMOVE, a, column, (int)index,
                        "This picture must be to the left of its partner, which has no possible column to its right here.");
                return 1;
            }
    }
    return 0;
}

int sh_find_hint_in_bank(const SherlockGame *game, unsigned bank,
                         SHHint *hint, unsigned search_budget) {
    uint8_t domains[36], checked[36];
    unsigned row, column, i, group, slot, validation_budget = 0;
    static const char *reasons[7] = {
        "These items must share a column; this position has no matching partner.",
        "These items cannot share a column; this position has no legal partner.",
        "These items must occupy neighboring columns; this position cannot do so.",
        "These items must not be neighbors; this position would force adjacency.",
        "The first item must be left of the second; this position cannot satisfy that order.",
        "The middle item must have the other two as its immediate neighbors.",
        "The outer items must be two columns apart, with the named item absent from the middle."
    };
    if (!game || !hint || bank >= 2) return -1;
    memset(hint, 0, sizeof *hint);
    hint->clue_index = -1;
    if (game->outcome != SH_PLAYING) return 0;
    if (sh_check_candidates(&game->puzzle, game->board.candidates,
                            &validation_budget) == SH_CONSTRAINT_INVALID)
        return -1;
    visible_domains(game, domains);
    memcpy(checked, domains, sizeof checked);
    if (!propagate(&game->puzzle, checked)) {
        hint->kind = SH_HINT_CONTRADICTION;
        snprintf(hint->explanation, sizeof hint->explanation,
                 "The current possibilities contradict the clues or a row's six distinct items. Undo a deduction or restore a removed possibility.");
        return 0;
    }
    for (row = 0; row < 6; ++row) for (column = 0; column < 6; ++column) {
        uint8_t mask = game->board.candidates[row][column];
        if (game->board.chosen[row][column] < 0 && bits(mask) == 1) {
            hint_at(hint, SH_HINT_CHOOSE, row * 6 + first_bit(mask), column, -1,
                    "Only this item remains possible in this square. Select it.");
            return 1;
        }
    }
    for (i = 0; i < 36; ++i) if (bits(domains[i]) == 1) {
        column = first_bit(domains[i]);
        if (game->board.chosen[i / 6][column] < 0) {
            hint_at(hint, SH_HINT_CHOOSE, i, column, -1,
                    "This is the only remaining column for this item. Select it.");
            return 1;
        }
    }
    for (group = 0; group < 2; ++group)
      for (slot = 0; slot < (group ? SH_HORIZONTAL_SLOTS : SH_VERTICAL_SLOTS); ++slot) {
        int index = game->board.clue_slots[bank][group][slot];
        if (index < 0 || (unsigned)index >= game->puzzle.clue_count) continue;
        i = (unsigned)index;
        const SherlockClue *clue = &game->puzzle.clues[i];
        unsigned k, objects[3] = { clue->a, clue->b, clue->c };
        if (clue->type >= 7) continue;
        if (ordered_clue_hint(game, i, domains, hint)) return 1;
        for (k = 0; k < clue_arity(clue); ++k) {
            unsigned object = objects[k];
            for (column = 0; column < 6; ++column)
                if ((domains[object] & (1u << column)) &&
                    !has_support(clue, domains, object, column)) {
                    hint_at(hint, SH_HINT_REMOVE, object, column, (int)i,
                            reasons[clue->type]);
                    return 1;
                }
        }
    }
    /* A propagation chain or Hall set can prove an elimination even when no
     * individual visible clue can yet explain the complete chain in one step. */
    for (i = 0; i < 36; ++i) for (column = 0; column < 6; ++column)
        if ((domains[i] & (1u << column)) && !(checked[i] & (1u << column))) {
            hint_at(hint, SH_HINT_REMOVE, i, column, -1,
                    "Combining the clues with the rule that each row contains every item once rules out this position.");
            return 1;
        }
    if (search_budget) {
        int result;
        memcpy(checked, domains, sizeof checked);
        result = satisfiable(&game->puzzle, checked, &search_budget);
        if (!result) {
            hint->kind = SH_HINT_CONTRADICTION;
            snprintf(hint->explanation, sizeof hint->explanation,
                     "No completion satisfies the clues and your current possibilities. Undo a deduction or restore a candidate.");
            return 0;
        }
        if (result < 0) goto unresolved;
        for (i = 0; i < 36; ++i) {
            if (bits(domains[i]) <= 1) continue;
            for (column = 0; column < 6; ++column) {
                if (!(domains[i] & (1u << column))) continue;
                memcpy(checked, domains, sizeof checked);
                checked[i] = (uint8_t)(1u << column);
                result = satisfiable(&game->puzzle, checked, &search_budget);
                if (!result) {
                    hint_at(hint, SH_HINT_REMOVE, i, column, -1,
                            "Assuming this position leaves no possible completion under the clues. Remove it.");
                    return 1;
                }
                if (result < 0) goto unresolved;
            }
        }
    }
    hint->kind = SH_HINT_NONE;
    snprintf(hint->explanation, sizeof hint->explanation,
             "No forced deduction was found from the current possibilities and clues. No time penalty was charged.");
    return 0;
unresolved:
    hint->kind = SH_HINT_UNRESOLVED;
    snprintf(hint->explanation, sizeof hint->explanation,
             "The bounded logical search did not finish. No move or time penalty was applied.");
    return 0;
}

int sh_find_hint(const SherlockGame *game, SHHint *hint, unsigned search_budget) {
    return sh_find_hint_in_bank(game, 0, hint, search_budget);
}

int sh_request_hint_in_bank(SherlockGame *game, unsigned bank,
                            unsigned search_budget) {
    SHHint hint;
    int result;
    if (!game || bank >= 2) return -1;
    if (game->hint_pending || game->paused || game->outcome != SH_PLAYING) return 0;
    result = sh_find_hint_in_bank(game, bank, &hint, search_budget);
    game->pending_hint = hint;
    if (result != 1) return result;
    game->hint_pending = 1;
    /* Original caller charges after the modal applies its move and returns. */
    return 1;
}

int sh_request_hint(SherlockGame *game, unsigned search_budget) {
    return sh_request_hint_in_bank(game, 0, search_budget);
}

int sh_accept_hint(SherlockGame *game) {
    SHHint hint;
    int mutation = 0;
    if (!game) return -1;
    if (!game->hint_pending || game->outcome != SH_PLAYING) return 0;
    hint = game->pending_hint;
    game->hint_pending = 0;
    if (hint.kind == SH_HINT_REMOVE)
        mutation = sh_remove(game, hint.row, hint.column, hint.item);
    else if (hint.kind == SH_HINT_CHOOSE)
        mutation = sh_choose(game, hint.row, hint.column, hint.item);
    if (mutation == 1) {
        advance_elapsed(game, 30000);
        /* Original expiration is checked before completion after the modal.
         * This includes a hint that placed the board's final item. */
        if (game->limit_ms && game->elapsed_ms >= game->limit_ms)
            game->outcome = SH_TIMED_OUT;
    }
    return mutation;
}
