/* Native logic tests are self-contained: no historical table, media, state
 * implementation, emulator, or third-party solver is linked. */
#include "../core/sherlock_logic.h"

#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>

#define ANSWER(a) ((const uint8_t (*)[6])(a))

static SherlockPuzzle empty_puzzle(void) {
    SherlockPuzzle puzzle;
    memset(&puzzle, 0, sizeof puzzle);
    memset(puzzle.given, -1, sizeof puzzle.given);
    memset(puzzle.solution, 255, sizeof puzzle.solution);
    memset(puzzle.original_slot, 255, sizeof puzzle.original_slot);
    return puzzle;
}

static void identity(uint8_t answer[6][6]) {
    unsigned row, column;
    for (row = 0; row < 6; ++row) for (column = 0; column < 6; ++column)
        answer[row][column] = (uint8_t)column;
}

static void fix_identity(SherlockPuzzle *puzzle) {
    unsigned row, column;
    for (row = 0; row < 6; ++row) for (column = 0; column < 6; ++column)
        puzzle->given[row][column] = (int8_t)column;
}

/* Deliberately separate equations form the small exhaustive test oracle. */
static int oracle_relation(unsigned type, int a, int b, int c) {
    switch (type) {
        case SHERLOCK_SAME_COLUMN: return a == b;
        case SHERLOCK_NOT_SAME_COLUMN: return a != b;
        case SHERLOCK_NEXT_TO: return a + 1 == b || b + 1 == a;
        case SHERLOCK_NOT_NEXT_TO: return a + 1 != b && b + 1 != a;
        case SHERLOCK_LEFT_OF: return a < b;
        case SHERLOCK_BETWEEN:
            return (a + 2 == c && b == a + 1) || (c + 2 == a && b == c + 1);
        case SHERLOCK_NOT_BETWEEN:
            return (a + 2 == c && b != a + 1) || (c + 2 == a && b != c + 1);
        case SHERLOCK_UNUSED: return 1;
        default: return 0;
    }
}

static int oracle_accepts(const SherlockPuzzle *puzzle, const uint8_t answer[6][6]) {
    unsigned row, column, i;
    uint8_t positions[36];
    for (row = 0; row < 6; ++row) {
        unsigned seen = 0;
        for (column = 0; column < 6; ++column) {
            unsigned item = answer[row][column];
            if (item >= 6 || (seen & (1u << item))) return 0;
            seen |= 1u << item;
            if (puzzle->given[row][column] >= 0 &&
                puzzle->given[row][column] != (int)item) return 0;
            positions[row * 6 + item] = (uint8_t)column;
        }
    }
    for (i = 0; i < puzzle->clue_count; ++i) {
        SherlockClue clue = puzzle->clues[i];
        int c = clue.type == SHERLOCK_BETWEEN || clue.type == SHERLOCK_NOT_BETWEEN ?
                positions[clue.c] : 0;
        if (clue.type == SHERLOCK_UNUSED) continue;
        if (!oracle_relation(clue.type, positions[clue.a], positions[clue.b], c)) return 0;
    }
    return 1;
}

static void predicate_contract(void) {
    unsigned type;
    int a, b, c;
    for (type = 0; type <= SHERLOCK_UNUSED; ++type)
        for (a = 0; a < 6; ++a) for (b = 0; b < 6; ++b) for (c = 0; c < 6; ++c)
            assert(sherlock_relation_holds(type, a, b, c) == oracle_relation(type, a, b, c));
    /* The unused third binary argument must not be evaluated arithmetically. */
    for (type = 0; type <= SHERLOCK_LEFT_OF; ++type)
        for (a = 0; a < 6; ++a) for (b = 0; b < 6; ++b) {
            assert(sherlock_relation_holds(type, a, b, INT_MIN) == oracle_relation(type, a, b, 0));
            assert(sherlock_relation_holds(type, a, b, INT_MAX) == oracle_relation(type, a, b, 0));
        }
    assert(!sherlock_relation_holds(SHERLOCK_NOT_BETWEEN, 0, 2, 4));
    assert(sherlock_relation_holds(SHERLOCK_NOT_BETWEEN, 0, 0, 2));
    assert(!sherlock_relation_holds(SHERLOCK_BETWEEN, 0, 1, INT_MIN));
    assert(!sherlock_relation_holds(SHERLOCK_SAME_COLUMN, INT_MIN, 0, 0));
    assert(!sherlock_relation_holds(8, 0, 0, 0));
}

