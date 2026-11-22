/* SPDX-License-Identifier: GPL-2.0-only
 * AGI v2 picture, VIEW and raster semantics adapted from Sarien.
 * Copyright (C) 1999-2003 Stuart George and Claudio Matsuoka.
 * Modifications for fDisBull contributors, 2026-11-22.
 *
 * Original grant: This program is free software; you can redistribute it
 * and/or modify it under the terms of the GNU General Public License as
 * published by the Free Software Foundation; see docs/COPYING for further
 * details. This adaptation elects GPL version 2; see COPYING.sarien.txt and
 * RUNTIME_SCENE_PROVENANCE.md. Distributed without warranty.
 */
#include "runtime_scene.h"
#include <stdlib.h>
#include <string.h>

#define W AGI_RUNTIME_WIDTH
#define H AGI_RUNTIME_HEIGHT
#define N AGI_RUNTIME_PLANE_BYTES

static int overlap(const void *a, size_t an, const void *b, size_t bn)
{
    uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
    if (!an || !bn) {
        return 0;
    }
    return x <= y ? y - x < an : x - y < bn;
}

static int palette(const uint8_t *p, size_t n)
{
    size_t i;
    for (i = 0; i < n; i++) {
        if (p[i] > 15) {
            return 0;
        }
    }
    return 1;
}

static int planes(uint8_t *v, uint8_t *p, size_t n)
{
    return v && p && n == N && !overlap(v, N, p, N);
}

static const uint8_t circles[8][15] = {
    { 0x80 }, { 0xfc }, { 0x5f, 0xf4 }, { 0x66, 0xff, 0xf6, 0x60 },
    { 0x23, 0xbf, 0xff, 0xff, 0xee, 0x20 },
    { 0x31, 0xe7, 0x9e, 0xff, 0xff, 0xde, 0x79, 0xe3, 0x00 },
    { 0x38, 0xf9, 0xf3, 0xef, 0xff, 0xff, 0xff, 0xfe,
      0xf9, 0xf3, 0xe3, 0x80 },
    { 0x18, 0x3c, 0x7e, 0x7e, 0x7e, 0xff, 0xff, 0xff,
      0xff, 0xff, 0x7e, 0x7e, 0x7e, 0x3c, 0x18 }
};

static const uint8_t splatter_map[32] = {
    0x20, 0x94, 0x02, 0x24, 0x90, 0x82, 0xa4, 0xa2,
    0x82, 0x09, 0x0a, 0x22, 0x12, 0x10, 0x42, 0x14,
    0x91, 0x4a, 0x91, 0x11, 0x08, 0x12, 0x25, 0x10,
    0x22, 0xa8, 0x14, 0x24, 0x00, 0x50, 0x24, 0x04
};

static const uint8_t splatter_start[128] = {
    0x00, 0x18, 0x30, 0xc4, 0xdc, 0x65, 0xeb, 0x48,
    0x60, 0xbd, 0x89, 0x05, 0x0a, 0xf4, 0x7d, 0x7d,
    0x85, 0xb0, 0x8e, 0x95, 0x1f, 0x22, 0x0d, 0xdf,
    0x2a, 0x78, 0xd5, 0x73, 0x1c, 0xb4, 0x40, 0xa1,
    0xb9, 0x3c, 0xca, 0x58, 0x92, 0x34, 0xcc, 0xce,
    0xd7, 0x42, 0x90, 0x0f, 0x8b, 0x7f, 0x32, 0xed,
    0x5c, 0x9d, 0xc8, 0x99, 0xad, 0x4e, 0x56, 0xa6,
    0xf7, 0x68, 0xb7, 0x25, 0x82, 0x37, 0x3a, 0x51,
    0x69, 0x26, 0x38, 0x52, 0x9e, 0x9a, 0x4f, 0xa7,
    0x43, 0x10, 0x80, 0xee, 0x3d, 0x59, 0x35, 0xcf,
    0x79, 0x74, 0xb5, 0xa2, 0xb1, 0x96, 0x23, 0xe0,
    0xbe, 0x05, 0xf5, 0x6e, 0x19, 0xc5, 0x66, 0x49,
    0xf0, 0xd1, 0x54, 0xa9, 0x70, 0x4b, 0xa4, 0xe2,
    0xe6, 0xe5, 0xab, 0xe4, 0xd2, 0xaa, 0x4c, 0xe3,
    0x06, 0x6f, 0xc6, 0x4a, 0xa4, 0x75, 0x97, 0xe1
};

