/*
 * Sarien - A Sierra AGI resource interpreter engine
 * Copyright (C) 1999-2003 Stuart George and Claudio Matsuoka.
 *
 * Original notice:
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; see docs/COPYING for further details.
 *
 * Modified by fDisBull contributors, 2026-11-21: reentrant, bounded AGI 2.x
 * placement and decoded-cel priority rasterization. This adaptation elects
 * GPL version 2; see COPYING.sarien.txt and SARIEN_PROVENANCE.md. Distributed
 * without warranty, including merchantability or fitness for a particular
 * purpose. SPDX-License-Identifier: GPL-2.0-only
 */

#include "sarien_scene.h"

#define AGI_SCENE_KNOWN_FLAGS 255u

uint32_t agi_scene_abi_version(void)
{
    return 1u;
}

/* Integer differences avoid pointer ordering/subtraction across C objects. */
static int overlaps(const void *a, size_t an, const void *b, size_t bn)
{
    uintptr_t ap, bp;

    if (a == NULL || b == NULL || an == 0u || bn == 0u) {
        return 0;
    }
    ap = (uintptr_t)a;
    bp = (uintptr_t)b;
    return ap <= bp ? bp - ap < an : ap - bp < bn;
}

static int palette_valid(const uint8_t *pixels, size_t size)
{
    size_t i;

    for (i = 0; i < size; i++) {
        if (pixels[i] > 15u) {
            return 0;
        }
    }
    return 1;
}

static int coordinate_valid(int32_t value)
{
    return value >= -32768 && value <= 32767;
}

static int geometry_valid(const AGISceneActor *actor, int positive)
{
    int32_t minimum = positive ? 1 : 0;

    return actor->width >= minimum && actor->width <= 160 &&
           actor->height >= minimum && actor->height <= 168;
}

/* Adapted from checks.c:check_position; the AGI 3.x workaround is excluded. */
static int check_position(const AGISceneActor *actor, int32_t horizon)
{
    return actor->x >= 0 && actor->x + actor->width <= 160 &&
           actor->y - actor->height + 1 >= 0 && actor->y < 168 &&
           ((actor->flags & AGI_SCENE_IGNORE_HORIZON) || actor->y > horizon);
}

/* Preserve Sarien's inclusive horizontal endpoints and baseline crossings. */
static int check_collision(const AGISceneActor *actor,
                           const AGISceneActor *actors, size_t count)
{
    size_t i;

    if (actor->flags & AGI_SCENE_IGNORE_OBJECTS) {
        return 0;
    }
    for (i = 0; i < count; i++) {
        const AGISceneActor *peer = &actors[i];

        if ((peer->flags & (AGI_SCENE_ANIMATED | AGI_SCENE_DRAWN)) !=
            (AGI_SCENE_ANIMATED | AGI_SCENE_DRAWN) ||
            (peer->flags & AGI_SCENE_IGNORE_OBJECTS) ||
            peer->id == actor->id) {
            continue;
        }
        if (actor->x + actor->width < peer->x ||
            actor->x > peer->x + peer->width) {
            continue;
        }
        if (actor->y == peer->y ||
            (actor->y > peer->y && actor->prev_y < peer->prev_y) ||
            (actor->y < peer->y && actor->prev_y > peer->prev_y)) {
            return 1;
        }
    }
    return 0;
}

/* Adapted from checks.c:check_priority. Call only after check_position. */
static int check_priority(AGISceneActor *actor, const uint8_t *priority,
                          const uint8_t *bands, uint32_t *trigger,
                          uint32_t *water)
{
    int32_t i;
    int pass = 1;
    size_t offset = (size_t)actor->y * AGI_SCENE_WIDTH + (size_t)actor->x;

    if (!(actor->flags & AGI_SCENE_FIXED_PRIORITY)) {
        actor->priority = bands[actor->y];
    }
    *trigger = 0u;
    *water = 0u;
    if (actor->priority == 15u) {
        return 1;
    }
    *water = 1u;
    for (i = 0; i < actor->width; i++) {
        uint8_t value = priority[offset + (size_t)i];

        if (value == 0u) {
            pass = 0;
            break;
        }
        if (value == 3u) {
            continue;
        }
        *water = 0u;
        if (value == 1u) {
            if (actor->flags & AGI_SCENE_IGNORE_BLOCKS) {
                continue;
            }
            pass = 0;
            break;
        }
        if (value == 2u) {
            *trigger = 1u;
        }
    }
    if (pass && ((!*water && (actor->flags & AGI_SCENE_ON_WATER)) ||
                 (*water && (actor->flags & AGI_SCENE_ON_LAND)))) {
        pass = 0;
    }
    return pass;
}

