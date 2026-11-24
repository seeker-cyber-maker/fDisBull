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
            unsigned scene_changes = actions[low] == NO_ACTION ? 0 : 1;
            CHECK(trace->count == 1 + scene_changes);
            CHECK(trace->eligible[0] == 1 && trace->eligible[1] == scene_changes);
            CHECK(trace->events[0].channel == 0 && trace->events[0].size == 3);
            CHECK(memcmp(trace->events[0].bytes, code, sizeof(code)) == 0);
            if (scene_changes) {
                CHECK(trace->events[1].channel == 1 && trace->events[1].kind == S_EVENT_RESOURCE);
                CHECK(trace->events[1].resource_type == type && trace->events[1].resource_id == 3);
            }
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
        CHECK(trace->count == 2 && trace->eligible[1] == 1);
        CHECK(trace->events[1].kind == S_EVENT_CONTROL);
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
            /* Load, lock, cursor and cutscene each commit a scene change;
             * stop contributes only its retirement. One shared drop-new
             * journal retains this independently specified event order. */
            static const unsigned channels[] = {0, 1, 0, 1, 0, 1, 0, 1, 0};
            unsigned eligible[2] = {(mask & 1) ? 5 : 0, (mask & 2) ? 4 : 0};
            unsigned stored[2] = {0}, retained = 0;
            for (unsigned event = 0; event < sizeof(channels) / sizeof(channels[0]); ++event) {
                unsigned channel = channels[event];
                if ((mask & (1u << channel)) && retained < capacities[c]) {
                    CHECK(trace->events[retained].channel == channel);
                    ++stored[channel];
                    ++retained;
                }
            }
            CHECK(trace->count == retained);
            CHECK(trace->helper_calls == ((mask & 1) ? 5 : (mask & 2) ? 4 : 0));
            for (unsigned channel = 0; channel < 2; ++channel) {
                CHECK(trace->eligible[channel] == eligible[channel]);
                CHECK(trace->stored[channel] == stored[channel]);
                CHECK(trace->dropped[channel] == eligible[channel] - stored[channel]);
            }
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

static void verb_creation_and_delete(void)
{
    context = "verb creation commits authored fields and one scene change";
    static const uint8_t create[] = {0x7a, 9, 3, 4, 0, 5, 'U', 's', 'e', 0};
    ScummState s = {0};
    ScummRuntime r = fresh_runtime(), expected = r;
    ScummVerb created = {0};
    created.id = 9; created.x = 24; created.y = 32;
    created.color = 2; created.hicolor = 14; created.dimcolor = 8;
    created.mode = 1; created.key = 'q'; created.prep = 5;
    created.name_pc = 6; created.name_size = 3;
    expected.verbs[1] = created; expected.ui_revision = 1;
    ScummVerb previous = r.verbs[1];
    fresh_trace(3, 4);
    expect_success(create, sizeof(create), &s, &r);
    CHECK(memcmp(&r, &expected, sizeof(r)) == 0);
    CHECK(trace->count == 2 && trace->eligible[1] == 1);
    CHECK(trace->events[0].kind == S_EVENT_RETIRE);
    ScummEvent *event = &trace->events[1];
    CHECK(event->kind == S_EVENT_VERB && event->verb_slot == 1);
    CHECK(memcmp(&event->before_verb, &previous, sizeof(previous)) == 0);
    CHECK(memcmp(&event->after_verb, &created, sizeof(created)) == 0);
    CHECK(event->before_ui_revision == 0 && event->after_ui_revision == 1);
    CHECK(event->insn.count == 3 && event->insn.arg[1].kind == S_IMM);
    CHECK(event->resolved[0] == 9 && event->resolved[1] == 0 && event->resolved[2] == 5);
    CHECK(event->insn.payload_pc == 2 && event->insn.payload_size == 8);

    context = "replacement preserves an assigned empty name and pixel origin";
    static const uint8_t replace[] = {0x7a, 11, 255, 254, 0, 7, 0};
    s = (ScummState){0};
    fresh_trace(2, 2);
    expect_success(replace, sizeof(replace), &s, &r);
    CHECK(r.verbs[1].id == 11 && r.verbs[1].x == 2040 && r.verbs[1].y == 2032);
    CHECK(r.verbs[1].name_pc == 6 && r.verbs[1].name_size == 0);
    CHECK(r.verbs[1].prep == 7 && r.verbs[1].mode == 1 && r.ui_revision == 2);

    context = "delete clears identity mode save and name but preserves metadata";
    static const uint8_t remove[] = {0x7a, 0, 0};
    r.verbs[1].saveid = 17;
    ScummVerb deleted = r.verbs[1];
    deleted.id = deleted.saveid = deleted.mode = 0;
    deleted.name_pc = 0; deleted.name_size = 0;
    s = (ScummState){0}; fresh_trace(3, 2);
    expect_success(remove, sizeof(remove), &s, &r);
    CHECK(memcmp(&r.verbs[1], &deleted, sizeof(deleted)) == 0);
    CHECK(trace->events[1].before_verb.saveid == 17 && r.ui_revision == 3);

    context = "repeated delete records its UI invalidation without invented slot changes";
    s = (ScummState){0}; fresh_trace(2, 2);
    expect_success(remove, sizeof(remove), &s, &r);
    event = &trace->events[0];
    CHECK(trace->count == 1 && trace->eligible[1] == 1);
    CHECK(event->kind == S_EVENT_VERB && event->verb_slot == 1);
    CHECK(memcmp(&event->before_verb, &event->after_verb, sizeof(ScummVerb)) == 0);
    CHECK(event->before_ui_revision == 3 && event->after_ui_revision == 4);

    context = "reset restores all one hundred slots including a disabled runtime";
    for (unsigned enabled = 0; enabled < 2; ++enabled) {
        r.enabled = enabled;
        r.verbs[0].mode = 255; r.verbs[99] = created;
        scumm_runtime_reset(&r);
        ScummVerb defaults = {0}; defaults.color = 2; defaults.charset = 1;
        for (unsigned slot = 0; slot < SCUMM_VERBS; ++slot) {
            CHECK(memcmp(&r.verbs[slot], &defaults, sizeof(defaults)) == 0);
        }
        CHECK(r.ui_revision == 0 && r.script_id == 1 && r.counts[S_RES_SCRIPT] == 8);
        CHECK(r.resources[S_RES_SCRIPT][1].available == 1);
        CHECK(r.resources[S_RES_SCRIPT][1].resident == enabled);
    }
}

