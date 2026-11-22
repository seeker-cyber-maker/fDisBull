/* SPDX-License-Identifier: GPL-2.0-only
 * Portable AGI actor semantics adapted from Sarien.
 * Copyright (C) 1999-2003 Stuart George and Claudio Matsuoka
 *
 * Original upstream grant:
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; see docs/COPYING for further details.
 *
 * Modified for fDisBull on 2026-11-22; this adaptation elects GPL version 2.
 * See native/qemu-agi/RUNTIME_ACTOR_PROVENANCE.md for the immutable donor,
 * changes, compatibility boundary and retained license.
 */
#include "runtime_actor.h"

#include <limits.h>
#include <string.h>

#define ACTIVE (AGI_RA_ANIMATED | AGI_RA_UPDATE | AGI_RA_DRAWN)
#define V_EGO_BORDER 2
#define V_OBJECT_BORDER_ID 4
#define V_OBJECT_BORDER 5
#define V_EGO_DIRECTION 6
#define F_EGO_WATER 0
#define F_EGO_TRIGGER 3
#define RANDOM_RETRIES 1024u

static const int8_t delta_x[9] = {0, 0, 1, 1, 1, 0, -1, -1, -1};
static const int8_t delta_y[9] = {0, -1, -1, 0, 1, 1, 1, 0, -1};

static int actor_valid(const AgiRuntimeActor *a)
{
    /* Public structures also serve snapshots. Reject malformed snapshots
     * before indexes, signed arithmetic or byte-sized donor parameters. */
    if (a->x < -512 || a->x > 512 || a->y < -512 || a->y > 512 ||
        a->prev_x < -512 || a->prev_x > 512 ||
        a->prev_y < -512 || a->prev_y > 512 ||
        a->target_x < 0 || a->target_x > 255 ||
        a->target_y < 0 || a->target_y > 255 ||
        a->view > 255 || a->loop > 255 || a->cel > 255 ||
        a->loop_count > 255 || a->cel_count > 255 ||
        a->priority > 15 || a->direction > 8 ||
        a->motion > AGI_RM_MOVE || a->cycle > AGI_RC_REVERSE ||
        a->step_size > 255 || a->step_time > 255 ||
        a->step_time_count > 255 || a->cycle_time > 255 ||
        a->cycle_time_count > 255 || a->motion_flag > 255 ||
        a->cycle_flag > 255 || a->saved_step > 255 ||
        a->follow_step > 255 || a->follow_count > 255 ||
        a->width > AGI_RUNTIME_WIDTH || a->height > AGI_RUNTIME_HEIGHT ||
        a->prev_width > AGI_RUNTIME_WIDTH ||
        a->prev_height > AGI_RUNTIME_HEIGHT) {
        return AGI_RA_BAD_ARGUMENT;
    }
    return AGI_RA_HANDLED;
}

static int world_valid(const AgiRuntimeWorld *w)
{
    if (w->horizon > 255 || w->player_control > 1 || w->block_active > 1 ||
        w->priority_base > 255 || w->block_x1 < 0 || w->block_x1 > 255 ||
        w->block_y1 < 0 || w->block_y1 > 255 ||
        w->block_x2 < 0 || w->block_x2 > 255 ||
        w->block_y2 < 0 || w->block_y2 > 255) {
        return AGI_RA_BAD_ARGUMENT;
    }
    return AGI_RA_HANDLED;
}

static int plane_valid(const AgiRuntimeWorld *w,
                       const AgiRuntimeActorCallbacks *cb)
{
    size_t i;
    if (!cb || !cb->priority) {
        return AGI_RA_MISSING_PLANE;
    }
    if (cb->priority_size != AGI_RUNTIME_PLANE_BYTES) {
        return AGI_RA_BAD_PLANE;
    }
    for (i = 0; i < AGI_RUNTIME_PLANE_BYTES; i++) {
        if (cb->priority[i] > 15) {
            return AGI_RA_BAD_PLANE;
        }
    }
    for (i = 0; i < AGI_RUNTIME_HEIGHT; i++) {
        if (w->priority_bands[i] > 15) {
            return AGI_RA_BAD_PLANE;
        }
    }
    return AGI_RA_HANDLED;
}

static int geometry(const AgiRuntimeWorld *w,
                    const AgiRuntimeActorCallbacks *cb, uint32_t view,
                    uint32_t loop, uint32_t cel, AgiRuntimeGeometry *g)
{
    int found;
    if (!cb || !cb->geometry) {
        return AGI_RA_MISSING_VIEW;
    }
    memset(g, 0, sizeof(*g));
    found = cb->geometry(cb->opaque, (uint8_t)view, (uint8_t)loop,
                         (uint8_t)cel, g);
    if (!found) {
        return AGI_RA_MISSING_VIEW;
    }
    if (found != 1 || !g->loop_count || g->loop_count > 255 ||
        g->cel_count > 255) {
        return AGI_RA_BAD_GEOMETRY;
    }
    if (!w->loaded_views[view]) {
        return AGI_RA_VIEW_NOT_LOADED;
    }
    return AGI_RA_HANDLED;
}

