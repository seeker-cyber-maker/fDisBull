#include "abi.h"

uint16_t normalize(int16_t raw)
{
    if (raw < 0) {
        return 0;
    }
    if (raw > 3) {
        return 3;
    }
    return (uint16_t)raw;
}

uint16_t award(uint16_t count)
{
    uint16_t points = (uint16_t)(2u * count);
    if (count == 3u) {
        points = (uint16_t)(points + 1u);
    }
    return points;
}

PairResult pair(int16_t raw)
{
    PairResult result;
    result.count = normalize(raw);
    result.points = award(result.count);
    return result;
}