typedef struct Picture {
    const uint8_t *data;
    size_t length, at;
    uint8_t *visual, *priority;
    uint16_t *queue;
    uint32_t work, commands;
    uint8_t visual_on, priority_on, color, pri_color, pattern;
    int error;
} Picture;

static int spend(Picture *p)
{
    if (p->error) {
        return 0;
    }
    if (p->work == AGI_RUNTIME_PICTURE_MAX_WORK) {
        p->error = AGI_RS_WORK_LIMIT;
        return 0;
    }
    p->work++;
    return 1;
}

static int next(Picture *p, uint8_t *out)
{
    if (p->at == p->length) {
        p->error = AGI_RS_TRUNCATED;
        return 0;
    }
    if (!spend(p)) {
        return 0;
    }
    *out = p->data[p->at++];
    return 1;
}

static int more_coordinates(const Picture *p)
{
    return p->at < p->length && p->data[p->at] < 0xf0;
}

static int pair(Picture *p, int32_t *x, int32_t *y)
{
    uint8_t a, b;
    if (!next(p, &a) || !next(p, &b)) {
        return 0;
    }
    if (a >= 0xf0 || b >= 0xf0) {
        p->error = AGI_RS_BAD_PICTURE;
        return 0;
    }
    *x = a;
    *y = b;
    return 1;
}

static void put(Picture *p, int32_t x, int32_t y)
{
    size_t at;
    if (!spend(p) || x < 0 || y < 0 || x >= (int32_t)W ||
        y >= (int32_t)H) {
        return;
    }
    at = (size_t)y * W + (uint32_t)x;
    if (p->visual_on) {
        p->visual[at] = p->color;
    }
    if (p->priority_on) {
        p->priority[at] = p->pri_color;
    }
}

/* Sarien's integer AGI line, without its separate high-resolution path. */
static void line(Picture *p, int32_t x, int32_t y, int32_t x2, int32_t y2)
{
    int32_t dx, dy, sx, sy, ex, ey, major, i;
    if (x >= (int32_t)W) { x = W - 1; }
    if (x2 >= (int32_t)W) { x2 = W - 1; }
    if (y >= (int32_t)H) { y = H - 1; }
    if (y2 >= (int32_t)H) { y2 = H - 1; }
    sx = x2 >= x ? 1 : -1;
    sy = y2 >= y ? 1 : -1;
    dx = x2 >= x ? x2 - x : x - x2;
    dy = y2 >= y ? y2 - y : y - y2;
    major = dx >= dy ? dx : dy;
    ex = dx >= dy ? 0 : dy / 2;
    ey = dx >= dy ? dx / 2 : 0;
    put(p, x, y);
    for (i = 0; i < major && !p->error; i++) {
        ey += dy;
        if (ey >= major) { ey -= major; y += sy; }
        ex += dx;
        if (ex >= major) { ex -= major; x += sx; }
        put(p, x, y);
    }
}

static int fillable(Picture *p, int32_t x, int32_t y)
{
    size_t at;
    if (!spend(p) || x < 0 || y < 0 || x >= (int32_t)W ||
        y >= (int32_t)H) {
        return 0;
    }
    at = (size_t)y * W + (uint32_t)x;
    if (p->visual_on) {
        return p->color != 15 && p->visual[at] == 15;
    }
    return p->priority_on && p->pri_color != 4 && p->priority[at] == 4;
}

