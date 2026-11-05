#include "../state/sherlock_images.h"

#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>

/* Authored sentinels, not original image bytes. The first pixels identify the
 * tile and fixture independently of the body pattern. Every row, empty image
 * and clue marker can therefore be distinguished after a copy or rollback. */
static uint8_t initial[SH_IMAGES_PIXEL_BYTES];
static uint8_t imported[SH_IMAGES_PIXEL_BYTES];
static uint8_t expected[SH_IMAGES_PIXEL_BYTES];
static uint8_t saved[SH_IMAGES_PIXEL_BYTES];
static uint8_t bad[SH_IMAGES_PIXEL_BYTES];
static SHImageEdit edit, before;
static unsigned rejection_count;

static void fixture(uint8_t *pixels, unsigned tag) {
    unsigned tile, y, x;
    for (tile = 0; tile < SHI_IMAGE_COUNT; ++tile) {
        uint8_t *image = pixels + tile * SH_IMAGES_TILE_BYTES;
        for (y = 0; y < SHI_HEIGHT; ++y)
            for (x = 0; x < SHI_WIDTH; ++x)
                image[y * SHI_WIDTH + x] =
                    (uint8_t)((tag + tile * 3 + x * 5 + y * 7 + (x ^ y)) & 15);
        image[0] = (uint8_t)(tile & 15);
        image[1] = (uint8_t)(tile >> 4);
        image[2] = (uint8_t)tag;
    }
}

static void begin(void) {
    assert(sh_images_begin(&edit, initial, sizeof initial) == 0);
    assert(memcmp(edit.images, initial, sizeof initial) == 0);
    assert(memcmp(edit.entry, initial, sizeof initial) == 0);
    assert(edit.dirty == 0);
}

static void image_is(unsigned tile, const uint8_t *source, unsigned source_tile) {
    assert(memcmp(edit.images[tile], source + source_tile * SH_IMAGES_TILE_BYTES,
                  SH_IMAGES_TILE_BYTES) == 0);
}

#define REJECT_UNCHANGED(operation) do { \
    memcpy(&before, &edit, sizeof before); \
    assert((operation) == -1); \
    assert(memcmp(&before, &edit, sizeof before) == 0); \
    ++rejection_count; \
} while (0)

static void row_and_empty_merges(void) {
    unsigned from, to, tile;
    for (from = 0; from < 6; ++from) {
        for (to = 0; to < 6; ++to) {
            begin();
            assert(sh_images_merge_row(&edit, imported, sizeof imported, from, to) == 0);
            for (tile = 0; tile < SHI_IMAGE_COUNT; ++tile) {
                if (tile / 6 == to && tile < 36)
                    image_is(tile, imported, from * 6 + tile % 6);
                else image_is(tile, initial, tile);
            }
            assert(edit.dirty == 1);
            assert(memcmp(edit.entry, initial, sizeof initial) == 0);

            /* The same selection contract also works when the source set is
             * the working set, including an unchanged same-row merge. */
            begin();
            assert(sh_images_merge_row(&edit, (const uint8_t *)edit.images,
                                       sizeof edit.images, from, to) == 0);
            for (tile = 0; tile < SHI_IMAGE_COUNT; ++tile)
                image_is(tile, initial, tile < 36 && tile / 6 == to
                         ? from * 6 + tile % 6 : tile);
            assert(edit.dirty == 1);
            assert(memcmp(edit.entry, initial, sizeof initial) == 0);
        }
    }
    begin();
    assert(sh_images_merge_empty(&edit, imported, sizeof imported) == 0);
    for (tile = 0; tile < SHI_IMAGE_COUNT; ++tile)
        image_is(tile, tile == 36 ? imported : initial, tile);
    assert(edit.dirty == 1);
    assert(sh_images_saved(&edit) == 0 && edit.dirty == 0);
    assert(sh_images_merge_empty(&edit, (const uint8_t *)edit.images,
                                sizeof edit.images) == 0);
    assert(edit.dirty == 1);
}

static void copying_and_pixel_acceptance(void) {
    static const unsigned pairs[][2] = {{0, 36}, {36, 0}, {17, 35}, {0, 0}};
    unsigned i, tile;
    for (i = 0; i < sizeof pairs / sizeof pairs[0]; ++i) {
        begin();
        assert(sh_images_copy_tile(&edit, pairs[i][0], pairs[i][1]) == 0);
        for (tile = 0; tile < SHI_IMAGE_COUNT; ++tile)
            image_is(tile, initial, tile == pairs[i][1] ? pairs[i][0] : tile);
        assert(edit.dirty == 1);
        assert(memcmp(edit.entry, initial, sizeof initial) == 0);
    }

    begin();
    assert(sh_images_replace_tile(&edit, 36, imported + 36 * SH_IMAGES_TILE_BYTES,
                                   SH_IMAGES_TILE_BYTES) == 0);
    for (tile = 0; tile < SHI_IMAGE_COUNT; ++tile)
        image_is(tile, tile == 36 ? imported : initial, tile);
    assert(edit.dirty == 1);

    begin();
    /* Pixel INIT or paint-to-the-existing-color is an accepted operation even
     * when it returns identical pixels. An untouched pixel dialog makes no
     * call; a nested Abort likewise leaves the overview alone. */
    assert(sh_images_replace_tile(&edit, 0, initial, SH_IMAGES_TILE_BYTES) == 0);
    assert(memcmp(edit.images, initial, sizeof initial) == 0);
    assert(edit.dirty == 1);
    assert(sh_images_saved(&edit) == 0 && edit.dirty == 0);
    assert(memcmp(edit.images, initial, sizeof initial) == 0);
}