int agi_scene_place(const uint8_t *priority, size_t plane_size,
                    const uint8_t *bands, size_t bands_size, int32_t horizon,
                    const AGISceneActor *actors, size_t count,
                    uint32_t target_id, uint32_t max_attempts,
                    AGIScenePlacement *out)
{
    AGIScenePlacement result = {AGI_SCENE_INVALID_INPUT, 0, 0, 0, 0, 0, 0};
    AGISceneActor candidate;
    size_t i, j, target = count;
    uint32_t direction = 0u, leg_size = 1u, remaining = 1u;
    uint32_t trigger = 0u, water = 0u;

    if (out == NULL || count > SIZE_MAX / sizeof(*actors)) {
        return AGI_SCENE_INVALID_INPUT;
    }
    if (overlaps(out, sizeof(*out), priority, plane_size) ||
        overlaps(out, sizeof(*out), bands, bands_size) ||
        overlaps(out, sizeof(*out), actors, count * sizeof(*actors))) {
        return AGI_SCENE_INVALID_INPUT;
    }
    if (priority == NULL || bands == NULL || actors == NULL ||
        plane_size != AGI_SCENE_PLANE_SIZE || bands_size != AGI_SCENE_HEIGHT ||
        horizon < 0 || horizon >= 168 || count == 0u ||
        count > AGI_SCENE_MAX_ACTORS || target_id > 255u ||
        max_attempts == 0u || max_attempts > AGI_SCENE_MAX_ATTEMPTS) {
        *out = result;
        return AGI_SCENE_INVALID_INPUT;
    }
    if (!palette_valid(priority, plane_size) || !palette_valid(bands, bands_size)) {
        *out = result;
        return AGI_SCENE_INVALID_INPUT;
    }
    for (i = 0; i < count; i++) {
        const AGISceneActor *actor = &actors[i];
        int active = (actor->flags & (AGI_SCENE_ANIMATED | AGI_SCENE_DRAWN)) ==
                     (AGI_SCENE_ANIMATED | AGI_SCENE_DRAWN);

        if (actor->id < 0 || actor->id > 255 ||
            !coordinate_valid(actor->x) || !coordinate_valid(actor->y) ||
            !coordinate_valid(actor->prev_x) || !coordinate_valid(actor->prev_y) ||
            (actor->flags & ~AGI_SCENE_KNOWN_FLAGS) || actor->priority > 15u ||
            !geometry_valid(actor, active || (uint32_t)actor->id == target_id)) {
            *out = result;
            return AGI_SCENE_INVALID_INPUT;
        }
        for (j = 0; j < i; j++) {
            if (actors[j].id == actor->id) {
                *out = result;
                return AGI_SCENE_INVALID_INPUT;
            }
        }
        if ((uint32_t)actor->id == target_id) {
            target = i;
        }
    }
    if (target == count) {
        *out = result;
        return AGI_SCENE_INVALID_INPUT;
    }

    candidate = actors[target];
    result.status = AGI_SCENE_BUDGET_EXHAUSTED;
    result.x = candidate.x;
    result.y = candidate.y;
    result.priority = candidate.priority;
    if (!(candidate.flags & AGI_SCENE_IGNORE_HORIZON) && candidate.y <= horizon) {
        candidate.y = horizon + 1;
    }
    /* Sarien's west/south/east/north expanding spiral, with a finite budget. */
    while (result.attempts < max_attempts) {
        result.attempts++;
        if (check_position(&candidate, horizon) &&
            !check_collision(&candidate, actors, count) &&
            check_priority(&candidate, priority, bands, &trigger, &water)) {
            result.status = AGI_SCENE_SUCCESS;
            result.x = candidate.x;
            result.y = candidate.y;
            result.priority = candidate.priority;
            if (candidate.id == 0) {
                result.ego_trigger = trigger;
                result.ego_water = water;
            }
            *out = result;
            return AGI_SCENE_SUCCESS;
        }
        if (result.attempts == max_attempts) {
            break;
        }
        switch (direction) {
        case 0u: candidate.x--; break;
        case 1u: candidate.y++; break;
        case 2u: candidate.x++; break;
        default: candidate.y--; break;
        }
        if (--remaining == 0u) {
            direction = (direction + 1u) & 3u;
            if (direction == 0u || direction == 2u) {
                leg_size++;
            }
            remaining = leg_size;
        }
    }
    *out = result;
    return AGI_SCENE_BUDGET_EXHAUSTED;
}