static int bound(const AgiRuntimeWorld *w, const AgiRuntimeActor *a)
{
    if (!(a->flags & AGI_RA_VIEW_BOUND)) {
        return AGI_RA_VIEW_UNBOUND;
    }
    if (!w->loaded_views[a->view]) {
        return AGI_RA_VIEW_NOT_LOADED;
    }
    if (!a->loop_count || a->loop >= a->loop_count) {
        return AGI_RA_INVALID_LOOP;
    }
    if (!a->cel_count) {
        return AGI_RA_EMPTY_LOOP;
    }
    if (a->cel >= a->cel_count) {
        return AGI_RA_INVALID_CEL;
    }
    if (!a->width || !a->height) {
        return AGI_RA_BAD_GEOMETRY;
    }
    return AGI_RA_HANDLED;
}

/* kind 0 binds a view, 1 selects a loop, 2 selects a cel. Only a new view
 * may reset an out-of-range loop; selecting a loop may reset its cel. */
static int select_geometry(AgiRuntimeWorld *w, AgiRuntimeActor *a,
                           const AgiRuntimeActorCallbacks *cb,
                           unsigned kind, uint32_t value)
{
    AgiRuntimeGeometry g;
    uint32_t view = kind == 0 ? value : a->view;
    uint32_t loop = kind == 1 ? value : a->loop;
    uint32_t cel = kind == 2 ? value : a->cel;
    int r;
    if (kind && !(a->flags & AGI_RA_VIEW_BOUND)) {
        return AGI_RA_VIEW_UNBOUND;
    }
    r = geometry(w, cb, view, loop, cel, &g);
    if (r < 0) {
        return r;
    }
    if (loop >= g.loop_count) {
        if (kind) {
            return AGI_RA_INVALID_LOOP;
        }
        loop = 0;
        r = geometry(w, cb, view, loop, cel, &g);
        if (r < 0) {
            return r;
        }
    }
    if (!g.cel_count) {
        return AGI_RA_EMPTY_LOOP;
    }
    if (cel >= g.cel_count) {
        if (kind == 2) {
            return AGI_RA_INVALID_CEL;
        }
        cel = 0;
        r = geometry(w, cb, view, loop, cel, &g);
        if (r < 0) {
            return r;
        }
    }
    if (!g.width || g.width > AGI_RUNTIME_WIDTH ||
        !g.height || g.height > AGI_RUNTIME_HEIGHT ||
        loop >= g.loop_count || cel >= g.cel_count) {
        return AGI_RA_BAD_GEOMETRY;
    }
    a->view = view;
    a->loop = loop;
    a->cel = cel;
    a->loop_count = g.loop_count;
    a->cel_count = g.cel_count;
    a->width = g.width;
    a->height = g.height;
    a->flags |= AGI_RA_VIEW_BOUND;
    if (kind == 0) {
        a->flags |= AGI_RA_VIEW_REPLACED;
    }
    if (a->x + (int32_t)a->width > (int32_t)AGI_RUNTIME_WIDTH) {
        a->x = AGI_RUNTIME_WIDTH - a->width;
        a->flags |= AGI_RA_UPDATE_POSITION;
    }
    /* Existing native CPU's qualified nominal DOS 2.917 distinction:
     * horizon repair is nested inside top-edge repair for geometry binding.
     * General placement and movement enforce the horizon separately. */
    if (a->y + 1 < (int32_t)a->height) {
        a->y = (int32_t)a->height - 1;
        a->flags |= AGI_RA_UPDATE_POSITION;
        if (a->y <= (int32_t)w->horizon &&
            !(a->flags & AGI_RA_IGNORE_HORIZON)) {
            a->y = (int32_t)w->horizon + 1;
        }
    }
    return AGI_RA_HANDLED;
}

static int position_valid(const AgiRuntimeWorld *w, const AgiRuntimeActor *a)
{
    return a->x >= 0 && a->x + (int32_t)a->width <= (int32_t)AGI_RUNTIME_WIDTH &&
        a->y + 1 >= (int32_t)a->height && a->y < (int32_t)AGI_RUNTIME_HEIGHT &&
        ((a->flags & AGI_RA_IGNORE_HORIZON) || a->y > (int32_t)w->horizon);
}

static int collision(const AgiRuntimeWorld *w, unsigned id)
{
    const AgiRuntimeActor *a = &w->actors[id];
    unsigned i;
    if (a->flags & AGI_RA_IGNORE_OBJECTS) {
        return 0;
    }
    for (i = 0; i < AGI_RUNTIME_ACTORS; i++) {
        const AgiRuntimeActor *b = &w->actors[i];
        if (i == id ||
            (b->flags & (AGI_RA_ANIMATED | AGI_RA_DRAWN)) !=
                (AGI_RA_ANIMATED | AGI_RA_DRAWN) ||
            (b->flags & AGI_RA_IGNORE_OBJECTS)) {
            continue;
        }
        /* Sarien uses inclusive bounding baselines, including touching ends. */
        if ((int64_t)a->x + a->width < b->x ||
            a->x > (int64_t)b->x + b->width) {
            continue;
        }
        if (a->y == b->y ||
            (a->y > b->y && a->prev_y < b->prev_y) ||
            (a->y < b->y && a->prev_y > b->prev_y)) {
            return 1;
        }
    }
    return 0;
}

