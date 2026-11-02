#include "abi.h"

uint16_t normalize(int16_t raw)
{
    if (raw < 0) {
        return 0u;
    }
    if (raw > 3) {
        return 3u;
    }
    return (uint16_t)raw;
}

uint16_t award(uint16_t count)
{
    const uint16_t bonus = count == 3u ? 1u : 0u;
    return (uint16_t)(2u * count + bonus);
}

ApplyResult apply(uint16_t score, uint16_t points)
{
    uint16_t next_score = (uint16_t)(score + points);
    if (next_score > 10u) {
        next_score = 10u;
    }
    return (ApplyResult){ .next_score = next_score, .won = next_score == 10u };
}

TurnResult turn(int16_t raw, uint16_t score)
{
    const uint16_t count = normalize(raw);
    const uint16_t points = award(count);
    const ApplyResult updated = apply(score, points);

    return (TurnResult){
        .count = count,
        .points = points,
        .next_score = updated.next_score,
        .won = updated.won
    };
}