static void transactions(void) {
    begin();
    assert(sh_images_replace_tile(&edit, 0, imported, SH_IMAGES_TILE_BYTES) == 0);
    /* Model an already completed external save. This test qualifies the state
     * acknowledgement and rollback; it does not claim to test filesystem I/O. */
    memcpy(saved, edit.images, sizeof saved);
    assert(sh_images_saved(&edit) == 0 && edit.dirty == 0);
    assert(memcmp(edit.entry, initial, sizeof initial) == 0);
    assert(sh_images_replace_tile(&edit, 1, imported + SH_IMAGES_TILE_BYTES,
                                   SH_IMAGES_TILE_BYTES) == 0);
    assert(edit.dirty == 1);
    assert(sh_images_abort(&edit) == 0);
    assert(memcmp(edit.images, initial, sizeof initial) == 0);
    assert(edit.dirty == 0);
    assert(memcmp(saved, imported, SH_IMAGES_TILE_BYTES) == 0);
    assert(memcmp(saved + SH_IMAGES_TILE_BYTES, initial + SH_IMAGES_TILE_BYTES,
                  sizeof saved - SH_IMAGES_TILE_BYTES) == 0);

    begin();
    assert(sh_images_copy_tile(&edit, 0, 1) == 0);
    assert(sh_images_load(&edit, imported, sizeof imported) == 0);
    assert(edit.dirty == 0);
    assert(memcmp(edit.images, imported, sizeof imported) == 0);
    assert(memcmp(edit.entry, initial, sizeof initial) == 0);
    /* Full rollback is a deliberate native correction: the original restores
     * editable tiles 0..36 but can retain imported clue markers 37..45. */
    assert(sh_images_abort(&edit) == 0);
    assert(memcmp(edit.images, initial, sizeof initial) == 0);

    /* Defaults uses the same complete-set acceptance as a successful Load.
     * The entry snapshot remains intact until a new overview visit begins. */
    assert(sh_images_begin(&edit, imported, sizeof imported) == 0);
    assert(sh_images_copy_tile(&edit, 1, 2) == 0);
    assert(sh_images_load(&edit, initial, sizeof initial) == 0);
    assert(edit.dirty == 0);
    assert(sh_images_abort(&edit) == 0);
    assert(memcmp(edit.images, imported, sizeof imported) == 0);

    /* Re-entering the overview keeps accepted working pixels but resets the
     * operation flag and snapshots that new entry, as the original does. */
    assert(sh_images_copy_tile(&edit, 0, 36) == 0);
    memcpy(expected, edit.images, sizeof expected);
    assert(sh_images_begin(&edit, (const uint8_t *)edit.images, sizeof edit.images) == 0);
    assert(edit.dirty == 0);
    assert(memcmp(edit.images, expected, sizeof expected) == 0);
    assert(memcmp(edit.entry, expected, sizeof expected) == 0);
}

static void aliasing(void) {
    const uint8_t *overlapping;
    begin();
    assert(sh_images_load(&edit, imported, sizeof imported) == 0);
    assert(sh_images_begin(&edit, (const uint8_t *)edit.entry, sizeof edit.entry) == 0);
    assert(memcmp(edit.images, initial, sizeof initial) == 0);
    assert(memcmp(edit.entry, initial, sizeof initial) == 0);

    /* A complete source set can overlap the destination and extend into the
     * untouched entry array. Validation must precede all writes. */
    overlapping = (const uint8_t *)&edit + offsetof(SHImageEdit, images) + 32;
    memcpy(expected, overlapping, sizeof expected);
    assert(sh_images_load(&edit, overlapping, sizeof expected) == 0);
    assert(memcmp(edit.images, expected, sizeof expected) == 0);
    assert(memcmp(edit.entry, initial, sizeof initial) == 0);

    begin();
    overlapping = (const uint8_t *)&edit + offsetof(SHImageEdit, images) + 17;
    memcpy(expected, overlapping, sizeof expected);
    assert(sh_images_begin(&edit, overlapping, sizeof expected) == 0);
    assert(memcmp(edit.images, expected, sizeof expected) == 0);
    assert(memcmp(edit.entry, expected, sizeof expected) == 0);

    begin();
    memcpy(expected, initial + 1, SH_IMAGES_TILE_BYTES);
    assert(sh_images_replace_tile(&edit, 0, (const uint8_t *)edit.images + 1,
                                   SH_IMAGES_TILE_BYTES) == 0);
    assert(memcmp(edit.images[0], expected, SH_IMAGES_TILE_BYTES) == 0);
    assert(memcmp(edit.images[1], initial + SH_IMAGES_TILE_BYTES,
                  sizeof initial - SH_IMAGES_TILE_BYTES) == 0);
    assert(memcmp(edit.entry, initial, sizeof initial) == 0);
}

