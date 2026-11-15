#ifndef SHERLOCK_SHI_H
#define SHERLOCK_SHI_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum {
    SHI_IMAGE_COUNT = 46,
    SHI_WIDTH = 32,
    SHI_HEIGHT = 32,
    SHI_RECORD_SIZE = 520,
    SHI_FILE_SIZE = SHI_IMAGE_COUNT * SHI_RECORD_SIZE
};

/* Sherlock's observed default palette. The SHI file itself has no palette. */
extern uint8_t shi_palette[16][3];

/*
 * Pixels are [image][y][x], palette indices 0..15, top row first.
 * Both functions return 0 on success, -1 on failure and set errno.
 * Invalid arguments, headers, lengths, or pixel values report EINVAL.
 * A failed load leaves the caller's pixel array unchanged.
 * Save validates all pixels before opening the destination. An I/O failure
 * can leave a partial file; use a temporary path and rename when replacing
 * valuable existing files.
 *
 * Slots: 0..5 faces; 6..11 houses; 12..17 letters; 18..23 fruit;
 * 24..29 vehicles; 30..35 dice; 36 empty; 37..45 clue marker images.
 * All 46 images are retained without interpreting marker compositing.
 */
int shi_load(const char *path, uint8_t pixels[46][32][32]);
int shi_save(const char *path, const uint8_t pixels[46][32][32]);

#ifdef __cplusplus
}
#endif
#endif
