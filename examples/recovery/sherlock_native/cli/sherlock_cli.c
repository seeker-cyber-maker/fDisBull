/* Agent-facing, answer-free JSON protocol over the same native logic used by
 * the application. Challenge responses serialize only public givens/clues.
 * Verification reconstructs the challenge from its number or generator seed;
 * it never accepts client-supplied puzzle data or an "accepted" assertion. */
#include "sherlock_cli.h"
#include "../core/sherlock_core.h"
#include "../core/sherlock_logic.h"
#include "../state/sherlock_hint_proof.h"

#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SH_CLI_FORMAT "sherlock-cli-1"
#define SH_ANSWER_LIMIT 65536u
#define SH_CLI_HINT_NODES 20000u
#define SH_CLI_HINT_SELECTION_NODES 20000u

enum {
    CLI_OK = 0, CLI_REJECTED = 1, CLI_INPUT_ERROR = 2,
    CLI_ENGINE_ERROR = 3, CLI_INCOMPLETE = 4
};
typedef enum Command {
    CMD_PUZZLE, CMD_GENERATE, CMD_VERIFY, CMD_ANALYZE, CMD_HINT, CMD_CHECK_HINT
} Command;
typedef enum Source { SOURCE_NONE, SOURCE_ORIGINAL, SOURCE_NATIVE } Source;

typedef struct Options {
    Command command;
    Source source;
    uint16_t number;
    uint64_t seed, node_budget;
    const char *data_path, *answer_path, *state_path, *move_path;
    int have_number, have_seed, have_nodes, have_data, have_answer;
    int have_state, have_move;
} Options;

typedef struct Challenge {
    SherlockPuzzle puzzle;
    SherlockGenerateResult generation;
    uint64_t fingerprint;
    char id[192];
} Challenge;

typedef struct HintStateInput {
    uint8_t candidates[SH_SIZE][SH_SIZE];
    int8_t chosen[SH_SIZE][SH_SIZE];
    int have_chosen;
} HintStateInput;

static const char *const clue_names[8] = {
    "same_column", "not_same_column", "next_to", "not_next_to",
    "left_of", "between", "not_between", "reference"
};

/* Keep output valid UTF-8 JSON even when an OS argument contains invalid UTF-8
 * bytes. Valid UTF-8 is preserved; invalid bytes become U+00xx escapes. */
static void json_string(const char *value) {
    const unsigned char *p = (const unsigned char *)(value ? value : "");
    size_t length = strlen((const char *)p), i = 0;
    putchar('"');
    while (i < length) {
        unsigned char c = p[i];
        if (c == '"' || c == '\\') { putchar('\\'); putchar(c); ++i; }
        else if (c < 0x20u) { printf("\\u%04x", (unsigned)c); ++i; }
        else if (c < 0x80u) { putchar(c); ++i; }
        else {
            size_t count = c >= 0xC2u && c <= 0xDFu ? 2u :
                           c >= 0xE0u && c <= 0xEFu ? 3u :
                           c >= 0xF0u && c <= 0xF4u ? 4u : 0u;
            int valid = count && count <= length - i;
            size_t j;
            if (valid) {
                for (j = 1; j < count; ++j)
                    if (p[i + j] < 0x80u || p[i + j] > 0xBFu) valid = 0;
                if ((c == 0xE0u && p[i + 1] < 0xA0u) ||
                    (c == 0xEDu && p[i + 1] >= 0xA0u) ||
                    (c == 0xF0u && p[i + 1] < 0x90u) ||
                    (c == 0xF4u && p[i + 1] >= 0x90u)) valid = 0;
            }
            if (valid) { (void)fwrite(p + i, 1, count, stdout); i += count; }
            else { printf("\\u%04x", (unsigned)c); ++i; }
        }
    }
    putchar('"');
}

static int finish_json(int status) {
    putchar('\n');
    return fflush(stdout) == 0 && !ferror(stdout) ? status : CLI_ENGINE_ERROR;
}

static int error_json(int status, const char *code, const char *message,
                       const char *detail_name, const char *detail,
                       int have_offset, size_t offset) {
    printf("{\"format\":\"%s\",\"kind\":\"error\",\"ok\":false,\"error\":{\"code\":", SH_CLI_FORMAT);
    json_string(code);
    fputs(",\"message\":", stdout); json_string(message);
    if (detail_name && detail) {
        putchar(','); json_string(detail_name); putchar(':'); json_string(detail);
    }
    if (have_offset) printf(",\"byte_offset\":%zu", offset);
    fputs("}}", stdout);
    return finish_json(status);
}

static int argument_error(const char *message, const char *argument) {
    return error_json(CLI_INPUT_ERROR, "invalid_arguments", message,
                       "argument", argument, 0, 0);
}

/* Unsigned decimal only: no signs, surrounding whitespace, base prefixes,
 * floating point, overflow or ignored suffixes. Leading zeroes are harmless. */
static int unsigned_decimal(const char *text, uint64_t maximum, uint64_t *out) {
    uint64_t value = 0;
    const unsigned char *p = (const unsigned char *)text;
    if (!p || !*p) return 0;
    while (*p) {
        unsigned digit;
        if (*p < '0' || *p > '9') return 0;
        digit = (unsigned)(*p++ - '0');
        if (value > maximum / 10u ||
            (value == maximum / 10u && digit > maximum % 10u)) return 0;
        value = value * 10u + digit;
    }
    *out = value;
    return 1;
}

static void print_source(const Options *options) {
    if (options->source == SOURCE_ORIGINAL) {
        printf("{\"kind\":\"original\",\"edition\":\"Sherlock 1.50 UK\","
               "\"table_format\":1,\"number\":%u}", (unsigned)options->number);
    } else {
        fputs("{\"kind\":\"native\",\"generator\":", stdout);
        json_string(SHERLOCK_NATIVE_GENERATOR_ID);
        printf(",\"generator_version\":%u,\"seed\":\"%" PRIu64 "\","
               "\"limits\":{\"node_budget\":\"%" PRIu64 "\",\"max_attempts\":%u,\"max_givens\":%u}}",
               (unsigned)SHERLOCK_NATIVE_GENERATOR_VERSION, options->seed,
               SHERLOCK_DEFAULT_GENERATE_NODES,
               (unsigned)SHERLOCK_DEFAULT_GENERATE_ATTEMPTS,
               (unsigned)SHERLOCK_DEFAULT_GENERATE_GIVENS);
    }
}

