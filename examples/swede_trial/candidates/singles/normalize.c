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