static void verb_slot_and_mode_selection(void)
{
    context = "Amiga verb keyboard mapping ends after slot fifteen";
    static const unsigned slots[] = {1, 15, 16, 99};
    static const unsigned keys[] = {'q', 'b', 0, 0};
    for (unsigned n = 0; n < sizeof(slots) / sizeof(slots[0]); ++n) {
        uint8_t code[] = {0x7a, 4, 1, 2, slots[n] - 1, 0, 0};
        ScummState s = {0}; ScummRuntime r = fresh_runtime();
        fresh_trace(2, 1);
        expect_success(code, sizeof(code), &s, &r);
        CHECK(r.verbs[slots[n]].key == keys[n]);
        CHECK(trace->events[0].verb_slot == slots[n]);
    }

    context = "all mode bytes survive literal lookup and saved slots are excluded";
    ScummState s = {0}; ScummRuntime r = fresh_runtime();
    r.verbs[2].id = r.verbs[7].id = 42; r.verbs[2].saveid = 1;
    r.verbs[2].mode = 19;
    for (unsigned mode = 0; mode <= 255; ++mode) {
        /* The opcode's variable bit does not apply to the mode form. */
        uint8_t code[] = {0xfa, 255, 42, mode};
        s = (ScummState){0}; s.vars[42] = 65535;
        fresh_trace(2, 1);
        expect_success(code, sizeof(code), &s, &r);
        CHECK(r.verbs[7].mode == mode && r.verbs[2].mode == 19);
        CHECK(trace->events[0].verb_slot == 7);
        CHECK(trace->events[0].insn.arg[1].kind == S_IMM);
        CHECK(trace->events[0].resolved[2] == mode);
    }
    CHECK(r.ui_revision == 256);
    context = "mode lookup takes the first unsaved matching slot";
    static const uint8_t first[] = {0x7a, 255, 42, 2};
    r.verbs[2].saveid = 0; s = (ScummState){0}; fresh_trace(2, 1);
    expect_success(first, sizeof(first), &s, &r);
    CHECK(r.verbs[2].mode == 2 && r.verbs[7].mode == 255);
    CHECK(trace->events[0].verb_slot == 2);

    context = "lookup miss changes reserved slot zero without fabricating a verb";
    static const uint8_t missing[] = {0x7a, 255, 88, 253};
    s = (ScummState){0}; fresh_trace(2, 1);
    expect_success(missing, sizeof(missing), &s, &r);
    CHECK(trace->events[0].verb_slot == 0);
    CHECK(r.verbs[0].id == 0 && r.verbs[0].mode == 253 && r.verbs[0].name_pc == 0);

    context = "verb ID zero matches the first unsaved empty ordinary slot";
    static const uint8_t empty_id[] = {0x7a, 255, 0, 254};
    s = (ScummState){0}; fresh_trace(2, 1);
    expect_success(empty_id, sizeof(empty_id), &s, &r);
    CHECK(trace->events[0].verb_slot == 1);
    CHECK(r.verbs[1].mode == 254 && r.verbs[0].mode == 253);
}