static void flood(Picture *p, int32_t x, int32_t y)
{
    size_t head = 0, tail = 0;
    static const int32_t dx[4] = { -1, 1, 0, 0 };
    static const int32_t dy[4] = { 0, 0, -1, 1 };
    if (!fillable(p, x, y)) {
        return;
    }
    if (!p->queue) {
        p->queue = malloc(N * sizeof(*p->queue));
        if (!p->queue) {
            p->error = AGI_RS_NO_MEMORY;
            return;
        }
    }
    put(p, x, y); /* Mark on insertion: each canvas pixel enters at most once. */
    p->queue[tail++] = (uint16_t)(y * (int32_t)W + x);
    while (head < tail && !p->error) {
        uint16_t at = p->queue[head++];
        uint32_t k;
        x = at % W;
        y = at / W;
        for (k = 0; k < 4 && !p->error; k++) {
            int32_t nx = x + dx[k], ny = y + dy[k];
            if (fillable(p, nx, ny)) {
                put(p, nx, ny);
                p->queue[tail++] = (uint16_t)(ny * (int32_t)W + nx);
            }
        }
    }
}

static void brush(Picture *p, int32_t x, int32_t y, uint8_t seed)
{
    int32_t xx, yy, r = p->pattern & 7;
    uint32_t circle_at = 0, bit = splatter_start[(seed >> 1) & 0x7f];
    if (x < r) { x = r - 1; }
    if (y < r) { y = r; }
    for (yy = y - r; yy <= y + r && !p->error; yy++) {
        for (xx = x - (r + 1) / 2; xx <= x + r / 2 && !p->error; xx++) {
            int selected = (p->pattern & 0x10) ||
                ((circles[r][circle_at >> 3] >> (7 - (circle_at & 7))) & 1);
            circle_at++;
            if (!spend(p)) { return; }
            if (!selected) { continue; }
            if (p->pattern & 0x20) {
                if ((splatter_map[bit >> 3] >> (7 - (bit & 7))) & 1) {
                    put(p, xx, yy);
                }
                if (++bit == 0xff) { bit = 0; }
            } else {
                put(p, xx, yy);
            }
        }
    }
}

static int picture_commands(Picture *p)
{
    uint8_t op, value;
    int32_t x, y, nx, ny;
    while (next(p, &op)) {
        uint32_t axis;
        p->commands++;
        switch (op) {
        case 0xf0:
        case 0xf2:
        case 0xf9:
            if (!next(p, &value)) { return p->error; }
            if (op == 0xf0) { p->visual_on = 1; p->color = value & 15; }
            if (op == 0xf2) { p->priority_on = 1; p->pri_color = value & 15; }
            if (op == 0xf9) { p->pattern = value; }
            break;
        case 0xf1: p->visual_on = 0; break;
        case 0xf3: p->priority_on = 0; break;
        case 0xf4:
        case 0xf5:
        case 0xf6:
        case 0xf7:
            if (!pair(p, &x, &y)) { return p->error; }
            put(p, x, y);
            axis = 0;
            while (more_coordinates(p) && !p->error) {
                nx = x; ny = y;
                if (op == 0xf6) {
                    if (!pair(p, &nx, &ny)) { return p->error; }
                } else if (op == 0xf7) {
                    if (!next(p, &value)) { return p->error; }
                    nx += (value & 0x80 ? -1 : 1) * ((value >> 4) & 7);
                    ny += (value & 0x08 ? -1 : 1) * (value & 7);
                } else {
                    if (!next(p, &value)) { return p->error; }
                    if (((axis++ & 1) == 0) == (op == 0xf4)) { ny = value; }
                    else { nx = value; }
                }
                line(p, x, y, nx, ny);
                x = nx; y = ny;
            }
            break;
        case 0xf8:
            while (more_coordinates(p) && !p->error) {
                if (!pair(p, &x, &y)) { return p->error; }
                flood(p, x, y);
            }
            break;
        case 0xfa:
            while (more_coordinates(p) && !p->error) {
                value = 0;
                if ((p->pattern & 0x20) && !next(p, &value)) { return p->error; }
                if (!pair(p, &x, &y)) { return p->error; }
                brush(p, x, y, value);
            }
            break;
        case 0xff: return AGI_RS_SUCCESS;
        default: return AGI_RS_BAD_PICTURE;
        }
        if (p->error) { return p->error; }
    }
    return p->error;
}