static int priority_pass(AgiRuntimeWorld *w, unsigned id, uint8_t flags[256],
                         const AgiRuntimeActorCallbacks *cb)
{
    AgiRuntimeActor *a = &w->actors[id];
    unsigned x;
    int water = 0, trigger = 0, pass = 1;
    if (!(a->flags & AGI_RA_FIXED_PRIORITY)) {
        a->priority = w->priority_bands[a->y];
    }
    if (a->priority != 15) {
        water = 1;
        for (x = 0; x < a->width; x++) {
            uint8_t p = cb->priority[(size_t)a->y * AGI_RUNTIME_WIDTH + a->x + x];
            if (p == 0) {
                pass = 0;
                break;
            }
            if (p == 3) {
                continue;
            }
            water = 0;
            if (p == 1 && !(a->flags & AGI_RA_IGNORE_BLOCKS)) {
                pass = 0;
                break;
            }
            if (p == 2) {
                trigger = 1;
            }
        }
        if (pass && ((!water && (a->flags & AGI_RA_ON_WATER)) ||
                     (water && (a->flags & AGI_RA_ON_LAND)))) {
            pass = 0;
        }
    }
    if (id == 0) {
        flags[F_EGO_WATER] = (uint8_t)water;
        flags[F_EGO_TRIGGER] = (uint8_t)trigger;
    }
    return pass;
}

static unsigned distance_abs(int32_t a, int32_t b)
{
    return (unsigned)(a > b ? a - b : b - a);
}

static int fix_position(AgiRuntimeWorld *w, unsigned id, uint8_t flags[256],
                        const AgiRuntimeActorCallbacks *cb)
{
    AgiRuntimeActor *a = &w->actors[id];
    unsigned direction = 0, count = 1, size = 1, attempts, radius, limit;
    int r = bound(w, a);
    if (r < 0) {
        return r;
    }
    if (!(a->flags & AGI_RA_IGNORE_HORIZON) && a->y <= (int32_t)w->horizon) {
        a->y = (int32_t)w->horizon + 1;
    }
    /* A complete square around the starting point that contains every
     * picture coordinate bounds the donor's otherwise unbounded spiral. */
    radius = distance_abs(a->x, 0);
    if (radius < distance_abs(a->x, AGI_RUNTIME_WIDTH - 1)) {
        radius = distance_abs(a->x, AGI_RUNTIME_WIDTH - 1);
    }
    if (radius < distance_abs(a->y, 0)) {
        radius = distance_abs(a->y, 0);
    }
    if (radius < distance_abs(a->y, AGI_RUNTIME_HEIGHT - 1)) {
        radius = distance_abs(a->y, AGI_RUNTIME_HEIGHT - 1);
    }
    limit = (radius * 2 + 3) * (radius * 2 + 3);
    for (attempts = 0; attempts < limit; attempts++) {
        if (position_valid(w, a) && !collision(w, id) &&
            priority_pass(w, id, flags, cb)) {
            return AGI_RA_HANDLED;
        }
        switch (direction) {
        case 0: a->x--; break;
        case 1: a->y++; break;
        case 2: a->x++; break;
        default: a->y--; break;
        }
        if (--count == 0) {
            if (direction == 1 || direction == 3) {
                size++;
            }
            direction = (direction + 1) & 3;
            count = size;
        }
    }
    return AGI_RA_NO_POSITION;
}

static unsigned get_direction(int32_t x0, int32_t y0, int32_t x, int32_t y,
                              unsigned step)
{
    static const uint8_t table[9] = {8, 1, 2, 7, 0, 3, 6, 5, 4};
    int dx = x - x0, dy = y - y0;
    unsigned ix = dx <= -(int)step ? 0 : dx >= (int)step ? 2 : 1;
    unsigned iy = dy <= -(int)step ? 0 : dy >= (int)step ? 2 : 1;
    return table[ix + iy * 3];
}

static void in_destination(AgiRuntimeWorld *w, unsigned id, uint8_t flags[256])
{
    AgiRuntimeActor *a = &w->actors[id];
    if (a->motion == AGI_RM_MOVE) {
        a->step_size = a->saved_step;
        flags[a->motion_flag] = 1;
    }
    a->motion = AGI_RM_NORMAL;
    if (id == 0) {
        w->player_control = 1;
    }
}

static void motion_move(AgiRuntimeWorld *w, unsigned id,
                        uint8_t vars[256], uint8_t flags[256])
{
    AgiRuntimeActor *a = &w->actors[id];
    a->direction = get_direction(a->x, a->y, a->target_x, a->target_y,
                                 a->step_size);
    if (id == 0) {
        vars[V_EGO_DIRECTION] = (uint8_t)a->direction;
    }
    if (!a->direction) {
        in_destination(w, id, flags);
    }
}

static int random_below(AgiRuntimeWorld *w, const AgiRuntimeActorCallbacks *cb,
                        unsigned upper, uint32_t *value)
{
    if (!cb || !cb->random) {
        return AGI_RA_MISSING_RANDOM;
    }
    *value = cb->random(cb->opaque, &w->rng_state, upper);
    return *value < upper ? AGI_RA_HANDLED : AGI_RA_BAD_RANDOM;
}

static int motion_wander(AgiRuntimeWorld *w, unsigned id, uint8_t vars[256],
                          const AgiRuntimeActorCallbacks *cb)
{
    AgiRuntimeActor *a = &w->actors[id];
    uint32_t old = a->follow_count;
    unsigned retries = 0;
    int r;
    a->follow_count = (a->follow_count - 1) & 255;
    if (old && !(a->flags & AGI_RA_DIDNT_MOVE)) {
        return AGI_RA_HANDLED;
    }
    r = random_below(w, cb, 9, &a->direction);
    if (r < 0) {
        return r;
    }
    if (id == 0) {
        vars[V_EGO_DIRECTION] = (uint8_t)a->direction;
        while (a->follow_count < 6) {
            if (++retries > RANDOM_RETRIES) {
                return AGI_RA_BAD_RANDOM;
            }
            r = random_below(w, cb, 51, &a->follow_count);
            if (r < 0) {
                return r;
            }
        }
    }
    return AGI_RA_HANDLED;
}

