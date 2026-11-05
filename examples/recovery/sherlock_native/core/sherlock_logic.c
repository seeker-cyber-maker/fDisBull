/* Authored native constraint engine. No original code, table, emulator, or
 * third-party solver is required. The propagation rules reuse the row Hall-set
 * and clue-support approach already authored in sherlock_state.c. */
#include "sherlock_logic.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define OBJECTS 36u
#define ALL_COLUMNS 63u
#define MAX_TUPLES 40u
#define POOL_CAPACITY 8192u
#define GENERATOR_SOLVE_SLICE UINT64_C(20000)
#define MIN_GENERATED_CLUES 12u

typedef struct Constraint {
    uint8_t object[3], arity, count;
    uint8_t tuple[MAX_TUPLES][3];
} Constraint;

typedef struct Search {
    const SherlockPuzzle *puzzle;
    SherlockSolveResult *result;
    uint64_t budget;
    unsigned count;
    uint16_t degree[OBJECTS];
    Constraint constraint[SHERLOCK_MAX_CLUES];
    int exhausted, error;
} Search;

static unsigned bit_count(unsigned value) {
    value &= ALL_COLUMNS;
    value -= (value >> 1) & 0x55u;
    value = (value & 0x33u) + ((value >> 2) & 0x33u);
    return (value + (value >> 4)) & 15u;
}

static unsigned first_column(unsigned mask) {
    unsigned column = 0;
    while (column < 6 && !(mask & (1u << column))) ++column;
    return column;
}

static unsigned arity(unsigned type) {
    return type == SHERLOCK_BETWEEN || type == SHERLOCK_NOT_BETWEEN ? 3u : 2u;
}

int sherlock_relation_holds(unsigned type, int a, int b, int c) {
    int ab, ac;
    if (type == SHERLOCK_UNUSED) return 1;
    if (type > SHERLOCK_UNUSED || a < 0 || a >= 6 || b < 0 || b >= 6)
        return 0;
    if (arity(type) == 3 && (c < 0 || c >= 6)) return 0;
    ab = a > b ? a - b : b - a;
    ac = arity(type) == 3 ? (a > c ? a - c : c - a) : 0;
    switch (type) {
        case SHERLOCK_SAME_COLUMN: return a == b;
        case SHERLOCK_NOT_SAME_COLUMN: return a != b;
        case SHERLOCK_NEXT_TO: return ab == 1;
        case SHERLOCK_NOT_NEXT_TO: return ab != 1;
        case SHERLOCK_LEFT_OF: return a < b;
        case SHERLOCK_BETWEEN: return ac == 2 && 2 * b == a + c;
        case SHERLOCK_NOT_BETWEEN: return ac == 2 && 2 * b != a + c;
        default: return 0;
    }
}

/* Structural validation intentionally ignores number, display slots and the
 * stored solution. Duplicate/conflicting givens are logical UNSAT, not a schema
 * error. Unused fields of binary relations are immaterial. */
static int valid_puzzle(const SherlockPuzzle *puzzle, char reason[160]) {
    unsigned row, column, i;
    if (!puzzle) {
        snprintf(reason, 160, "No puzzle was supplied.");
        return 0;
    }
    if (puzzle->clue_count > SHERLOCK_MAX_CLUES) {
        snprintf(reason, 160, "The clue count exceeds the supported capacity.");
        return 0;
    }
    for (row = 0; row < 6; ++row) for (column = 0; column < 6; ++column) {
        int item = puzzle->given[row][column];
        if (item < -1 || item >= 6) {
            snprintf(reason, 160, "A given contains an invalid item index.");
            return 0;
        }
    }
    for (i = 0; i < puzzle->clue_count; ++i) {
        const SherlockClue *clue = &puzzle->clues[i];
        if (clue->type > SHERLOCK_UNUSED || clue->a >= OBJECTS ||
            (clue->type != SHERLOCK_UNUSED && clue->b >= OBJECTS) ||
            (arity(clue->type) == 3 && clue->c >= OBJECTS)) {
            snprintf(reason, 160, "Clue %u has an invalid relation or object reference.", i);
            return 0;
        }
    }
    return 1;
}