static int help_json(void) {
    printf("{\"format\":\"%s\",\"kind\":\"help\",\"ok\":true,"
           "\"commands\":["
           "\"puzzle --number N [--data PATH]\","
           "\"generate --seed UINT64\","
           "\"verify (--number N | --seed UINT64) --solution PATH|- [--data PATH]\","
           "\"analyze (--number N | --seed UINT64) [--max-nodes UINT64] [--data PATH]\","
           "\"hint (--number N | --seed UINT64) [--state PATH|-] [--max-nodes UINT] [--data PATH]\","
           "\"check-hint (--number N | --seed UINT64) --move PATH|- [--state PATH|-] [--max-nodes UINT] [--data PATH]\","
           "\"help\",\"version\"],"
           "\"number_range\":[0,65535],\"seed_range\":[\"0\",\"18446744073709551615\"],"
           "\"answer\":{\"forms\":[\"6x6 array\",\"object with only a solution field containing that array\"],"
           "\"layout\":\"answer[row][column] is the within-row item ID 0..5\","
           "\"item_tokens\":\"single JSON integer digits 0 through 5\",\"maximum_bytes\":%u},"
           "\"default_analyze_nodes\":\"%" PRIu64 "\","
           "\"default_hint_nodes\":\"%u\",\"hint_selection_nodes\":\"%u\","
           "\"hint_node_maximum\":\"%u\","
           "\"hint_state\":{\"required\":\"candidates: six by six masks 0..63\","
           "\"optional\":\"chosen: six by six integers -1..5; chosen items need singleton masks\","
           "\"meaning\":\"Candidate masks are assumptions, not certified earlier deductions; canonical givens cannot change.\"},"
           "\"hint_move\":{\"fields\":[\"kind\",\"row\",\"column\",\"item\"],"
           "\"kinds\":[\"remove\",\"choose\"],\"index_range\":[0,5]},"
           "\"data_precedence\":[\"--data PATH\",\"SHERLOCK_PUZZLE_TABLE\","
           "\"embedded resource directory or executable ../Resources\","
           "\"working-directory Resources/, core/, current directory when no resource directory was supplied\"],"
           "\"notes\":[\"Flags and values are separate arguments.\","
           "\"--data applies only to original-number commands. Native generation needs no puzzle table.\","
           "\"Verification regenerates or reloads the canonical challenge and checks all public constraints.\","
           "\"Hint commands prove a fixed target from public clues and stated candidate assumptions; they do not apply moves or charge time.\","
           "\"Hint selection has its own fixed budget; --max-nodes is shared by consistency, refutation and clue reduction.\","
           "\"Only a proved hint has a certified support_record. Incomplete reduction does not invalidate an already proved move.\","
           "\"No command emits a hidden solution. 64-bit values are decimal JSON strings.\"],"
           "\"exit_codes\":{\"0\":\"success, proved hint, no hint or conclusive analysis\",\"1\":\"answer rejected or hint refuted/inconsistent\","
           "\"2\":\"invalid arguments or input JSON/target\",\"3\":\"resource, I/O or engine error\","
           "\"4\":\"analysis/hint unresolved or generator budget exhausted\"}}",
           SH_CLI_FORMAT, SH_ANSWER_LIMIT, SHERLOCK_DEFAULT_SOLVE_NODES,
           SH_CLI_HINT_NODES, SH_CLI_HINT_SELECTION_NODES, UINT_MAX);
    return finish_json(CLI_OK);
}

static int version_json(void) {
    printf("{\"format\":\"%s\",\"kind\":\"version\",\"ok\":true,\"generator\":", SH_CLI_FORMAT);
    json_string(SHERLOCK_NATIVE_GENERATOR_ID);
    printf(",\"generator_version\":%u}", (unsigned)SHERLOCK_NATIVE_GENERATOR_VERSION);
    return finish_json(CLI_OK);
}

static int parse_options(int argc, char **argv, Options *options) {
    int i;
    memset(options, 0, sizeof *options);
    options->node_budget = SHERLOCK_DEFAULT_SOLVE_NODES;
    if (!strcmp(argv[1], "puzzle")) options->command = CMD_PUZZLE;
    else if (!strcmp(argv[1], "generate")) options->command = CMD_GENERATE;
    else if (!strcmp(argv[1], "verify")) options->command = CMD_VERIFY;
    else if (!strcmp(argv[1], "analyze")) options->command = CMD_ANALYZE;
    else if (!strcmp(argv[1], "hint")) options->command = CMD_HINT;
    else if (!strcmp(argv[1], "check-hint")) options->command = CMD_CHECK_HINT;
    else return argument_error("Unknown command. Use help for the supported commands.", argv[1]);
    if (options->command == CMD_HINT || options->command == CMD_CHECK_HINT)
        options->node_budget = SH_CLI_HINT_NODES;
    for (i = 2; i < argc; ++i) {
        const char *flag = argv[i];
        const char *value;
        uint64_t number;
        if (strcmp(flag, "--number") && strcmp(flag, "--seed") &&
            strcmp(flag, "--max-nodes") && strcmp(flag, "--data") &&
            strcmp(flag, "--solution") && strcmp(flag, "--state") &&
            strcmp(flag, "--move")) return argument_error("Unknown option or trailing argument.", flag);
        if (i + 1 >= argc) return argument_error("This option requires a value.", flag);
        value = argv[++i];
        if (!strcmp(flag, "--number")) {
            if (options->have_number) return argument_error("Duplicate --number option.", flag);
            if (!unsigned_decimal(value, 65535u, &number))
                return argument_error("The original number must be an unsigned decimal integer from 0 to 65535.", value);
            options->number = (uint16_t)number; options->have_number = 1;
        } else if (!strcmp(flag, "--seed")) {
            if (options->have_seed) return argument_error("Duplicate --seed option.", flag);
            if (!unsigned_decimal(value, UINT64_MAX, &number))
                return argument_error("The seed must be an unsigned decimal uint64 integer.", value);
            options->seed = number; options->have_seed = 1;
        } else if (!strcmp(flag, "--max-nodes")) {
            if (options->have_nodes) return argument_error("Duplicate --max-nodes option.", flag);
            if (!unsigned_decimal(value, UINT64_MAX, &number))
                return argument_error("The node budget must be an unsigned decimal uint64 integer.", value);
            options->node_budget = number; options->have_nodes = 1;
        } else if (!strcmp(flag, "--data")) {
            if (options->have_data) return argument_error("Duplicate --data option.", flag);
            if (!*value) return argument_error("The data path must not be empty.", flag);
            options->data_path = value; options->have_data = 1;
        } else if (!strcmp(flag, "--solution")) {
            if (options->have_answer) return argument_error("Duplicate --solution option.", flag);
            if (!*value) return argument_error("The solution path must not be empty; use - for stdin.", flag);
            options->answer_path = value; options->have_answer = 1;
        } else if (!strcmp(flag, "--state")) {
            if (options->have_state) return argument_error("Duplicate --state option.", flag);
            if (!*value) return argument_error("The state path must not be empty; use - for stdin.", flag);
            options->state_path = value; options->have_state = 1;
        } else {
            if (options->have_move) return argument_error("Duplicate --move option.", flag);
            if (!*value) return argument_error("The move path must not be empty; use - for stdin.", flag);
            options->move_path = value; options->have_move = 1;
        }
    }
    if (options->have_number + options->have_seed != 1)
        return argument_error("Supply exactly one source: --number N or --seed UINT64.", NULL);
    options->source = options->have_number ? SOURCE_ORIGINAL : SOURCE_NATIVE;
    if ((options->command == CMD_PUZZLE && !options->have_number) ||
        (options->command == CMD_GENERATE && !options->have_seed))
        return argument_error("puzzle requires --number; generate requires --seed.", NULL);
    if ((options->command == CMD_VERIFY) != options->have_answer)
        return argument_error("Only verify accepts and requires --solution PATH|-.", NULL);
    if (options->have_nodes && options->command != CMD_ANALYZE &&
        options->command != CMD_HINT && options->command != CMD_CHECK_HINT)
        return argument_error("--max-nodes is supported only by analyze, hint and check-hint.", NULL);
    if ((options->command == CMD_HINT || options->command == CMD_CHECK_HINT) &&
        options->node_budget > UINT_MAX)
        return argument_error("Hint proof node budgets must fit an unsigned int; see help for hint_node_maximum.", NULL);
    if (options->have_state && options->command != CMD_HINT && options->command != CMD_CHECK_HINT)
        return argument_error("--state is supported only by hint and check-hint.", NULL);
    if ((options->command == CMD_CHECK_HINT) != options->have_move)
        return argument_error("Only check-hint accepts and requires --move PATH|-.", NULL);
    if (options->have_state && options->have_move &&
        !strcmp(options->state_path, "-") && !strcmp(options->move_path, "-"))
        return argument_error("Only one input document may use stdin; supply a file for --state or --move.", NULL);
    if (options->have_data && options->source != SOURCE_ORIGINAL)
        return argument_error("--data applies only to original-number commands.", NULL);
    return CLI_OK;
}