static int motion_follow(AgiRuntimeWorld *w, unsigned id, uint8_t flags[256],
                          const AgiRuntimeActorCallbacks *cb)
{
    AgiRuntimeActor *a = &w->actors[id];
    const AgiRuntimeActor *ego = &w->actors[0];
    int32_t ex = ego->x + (int32_t)(ego->width / 2);
    int32_t ax = a->x + (int32_t)(a->width / 2);
    unsigned direction = get_direction(ax, a->y, ex, ego->y, a->follow_step);
    unsigned retries = 0, distance;
    int r;
    if (!direction) {
        a->direction = 0;
        a->motion = AGI_RM_NORMAL;
        flags[a->motion_flag] = 1;
        return AGI_RA_HANDLED;
    }
    if (a->follow_count == 255) {
        a->follow_count = 0;
    } else if (a->flags & AGI_RA_DIDNT_MOVE) {
        do {
            if (++retries > RANDOM_RETRIES) {
                return AGI_RA_BAD_RANDOM;
            }
            r = random_below(w, cb, 9, &a->direction);
            if (r < 0) {
                return r;
            }
        } while (!a->direction);
        distance = (distance_abs(ego->y, a->y) + distance_abs(ex, ax)) / 2 + 1;
        if (distance <= a->step_size) {
            a->follow_count = a->step_size;
            return AGI_RA_HANDLED;
        }
        retries = 0;
        do {
            uint32_t value;
            if (++retries > RANDOM_RETRIES) {
                return AGI_RA_BAD_RANDOM;
            }
            r = random_below(w, cb, distance, &value);
            if (r < 0) {
                return r;
            }
            a->follow_count = value & 255;
        } while (a->follow_count < a->step_size);
        return AGI_RA_HANDLED;
    }
    if (a->follow_count) {
        a->follow_count = (a->follow_count - a->step_size) & 255;
        if (a->follow_count & 128) {
            a->follow_count = 0;
        }
    } else {
        a->direction = direction;
    }
    return AGI_RA_HANDLED;
}

static int inside_block(const AgiRuntimeWorld *w, int32_t x, int32_t y)
{
    return x > w->block_x1 && x < w->block_x2 &&
           y > w->block_y1 && y < w->block_y2;
}

static int prepare_inner(AgiRuntimeWorld *w, uint8_t vars[256],
                          uint8_t flags[256], const AgiRuntimeActorCallbacks *cb)
{
    unsigned i;
    int r;
    if (w->player_control) {
        if (w->actors[0].direction > 8) {
            return AGI_RA_BAD_ARGUMENT;
        }
        vars[V_EGO_DIRECTION] = (uint8_t)w->actors[0].direction;
    } else {
        if (vars[V_EGO_DIRECTION] > 8) {
            return AGI_RA_BAD_ARGUMENT;
        }
        w->actors[0].direction = vars[V_EGO_DIRECTION];
    }
    for (i = 0; i < AGI_RUNTIME_ACTORS; i++) {
        AgiRuntimeActor *a = &w->actors[i];
        if ((a->flags & ACTIVE) != ACTIVE || a->step_time_count != 1) {
            continue;
        }
        r = actor_valid(a);
        if (r < 0) {
            return r;
        }
        switch (a->motion) {
        case AGI_RM_WANDER: r = motion_wander(w, i, vars, cb); break;
        case AGI_RM_FOLLOW: r = motion_follow(w, i, flags, cb); break;
        case AGI_RM_MOVE: motion_move(w, i, vars, flags); break;
        default: break;
        }
        if (r < 0) {
            return r;
        }
        if (w->block_active && !(a->flags & AGI_RA_IGNORE_BLOCKS) &&
            a->direction) {
            int32_t x = a->x + (int32_t)a->step_size * delta_x[a->direction];
            int32_t y = a->y + (int32_t)a->step_size * delta_y[a->direction];
            if (inside_block(w, x, y) == inside_block(w, a->x, a->y)) {
                a->flags &= ~(AGI_RA_MOTION_ACTIVE | AGI_RA_BLOCKED);
            } else {
                a->flags |= AGI_RA_MOTION_ACTIVE | AGI_RA_BLOCKED;
                a->direction = 0;
                if (i == 0) {
                    vars[V_EGO_DIRECTION] = 0;
                }
            }
        }
    }
    return AGI_RA_HANDLED;
}

static int cycle_actor(AgiRuntimeWorld *w, AgiRuntimeActor *a,
                       uint8_t flags[256], const AgiRuntimeActorCallbacks *cb)
{
    uint32_t cel = a->cel;
    int complete = 0;
    if (a->flags & AGI_RA_DONT_UPDATE) {
        a->flags &= ~AGI_RA_DONT_UPDATE;
        return AGI_RA_HANDLED;
    }
    switch (a->cycle) {
    case AGI_RC_NORMAL: cel = (cel + 1) % a->cel_count; break;
    case AGI_RC_REVERSE: cel = cel ? cel - 1 : a->cel_count - 1; break;
    case AGI_RC_END:
        if (cel < a->cel_count - 1) {
            cel++;
        }
        complete = cel == a->cel_count - 1;
        break;
    case AGI_RC_REVERSE_LOOP:
        if (cel) {
            cel--;
        }
        complete = cel == 0;
        break;
    }
    if (complete) {
        flags[a->cycle_flag] = 1;
        a->flags &= ~AGI_RA_CYCLING;
        a->direction = 0;
        a->cycle = AGI_RC_NORMAL;
    }
    return select_geometry(w, a, cb, 2, cel);
}

