#include "shi.h"

#include <errno.h>
#include <stdio.h>
#include <string.h>

uint8_t shi_palette[16][3] = {
    {  0,   0,   0}, { 85,  85,  85},
    {170,  85,   0}, {255,   0,   0},
    {255, 170,   0}, {255, 255,   0},
    {  0, 255,   0}, {  0, 255, 170},
    {  0, 170, 255}, {  0,   0, 255},
    {170,   0, 170}, {170,  85, 255},
    {255,   0, 170}, {255, 170, 170},
    {170, 170, 170}, {255, 255, 255}
};

static const uint8_t shi_header[8] = {4, 0, 1, 0, 32, 0, 32, 0};

static int fail_with(int error)
{
    errno = error;
    return -1;
}

int shi_load(const char *path, uint8_t pixels[46][32][32])
{
    uint8_t encoded[SHI_FILE_SIZE];
    uint8_t decoded[SHI_IMAGE_COUNT][SHI_HEIGHT][SHI_WIDTH];
    FILE *file;
    size_t count;
    int extra, saved_error;
    unsigned image, y, x, plane;

    if (path == NULL || pixels == NULL)
        return fail_with(EINVAL);
    file = fopen(path, "rb");
    if (file == NULL)
        return -1;

    errno = 0;
    count = fread(encoded, 1, sizeof(encoded), file);
    extra = fgetc(file);
    if (ferror(file)) {
        saved_error = errno ? errno : EIO;
        fclose(file);
        return fail_with(saved_error);
    }
    if (fclose(file) != 0)
        return -1;
    if (count != sizeof(encoded) || extra != EOF)
        return fail_with(EINVAL);

    for (image = 0; image < SHI_IMAGE_COUNT; ++image) {
        const uint8_t *record = encoded + image * SHI_RECORD_SIZE;
        if (memcmp(record, shi_header, sizeof(shi_header)) != 0)
            return fail_with(EINVAL);
        for (y = 0; y < SHI_HEIGHT; ++y) {
            for (x = 0; x < SHI_WIDTH; ++x) {
                uint8_t value = 0;
                for (plane = 0; plane < 4; ++plane) {
                    unsigned offset = 8 + y * 16 + plane * 4 + x / 8;
                    value |= (uint8_t)(((record[offset] >> (7 - x % 8)) & 1) << plane);
                }
                decoded[image][y][x] = value;
            }
        }
    }
    memcpy(pixels, decoded, sizeof(decoded));
    return 0;
}

int shi_save(const char *path, const uint8_t pixels[46][32][32])
{
    uint8_t encoded[SHI_FILE_SIZE] = {0};
    FILE *file;
    unsigned image, y, x, plane;
    int saved_error;

    if (path == NULL || pixels == NULL)
        return fail_with(EINVAL);
    for (image = 0; image < SHI_IMAGE_COUNT; ++image) {
        uint8_t *record = encoded + image * SHI_RECORD_SIZE;
        memcpy(record, shi_header, sizeof(shi_header));
        for (y = 0; y < SHI_HEIGHT; ++y) {
            for (x = 0; x < SHI_WIDTH; ++x) {
                uint8_t value = pixels[image][y][x];
                if (value > 15)
                    return fail_with(EINVAL);
                for (plane = 0; plane < 4; ++plane) {
                    unsigned offset = 8 + y * 16 + plane * 4 + x / 8;
                    record[offset] |= (uint8_t)(((value >> plane) & 1) << (7 - x % 8));
                }
            }
        }
    }
    file = fopen(path, "wb");
    if (file == NULL)
        return -1;
    errno = 0;
    if (fwrite(encoded, 1, sizeof(encoded), file) != sizeof(encoded)) {
        saved_error = errno ? errno : EIO;
        fclose(file);
        return fail_with(saved_error);
    }
    return fclose(file) == 0 ? 0 : -1;
}
