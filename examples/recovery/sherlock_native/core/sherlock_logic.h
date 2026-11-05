#ifndef SHERLOCK_LOGIC_H
#define SHERLOCK_LOGIC_H

#include <stdint.h>
#include "sherlock_core.h"

#ifdef __cplusplus
extern "C" {
#endif

#define SHERLOCK_NATIVE_GENERATOR_ID "sherlock-native-constraints"
#define SHERLOCK_NATIVE_GENERATOR_VERSION 1u
#define SHERLOCK_DEFAULT_SOLVE_NODES UINT64_C(200000)
#define SHERLOCK_DEFAULT_GENERATE_NODES UINT64_C(1000000)
#define SHERLOCK_DEFAULT_GENERATE_ATTEMPTS 16u
#define SHERLOCK_DEFAULT_GENERATE_GIVENS 3u

/* UNKNOWN is not UNSAT: the node budget expired before classification.
 * solution_count is capped at two and is only a lower bound for UNKNOWN.
 * Neither this operation nor answer verification reads puzzle.solution. */
typedef enum SherlockSolveStatus {
    SH_SOLVE_ERROR = -1,
    SH_SOLVE_UNSAT = 0,
    SH_SOLVE_UNIQUE = 1,
    SH_SOLVE_MULTIPLE = 2,
    SH_SOLVE_UNKNOWN = 3
} SherlockSolveStatus;

typedef struct SherlockSolveResult {
    SherlockSolveStatus status;
    uint32_t solution_count;
    uint64_t nodes;
    uint8_t first_solution[6][6];
    uint8_t second_solution[6][6];
    char reason[160];
} SherlockSolveResult;

SherlockSolveStatus sherlock_analyze(const SherlockPuzzle *puzzle,
                                     uint64_t node_budget,
                                     SherlockSolveResult *result);

typedef enum SherlockVerifyStatus {
    SH_VERIFY_ERROR = -1,
    SH_VERIFY_REJECTED = 0,
    SH_VERIFY_ACCEPTED = 1
} SherlockVerifyStatus;

typedef struct SherlockVerifyResult {
    SherlockVerifyStatus status;
    int16_t row, column, clue_index; /* -1 when not applicable. */
    char reason[160];
} SherlockVerifyResult;

/* result may be NULL. Answers contain within-row item IDs, 0..5. */
SherlockVerifyStatus sherlock_verify_answer(const SherlockPuzzle *puzzle,
                                           const uint8_t answer[6][6],
                                           SherlockVerifyResult *result);

/* Column-domain predicate shared by verifier, solver and visible-state hints. */
int sherlock_relation_holds(unsigned type, int a, int b, int c);

typedef struct SherlockGenerateLimits {
    uint64_t node_budget;      /* Total solver nodes across the generation. */
    uint32_t max_attempts;
    uint8_t max_givens;        /* 0..3; default is 3. */
} SherlockGenerateLimits;

typedef enum SherlockGenerateStatus {
    SH_GENERATE_ERROR = -1,
    SH_GENERATE_OK = 0,
    SH_GENERATE_EXHAUSTED = 1
} SherlockGenerateStatus;

typedef struct SherlockGenerateResult {
    SherlockGenerateStatus status;
    uint64_t seed;
    uint32_t version;
    uint32_t attempts;
    uint64_t nodes;
    uint16_t clue_count;
    uint8_t given_count;
    SherlockSolveStatus proof;
    char reason[160];
} SherlockGenerateResult;

void sherlock_default_generate_limits(SherlockGenerateLimits *limits);

/* Deterministic for (seed, version, limits). NULL limits selects defaults.
 * On success, out.solution holds the independently verified UNIQUE solution.
 * out.number is zero only as an unused compatibility field: callers MUST tag
 * this as a native generated puzzle using the full seed and generator version,
 * never as original numbered puzzle 0. No output puzzle is written on failure.
 * Original numbered-puzzle lookup remains sherlock_generate() in core.h. */
SherlockGenerateStatus sherlock_generate_random(uint64_t seed,
                                               const SherlockGenerateLimits *limits,
                                               SherlockPuzzle *out,
                                               SherlockGenerateResult *result);

#ifdef __cplusplus
}
#endif
#endif