int agi_runtime_decode_picture(const uint8_t *data, size_t length, int clear,
                               uint8_t *visual, uint8_t *priority,
                               size_t plane_size, AgiRuntimePictureInfo *info)
{
    Picture p;
    uint8_t *image;
    int result;
    if (!data || !length || length > AGI_RUNTIME_RESOURCE_MAX ||
        (clear != 0 && clear != 1) || !planes(visual, priority, plane_size) ||
        overlap(data, length, visual, N) || overlap(data, length, priority, N) ||
        (info && (overlap(info, sizeof(*info), visual, N) ||
                  overlap(info, sizeof(*info), priority, N) ||
                  overlap(info, sizeof(*info), data, length)))) {
        return AGI_RS_BAD_ARGUMENT;
    }
    if (!clear && (!palette(visual, N) || !palette(priority, N))) {
        return AGI_RS_BAD_PALETTE;
    }
    image = malloc(2 * N);
    if (!image) { return AGI_RS_NO_MEMORY; }
    if (clear) {
        memset(image, 15, N); memset(image + N, 4, N);
    } else {
        memcpy(image, visual, N); memcpy(image + N, priority, N);
    }
    memset(&p, 0, sizeof(p));
    p.data = data; p.length = length; p.visual = image; p.priority = image + N;
    p.color = 15; p.pri_color = 4;
    result = picture_commands(&p);
    if (result == AGI_RS_SUCCESS) {
        memcpy(visual, image, N); memcpy(priority, image + N, N);
        if (info) {
            info->bytes_consumed = p.at;
            info->commands = p.commands;
            info->work_units = p.work;
        }
    }
    free(p.queue); free(image);
    return result;
}

typedef struct ViewSelection {
    AgiRuntimeViewCel info;
    size_t start, limit;
    int selected;
} ViewSelection;

static uint32_t word(const uint8_t *data, size_t at)
{
    return data[at] | (uint32_t)data[at + 1] << 8;
}

static int span_overlap(size_t a, size_t an, size_t b, size_t bn)
{
    return a <= b ? b - a < an : a - b < bn;
}

static int view_select(const uint8_t *data, size_t length, uint32_t loop,
                        uint32_t cel, ViewSelection *out)
{
    uint32_t i, j, count;
    size_t directory, description, description_size = 0;
    ViewSelection v;
    if (!data || length < 5 || length > AGI_RUNTIME_RESOURCE_MAX) {
        return AGI_RS_BAD_VIEW;
    }
    count = data[2]; directory = 5 + (size_t)count * 2;
    if (!count || directory > length) { return AGI_RS_BAD_VIEW; }
    description = word(data, 3);
    if (description) {
        const uint8_t *end;
        if (description < directory || description >= length) {
            return AGI_RS_BAD_VIEW;
        }
        end = memchr(data + description, 0, length - description);
        if (!end) { return AGI_RS_BAD_VIEW; }
        description_size = (size_t)(end - (data + description)) + 1;
    }
    memset(&v, 0, sizeof(v));
    v.info.geometry.loop_count = count;
    v.limit = length;
    for (i = 0; i < count; i++) {
        size_t lo = word(data, 5 + (size_t)i * 2), header;
        uint32_t cels;
        if (lo < directory || lo >= length) { return AGI_RS_BAD_VIEW; }
        cels = data[lo]; header = 1 + (size_t)cels * 2;
        if (header > length - lo ||
            (description && span_overlap(lo, header, description, description_size))) {
            return AGI_RS_BAD_VIEW;
        }
        if (i == loop) { v.info.geometry.cel_count = cels; }
        for (j = 0; j < cels; j++) {
            size_t relative = word(data, lo + 1 + (size_t)j * 2);
            size_t at = lo + relative;
            if (relative < header || at > length - 3 ||
                !data[at] || data[at] > W || !data[at + 1] || data[at + 1] > H ||
                (description && span_overlap(at, 3, description, description_size))) {
                return AGI_RS_BAD_VIEW;
            }
            if (i == loop && j == cel) {
                v.selected = 1; v.start = at;
                v.info.geometry.width = data[at];
                v.info.geometry.height = data[at + 1];
                v.info.transparent = data[at + 2] & 15;
                v.info.mirrored = !!((data[at + 2] & 0x80) &&
                    ((data[at + 2] >> 4) & 7) != loop);
                v.info.data_offset = at + 3;
            }
        }
    }
    if (v.selected) {
        if (description > v.start && description < v.limit) {
            v.limit = description;
        }
        for (i = 0; i < count; i++) {
            size_t lo = word(data, 5 + (size_t)i * 2);
            size_t header = 1 + (size_t)data[lo] * 2;
            if (span_overlap(v.start, 3, lo, header)) { return AGI_RS_BAD_VIEW; }
            if (lo > v.start && lo < v.limit) { v.limit = lo; }
            for (j = 0; j < data[lo]; j++) {
                size_t at = lo + word(data, lo + 1 + (size_t)j * 2);
                if (at > v.start && at < v.limit) { v.limit = at; }
            }
        }
        if (v.limit - v.start < 3) { return AGI_RS_BAD_VIEW; }
    }
    *out = v;
    return AGI_RS_SUCCESS;
}