static void commit_actor(AgiRuntimeActor *a)
{
    a->prev_width = a->width;
    a->prev_height = a->height;
    a->flags &= ~AGI_RA_VIEW_REPLACED;
    if (a->step_time_count == a->step_time) {
        if (a->x == a->prev_x && a->y == a->prev_y) {
            a->flags |= AGI_RA_DIDNT_MOVE;
        } else {
            a->prev_x = a->x;
            a->prev_y = a->y;
            a->flags &= ~AGI_RA_DIDNT_MOVE;
        }
    }
}

static int finish_inner(AgiRuntimeWorld *w, uint8_t vars[256],
                         uint8_t flags[256], const AgiRuntimeActorCallbacks *cb)
{
    static const uint8_t loops2[9] = {4, 4, 0, 0, 0, 4, 1, 1, 1};
    static const uint8_t loops4[9] = {4, 3, 0, 0, 0, 2, 1, 1, 1};
    unsigned i, active = 0;
    int r;
    if (vars[V_EGO_DIRECTION] > 8 || w->ticks == UINT64_MAX) {
        return AGI_RA_BAD_ARGUMENT;
    }
    w->actors[0].direction = vars[V_EGO_DIRECTION];
    for (i = 0; i < AGI_RUNTIME_ACTORS; i++) {
        AgiRuntimeActor *a = &w->actors[i];
        if ((a->flags & ACTIVE) != ACTIVE) {
            continue;
        }
        active++;
        r = actor_valid(a);
        if (r < 0) {
            return r;
        }
        r = bound(w, a);
        if (r < 0) {
            return r;
        }
    }
    if (active) {
        r = plane_valid(w, cb);
        if (r < 0) {
            return r;
        }
    }
    for (i = 0; i < AGI_RUNTIME_ACTORS; i++) {
        AgiRuntimeActor *a = &w->actors[i];
        unsigned loop = 4;
        if ((a->flags & ACTIVE) != ACTIVE) {
            continue;
        }
        if (!(a->flags & AGI_RA_FIXED_LOOP)) {
            if (a->loop_count == 2 || a->loop_count == 3) {
                loop = loops2[a->direction];
            } else if (a->loop_count == 4) {
                loop = loops4[a->direction];
            }
        }
        if (loop != 4 && loop != a->loop && a->step_time_count == 1) {
            r = select_geometry(w, a, cb, 1, loop);
            if (r < 0) {
                return r;
            }
        }
        if ((a->flags & AGI_RA_CYCLING) && a->cycle_time_count &&
            --a->cycle_time_count == 0) {
            r = cycle_actor(w, a, flags, cb);
            if (r < 0) {
                return r;
            }
            a->cycle_time_count = a->cycle_time;
        }
    }
    if (active) {
        vars[V_EGO_BORDER] = vars[V_OBJECT_BORDER_ID] = vars[V_OBJECT_BORDER] = 0;
    }
    for (i = 0; i < AGI_RUNTIME_ACTORS; i++) {
        AgiRuntimeActor *a = &w->actors[i];
        int32_t old_x, old_y;
        unsigned border = 0;
        if ((a->flags & ACTIVE) != ACTIVE) {
            continue;
        }
        if (a->step_time_count && --a->step_time_count) {
            continue;
        }
        a->step_time_count = a->step_time;
        old_x = a->x;
        old_y = a->y;
        if (!(a->flags & AGI_RA_UPDATE_POSITION)) {
            a->x += (int32_t)a->step_size * delta_x[a->direction];
            a->y += (int32_t)a->step_size * delta_y[a->direction];
        }
        if (a->x < 0) {
            a->x = 0;
            border = 4;
        } else if (a->x + (int32_t)a->width > (int32_t)AGI_RUNTIME_WIDTH) {
            a->x = (int32_t)(AGI_RUNTIME_WIDTH - a->width);
            border = 2;
        }
        if (a->y + 1 < (int32_t)a->height) {
            a->y = (int32_t)a->height - 1;
            border = 1;
        } else if (a->y >= (int32_t)AGI_RUNTIME_HEIGHT) {
            a->y = AGI_RUNTIME_HEIGHT - 1;
            border = 3;
        } else if (!(a->flags & AGI_RA_IGNORE_HORIZON) &&
                   a->y <= (int32_t)w->horizon) {
            a->y = (int32_t)w->horizon + 1;
            border = 1;
        }
        if (!position_valid(w, a) || collision(w, i) ||
            !priority_pass(w, i, flags, cb)) {
            a->x = old_x;
            a->y = old_y;
            border = 0;
            r = fix_position(w, i, flags, cb);
            if (r < 0) {
                return r;
            }
        }
        if (border) {
            if (i == 0) {
                vars[V_EGO_BORDER] = (uint8_t)border;
            } else {
                vars[V_OBJECT_BORDER_ID] = (uint8_t)i;
                vars[V_OBJECT_BORDER] = (uint8_t)border;
            }
            if (a->motion == AGI_RM_MOVE) {
                in_destination(w, i, flags);
            }
        }
        a->flags &= ~AGI_RA_UPDATE_POSITION;
    }
    for (i = 0; i < AGI_RUNTIME_ACTORS; i++) {
        if ((w->actors[i].flags & ACTIVE) == ACTIVE) {
            commit_actor(&w->actors[i]);
        }
    }
    if (active) {
        w->actors[0].flags &= ~(AGI_RA_ON_WATER | AGI_RA_ON_LAND);
    }
    w->ticks++;
    return AGI_RA_HANDLED;
}

