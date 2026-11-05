#ifndef SHERLOCK_VICTORY_H
#define SHERLOCK_VICTORY_H

/* Native movement model for the original Sherlock 1.50 celebration. This is
 * a bounded event iterator, not an emulator or a clock. The host supplies an
 * explicit RNG state, renders the events in order without clearing trails,
 * clips to its canvas, and chooses its presentation cadence. Original
 * post-puzzle RNG state and hardware pacing are separate adapter boundaries. */
#include <stdint.h>

#define SH_VICTORY_PARTICLES 16
#define SH_VICTORY_BURST_FRAMES 20

enum SHVictoryEventKind {
    SH_VICTORY_WAIT = 0,
    SH_VICTORY_CLEAR,
    SH_VICTORY_STAMP,
    SH_VICTORY_BURST,
    SH_VICTORY_DONE
};

typedef struct SHVictoryPoint {
    int16_t x, y;
} SHVictoryPoint;

typedef struct SHVictoryEvent {
    enum SHVictoryEventKind kind;
    uint8_t object; /* 0..35. CLEAR renders the empty full tile (36). */
    uint8_t frame;  /* BURST: 0..19; otherwise zero. */
    uint8_t count;  /* CLEAR/STAMP: 1, BURST: 16, WAIT/DONE: 0. */
    SHVictoryPoint points[SH_VICTORY_PARTICLES];
} SHVictoryEvent;

typedef struct SHVictory {
    uint64_t used;
    uint32_t rng_state;
    int16_t x, y, dx, dy;
    uint8_t object, completed_objects, phase, burst_frame, skip_requested;
} SHVictory;

void sh_victory_init(SHVictory *state, uint32_t rng_state);

/* Escape-style skip. A flight ends at its current advanced position, and its
 * complete burst is retained. Before any object has started, skip ends at once.
 * Requesting skip during a burst does not drop its remaining frames. */
void sh_victory_request_skip(SHVictory *state);

/* Returns one event; DONE is idempotent. Each call is bounded. Selection uses
 * at most 256 draws from the original RNG before returning WAIT, preserving
 * RNG state and retry order for the next call. A zero velocity yields repeated
 * identical STAMP events until skip, as in the original, without blocking the
 * caller. Null inputs return DONE without a mutation. */
enum SHVictoryEventKind sh_victory_next(SHVictory *state, SHVictoryEvent *event);

#endif