static void verb_indirection_and_bounds(void)
{
    for (unsigned selector = 14; selector <= 16; ++selector) {
        context = "variable create resolves v14 through v16 before adding one";
        uint8_t code[] = {0xfa, 13, 9, 8, selector, 6, 0};
        ScummState s = {0}; ScummRuntime r = fresh_runtime();
        s.vars[selector] = 40; s.vars[40] = 98;
        fresh_trace(3, 2);
        expect_success(code, sizeof(code), &s, &r);
        CHECK(r.verbs[99].id == 13 && r.verbs[99].x == 72 && r.verbs[99].y == 64);
        CHECK(trace->events[1].insn.arg[1].kind == S_VAR);
        CHECK(trace->events[1].insn.arg[1].value == selector);
        CHECK(trace->events[1].resolved[1] == 98 && trace->events[1].verb_slot == 99);

        context = "variable delete uses the same indirect slot selection";
        uint8_t remove[] = {0xfa, 0, selector};
        s.pc = 0; s.status = S_READY; fresh_trace(3, 2);
        expect_success(remove, sizeof(remove), &s, &r);
        CHECK(r.verbs[99].id == 0 && r.verbs[99].name_pc == 0);
        CHECK(trace->events[1].resolved[1] == 98 && trace->events[1].verb_slot == 99);
    }

    static const unsigned invalid[] = {99, 255, 65535};
    for (unsigned n = 0; n < sizeof(invalid) / sizeof(invalid[0]); ++n) {
        for (unsigned create = 0; create < 2; ++create) {
            context = "out of range slot is rejected before mutation without byte wrapping";
            const uint8_t remove[] = {0xfa, 0, 20};
            const uint8_t add[] = {0xfa, 3, 9, 8, 20, 6, 0};
            const uint8_t *code = create ? add : remove;
            size_t size = create ? sizeof(add) : sizeof(remove);
            ScummState s = {0}; ScummRuntime r = fresh_runtime();
            s.vars[20] = invalid[n]; r.verbs[1].id = 25;
            fresh_trace(3, 2);
            expect_failure(2, code, size, &s, &r, S_FAULT, S_BAD_VERB, S_BLOCK_NONE);
        }
    }
    context = "invalid indirect variable faults before verb slot resolution";
    static const uint8_t bad_var[] = {0xfa, 3, 9, 8, 14, 6, 0};
    ScummState s = {0}; ScummRuntime r = fresh_runtime(); s.vars[14] = 256;
    fresh_trace(3, 2);
    expect_failure(2, bad_var, sizeof(bad_var), &s, &r, S_FAULT, S_BAD_VAR, S_BLOCK_NONE);
}