/* The answer parser deliberately accepts only the specified array and one-key
 * object. Hint inputs below share its reader but have their own closed schemas.
 * Every accepted byte sequence is valid JSON; unsupported JSON forms fail. */
typedef struct AnswerReader {
    const unsigned char *start, *at, *end;
    const char *reason;
} AnswerReader;

static void whitespace(AnswerReader *reader) {
    while (reader->at < reader->end &&
           (*reader->at == ' ' || *reader->at == '\t' ||
            *reader->at == '\r' || *reader->at == '\n')) ++reader->at;
}

static int expect(AnswerReader *reader, unsigned char wanted, const char *reason) {
    whitespace(reader);
    if (reader->at >= reader->end || *reader->at != wanted) {
        reader->reason = reason; return 0;
    }
    ++reader->at; return 1;
}

static int hex_digit(unsigned char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static int solution_key(AnswerReader *reader) {
    static const unsigned char key[] = "solution";
    size_t i;
    if (!expect(reader, '"', "The object must have exactly the key \"solution\".")) return 0;
    for (i = 0; i < sizeof key - 1u; ++i) {
        unsigned value;
        if (reader->at >= reader->end) goto invalid;
        value = *reader->at++;
        if (value == '\\') {
            unsigned j;
            if (reader->at >= reader->end || *reader->at++ != 'u') goto invalid;
            value = 0;
            for (j = 0; j < 4; ++j) {
                int digit;
                if (reader->at >= reader->end || (digit = hex_digit(*reader->at++)) < 0) goto invalid;
                value = value * 16u + (unsigned)digit;
            }
        }
        if (value != key[i]) goto invalid;
    }
    /* No whitespace is allowed inside a JSON string before its closing quote. */
    if (reader->at >= reader->end || *reader->at++ != '"') goto invalid;
    return 1;
invalid:
    reader->reason = "The object must have exactly the key \"solution\"; other fields are not accepted.";
    return 0;
}

static int answer_array(AnswerReader *reader, uint8_t answer[6][6]) {
    unsigned row, column;
    if (!expect(reader, '[', "Expected an array of exactly six rows.")) return 0;
    for (row = 0; row < 6; ++row) {
        if (!expect(reader, '[', "Each of the six rows must be an array.")) return 0;
        for (column = 0; column < 6; ++column) {
            whitespace(reader);
            if (reader->at >= reader->end || *reader->at < '0' || *reader->at > '5') {
                reader->reason = "Each item must be a single JSON integer digit from 0 through 5.";
                return 0;
            }
            answer[row][column] = (uint8_t)(*reader->at++ - '0');
            if (column < 5 && !expect(reader, ',', "Each row must have exactly six integer items.")) return 0;
        }
        if (!expect(reader, ']', "Each row must end after exactly six integer items.")) return 0;
        if (row < 5 && !expect(reader, ',', "The answer must contain exactly six rows.")) return 0;
    }
    return expect(reader, ']', "The answer must end after exactly six rows.");
}

static int parse_answer(const unsigned char *bytes, size_t size,
                         uint8_t answer[6][6], const char **reason, size_t *offset) {
    AnswerReader reader = {bytes, bytes, bytes + size, NULL};
    int object, valid = 0;
    whitespace(&reader);
    object = reader.at < reader.end && *reader.at == '{';
    if (object) {
        ++reader.at;
        if (!solution_key(&reader) || !expect(&reader, ':', "Expected ':' after the solution key.")) goto done;
    }
    if (!answer_array(&reader, answer)) goto done;
    if (object && !expect(&reader, '}', "The solution object permits exactly one field and no trailing comma.")) goto done;
    whitespace(&reader);
    if (reader.at != reader.end) {
        reader.reason = "Trailing data after the JSON answer is not permitted."; goto done;
    }
    valid = 1;
done:
    *reason = reader.reason ? reader.reason : "Invalid JSON answer.";
    *offset = (size_t)(reader.at - reader.start);
    return valid;
}

static int read_answer(const char *path, uint8_t answer[6][6]) {
    FILE *file = !strcmp(path, "-") ? stdin : fopen(path, "rb");
    unsigned char *bytes;
    size_t size, offset;
    const char *reason;
    int result;
    if (!file) return error_json(CLI_ENGINE_ERROR, "answer_io_error", strerror(errno), "path", path, 0, 0);
    bytes = (unsigned char *)malloc(SH_ANSWER_LIMIT + 1u);
    if (!bytes) {
        if (file != stdin) fclose(file);
        return error_json(CLI_ENGINE_ERROR, "out_of_memory", "Unable to allocate the answer buffer.", NULL, NULL, 0, 0);
    }
    size = fread(bytes, 1, SH_ANSWER_LIMIT + 1u, file);
    if (ferror(file)) {
        int saved_errno = errno;
        if (file != stdin) fclose(file);
        free(bytes);
        return error_json(CLI_ENGINE_ERROR, "answer_io_error", saved_errno ? strerror(saved_errno) : "The answer could not be read.", "path", path, 0, 0);
    }
    if (file != stdin) fclose(file);
    if (size > SH_ANSWER_LIMIT) {
        free(bytes);
        return error_json(CLI_INPUT_ERROR, "answer_too_large", "The JSON answer exceeds 65536 bytes.", "path", path, 0, 0);
    }
    result = parse_answer(bytes, size, answer, &reason, &offset);
    free(bytes);
    return result ? CLI_OK : error_json(CLI_INPUT_ERROR, "invalid_answer", reason, NULL, NULL, 1, offset);
}

/* Hint documents have a small, closed schema too. These parsers accept JSON
 * ASCII strings (including equivalent Unicode escapes) and bounded integers;
 * they never skip an unknown field or coerce a Boolean/float/string to a number. */
static int ascii_string(AnswerReader *reader, char *output, size_t capacity) {
    size_t length = 0;
    if (!expect(reader, '"', "Expected a quoted ASCII field name or move kind.")) return 0;
    while (reader->at < reader->end) {
        unsigned value = *reader->at++;
        if (value == '"') {
            output[length] = '\0';
            return 1;
        }
        if (value == '\\') {
            unsigned j;
            if (reader->at >= reader->end) goto invalid;
            value = *reader->at++;
            if (value == 'u') {
                value = 0;
                for (j = 0; j < 4; ++j) {
                    int digit;
                    if (reader->at >= reader->end || (digit = hex_digit(*reader->at++)) < 0)
                        goto invalid;
                    value = value * 16u + (unsigned)digit;
                }
            } else if (value != '"' && value != '\\' && value != '/') goto invalid;
        }
        /* The accepted vocabulary has no control characters, including NUL.
         * Rejecting decoded NUL also prevents truncated-key comparisons. */
        if (value < 0x20u || value > 0x7eu || length + 1u >= capacity) goto invalid;
        output[length++] = (char)value;
    }
invalid:
    reader->reason = "Expected a supported ASCII field name or move kind.";
    return 0;
}

static int bounded_json_integer(AnswerReader *reader, int minimum,
                                 unsigned maximum, int *output) {
    unsigned value = 0;
    whitespace(reader);
    if (minimum == -1 && reader->at < reader->end && *reader->at == '-') {
        ++reader->at;
        if (reader->at >= reader->end || *reader->at++ != '1') goto invalid;
        if (reader->at < reader->end && *reader->at >= '0' && *reader->at <= '9') goto invalid;
        *output = -1;
        return 1;
    }
    if (reader->at >= reader->end || *reader->at < '0' || *reader->at > '9') goto invalid;
    if (*reader->at == '0') {
        ++reader->at;
        if (reader->at < reader->end && *reader->at >= '0' && *reader->at <= '9') goto invalid;
    } else {
        do {
            unsigned digit = (unsigned)(*reader->at++ - '0');
            if (value > maximum / 10u ||
                (value == maximum / 10u && digit > maximum % 10u)) goto invalid;
            value = value * 10u + digit;
        } while (reader->at < reader->end && *reader->at >= '0' && *reader->at <= '9');
    }
    *output = (int)value;
    return 1;
invalid:
    reader->reason = minimum == -1 ?
        "Chosen entries must be JSON integers -1 or 0 through 5." :
        maximum == 63u ? "Candidate masks must be JSON integers 0 through 63." :
        "Move coordinates and item IDs must be JSON integers 0 through 5.";
    return 0;
}

static int bounded_matrix(AnswerReader *reader, int minimum, unsigned maximum,
                            int matrix[SH_SIZE][SH_SIZE]) {
    unsigned row, column;
    if (!expect(reader, '[', "Expected a matrix of exactly six rows.")) return 0;
    for (row = 0; row < SH_SIZE; ++row) {
        if (!expect(reader, '[', "Each matrix row must be an array.")) return 0;
        for (column = 0; column < SH_SIZE; ++column) {
            if (!bounded_json_integer(reader, minimum, maximum, &matrix[row][column])) return 0;
            if (column < SH_SIZE - 1u &&
                !expect(reader, ',', "Each row must contain exactly six integers.")) return 0;
        }
        if (!expect(reader, ']', "Each row must end after exactly six integers.")) return 0;
        if (row < SH_SIZE - 1u &&
            !expect(reader, ',', "The matrix must contain exactly six rows.")) return 0;
    }
    return expect(reader, ']', "The matrix must end after exactly six rows.");
}

static int parse_hint_state(AnswerReader *reader, HintStateInput *state) {
    unsigned seen = 0;
    memset(state, 0, sizeof *state);
    memset(state->chosen, -1, sizeof state->chosen);
    if (!expect(reader, '{', "State must be an object with candidates and optional chosen.")) return 0;
    for (;;) {
        char key[32];
        unsigned field, row, column;
        int matrix[SH_SIZE][SH_SIZE];
        if (!ascii_string(reader, key, sizeof key)) return 0;
        field = !strcmp(key, "candidates") ? 1u : !strcmp(key, "chosen") ? 2u : 0u;
        if (!field || (seen & field)) {
            reader->reason = "State accepts exactly one candidates field and at most one chosen field; no other fields.";
            return 0;
        }
        seen |= field;
        if (!expect(reader, ':', "Expected ':' after the state field name.") ||
            !bounded_matrix(reader, field == 2u ? -1 : 0, field == 2u ? 5u : 63u, matrix)) return 0;
        for (row = 0; row < SH_SIZE; ++row) for (column = 0; column < SH_SIZE; ++column) {
            if (field == 1u) state->candidates[row][column] = (uint8_t)matrix[row][column];
            else state->chosen[row][column] = (int8_t)matrix[row][column];
        }
        whitespace(reader);
        if (reader->at < reader->end && *reader->at == '}') { ++reader->at; break; }
        if (!expect(reader, ',', "Expected ',' or the end of the state object.")) return 0;
    }
    if (!(seen & 1u)) {
        reader->reason = "State requires its candidates matrix.";
        return 0;
    }
    state->have_chosen = (seen & 2u) != 0;
    return 1;
}

static int parse_hint_move(AnswerReader *reader, SHHint *move) {
    unsigned seen = 0;
    memset(move, 0, sizeof *move);
    move->clue_index = -1;
    if (!expect(reader, '{', "Move must be an object with kind, row, column and item.")) return 0;
    for (;;) {
        char key[32];
        unsigned field;
        int value;
        if (!ascii_string(reader, key, sizeof key)) return 0;
        field = !strcmp(key, "kind") ? 1u : !strcmp(key, "row") ? 2u :
                !strcmp(key, "column") ? 4u : !strcmp(key, "item") ? 8u : 0u;
        if (!field || (seen & field)) {
            reader->reason = "Move requires exactly kind, row, column and item; duplicates and other fields are rejected.";
            return 0;
        }
        seen |= field;
        if (!expect(reader, ':', "Expected ':' after the move field name.")) return 0;
        if (field == 1u) {
            char kind[16];
            if (!ascii_string(reader, kind, sizeof kind)) return 0;
            if (!strcmp(kind, "remove")) move->kind = SH_HINT_REMOVE;
            else if (!strcmp(kind, "choose")) move->kind = SH_HINT_CHOOSE;
            else {
                reader->reason = "Move kind must be remove or choose.";
                return 0;
            }
        } else {
            if (!bounded_json_integer(reader, 0, 5u, &value)) return 0;
            if (field == 2u) move->row = (uint8_t)value;
            else if (field == 4u) move->column = (uint8_t)value;
            else move->item = (uint8_t)value;
        }
        whitespace(reader);
        if (reader->at < reader->end && *reader->at == '}') { ++reader->at; break; }
        if (!expect(reader, ',', "Expected ',' or the end of the move object.")) return 0;
    }
    if (seen != 15u) {
        reader->reason = "Move requires all four fields: kind, row, column and item.";
        return 0;
    }
    return 1;
}

static int read_hint_document(const char *path, HintStateInput *state, SHHint *move) {
    FILE *file = !strcmp(path, "-") ? stdin : fopen(path, "rb");
    unsigned char *bytes;
    size_t size, offset;
    AnswerReader reader;
    const char *io_code = state ? "state_io_error" : "move_io_error";
    int valid;
    if (!file) return error_json(CLI_ENGINE_ERROR, io_code, strerror(errno), "path", path, 0, 0);
    bytes = (unsigned char *)malloc(SH_ANSWER_LIMIT + 1u);
    if (!bytes) {
        if (file != stdin) fclose(file);
        return error_json(CLI_ENGINE_ERROR, "out_of_memory", "Unable to allocate the input buffer.", NULL, NULL, 0, 0);
    }
    size = fread(bytes, 1, SH_ANSWER_LIMIT + 1u, file);
    if (ferror(file)) {
        int saved_errno = errno;
        if (file != stdin) fclose(file);
        free(bytes);
        return error_json(CLI_ENGINE_ERROR, io_code, saved_errno ? strerror(saved_errno) : "The JSON document could not be read.", "path", path, 0, 0);
    }
    if (file != stdin) fclose(file);
    if (size > SH_ANSWER_LIMIT) {
        free(bytes);
        return error_json(CLI_INPUT_ERROR, state ? "state_too_large" : "move_too_large",
                           "The JSON document exceeds 65536 bytes.", "path", path, 0, 0);
    }
    reader.start = bytes; reader.at = bytes; reader.end = bytes + size; reader.reason = NULL;
    valid = state ? parse_hint_state(&reader, state) : parse_hint_move(&reader, move);
    if (valid) {
        whitespace(&reader);
        if (reader.at != reader.end) {
            reader.reason = "Trailing data after the JSON document is not permitted.";
            valid = 0;
        }
    }
    offset = (size_t)(reader.at - reader.start);
    free(bytes);
    return valid ? CLI_OK : error_json(CLI_INPUT_ERROR, state ? "invalid_state" : "invalid_move",
        reader.reason ? reader.reason : "Invalid JSON document.", NULL, NULL, 1, offset);
}

static char *table_path(const char *directory) {
    static const char name[] = "sherlock_puzzles.bin";
    size_t length = strlen(directory);
    int slash = length > 0 && directory[length - 1u] != '/';
    char *path;
    if (length > SIZE_MAX - sizeof name - 1u) return NULL;
    path = (char *)malloc(length + (size_t)slash + sizeof name);
    if (!path) return NULL;
    memcpy(path, directory, length);
    if (slash) path[length++] = '/';
    memcpy(path + length, name, sizeof name);
    return path;
}

static int load_table(const Options *options, const char *resource_directory) {
    const char *configured = options->data_path;
    char *owned = NULL;
    int status;
    if (!configured) {
        configured = getenv("SHERLOCK_PUZZLE_TABLE");
        if (configured && !*configured) configured = NULL;
    }
    if (!configured && resource_directory && *resource_directory) {
        owned = table_path(resource_directory);
        if (!owned) return error_json(CLI_ENGINE_ERROR, "out_of_memory", "Unable to construct the resource path.", NULL, NULL, 0, 0);
        configured = owned;
    }
    if (!configured) {
        static const char *const paths[] = {
            "Resources/sherlock_puzzles.bin", "core/sherlock_puzzles.bin", "sherlock_puzzles.bin"
        };
        size_t i;
        for (i = 0; i < sizeof paths / sizeof paths[0]; ++i) {
            FILE *probe;
            errno = 0;
            probe = fopen(paths[i], "rb");
            if (probe) { fclose(probe); configured = paths[i]; break; }
            if (errno != ENOENT && errno != ENOTDIR)
                return error_json(CLI_ENGINE_ERROR, "resource_error", strerror(errno), "path", paths[i], 0, 0);
        }
    }
    if (!configured)
        return error_json(CLI_ENGINE_ERROR, "resource_not_found", "No original puzzle table was found. Supply --data PATH or SHERLOCK_PUZZLE_TABLE.", NULL, NULL, 0, 0);
    status = sherlock_load_puzzle_table(configured);
    if (status != 0) {
        int result = error_json(CLI_ENGINE_ERROR, "resource_error", sherlock_core_error(), "path", configured, 0, 0);
        free(owned); return result;
    }
    free(owned); return CLI_OK;
}

static unsigned clue_arity(unsigned type) {
    return type == SHERLOCK_UNUSED ? 1u :
           type == SHERLOCK_BETWEEN || type == SHERLOCK_NOT_BETWEEN ? 3u : 2u;
}

static int valid_public_puzzle(const SherlockPuzzle *puzzle) {
    unsigned row, column, i;
    if (puzzle->clue_count > SHERLOCK_MAX_CLUES) return 0;
    for (row = 0; row < 6; ++row) for (column = 0; column < 6; ++column)
        if (puzzle->given[row][column] < -1 || puzzle->given[row][column] > 5) return 0;
    for (i = 0; i < puzzle->clue_count; ++i) {
        const SherlockClue *clue = &puzzle->clues[i];
        unsigned arity = clue_arity(clue->type);
        if (clue->type > SHERLOCK_UNUSED || clue->a > 35 ||
            (arity >= 2 && clue->b > 35) || (arity == 3 && clue->c > 35)) return 0;
    }
    return 1;
}

static uint64_t fingerprint_byte(uint64_t hash, unsigned value) {
    return (hash ^ (uint8_t)value) * UINT64_C(1099511628211);
}

static uint64_t public_fingerprint(const SherlockPuzzle *puzzle) {
    static const unsigned char domain[] = "sherlock-public-v1";
    uint64_t hash = UINT64_C(14695981039346656037);
    unsigned row, column, i;
    for (i = 0; i < sizeof domain - 1u; ++i) hash = fingerprint_byte(hash, domain[i]);
    hash = fingerprint_byte(hash, 6); hash = fingerprint_byte(hash, 6);
    for (row = 0; row < 6; ++row) for (column = 0; column < 6; ++column)
        hash = fingerprint_byte(hash, puzzle->given[row][column] < 0 ? 255u : (unsigned)puzzle->given[row][column]);
    hash = fingerprint_byte(hash, puzzle->clue_count & 255u);
    hash = fingerprint_byte(hash, puzzle->clue_count >> 8);
    for (i = 0; i < puzzle->clue_count; ++i) {
        const SherlockClue *clue = &puzzle->clues[i];
        unsigned arity = clue_arity(clue->type), slot = puzzle->original_slot[i];
        hash = fingerprint_byte(hash, clue->type);
        hash = fingerprint_byte(hash, clue->a);
        hash = fingerprint_byte(hash, arity >= 2 ? clue->b : 255u);
        hash = fingerprint_byte(hash, arity == 3 ? clue->c : 255u);
        hash = fingerprint_byte(hash, slot >= 36 && slot <= 74 ? slot : 255u);
    }
    return hash;
}

int sh_cli_format_challenge_id(const SherlockPuzzle *puzzle,
                              int native_generator, uint64_t seed,
                              char *output, size_t capacity) {
    char identity[192];
    uint64_t hash;
    int length;
    if (!puzzle || !output || !capacity ||
        (native_generator != 0 && native_generator != 1) ||
        !valid_public_puzzle(puzzle)) return -1;
    hash = public_fingerprint(puzzle);
    if (!native_generator)
        length = snprintf(identity, sizeof identity,
            "sherlock-1.50-uk:%u:%016" PRIx64, (unsigned)puzzle->number, hash);
    else
        length = snprintf(identity, sizeof identity,
            "%s:v%u:%" PRIu64 ":%016" PRIx64, SHERLOCK_NATIVE_GENERATOR_ID,
            (unsigned)SHERLOCK_NATIVE_GENERATOR_VERSION, seed, hash);
    if (length < 0 || (size_t)length >= sizeof identity || (size_t)length >= capacity)
        return -1;
    memcpy(output, identity, (size_t)length + 1u);
    return 0;
}

static int generation_error(const Options *options, const SherlockGenerateResult *result,
                             SherlockGenerateStatus status) {
    printf("{\"format\":\"%s\",\"kind\":\"error\",\"ok\":false,\"source\":", SH_CLI_FORMAT);
    print_source(options);
    fputs(",\"error\":{\"code\":", stdout);
    json_string(status == SH_GENERATE_EXHAUSTED ? "generation_exhausted" : "generation_error");
    fputs(",\"message\":", stdout); json_string(result->reason);
    printf("},\"generation\":{\"attempts\":%u,\"nodes\":\"%" PRIu64 "\"}}",
           (unsigned)result->attempts, result->nodes);
    return finish_json(status == SH_GENERATE_EXHAUSTED ? CLI_INCOMPLETE : CLI_ENGINE_ERROR);
}

static int canonical_challenge(const Options *options, const char *resource_directory,
                                Challenge *challenge) {
    memset(challenge, 0, sizeof *challenge);
    if (options->source == SOURCE_ORIGINAL) {
        int status = load_table(options, resource_directory);
        if (status) return status;
        if (sherlock_generate(options->number, &challenge->puzzle) != 0)
            return error_json(CLI_ENGINE_ERROR, "puzzle_error", sherlock_core_error(), NULL, NULL, 0, 0);
    } else {
        SherlockGenerateStatus status = sherlock_generate_random(options->seed, NULL,
            &challenge->puzzle, &challenge->generation);
        if (status != SH_GENERATE_OK) return generation_error(options, &challenge->generation, status);
        if (challenge->generation.proof != SH_SOLVE_UNIQUE ||
            challenge->generation.seed != options->seed ||
            challenge->generation.version != SHERLOCK_NATIVE_GENERATOR_VERSION)
            return error_json(CLI_ENGINE_ERROR, "generation_error", "The generator did not return the requested, uniquely proved challenge identity.", NULL, NULL, 0, 0);
    }
    if (!valid_public_puzzle(&challenge->puzzle))
        return error_json(CLI_ENGINE_ERROR, "puzzle_error", "The engine returned malformed public puzzle fields.", NULL, NULL, 0, 0);
    challenge->fingerprint = public_fingerprint(&challenge->puzzle);
    if (sh_cli_format_challenge_id(&challenge->puzzle, options->source == SOURCE_NATIVE,
                                  options->seed, challenge->id, sizeof challenge->id) != 0)
        return error_json(CLI_ENGINE_ERROR, "identity_error", "The challenge identity could not be represented.", NULL, NULL, 0, 0);
    return CLI_OK;
}

static void print_identity(const Options *options, const Challenge *challenge) {
    fputs("\"challenge_id\":", stdout); json_string(challenge->id);
    fputs(",\"source\":", stdout); print_source(options);
    printf(",\"public_fingerprint\":{\"algorithm\":\"fnv1a64-public-v1\",\"hex\":\"%016" PRIx64 "\"}",
           challenge->fingerprint);
}

static int puzzle_json(const Options *options, const Challenge *challenge) {
    const SherlockPuzzle *puzzle = &challenge->puzzle;
    unsigned row, column, i, count = 0;
    printf("{\"format\":\"%s\",\"kind\":\"puzzle\",\"ok\":true,\"challenge\":{", SH_CLI_FORMAT);
    print_identity(options, challenge);
    fputs(",\"rows\":6,\"columns\":6,\"items_per_row\":6,"
          "\"answer_format\":{\"layout\":\"answer[row][column] = within-row item ID\","
          "\"item_minimum\":0,\"item_maximum\":5,\"row_constraint\":\"each row is a permutation of 0..5\"},"
          "\"object_ids\":{\"minimum\":0,\"maximum\":35,\"formula\":\"row * 6 + item\","
          "\"inverse_row\":\"id / 6 (integer division)\",\"inverse_item\":\"id % 6\"},"
          "\"column_function\":\"col(object) is its zero-based column in the submitted answer\","
          "\"clue_predicates\":{"
          "\"same_column\":\"col(a) == col(b)\","
          "\"not_same_column\":\"col(a) != col(b)\","
          "\"next_to\":\"abs(col(a)-col(b)) == 1\","
          "\"not_next_to\":\"abs(col(a)-col(b)) != 1\","
          "\"left_of\":\"col(a) < col(b)\","
          "\"between\":\"abs(col(a)-col(c)) == 2 && 2*col(b) == col(a)+col(c)\","
          "\"not_between\":\"abs(col(a)-col(c)) == 2 && 2*col(b) != col(a)+col(c)\","
          "\"reference\":\"true (informational object only)\"},\"givens\":[", stdout);
    for (row = 0; row < 6; ++row) for (column = 0; column < 6; ++column) {
        int item = puzzle->given[row][column];
        if (item < 0) continue;
        if (count++) putchar(',');
        printf("{\"row\":%u,\"column\":%u,\"item\":%u,\"object\":%u}",
               row, column, (unsigned)item, row * 6u + (unsigned)item);
    }
    fputs("],\"clues\":[", stdout);
    for (i = 0; i < puzzle->clue_count; ++i) {
        const SherlockClue *clue = &puzzle->clues[i];
        unsigned arity = clue_arity(clue->type), slot = puzzle->original_slot[i];
        if (i) putchar(',');
        printf("{\"index\":%u,\"type\":", i); json_string(clue_names[clue->type]);
        printf(",\"a\":%u", (unsigned)clue->a);
        if (arity >= 2) printf(",\"b\":%u", (unsigned)clue->b);
        if (arity == 3) printf(",\"c\":%u", (unsigned)clue->c);
        fputs(",\"display_slot\":", stdout);
        if (slot >= 36 && slot <= 74) printf("%u", slot); else fputs("null", stdout);
        putchar('}');
    }
    fputs("]}", stdout);
    if (options->source == SOURCE_NATIVE)
        printf(",\"generation\":{\"classification\":\"unique\",\"attempts\":%u,\"nodes\":\"%" PRIu64 "\"}",
               (unsigned)challenge->generation.attempts, challenge->generation.nodes);
    putchar('}'); return finish_json(CLI_OK);
}

static void nullable_index(int value) {
    if (value < 0) fputs("null", stdout); else printf("%d", value);
}

static int verify_json(const Options *options, const Challenge *challenge,
                        const uint8_t answer[6][6]) {
    SherlockVerifyResult result;
    SherlockVerifyStatus status = sherlock_verify_answer(&challenge->puzzle, answer, &result);
    if (status == SH_VERIFY_ERROR)
        return error_json(CLI_ENGINE_ERROR, "verification_error", result.reason, NULL, NULL, 0, 0);
    printf("{\"format\":\"%s\",\"kind\":\"verification\",\"ok\":true,", SH_CLI_FORMAT);
    print_identity(options, challenge);
    printf(",\"accepted\":%s,\"reason\":", status == SH_VERIFY_ACCEPTED ? "true" : "false");
    json_string(result.reason);
    fputs(",\"violation\":{\"row\":", stdout); nullable_index(result.row);
    fputs(",\"column\":", stdout); nullable_index(result.column);
    fputs(",\"clue_index\":", stdout); nullable_index(result.clue_index);
    fputs("}}", stdout);
    return finish_json(status == SH_VERIFY_ACCEPTED ? CLI_OK : CLI_REJECTED);
}

static int analyze_json(const Options *options, const Challenge *challenge) {
    SherlockSolveResult result;
    SherlockSolveStatus status = sherlock_analyze(&challenge->puzzle, options->node_budget, &result);
    const char *classification;
    if (status == SH_SOLVE_ERROR)
        return error_json(CLI_ENGINE_ERROR, "analysis_error", result.reason, NULL, NULL, 0, 0);
    classification = status == SH_SOLVE_UNIQUE ? "unique" : status == SH_SOLVE_MULTIPLE ? "multiple" :
                     status == SH_SOLVE_UNSAT ? "unsat" : "unknown";
    printf("{\"format\":\"%s\",\"kind\":\"analysis\",\"ok\":true,", SH_CLI_FORMAT);
    print_identity(options, challenge);
    fputs(",\"classification\":", stdout); json_string(classification);
    printf(",\"solutions_found\":%u,\"solution_count_is_exact\":%s,\"nodes\":\"%" PRIu64 "\","
           "\"node_budget\":\"%" PRIu64 "\",\"reason\":",
           (unsigned)result.solution_count,
           status == SH_SOLVE_UNIQUE || status == SH_SOLVE_UNSAT ? "true" : "false",
           result.nodes, options->node_budget);
    json_string(result.reason); putchar('}');
    return finish_json(status == SH_SOLVE_UNKNOWN ? CLI_INCOMPLETE : CLI_OK);
}

static void print_candidate_matrix(const uint8_t matrix[SH_SIZE][SH_SIZE]) {
    unsigned row, column;
    putchar('[');
    for (row = 0; row < SH_SIZE; ++row) {
        if (row) putchar(',');
        putchar('[');
        for (column = 0; column < SH_SIZE; ++column) {
            if (column) putchar(',');
            printf("%u", (unsigned)matrix[row][column]);
        }
        putchar(']');
    }
    putchar(']');
}

static void print_index_matrix(const int8_t matrix[SH_SIZE][SH_SIZE]) {
    unsigned row, column;
    putchar('[');
    for (row = 0; row < SH_SIZE; ++row) {
        if (row) putchar(',');
        putchar('[');
        for (column = 0; column < SH_SIZE; ++column) {
            if (column) putchar(',');
            printf("%d", (int)matrix[row][column]);
        }
        putchar(']');
    }
    putchar(']');
}

static void print_hint_target(enum SHHintKind kind, unsigned row,
                               unsigned column, unsigned item) {
    fputs("{\"kind\":", stdout);
    json_string(kind == SH_HINT_REMOVE ? "remove" : "choose");
    printf(",\"row\":%u,\"column\":%u,\"item\":%u}", row, column, item);
}

static void print_hint_support(const SHHintProof *record) {
    unsigned i;
    printf("{\"format\":\"sherlock-hint-support-1\",\"version\":%u,"
           "\"background_rule_mask\":%u,\"row_rule\":\"Each row is a permutation of items 0..5.\","
           "\"candidate_semantics\":\"candidates[row][column] is a mask; bit item permits that item at that column. All masks are frozen premises.\","
           "\"target\":", (unsigned)record->version, (unsigned)record->background_rules);
    print_hint_target(record->target.kind, record->target.row,
                      record->target.column, record->target.item);
    fputs(",\"selected_clue_index\":", stdout); nullable_index(record->selected_clue_index);
    printf(",\"source_clue_count\":%u,\"candidates\":", (unsigned)record->source_clue_count);
    print_candidate_matrix(record->candidates);
    fputs(",\"givens\":", stdout); print_index_matrix(record->given);
    printf(",\"support_count\":%u,\"clues\":[", (unsigned)record->support_count);
    for (i = 0; i < record->support_count; ++i) {
        const SHHintProofClue *support = &record->support[i];
        const SherlockClue *clue = &support->clue;
        unsigned arity = clue_arity(clue->type);
        if (i) putchar(',');
        printf("{\"index\":%u,\"type\":", (unsigned)support->index);
        json_string(clue_names[clue->type]);
        printf(",\"a\":%u", (unsigned)clue->a);
        if (arity >= 2) printf(",\"b\":%u", (unsigned)clue->b);
        if (arity == 3) printf(",\"c\":%u", (unsigned)clue->c);
        putchar('}');
    }
    fputs("]}", stdout);
}

static int prepare_hint_game(const Challenge *challenge, const HintStateInput *state,
                              SherlockGame *game) {
    unsigned row, column;
    sh_game_init(game, &challenge->puzzle, 0);
    if (game->outcome != SH_PLAYING)
        return error_json(CLI_ENGINE_ERROR, "state_error",
            "The canonical challenge could not initialize a player state.", NULL, NULL, 0, 0);
    if (!state) return CLI_OK;
    for (row = 0; row < SH_SIZE; ++row) for (column = 0; column < SH_SIZE; ++column) {
        int chosen = state->have_chosen ? state->chosen[row][column] : game->board.chosen[row][column];
        if (chosen >= 0 && state->candidates[row][column] != (uint8_t)(1u << chosen))
            return error_json(CLI_INPUT_ERROR, "invalid_state",
                "A chosen item requires exactly its singleton candidate mask.", NULL, NULL, 0, 0);
        if (game->fixed[row][column] &&
            (state->candidates[row][column] != game->board.candidates[row][column] ||
             chosen != game->board.chosen[row][column]))
            return error_json(CLI_INPUT_ERROR, "invalid_state",
                "State cannot change a canonical given's candidate mask or chosen item.", NULL, NULL, 0, 0);
    }
    memcpy(game->board.candidates, state->candidates, sizeof game->board.candidates);
    if (state->have_chosen) memcpy(game->board.chosen, state->chosen, sizeof game->board.chosen);
    return CLI_OK;
}

static int hint_json(const Options *options, const Challenge *challenge,
                      const HintStateInput *state, const SHHint *requested) {
    SherlockGame game;
    SHHint selected;
    SHHintProof record;
    SHHintProofResult report;
    SHHintProofStatus proof_status = SH_PROOF_UNRESOLVED;
    const char *classification, *reason;
    int status, have_target, proof_ran = 0;
    status = prepare_hint_game(challenge, state, &game);
    if (status) return status;
    memset(&selected, 0, sizeof selected);
    selected.clue_index = -1;
    if (requested) { selected = *requested; have_target = 1; }
    else {
        int found = sh_find_hint(&game, &selected, SH_CLI_HINT_SELECTION_NODES);
        if (found < 0)
            return error_json(CLI_ENGINE_ERROR, "hint_error",
                "The native hint selector rejected the canonical state.", NULL, NULL, 0, 0);
        have_target = found == 1;
    }
    if (have_target) {
        proof_ran = 1;
        proof_status = sh_explain_hint(&game, &selected, (unsigned)options->node_budget,
                                       &record, &report);
        if (proof_status == SH_PROOF_INVALID)
            return error_json(requested ? CLI_INPUT_ERROR : CLI_ENGINE_ERROR,
                requested ? "invalid_move" : "hint_error", report.reason, NULL, NULL, 0, 0);
        classification = proof_status == SH_PROOF_PROVED ? "proved" :
                         proof_status == SH_PROOF_REFUTED ? "refuted" :
                         proof_status == SH_PROOF_INCONSISTENT ? "inconsistent" : "unresolved";
        reason = report.reason;
        status = proof_status == SH_PROOF_PROVED ? CLI_OK :
                 proof_status == SH_PROOF_UNRESOLVED ? CLI_INCOMPLETE : CLI_REJECTED;
    } else {
        if (selected.kind != SH_HINT_NONE && selected.kind != SH_HINT_CONTRADICTION &&
            selected.kind != SH_HINT_UNRESOLVED)
            return error_json(CLI_ENGINE_ERROR, "hint_error",
                "The native selector returned an unsupported result.", NULL, NULL, 0, 0);
        classification = selected.kind == SH_HINT_CONTRADICTION ? "inconsistent" :
                         selected.kind == SH_HINT_UNRESOLVED ? "unresolved" : "none";
        reason = selected.explanation;
        status = selected.kind == SH_HINT_CONTRADICTION ? CLI_REJECTED :
                 selected.kind == SH_HINT_UNRESOLVED ? CLI_INCOMPLETE : CLI_OK;
    }
    printf("{\"format\":\"%s\",\"kind\":", SH_CLI_FORMAT);
    json_string(requested ? "hint_verification" : "hint");
    fputs(",\"ok\":true,", stdout); print_identity(options, challenge);
    fputs(",\"classification\":", stdout); json_string(classification);
    printf(",\"proved\":%s,\"reason\":", proof_status == SH_PROOF_PROVED ? "true" : "false");
    json_string(reason);
    fputs(",\"state_origin\":", stdout);
    json_string(state ? "submitted_assumptions" : "canonical_initial");
    fputs(",\"assumptions\":{\"candidate_masks\":\"premises\","
          "\"earlier_edits_verified\":false,"
          "\"meaning\":\"A proved result follows from these candidate masks, canonical givens and retained clues; it does not certify how earlier edits were obtained.\"},"
          "\"state\":{\"candidates\":", stdout);
    print_candidate_matrix((const uint8_t (*)[SH_SIZE])game.board.candidates);
    fputs(",\"chosen\":", stdout);
    print_index_matrix((const int8_t (*)[SH_SIZE])game.board.chosen);
    fputs("},\"proposed_move\":", stdout);
    if (have_target) print_hint_target(selected.kind, selected.row, selected.column, selected.item);
    else fputs("null", stdout);
    fputs(",\"selection\":", stdout);
    if (requested) fputs("null", stdout);
    else {
        printf("{\"policy\":\"native_visible_constraints_v1\",\"node_budget\":\"%u\","
               "\"budget_scope\":\"bounded fallback search; propagation is not counted\","
               "\"selected_clue_index\":", SH_CLI_HINT_SELECTION_NODES);
        nullable_index(selected.clue_index);
        fputs(",\"explanation\":", stdout); json_string(selected.explanation);
        putchar('}');
    }
    fputs(",\"proof\":", stdout);
    if (proof_ran) {
        printf("{\"node_budget\":\"%u\",\"nodes_used\":\"%u\",\"deletion_checks\":%u,"
               "\"reduction_complete\":%s,\"minimality\":",
               report.node_budget, report.nodes_used, report.deletion_checks,
               report.reduction_complete ? "true" : "false");
        json_string(proof_status == SH_PROOF_PROVED && report.reduction_complete ?
            "deletion_minimal_clues_relative_to_frozen_background" : "not_certified");
        putchar('}');
    } else fputs("null", stdout);
    fputs(",\"support_record\":", stdout);
    if (proof_status == SH_PROOF_PROVED) print_hint_support(&record);
    else fputs("null", stdout);
    putchar('}');
    return finish_json(status);
}

int sh_cli_main(int argc, char **argv, const char *resource_directory) {
    Options options;
    Challenge challenge;
    uint8_t answer[6][6];
    HintStateInput hint_state;
    SHHint requested_move;
    int status;
    if (argc < 2 || !argv || !argv[1]) return help_json();
    if (!strcmp(argv[1], "help") || !strcmp(argv[1], "--help"))
        return argc == 2 ? help_json() : argument_error("help accepts no additional arguments.", argv[2]);
    if (!strcmp(argv[1], "version") || !strcmp(argv[1], "--version"))
        return argc == 2 ? version_json() : argument_error("version accepts no additional arguments.", argv[2]);
    if (argc == 3 && !strcmp(argv[2], "--help") &&
        (!strcmp(argv[1], "puzzle") || !strcmp(argv[1], "generate") ||
         !strcmp(argv[1], "verify") || !strcmp(argv[1], "analyze") ||
         !strcmp(argv[1], "hint") || !strcmp(argv[1], "check-hint"))) return help_json();
    status = parse_options(argc, argv, &options);
    if (status) return status;
    if (options.command == CMD_VERIFY) {
        status = read_answer(options.answer_path, answer);
        if (status) return status;
    }
    if (options.have_state) {
        status = read_hint_document(options.state_path, &hint_state, NULL);
        if (status) return status;
    }
    if (options.have_move) {
        status = read_hint_document(options.move_path, NULL, &requested_move);
        if (status) return status;
    }
    status = canonical_challenge(&options, resource_directory, &challenge);
    if (status) return status;
    if (options.command == CMD_VERIFY)
        return verify_json(&options, &challenge, (const uint8_t (*)[6])answer);
    if (options.command == CMD_ANALYZE) return analyze_json(&options, &challenge);
    if (options.command == CMD_HINT || options.command == CMD_CHECK_HINT)
        return hint_json(&options, &challenge, options.have_state ? &hint_state : NULL,
                         options.have_move ? &requested_move : NULL);
    return puzzle_json(&options, &challenge);
}