/* Adapted from sprite.c:blit_pixel, using separate indexed planes. */
static int blit_pixel(uint8_t *visual, uint8_t *priority, size_t position,
                      uint8_t color, uint32_t actor_priority)
{
    uint8_t real = priority[position];
    uint8_t effective = real;

    if (real < 3u) {
        size_t scan = position;

        while (scan < AGI_SCENE_PLANE_SIZE && priority[scan] < 3u) {
            scan += AGI_SCENE_WIDTH;
        }
        effective = scan < AGI_SCENE_PLANE_SIZE ? priority[scan] : 4u;
    }
    if (actor_priority < effective) {
        return 0;
    }
    visual[position] = color;
    if (real >= 3u) {
        priority[position] = (uint8_t)actor_priority;
    }
    return 1;
}

int agi_scene_blit(uint8_t *visual, uint8_t *priority, size_t plane_size,
                   const uint8_t *cel, size_t cel_size, int32_t x,
                   int32_t baseline, uint32_t width, uint32_t height,
                   uint32_t transparent, uint32_t actor_priority,
                   AGISceneBlit *out)
{
    AGISceneBlit result = {0u, 1u};
    uint32_t row, column;
    int32_t top;

    if (visual == NULL || priority == NULL || cel == NULL || out == NULL ||
        plane_size != AGI_SCENE_PLANE_SIZE || width == 0u ||
        width > AGI_SCENE_WIDTH || height == 0u || height > AGI_SCENE_HEIGHT ||
        cel_size != (size_t)width * height || transparent > 15u ||
        actor_priority > 15u || x < 0 || x > (int32_t)(AGI_SCENE_WIDTH - width) ||
        baseline < (int32_t)height - 1 || baseline >= 168) {
        return AGI_SCENE_INVALID_INPUT;
    }
    if (overlaps(visual, plane_size, priority, plane_size) ||
        overlaps(visual, plane_size, cel, cel_size) ||
        overlaps(priority, plane_size, cel, cel_size) ||
        overlaps(out, sizeof(*out), visual, plane_size) ||
        overlaps(out, sizeof(*out), priority, plane_size) ||
        overlaps(out, sizeof(*out), cel, cel_size)) {
        return AGI_SCENE_INVALID_INPUT;
    }
    if (!palette_valid(visual, plane_size) || !palette_valid(priority, plane_size) ||
        !palette_valid(cel, cel_size)) {
        return AGI_SCENE_INVALID_INPUT;
    }

    top = baseline - (int32_t)height + 1;
    for (row = 0u; row < height; row++) {
        size_t position = ((size_t)top + row) * AGI_SCENE_WIDTH + (size_t)x;

        for (column = 0u; column < width; column++) {
            uint8_t color = cel[(size_t)row * width + column];

            if (color != transparent &&
                blit_pixel(visual, priority, position + column, color, actor_priority)) {
                result.written_pixels++;
                result.hidden = 0u;
            }
        }
    }
    *out = result;
    return AGI_SCENE_SUCCESS;
}
