#include "sherlock_images.h"

#include <string.h>

static int valid_pixels(const uint8_t *pixels, size_t length, size_t expected) {
    size_t i;
    if (!pixels || length != expected) return 0;
    for (i = 0; i < length; ++i)
        if (pixels[i] > 15) return 0;
    return 1;
}

int sh_images_begin(SHImageEdit *edit, const uint8_t *pixels, size_t length) {
    if (!edit || !valid_pixels(pixels, length, SH_IMAGES_PIXEL_BYTES)) return -1;
    memmove(edit->images, pixels, sizeof edit->images);
    memcpy(edit->entry, edit->images, sizeof edit->entry);
    edit->dirty = 0;
    return 0;
}

int sh_images_load(SHImageEdit *edit, const uint8_t *pixels, size_t length) {
    if (!edit || !valid_pixels(pixels, length, SH_IMAGES_PIXEL_BYTES)) return -1;
    memmove(edit->images, pixels, sizeof edit->images);
    edit->dirty = 0;
    return 0;
}

int sh_images_replace_tile(SHImageEdit *edit, unsigned index,
                           const uint8_t *pixels, size_t length) {
    if (!edit || index >= SH_IMAGES_EDITABLE_COUNT ||
        !valid_pixels(pixels, length, SH_IMAGES_TILE_BYTES)) return -1;
    memmove(edit->images[index], pixels, sizeof edit->images[index]);
    edit->dirty = 1;
    return 0;
}

int sh_images_copy_tile(SHImageEdit *edit, unsigned source, unsigned destination) {
    if (!edit || source >= SH_IMAGES_EDITABLE_COUNT ||
        destination >= SH_IMAGES_EDITABLE_COUNT) return -1;
    memmove(edit->images[destination], edit->images[source],
            sizeof edit->images[destination]);
    edit->dirty = 1;
    return 0;
}

int sh_images_merge_row(SHImageEdit *edit, const uint8_t *source, size_t length,
                        unsigned source_row, unsigned destination_row) {
    if (!edit || source_row >= 6 || destination_row >= 6 ||
        !valid_pixels(source, length, SH_IMAGES_PIXEL_BYTES)) return -1;
    memmove(edit->images[destination_row * 6],
            source + source_row * 6 * SH_IMAGES_TILE_BYTES,
            6 * SH_IMAGES_TILE_BYTES);
    edit->dirty = 1;
    return 0;
}

int sh_images_merge_empty(SHImageEdit *edit, const uint8_t *source, size_t length) {
    if (!edit || !valid_pixels(source, length, SH_IMAGES_PIXEL_BYTES)) return -1;
    memmove(edit->images[36], source + 36 * SH_IMAGES_TILE_BYTES,
            sizeof edit->images[36]);
    edit->dirty = 1;
    return 0;
}

int sh_images_saved(SHImageEdit *edit) {
    if (!edit) return -1;
    edit->dirty = 0;
    return 0;
}

int sh_images_abort(SHImageEdit *edit) {
    if (!edit) return -1;
    memcpy(edit->images, edit->entry, sizeof edit->images);
    edit->dirty = 0;
    return 0;
}
