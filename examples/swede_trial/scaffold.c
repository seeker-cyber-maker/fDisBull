/* Fixed experiment transport, supplied by the coordinator. */
#include "abi.h"
#include <stdio.h>

int main(void) {
    int op, a, b;
    while (scanf("%d %d %d", &op, &a, &b) == 3) {
        switch (op) {
        case 0: printf("%u\n", (unsigned)normalize((int16_t)a)); break;
        case 1: printf("%u\n", (unsigned)award((uint16_t)a)); break;
#if TRIAL_MODE != 2
        case 2: {
            ApplyResult r = apply((uint16_t)a, (uint16_t)b);
            printf("%u %u\n", (unsigned)r.next_score, (unsigned)r.won);
            break;
        }
#endif
#if TRIAL_MODE == 2
        case 3: {
            PairResult r = pair((int16_t)a);
            printf("%u %u\n", (unsigned)r.count, (unsigned)r.points);
            break;
        }
#endif
#if TRIAL_MODE == 3
        case 4: {
            TurnResult r = turn((int16_t)a, (uint16_t)b);
            printf("%u %u %u %u\n", (unsigned)r.count, (unsigned)r.points,
                   (unsigned)r.next_score, (unsigned)r.won);
            break;
        }
#endif
        default: return 2;
        }
    }
    return ferror(stdin) ? 3 : 0;
}
