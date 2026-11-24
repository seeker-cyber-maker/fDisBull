/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Independent authored fixtures for the explicitly isolated v2 runtime.
 * These checks establish control/catalog bookkeeping, not rendered output,
 * a scheduler, original boot state, or complete original-game equivalence. */
#include "overlay/target/scumm/early.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned checks;
static const char *context;
static ScummTrace *trace;

#define CHECK(condition) do { \
    ++checks; \
    if (!(condition)) { \
        fprintf(stderr, "%s:%d: %s: %s\n", __FILE__, __LINE__, context, #condition); \
        exit(EXIT_FAILURE); \
    } \
} while (0)

static ScummRuntime fresh_runtime(void)
{
    ScummRuntime r = {0};
    r.enabled = 1;
    r.script_id = 1;
    for (unsigned type = 0; type < SCUMM_RESOURCE_TYPES; ++type) {
        r.counts[type] = 8;
    }
    r.resources[S_RES_SCRIPT][1].available = 1;
    r.resources[S_RES_SCRIPT][1].size = 5;
    scumm_runtime_reset(&r);
    return r;
}

static void fresh_trace(unsigned mask, unsigned capacity)
{
    memset(trace, 0, sizeof(*trace));
    trace->mask = mask;
    trace->capacity = capacity;
}

static void expect_success(const uint8_t *code, size_t size, ScummState *s,
                           ScummRuntime *r)
{
    uint64_t retired = s->retired;
    uint32_t pc = s->pc;
    CHECK(scumm_step_runtime(2, code, size, s, trace, r));
    CHECK(s->retired == retired + 1);
    CHECK(s->pc > pc);
    CHECK(s->fault == S_OK);
    CHECK(r->blocked_reason == S_BLOCK_NONE);
}

static void expect_failure(unsigned version, const uint8_t *code, size_t size,
                           ScummState *s, ScummRuntime *r, unsigned status,
                           unsigned fault, unsigned reason)
{
    ScummState before = *s;
    ScummRuntime previous = *r;
    CHECK(!scumm_step_runtime(version, code, size, s, trace, r));
    CHECK(s->status == status);
    CHECK(s->fault == fault);
    CHECK(s->fault_opcode == code[before.pc]);
    CHECK(r->blocked_reason == reason);
    before.status = s->status;
    before.fault = s->fault;
    before.fault_opcode = s->fault_opcode;
    previous.blocked_reason = r->blocked_reason;
    CHECK(memcmp(s, &before, sizeof(before)) == 0);
    CHECK(memcmp(r, &previous, sizeof(previous)) == 0);
    CHECK(trace->count == 0 && trace->sequence == 0);
    CHECK(trace->eligible[0] == 0 && trace->eligible[1] == 0);
    CHECK(trace->dropped[0] == 0 && trace->dropped[1] == 0);
    CHECK(!scumm_step_runtime(version, code, size, s, trace, r));
    CHECK(memcmp(s, &before, sizeof(before)) == 0);
    CHECK(memcmp(r, &previous, sizeof(previous)) == 0);
    CHECK(trace->count == 0 && trace->sequence == 0);
}

