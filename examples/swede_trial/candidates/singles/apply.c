#include "abi.h"

ApplyResult apply(uint16_t score, uint16_t points)
{
    const uint16_t total = (uint16_t)(score + points);
    ApplyResult result;
    result.next_score = total > 10u ? 10u : total;
    result.won = result.next_score == 10u;
    return result;
}