static int view_pixels(const uint8_t *data, ViewSelection *v, uint8_t *pixels)
{
    uint32_t row, width = v->info.geometry.width, height = v->info.geometry.height;
    size_t at = v->info.data_offset;
    if (pixels) { memset(pixels, v->info.transparent, (size_t)width * height); }
    for (row = 0; row < height; row++) {
        uint32_t x = 0;
        for (;;) {
            uint8_t run;
            uint32_t n, j;
            if (at == v->limit) { return AGI_RS_TRUNCATED; }
            run = data[at++];
            if (!run) { break; }
            n = run & 15;
            if (!n || n > width - x) { return AGI_RS_BAD_VIEW; }
            if (pixels) {
                for (j = 0; j < n; j++) {
                    uint32_t column = v->info.mirrored ? width - 1 - (x + j) : x + j;
                    pixels[(size_t)row * width + column] = run >> 4;
                }
            }
            x += n;
        }
    }
    v->info.bytes_consumed = at - v->start;
    return AGI_RS_SUCCESS;
}

int agi_runtime_view_geometry(const uint8_t *data, size_t length,
                              uint32_t loop, uint32_t cel,
                              AgiRuntimeGeometry *out)
{
    ViewSelection v;
    int result;
    if (!out || (data && overlap(out, sizeof(*out), data, length))) {
        return AGI_RS_BAD_ARGUMENT;
    }
    result = view_select(data, length, loop, cel, &v);
    if (result) { return result; }
    if (v.selected && (result = view_pixels(data, &v, NULL))) { return result; }
    *out = v.info.geometry;
    return AGI_RS_SUCCESS;
}

int agi_runtime_view_cel(const uint8_t *data, size_t length,
                         uint32_t loop, uint32_t cel, uint8_t *pixels,
                         size_t pixel_capacity, AgiRuntimeViewCel *info)
{
    ViewSelection v;
    uint8_t *temporary;
    size_t count;
    int result = view_select(data, length, loop, cel, &v);
    if (result) { return result; }
    if (!v.selected) { return AGI_RS_BAD_SELECTION; }
    count = (size_t)v.info.geometry.width * v.info.geometry.height;
    if (!pixels || pixel_capacity < count || overlap(pixels, count, data, length) ||
        (info && (overlap(info, sizeof(*info), pixels, count) ||
                  overlap(info, sizeof(*info), data, length)))) {
        return AGI_RS_BAD_ARGUMENT;
    }
    temporary = malloc(count);
    if (!temporary) { return AGI_RS_NO_MEMORY; }
    result = view_pixels(data, &v, temporary);
    if (!result) {
        memcpy(pixels, temporary, count);
        if (info) { *info = v.info; }
    }
    free(temporary);
    return result;
}

static int cel_arguments(const uint8_t *pixels, size_t size, uint32_t width,
                         uint32_t height, uint32_t transparent, uint32_t priority)
{
    return pixels && width && width <= W && height && height <= H &&
        size == (size_t)width * height && transparent <= 15 && priority <= 15;
}