static void resource_commands(void)
{
    enum { NO_ACTION, LOAD, UNLOCK, LOCK };
    static const unsigned actions[16] = {
        NO_ACTION, LOAD, UNLOCK, LOCK, UNLOCK, LOCK, UNLOCK, LOCK,
        UNLOCK, LOCK, UNLOCK, LOCK, UNLOCK, LOCK, UNLOCK, LOCK
    };
    static const unsigned high[4] = {0x20, 0x30, 0x50, 0x60};
    char label[80];
    for (unsigned type = 0; type < 4; ++type) {
        for (unsigned low = 0; low < 16; ++low) {
            snprintf(label, sizeof(label), "resource type=%u command=%02x", type, high[type] + low);
            context = label;
            uint8_t code[] = {0x0c, 3, high[type] + low};
            ScummState s = {0};
            ScummRuntime r = fresh_runtime();
            ScummResource *res = &r.resources[type][3];
            res->available = actions[low] == LOAD;
            res->size = res->available ? 23 : 0;
            res->locked = actions[low] == UNLOCK || actions[low] == NO_ACTION;
            ScummRuntime expected = r;
            switch (actions[low]) {
            case LOAD: expected.resources[type][3].resident = 1; break;
            case LOCK: expected.resources[type][3].locked = 1; break;
            case UNLOCK: expected.resources[type][3].locked = 0; break;
            default: break;
            }
            fresh_trace(3, 4);
            expect_success(code, sizeof(code), &s, &r);
            CHECK(s.pc == 3 && s.status == S_RUNNING && s.retired == 1);
            CHECK(memcmp(&r, &expected, sizeof(r)) == 0);
            CHECK(trace->count == 1 && trace->eligible[0] == 1 && trace->eligible[1] == 0);
            CHECK(trace->events[0].channel == 0 && trace->events[0].size == 3);
            CHECK(memcmp(trace->events[0].bytes, code, sizeof(code)) == 0);
        }
    }
    context = "invalid resource types are no-ops before index validation";
    static const uint8_t invalid[] = {0x01, 0x11, 0x41, 0x71, 0x81, 0x91,
                                    0xa1, 0xb1, 0xc1, 0xd1, 0xe1, 0xf1};
    for (unsigned i = 0; i < sizeof(invalid); ++i) {
        uint8_t code[] = {0x0c, 255, invalid[i]};
        ScummState s = {0};
        ScummRuntime r = fresh_runtime(), expected = r;
        fresh_trace(3, 4);
        expect_success(code, sizeof(code), &s, &r);
        CHECK(memcmp(&r, &expected, sizeof(r)) == 0);
    }
    context = "zero resource operation and zero load ID";
    for (unsigned type = 0; type < 4; ++type) {
        uint8_t noop[] = {0x0c, 255, high[type]};
        uint8_t zero[] = {0x0c, 0, high[type] + 1};
        ScummState s = {0};
        ScummRuntime r = fresh_runtime(), expected = r;
        fresh_trace(0, 0);
        expect_success(noop, sizeof(noop), &s, &r);
        CHECK(memcmp(&r, &expected, sizeof(r)) == 0);
        s = (ScummState){0};
        /* Empty catalogs are valid; the executing script's catalog is retained. */
        if (type != S_RES_SCRIPT) r.counts[type] = 0;
        expected = r;
        expect_success(zero, sizeof(zero), &s, &r);
        CHECK(memcmp(&r, &expected, sizeof(r)) == 0);
    }
}

static void resource_boundaries(void)
{
    context = "unavailable load is non-retiring and atomic";
    uint8_t missing[] = {0x0c, 3, 0x21};
    ScummState s = {0};
    ScummRuntime r = fresh_runtime();
    r.user_state = 0xe0;
    r.resources[S_RES_COSTUME][3].locked = 1;
    fresh_trace(3, 4);
    expect_failure(2, missing, sizeof(missing), &s, &r,
                   S_BLOCKED, S_OK, S_BLOCK_RESOURCE_MISSING);

    context = "room load mapper is required before catalog index checking";
    uint8_t mapped[] = {0x0c, 200, 0x31};
    s = (ScummState){0}; r = fresh_runtime();
    fresh_trace(3, 4);
    expect_failure(2, mapped, sizeof(mapped), &s, &r,
                   S_BLOCKED, S_OK, S_BLOCK_ROOM_MAPPER);

    context = "room locks do not use the load mapper";
    uint8_t room_lock[] = {0x0c, 200, 0x33};
    s = (ScummState){0}; r = fresh_runtime();
    fresh_trace(3, 4);
    expect_failure(2, room_lock, sizeof(room_lock), &s, &r,
                   S_FAULT, S_BAD_RESOURCE, S_BLOCK_NONE);

    context = "resource index at catalog bound is invalid";
    uint8_t bound[] = {0x0c, 8, 0x63};
    s = (ScummState){0}; r = fresh_runtime();
    fresh_trace(3, 4);
    expect_failure(2, bound, sizeof(bound), &s, &r,
                   S_FAULT, S_BAD_RESOURCE, S_BLOCK_NONE);

    context = "variable resource operand retains value 300 instead of byte 44";
    uint8_t variable[] = {0x8c, 20, 0x21};
    s = (ScummState){0}; s.vars[20] = 300; r = fresh_runtime();
    r.counts[S_RES_COSTUME] = 64;
    r.resources[S_RES_COSTUME][44].available = 1;
    r.resources[S_RES_COSTUME][44].size = 12;
    fresh_trace(3, 4);
    expect_failure(2, variable, sizeof(variable), &s, &r,
                   S_FAULT, S_BAD_RESOURCE, S_BLOCK_NONE);

    context = "last permitted resource index loads without wrap";
    uint8_t last[] = {0x0c, 255, 0x61};
    s = (ScummState){0}; r = fresh_runtime();
    r.counts[S_RES_SOUND] = 256;
    r.resources[S_RES_SOUND][255].available = 1;
    r.resources[S_RES_SOUND][255].size = 12;
    fresh_trace(3, 4);
    expect_success(last, sizeof(last), &s, &r);
    CHECK(r.resources[S_RES_SOUND][255].resident == 1);
    CHECK(r.resources[S_RES_SOUND][255].available == 1);
    CHECK(r.resources[S_RES_SOUND][255].size == 12);

    context = "truncated resource cannot mutate an available slot";
    uint8_t truncated[] = {0x0c, 3};
    s = (ScummState){0}; r = fresh_runtime();
    r.resources[S_RES_COSTUME][3].available = 1;
    r.resources[S_RES_COSTUME][3].size = 12;
    fresh_trace(3, 4);
    expect_failure(2, truncated, sizeof(truncated), &s, &r,
                   S_FAULT, S_TRUNCATED, S_BLOCK_NONE);
}