void agi_runtime_world_init(AgiRuntimeWorld *w)
{
    unsigned i;
    if (!w) {
        return;
    }
    memset(w, 0, sizeof(*w));
    w->horizon = 36;
    w->player_control = 1;
    w->priority_base = 48;
    w->rng_state = 1;
    for (i = 0; i < AGI_RUNTIME_HEIGHT; i++) {
        unsigned p = i / 12 + 1;
        w->priority_bands[i] = (uint8_t)(p < 4 ? 4 : p);
    }
    for (i = 0; i < AGI_RUNTIME_ACTORS; i++) {
        AgiRuntimeActor *a = &w->actors[i];
        a->flags = AGI_RA_UPDATE;
        a->step_size = a->step_time = a->step_time_count = 1;
        a->cycle_time = a->cycle_time_count = 1;
    }
}

static int command_width(uint32_t op)
{
    static const uint8_t widths[] = {
        1, 0, 1, 1, 3, 3, 3, 3, 2, 2, 2, 2, 1, 1, 2, 2,
        2, 2, 2, 2, 2, 2, 2, 1, 2, 1, 1, 1, 1, 1, 1, 1,
        1, 1, 1, 1, 3, 1, 1, 1, 2, 1, 2, 2, 1, 1, 2, 2,
        5, 5, 3, 1, 1, 2, 2, 1, 1, 4, 0
    };
    if (op >= 33 && op <= 91) {
        return widths[op - 33];
    }
    return op == 147 || op == 148 ? 3 : -1;
}