SherlockVerifyStatus sherlock_verify_answer(const SherlockPuzzle *puzzle,
                                           const uint8_t answer[6][6],
                                           SherlockVerifyResult *result) {
    SherlockVerifyResult local;
    uint8_t position[OBJECTS];
    unsigned row, column, i;
    if (!result) result = &local;
    memset(result, 0, sizeof *result);
    result->status = SH_VERIFY_ERROR;
    result->row = result->column = result->clue_index = -1;
    if (!valid_puzzle(puzzle, result->reason)) return result->status;
    if (!answer) {
        snprintf(result->reason, sizeof result->reason, "No complete answer was supplied.");
        return result->status;
    }
    result->status = SH_VERIFY_REJECTED;
    for (row = 0; row < 6; ++row) {
        unsigned seen = 0;
        for (column = 0; column < 6; ++column) {
            unsigned item = answer[row][column];
            if (item >= 6 || (seen & (1u << item))) {
                result->row = (int16_t)row;
                result->column = (int16_t)column;
                snprintf(result->reason, sizeof result->reason,
                         "Each row must contain all six item indices exactly once.");
                return result->status;
            }
            seen |= 1u << item;
            position[row * 6 + item] = (uint8_t)column;
        }
    }
    for (row = 0; row < 6; ++row) for (column = 0; column < 6; ++column) {
        int given = puzzle->given[row][column];
        if (given >= 0 && answer[row][column] != (unsigned)given) {
            result->row = (int16_t)row;
            result->column = (int16_t)column;
            snprintf(result->reason, sizeof result->reason,
                     "The answer disagrees with a given square.");
            return result->status;
        }
    }
    for (i = 0; i < puzzle->clue_count; ++i) {
        const SherlockClue *clue = &puzzle->clues[i];
        if (clue->type == SHERLOCK_UNUSED) continue;
        if (!sherlock_relation_holds(clue->type, position[clue->a],
                position[clue->b], arity(clue->type) == 3 ? position[clue->c] : 0)) {
            result->clue_index = (int16_t)i;
            snprintf(result->reason, sizeof result->reason,
                     "Clue %u does not hold for this answer.", i);
            return result->status;
        }
    }
    result->status = SH_VERIFY_ACCEPTED;
    snprintf(result->reason, sizeof result->reason,
             "All rows, givens, and clue relations are satisfied.");
    return result->status;
}

static int compatible(unsigned a, unsigned b, unsigned ca, unsigned cb) {
    if (a == b) return ca == cb;
    return a / 6 != b / 6 || ca != cb;
}

static void prepare_search(Search *search, const SherlockPuzzle *puzzle,
                           SherlockSolveResult *result, uint64_t budget) {
    unsigned i, a, b, c;
    memset(search, 0, sizeof *search);
    search->puzzle = puzzle;
    search->result = result;
    search->budget = budget;
    for (i = 0; i < puzzle->clue_count; ++i) {
        const SherlockClue *clue = &puzzle->clues[i];
        Constraint *constraint;
        if (clue->type == SHERLOCK_UNUSED) continue;
        constraint = &search->constraint[search->count++];
        constraint->object[0] = clue->a;
        constraint->object[1] = clue->b;
        constraint->object[2] = clue->c;
        constraint->arity = (uint8_t)arity(clue->type);
        ++search->degree[clue->a]; ++search->degree[clue->b];
        if (constraint->arity == 3) ++search->degree[clue->c];
        for (a = 0; a < 6; ++a) for (b = 0; b < 6; ++b) {
            if (!compatible(clue->a, clue->b, a, b)) continue;
            for (c = 0; c < (constraint->arity == 3 ? 6u : 1u); ++c) {
                if (constraint->arity == 3 &&
                    (!compatible(clue->a, clue->c, a, c) ||
                     !compatible(clue->b, clue->c, b, c))) continue;
                if (sherlock_relation_holds(clue->type, (int)a, (int)b, (int)c)) {
                    /* The seven six-column predicates admit at most 40 tuples. */
                    unsigned n = constraint->count++;
                    constraint->tuple[n][0] = (uint8_t)a;
                    constraint->tuple[n][1] = (uint8_t)b;
                    constraint->tuple[n][2] = (uint8_t)c;
                }
            }
        }
    }
}