static void verb_encoded_names(void)
{
    context = "verb resource string extent retains escape arguments containing zeros";
    static const uint8_t code[] = {
        0x7a, 4, 1, 2, 3, 0, 'A', 0xff, 4, 0, 0, 'B',
        0xff, 1, 0xff, 2, 0xff, 3, 0xff, 8, 0
    };
    ScummInsn insn;
    CHECK(scumm_decode(2, code, sizeof(code), 0, &insn));
    CHECK(insn.next == 21 && insn.size == 21 && insn.payload_pc == 2 && insn.payload_size == 19);
    ScummState s = {0}; ScummRuntime r = fresh_runtime();
    fresh_trace(3, 2);
    expect_success(code, sizeof(code), &s, &r);
    CHECK(r.verbs[4].name_pc == 6 && r.verbs[4].name_size == 14);
    CHECK(trace->events[1].size == sizeof(code));
    CHECK(memcmp(trace->events[1].bytes, code, sizeof(code)) == 0);

    context = "every truncated header or encoded name prefix is non-retiring and atomic";
    for (size_t size = 1; size < sizeof(code); ++size) {
        s = (ScummState){0}; r = fresh_runtime(); r.verbs[4].id = 22;
        fresh_trace(3, 2);
        expect_failure(2, code, size, &s, &r, S_FAULT, S_TRUNCATED, S_BLOCK_NONE);
    }
    context = "escape command zero is not the outer string terminator";
    static const uint8_t zero_command[] = {0x7a, 4, 1, 2, 3, 0, 0xff, 0, 0, 0, 'X', 0};
    CHECK(scumm_decode(2, zero_command, sizeof(zero_command), 0, &insn));
    CHECK(insn.size == sizeof(zero_command) && insn.payload_size == 10);

    context = "full verb instruction admits exactly 514 bytes";
    uint8_t longest[SCUMM_INSN_MAX + 1];
    memset(longest, 'N', sizeof(longest));
    const uint8_t header[] = {0x7a, 8, 1, 2, 0, 0};
    memcpy(longest, header, sizeof(header)); longest[SCUMM_INSN_MAX - 1] = 0;
    s = (ScummState){0}; r = fresh_runtime(); fresh_trace(3, 2);
    expect_success(longest, SCUMM_INSN_MAX, &s, &r);
    CHECK(s.pc == 514 && r.verbs[1].name_pc == 6 && r.verbs[1].name_size == 507);
    CHECK(trace->events[1].size == 514);
    context = "a terminator beyond the instruction bound cannot commit";
    longest[SCUMM_INSN_MAX - 1] = 'N'; longest[SCUMM_INSN_MAX] = 0;
    s = (ScummState){0}; r = fresh_runtime(); fresh_trace(3, 2);
    expect_failure(2, longest, sizeof(longest), &s, &r, S_FAULT, S_TRUNCATED, S_BLOCK_NONE);
}

static void transactional_counter_limits(void)
{
    static const struct {
        uint8_t code[7]; size_t size;
    } revisions[] = {
        {{0x7a, 3, 1, 2, 0, 0, 0}, 7}, {{0x7a, 0, 0}, 3},
        {{0x7a, 255, 3, 1}, 4}, {{0x60, 9, 0xe4}, 3}, {{0x40}, 1}
    };
    for (unsigned mask = 0; mask < 4; ++mask) {
        for (unsigned n = 0; n < sizeof(revisions) / sizeof(revisions[0]); ++n) {
            context = "UI revision exhaustion faults before verb cursor or cutscene mutation";
            ScummState s = {0}; ScummRuntime r = fresh_runtime();
            s.vars[21] = 77; s.vars[38] = 42; r.user_state = 0xe0;
            r.verbs[1].id = 3; r.verbs[1].mode = 2; r.ui_revision = UINT64_MAX;
            fresh_trace(mask, 2);
            expect_failure(2, revisions[n].code, revisions[n].size, &s, &r,
                           S_FAULT, S_COUNTER_EXHAUSTED, S_BLOCK_NONE);
            CHECK(trace->helper_calls == 0);
        }
        context = "retirement exhaustion is checked before scalar or verb mutation";
        static const uint8_t scalar[] = {0x46, 20};
        ScummState s = {0}; ScummRuntime r = fresh_runtime();
        s.retired = UINT64_MAX; s.vars[20] = 99;
        fresh_trace(mask, 2);
        expect_failure(2, scalar, sizeof(scalar), &s, &r,
                       S_FAULT, S_COUNTER_EXHAUSTED, S_BLOCK_NONE);
        s = (ScummState){0}; s.retired = UINT64_MAX;
        fresh_trace(mask, 2);
        expect_failure(2, revisions[0].code, revisions[0].size, &s, &r,
                       S_FAULT, S_COUNTER_EXHAUSTED, S_BLOCK_NONE);
    }
    context = "the last representable verb retirement and UI revision commit";
    static const uint8_t last[] = {0x7a, 5, 1, 2, 0, 0, 0, 0};
    ScummState s = {0}; ScummRuntime r = fresh_runtime();
    s.retired = UINT64_MAX - 1; r.ui_revision = UINT64_MAX - 1;
    fresh_trace(3, 2);
    expect_success(last, sizeof(last), &s, &r);
    CHECK(s.retired == UINT64_MAX && r.ui_revision == UINT64_MAX);
    CHECK(trace->events[1].after_ui_revision == UINT64_MAX);
    fresh_trace(3, 2);
    expect_failure(2, last, sizeof(last), &s, &r,
                   S_FAULT, S_COUNTER_EXHAUSTED, S_BLOCK_NONE);

    context = "full UI revision does not block scalar operations that do not revise UI";
    static const uint8_t scalar[] = {0x46, 20};
    s = (ScummState){0}; r = fresh_runtime(); r.ui_revision = UINT64_MAX;
    fresh_trace(2, 2);
    expect_success(scalar, sizeof(scalar), &s, &r);
    CHECK(s.vars[20] == 1 && r.ui_revision == UINT64_MAX && trace->count == 0);
}