static int command_inner(AgiRuntimeWorld *w, uint32_t op, const uint8_t *p,
                           uint8_t vars[256], uint8_t flags[256],
                           const AgiRuntimeActorCallbacks *cb)
{
    unsigned id = command_width(op) ? p[0] : 0;
    AgiRuntimeActor *a = &w->actors[id];
    unsigned i, value;
    int r = (op == 34 || op == 60 || op == 63 || op == 90 || op == 91) ?
            AGI_RA_HANDLED : actor_valid(a);
    if (r < 0) {
        return r;
    }
    switch (op) {
    case 33:
        if (!(a->flags & AGI_RA_ANIMATED)) {
            a->flags = (a->flags & AGI_RA_VIEW_BOUND) |
                       AGI_RA_ANIMATED | AGI_RA_UPDATE | AGI_RA_CYCLING;
            a->motion = AGI_RM_NORMAL;
            a->cycle = AGI_RC_NORMAL;
            a->direction = 0;
        }
        break;
    case 34:
        for (i = 0; i < AGI_RUNTIME_ACTORS; i++) {
            w->actors[i].flags &= ~(AGI_RA_ANIMATED | AGI_RA_DRAWN);
        }
        break;
    case 35:
        if (a->flags & AGI_RA_DRAWN) {
            break;
        }
        r = bound(w, a);
        if (r < 0) {
            return r;
        }
        r = plane_valid(w, cb);
        if (r < 0) {
            return r;
        }
        r = fix_position(w, id, flags, cb);
        if (r < 0) {
            return r;
        }
        a->prev_x = a->x;
        a->prev_y = a->y;
        a->prev_width = a->width;
        a->prev_height = a->height;
        a->flags |= AGI_RA_UPDATE | AGI_RA_DRAWN;
        a->flags &= ~(AGI_RA_DONT_UPDATE | AGI_RA_VIEW_REPLACED);
        break;
    case 36: a->flags &= ~AGI_RA_DRAWN; break;
    case 37: case 38:
        a->x = a->prev_x = op == 37 ? p[1] : vars[p[1]];
        a->y = a->prev_y = op == 37 ? p[2] : vars[p[2]];
        break;
    case 39:
        vars[p[1]] = (uint8_t)a->x;
        vars[p[2]] = (uint8_t)a->y;
        break;
    case 40: case 147: case 148:
        r = plane_valid(w, cb);
        if (r < 0) {
            return r;
        }
        if (op == 40) {
            int dx = vars[p[1]], dy = vars[p[2]];
            dx = dx >= 128 ? dx - 256 : dx;
            dy = dy >= 128 ? dy - 256 : dy;
            a->x = a->x + dx < 0 ? 0 : a->x + dx;
            a->y = a->y + dy < 0 ? 0 : a->y + dy;
        } else {
            a->x = op == 147 ? p[1] : vars[p[1]];
            a->y = op == 147 ? p[2] : vars[p[2]];
        }
        a->flags |= AGI_RA_UPDATE_POSITION;
        return fix_position(w, id, flags, cb);
    case 41: case 42:
        return select_geometry(w, a, cb, 0, op == 41 ? p[1] : vars[p[1]]);
    case 43: case 44:
        return select_geometry(w, a, cb, 1, op == 43 ? p[1] : vars[p[1]]);
    case 45: a->flags |= AGI_RA_FIXED_LOOP; break;
    case 46: a->flags &= ~AGI_RA_FIXED_LOOP; break;
    case 47: case 48:
        r = select_geometry(w, a, cb, 2, op == 47 ? p[1] : vars[p[1]]);
        if (r < 0) {
            return r;
        }
        a->flags &= ~AGI_RA_DONT_UPDATE;
        break;
    case 49:
        r = bound(w, a);
        if (r < 0) {
            return r;
        }
        vars[p[1]] = (uint8_t)(a->cel_count - 1);
        break;
    case 50: vars[p[1]] = (uint8_t)a->cel; break;
    case 51: vars[p[1]] = (uint8_t)a->loop; break;
    case 52: vars[p[1]] = (uint8_t)a->view; break;
    case 53: vars[p[1]] = (uint8_t)a->loop_count; break;
    case 54: case 55:
        value = op == 54 ? p[1] : vars[p[1]];
        if (value > 15) {
            return AGI_RA_BAD_ARGUMENT;
        }
        a->priority = value;
        a->flags |= AGI_RA_FIXED_PRIORITY;
        break;
    case 56: a->flags &= ~AGI_RA_FIXED_PRIORITY; break;
    case 57: vars[p[1]] = (uint8_t)a->priority; break;
    case 58: a->flags &= ~AGI_RA_UPDATE; break;
    case 59: a->flags |= AGI_RA_UPDATE; break;
    case 60:
        /* Root must publish the force-refresh renderer effect even if the
         * native remembered-pose bookkeeping happens to be unchanged. */
        for (i = 0; i < AGI_RUNTIME_ACTORS; i++) {
            if (w->actors[i].flags & AGI_RA_DRAWN) {
                commit_actor(&w->actors[i]);
            }
        }
        break;
    case 61: a->flags |= AGI_RA_IGNORE_HORIZON; break;
    case 62: a->flags &= ~AGI_RA_IGNORE_HORIZON; break;
    case 63: w->horizon = p[0]; break;
    case 64: a->flags |= AGI_RA_ON_WATER; break;
    case 65: a->flags |= AGI_RA_ON_LAND; break;
    case 66: a->flags &= ~(AGI_RA_ON_WATER | AGI_RA_ON_LAND); break;
    case 67: a->flags |= AGI_RA_IGNORE_OBJECTS; break;
    case 68: a->flags &= ~AGI_RA_IGNORE_OBJECTS; break;
    case 69:
        if ((a->flags & AGI_RA_DRAWN) && (w->actors[p[1]].flags & AGI_RA_DRAWN)) {
            AgiRuntimeActor *b = &w->actors[p[1]];
            r = actor_valid(b);
            if (r < 0) {
                return r;
            }
            value = distance_abs(a->x + (int32_t)(a->width / 2),
                                  b->x + (int32_t)(b->width / 2)) +
                    distance_abs(a->y, b->y);
            vars[p[2]] = (uint8_t)(value > 254 ? 254 : value);
        } else {
            vars[p[2]] = 255;
        }
        break;
    case 70: a->flags &= ~AGI_RA_CYCLING; break;
    case 71: a->flags |= AGI_RA_CYCLING; break;
    case 72: case 74:
        a->cycle = op == 72 ? AGI_RC_NORMAL : AGI_RC_REVERSE;
        a->flags |= AGI_RA_CYCLING;
        break;
    case 73: case 75:
        a->cycle = op == 73 ? AGI_RC_END : AGI_RC_REVERSE_LOOP;
        a->flags |= AGI_RA_DONT_UPDATE | AGI_RA_UPDATE | AGI_RA_CYCLING;
        a->cycle_flag = p[1];
        flags[p[1]] = 0;
        break;
    case 76: a->cycle_time = a->cycle_time_count = vars[p[1]]; break;
    case 77:
        a->direction = 0;
        a->motion = AGI_RM_NORMAL;
        if (id == 0) {
            vars[V_EGO_DIRECTION] = 0;
            w->player_control = 0;
        }
        break;
    case 78:
        a->motion = AGI_RM_NORMAL;
        if (id == 0) {
            vars[V_EGO_DIRECTION] = 0;
            w->player_control = 1;
        }
        break;
    case 79: a->step_size = vars[p[1]]; break;
    case 80: a->step_time = a->step_time_count = vars[p[1]]; break;
    case 81: case 82:
        a->motion = AGI_RM_MOVE;
        a->target_x = op == 81 ? p[1] : vars[p[1]];
        a->target_y = op == 81 ? p[2] : vars[p[2]];
        a->saved_step = a->step_size;
        a->motion_flag = p[4];
        value = op == 81 ? p[3] : vars[p[3]];
        if (value) {
            a->step_size = value;
        }
        flags[p[4]] = 0;
        a->flags |= AGI_RA_UPDATE;
        if (id == 0) {
            w->player_control = 0;
        }
        motion_move(w, id, vars, flags);
        break;
    case 83:
        a->motion = AGI_RM_FOLLOW;
        a->follow_step = p[1] > a->step_size ? p[1] : a->step_size;
        a->motion_flag = p[2];
        a->follow_count = 255;
        flags[p[2]] = 0;
        a->flags |= AGI_RA_UPDATE;
        break;
    case 84:
        a->motion = AGI_RM_WANDER;
        a->flags |= AGI_RA_UPDATE;
        if (id == 0) {
            w->player_control = 0;
        }
        break;
    case 85: a->motion = AGI_RM_NORMAL; break;
    case 86:
        if (vars[p[1]] > 8) {
            return AGI_RA_BAD_ARGUMENT;
        }
        a->direction = vars[p[1]];
        break;
    case 87: vars[p[1]] = (uint8_t)a->direction; break;
    case 88: a->flags |= AGI_RA_IGNORE_BLOCKS; break;
    case 89: a->flags &= ~AGI_RA_IGNORE_BLOCKS; break;
    case 90:
        w->block_active = 1;
        w->block_x1 = p[0]; w->block_y1 = p[1];
        w->block_x2 = p[2]; w->block_y2 = p[3];
        break;
    case 91: w->block_active = 0; break;
    default: return AGI_RA_UNHANDLED;
    }
    return AGI_RA_HANDLED;
}

