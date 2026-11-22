/* SPDX-License-Identifier: GPL-2.0-only
 * Portable actor/world semantics adapted from pinned Sarien; see
 * RUNTIME_ACTOR_PROVENANCE.md and COPYING.sarien.txt in native/qemu-agi.
 */
#ifndef FDISBULL_AGI_RUNTIME_ACTOR_H
#define FDISBULL_AGI_RUNTIME_ACTOR_H
#include <stddef.h>
#include <stdint.h>

#define AGI_RUNTIME_ACTORS 256u
#define AGI_RUNTIME_WIDTH 160u
#define AGI_RUNTIME_HEIGHT 168u
#define AGI_RUNTIME_PLANE_BYTES (AGI_RUNTIME_WIDTH * AGI_RUNTIME_HEIGHT)

enum AgiRuntimeActorFlag {
    AGI_RA_ANIMATED = 1u << 0, AGI_RA_DRAWN = 1u << 1,
    AGI_RA_UPDATE = 1u << 2, AGI_RA_CYCLING = 1u << 3,
    AGI_RA_IGNORE_HORIZON = 1u << 4, AGI_RA_IGNORE_OBJECTS = 1u << 5,
    AGI_RA_IGNORE_BLOCKS = 1u << 6, AGI_RA_ON_WATER = 1u << 7,
    AGI_RA_ON_LAND = 1u << 8, AGI_RA_FIXED_PRIORITY = 1u << 9,
    AGI_RA_FIXED_LOOP = 1u << 10, AGI_RA_UPDATE_POSITION = 1u << 11,
    AGI_RA_VIEW_REPLACED = 1u << 12, AGI_RA_DONT_UPDATE = 1u << 13,
    AGI_RA_DIDNT_MOVE = 1u << 14, AGI_RA_MOTION_ACTIVE = 1u << 15,
    AGI_RA_VIEW_BOUND = 1u << 16, AGI_RA_BLOCKED = 1u << 17
};
enum AgiRuntimeMotion { AGI_RM_NORMAL, AGI_RM_WANDER, AGI_RM_FOLLOW, AGI_RM_MOVE };
enum AgiRuntimeCycle { AGI_RC_NORMAL, AGI_RC_END, AGI_RC_REVERSE_LOOP, AGI_RC_REVERSE };
enum AgiRuntimeActorResult {
    AGI_RA_UNHANDLED = 0, AGI_RA_HANDLED = 1,
    AGI_RA_BAD_ARGUMENT = -1, AGI_RA_MISSING_VIEW = -2,
    AGI_RA_VIEW_NOT_LOADED = -3, AGI_RA_VIEW_UNBOUND = -4,
    AGI_RA_INVALID_LOOP = -5, AGI_RA_INVALID_CEL = -6,
    AGI_RA_EMPTY_LOOP = -7, AGI_RA_BAD_GEOMETRY = -8,
    AGI_RA_MISSING_PLANE = -9, AGI_RA_BAD_PLANE = -10,
    AGI_RA_NO_POSITION = -11, AGI_RA_MISSING_RANDOM = -12,
    AGI_RA_BAD_RANDOM = -13, AGI_RA_TICK_LIMIT = -14
};

typedef struct AgiRuntimeActor {
    int32_t x, y, prev_x, prev_y, target_x, target_y;
    uint32_t width, height, prev_width, prev_height;
    uint32_t view, loop, cel, loop_count, cel_count, priority, flags;
    uint32_t motion, cycle, direction;
    uint32_t step_size, step_time, step_time_count;
    uint32_t cycle_time, cycle_time_count;
    uint32_t motion_flag, cycle_flag, saved_step, follow_step, follow_count;
} AgiRuntimeActor;

typedef struct AgiRuntimeWorld {
    AgiRuntimeActor actors[AGI_RUNTIME_ACTORS];
    uint8_t loaded_views[256];
    uint8_t priority_bands[AGI_RUNTIME_HEIGHT];
    uint32_t horizon, block_active, player_control, priority_base;
    int32_t block_x1, block_y1, block_x2, block_y2;
    uint32_t rng_state;
    uint64_t ticks;
} AgiRuntimeWorld;

typedef struct AgiRuntimeGeometry {
    uint32_t loop_count, cel_count, width, height;
} AgiRuntimeGeometry;

typedef struct AgiRuntimeActorCallbacks {
    void *opaque;
    /* Return 1 for an existing VIEW, 0 if absent. Always give loop_count;
     * give cel_count for a valid loop, and dimensions for a valid cel.
     * Out-of-range loop/cel selections have zero unavailable fields. Pure. */
    int (*geometry)(void *opaque, uint8_t view, uint8_t loop, uint8_t cel,
                    AgiRuntimeGeometry *out);
    /* A complete immutable priority/control plane, values 0..15. Required
     * by draw, repaired placement and moving/drawn actors; never defaulted. */
    const uint8_t *priority;
    size_t priority_size;
    /* Return [0,upper_exclusive), modifying only *state. No global RNG or
     * wall clock. The transaction passes a private copy of world.rng_state. */
    uint32_t (*random)(void *opaque, uint32_t *state, uint32_t upper_exclusive);
} AgiRuntimeActorCallbacks;

void agi_runtime_world_init(AgiRuntimeWorld *world);
/* Read-only admission for pointer-free snapshots; same domains as commands. */
int agi_runtime_world_validate(const AgiRuntimeWorld *world);
/* Width-checked bytecode arguments. 33..91 and 147/148 are handled;
 * resource load/discard (30..32), inventory (92..) belong to the parent.
 * On a negative result, world/variables/flags are unchanged. Callbacks must
 * be pure except the supplied private RNG state. No renderer is dispatched. */
int agi_runtime_actor_command(AgiRuntimeWorld *world, uint32_t opcode,
                              const uint8_t *args, size_t argc,
                              uint8_t variables[256], uint8_t flags[256],
                              const AgiRuntimeActorCallbacks *callbacks);
/* Authentic interpreter ordering: prepare, execute LOGIC 0 (and its calls),
 * finish. Each phase commits atomically. The caller owns the cycle-active
 * guard: never prepare twice or mix tick with a prepared unfinished cycle.
 * prepare synchronizes ego/v6 and selects motion without incrementing ticks;
 * finish applies LOGIC's v6, cycles and positions, then increments ticks. */
int agi_runtime_actor_prepare(AgiRuntimeWorld *world, uint8_t variables[256],
                              uint8_t flags[256],
                              const AgiRuntimeActorCallbacks *callbacks);
int agi_runtime_actor_finish(AgiRuntimeWorld *world, uint8_t variables[256],
                             uint8_t flags[256],
                             const AgiRuntimeActorCallbacks *callbacks);
/* Advance exact logical ticks, at most 4096 per call. Cycles, motion,
 * collision and completion flags advance; no wall time or presentation.
 * A failed batch commits nothing, including RNG/tick state. */
int agi_runtime_actor_tick(AgiRuntimeWorld *world, uint32_t count,
                           uint8_t variables[256], uint8_t flags[256],
                           const AgiRuntimeActorCallbacks *callbacks);
const char *agi_runtime_actor_error(int result);
#endif