/* Full Hall subsets are tiny for six items. Together with complete supported
 * tuple unions this is sound propagation; DFS supplies completeness. */
static int propagate(const Search *search, uint8_t domains[OBJECTS]) {
    int changed;
    unsigned i, row, subset, item;
    do {
        changed = 0;
        for (i = 0; i < OBJECTS; ++i) if (!domains[i]) return 0;
        for (row = 0; row < 6; ++row) {
            for (subset = 1; subset < 64; ++subset) {
                unsigned places = 0, count = bit_count(subset);
                for (item = 0; item < 6; ++item)
                    if (subset & (1u << item)) places |= domains[row * 6 + item];
                if (bit_count(places) < count) return 0;
                if (bit_count(places) != count) continue;
                for (item = 0; item < 6; ++item) if (!(subset & (1u << item))) {
                    unsigned object = row * 6 + item;
                    uint8_t old = domains[object];
                    domains[object] &= (uint8_t)~places;
                    if (!domains[object]) return 0;
                    changed |= domains[object] != old;
                }
            }
        }
        for (i = 0; i < search->count; ++i) {
            const Constraint *constraint = &search->constraint[i];
            unsigned tuple, k;
            uint8_t supported[3] = { 0, 0, 0 };
            for (tuple = 0; tuple < constraint->count; ++tuple) {
                for (k = 0; k < constraint->arity; ++k)
                    if (!(domains[constraint->object[k]] &
                          (1u << constraint->tuple[tuple][k]))) break;
                if (k < constraint->arity) continue;
                for (k = 0; k < constraint->arity; ++k)
                    supported[k] |= (uint8_t)(1u << constraint->tuple[tuple][k]);
            }
            for (k = 0; k < constraint->arity; ++k) {
                unsigned object = constraint->object[k];
                uint8_t old = domains[object];
                domains[object] &= supported[k];
                if (!domains[object]) return 0;
                changed |= old != domains[object];
            }
        }
    } while (changed);
    return 1;
}

static void count_solutions(Search *search, uint8_t domains[OBJECTS]) {
    unsigned object = OBJECTS, smallest = 7, degree = 0, i, column;
    SherlockSolveResult *result = search->result;
    if (result->solution_count >= 2 || search->error || search->exhausted) return;
    if (result->nodes == search->budget) { search->exhausted = 1; return; }
    ++result->nodes;
    if (!propagate(search, domains)) return;
    for (i = 0; i < OBJECTS; ++i) {
        unsigned count = bit_count(domains[i]);
        if (count > 1 && (count < smallest ||
            (count == smallest && search->degree[i] > degree))) {
            object = i; smallest = count; degree = search->degree[i];
        }
    }
    if (object == OBJECTS) {
        uint8_t answer[6][6];
        memset(answer, 255, sizeof answer);
        for (i = 0; i < OBJECTS; ++i)
            answer[i / 6][first_column(domains[i])] = (uint8_t)(i % 6);
        if (sherlock_verify_answer(search->puzzle,
                (const uint8_t (*)[6])answer, NULL) != SH_VERIFY_ACCEPTED) {
            search->error = 1;
            return;
        }
        if (!result->solution_count) memcpy(result->first_solution, answer, sizeof answer);
        else memcpy(result->second_solution, answer, sizeof answer);
        ++result->solution_count;
        return;
    }
    for (column = 0; column < 6; ++column) if (domains[object] & (1u << column)) {
        uint8_t child[OBJECTS];
        memcpy(child, domains, sizeof child);
        child[object] = (uint8_t)(1u << column);
        count_solutions(search, child);
        if (result->solution_count >= 2 || search->exhausted || search->error) return;
    }
}

