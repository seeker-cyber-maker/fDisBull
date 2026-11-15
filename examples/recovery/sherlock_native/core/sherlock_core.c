/* Native Sherlock 1.50 numbered-puzzle mapping.
 *
 * The resource contains recovered puzzle semantics for every uint16_t number.
 * Runtime requirements: ISO C99 and the semantic data file. There is no DOS,
 * x86 decoder, CPU interpreter, or original game executable in this module.
 */
#include "sherlock_core.h"
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define PUZZLE_COUNT 65536u
#define TABLE_HEADER_SIZE 16u
#define TABLE_INDEX_SIZE ((PUZZLE_COUNT + 1u) * 4u)
#define TABLE_PAYLOAD_START (TABLE_HEADER_SIZE + TABLE_INDEX_SIZE)

static unsigned char *puzzle_table;
static size_t puzzle_table_size;
static char core_error[192] = "Puzzle table has not been loaded.";

static uint32_t read_u32(const unsigned char *p) {
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 |
           (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static int fail(const char *reason) {
    snprintf(core_error, sizeof core_error, "%s", reason);
    return -1;
}

const char *sherlock_core_error(void) { return core_error; }

int sherlock_load_puzzle_table(const char *path) {
    FILE *file;
    unsigned char *data;
    long length;
    uint32_t i, previous = 0;
    size_t payload_size;
    if (!path || !*path) return fail("No puzzle table path was supplied.");
    file = fopen(path, "rb");
    if (!file) return fail("The numbered-puzzle resource could not be opened.");
    if (fseek(file, 0, SEEK_END) != 0 || (length = ftell(file)) < 0 ||
        fseek(file, 0, SEEK_SET) != 0) {
        fclose(file);
        return fail("The numbered-puzzle resource could not be read.");
    }
    if ((unsigned long)length < TABLE_PAYLOAD_START ||
        (unsigned long)length > 32u * 1024u * 1024u) {
        fclose(file);
        return fail("The numbered-puzzle resource has an invalid size.");
    }
    data = (unsigned char *)malloc((size_t)length);
    if (!data) { fclose(file); return fail("Unable to allocate puzzle data."); }
    if (fread(data, 1, (size_t)length, file) != (size_t)length) {
        free(data); fclose(file);
        return fail("The numbered-puzzle resource is incomplete.");
    }
    fclose(file);
    if (memcmp(data, "SHRL150\0", 8) || read_u32(data + 8) != 1u ||
        read_u32(data + 12) != PUZZLE_COUNT) {
        free(data);
        return fail("The numbered-puzzle resource has an unknown format.");
    }
    payload_size = (size_t)length - TABLE_PAYLOAD_START;
    for (i = 0; i <= PUZZLE_COUNT; ++i) {
        uint32_t offset = read_u32(data + TABLE_HEADER_SIZE + i * 4u);
        if ((i == 0 && offset != 0) || offset < previous ||
            offset > payload_size || (i == PUZZLE_COUNT && offset != payload_size)) {
            free(data);
            return fail("The numbered-puzzle index is invalid.");
        }
        previous = offset;
    }
    free(puzzle_table);
    puzzle_table = data;
    puzzle_table_size = (size_t)length;
    core_error[0] = '\0';
    return 0;
}

static int ensure_table(void) {
    const char *configured;
    if (puzzle_table) return 0;
    configured = getenv("SHERLOCK_PUZZLE_TABLE");
    if (configured && *configured) return sherlock_load_puzzle_table(configured);
    if (sherlock_load_puzzle_table("core/sherlock_puzzles.bin") == 0) return 0;
    if (sherlock_load_puzzle_table("sherlock_puzzles.bin") == 0) return 0;
    return fail("The numbered-puzzle resource is missing. Reinstall the application resources.");
}

int sherlock_generate(uint16_t seed, SherlockPuzzle *out) {
    SherlockPuzzle result;
    const unsigned char *p, *end;
    uint32_t start_offset, end_offset;
    unsigned i, row, column, count, previous_slot = 35;
    if (!out) return fail("No puzzle output was supplied.");
    if (ensure_table()) return -1;
    start_offset = read_u32(puzzle_table + TABLE_HEADER_SIZE + (uint32_t)seed * 4u);
    end_offset = read_u32(puzzle_table + TABLE_HEADER_SIZE + ((uint32_t)seed + 1u) * 4u);
    if (end_offset <= start_offset ||
        TABLE_PAYLOAD_START + end_offset > puzzle_table_size)
        return fail("This puzzle number is absent from the resource.");
    p = puzzle_table + TABLE_PAYLOAD_START + start_offset;
    end = puzzle_table + TABLE_PAYLOAD_START + end_offset;
    if (end - p < 38) return fail("The puzzle record is incomplete.");
    memset(&result, 0, sizeof result);
    memset(result.given, -1, sizeof result.given);
    memset(result.original_slot, 255, sizeof result.original_slot);
    result.number = seed;
    for (row = 0; row < SHERLOCK_ROWS; ++row) {
        unsigned seen = 0;
        for (column = 0; column < SHERLOCK_COLUMNS; ++column) {
            unsigned item = *p++;
            if (item >= SHERLOCK_COLUMNS || (seen & (1u << item)))
                return fail("The puzzle solution is invalid.");
            result.solution[row][column] = (uint8_t)item;
            seen |= 1u << item;
        }
    }
    count = *p++;
    if (count > 36 || end - p < (ptrdiff_t)(count * 2u + 1u))
        return fail("The given-square record is invalid.");
    for (i = 0; i < count; ++i) {
        unsigned cell = *p++, item = *p++;
        if (cell >= 36 || item >= 6) return fail("A given square is invalid.");
        row = cell / 6; column = cell % 6;
        if (result.given[row][column] != -1 || result.solution[row][column] != item)
            return fail("A given square conflicts with its solution.");
        result.given[row][column] = (int8_t)item;
    }
    count = *p++;
    if (count > 39 || end - p != (ptrdiff_t)(count * 5u))
        return fail("The clue record is invalid.");
    result.clue_count = (uint16_t)count;
    for (i = 0; i < count; ++i) {
        SherlockClue *clue = &result.clues[i];
        unsigned slot;
        clue->type = *p++; clue->a = *p++; clue->b = *p++; clue->c = *p++;
        slot = *p++;
        if (clue->type > SHERLOCK_UNUSED || clue->a >= 36 ||
            (clue->type != SHERLOCK_UNUSED && clue->b >= 36) ||
            ((clue->type == SHERLOCK_BETWEEN || clue->type == SHERLOCK_NOT_BETWEEN) && clue->c >= 36) ||
            (clue->c >= 36 && clue->c != 255) ||
            slot < 36 || slot >= 75 || slot <= previous_slot)
            return fail("A clue contains an invalid object or display slot.");
        result.original_slot[i] = (uint8_t)slot;
        previous_slot = slot;
    }
    *out = result;
    core_error[0] = '\0';
    return 0;
}