static void verifier_contract(void) {
    static const SherlockClue true_clue[] = {
        { SHERLOCK_SAME_COLUMN, 0, 6, 255 },
        { SHERLOCK_NOT_SAME_COLUMN, 0, 7, 255 },
        { SHERLOCK_NEXT_TO, 0, 7, 255 },
        { SHERLOCK_NOT_NEXT_TO, 0, 8, 255 },
        { SHERLOCK_LEFT_OF, 0, 7, 255 },
        { SHERLOCK_BETWEEN, 0, 7, 14 },
        { SHERLOCK_NOT_BETWEEN, 0, 9, 14 }
    };
    static const SherlockClue false_clue[] = {
        { SHERLOCK_SAME_COLUMN, 0, 7, 255 },
        { SHERLOCK_NOT_SAME_COLUMN, 0, 6, 255 },
        { SHERLOCK_NEXT_TO, 0, 8, 255 },
        { SHERLOCK_NOT_NEXT_TO, 0, 7, 255 },
        { SHERLOCK_LEFT_OF, 1, 6, 255 },
        { SHERLOCK_BETWEEN, 0, 8, 14 },
        { SHERLOCK_NOT_BETWEEN, 0, 7, 14 }
    };
    SherlockPuzzle puzzle = empty_puzzle();
    SherlockVerifyResult result;
    uint8_t answer[6][6];
    unsigned type;
    identity(answer);
    assert(sherlock_verify_answer(&puzzle, ANSWER(answer), &result) == SH_VERIFY_ACCEPTED);
    assert(result.row == -1 && result.column == -1 && result.clue_index == -1);
    /* A different valid permutation is also accepted when the puzzle is ambiguous. */
    answer[0][0] = 1; answer[0][1] = 0;
    assert(sherlock_verify_answer(&puzzle, ANSWER(answer), NULL) == SH_VERIFY_ACCEPTED);
    puzzle.given[0][0] = 0;
    assert(sherlock_verify_answer(&puzzle, ANSWER(answer), &result) == SH_VERIFY_REJECTED);
    assert(result.row == 0 && result.column == 0);
    puzzle.given[0][0] = -1;
    identity(answer);
    answer[2][3] = 2;
    assert(sherlock_verify_answer(&puzzle, ANSWER(answer), &result) == SH_VERIFY_REJECTED);
    assert(result.row == 2 && result.column == 3);
    answer[2][3] = 255;
    assert(sherlock_verify_answer(&puzzle, ANSWER(answer), NULL) == SH_VERIFY_REJECTED);
    identity(answer);
    puzzle.clue_count = 1;
    for (type = 0; type < 7; ++type) {
        puzzle.clues[0] = true_clue[type];
        assert(sherlock_verify_answer(&puzzle, ANSWER(answer), NULL) == SH_VERIFY_ACCEPTED);
        puzzle.clues[0] = false_clue[type];
        assert(sherlock_verify_answer(&puzzle, ANSWER(answer), &result) == SH_VERIFY_REJECTED);
        assert(result.clue_index == 0);
    }
    puzzle.clues[0] = (SherlockClue){ SHERLOCK_UNUSED, 0, 255, 255 };
    assert(sherlock_verify_answer(&puzzle, ANSWER(answer), NULL) == SH_VERIFY_ACCEPTED);
    assert(sherlock_verify_answer(&puzzle, NULL, &result) == SH_VERIFY_ERROR);
    assert(sherlock_verify_answer(NULL, ANSWER(answer), &result) == SH_VERIFY_ERROR);
}