int agi_runtime_actor_command(AgiRuntimeWorld *world, uint32_t opcode,
                              const uint8_t *args, size_t argc,
                              uint8_t variables[256], uint8_t flags[256],
                              const AgiRuntimeActorCallbacks *callbacks)
{
    AgiRuntimeWorld candidate;
    uint8_t vars_copy[256], flags_copy[256];
    int width = command_width(opcode), r;
    if (width < 0) {
        return AGI_RA_UNHANDLED;
    }
    if (!world || !variables || !flags || argc != (size_t)width ||
        (argc && !args)) {
        return AGI_RA_BAD_ARGUMENT;
    }
    r = world_valid(world);
    if (r < 0) {
        return r;
    }
    candidate = *world;
    memcpy(vars_copy, variables, sizeof(vars_copy));
    memcpy(flags_copy, flags, sizeof(flags_copy));
    r = command_inner(&candidate, opcode, args, vars_copy, flags_copy, callbacks);
    if (r == AGI_RA_HANDLED) {
        *world = candidate;
        memcpy(variables, vars_copy, sizeof(vars_copy));
        memcpy(flags, flags_copy, sizeof(flags_copy));
    }
    return r;
}

static int phases(AgiRuntimeWorld *world, uint32_t count, unsigned which,
                   uint8_t variables[256], uint8_t flags[256],
                   const AgiRuntimeActorCallbacks *callbacks)
{
    AgiRuntimeWorld candidate;
    uint8_t vars_copy[256], flags_copy[256];
    uint32_t i;
    int r;
    if (!world || !variables || !flags) {
        return AGI_RA_BAD_ARGUMENT;
    }
    if (count > 4096) {
        return AGI_RA_TICK_LIMIT;
    }
    r = world_valid(world);
    if (r < 0) {
        return r;
    }
    for (i = 0; i < AGI_RUNTIME_ACTORS; i++) {
        r = actor_valid(&world->actors[i]);
        if (r < 0) {
            return r;
        }
    }
    candidate = *world;
    memcpy(vars_copy, variables, sizeof(vars_copy));
    memcpy(flags_copy, flags, sizeof(flags_copy));
    for (i = 0; i < count; i++) {
        if (which & 1) {
            r = prepare_inner(&candidate, vars_copy, flags_copy, callbacks);
            if (r < 0) {
                return r;
            }
        }
        if (which & 2) {
            r = finish_inner(&candidate, vars_copy, flags_copy, callbacks);
            if (r < 0) {
                return r;
            }
        }
    }
    *world = candidate;
    memcpy(variables, vars_copy, sizeof(vars_copy));
    memcpy(flags, flags_copy, sizeof(flags_copy));
    return AGI_RA_HANDLED;
}

int agi_runtime_actor_prepare(AgiRuntimeWorld *world, uint8_t variables[256],
                              uint8_t flags[256],
                              const AgiRuntimeActorCallbacks *callbacks)
{
    return phases(world, 1, 1, variables, flags, callbacks);
}

int agi_runtime_actor_finish(AgiRuntimeWorld *world, uint8_t variables[256],
                             uint8_t flags[256],
                             const AgiRuntimeActorCallbacks *callbacks)
{
    return phases(world, 1, 2, variables, flags, callbacks);
}

int agi_runtime_actor_tick(AgiRuntimeWorld *world, uint32_t count,
                           uint8_t variables[256], uint8_t flags[256],
                           const AgiRuntimeActorCallbacks *callbacks)
{
    return phases(world, count, 3, variables, flags, callbacks);
}

const char *agi_runtime_actor_error(int result)
{
    switch (result) {
    case AGI_RA_UNHANDLED: return "unhandled actor opcode";
    case AGI_RA_HANDLED: return "handled";
    case AGI_RA_BAD_ARGUMENT: return "invalid actor argument or state";
    case AGI_RA_MISSING_VIEW: return "view geometry unavailable";
    case AGI_RA_VIEW_NOT_LOADED: return "view is not loaded";
    case AGI_RA_VIEW_UNBOUND: return "actor has no bound view";
    case AGI_RA_INVALID_LOOP: return "loop is out of range";
    case AGI_RA_INVALID_CEL: return "cel is out of range";
    case AGI_RA_EMPTY_LOOP: return "view loop has no cels";
    case AGI_RA_BAD_GEOMETRY: return "invalid view geometry";
    case AGI_RA_MISSING_PLANE: return "priority/control plane unavailable";
    case AGI_RA_BAD_PLANE: return "invalid priority/control plane";
    case AGI_RA_NO_POSITION: return "no admissible actor position";
    case AGI_RA_MISSING_RANDOM: return "deterministic random callback unavailable";
    case AGI_RA_BAD_RANDOM: return "invalid or non-progressing random callback";
    case AGI_RA_TICK_LIMIT: return "logical tick batch exceeds 4096";
    default: return "unknown actor result";
    }
}
