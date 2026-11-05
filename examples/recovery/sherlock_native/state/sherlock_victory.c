#include "sherlock_victory.h"
#include <string.h>

enum SHVictoryPhase { SELECT_OBJECT, FIRST_STAMP, FLIGHT, BURST, FINISHED };

/* Recovered semantic movement vectors; no image or executable bytes. */
static const int8_t burst_dx[SH_VICTORY_PARTICLES] = {
    9, 8, 6, 3, 0, -3, -6, -8, -9, -8, -6, -3, 0, 3, 6, 8
};
static const int8_t burst_dy[SH_VICTORY_PARTICLES] = {
    0, 3, 6, 8, 9, 8, 6, 3, 0, -3, -6, -8, -9, -8, -6, -3
};

static unsigned next_random(SHVictory *state) {
    state->rng_state = state->rng_state * UINT32_C(214013) + UINT32_C(2531011);
    return (state->rng_state >> 16) & UINT32_C(32767);
}

void sh_victory_init(SHVictory *state, uint32_t rng_state) {
    if (!state) return;
    memset(state, 0, sizeof(*state));
    state->rng_state = rng_state;
    state->object = UINT8_MAX;
}

void sh_victory_request_skip(SHVictory *state) {
    if (state) state->skip_requested = 1;
}

static enum SHVictoryEventKind stamp(SHVictory *state, SHVictoryEvent *event) {
    event->kind = SH_VICTORY_STAMP;
    event->object = state->object;
    event->count = 1;
    event->points[0] = (SHVictoryPoint){state->x, state->y};
    state->x = (int16_t)(state->x + state->dx);
    state->y = (int16_t)(state->y + state->dy);
    if (state->x <= 16 || state->x >= 624 || state->y <= 16 || state->y >= 334 ||
        state->skip_requested) {
        state->phase = BURST;
        state->burst_frame = 0;
    } else state->phase = FLIGHT;
    return event->kind;
}

static enum SHVictoryEventKind burst(SHVictory *state, SHVictoryEvent *event) {
    event->kind = SH_VICTORY_BURST;
    event->object = state->object;
    event->frame = state->burst_frame;
    event->count = SH_VICTORY_PARTICLES;
    for (unsigned i = 0; i < SH_VICTORY_PARTICLES; ++i) {
        event->points[i].x = (int16_t)(state->x + state->burst_frame * burst_dx[i]);
        event->points[i].y = (int16_t)(state->y + state->burst_frame * burst_dy[i]);
    }
    ++state->burst_frame;
    if (state->burst_frame == SH_VICTORY_BURST_FRAMES) {
        state->used |= UINT64_C(1) << state->object;
        ++state->completed_objects;
        state->phase = state->skip_requested || state->completed_objects == 36
                     ? FINISHED : SELECT_OBJECT;
    }
    return event->kind;
}

enum SHVictoryEventKind sh_victory_next(SHVictory *state, SHVictoryEvent *event) {
    if (!state || !event) return SH_VICTORY_DONE;
    memset(event, 0, sizeof(*event));
    event->object = UINT8_MAX;
    switch (state->phase) {
        case SELECT_OBJECT:
            if (state->skip_requested) {
                state->phase = FINISHED;
                event->kind = SH_VICTORY_DONE;
                return event->kind;
            }
            for (unsigned attempt = 0; attempt < 256; ++attempt) {
                unsigned object = next_random(state) % 36;
                if (state->used & (UINT64_C(1) << object)) continue;
                state->object = (uint8_t)object;
                state->x = (int16_t)((object % 6) * 52 + 22);
                state->y = (int16_t)((object / 6) * 32 + 19);
                state->phase = FIRST_STAMP;
                event->kind = SH_VICTORY_CLEAR;
                event->object = state->object;
                event->count = 1;
                event->points[0] = (SHVictoryPoint){state->x, state->y};
                return event->kind;
            }
            event->kind = SH_VICTORY_WAIT;
            return event->kind;
        case FIRST_STAMP:
            state->dx = (int16_t)(16 - (int)(next_random(state) % 32));
            state->dy = (int16_t)(16 - (int)(next_random(state) % 32));
            return stamp(state, event);
        case FLIGHT:
            if (state->skip_requested) {
                state->phase = BURST;
                state->burst_frame = 0;
                return burst(state, event);
            }
            return stamp(state, event);
        case BURST:
            return burst(state, event);
        default:
            event->kind = SH_VICTORY_DONE;
            return event->kind;
    }
}
