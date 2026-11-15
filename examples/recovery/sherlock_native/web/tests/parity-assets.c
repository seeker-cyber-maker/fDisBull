/* Read-only private asset oracle. Raw decoded pixels are stdout only and are
 * compared in memory by parity.js; this source contains no game assets. */
#include "../../media/shi.h"
#include <stdio.h>

int main(int argc, char **argv) {
    uint8_t pixels[SHI_IMAGE_COUNT][SHI_HEIGHT][SHI_WIDTH];
    if (argc != 2) return 2;
    if (shi_load(argv[1], pixels) != 0) return 1;
    if (fwrite(pixels, 1, sizeof pixels, stdout) != sizeof pixels) return 3;
    return 0;
}
