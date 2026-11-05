#ifndef SWEDE_TRIAL_ABI_H
#define SWEDE_TRIAL_ABI_H
#include <stdbool.h>
#include <stdint.h>

typedef struct { uint16_t next_score; bool won; } ApplyResult;
typedef struct { uint16_t count; uint16_t points; } PairResult;
typedef struct { uint16_t count; uint16_t points; uint16_t next_score; bool won; } TurnResult;

uint16_t normalize(int16_t raw);
uint16_t award(uint16_t count);
ApplyResult apply(uint16_t score, uint16_t points);
PairResult pair(int16_t raw);
TurnResult turn(int16_t raw, uint16_t score);
#endif