static int pose(int32_t x, int32_t y, uint32_t width, uint32_t height)
{
    return x >= 0 && y >= (int32_t)height - 1 &&
        (uint32_t)x <= W - width && y < (int32_t)H;
}

/* One priority rule for decoded sprites, full composition and add.to.pic. */
static int blit_pixel(uint8_t *visual, uint8_t *priority, size_t at,
                      uint8_t color, uint32_t sprite_priority)
{
    uint8_t real = priority[at], effective = real;
    if (real < 3) {
        size_t below = at;
        while (below < N && priority[below] < 3) { below += W; }
        effective = below < N ? priority[below] : 4;
    }
    if (sprite_priority < effective) { return 0; }
    visual[at] = color;
    if (real >= 3) { priority[at] = (uint8_t)sprite_priority; }
    return 1;
}

static AgiRuntimeBlitInfo blit(uint8_t *visual, uint8_t *priority,
                               const uint8_t *pixels, uint32_t width,
                               uint32_t height, uint32_t transparent,
                               uint32_t x, uint32_t top, uint32_t sprite_priority)
{
    AgiRuntimeBlitInfo info = { 0, 1 };
    uint32_t row, column;
    for (row = 0; row < height && top + row < H; row++) {
        for (column = 0; column < width && x + column < W; column++) {
            uint8_t color = pixels[(size_t)row * width + column];
            size_t at = (size_t)(top + row) * W + x + column;
            if (color != transparent &&
                blit_pixel(visual, priority, at, color, sprite_priority)) {
                info.written_pixels++; info.hidden = 0;
            }
        }
    }
    return info;
}

static int blit_inputs(uint8_t *visual, uint8_t *priority, size_t plane_size,
                       const uint8_t *pixels, size_t pixel_size, uint32_t width,
                       uint32_t height, uint32_t transparent, uint32_t spr,
                       AgiRuntimeBlitInfo *info)
{
    if (!planes(visual, priority, plane_size) ||
        !cel_arguments(pixels, pixel_size, width, height, transparent, spr) ||
        overlap(pixels, pixel_size, visual, N) ||
        overlap(pixels, pixel_size, priority, N) ||
        (info && (overlap(info, sizeof(*info), visual, N) ||
                  overlap(info, sizeof(*info), priority, N) ||
                  overlap(info, sizeof(*info), pixels, pixel_size)))) {
        return AGI_RS_BAD_ARGUMENT;
    }
    if (!palette(visual, N) || !palette(priority, N) || !palette(pixels, pixel_size)) {
        return AGI_RS_BAD_PALETTE;
    }
    return AGI_RS_SUCCESS;
}

int agi_runtime_scene_blit(uint8_t *visual, uint8_t *priority, size_t plane_size,
                           const uint8_t *pixels, size_t pixel_size,
                           uint32_t width, uint32_t height, uint32_t transparent,
                           int32_t x, int32_t baseline, uint32_t sprite_priority,
                           AgiRuntimeBlitInfo *info)
{
    AgiRuntimeBlitInfo result;
    int status = blit_inputs(visual, priority, plane_size, pixels, pixel_size,
                             width, height, transparent, sprite_priority, info);
    if (status) { return status; }
    if (!pose(x, baseline, width, height)) { return AGI_RS_BAD_GEOMETRY; }
    /* All validation precedes mutation; the bounded raster cannot fail. */
    result = blit(visual, priority, pixels, width, height, transparent,
                  (uint32_t)x, (uint32_t)baseline - height + 1, sprite_priority);
    if (info) { *info = result; }
    return AGI_RS_SUCCESS;
}

static int sort_y(const AgiRuntimeWorld *world, const AgiRuntimeActor *actor)
{
    int y;
    if (!(actor->flags & AGI_RA_FIXED_PRIORITY)) { return actor->y; }
    for (y = H - 1; y >= 0; y--) {
        if (world->priority_bands[y] < actor->priority) { return y; }
    }
    return -1;
}