SherlockSolveStatus sherlock_analyze(const SherlockPuzzle *puzzle,
                                     uint64_t node_budget,
                                     SherlockSolveResult *result) {
    Search search;
    uint8_t domains[OBJECTS];
    unsigned row, column;
    if (!result) return SH_SOLVE_ERROR;
    memset(result, 0, sizeof *result);
    result->status = SH_SOLVE_ERROR;
    if (!valid_puzzle(puzzle, result->reason)) return result->status;
    memset(domains, ALL_COLUMNS, sizeof domains);
    for (row = 0; row < 6; ++row) for (column = 0; column < 6; ++column) {
        int item = puzzle->given[row][column];
        if (item >= 0) domains[row * 6 + (unsigned)item] &= (uint8_t)(1u << column);
    }
    prepare_search(&search, puzzle, result, node_budget);
    count_solutions(&search, domains);
    if (search.error) {
        result->status = SH_SOLVE_ERROR;
        snprintf(result->reason, sizeof result->reason, "A solver completion failed independent answer validation.");
    } else if (result->solution_count >= 2) {
        result->status = SH_SOLVE_MULTIPLE;
        snprintf(result->reason, sizeof result->reason, "At least two distinct answers satisfy the visible constraints.");
    } else if (search.exhausted) {
        result->status = SH_SOLVE_UNKNOWN;
        snprintf(result->reason, sizeof result->reason, "The node budget expired before solution multiplicity was proved.");
    } else if (result->solution_count == 1) {
        result->status = SH_SOLVE_UNIQUE;
        snprintf(result->reason, sizeof result->reason, "Exactly one answer satisfies the visible constraints.");
    } else {
        result->status = SH_SOLVE_UNSAT;
        snprintf(result->reason, sizeof result->reason, "No answer satisfies all givens and clue relations.");
    }
    return result->status;
}

/* SplitMix64, using fixed-width unsigned wrap and no platform rand() state.
 * Modulo reduction, Fisher-Yates order, scoring and pruning order are part of
 * native generator version 1. This is not the historical DOS generator. */
static uint64_t random_word(uint64_t *state) {
    uint64_t value;
    *state += UINT64_C(0x9e3779b97f4a7c15);
    value = *state;
    value = (value ^ (value >> 30)) * UINT64_C(0xbf58476d1ce4e5b9);
    value = (value ^ (value >> 27)) * UINT64_C(0x94d049bb133111eb);
    return value ^ (value >> 31);
}

static unsigned random_below(uint64_t *state, unsigned bound) {
    return (unsigned)(random_word(state) % bound);
}

static void shuffle_bytes(uint8_t *values, unsigned count, uint64_t *state) {
    while (count > 1) {
        unsigned other = random_below(state, count);
        uint8_t value = values[count - 1];
        values[count - 1] = values[other]; values[other] = value;
        --count;
    }
}

static void positions(const uint8_t answer[6][6], uint8_t output[OBJECTS]) {
    unsigned row, column;
    for (row = 0; row < 6; ++row) for (column = 0; column < 6; ++column)
        output[row * 6 + answer[row][column]] = (uint8_t)column;
}

static int clue_holds(const SherlockClue *clue, const uint8_t position[OBJECTS]) {
    return sherlock_relation_holds(clue->type, position[clue->a],
        position[clue->b], arity(clue->type) == 3 ? position[clue->c] : 0);
}