static void cursor_controls(void)
{
    struct CursorFixture { uint8_t low, high, ui, put, cursor; uint16_t value; };
    static const struct CursorFixture cases[] = {
        {7, 0x00, 0xe0, 1, 1, 7}, {0, 0x00, 0xe0, 1, 1, 99},
        {0, 0x04, 0x00, 1, 1, 99}, {0, 0xa4, 0xa0, 1, 1, 99},
        {0, 0x02, 0xe0, 0, 0, 99}, {0, 0x12, 0xe0, 1, 1, 99},
        {0, 0x08, 0xe0, 1, 1, 99}, {0, 0x09, 0xe0, 1, 1, 99},
        {0, 0x01, 0xe0, 1, 1, 99}, {0, 0x20, 0xe0, 1, 1, 99},
        {255, 0xff, 0xe0, 1, 1, 255}
    };
    char label[64];
    for (unsigned n = 0; n < sizeof(cases) / sizeof(cases[0]); ++n) {
        snprintf(label, sizeof(label), "cursor flags %02x value %u", cases[n].high, cases[n].low);
        context = label;
        uint8_t code[] = {0x60, cases[n].low, cases[n].high};
        ScummState s = {0}; s.vars[21] = 99;
        ScummRuntime r = fresh_runtime();
        r.user_state = 0xe0; r.user_put = 1; r.cursor_visible = 1;
        r.current_room = 7; r.camera_mode = 2; r.ui_revision = 9;
        ScummRuntime expected = r;
        expected.user_state = cases[n].ui;
        expected.user_put = cases[n].put;
        expected.cursor_visible = cases[n].cursor;
        expected.ui_revision = 10;
        fresh_trace(3, 4);
        expect_success(code, sizeof(code), &s, &r);
        CHECK(s.vars[21] == cases[n].value);
        CHECK(memcmp(&r, &expected, sizeof(r)) == 0);
        CHECK(trace->count == 1 && trace->eligible[1] == 0);
    }

    context = "cursor variable uses full word and read indirection";
    uint8_t indirect[] = {0xe0, 14};
    ScummState s = {0}; s.vars[14] = 20; s.vars[20] = 0x12c8; s.vars[21] = 99;
    ScummRuntime r = fresh_runtime();
    r.cutscene_active = 1;
    fresh_trace(3, 4);
    expect_success(indirect, sizeof(indirect), &s, &r);
    CHECK(s.pc == 2 && s.vars[21] == 200);
    CHECK(s.vars[14] == 20 && s.vars[20] == 0x12c8);
    CHECK(r.user_put == 1 && r.cursor_visible == 1 && r.user_state == 0);
    CHECK(r.cutscene_active == 1 && r.ui_revision == 1);

    context = "truncated cursor word has no partial variable or UI changes";
    uint8_t truncated[] = {0x60, 200};
    s = (ScummState){0}; s.vars[21] = 99; r = fresh_runtime();
    r.user_state = 0xe0; r.user_put = 1; r.cursor_visible = 1;
    fresh_trace(3, 4);
    expect_failure(2, truncated, sizeof(truncated), &s, &r,
                   S_FAULT, S_TRUNCATED, S_BLOCK_NONE);
}

