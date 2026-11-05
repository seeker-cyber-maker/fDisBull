#include "../state/sherlock_victory.h"
#include <assert.h>
#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void first_object(void) {
    SHVictory state;
    SHVictoryEvent event;
    sh_victory_init(&state, 1);
    assert(sh_victory_next(&state, &event) == SH_VICTORY_CLEAR);
    assert(event.object == 5 && event.count == 1);
    assert(event.points[0].x == 282 && event.points[0].y == 19);
    assert(sh_victory_next(&state, &event) == SH_VICTORY_STAMP);
    assert(event.points[0].x == 282 && event.points[0].y == 19);
    assert(state.dx == 13 && state.dy == -14);
    assert(sh_victory_next(&state, &event) == SH_VICTORY_BURST);
    assert(event.frame == 0 && event.count == 16);
    for (unsigned i = 0; i < 16; ++i)
        assert(event.points[i].x == 295 && event.points[i].y == 5);
    assert(sh_victory_next(&state, &event) == SH_VICTORY_BURST);
    assert(event.frame == 1);
    assert(event.points[0].x == 304 && event.points[0].y == 5);
    assert(event.points[4].x == 295 && event.points[4].y == 14);
    assert(event.points[8].x == 286 && event.points[8].y == 5);
    assert(event.points[12].x == 295 && event.points[12].y == -4);
}

static void complete_trace(uint32_t seed, uint32_t expected_rng) {
    SHVictory state;
    SHVictoryEvent event;
    unsigned clears = 0, stamps = 0, bursts = 0, frame = 0, waits = 0;
    uint64_t seen = 0;
    int object = -1;
    sh_victory_init(&state, seed);
    for (unsigned step = 0; step < 100000; ++step) {
        enum SHVictoryEventKind kind = sh_victory_next(&state, &event);
        assert(kind == event.kind);
        if (kind == SH_VICTORY_DONE) {
            assert(event.count == 0);
            assert(clears == 36 && bursts == 36 * 20 && stamps >= 36);
            assert(seen == ((UINT64_C(1) << 36) - 1));
            assert(state.used == seen && state.completed_objects == 36);
            assert(state.rng_state == expected_rng);
            SHVictory retained = state;
            assert(sh_victory_next(&state, &event) == SH_VICTORY_DONE);
            assert(memcmp(&state, &retained, sizeof(state)) == 0);
            printf("victory seed %" PRIu32 ": 36 objects, %u full stamps, %u burst frames, %u waits\n",
                   seed, stamps, bursts, waits);
            return;
        }
        if (kind == SH_VICTORY_WAIT) {
            assert(event.count == 0); ++waits; continue;
        }
        assert(event.object < 36);
        if (kind == SH_VICTORY_CLEAR) {
            assert(object < 0 || frame == 20);
            assert(!(seen & (UINT64_C(1) << event.object)));
            seen |= UINT64_C(1) << event.object;
            assert(event.count == 1);
            assert(event.points[0].x == (event.object % 6) * 52 + 22);
            assert(event.points[0].y == (event.object / 6) * 32 + 19);
            object = event.object; frame = 0; ++clears;
        } else if (kind == SH_VICTORY_STAMP) {
            assert(event.object == object && event.count == 1 && frame == 0);
            ++stamps;
        } else {
            assert(kind == SH_VICTORY_BURST && event.object == object);
            assert(event.count == 16 && event.frame == frame && frame < 20);
            /* Opposite particles stay symmetric about the burst origin. */
            for (unsigned i = 0; i < 8; ++i) {
                assert(event.points[i].x + event.points[i + 8].x == 2 * state.x);
                assert(event.points[i].y + event.points[i + 8].y == 2 * state.y);
            }
            ++frame; ++bursts;
        }
    }
    assert(!"finite trace did not finish within the test bound");
}