static void solve_classifications(void) {
    SherlockPuzzle puzzle = empty_puzzle();
    SherlockSolveResult result;
    uint8_t expected[6][6];
    identity(expected);
    assert(sherlock_analyze(NULL, 100, &result) == SH_SOLVE_ERROR);
    assert(sherlock_analyze(&puzzle, 100, NULL) == SH_SOLVE_ERROR);
    assert(sherlock_analyze(&puzzle, 100, &result) == SH_SOLVE_MULTIPLE);
    assert(result.solution_count == 2 && memcmp(result.first_solution, result.second_solution, 36));
    fix_identity(&puzzle);
    puzzle.given[5][0] = puzzle.given[5][1] = -1;
    assert(sherlock_analyze(&puzzle, 0, &result) == SH_SOLVE_UNKNOWN);
    assert(result.nodes == 0 && result.solution_count == 0);
    assert(sherlock_analyze(&puzzle, 1, &result) == SH_SOLVE_UNKNOWN);
    assert(result.nodes == 1 && result.solution_count == 0);
    assert(sherlock_analyze(&puzzle, 2, &result) == SH_SOLVE_UNKNOWN);
    assert(result.nodes == 2 && result.solution_count == 1);
    assert(sherlock_analyze(&puzzle, 3, &result) == SH_SOLVE_MULTIPLE);
    assert(result.nodes == 3 && result.solution_count == 2);
    puzzle.clue_count = 1;
    puzzle.clues[0] = (SherlockClue){ SHERLOCK_LEFT_OF, 30, 31, 255 };
    assert(sherlock_analyze(&puzzle, 1, &result) == SH_SOLVE_UNIQUE);
    assert(result.nodes == 1 && result.solution_count == 1);
    assert(!memcmp(result.first_solution, expected, 36));
    memset(puzzle.solution, 3, sizeof puzzle.solution);
    assert(sherlock_analyze(&puzzle, 1, &result) == SH_SOLVE_UNIQUE);
    assert(!memcmp(result.first_solution, expected, 36));
    puzzle.clues[0] = (SherlockClue){ SHERLOCK_SAME_COLUMN, 30, 31, 255 };
    assert(sherlock_analyze(&puzzle, 1, &result) == SH_SOLVE_UNSAT);
    assert(result.solution_count == 0);
    puzzle.clues[0] = (SherlockClue){ SHERLOCK_SAME_COLUMN, 30, 30, 255 };
    assert(sherlock_analyze(&puzzle, 3, &result) == SH_SOLVE_MULTIPLE);
    puzzle.clue_count = 0;
    puzzle.given[0][1] = 0;
    assert(sherlock_analyze(&puzzle, 1, &result) == SH_SOLVE_UNSAT);
    puzzle.given[0][1] = -2;
    assert(sherlock_analyze(&puzzle, 100, &result) == SH_SOLVE_ERROR);
    puzzle.given[0][1] = 6;
    assert(sherlock_analyze(&puzzle, 100, &result) == SH_SOLVE_ERROR);
    puzzle.given[0][1] = 1;
    puzzle.clue_count = SHERLOCK_MAX_CLUES + 1;
    assert(sherlock_analyze(&puzzle, 100, &result) == SH_SOLVE_ERROR);
    puzzle.clue_count = 1;
    puzzle.clues[0] = (SherlockClue){ 8, 0, 6, 255 };
    assert(sherlock_analyze(&puzzle, 100, &result) == SH_SOLVE_ERROR);
    puzzle.clues[0] = (SherlockClue){ SHERLOCK_BETWEEN, 0, 6, 36 };
    assert(sherlock_analyze(&puzzle, 100, &result) == SH_SOLVE_ERROR);
}

static uint32_t test_random(uint32_t *state) {
    *state = *state * UINT32_C(1664525) + UINT32_C(1013904223);
    return *state;
}