static void cutscene_controls(void)
{
    context = "cutscene entry saves and updates all declared fields";
    uint8_t begin[] = {0x40};
    ScummRuntime r = fresh_runtime();
    r.user_state = 0xe0; r.user_put = 1; r.cursor_visible = 1;
    r.current_room = 7; r.camera_mode = 2; r.ui_revision = 9;
    r.override_pc = 1234; r.override_script = 88;
    ScummState s = {0};
    s.vars[5] = 1; s.vars[21] = 99; s.vars[26] = 5;
    s.vars[27] = 6; s.vars[28] = 7; s.vars[29] = 8; s.vars[38] = 42;
    ScummRuntime expected = r;
    expected.saved_user_state = 0xf0; expected.saved_cursor = 99;
    expected.saved_room = 7; expected.saved_camera_mode = 2;
    expected.user_state = 0; expected.user_put = 0; expected.cursor_visible = 0;
    expected.cutscene_active = 1; expected.override_pc = 0; expected.ui_revision = 10;
    ScummState expected_s = s;
    expected_s.vars[21] = 200; expected_s.vars[26] = 42;
    expected_s.vars[27] = expected_s.vars[28] = expected_s.vars[29] = 0;
    expected_s.pc = 1; expected_s.retired = 1; expected_s.status = S_RUNNING;
    fresh_trace(3, 4);
    expect_success(begin, sizeof(begin), &s, &r);
    CHECK(memcmp(&r, &expected, sizeof(r)) == 0);
    CHECK(memcmp(&s, &expected_s, sizeof(s)) == 0);
    CHECK(r.override_script == 88 && s.vars[5] == 1);

    context = "nested cutscene rejected before replacing saved context";
    s.pc = 0; s.status = S_READY;
    fresh_trace(3, 4);
    expect_failure(2, begin, sizeof(begin), &s, &r,
                   S_BLOCKED, S_OK, S_BLOCK_CUTSCENE_NESTED);

    context = "sentence script cannot silently stop itself at cutscene entry";
    s = (ScummState){0}; r = fresh_runtime(); r.script_id = 2;
    r.resources[S_RES_SCRIPT][2].available = 1;
    r.resources[S_RES_SCRIPT][2].size = 1;
    scumm_runtime_reset(&r);
    s.vars[21] = 99; r.user_state = 0xe0;
    fresh_trace(3, 4);
    expect_failure(2, begin, sizeof(begin), &s, &r,
                   S_BLOCKED, S_OK, S_BLOCK_SENTENCE_OWNER);

    context = "end cutscene preserves context while camera semantics are absent";
    uint8_t end[] = {0xc0};
    s = expected_s; s.pc = 0; s.status = S_READY; r = expected;
    fresh_trace(3, 4);
    expect_failure(2, end, sizeof(end), &s, &r,
                   S_BLOCKED, S_OK, S_BLOCK_UNIMPLEMENTED);
}

static void mode_admission(void)
{
    context = "enabled runtime rejects non-v2 machines";
    uint8_t stop[] = {0};
    for (unsigned version = 0; version < 2; ++version) {
        ScummState s = {0}; ScummRuntime r = fresh_runtime();
        fresh_trace(3, 4);
        expect_failure(version, stop, sizeof(stop), &s, &r,
                       S_FAULT, S_BAD_VERSION, S_BLOCK_NONE);
    }

    context = "disabled and absent runtime preserve the legacy blocked behavior";
    uint8_t resource[] = {0x0c, 3, 0x21};
    ScummState legacy = {0}, disabled = {0}, absent = {0};
    ScummRuntime r = fresh_runtime(); r.enabled = 0;
    r.resources[S_RES_COSTUME][3].available = 1;
    r.resources[S_RES_COSTUME][3].size = 12;
    ScummRuntime previous = r;
    fresh_trace(0, 0);
    CHECK(!scumm_step(2, resource, sizeof(resource), &legacy, NULL));
    CHECK(!scumm_step_runtime(2, resource, sizeof(resource), &disabled, NULL, &r));
    CHECK(!scumm_step_runtime(2, resource, sizeof(resource), &absent, NULL, NULL));
    CHECK(memcmp(&legacy, &disabled, sizeof(legacy)) == 0);
    CHECK(memcmp(&legacy, &absent, sizeof(legacy)) == 0);
    CHECK(memcmp(&r, &previous, sizeof(r)) == 0);

    context = "scheduler operations remain explicitly blocked";
    static const uint8_t ops[] = {0x42, 0x62, 0x4a};
    for (unsigned i = 0; i < sizeof(ops); ++i) {
        uint8_t code[] = {ops[i], 2};
        ScummState s = {0}; r = fresh_runtime();
        fresh_trace(3, 4);
        expect_failure(2, code, sizeof(code), &s, &r,
                       S_BLOCKED, S_OK, S_BLOCK_UNIMPLEMENTED);
    }
}