static int precedes(const AgiRuntimeWorld *world, uint16_t left, uint16_t right)
{
    const AgiRuntimeActor *a = &world->actors[left], *b = &world->actors[right];
    int au = !!(a->flags & AGI_RA_UPDATE), bu = !!(b->flags & AGI_RA_UPDATE);
    int ay, by;
    if (au != bu) { return au < bu; }
    ay = sort_y(world, a); by = sort_y(world, b);
    return ay != by ? ay < by : left < right;
}

int agi_runtime_scene_compose(const AgiRuntimeWorld *world,
                              const uint8_t *background_visual,
                              const uint8_t *background_priority,
                              size_t plane_size, AgiRuntimeViewSource source,
                              void *opaque, uint8_t *visual, uint8_t *priority,
                              AgiRuntimeSceneInfo *info)
{
    AgiRuntimeSceneInfo result;
    uint8_t *image, *cel;
    uint32_t id, i;
    int status = AGI_RS_SUCCESS;
    if (!world || !source || !background_visual || !background_priority ||
        !planes(visual, priority, plane_size) ||
        overlap(background_visual, N, background_priority, N) ||
        overlap(world, sizeof(*world), visual, N) ||
        overlap(world, sizeof(*world), priority, N) ||
        (visual != background_visual && overlap(visual, N, background_visual, N)) ||
        (priority != background_priority && overlap(priority, N, background_priority, N)) ||
        overlap(visual, N, background_priority, N) ||
        overlap(priority, N, background_visual, N) ||
        (info && (overlap(info, sizeof(*info), visual, N) ||
                  overlap(info, sizeof(*info), priority, N) ||
                  overlap(info, sizeof(*info), background_visual, N) ||
                  overlap(info, sizeof(*info), background_priority, N) ||
                  overlap(info, sizeof(*info), world, sizeof(*world))))) {
        return AGI_RS_BAD_ARGUMENT;
    }
    if (!palette(background_visual, N) || !palette(background_priority, N) ||
        !palette(world->priority_bands, H)) { return AGI_RS_BAD_PALETTE; }
    memset(&result, 0, sizeof(result));
    for (id = 0; id < AGI_RUNTIME_ACTORS; id++) {
        const AgiRuntimeActor *a = &world->actors[id];
        uint32_t needed = AGI_RA_ANIMATED | AGI_RA_DRAWN;
        if ((a->flags & needed) != needed) { continue; }
        if (a->view > 255 || a->loop > 255 || a->cel > 255 || a->priority > 15) {
            return AGI_RS_BAD_ARGUMENT;
        }
        if (!world->loaded_views[a->view]) { continue; }
        if (!(a->flags & AGI_RA_VIEW_BOUND) || !a->width || a->width > W ||
            !a->height || a->height > H || !pose(a->x, a->y, a->width, a->height)) {
            return AGI_RS_BAD_GEOMETRY;
        }
        i = result.actor_count++;
        while (i && precedes(world, (uint16_t)id, result.draw_order[i - 1])) {
            result.draw_order[i] = result.draw_order[i - 1]; i--;
        }
        result.draw_order[i] = (uint16_t)id;
    }
    image = malloc(3 * N);
    if (!image) { return AGI_RS_NO_MEMORY; }
    cel = image + 2 * N;
    memcpy(image, background_visual, N); memcpy(image + N, background_priority, N);
    for (i = 0; i < result.actor_count; i++) {
        const AgiRuntimeActor *a = &world->actors[result.draw_order[i]];
        const uint8_t *data = NULL;
        size_t length = 0;
        AgiRuntimeViewCel c;
        AgiRuntimeBlitInfo b;
        if (source(opaque, (uint8_t)a->view, &data, &length) != 1) {
            status = AGI_RS_MISSING_VIEW; break;
        }
        if (data && (overlap(data, length, visual, N) ||
                     overlap(data, length, priority, N) ||
                     (info && overlap(data, length, info, sizeof(*info))))) {
            status = AGI_RS_BAD_ARGUMENT; break;
        }
        status = agi_runtime_view_cel(data, length, a->loop, a->cel, cel, N, &c);
        if (status) { break; }
        if (c.geometry.width != a->width || c.geometry.height != a->height ||
            c.geometry.loop_count != a->loop_count || c.geometry.cel_count != a->cel_count) {
            status = AGI_RS_BAD_GEOMETRY; break;
        }
        b = blit(image, image + N, cel, a->width, a->height, c.transparent,
                  (uint32_t)a->x, (uint32_t)a->y - a->height + 1, a->priority);
        result.written_pixels += b.written_pixels;
        result.hidden[result.draw_order[i]] = (uint8_t)b.hidden;
    }
    if (!status) {
        memcpy(visual, image, N); memcpy(priority, image + N, N);
        if (info) { *info = result; }
    }
    free(image);
    return status;
}

