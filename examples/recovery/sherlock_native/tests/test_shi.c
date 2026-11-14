#define _POSIX_C_SOURCE 200809L
#include "../media/shi.h"

#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* Authored test vectors only; no original game data is required. */
static uint8_t source[46][32][32], decoded[46][32][32];
static uint8_t bytes[SHI_FILE_SIZE + 1];

static void write_bytes(const char *path, size_t size)
{
    FILE *f = fopen(path, "wb");
    assert(f != NULL);
    assert(fwrite(bytes, 1, size, f) == size);
    assert(fclose(f) == 0);
}

static void reject_unchanged(const char *path)
{
    unsigned i, y, x;
    memset(decoded, 0xa5, sizeof(decoded));
    errno = 0;
    assert(shi_load(path, decoded) == -1 && errno == EINVAL);
    for (i = 0; i < 46; ++i)
        for (y = 0; y < 32; ++y)
            for (x = 0; x < 32; ++x)
                assert(decoded[i][y][x] == 0xa5);
}

int main(void)
{
    char directory[] = "/tmp/sherlock-shi-test-XXXXXX";
    char path[128];
    FILE *f;
    unsigned i, y, x;
    assert(mkdtemp(directory) != NULL);
    assert(snprintf(path, sizeof(path), "%s/fixture.shi", directory) > 0);

    /* Independent byte-level vector: first pixel of each stored plane,
       the last bit of the last row, and the final image record. */
    memset(bytes, 0, sizeof(bytes));
    for (i = 0; i < 46; ++i) {
        const uint8_t header[8] = {4, 0, 1, 0, 32, 0, 32, 0};
        memcpy(bytes + i * 520, header, 8);
    }
    bytes[8] = 0x80;
    bytes[8 + 4] = 0x40;
    bytes[8 + 8] = 0x20;
    bytes[8 + 12] = 0x10;
    bytes[8 + 31 * 16 + 15] = 0x01;
    bytes[45 * 520 + 8 + 17 * 16 + 9] = 0x04;
    write_bytes(path, SHI_FILE_SIZE);
    assert(shi_load(path, decoded) == 0);
    source[0][0][0] = 1;
    source[0][0][1] = 2;
    source[0][0][2] = 4;
    source[0][0][3] = 8;
    source[0][31][31] = 8;
    source[45][17][13] = 4;
    assert(memcmp(source, decoded, sizeof(source)) == 0);
    assert(shi_save(path, (const uint8_t (*)[32][32])source) == 0);
    f = fopen(path, "rb");
    assert(f != NULL);
    for (i = 0; i < SHI_FILE_SIZE; ++i)
        assert(fgetc(f) == bytes[i]);
    assert(fgetc(f) == EOF);
    assert(fclose(f) == 0);

    /* Every color and coordinate, including all 46 records. */
    for (i = 0; i < 46; ++i)
        for (y = 0; y < 32; ++y)
            for (x = 0; x < 32; ++x)
                source[i][y][x] = (uint8_t)((i * 7 + y * 3 + x) & 15);
    assert(shi_save(path, (const uint8_t (*)[32][32])source) == 0);
    assert(shi_load(path, decoded) == 0);
    assert(memcmp(source, decoded, sizeof(source)) == 0);

    write_bytes(path, SHI_FILE_SIZE - 1);
    reject_unchanged(path);
    write_bytes(path, SHI_FILE_SIZE + 1);
    reject_unchanged(path);
    bytes[45 * 520 + 4] = 31;
    write_bytes(path, SHI_FILE_SIZE);
    reject_unchanged(path);
    bytes[45 * 520 + 4] = 32;
    write_bytes(path, SHI_FILE_SIZE);

    source[45][31][31] = 16;
    assert(shi_save(path, (const uint8_t (*)[32][32])source) == -1 && errno == EINVAL);
    /* Invalid pixels must not truncate/replace the pre-existing file. */
    assert(shi_load(path, decoded) == 0 && decoded[0][0][0] == 1);
    assert(shi_load(NULL, decoded) == -1 && errno == EINVAL);
    assert(shi_load(path, NULL) == -1 && errno == EINVAL);
    assert(shi_save(NULL, (const uint8_t (*)[32][32])source) == -1 && errno == EINVAL);
    assert(shi_save(path, NULL) == -1 && errno == EINVAL);

    assert(unlink(path) == 0);
    assert(rmdir(directory) == 0);
    puts("SHI: golden byte vector, all-image roundtrip, malformed files, unchanged output, invalid pixels: PASS");
    return 0;
}
