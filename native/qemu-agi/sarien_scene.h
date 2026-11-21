/*
 * Bounded scene primitives adapted from Sarien.
 * Copyright (C) 1999-2003 Stuart George and Claudio Matsuoka.
 * Adaptation: fDisBull contributors, 2026-11-21.
 *
 * Sarien grants redistribution and modification under the GNU General Public
 * License; this adaptation elects version 2. See COPYING.sarien.txt and
 * SARIEN_PROVENANCE.md for the original notice and exact source provenance.
 * Distributed without warranty, including merchantability or fitness for a
 * particular purpose. This file is licensed under GPL-2.0-only.
 */

#ifndef FDISBULL_SARIEN_SCENE_H
#define FDISBULL_SARIEN_SCENE_H

#include <stddef.h>
#include <stdint.h>

#define AGI_SCENE_WIDTH 160u
#define AGI_SCENE_HEIGHT 168u
#define AGI_SCENE_PLANE_SIZE (AGI_SCENE_WIDTH * AGI_SCENE_HEIGHT)
#define AGI_SCENE_MAX_ACTORS 16u
#define AGI_SCENE_MAX_ATTEMPTS 1048576u

#define AGI_SCENE_ANIMATED 1u
#define AGI_SCENE_DRAWN 2u
#define AGI_SCENE_IGNORE_OBJECTS 4u
#define AGI_SCENE_IGNORE_BLOCKS 8u
#define AGI_SCENE_ON_WATER 16u
#define AGI_SCENE_ON_LAND 32u
#define AGI_SCENE_IGNORE_HORIZON 64u
#define AGI_SCENE_FIXED_PRIORITY 128u

#define AGI_SCENE_SUCCESS 0
#define AGI_SCENE_BUDGET_EXHAUSTED 1
#define AGI_SCENE_INVALID_INPUT 2

typedef struct AGISceneActor {
    int32_t id, x, y, prev_x, prev_y, width, height;
    uint32_t flags, priority;
} AGISceneActor;

typedef struct AGIScenePlacement {
    int32_t status, x, y;
    uint32_t priority, attempts, ego_trigger, ego_water;
} AGIScenePlacement;

typedef struct AGISceneBlit {
    uint32_t written_pixels, hidden;
} AGISceneBlit;

uint32_t agi_scene_abi_version(void);

/*
 * Read-only placement search in the Sarien AGI 2.x scope. Each evaluation,
 * including the initial position after horizon adjustment, consumes one
 * attempt. Success reports a resolved pose and target-ego flags. Exhaustion
 * reports the original x/y/priority, attempts used and zero ego flags.
 * Ordinary invalid input produces status 2 with all other output fields zero.
 * Null output or overlap of output with an input returns 2 without writing it.
 * All pointers must describe valid C objects of the declared accessible size.
 */
int agi_scene_place(const uint8_t *priority, size_t plane_size,
                    const uint8_t *bands, size_t bands_size, int32_t horizon,
                    const AGISceneActor *actors, size_t count,
                    uint32_t target_id, uint32_t max_attempts,
                    AGIScenePlacement *out);

/*
 * Composite one decoded, already oriented cel at an in-bounds baseline pose.
 * All palette/geometry validation completes before either plane is changed.
 * Visual and priority planes, cel and output must not overlap. Invalid input
 * leaves planes and output untouched and returns 2. On success, hidden is one
 * exactly when no nontransparent cel pixel passes the priority comparison.
 * This reports raster admission, not host presentation or a completed draw.
 */
int agi_scene_blit(uint8_t *visual, uint8_t *priority, size_t plane_size,
                   const uint8_t *cel, size_t cel_size, int32_t x,
                   int32_t baseline, uint32_t width, uint32_t height,
                   uint32_t transparent, uint32_t actor_priority,
                   AGISceneBlit *out);

#endif