static void control_pixel(uint8_t *priority, uint32_t x, uint32_t y, uint32_t margin)
{
    size_t at = (size_t)y * W + x;
    if (priority[at] >= 4) { priority[at] = (uint8_t)margin; }
}

int agi_runtime_add_to_picture(uint8_t *visual, uint8_t *priority,
                               size_t plane_size, const uint8_t *pixels,
                               size_t pixel_size, uint32_t width,
                               uint32_t height, uint32_t transparent,
                               int32_t x, int32_t baseline,
                               uint32_t sprite_priority, uint32_t margin,
                               const uint8_t *bands, size_t bands_size,
                               AgiRuntimeBlitInfo *info)
{
    AgiRuntimeBlitInfo result;
    uint32_t top, bottom, right, upper, row, column;
    int status = blit_inputs(visual, priority, plane_size, pixels, pixel_size,
                             width, height, transparent, sprite_priority, info);
    if (status) { return status; }
    if (!bands || bands_size != H || margin > 255 ||
        overlap(bands, H, visual, N) || overlap(bands, H, priority, N) ||
        (info && overlap(info, sizeof(*info), bands, H))) {
        return AGI_RS_BAD_ARGUMENT;
    }
    if (!palette(bands, H)) { return AGI_RS_BAD_PALETTE; }
    if (x < 0 || x >= (int32_t)W || baseline < 0 || baseline >= (int32_t)H) {
        return AGI_RS_BAD_GEOMETRY;
    }
    if (!sprite_priority) { sprite_priority = bands[baseline]; }
    top = baseline < (int32_t)height - 1 ? 0 : (uint32_t)baseline - height + 1;
    bottom = top + height - 1;
    if (bottom >= H) { bottom = H - 1; }
    right = (uint32_t)x + width - 1;
    if (right >= W) { right = W - 1; }
    result = blit(visual, priority, pixels, width, height, transparent,
                  (uint32_t)x, top, sprite_priority);
    if (margin < 4) {
        upper = (bottom / 12) * 12 + 1;
        for (row = upper; row <= bottom; row++) {
            control_pixel(priority, (uint32_t)x, row, margin);
            control_pixel(priority, right, row, margin);
        }
        for (column = (uint32_t)x; column <= right; column++) {
            control_pixel(priority, column, upper, margin);
            control_pixel(priority, column, bottom, margin);
        }
    }
    if (info) { *info = result; }
    return AGI_RS_SUCCESS;
}

const char *agi_runtime_scene_error(int result)
{
    switch (result) {
    case AGI_RS_SUCCESS: return "success";
    case AGI_RS_BAD_ARGUMENT: return "invalid scene argument or overlapping output";
    case AGI_RS_NO_MEMORY: return "scene transaction allocation failed";
    case AGI_RS_TRUNCATED: return "truncated picture or VIEW cel";
    case AGI_RS_BAD_PICTURE: return "invalid AGI v2 picture stream";
    case AGI_RS_WORK_LIMIT: return "picture work limit exhausted";
    case AGI_RS_BAD_VIEW: return "invalid AGI v2 VIEW resource";
    case AGI_RS_BAD_SELECTION: return "VIEW loop or cel is absent";
    case AGI_RS_MISSING_VIEW: return "loaded VIEW bytes are absent";
    case AGI_RS_BAD_GEOMETRY: return "cel geometry or scene placement is invalid";
    case AGI_RS_BAD_PALETTE: return "palette index exceeds 15";
    default: return "unknown scene error";
    }
}