static void verb_modes_and_admission(void)
{
    context = "verb architecture and exact shared journal order are invariant across modes";
    static const uint8_t code[] = {
        0x7a, 9, 3, 4, 0, 0, 'A', 0, 0x7a, 255, 9, 255,
        0x7a, 0, 0, 0x7a, 0, 0, 0
    };
    static const unsigned capacities[] = {0, 1, 9};
    static const unsigned channels[] = {0, 1, 0, 1, 0, 1, 0, 1, 0};
    ScummState baseline = {0}; ScummRuntime baseline_r = {0};
    for (unsigned mask = 0; mask < 4; ++mask) {
        for (unsigned n = 0; n < sizeof(capacities) / sizeof(capacities[0]); ++n) {
            ScummState s = {0}; ScummRuntime r = fresh_runtime();
            fresh_trace(mask, capacities[n]);
            for (unsigned instruction = 0; instruction < 5; ++instruction) {
                expect_success(code, sizeof(code), &s, &r);
            }
            if (!mask && !n) { baseline = s; baseline_r = r; }
            CHECK(memcmp(&s, &baseline, sizeof(s)) == 0);
            CHECK(memcmp(&r, &baseline_r, sizeof(r)) == 0);
            CHECK(s.status == S_RETURN && s.retired == 5 && r.ui_revision == 4);
            CHECK(r.verbs[1].id == 0 && r.verbs[1].x == 24 && r.verbs[1].key == 'q');
            unsigned retained = 0, stored[2] = {0};
            unsigned eligible[2] = {(mask & 1) ? 5 : 0, (mask & 2) ? 4 : 0};
            for (unsigned e = 0; e < sizeof(channels) / sizeof(channels[0]); ++e) {
                unsigned channel = channels[e];
                if ((mask & (1u << channel)) && retained < capacities[n]) {
                    CHECK(trace->events[retained].channel == channel);
                    CHECK(trace->events[retained].kind == (channel ? S_EVENT_VERB : S_EVENT_RETIRE));
                    ++retained; ++stored[channel];
                }
            }
            CHECK(trace->count == retained);
            CHECK(trace->helper_calls == ((mask & 1) ? 5 : (mask & 2) ? 4 : 0));
            for (unsigned channel = 0; channel < 2; ++channel) {
                CHECK(trace->eligible[channel] == eligible[channel]);
                CHECK(trace->stored[channel] == stored[channel]);
                CHECK(trace->dropped[channel] == eligible[channel] - stored[channel]);
            }
        }
    }
    context = "valid verbs remain blocked without an enabled v2 runtime";
    ScummState s = {0}, absent = {0}; ScummRuntime r = fresh_runtime();
    r.enabled = 0; fresh_trace(3, 2);
    expect_failure(2, code, sizeof(code), &s, &r, S_BLOCKED, S_OK, S_BLOCK_NONE);
    CHECK(!scumm_step_runtime(2, code, sizeof(code), &absent, trace, NULL));
    CHECK(memcmp(&s, &absent, sizeof(s)) == 0 && trace->count == 0);
    CHECK(scumm_scene_op(S_VERB));
    CHECK(!scumm_scene_op(S_LOAD_ROOM) && !scumm_scene_op(S_WALK));
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
    verb_creation_and_delete();
    verb_slot_and_mode_selection();
    verb_indirection_and_bounds();
    verb_encoded_names();
    transactional_counter_limits();
    verb_modes_and_admission();
    free(trace);
    printf("isolated v2 runtime authored checks passed: %u assertions\n", checks);
    return 0;
}
