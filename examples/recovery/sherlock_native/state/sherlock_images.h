#ifndef SHERLOCK_IMAGES_H
#define SHERLOCK_IMAGES_H

#include "../media/shi.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

enum {
    SH_IMAGES_EDITABLE_COUNT = 37,
    SH_IMAGES_TILE_BYTES = SHI_WIDTH * SHI_HEIGHT,
    SH_IMAGES_PIXEL_BYTES = SHI_IMAGE_COUNT * SH_IMAGES_TILE_BYTES
};

/* One visit to the image overview. Pixels are palette indices 0..15, ordered
 * [image][y][x]. The caller may inspect images and dirty; mutations go through
 * these functions. Call begin before using any other operation.
 *
 * dirty records accepted editing operations, not pixel inequality. Painting
 * the existing color or accepting a pixel-editor INIT can therefore be dirty.
 * Begin, successful Load/Defaults, successful Save and Abort clear it. Done
 * keeps the working images; it is not a file save.
 *
 * Native Abort deliberately restores all 46 records. The original only
 * restores the 37 editable records, leaving loaded clue markers behind.
 * Filename associations, nested pixel-editor operations, user confirmations
 * and actual file I/O belong to the caller.
 */
typedef struct SHImageEdit {
    uint8_t images[SHI_IMAGE_COUNT][SHI_HEIGHT][SHI_WIDTH];
    uint8_t entry[SHI_IMAGE_COUNT][SHI_HEIGHT][SHI_WIDTH];
    int dirty;
} SHImageEdit;

/* All functions return 0 on success and -1 on invalid arguments. Failure
 * leaves the entire editor unchanged. Pixel buffers are flat, contiguous
 * arrays; their length must be exactly the documented size. Source buffers
 * may overlap the editor's arrays. No allocation or file access occurs.
 */
int sh_images_begin(SHImageEdit *edit, const uint8_t *pixels, size_t length);

/* Accept a fully decoded image set (or the factory set for Defaults), clearing
 * dirty while preserving the overview-entry snapshot. Call only after a
 * successful decode. Cancelled/failed loads require no state operation.
 */
int sh_images_load(SHImageEdit *edit, const uint8_t *pixels, size_t length);

/* Commit an accepted, edited pixel dialog. index is 0..36; length is
 * SH_IMAGES_TILE_BYTES. This sets dirty even when the pixels are unchanged.
 * An untouched dialog or pixel Abort must not call this function.
 */
int sh_images_replace_tile(SHImageEdit *edit, unsigned index,
                           const uint8_t *pixels, size_t length);
int sh_images_copy_tile(SHImageEdit *edit, unsigned source, unsigned destination);

/* source is a complete SH_IMAGES_PIXEL_BYTES decoded set. Rows are 0..5.
 * A row merge copies six images; an empty-image merge copies only image 36.
 * Both leave all other images, including clue markers 37..45, untouched and
 * mark dirty even if the copied pixels equal their previous values.
 */
int sh_images_merge_row(SHImageEdit *edit, const uint8_t *source, size_t length,
                        unsigned source_row, unsigned destination_row);
int sh_images_merge_empty(SHImageEdit *edit, const uint8_t *source, size_t length);

/* Acknowledge a completed file save. Call only after the write/replace has
 * succeeded; cancelled or failed saves must retain dirty. Saving does not
 * move the entry snapshot, and Abort cannot undo bytes already written.
 */
int sh_images_saved(SHImageEdit *edit);
int sh_images_abort(SHImageEdit *edit);

#ifdef __cplusplus
}
#endif
#endif
