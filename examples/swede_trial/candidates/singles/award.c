#include "abi.h"

uint16_t award(uint16_t count)
{
    uint16_t points = (uint16_t)(2u * count);
    if (count == 3u) {
        ++points;
    }
    return points;
}