static unsigned make_pool(SherlockClue *pool, const uint8_t position[OBJECTS]) {
    unsigned count = 0, a, b, c, type;
    for (a = 0; a < OBJECTS; ++a) for (b = a + 1; b < OBJECTS; ++b) {
        for (type = 0; type < 4; ++type) {
            if (type < 2 && a / 6 == b / 6) continue; /* Row tautologies. */
            if (sherlock_relation_holds(type, position[a], position[b], 0))
                pool[count++] = (SherlockClue){ (uint8_t)type, (uint8_t)a, (uint8_t)b, 255 };
        }
        if (position[a] < position[b])
            pool[count++] = (SherlockClue){ SHERLOCK_LEFT_OF, (uint8_t)a, (uint8_t)b, 255 };
        else if (position[b] < position[a])
            pool[count++] = (SherlockClue){ SHERLOCK_LEFT_OF, (uint8_t)b, (uint8_t)a, 255 };
    }
    for (a = 0; a < OBJECTS; ++a) for (c = a + 1; c < OBJECTS; ++c) {
        int distance = (int)position[a] - (int)position[c];
        if (distance != -2 && distance != 2) continue;
        for (b = 0; b < OBJECTS; ++b) {
            if (b == a || b == c) continue;
            type = position[b] * 2 == position[a] + position[c] ?
                   SHERLOCK_BETWEEN : SHERLOCK_NOT_BETWEEN;
            pool[count++] = (SherlockClue){ (uint8_t)type, (uint8_t)a, (uint8_t)b, (uint8_t)c };
        }
    }
    return count; /* For a six-by-six permutation board this is exactly 6606. */
}

void sherlock_default_generate_limits(SherlockGenerateLimits *limits) {
    if (!limits) return;
    limits->node_budget = SHERLOCK_DEFAULT_GENERATE_NODES;
    limits->max_attempts = SHERLOCK_DEFAULT_GENERATE_ATTEMPTS;
    limits->max_givens = SHERLOCK_DEFAULT_GENERATE_GIVENS;
}

static SherlockGenerateStatus generation_end(SherlockGenerateResult *result,
                                             SherlockGenerateStatus status,
                                             const char *reason) {
    result->status = status;
    snprintf(result->reason, sizeof result->reason, "%s", reason);
    return status;
}

static SherlockSolveStatus generation_solve(const SherlockPuzzle *puzzle,
                                            uint64_t *remaining,
                                            SherlockGenerateResult *generated,
                                            SherlockSolveResult *solved) {
    uint64_t slice = *remaining < GENERATOR_SOLVE_SLICE ? *remaining : GENERATOR_SOLVE_SLICE;
    SherlockSolveStatus status = sherlock_analyze(puzzle, slice, solved);
    *remaining -= solved->nodes;
    generated->nodes += solved->nodes;
    return status;
}

static void remove_clue(SherlockPuzzle *puzzle, unsigned index) {
    --puzzle->clue_count;
    memmove(&puzzle->clues[index], &puzzle->clues[index + 1],
            (puzzle->clue_count - index) * sizeof puzzle->clues[0]);
    memset(&puzzle->clues[puzzle->clue_count], 0, sizeof puzzle->clues[0]);
}

static void restore_clue(SherlockPuzzle *puzzle, unsigned index, SherlockClue clue) {
    memmove(&puzzle->clues[index + 1], &puzzle->clues[index],
            (puzzle->clue_count - index) * sizeof puzzle->clues[0]);
    puzzle->clues[index] = clue;
    ++puzzle->clue_count;
}