static void small_exhaustive_oracle(void) {
    static const uint8_t permutation[6][3] = {
        {0,1,2}, {0,2,1}, {1,0,2}, {1,2,0}, {2,0,1}, {2,1,0}
    };
    uint32_t random = UINT32_C(0x19e53b72);
    unsigned trial, classifications[3] = { 0, 0, 0 };
    for (trial = 0; trial < 240; ++trial) {
        SherlockPuzzle puzzle = empty_puzzle();
        SherlockSolveResult result;
        uint8_t answer[6][6], first[6][6];
        unsigned i, row, column, x, y, count = 0;
        identity(answer);
        fix_identity(&puzzle);
        for (row = 4; row < 6; ++row) for (column = 0; column < 3; ++column)
            puzzle.given[row][column] = -1;
        puzzle.clue_count = (uint16_t)(trial % 11);
        for (i = 0; i < puzzle.clue_count; ++i) {
            SherlockClue *clue = &puzzle.clues[i];
            clue->type = (uint8_t)(test_random(&random) % 8);
            clue->a = (uint8_t)(test_random(&random) % 36);
            clue->b = (uint8_t)(test_random(&random) % 36);
            clue->c = (uint8_t)(test_random(&random) % 36);
        }
        /* Include guaranteed unique fixtures among mixed random constraints. */
        if (trial % 17 == 0) {
            puzzle.clue_count = 4;
            puzzle.clues[0] = (SherlockClue){ SHERLOCK_LEFT_OF, 24, 25, 255 };
            puzzle.clues[1] = (SherlockClue){ SHERLOCK_LEFT_OF, 25, 26, 255 };
            puzzle.clues[2] = (SherlockClue){ SHERLOCK_LEFT_OF, 30, 31, 255 };
            puzzle.clues[3] = (SherlockClue){ SHERLOCK_LEFT_OF, 31, 32, 255 };
        }
        for (x = 0; x < 6; ++x) for (y = 0; y < 6; ++y) {
            memcpy(answer[4], permutation[x], 3);
            memcpy(answer[5], permutation[y], 3);
            if (oracle_accepts(&puzzle, ANSWER(answer))) {
                if (!count) memcpy(first, answer, sizeof first);
                ++count;
            }
        }
        assert(sherlock_analyze(&puzzle, 10000, &result) ==
               (count == 0 ? SH_SOLVE_UNSAT : count == 1 ? SH_SOLVE_UNIQUE : SH_SOLVE_MULTIPLE));
        assert(result.solution_count == (count < 2 ? count : 2));
        ++classifications[count < 2 ? count : 2];
        if (count) assert(oracle_accepts(&puzzle, ANSWER(result.first_solution)));
        if (count == 1) assert(!memcmp(first, result.first_solution, sizeof first));
        if (count > 1) {
            assert(oracle_accepts(&puzzle, ANSWER(result.second_solution)));
            assert(memcmp(result.first_solution, result.second_solution, 36));
        }
    }
    assert(classifications[0] && classifications[1] && classifications[2]);
    printf("Independent oracle: 240 fixtures x 36 completions; UNSAT=%u UNIQUE=%u MULTIPLE=%u.\n",
           classifications[0], classifications[1], classifications[2]);
}

/* Regression fingerprints pin version-1 semantics across future builds. These
 * are not the correctness oracle; independent equations and enumeration above
 * establish correctness. Encoding is explicit and excludes structure padding. */
static void fingerprint_byte(uint64_t *value, unsigned byte) {
    *value ^= (uint8_t)byte;
    *value *= UINT64_C(1099511628211);
}

static uint64_t puzzle_fingerprint(const SherlockPuzzle *puzzle) {
    uint64_t value = UINT64_C(14695981039346656037);
    unsigned row, column, i;
    fingerprint_byte(&value, puzzle->number);
    fingerprint_byte(&value, puzzle->number >> 8);
    for (row = 0; row < 6; ++row) for (column = 0; column < 6; ++column)
        fingerprint_byte(&value, puzzle->solution[row][column]);
    for (row = 0; row < 6; ++row) for (column = 0; column < 6; ++column)
        fingerprint_byte(&value, (uint8_t)puzzle->given[row][column]);
    fingerprint_byte(&value, puzzle->clue_count);
    fingerprint_byte(&value, puzzle->clue_count >> 8);
    for (i = 0; i < puzzle->clue_count; ++i) {
        fingerprint_byte(&value, puzzle->clues[i].type);
        fingerprint_byte(&value, puzzle->clues[i].a);
        fingerprint_byte(&value, puzzle->clues[i].b);
        fingerprint_byte(&value, puzzle->clues[i].c);
        fingerprint_byte(&value, puzzle->original_slot[i]);
    }
    return value;
}