static void observations_and_reset(void)
{
    context = "runtime architecture is independent of observer capacity and mask";
    static const uint8_t code[] = {0x0c, 3, 0x21, 0x0c, 3, 0x23,
                                   0x60, 7, 0xe4, 0x40, 0x00};
    static const unsigned capacities[] = {0, 1, 8};
    ScummState baseline = {0}; ScummRuntime baseline_r = {0};
    for (unsigned mask = 0; mask < 4; ++mask) {
        for (unsigned c = 0; c < sizeof(capacities) / sizeof(capacities[0]); ++c) {
            ScummState s = {0}; s.vars[38] = 9;
            ScummRuntime r = fresh_runtime();
            r.resources[S_RES_COSTUME][3].available = 1;
            r.resources[S_RES_COSTUME][3].size = 23;
            fresh_trace(mask, capacities[c]);
            for (unsigned instruction = 0; instruction < 5; ++instruction) {
                expect_success(code, sizeof(code), &s, &r);
            }
            CHECK(s.pc == sizeof(code) && s.status == S_RETURN && s.retired == 5);
            CHECK(s.vars[21] == 200 && s.vars[26] == 9 && s.vars[38] == 9);
            CHECK(r.ui_revision == 2 && r.cutscene_active == 1 && r.saved_cursor == 7);
            CHECK(r.resources[S_RES_COSTUME][3].resident && r.resources[S_RES_COSTUME][3].locked);
            if (mask == 0 && c == 0) { baseline = s; baseline_r = r; }
            CHECK(memcmp(&s, &baseline, sizeof(s)) == 0);
            CHECK(memcmp(&r, &baseline_r, sizeof(r)) == 0);
            unsigned eligible = (mask & 1) ? 5 : 0;
            unsigned retained = eligible < capacities[c] ? eligible : capacities[c];
            CHECK(trace->count == retained);
            CHECK(trace->eligible[0] == eligible && trace->eligible[1] == 0);
            CHECK(trace->dropped[0] == eligible - retained && trace->dropped[1] == 0);
        }
    }
    context = "runtime reset preserves catalog and binds only current script residency";
    ScummRuntime r = baseline_r, expected = baseline_r;
    r.override_pc = 999; r.override_script = 77; r.sentence_count = 3;
    r.blocked_reason = S_BLOCK_RESOURCE_MISSING;
    for (unsigned type = 0; type < 4; ++type) {
        for (unsigned i = 0; i < 256; ++i) {
            expected.resources[type][i].resident = 0;
            expected.resources[type][i].locked = 0;
        }
    }
    expected.resources[S_RES_SCRIPT][1].resident = 1;
    expected.user_state = expected.user_put = expected.cursor_visible = 0;
    expected.current_room = expected.camera_mode = expected.cutscene_active = 0;
    expected.saved_user_state = expected.saved_room = expected.saved_camera_mode = 0;
    expected.saved_cursor = 0; expected.override_pc = 0; expected.override_script = 0;
    expected.sentence_count = 0; expected.ui_revision = 0; expected.blocked_reason = 0;
    scumm_runtime_reset(&r);
    CHECK(memcmp(&r, &expected, sizeof(r)) == 0);
}

int main(void)
{
    trace = calloc(1, sizeof(*trace));
    context = "allocate trace";
    CHECK(trace != NULL);
    resource_commands();
    resource_boundaries();
    cursor_controls();
    cutscene_controls();
    mode_admission();
    observations_and_reset();
    free(trace);
    printf("isolated v2 runtime authored checks passed: %u assertions\n", checks);
    return 0;
}