SherlockGenerateStatus sherlock_generate_random(uint64_t seed,
                                               const SherlockGenerateLimits *limits,
                                               SherlockPuzzle *out,
                                               SherlockGenerateResult *result) {
    SherlockGenerateLimits defaults;
    SherlockGenerateResult local;
    SherlockClue *pool;
    uint8_t active[POOL_CAPACITY];
    uint64_t random = seed ^ UINT64_C(0x534845524c4f434b), remaining;
    unsigned attempt;
    static const int information[7] = { 18, 2, 12, 4, 8, 22, 16 };
    if (!result) result = &local;
    memset(result, 0, sizeof *result);
    result->seed = seed; result->version = SHERLOCK_NATIVE_GENERATOR_VERSION;
    result->proof = SH_SOLVE_UNKNOWN;
    if (!limits) { sherlock_default_generate_limits(&defaults); limits = &defaults; }
    if (!out || limits->max_givens > 3 || limits->max_attempts > 64)
        return generation_end(result, SH_GENERATE_ERROR, "Invalid generation output or limits (at most 3 givens and 64 attempts).");
    if (!limits->node_budget || !limits->max_attempts)
        return generation_end(result, SH_GENERATE_EXHAUSTED, "The generation budget permits no work.");
    pool = (SherlockClue *)malloc(POOL_CAPACITY * sizeof *pool);
    if (!pool) return generation_end(result, SH_GENERATE_ERROR, "Unable to allocate the bounded clue pool.");
    remaining = limits->node_budget;
    for (attempt = 0; attempt < limits->max_attempts && remaining; ++attempt) {
        SherlockPuzzle puzzle;
        SherlockSolveResult solved;
        uint8_t target[6][6], target_position[OBJECTS];
        uint8_t rows[6] = { 0, 1, 2, 3, 4, 5 };
        unsigned pool_count, row, column, i, givens;
        unsigned group_count[2] = { 0, 0 }, type_count[7] = { 0, 0, 0, 0, 0, 0, 0 };
        int proved = 0;
        result->attempts = attempt + 1;
        memset(&puzzle, 0, sizeof puzzle);
        memset(puzzle.given, -1, sizeof puzzle.given);
        memset(puzzle.original_slot, 255, sizeof puzzle.original_slot);
        for (row = 0; row < 6; ++row) {
            for (column = 0; column < 6; ++column) target[row][column] = (uint8_t)column;
            shuffle_bytes(target[row], 6, &random);
        }
        positions((const uint8_t (*)[6])target, target_position);
        shuffle_bytes(rows, 6, &random);
        givens = limits->max_givens ? 1u + random_below(&random, limits->max_givens) : 0;
        for (i = 0; i < givens; ++i) {
            row = rows[i]; column = random_below(&random, 6);
            puzzle.given[row][column] = (int8_t)target[row][column];
        }
        pool_count = make_pool(pool, target_position);
        if (pool_count > POOL_CAPACITY) {
            free(pool);
            return generation_end(result, SH_GENERATE_ERROR, "The bounded clue pool overflowed.");
        }
        memset(active, 0, pool_count);
        for (;;) {
            SherlockSolveStatus status = generation_solve(&puzzle, &remaining, result, &solved);
            uint8_t alternative[2][OBJECTS];
            unsigned alternatives = 0;
            int best = -1, best_score = -10000;
            if (status == SH_SOLVE_ERROR || status == SH_SOLVE_UNSAT) {
                free(pool);
                return generation_end(result, SH_GENERATE_ERROR, "True target clues produced an inconsistent constraint problem.");
            }
            if (status == SH_SOLVE_UNIQUE && puzzle.clue_count >= MIN_GENERATED_CLUES) {
                proved = 1;
                break;
            }
            if (!remaining || puzzle.clue_count == 39) break;
            if (solved.solution_count && memcmp(solved.first_solution, target, sizeof target))
                positions((const uint8_t (*)[6])solved.first_solution, alternative[alternatives++]);
            if (solved.solution_count > 1 && memcmp(solved.second_solution, target, sizeof target))
                positions((const uint8_t (*)[6])solved.second_solution, alternative[alternatives++]);
            for (i = 0; i < pool_count; ++i) {
                const SherlockClue *clue = &pool[i];
                unsigned group = clue->type < 2 ? 0u : 1u, cuts = 0, j;
                int score;
                if (active[i] || group_count[group] == (group ? 21u : 18u)) continue;
                for (j = 0; j < alternatives; ++j) cuts += !clue_holds(clue, alternative[j]);
                if (alternatives && !cuts) continue;
                score = (int)(128 * cuts) + (!type_count[clue->type] ? 32 : 0) +
                        information[clue->type] - (int)(2 * type_count[clue->type]) +
                        (int)random_below(&random, 16);
                if (score > best_score) { best = (int)i; best_score = score; }
            }
            if (best < 0) break;
            puzzle.clues[puzzle.clue_count++] = pool[best];
            active[best] = 1;
            ++type_count[pool[best].type];
            ++group_count[pool[best].type < 2 ? 0 : 1];
        }
        if (!proved) continue;
        /* Deterministic bounded redundancy removal. UNKNOWN never permits a
         * removal. Exhausting the total budget returns no puzzle, so a smaller
         * resource budget cannot silently produce a different successful seed. */
        for (i = puzzle.clue_count; i > 0 && puzzle.clue_count > MIN_GENERATED_CLUES; --i) {
            unsigned index = i - 1;
            SherlockClue saved = puzzle.clues[index];
            SherlockSolveStatus status;
            uint64_t available = remaining;
            remove_clue(&puzzle, index);
            status = generation_solve(&puzzle, &remaining, result, &solved);
            if (status != SH_SOLVE_UNIQUE) restore_clue(&puzzle, index, saved);
            if (status == SH_SOLVE_UNKNOWN && available < GENERATOR_SOLVE_SLICE) {
                free(pool);
                return generation_end(result, SH_GENERATE_EXHAUSTED,
                                      "The total solver-node budget expired during clue pruning; no puzzle was returned.");
            }
            if (status == SH_SOLVE_ERROR || status == SH_SOLVE_UNSAT) {
                free(pool);
                return generation_end(result, SH_GENERATE_ERROR, "Removing a clue violated the known satisfiable target.");
            }
        }
        for (row = 0; row < 6; ++row) for (column = 0; column < 6; ++column) {
            int8_t saved = puzzle.given[row][column];
            SherlockSolveStatus status;
            uint64_t available = remaining;
            if (saved < 0) continue;
            puzzle.given[row][column] = -1;
            status = generation_solve(&puzzle, &remaining, result, &solved);
            if (status != SH_SOLVE_UNIQUE) puzzle.given[row][column] = saved;
            if (status == SH_SOLVE_UNKNOWN && available < GENERATOR_SOLVE_SLICE) {
                free(pool);
                return generation_end(result, SH_GENERATE_EXHAUSTED,
                                      "The total solver-node budget expired during given pruning; no puzzle was returned.");
            }
            if (status == SH_SOLVE_ERROR || status == SH_SOLVE_UNSAT) {
                free(pool);
                return generation_end(result, SH_GENERATE_ERROR, "Removing a given violated the known satisfiable target.");
            }
        }
        if (sherlock_verify_answer(&puzzle, (const uint8_t (*)[6])target, NULL) != SH_VERIFY_ACCEPTED) {
            free(pool);
            return generation_end(result, SH_GENERATE_ERROR, "The generated target failed answer validation.");
        }
        memcpy(puzzle.solution, target, sizeof target);
        group_count[0] = group_count[1] = 0;
        for (i = 0; i < puzzle.clue_count; ++i) {
            unsigned group = puzzle.clues[i].type < 2 ? 0u : 1u;
            puzzle.original_slot[i] = (uint8_t)((group ? 54u : 36u) + group_count[group]++);
        }
        /* Keep the public clue order in original-slot order for existing UIs. */
        for (i = 1; i < puzzle.clue_count; ++i) {
            SherlockClue clue = puzzle.clues[i];
            uint8_t slot = puzzle.original_slot[i];
            unsigned j = i;
            while (j && puzzle.original_slot[j - 1] > slot) {
                puzzle.clues[j] = puzzle.clues[j - 1];
                puzzle.original_slot[j] = puzzle.original_slot[j - 1];
                --j;
            }
            puzzle.clues[j] = clue; puzzle.original_slot[j] = slot;
        }
        result->given_count = 0;
        for (row = 0; row < 6; ++row) for (column = 0; column < 6; ++column)
            result->given_count += puzzle.given[row][column] >= 0;
        result->clue_count = puzzle.clue_count;
        result->proof = SH_SOLVE_UNIQUE;
        *out = puzzle;
        free(pool);
        return generation_end(result, SH_GENERATE_OK, "A unique native puzzle was proved from its visible constraints.");
    }
    free(pool);
    return generation_end(result, SH_GENERATE_EXHAUSTED,
                           remaining ? "The attempt limit was reached before a display-sized unique puzzle was proved." :
                                       "The total solver-node budget was exhausted; no puzzle was returned.");
}