static void generated_puzzles(void) {
    const uint64_t boundary_seed[] = { 0, 1, 235, 11656, 65535,
                                      UINT64_C(0x8000000000000000), UINT64_MAX };
    uint64_t total_nodes = 0;
    unsigned sample, minimum_clues = 256, maximum_clues = 0;
    for (sample = 0; sample < 48; ++sample) {
        uint64_t seed = sample < sizeof boundary_seed / sizeof boundary_seed[0] ?
                        boundary_seed[sample] : UINT64_C(0x9e3779b97f4a7c15) * sample;
        SherlockPuzzle puzzle, again, poisoned;
        SherlockGenerateResult generated, repeated;
        SherlockSolveResult solved;
        SherlockGenerateLimits limits;
        uint8_t altered[6][6];
        unsigned i, row, column, givens = 0, group[2] = { 0, 0 };
        assert(sherlock_generate_random(seed, NULL, &puzzle, &generated) == SH_GENERATE_OK);
        assert(generated.seed == seed && generated.version == SHERLOCK_NATIVE_GENERATOR_VERSION);
        assert(generated.proof == SH_SOLVE_UNIQUE && generated.nodes > 0);
        assert(generated.nodes <= SHERLOCK_DEFAULT_GENERATE_NODES);
        assert(generated.attempts > 0 && generated.attempts <= SHERLOCK_DEFAULT_GENERATE_ATTEMPTS);
        assert(generated.clue_count == puzzle.clue_count);
        assert(puzzle.number == 0 && puzzle.clue_count >= 12 && puzzle.clue_count <= 39);
        if (seed == 0) assert(puzzle_fingerprint(&puzzle) == UINT64_C(0x48cc1f507cce2027));
        if (seed == UINT64_MAX) assert(puzzle_fingerprint(&puzzle) == UINT64_C(0x0ca2ca2e7d9ccfa9));
        total_nodes += generated.nodes;
        if (puzzle.clue_count < minimum_clues) minimum_clues = puzzle.clue_count;
        if (puzzle.clue_count > maximum_clues) maximum_clues = puzzle.clue_count;
        for (row = 0; row < 6; ++row) for (column = 0; column < 6; ++column)
            givens += puzzle.given[row][column] >= 0;
        assert(givens <= 3 && givens == generated.given_count);
        for (i = 0; i < puzzle.clue_count; ++i) {
            unsigned orientation = puzzle.clues[i].type < 2 ? 0u : 1u;
            assert(puzzle.clues[i].type < SHERLOCK_UNUSED);
            assert(puzzle.original_slot[i] == (orientation ? 54 : 36) + group[orientation]++);
            if (i) assert(puzzle.original_slot[i] > puzzle.original_slot[i - 1]);
        }
        assert(group[0] <= 18 && group[1] <= 21);
        assert(oracle_accepts(&puzzle, ANSWER(puzzle.solution)));
        assert(sherlock_verify_answer(&puzzle, ANSWER(puzzle.solution), NULL) == SH_VERIFY_ACCEPTED);
        poisoned = puzzle;
        memset(poisoned.solution, 255, sizeof poisoned.solution);
        assert(sherlock_analyze(&poisoned, SHERLOCK_DEFAULT_SOLVE_NODES, &solved) == SH_SOLVE_UNIQUE);
        assert(solved.solution_count == 1 && !memcmp(solved.first_solution, puzzle.solution, 36));
        for (row = 0; row < 6; ++row) {
            memcpy(altered, puzzle.solution, sizeof altered);
            altered[row][0] = puzzle.solution[row][1];
            altered[row][1] = puzzle.solution[row][0];
            assert(!oracle_accepts(&poisoned, ANSWER(altered)));
            assert(sherlock_verify_answer(&poisoned, ANSWER(altered), NULL) == SH_VERIFY_REJECTED);
        }
        assert(sherlock_generate_random(seed, NULL, &again, &repeated) == SH_GENERATE_OK);
        assert(!memcmp(&again, &puzzle, sizeof puzzle));
        assert(repeated.nodes == generated.nodes && repeated.attempts == generated.attempts);
        if (sample < 7) {
            /* A resource limit may fail, but must not alter a successful seed.
             * Exactly enough nodes must succeed; one fewer must fail closed. */
            sherlock_default_generate_limits(&limits);
            limits.node_budget = generated.nodes;
            assert(sherlock_generate_random(seed, &limits, &again, &repeated) == SH_GENERATE_OK);
            assert(!memcmp(&again, &puzzle, sizeof puzzle));
            --limits.node_budget;
            memset(&again, 0xa5, sizeof again);
            poisoned = again;
            assert(sherlock_generate_random(seed, &limits, &again, &repeated) == SH_GENERATE_EXHAUSTED);
            assert(!memcmp(&again, &poisoned, sizeof again));
            assert(repeated.nodes <= limits.node_budget && repeated.proof != SH_SOLVE_UNIQUE);
        }
    }
    printf("Native generator: 48 seeds, each independently UNIQUE; clues=%u..%u, nodes=%llu; 288 permuted wrong answers rejected.\n",
           minimum_clues, maximum_clues, (unsigned long long)total_nodes);
}