static void rejection_and_failure_boundaries(void) {
    unsigned index;
    static const size_t invalid_lengths[] = {0, 1, SH_IMAGES_PIXEL_BYTES - 1,
                                            SH_IMAGES_PIXEL_BYTES + 1, SIZE_MAX};
    begin();
    assert(sh_images_copy_tile(&edit, 0, 1) == 0);
    for (index = 0; index < sizeof invalid_lengths / sizeof invalid_lengths[0]; ++index) {
        size_t length = invalid_lengths[index];
        REJECT_UNCHANGED(sh_images_begin(&edit, imported, length));
        REJECT_UNCHANGED(sh_images_load(&edit, imported, length));
        REJECT_UNCHANGED(sh_images_merge_row(&edit, imported, length, 0, 0));
        REJECT_UNCHANGED(sh_images_merge_empty(&edit, imported, length));
    }
    REJECT_UNCHANGED(sh_images_begin(&edit, NULL, sizeof initial));
    REJECT_UNCHANGED(sh_images_load(&edit, NULL, sizeof initial));
    REJECT_UNCHANGED(sh_images_merge_row(&edit, NULL, sizeof initial, 0, 0));
    REJECT_UNCHANGED(sh_images_merge_empty(&edit, NULL, sizeof initial));
    REJECT_UNCHANGED(sh_images_replace_tile(&edit, 0, NULL, SH_IMAGES_TILE_BYTES));
    REJECT_UNCHANGED(sh_images_replace_tile(&edit, 0, imported, 0));
    REJECT_UNCHANGED(sh_images_replace_tile(&edit, 0, imported, SH_IMAGES_TILE_BYTES - 1));
    REJECT_UNCHANGED(sh_images_replace_tile(&edit, 0, imported, SH_IMAGES_TILE_BYTES + 1));
    REJECT_UNCHANGED(sh_images_replace_tile(&edit, 0, imported, SIZE_MAX));

    for (index = 0; index < 2; ++index) {
        unsigned invalid_tile = index ? UINT_MAX : 37;
        unsigned invalid_row = index ? UINT_MAX : 6;
        REJECT_UNCHANGED(sh_images_replace_tile(&edit, invalid_tile, imported, SH_IMAGES_TILE_BYTES));
        REJECT_UNCHANGED(sh_images_copy_tile(&edit, invalid_tile, 0));
        REJECT_UNCHANGED(sh_images_copy_tile(&edit, 0, invalid_tile));
        REJECT_UNCHANGED(sh_images_merge_row(&edit, imported, sizeof imported, invalid_row, 0));
        REJECT_UNCHANGED(sh_images_merge_row(&edit, imported, sizeof imported, 0, invalid_row));
    }
    for (index = 0; index < 2; ++index) {
        memcpy(bad, imported, sizeof bad);
        bad[index ? sizeof bad - 1 : 0] = index ? 255 : 16;
        REJECT_UNCHANGED(sh_images_begin(&edit, bad, sizeof bad));
        REJECT_UNCHANGED(sh_images_load(&edit, bad, sizeof bad));
        REJECT_UNCHANGED(sh_images_merge_row(&edit, bad, sizeof bad, 5, 5));
        REJECT_UNCHANGED(sh_images_merge_empty(&edit, bad, sizeof bad));
    }
    memcpy(bad, imported, SH_IMAGES_TILE_BYTES);
    bad[SH_IMAGES_TILE_BYTES - 1] = 16;
    REJECT_UNCHANGED(sh_images_replace_tile(&edit, 0, bad, SH_IMAGES_TILE_BYTES));
    assert(edit.dirty == 1);

    /* No save acknowledgement is sent on cancellation or I/O failure. A bad
     * decoded replacement likewise preserves both the dirty pixels and entry. */
    assert(sh_images_begin(NULL, initial, sizeof initial) == -1);
    assert(sh_images_load(NULL, initial, sizeof initial) == -1);
    assert(sh_images_replace_tile(NULL, 0, initial, SH_IMAGES_TILE_BYTES) == -1);
    assert(sh_images_copy_tile(NULL, 0, 0) == -1);
    assert(sh_images_merge_row(NULL, initial, sizeof initial, 0, 0) == -1);
    assert(sh_images_merge_empty(NULL, initial, sizeof initial) == -1);
    assert(sh_images_saved(NULL) == -1);
    assert(sh_images_abort(NULL) == -1);
}

int main(void) {
    fixture(initial, 3);
    fixture(imported, 12);
    row_and_empty_merges();
    copying_and_pixel_acceptance();
    transactions();
    aliasing();
    rejection_and_failure_boundaries();
    printf("Image transactions: 36 row mappings and 36 aliased mappings, empty/tile copies, "
           "operation-based dirty state, save/load/abort boundaries, complete rollback, "
           "overlap safety, %u unchanged-state rejections: PASS\n", rejection_count);
    return 0;
}
