/* SPDX-License-Identifier: GPL-2.0-only
 * Bounded AGI v2 pictures, VIEW cels and scene composition.
 * Adapted from Sarien; see RUNTIME_SCENE_PROVENANCE.md and COPYING.sarien.txt.
 */
#ifndef FDISBULL_AGI_RUNTIME_SCENE_H
#define FDISBULL_AGI_RUNTIME_SCENE_H

#include <stddef.h>
#include <stdint.h>
#include "runtime_actor.h"

#define AGI_RUNTIME_RESOURCE_MAX (2u * 1024u * 1024u)
#define AGI_RUNTIME_PICTURE_MAX_WORK 20000000u

enum AgiRuntimeSceneResult {
    AGI_RS_SUCCESS = 0, AGI_RS_BAD_ARGUMENT = -1,
    AGI_RS_NO_MEMORY = -2, AGI_RS_TRUNCATED = -3,
    AGI_RS_BAD_PICTURE = -4, AGI_RS_WORK_LIMIT = -5,
    AGI_RS_BAD_VIEW = -6, AGI_RS_BAD_SELECTION = -7,
    AGI_RS_MISSING_VIEW = -8, AGI_RS_BAD_GEOMETRY = -9,
    AGI_RS_BAD_PALETTE = -10
};

typedef struct AgiRuntimePictureInfo {
    size_t bytes_consumed;
    uint32_t commands, work_units;
} AgiRuntimePictureInfo;

typedef struct AgiRuntimeViewCel {
    AgiRuntimeGeometry geometry;
    uint32_t transparent, mirrored;
    size_t data_offset, bytes_consumed;
} AgiRuntimeViewCel;

typedef struct AgiRuntimeBlitInfo {
    uint32_t written_pixels, hidden;
} AgiRuntimeBlitInfo;

typedef struct AgiRuntimeSceneInfo {
    uint32_t actor_count, written_pixels;
    uint16_t draw_order[AGI_RUNTIME_ACTORS];
    uint8_t hidden[AGI_RUNTIME_ACTORS];
} AgiRuntimeSceneInfo;

typedef struct AgiRuntimeSceneOrder {
    uint32_t actor_count;
    uint16_t draw_order[AGI_RUNTIME_ACTORS];
} AgiRuntimeSceneOrder;

/* Return 1 for immutable raw VIEW bytes and 0 when the resource is absent.
 * This callback is read-only; it must not mutate its inputs or the world. */
typedef int (*AgiRuntimeViewSource)(void *opaque, uint8_t view,
                                  const uint8_t **data, size_t *length);

/* All public functions commit outputs only on success. Pointers must denote
 * accessible C objects of the specified sizes. Independent output objects
 * must not overlap. info may be NULL. No function performs I/O or presentation.
 *
 * Decode/replay F0..FA/FF AGI v2 picture commands. clear=1 starts at visual15 /
 * priority4; clear=0 executes the vector stream against the supplied planes,
 * including fills against the existing image. Both planes are exactly 160x168.
 * A terminator is required; bytes after it are left unconsumed. Work and input
 * are bounded by the constants above; failure preserves both input planes. */
int agi_runtime_decode_picture(const uint8_t *data, size_t length, int clear,
                               uint8_t *visual, uint8_t *priority,
                               size_t plane_size, AgiRuntimePictureInfo *info);

/* Inspect a resource and selected geometry. An out-of-range loop/cel is a
 * successful partial result: loop_count is always given, cel_count for a
 * valid loop, and width/height for a valid cel. Selected cel RLE is checked.
 * Invalid resource data leaves out unchanged. This directly supports the
 * actor module's partial-geometry callback contract. */
int agi_runtime_view_geometry(const uint8_t *data, size_t length,
                              uint32_t loop, uint32_t cel,
                              AgiRuntimeGeometry *out);

/* Decode one selected cel into row-major palette indices. Short RLE rows are
 * padded with transparency. Mirroring is resolved here, once; the result must
 * not be mirrored again by the compositor. Writes width*height bytes at most
 * AGI_RUNTIME_PLANE_BYTES; remaining capacity is unchanged. */
int agi_runtime_view_cel(const uint8_t *data, size_t length,
                         uint32_t loop, uint32_t cel, uint8_t *pixels,
                         size_t pixel_capacity, AgiRuntimeViewCel *info);

/* Blit one already oriented cel. The complete rectangle must fit; position
 * repair belongs to actor semantics. Control priorities0..2 are preserved and
 * read through downwards; water3 is replaced by a passing sprite priority. */
int agi_runtime_scene_blit(uint8_t *visual, uint8_t *priority, size_t plane_size,
                           const uint8_t *pixels, size_t pixel_size,
                           uint32_t width, uint32_t height, uint32_t transparent,
                           int32_t x, int32_t baseline, uint32_t sprite_priority,
                           AgiRuntimeBlitInfo *info);

/* Select and order current actors using the same state checks as composition.
 * This validates state geometry and priority bands, not resource bytes or
 * raster visibility. It performs no decoding, drawing, mutation or allocation.
 * Failure preserves out; out must not overlap world. */
int agi_runtime_scene_order(const AgiRuntimeWorld *world,
                            AgiRuntimeSceneOrder *out);

/* Compose from persistent background, not a previously composited frame.
 * This makes draw/erase/move/cycle changes remove previous sprite pixels.
 * Include animated+drawn actors with loaded VIEWs. Non-updating actors precede
 * updating actors. Each group sorts by baseline (fixed priority uses the
 * priority band's preceding row), then ascending actor ID. Stored actor
 * priority is authoritative. Active geometry must match decoded VIEW data.
 * Output planes may equal the corresponding background inputs exactly. */
int agi_runtime_scene_compose(const AgiRuntimeWorld *world,
                              const uint8_t *background_visual,
                              const uint8_t *background_priority,
                              size_t plane_size, AgiRuntimeViewSource source,
                              void *opaque, uint8_t *visual, uint8_t *priority,
                              AgiRuntimeSceneInfo *info);

/* Persist a cel into background planes. Priority0 selects bands[baseline].
 * Margin0..3 adds a control rectangle from the start of the nominal twelve-row
 * band (+1, Sarien's AGI2 rule) to the baseline, preserving existing controls
 * 0..3. Margin>=4 omits the rectangle. A cel extending above the picture is
 * moved down to top0, as in Sarien; right/bottom pixels are safely clipped.
 * x/baseline must themselves be in bounds. The compositor adds actors later. */
int agi_runtime_add_to_picture(uint8_t *visual, uint8_t *priority,
                               size_t plane_size, const uint8_t *pixels,
                               size_t pixel_size, uint32_t width,
                               uint32_t height, uint32_t transparent,
                               int32_t x, int32_t baseline,
                               uint32_t sprite_priority, uint32_t margin,
                               const uint8_t *bands, size_t bands_size,
                               AgiRuntimeBlitInfo *info);

const char *agi_runtime_scene_error(int result);
#endif