static void zero_velocity_and_skip(void) {
    SHVictory state;
    SHVictoryEvent event;
    sh_victory_init(&state, 1084);
    assert(sh_victory_next(&state, &event) == SH_VICTORY_CLEAR);
    assert(event.object == 14);
    for (unsigned i = 0; i < 2000; ++i) {
        assert(sh_victory_next(&state, &event) == SH_VICTORY_STAMP);
        assert(event.points[0].x == 126 && event.points[0].y == 83);
        assert(state.dx == 0 && state.dy == 0);
    }
    sh_victory_request_skip(&state);
    for (unsigned frame = 0; frame < 20; ++frame) {
        assert(sh_victory_next(&state, &event) == SH_VICTORY_BURST);
        assert(event.frame == frame && event.object == 14);
    }
    assert(sh_victory_next(&state, &event) == SH_VICTORY_DONE);
    assert(state.completed_objects == 1 && state.rng_state == UINT32_C(1318074625));

    sh_victory_init(&state, 1);
    sh_victory_request_skip(&state);
    assert(sh_victory_next(&state, &event) == SH_VICTORY_DONE);
    assert(state.rng_state == 1 && state.completed_objects == 0);

    sh_victory_init(&state, 1);
    assert(sh_victory_next(&state, &event) == SH_VICTORY_CLEAR);
    sh_victory_request_skip(&state);
    assert(sh_victory_next(&state, &event) == SH_VICTORY_STAMP);
    for (unsigned i = 0; i < 20; ++i)
        assert(sh_victory_next(&state, &event) == SH_VICTORY_BURST);
    assert(sh_victory_next(&state, &event) == SH_VICTORY_DONE);

    sh_victory_init(&state, 1);
    assert(sh_victory_next(&state, &event) == SH_VICTORY_CLEAR);
    assert(sh_victory_next(&state, &event) == SH_VICTORY_STAMP);
    for (unsigned i = 0; i < 7; ++i)
        assert(sh_victory_next(&state, &event) == SH_VICTORY_BURST);
    sh_victory_request_skip(&state);
    for (unsigned i = 7; i < 20; ++i) {
        assert(sh_victory_next(&state, &event) == SH_VICTORY_BURST);
        assert(event.frame == i);
    }
    assert(sh_victory_next(&state, &event) == SH_VICTORY_DONE);
    assert(state.completed_objects == 1);
}

static void bounded_selection(void) {
    SHVictory state;
    SHVictoryEvent event;
    sh_victory_init(&state, 59);
    /* Authored retained-state boundary: only object 35 remains. This does not
     * claim that this initial used/RNG combination was observed in a game. */
    state.used = (UINT64_C(1) << 35) - 1;
    state.completed_objects = 35;
    assert(sh_victory_next(&state, &event) == SH_VICTORY_WAIT);
    assert(event.count == 0 && state.rng_state == UINT32_C(890619195));
    assert(sh_victory_next(&state, &event) == SH_VICTORY_CLEAR);
    assert(event.object == 35);
    SHVictory retained = state;
    assert(sh_victory_next(&state, NULL) == SH_VICTORY_DONE);
    assert(memcmp(&state, &retained, sizeof(state)) == 0);
    assert(sh_victory_next(NULL, &event) == SH_VICTORY_DONE);
    sh_victory_init(NULL, 0);
    sh_victory_request_skip(NULL);
}

/* Research-only trace mode. It emits semantic coordinates, never image bytes,
 * and is not a command of the game or agent-facing product CLI. */
static int trace(uint32_t seed, unsigned skip_after) {
    SHVictory state;
    SHVictoryEvent event;
    unsigned stamps = 0;
    sh_victory_init(&state, seed);
    for (unsigned step = 0; step < 100000; ++step) {
        enum SHVictoryEventKind kind = sh_victory_next(&state, &event);
        if (kind == SH_VICTORY_WAIT) continue;
        if (kind == SH_VICTORY_DONE) {
            printf("{\"done\":true,\"rng_state\":%" PRIu32 ",\"completed_objects\":%u}\n",
                   state.rng_state, state.completed_objects);
            return 0;
        }
        printf("{\"kind\":%u,\"object\":%u,\"frame\":%u,\"points\":[",
               (unsigned)kind, event.object, event.frame);
        for (unsigned i = 0; i < event.count; ++i)
            printf("%s[%d,%d]", i ? "," : "", event.points[i].x, event.points[i].y);
        puts("]}");
        if (kind == SH_VICTORY_STAMP && ++stamps == skip_after)
            sh_victory_request_skip(&state);
    }
    fputs("victory trace reached its event bound before DONE\n", stderr);
    return 1;
}

int main(int argc, char **argv) {
    if ((argc == 3 || argc == 4) && strcmp(argv[1], "--trace") == 0) {
        char *end = NULL;
        errno = 0;
        unsigned long long seed = strtoull(argv[2], &end, 10);
        if (errno || !end || end == argv[2] || *end || seed > UINT32_MAX || argv[2][0] == '-') return 2;
        unsigned skip = 0;
        if (argc == 4) {
            errno = 0;
            unsigned long long value = strtoull(argv[3], &end, 10);
            if (errno || !end || end == argv[3] || *end || value > 100000 || argv[3][0] == '-') return 2;
            skip = (unsigned)value;
        }
        return trace((uint32_t)seed, skip);
    }
    if (argc != 1) return 2;
    first_object();
    complete_trace(0, UINT32_C(2265435678));
    complete_trace(1, UINT32_C(2491506719));
    complete_trace(42, UINT32_C(2321247904));
    complete_trace(UINT32_MAX, UINT32_C(2464398919));
    complete_trace(UINT32_C(2147483648), UINT32_C(117952030));
    complete_trace(65535, UINT32_C(2004121289));
    complete_trace(235, UINT32_C(2426173990));
    complete_trace(11656, UINT32_C(3389086290));
    zero_velocity_and_skip();
    bounded_selection();
    puts("victory tests passed: original semantic witnesses, full traces, zero velocity, skips, bounded selection");
    return 0;
}