static void generation_limits(void) {
    SherlockGenerateLimits limits;
    SherlockGenerateResult generated;
    SherlockSolveResult solved;
    SherlockPuzzle puzzle, unchanged;
    unsigned maximum, row, column;
    sherlock_default_generate_limits(NULL);
    sherlock_default_generate_limits(&limits);
    assert(limits.node_budget == SHERLOCK_DEFAULT_GENERATE_NODES);
    assert(limits.max_attempts == SHERLOCK_DEFAULT_GENERATE_ATTEMPTS);
    assert(limits.max_givens == 3);
    memset(&puzzle, 0xa5, sizeof puzzle);
    unchanged = puzzle;
    limits.node_budget = 0;
    assert(sherlock_generate_random(0, &limits, &puzzle, &generated) == SH_GENERATE_EXHAUSTED);
    assert(!memcmp(&puzzle, &unchanged, sizeof puzzle) && generated.nodes == 0);
    limits.node_budget = 1;
    assert(sherlock_generate_random(0, &limits, &puzzle, &generated) == SH_GENERATE_EXHAUSTED);
    assert(!memcmp(&puzzle, &unchanged, sizeof puzzle) && generated.nodes <= 1);
    limits.max_attempts = 0;
    assert(sherlock_generate_random(0, &limits, &puzzle, NULL) == SH_GENERATE_EXHAUSTED);
    limits.max_attempts = 65;
    assert(sherlock_generate_random(0, &limits, &puzzle, &generated) == SH_GENERATE_ERROR);
    sherlock_default_generate_limits(&limits);
    limits.max_givens = 4;
    assert(sherlock_generate_random(0, &limits, &puzzle, &generated) == SH_GENERATE_ERROR);
    assert(!memcmp(&puzzle, &unchanged, sizeof puzzle));
    assert(sherlock_generate_random(0, NULL, NULL, &generated) == SH_GENERATE_ERROR);
    for (maximum = 0; maximum <= 3; ++maximum) {
        unsigned givens = 0;
        sherlock_default_generate_limits(&limits);
        limits.max_givens = (uint8_t)maximum;
        assert(sherlock_generate_random(17, &limits, &puzzle, &generated) == SH_GENERATE_OK);
        for (row = 0; row < 6; ++row) for (column = 0; column < 6; ++column)
            givens += puzzle.given[row][column] >= 0;
        assert(givens <= maximum);
        assert(sherlock_analyze(&puzzle, SHERLOCK_DEFAULT_SOLVE_NODES, &solved) == SH_SOLVE_UNIQUE);
    }
}

int main(void) {
    predicate_contract();
    verifier_contract();
    solve_classifications();
    small_exhaustive_oracle();
    generated_puzzles();
    generation_limits();
    puts("Native constraint solver, seeded generator, and independent answer verifier: PASS.");
    return 0;
}
