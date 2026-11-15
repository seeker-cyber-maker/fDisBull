/* SPDX-License-Identifier: MIT
 * Copyright (c) 2026 fDisBull contributors
 */

#include <stdint.h>

#ifdef BLA_PROTECTED
#include "bla_shield.h"
#endif

/* The caller supplies writable uint64_t storage when a write is permitted. */
__declspec(dllexport) __declspec(noinline)
void bounded_core(uint64_t x, uint64_t limit, uint64_t *out)
{
#ifdef GUARD_MUTATION
    if (x >= limit) {
#else
    if (x > limit) {
#endif
        return;
    }

    *out = (x ^ UINT64_C(0x5a)) + UINT64_C(7);
}

__declspec(dllexport) __declspec(noinline)
void bounded_update(uint64_t x, uint64_t limit, uint64_t *out)
{
#ifdef BLA_PROTECTED
    (void)BLA_SHIELD_ANCHOR((uint32_t)x);
#endif

    bounded_core(x, limit, out);
}
