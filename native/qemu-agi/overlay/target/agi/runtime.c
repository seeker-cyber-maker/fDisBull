/* SPDX-License-Identifier: GPL-2.0-or-later
 * Context-owned, bounded native AGI semantics. See RUNTIME_PROVENANCE.md.
 * No host decoder, wall clock, global engine, filesystem or implicit input.
 */
#include "runtime.h"
#include "runtime_scene.h"
#include <ctype.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *const status_names[] = {
    "ready", "running", "budget", "return", "pending", "fault", "quit"
};
static const char *const error_names[] = {
    "none", "decode", "missing_resource", "resource_not_loaded",
    "call_stack_limit", "invalid_pc", "invalid_string", "missing_message",
    "invalid_word", "invalid_inventory_object", "division_by_zero",
    "invalid_argument", "actor", "scene", "limit", "invalid_completion",
    "invalid_snapshot", "unimplemented_opcode"
};
static const char *const reply_names[] = {
    "ack", "text", "number", "choice", "menu", "restore"
};
const char *agi_runtime_status_name(uint32_t n)
{ return n < sizeof(status_names) / sizeof(*status_names) ? status_names[n] : "invalid"; }
const char *agi_runtime_error_name(uint32_t n)
{ return n < sizeof(error_names) / sizeof(*error_names) ? error_names[n] : "invalid"; }
const char *agi_runtime_reply_name(uint32_t n)
{ return n < sizeof(reply_names) / sizeof(*reply_names) ? reply_names[n] : "invalid"; }

static void copy_text(char *out, size_t capacity, const char *in)
{
    size_t length = strlen(in);
    if (length >= capacity) length = capacity - 1;
    memcpy(out, in, length);
    out[length] = 0;
}
static uint8_t code_read(void *opaque, uint32_t pc)
{ return ((const AgiRuntimeBlob *)opaque)->data[pc]; }
static int fail(AgiRuntime *r, uint32_t error, uint32_t detail)
{
    r->state.fault = error;
    r->state.fault_detail = detail;
    r->state.fault_logic = r->state.logic;
    r->state.fault_pc = r->state.pc;
    r->state.status = AGI_RT_FAULT;
    return -1;
}
static bool logic_exists(const AgiRuntime *r, uint32_t logic)
{
    return logic < 256 && r->resources->logics[logic].code.data &&
           r->resources->logics[logic].code.size > 0 &&
           r->resources->logics[logic].code.size <= AGI_CODE_MAX;
}
static uint32_t random_value(void *opaque, uint32_t *state, uint32_t upper)
{
    /* A named reproducible runtime RNG, not a claim of DOS RNG bit parity. */
    uint32_t x = *state ? *state : 0x6d2b79f5u;
    (void)opaque;
    x ^= x << 13; x ^= x >> 17; x ^= x << 5;
    *state = x;
    return upper ? x % upper : 0;
}
static int geometry(void *opaque, uint8_t view, uint8_t loop, uint8_t cel,
                    AgiRuntimeGeometry *out)
{
    const AgiRuntime *r = opaque;
    const AgiRuntimeBlob *blob = &r->resources->views[view];
    if (!blob->data || !blob->size) return 0;
    return agi_runtime_view_geometry(blob->data, blob->size, loop, cel, out) == AGI_RS_SUCCESS;
}
static AgiRuntimeActorCallbacks actor_callbacks(const AgiRuntime *r)
{
    AgiRuntimeActorCallbacks cb = {
        .opaque = (void *)r, .geometry = geometry,
        .priority = r->state.picture_priority,
        .priority_size = AGI_RUNTIME_PLANE_BYTES, .random = random_value
    };
    return cb;
}

static int sound_source(void *opaque, uint8_t number, const uint8_t **data, size_t *size)
{
    const AgiRuntime *r = opaque;
    const AgiRuntimeBlob *b = &r->resources->sounds[number];
    if (!b->data || !b->size) return 0;
    *data = b->data; *size = b->size;
    return 1;
}
static void sound_output(void *opaque, const AgiRuntimeSoundOutput *output)
{
    AgiRuntime *r = opaque;
    if (r->sound_output && output->count)
        r->sound_output(r->sound_output_opaque, output->events, output->count);
}
void agi_runtime_set_sound_output(AgiRuntime *r, AgiRuntimeSoundSink sink, void *opaque)
{ r->sound_output = sink; r->sound_output_opaque = opaque; }
static AgiRuntimeSoundCallbacks sound_callbacks(const AgiRuntime *r)
{
    AgiRuntimeSoundCallbacks callbacks = {
        .resource = sound_source, .output = sound_output, .opaque = (void *)r
    };
    return callbacks;
}
static void sync_sound(AgiRuntimeState *s)
{
    s->sound_active = s->sound.active;
    s->sound_id = s->sound.resource;
    s->sound_flag = s->sound.completion_flag;
    s->sound_remaining = s->sound.remaining;
}

void agi_runtime_clear_events(AgiRuntime *r)
{
    r->obs_count = 0;
    memset(r->obs_eligible, 0, sizeof(r->obs_eligible));
    memset(r->obs_dropped, 0, sizeof(r->obs_dropped));
    r->obs_calls = 0;
    r->epoch++;
}
bool agi_runtime_observation(AgiRuntime *r, uint32_t mask, uint32_t capacity)
{
    if (mask > 3 || capacity > r->obs_limit || capacity < r->obs_count) return false;
    r->obs_mask = mask;
    r->obs_capacity = capacity;
    return true;
}
static void append_event(AgiRuntime *r, const AgiDecodedInstruction *insn,
                          uint32_t logic, unsigned channel, uint32_t actor,
                          const AgiRuntimeActor *before, const uint32_t *resolved)
{
    AgiRuntimeEvent *e;
    r->obs_eligible[channel]++;
    if (r->obs_count == r->obs_capacity) {
        r->obs_dropped[channel]++;
        return;
    }
    e = &r->events[r->obs_count++];
    memset(e, 0, sizeof(*e));
    e->seq = r->obs_eligible[0] + r->obs_eligible[1];
    e->retired = r->state.retired;
    e->scene_revision = r->state.scene_revision;
    e->channel = channel;
    e->logic = logic;
    e->pc = insn ? insn->pc : r->state.pc;
    e->opcode = insn ? insn->opcode : 256;
    e->next_logic = r->state.logic;
    e->next_pc = r->state.pc;
    e->size = insn ? insn->size : 0;
    if (insn) memcpy(e->bytes, insn->bytes, insn->size);
    if (resolved) memcpy(e->resolved, resolved, sizeof(e->resolved));
    e->actor = actor;
    if (before && actor < 256) {
        e->kind = 1;
        e->before_actor = *before;
        e->after_actor = r->state.world.actors[actor];
    }
}
static void observe(AgiRuntime *r, const AgiDecodedInstruction *insn,
                     uint32_t logic, uint32_t actor,
                     const AgiRuntimeActor *before, const uint32_t *resolved,
                     uint64_t prior_scene)
{
    if (!r->obs_mask) return;
    r->obs_calls++;
    if (r->obs_mask & 1) append_event(r, insn, logic, 0, actor, NULL, resolved);
    if ((r->obs_mask & 2) && prior_scene != r->state.scene_revision) {
        append_event(r, insn, logic, 1, actor, before, resolved);
    }
}

void agi_runtime_restart(AgiRuntime *r)
{
    AgiRuntimeState *s = &r->state;
    uint64_t next = s->next_effect_id;
    if (s->sound.active) {
        AgiRuntimeSoundCallbacks callbacks = sound_callbacks(r);
        agi_runtime_sound_stop(&s->sound, s->f, &callbacks);
    }
    memset(s, 0, sizeof(*s));
    agi_runtime_world_init(&s->world);
    agi_runtime_sound_init(&s->sound);
    sync_sound(s);
    s->world.rng_state = 0x6d2b79f5u;
    s->logic = r->resources->entry_logic;
    s->loaded_logics[s->logic] = 1;
    s->status = AGI_RT_READY;
    s->next_effect_id = next ? next : 1;
    s->v[10] = 2;
    s->f[5] = s->f[9] = 1;
    memcpy(s->inventory, r->resources->object_rooms, sizeof(s->inventory));
    s->graphics = s->input_enabled = 1;
    s->foreground = 15;
    s->cursor = '_';
    s->input_line = 22;
    s->script_capacity = 256;
    memset(s->text, ' ', sizeof(s->text));
    memset(s->text_fg, 15, sizeof(s->text_fg));
    memset(s->picture_visual, 15, sizeof(s->picture_visual));
    memset(s->picture_priority, 4, sizeof(s->picture_priority));
    r->run_retired = 0;
    agi_runtime_clear_events(r);
}
bool agi_runtime_init(AgiRuntime *r, const AgiRuntimeResources *resources,
                      AgiRuntimeEvent *events, uint32_t capacity)
{
    if (!r || !resources || resources->entry_logic > 255 ||
        resources->object_count > 256 || capacity > AGI_RT_EVENTS_MAX ||
        (capacity && !events)) return false;
    memset(r, 0, sizeof(*r));
    r->resources = resources;
    if (!logic_exists(r, resources->entry_logic)) return false;
    r->events = events;
    r->obs_limit = r->obs_capacity = capacity;
    agi_runtime_restart(r);
    return true;
}

static const char *message(const AgiRuntime *r, uint32_t logic, uint32_t id)
{
    const AgiRuntimeLogic *l;
    if (logic >= 256 || id == 0 || id > 255) return NULL;
    l = &r->resources->logics[logic];
    return id <= l->message_count ? l->messages[id] : NULL;
}
static bool format_text(const AgiRuntime *r, uint32_t logic, const char *source,
                        char *out, size_t capacity, unsigned depth)
{
    size_t at = 0;
    if (!source || depth > 8) return false;
    while (*source) {
        char expansion[AGI_RT_TEXT_BYTES];
        const char *part = expansion;
        uint32_t n = 0, width = 0;
        bool fixed_width = false;
        char type;
        size_t length;
        expansion[0] = 0;
        if (*source == '\\' && source[1]) {
            if (at + 1 >= capacity) return false;
            source++;
            out[at++] = *source++;
            continue;
        }
        if (*source != '%') {
            if (at + 1 >= capacity) return false;
            out[at++] = *source++;
            continue;
        }
        source++;
        type = *source++;
        if (!type) return false;
        if (type == '%') { expansion[0] = '%'; expansion[1] = 0; }
        else {
            if (!isdigit((unsigned char)*source)) return false;
            while (isdigit((unsigned char)*source)) {
                n = n * 10 + (*source++ - '0');
                if (n > 255) return false;
            }
            if (type == 'v' && *source == '|') {
                fixed_width = true;
                source++;
                while (isdigit((unsigned char)*source)) {
                    width = width * 10 + (*source++ - '0');
                    if (width > 255) return false;
                }
            }
            switch (type) {
            case 'v':
                snprintf(expansion, sizeof(expansion), "%0*u", (int)width, r->state.v[n]);
                length = strlen(expansion);
                if (fixed_width && length > width) memmove(expansion, expansion + length - width, width + 1);
                break;
            case 's': if (n >= AGI_RT_STRINGS) return false; part = r->state.strings[n]; break;
            case 'w': if (!n || n > r->state.parsed_count) return false; part = r->state.parsed_words[n - 1]; break;
            case '0':
                if (!n || n > r->resources->object_count) return false;
                part = r->resources->object_names[n - 1]; break;
            case 'o': if (n >= r->resources->object_count) return false; part = r->resources->object_names[n]; break;
            case 'm': case 'g':
                if (!format_text(r, type == 'g' ? 0 : logic,
                                 message(r, type == 'g' ? 0 : logic, n),
                                 expansion, sizeof(expansion), depth + 1)) return false;
                break;
            default: return false;
            }
        }
        if (!part) return false;
        length = strlen(part);
        if (length >= capacity - at) return false;
        memcpy(out + at, part, length);
        at += length;
    }
    out[at] = 0;
    return true;
}
static bool formatted_message(const AgiRuntime *r, uint32_t id, char *out)
{ return format_text(r, r->state.logic, message(r, r->state.logic, id), out, AGI_RT_TEXT_BYTES, 0); }
static void put_text(AgiRuntimeState *s, unsigned row, unsigned col,
                      const char *text, unsigned width)
{
    unsigned start = col, limit = width ? col + width : 40;
    if (limit > 40) limit = 40;
    while (*text && row < 25 && col < 40) {
        if (*text == '\n') { row++; col = start; text++; continue; }
        s->text[row][col] = (uint8_t)*text++;
        s->text_fg[row][col] = s->foreground & 15;
        s->text_bg[row][col] = s->background & 15;
        if (++col >= limit) { col = start; row++; }
    }
}
static void clear_rect(AgiRuntimeState *s, unsigned y1, unsigned x1,
                       unsigned y2, unsigned x2, unsigned color)
{
    unsigned x, y;
    if (y2 > 24) y2 = 24;
    if (x2 > 39) x2 = 39;
    for (y = y1; y <= y2; y++) for (x = x1; x <= x2; x++) {
        s->text[y][x] = ' ';
        s->text_fg[y][x] = s->foreground & 15;
        s->text_bg[y][x] = color & 15;
    }
}
static bool parse_input(AgiRuntime *r, const char *text)
{
    AgiRuntimeState *s = &r->state;
    char clean[AGI_RT_TEXT_BYTES];
    size_t i, at = 0, best, length;
    uint32_t k, id;
    bool space = true;
    if (strlen(text) >= sizeof(clean)) return false;
    for (i = 0; text[i]; i++) {
        unsigned char c = (unsigned char)text[i];
        if (c == '\'' || c == '`' || c == '"' || c == '-') continue;
        if (isspace(c) || strchr(".,!?;:()", c)) {
            if (!space) clean[at++] = ' ';
            space = true;
        } else {
            if (c < 32 || c > 126) return false;
            clean[at++] = (char)tolower(c);
            space = false;
        }
    }
    if (at && clean[at - 1] == ' ') at--;
    clean[at] = 0;
    s->parsed_count = 0;
    memset(s->word_ids, 0, sizeof(s->word_ids));
    memset(s->parsed_words, 0, sizeof(s->parsed_words));
    s->v[9] = s->f[2] = s->f[4] = 0;
    for (i = 0; clean[i]; ) {
        best = 0; id = 19999;
        for (k = 0; k < r->resources->word_count; k++) {
            const AgiRuntimeWord *w = &r->resources->words[k];
            length = strlen(w->text);
            if (length > best && strncmp(clean + i, w->text, length) == 0 &&
                (clean[i + length] == 0 || clean[i + length] == ' ')) {
                best = length; id = w->id;
            }
        }
        if (!best) {
            while (clean[i + best] && clean[i + best] != ' ') best++;
        }
        if (id) {
            if (s->parsed_count == AGI_RT_WORDS) return false;
            k = s->parsed_count++;
            s->word_ids[k] = id;
            length = best < AGI_RT_STRING_BYTES ? best : AGI_RT_STRING_BYTES - 1;
            memcpy(s->parsed_words[k], clean + i, length);
            s->parsed_words[k][length] = 0;
            if (id == 19999) { s->v[9] = k + 1; break; }
        }
        i += best;
        if (clean[i] == ' ') i++;
    }
    s->f[2] = s->parsed_count != 0;
    return true;
}
static unsigned normalized_char(const char **s)
{
    while (**s && strchr(" \t-.,:;!'", **s)) (*s)++;
    return (unsigned)toupper((unsigned char)*(*s)++);
}
static bool strings_equal(const char *a, const char *b)
{
    unsigned x, y;
    do { x = normalized_char(&a); y = normalized_char(&b); } while (x && x == y);
    return x == y;
}
static int predicate(AgiRuntime *r, const AgiDecodedCondition *test,
                      const AgiDecodedOperand *args)
{
    AgiRuntimeState *s = &r->state;
    uint32_t a = test->operand_count ? args[0].value : 0;
    uint32_t b = test->operand_count > 1 ? args[1].value : 0;
    int64_t left, right, y;
    uint32_t k;
    switch (test->opcode) {
    case 0: return 0;
    case 1: return s->v[a] == b;
    case 2: return s->v[a] == s->v[b];
    case 3: return s->v[a] < b;
    case 4: return s->v[a] < s->v[b];
    case 5: return s->v[a] > b;
    case 6: return s->v[a] > s->v[b];
    case 7: return s->f[a] != 0;
    case 8: return s->f[s->v[a]] != 0;
    case 9: case 10:
        if (a >= r->resources->object_count) return -AGI_RT_INVENTORY;
        return s->inventory[a] == (test->opcode == 9 ? 255 : s->v[b]);
    case 12: return s->controllers[a] != 0;
    case 13: k = s->keypress; s->keypress = 0; return k != 0;
    case 14:
        if (!s->f[2] || s->f[4]) return 0;
        for (k = 0; k < a; k++) {
            uint32_t word = args[k + 1].value;
            if (word == 9999) { s->f[4] = 1; return 1; }
            if (k >= s->parsed_count || (word != 1 && word != s->word_ids[k])) return 0;
        }
        if (k != s->parsed_count) return 0;
        s->f[4] = 1;
        return 1;
    case 15:
        if (a >= AGI_RT_STRINGS || b >= AGI_RT_STRINGS) return -AGI_RT_STRING;
        return strings_equal(s->strings[a], s->strings[b]);
    case 11: case 16: case 17: case 18:
        left = s->world.actors[a].x;
        right = left;
        y = s->world.actors[a].y;
        if (test->opcode == 16) right += (int64_t)s->world.actors[a].width - 1;
        if (test->opcode == 17) left = right = left + s->world.actors[a].width / 2;
        if (test->opcode == 18) left = right = left + (int64_t)s->world.actors[a].width - 1;
        return left >= b && y >= args[2].value && right <= args[3].value && y <= args[4].value;
    default: return -AGI_RT_UNIMPLEMENTED;
    }
}
static int evaluate_if(AgiRuntime *r, const AgiDecodedInstruction *insn)
{
    bool in_or = false, group = false, negate = false;
    uint32_t i;
    int value;
    /* Canonical framing already checked the full expression. Skipped tests
     * must not consume keys or accept parser input. */
    for (i = 0; i < insn->condition_count; i++) {
        const AgiDecodedCondition *t = &insn->conditions[i];
        if (t->kind == AGI_CONDITION_NOT) { negate = true; continue; }
        if (t->kind == AGI_CONDITION_OR_BEGIN) { in_or = true; group = false; continue; }
        if (t->kind == AGI_CONDITION_OR_END) {
            in_or = false;
            if (!group) return 0;
            continue;
        }
        if (in_or && group) { negate = false; continue; }
        value = predicate(r, t, &insn->condition_operands[t->operand_start]);
        if (value < 0) return value;
        if (negate) value = !value;
        negate = false;
        if (in_or) group = value != 0;
        else if (!value) return 0;
    }
    return 1;
}

static bool request(AgiRuntime *r, const AgiDecodedInstruction *insn,
                     uint32_t reply, const char *text)
{
    AgiRuntimePending *p = &r->state.pending;
    if (r->state.next_effect_id == UINT64_MAX) return false;
    memset(p, 0, sizeof(*p));
    p->id = r->state.next_effect_id++;
    p->opcode = insn->opcode;
    p->logic = r->state.logic;
    p->pc = insn->pc;
    p->next_pc = insn->pc + insn->size;
    p->reply = reply;
    p->argc = insn->size - 1;
    memcpy(p->args, insn->bytes + 1, p->argc);
    if (text) copy_text(p->text, sizeof(p->text), text);
    r->state.status = AGI_RT_PENDING;
    return true;
}
static void stop_sound(AgiRuntime *r)
{
    AgiRuntimeSoundCallbacks callbacks = sound_callbacks(r);
    agi_runtime_sound_stop(&r->state.sound, r->state.f, &callbacks);
    sync_sound(&r->state);
}
static bool script_room(const AgiRuntimeState *s, uint32_t pairs)
{ return s->f[7] || pairs <= s->script_capacity - s->script_count; }
static void script_record(AgiRuntimeState *s, uint32_t opcode, const uint8_t *args, size_t count)
{
    AgiRuntimeScriptEntry *e;
    uint32_t kind;
    (void)count;
    if (s->f[7]) return;
    switch (opcode) {
    case 20: kind = 0; break; case 30: kind = 1; break;
    case 24: kind = 2; break; case 98: kind = 3; break;
    case 25: kind = 4; break; case 122: kind = 5; break;
    case 27: kind = 6; break; case 32: kind = 7; break;
    case 28: kind = 8; break; default: return;
    }
    e = &s->script[s->script_count++];
    memset(e, 0, sizeof(*e));
    e->opcode = kind;
    e->args[0] = kind == 5 ? 0 : args[0];
    if (kind == 5) {
        e = &s->script[s->script_count++]; memset(e, 0, sizeof(*e));
        e->opcode = args[0]; e->args[0] = args[1];
        e = &s->script[s->script_count++]; memset(e, 0, sizeof(*e));
        e->opcode = args[2]; e->args[0] = args[3];
        e = &s->script[s->script_count++]; memset(e, 0, sizeof(*e));
        e->opcode = args[4]; e->args[0] = ((args[5] & 15) << 4) | (args[6] & 15);
    }
}
static bool family_load(uint8_t loaded[256], uint8_t order[256], uint32_t *count, uint8_t id)
{
    if (loaded[id]) return true;
    if (*count >= 256) return false;
    loaded[id] = 1;
    order[(*count)++] = id;
    return true;
}
static bool family_discard(uint8_t loaded[256], uint8_t order[256], uint32_t *count, uint8_t id)
{
    uint32_t at, i;
    if (!loaded[id]) return false;
    for (at = 0; at < *count && order[at] != id; at++);
    if (at == *count) return false;
    for (i = at; i < *count; i++) { loaded[order[i]] = 0; order[i] = 0; }
    *count = at;
    return true;
}
static bool room_change(AgiRuntime *r, uint32_t room)
{
    AgiRuntimeState *s = &r->state;
    AgiRuntimeActor *ego = &s->world.actors[0];
    uint32_t i;
    if (!logic_exists(r, 0) || !logic_exists(r, room)) return false;
    stop_sound(r);
    for (i = 0; i < AGI_RUNTIME_ACTORS; i++) {
        AgiRuntimeActor *a = &s->world.actors[i];
        a->flags &= ~(AGI_RA_ANIMATED | AGI_RA_DRAWN);
        a->flags |= AGI_RA_UPDATE;
        a->step_size = a->step_time = a->step_time_count = 1;
        a->cycle_time = a->cycle_time_count = 1;
    }
    memset(s->loaded_logics, 0, sizeof(s->loaded_logics));
    memset(s->loaded_pictures, 0, sizeof(s->loaded_pictures));
    memset(s->loaded_sounds, 0, sizeof(s->loaded_sounds));
    memset(s->world.loaded_views, 0, sizeof(s->world.loaded_views));
    memset(s->view_order, 0, sizeof(s->view_order));
    memset(s->picture_order, 0, sizeof(s->picture_order));
    s->view_order_count = s->picture_order_count = 0;
    memset(s->scan_start + 1, 0, sizeof(s->scan_start) - sizeof(s->scan_start[0]));
    s->loaded_logics[0] = s->loaded_logics[room] = 1;
    s->world.player_control = 1;
    s->world.block_active = 0;
    s->world.horizon = 36;
    s->v[1] = s->v[0]; s->v[0] = room;
    s->v[4] = s->v[5] = 0; s->v[16] = ego->view;
    switch (s->v[2]) {
    case 1: ego->y = 167; break;
    case 2: ego->x = 0; break;
    case 3: ego->y = 37; break;
    case 4: ego->x = 160 - (int32_t)ego->width; break;
    }
    s->v[2] = 0;
    s->v[9] = s->f[2] = s->f[4] = 0;
    s->parsed_count = 0;
    memset(s->word_ids, 0, sizeof(s->word_ids));
    memset(s->parsed_words, 0, sizeof(s->parsed_words));
    s->f[5] = 1;
    s->stack_depth = 0;
    s->logic = 0; s->pc = s->scan_start[0];
    s->script_count = s->script_saved = 0;
    s->scene_revision++;
    return true;
}

/* Returns 1 for retirement, 0 for a resumable effect, -1 for a fault. */
int agi_runtime_step(AgiRuntime *r)
{
    AgiRuntimeState *s = &r->state;
    AgiDecodedInstruction insn;
    AgiRuntimeActor before_actor;
    AgiRuntimeActorCallbacks cb;
    const AgiRuntimeBlob *code;
    const uint8_t *p;
    uint32_t a, b, c, op, next, logic, value = 0, i, n, resolved[7] = {0};
    uint32_t actor = 256;
    uint64_t prior_scene = s->scene_revision;
    char text[AGI_RT_TEXT_BYTES];
    const char *literal;
    int result;
    bool changed_pc = false;
    if (s->status == AGI_RT_PENDING || s->status == AGI_RT_RETURN ||
        s->status == AGI_RT_QUIT) return 0;
    if (s->status == AGI_RT_FAULT) return -1;
    if (!logic_exists(r, s->logic)) return fail(r, AGI_RT_RESOURCE, s->logic);
    code = &r->resources->logics[s->logic].code;
    if (!agi_decode(code_read, (void *)code, code->size, s->pc,
                    AGI_DECODE_RUNTIME, AGI_DECODE_STRUCTURAL, &insn)) {
        return fail(r, AGI_RT_DECODE, insn.fault);
    }
    p = insn.bytes + 1;
    op = insn.opcode;
    a = insn.size > 1 ? p[0] : 0;
    b = insn.size > 2 ? p[1] : 0;
    c = insn.size > 3 ? p[2] : 0;
    next = s->pc + insn.size;
    logic = s->logic;
    for (i = 0; i < insn.operand_count && i < 7; i++) {
        const AgiDecodedOperand *o = &insn.operands[i];
        resolved[i] = o->kind == AGI_OPERAND_VARIABLE && o->access == AGI_ACCESS_READ ?
                      s->v[o->value] : (uint32_t)o->value;
    }
    s->status = AGI_RT_RUNNING;
    if ((op >= 33 && op <= 91) || op == 147 || op == 148) {
        actor = a;
        before_actor = s->world.actors[a];
        cb = actor_callbacks(r);
        result = agi_runtime_actor_command(&s->world, op, p, insn.size - 1, s->v, s->f, &cb);
        if (result < 0) return fail(r, AGI_RT_ACTOR, (uint32_t)-result);
        if (result != AGI_RA_HANDLED) return fail(r, AGI_RT_UNIMPLEMENTED, op);
        if (op == 34 || op == 60 || op == 63 || op == 90 || op == 91 ||
            memcmp(&before_actor, &s->world.actors[a], sizeof(before_actor))) s->scene_revision++;
        goto retire;
    }
    switch (op) {
    case 0:
        if (s->stack_depth) {
            AgiRuntimeFrame f = s->stack[--s->stack_depth];
            memset(&s->stack[s->stack_depth], 0, sizeof(s->stack[0]));
            s->logic = f.logic; s->pc = f.pc;
            changed_pc = true;
        } else {
            if (s->cycle_active) {
                if (s->graphics) {
                    cb = actor_callbacks(r);
                    result = agi_runtime_actor_finish(&s->world, s->v, s->f, &cb);
                    if (result < 0) return fail(r, AGI_RT_ACTOR, -result);
                }
                s->cycle_active = 0; s->cycle_count++;
                memset(s->controllers, 0, sizeof(s->controllers));
                s->v[4] = s->v[5] = s->f[5] = s->f[6] = s->f[12] = 0;
                s->f[2] = s->f[4] = 0;
                s->scene_revision++;
            }
            s->status = AGI_RT_RETURN;
        }
        break;
    case 1: if (s->v[a] != 255) s->v[a]++; break;
    case 2: if (s->v[a]) s->v[a]--; break;
    case 3: s->v[a] = b; break;
    case 4: s->v[a] = s->v[b]; break;
    case 5: s->v[a] += b; break;
    case 6: s->v[a] += s->v[b]; break;
    case 7: s->v[a] -= b; break;
    case 8: s->v[a] -= s->v[b]; break;
    case 9: s->v[s->v[a]] = s->v[b]; break;
    case 10: s->v[a] = s->v[s->v[b]]; break;
    case 11: s->v[s->v[a]] = b; break;
    case 12: s->f[a] = 1; break;
    case 13: s->f[a] = 0; break;
    case 14: s->f[a] ^= 1; break;
    case 15: s->f[s->v[a]] = 1; break;
    case 16: s->f[s->v[a]] = 0; break;
    case 17: s->f[s->v[a]] ^= 1; break;
    case 18: case 19:
        value = op == 18 ? a : s->v[a];
        if (!room_change(r, value)) return fail(r, AGI_RT_RESOURCE, value);
        changed_pc = true;
        break;
    case 20: case 21: case 22: case 23:
        value = (op & 1) ? s->v[a] : a;
        if (!logic_exists(r, value)) return fail(r, AGI_RT_RESOURCE, value);
        if (!s->loaded_logics[value] && !script_room(s, 1)) return fail(r, AGI_RT_LIMIT, AGI_RT_SCRIPT);
        if (op >= 22) {
            if (s->stack_depth == AGI_RT_STACK) return fail(r, AGI_RT_CALL_OVERFLOW, value);
            if (s->scan_start[value] >= r->resources->logics[value].code.size) return fail(r, AGI_RT_BAD_PC, value);
            s->stack[s->stack_depth++] = (AgiRuntimeFrame){logic, next};
            s->logic = value; s->pc = s->scan_start[value]; changed_pc = true;
        }
        if (!s->loaded_logics[value]) {
            uint8_t arg = value;
            s->loaded_logics[value] = 1;
            script_record(s, 20, &arg, 1);
        }
        break;
    case 24: case 25: case 27: case 28:
        value = s->v[a];
        if (op == 27) {
            uint8_t arg = value;
            if (!s->loaded_pictures[value]) break;
            if (!script_room(s, 1)) return fail(r, AGI_RT_LIMIT, AGI_RT_SCRIPT);
            if (!family_discard(s->loaded_pictures, s->picture_order, &s->picture_order_count, value))
                return fail(r, AGI_RT_ARGUMENT, value);
            script_record(s, 27, &arg, 1);
            break;
        }
        if (!r->resources->pictures[value].data) return fail(r, AGI_RT_RESOURCE, value);
        if (op == 24) {
            uint8_t arg = value;
            if (s->loaded_pictures[value]) break;
            if (!script_room(s, 1)) return fail(r, AGI_RT_LIMIT, AGI_RT_SCRIPT);
            if (!family_load(s->loaded_pictures, s->picture_order, &s->picture_order_count, value))
                return fail(r, AGI_RT_LIMIT, 256);
            script_record(s, 24, &arg, 1);
            break;
        }
        if (!s->loaded_pictures[value]) return fail(r, AGI_RT_RESOURCE_NOT_LOADED, value);
        if (!script_room(s, 1)) return fail(r, AGI_RT_LIMIT, AGI_RT_SCRIPT);
        result = agi_runtime_decode_picture(r->resources->pictures[value].data,
                   r->resources->pictures[value].size, op == 25,
                   s->picture_visual, s->picture_priority, AGI_RUNTIME_PLANE_BYTES, NULL);
        if (result < 0) return fail(r, AGI_RT_SCENE, -result);
        s->picture_id = value; s->picture_shown = 0;
        { uint8_t arg = value; script_record(s, op, &arg, 1); }
        s->scene_revision++;
        break;
    case 26:
        s->picture_shown = 1; s->f[15] = 0; s->window_open = 0;
        s->presentation_revision++; s->scene_revision++; break;
    case 30: case 31: case 32: case 153:
        value = (op == 31 || op == 153) ? s->v[a] : a;
        if (op == 32 || op == 153) {
            uint8_t arg = value;
            if (!s->world.loaded_views[value]) break;
            if (!script_room(s, 1)) return fail(r, AGI_RT_LIMIT, AGI_RT_SCRIPT);
            if (!family_discard(s->world.loaded_views, s->view_order, &s->view_order_count, value))
                return fail(r, AGI_RT_ARGUMENT, value);
            script_record(s, 32, &arg, 1);
            break;
        }
        if (!r->resources->views[value].data) return fail(r, AGI_RT_RESOURCE, value);
        if (!s->world.loaded_views[value]) {
            uint8_t arg = value;
            if (!script_room(s, 1)) return fail(r, AGI_RT_LIMIT, AGI_RT_SCRIPT);
            if (!family_load(s->world.loaded_views, s->view_order, &s->view_order_count, value))
                return fail(r, AGI_RT_LIMIT, 256);
            script_record(s, 30, &arg, 1);
        }
        break;
    case 92: case 93: case 94: case 95: case 96: case 97:
        value = (op == 93 || op == 96 || op == 97) ? s->v[a] : a;
        if (value >= r->resources->object_count) return fail(r, AGI_RT_INVENTORY, value);
        if (op == 97) s->v[b] = s->inventory[value];
        else s->inventory[value] = op <= 93 ? 255 : op == 94 ? 0 : s->v[b];
        break;
    case 98:
        if (!r->resources->sounds[a].data) return fail(r, AGI_RT_RESOURCE, a);
        if (agi_runtime_sound_validate(r->resources->sounds[a].data, r->resources->sounds[a].size, NULL) < 0)
            return fail(r, AGI_RT_RESOURCE, a);
        if (!s->loaded_sounds[a]) {
            uint8_t arg = a;
            if (!script_room(s, 1)) return fail(r, AGI_RT_LIMIT, AGI_RT_SCRIPT);
            s->loaded_sounds[a] = 1;
            script_record(s, 98, &arg, 1);
        }
        break;
    case 99:
        if (!s->loaded_sounds[a]) return fail(r, AGI_RT_RESOURCE_NOT_LOADED, a);
        { AgiRuntimeSoundCallbacks callbacks = sound_callbacks(r);
          if (agi_runtime_sound_start(&s->sound, a, b, s->v[22], s->f, &callbacks) < 0)
              return fail(r, AGI_RT_RESOURCE, a);
          sync_sound(s); }
        s->scene_revision++; break;
    case 100: stop_sound(r); s->scene_revision++; break;
    case 101: case 102: case 151: case 152:
        value = (op == 102 || op == 152) ? s->v[a] : a;
        if (!formatted_message(r, value ? value : 1, text)) return fail(r, AGI_RT_MESSAGE, value);
        if (s->f[15]) {
            put_text(s, op >= 151 ? b : 10, op >= 151 ? c : 1, text, op >= 151 ? p[3] : 38);
            s->window_open = 1; s->f[15] = 0; s->scene_revision++;
            break;
        }
        if (!request(r, &insn, AGI_RT_REPLY_ACK, text)) return fail(r, AGI_RT_LIMIT, 0);
        return 0;
    case 103: case 104:
        value = op == 104 ? s->v[c] : c;
        if (!formatted_message(r, value, text)) return fail(r, AGI_RT_MESSAGE, value);
        put_text(s, op == 104 ? s->v[a] : a, op == 104 ? s->v[b] : b, text, 0);
        s->scene_revision++; break;
    case 105: clear_rect(s, a, 0, b ? b : a, 39, c); s->scene_revision++; break;
    case 106:
        s->graphics = 0;
        if (s->background) s->background |= 8;
        clear_rect(s, 0, 0, 24, 39, s->background); s->scene_revision++; break;
    case 107: s->graphics = 1; s->scene_revision++; break;
    case 108:
        literal = message(r, logic, a);
        if (!literal) return fail(r, AGI_RT_MESSAGE, a);
        s->cursor = (uint8_t)*literal; break;
    case 109:
        s->foreground = a & 15; s->background = b & 15;
        if (s->graphics && b) { s->foreground = 0; s->background = 15; }
        s->scene_revision++; break;
    case 111: s->min_print_line = a; s->input_line = b; s->status_line_row = c; s->scene_revision++; break;
    case 112: case 113: s->status_line = op == 112; s->scene_revision++; break;
    case 114:
        if (a >= AGI_RT_STRINGS) return fail(r, AGI_RT_STRING, a);
        literal = message(r, logic, b);
        if (!literal) return fail(r, AGI_RT_MESSAGE, b);
        copy_text(s->strings[a], AGI_RT_STRING_BYTES, literal); break;
    case 115:
        if (a >= AGI_RT_STRINGS) return fail(r, AGI_RT_STRING, a);
        if (!formatted_message(r, b, text)) return fail(r, AGI_RT_MESSAGE, b);
        if (!request(r, &insn, AGI_RT_REPLY_TEXT, text)) return fail(r, AGI_RT_LIMIT, 0);
        return 0;
    case 116:
        if (a >= AGI_RT_STRINGS) return fail(r, AGI_RT_STRING, a);
        if (b >= s->parsed_count) return fail(r, AGI_RT_WORD, b);
        copy_text(s->strings[a], AGI_RT_STRING_BYTES, s->parsed_words[b]); break;
    case 117:
        if (a >= AGI_RT_STRINGS) return fail(r, AGI_RT_STRING, a);
        if (!format_text(r, logic, s->strings[a], text, sizeof(text), 0)) return fail(r, AGI_RT_STRING, a);
        { AgiRuntimeState saved = *s;
          if (!parse_input(r, text)) { *s = saved; return fail(r, AGI_RT_WORD, 0); } }
        break;
    case 118:
        if (!formatted_message(r, a, text)) return fail(r, AGI_RT_MESSAGE, a);
        if (!request(r, &insn, AGI_RT_REPLY_NUMBER, text)) return fail(r, AGI_RT_LIMIT, 0);
        return 0;
    case 119: case 120: s->input_enabled = op == 120; break;
    case 121:
        value = a | b << 8;
        for (i = 0; i < s->key_count; i++) if (s->keys[i] == value && s->key_controllers[i] == c) break;
        if (i == s->key_count) {
            if (s->key_count == 256) return fail(r, AGI_RT_LIMIT, 256);
            s->keys[i] = value; s->key_controllers[i] = c; s->key_count++;
            s->controllers[c] = 0;
        }
        break;
    case 122: case 123:
        /* The scene adapter consumes resolved bytes, not a second decoder. */
        { uint8_t args[7];
          for (i = 0; i < 7; i++) args[i] = op == 123 ? s->v[p[i]] : p[i];
          if (!r->resources->views[args[0]].data) return fail(r, AGI_RT_RESOURCE, args[0]);
          if (!script_room(s, 4)) return fail(r, AGI_RT_LIMIT, AGI_RT_SCRIPT);
          uint8_t pixels[AGI_RUNTIME_PLANE_BYTES];
          AgiRuntimeViewCel cel;
          result = agi_runtime_view_cel(r->resources->views[args[0]].data,
                     r->resources->views[args[0]].size, args[1], args[2],
                     pixels, sizeof(pixels), &cel);
          if (result < 0) return fail(r, AGI_RT_SCENE, -result);
          result = agi_runtime_add_to_picture(s->picture_visual, s->picture_priority,
                     AGI_RUNTIME_PLANE_BYTES, pixels, cel.geometry.width * cel.geometry.height,
                     cel.geometry.width, cel.geometry.height, cel.transparent,
                     args[3], args[4], args[5], args[6],
                     s->world.priority_bands, AGI_RUNTIME_HEIGHT, NULL);
          if (result < 0) return fail(r, AGI_RT_SCENE, -result);
          script_record(s, 122, args, 7); s->scene_revision++; }
        break;
    case 130:
        if (a > b) return fail(r, AGI_RT_ARGUMENT, op);
        s->v[c] = a + random_value(NULL, &s->world.rng_state, b - a + 1); break;
    case 131: s->world.player_control = 0; break;
    case 132: s->world.player_control = 1; s->world.actors[0].motion = AGI_RM_NORMAL; break;
    case 137: copy_text(s->input, sizeof(s->input), s->echo); s->scene_revision++; break;
    case 138: s->input[0] = 0; s->scene_revision++; break;
    case 140: s->monitor ^= 1; s->scene_revision++; break;
    case 142:
        n = a ? a : 256;
        s->script_capacity = n; s->script_count = s->script_saved = 0;
        memset(s->script, 0, sizeof(s->script)); break;
    case 143:
        literal = message(r, logic, a);
        if (!literal) return fail(r, AGI_RT_MESSAGE, a);
        copy_text(s->game_id, sizeof(s->game_id), literal); break;
    case 145: s->scan_start[logic] = next; break;
    case 146: s->scan_start[logic] = 0; break;
    case 149: s->trace_enabled = 1; break;
    case 150: s->trace_logic = a; s->trace_top = b; s->trace_height = c; break;
    case 154: clear_rect(s, a, b, c, p[3], p[4] ? 15 : 0); s->scene_revision++; break;
    case 155: /* Documented AGI 2.917 no-op; operands still decoded. */ break;
    case 156:
        if (s->menu_submitted) break;
        if (s->menu_count == AGI_RT_MENUS) return fail(r, AGI_RT_LIMIT, op);
        if (!formatted_message(r, a, text)) return fail(r, AGI_RT_MESSAGE, a);
        copy_text(s->menus[s->menu_count].text, AGI_RT_STRING_BYTES, text);
        s->menus[s->menu_count++].first_item = s->menu_item_count;
        s->scene_revision++; break;
    case 157:
        if (s->menu_submitted) break;
        if (!s->menu_count || s->menu_item_count == AGI_RT_MENU_ITEMS) return fail(r, AGI_RT_LIMIT, op);
        if (!formatted_message(r, a, text)) return fail(r, AGI_RT_MESSAGE, a);
        copy_text(s->menu_items[s->menu_item_count].text, AGI_RT_STRING_BYTES, text);
        s->menu_items[s->menu_item_count].controller = b;
        s->menu_items[s->menu_item_count++].enabled = 1;
        s->menus[s->menu_count - 1].item_count++; s->scene_revision++; break;
    case 158: s->menu_submitted = 1; s->scene_revision++; break;
    case 159: case 160:
        for (i = 0; i < s->menu_item_count; i++) if (s->menu_items[i].controller == a) s->menu_items[i].enabled = op == 159;
        s->scene_revision++; break;
    case 163: case 164: s->dialogue = op == 163; s->window_open = op == 163; s->scene_revision++; break;
    case 165: s->v[a] *= b; break;
    case 166: s->v[a] *= s->v[b]; break;
    case 167: case 168:
        value = op == 167 ? b : s->v[b];
        if (!value) return fail(r, AGI_RT_DIV_ZERO, op);
        s->v[a] /= value; break;
    case 169: s->window_open = 0; s->scene_revision++; break;
    case 170: s->simple_save = 1; break;
    case 171: s->script_saved = s->script_count; break;
    case 172:
        if (s->script_saved > s->script_count) return fail(r, AGI_RT_ARGUMENT, op);
        memset(s->script + s->script_saved, 0, (s->script_count - s->script_saved) * sizeof(*s->script));
        s->script_count = s->script_saved; break;
    case 173: s->hold_key = 1; break;
    case 254:
        if (!insn.successors[0].in_range) return fail(r, AGI_RT_BAD_PC, (uint32_t)insn.successors[0].pc);
        s->pc = insn.successors[0].pc; changed_pc = true; break;
    case 255:
        { uint8_t saved_flags[256]; uint32_t saved_key = s->keypress;
          memcpy(saved_flags, s->f, sizeof(saved_flags));
          result = evaluate_if(r, &insn);
          if (result < 0) { memcpy(s->f, saved_flags, sizeof(saved_flags)); s->keypress = saved_key; return fail(r, -result, op); }
          value = result ? 0 : 1;
          if (!insn.successors[value].in_range) { memcpy(s->f, saved_flags, sizeof(saved_flags)); s->keypress = saved_key; return fail(r, AGI_RT_BAD_PC, (uint32_t)insn.successors[value].pc); }
          s->pc = insn.successors[value].pc; changed_pc = true; }
        break;
    case 127: /* init.disk is a 2.917 compatibility no-op. */ break;
    case 29: case 110: case 124: case 125: case 126: case 128:
    case 129: case 133: case 134: case 135: case 136: case 139: case 141:
    case 144: case 161: case 162:
        text[0] = 0;
        value = AGI_RT_REPLY_ACK;
        if (op == 126) value = AGI_RT_REPLY_RESTORE;
        if (op == 124 && s->f[13]) value = AGI_RT_REPLY_NUMBER;
        if (op == 128 || op == 134) value = AGI_RT_REPLY_CHOICE;
        if (op == 161) {
            if (!s->f[14]) break;
            if (!s->menu_submitted) return fail(r, AGI_RT_ARGUMENT, op);
            value = AGI_RT_REPLY_MENU;
        }
        if ((op == 129 || op == 162) && !r->resources->views[op == 129 ? a : s->v[a]].data) return fail(r, AGI_RT_RESOURCE, op == 129 ? a : s->v[a]);
        if (op == 144 && !formatted_message(r, a, text)) return fail(r, AGI_RT_MESSAGE, a);
        if (op == 135) copy_text(text, sizeof(text), "Native AGI bounded resource memory");
        if (op == 141) copy_text(text, sizeof(text), "AGI 2.917 / fDisBull native runtime 1");
        if (op == 134 && a == 1) { stop_sound(r); s->status = AGI_RT_QUIT; break; }
        if (op == 128 && s->f[16]) {
            uint64_t retired = s->retired;
            agi_runtime_restart(r); s->retired = retired; s->f[6] = 1;
            changed_pc = true; break;
        }
        if (!request(r, &insn, value, text)) return fail(r, AGI_RT_LIMIT, 0);
        if (op == 136) stop_sound(r);
        return 0;
    default: return fail(r, AGI_RT_UNIMPLEMENTED, op);
    }
retire:
    if (!changed_pc) s->pc = next;
    s->retired++; r->run_retired++;
    observe(r, &insn, logic, actor, actor < 256 ? &before_actor : NULL, resolved, prior_scene);
    return 1;
}

int agi_runtime_run(AgiRuntime *r, uint64_t budget)
{
    int result;
    if (!budget || budget > 1000000000) return -1;
    r->run_retired = 0;
    while (r->run_retired < budget) {
        result = agi_runtime_step(r);
        if (result <= 0) return result;
        if (r->state.status == AGI_RT_RETURN || r->state.status == AGI_RT_QUIT) return 0;
    }
    if (r->state.status == AGI_RT_RUNNING) r->state.status = AGI_RT_BUDGET;
    return 1;
}
bool agi_runtime_cycle(AgiRuntime *r)
{
    AgiRuntimeState *s = &r->state;
    AgiRuntimeActorCallbacks cb = actor_callbacks(r);
    int result;
    uint32_t logic = r->resources->entry_logic;
    if ((s->status != AGI_RT_RETURN && s->status != AGI_RT_READY) || s->cycle_active ||
        !logic_exists(r, logic) || s->scan_start[logic] >= r->resources->logics[logic].code.size) return false;
    result = agi_runtime_actor_prepare(&s->world, s->v, s->f, &cb);
    if (result < 0) return false;
    s->logic = logic; s->pc = s->scan_start[logic]; s->stack_depth = 0;
    s->cycle_active = 1; s->status = AGI_RT_READY;
    return true;
}
static void clock_tick(AgiRuntimeState *s)
{
    s->clock_ticks++;
    if (s->clock_ticks % 20 == 0 && ++s->v[11] == 60) {
        s->v[11] = 0;
        if (++s->v[12] == 60) {
            s->v[12] = 0;
            if (++s->v[13] == 24) { s->v[13] = 0; s->v[14]++; }
        }
    }
}
typedef struct AgiRuntimeSoundBatch {
    AgiRuntime *runtime;
    AgiRuntimeSoundEvent *events;
    uint32_t count;
} AgiRuntimeSoundBatch;
static int batch_source(void *opaque, uint8_t number, const uint8_t **data, size_t *size)
{ return sound_source(((AgiRuntimeSoundBatch *)opaque)->runtime, number, data, size); }
static void batch_output(void *opaque, const AgiRuntimeSoundOutput *output)
{
    AgiRuntimeSoundBatch *batch = opaque;
    memcpy(batch->events + batch->count, output->events,
           output->count * sizeof(*batch->events));
    batch->count += output->count;
}
static bool advance_time(AgiRuntime *r, uint32_t ticks, bool world)
{
    AgiRuntimeState *s = &r->state;
    AgiRuntimeState *saved;
    AgiRuntimeActorCallbacks cb = actor_callbacks(r);
    AgiRuntimeSoundBatch batch = { .runtime = r };
    AgiRuntimeSoundCallbacks scb = {
        .resource = batch_source, .output = batch_output, .opaque = &batch
    };
    uint32_t i, audio_ticks = ticks * (world ? 3 : 1);
    bool ok = false;
    if (!ticks || ticks > 4096 || (world && s->cycle_active) ||
        s->status == AGI_RT_FAULT || s->status == AGI_RT_QUIT) return false;
    if (s->status == AGI_RT_PENDING && s->pending.opcode == 136) return false;
    /* Admit storage before modifying state. A later rejected tick rolls back
     * the entire command; external devices see only the committed batch. */
    saved = malloc(sizeof(*saved));
    batch.events = malloc((size_t)audio_ticks * AGI_SOUND_OUTPUT_MAX * sizeof(*batch.events));
    if (!saved || !batch.events) goto done;
    *saved = *s;
    if (world && agi_runtime_actor_tick(&s->world, ticks, s->v, s->f, &cb) < 0) goto rollback;
    for (i = 0; i < audio_ticks; i++)
        if (agi_runtime_sound_tick(&s->sound, s->f, s->v[23], &scb) < 0) goto rollback;
    sync_sound(s);
    if (world) for (i = 0; i < ticks; i++) clock_tick(s);
    s->scene_revision++;
    if (r->obs_mask & 2) append_event(r, NULL, s->logic, 1, 256, NULL, NULL);
    if (r->sound_output && batch.count)
        r->sound_output(r->sound_output_opaque, batch.events, batch.count);
    ok = true;
    goto done;
rollback:
    *s = *saved;
done:
    free(saved); free(batch.events);
    return ok;
}
bool agi_runtime_tick(AgiRuntime *r, uint32_t ticks)
{ return advance_time(r, ticks, true); }
bool agi_runtime_sound_ticks(AgiRuntime *r, uint32_t ticks)
{ return advance_time(r, ticks, false); }
bool agi_runtime_input(AgiRuntime *r, const char *text)
{
    AgiRuntimeState saved;
    if (!text || !r->state.input_enabled || strlen(text) >= AGI_RT_STRING_BYTES ||
        r->state.status == AGI_RT_FAULT || r->state.status == AGI_RT_QUIT) return false;
    saved = r->state;
    if (!parse_input(r, text)) { r->state = saved; return false; }
    copy_text(r->state.input, sizeof(r->state.input), text);
    copy_text(r->state.echo, sizeof(r->state.echo), text);
    return true;
}
bool agi_runtime_key(AgiRuntime *r, uint16_t key, bool pressed)
{
    AgiRuntimeState *s = &r->state;
    uint32_t i, direction = 0;
    if (s->status == AGI_RT_FAULT || s->status == AGI_RT_QUIT) return false;
    switch (key) {
    case 0x4800: direction = 1; break; case 0x4900: direction = 2; break;
    case 0x4d00: direction = 3; break; case 0x5100: direction = 4; break;
    case 0x5000: direction = 5; break; case 0x4f00: direction = 6; break;
    case 0x4b00: direction = 7; break; case 0x4700: direction = 8; break;
    }
    if (direction && s->world.player_control) {
        if (pressed) s->world.actors[0].direction = s->hold_key ? direction :
            s->world.actors[0].direction == direction ? 0 : direction;
        else if (s->hold_key && s->world.actors[0].direction == direction) s->world.actors[0].direction = 0;
        s->v[6] = s->world.actors[0].direction;
    }
    if (pressed) {
        s->keypress = key;
        s->v[19] = key & 255;
        for (i = 0; i < s->key_count; i++) if (s->keys[i] == key) s->controllers[s->key_controllers[i]] = 1;
    }
    return true;
}
bool agi_runtime_controller(AgiRuntime *r, uint8_t controller)
{
    if (r->state.status == AGI_RT_FAULT || r->state.status == AGI_RT_QUIT) return false;
    r->state.controllers[controller] = 1;
    return true;
}

bool agi_runtime_complete(AgiRuntime *r, uint64_t id, bool accepted,
                          const char *text, uint32_t number)
{
    AgiRuntimeState *s = &r->state;
    AgiRuntimePending p = s->pending;
    AgiDecodedInstruction insn;
    const AgiRuntimeBlob *code;
    uint32_t i, resolved[7] = {0};
    uint64_t prior = s->scene_revision;
    if (s->status != AGI_RT_PENDING || p.id != id || !id ||
        p.logic != s->logic || p.pc != s->pc || number > 255 ||
        (text && strlen(text) >= AGI_RT_STRING_BYTES)) return false;
    if (p.reply == AGI_RT_REPLY_RESTORE && accepted) return false;
    if (p.reply == AGI_RT_REPLY_TEXT && accepted && !text) return false;
    if (p.reply == AGI_RT_REPLY_TEXT && accepted && strlen(text) > p.args[4]) return false;
    if (p.reply == AGI_RT_REPLY_MENU && accepted) {
        for (i = 0; i < s->menu_item_count; i++) if (s->menu_items[i].controller == number && s->menu_items[i].enabled) break;
        if (i == s->menu_item_count) return false;
    }
    code = &r->resources->logics[p.logic].code;
    if (!agi_decode(code_read, (void *)code, code->size, p.pc, AGI_DECODE_RUNTIME,
                    AGI_DECODE_STRUCTURAL, &insn) || insn.opcode != p.opcode) return false;
    if (accepted) {
        if (p.reply == AGI_RT_REPLY_TEXT) copy_text(s->strings[p.args[0]], AGI_RT_STRING_BYTES, text);
        if (p.reply == AGI_RT_REPLY_NUMBER) {
            if (p.opcode == 124 && number != 255 &&
                (number >= r->resources->object_count || s->inventory[number] != 255)) return false;
            s->v[p.opcode == 124 ? 25 : p.args[1]] = number;
        }
        if (p.reply == AGI_RT_REPLY_MENU) s->controllers[number] = 1;
    }
    if (p.opcode == 124 && p.reply == AGI_RT_REPLY_NUMBER && !accepted) s->v[25] = 255;
    if (p.opcode == 134 && accepted) { stop_sound(r); s->status = AGI_RT_QUIT; }
    else if (p.opcode == 128 && accepted) {
        uint64_t retired = s->retired;
        agi_runtime_restart(r);
        s->retired = retired + 1; r->run_retired++;
        s->f[6] = 1;
        observe(r, &insn, p.logic, 256, NULL, resolved, prior);
        return true;
    } else s->status = AGI_RT_READY;
    s->pc = p.next_pc;
    memset(&s->pending, 0, sizeof(s->pending));
    s->retired++; r->run_retired++;
    s->scene_revision++;
    observe(r, &insn, p.logic, 256, NULL, resolved, prior);
    return true;
}

/* Same-ABI snapshots are intentionally distinct from portable game saves.
 * They carry no pointers and are bound to this exact resource package. */
typedef struct AgiRuntimeSnapshotHeader {
    char magic[8], resource_sha256[65];
    uint32_t size, endian, version;
} AgiRuntimeSnapshotHeader;
static bool valid_snapshot(const AgiRuntime *r, const AgiRuntimeState *s);
size_t agi_runtime_snapshot_size(void)
{ return sizeof(AgiRuntimeSnapshotHeader) + sizeof(AgiRuntimeState); }
bool agi_runtime_snapshot(const AgiRuntime *r, void *out, size_t size)
{
    AgiRuntimeSnapshotHeader header;
    AgiRuntimeState state = r->state;
    if (!out || size != agi_runtime_snapshot_size()) return false;
    memset(&header, 0, sizeof(header));
    memcpy(header.magic, "FDBAGIS1", 8);
    memcpy(header.resource_sha256, r->resources->sha256, 65);
    header.size = sizeof(state); header.endian = 0x01020304; header.version = 1;
    if (state.status == AGI_RT_PENDING && state.pending.opcode == 125) {
        state.pc = state.pending.next_pc;
        state.retired++;
        state.status = AGI_RT_READY;
        memset(&state.pending, 0, sizeof(state.pending));
    }
    if (state.status == AGI_RT_BUDGET || state.status == AGI_RT_RUNNING)
        state.status = AGI_RT_READY;
    if (!valid_snapshot(r, &state)) return false;
    memcpy(out, &header, sizeof(header));
    memcpy((uint8_t *)out + sizeof(header), &state, sizeof(state));
    return true;
}
static bool valid_snapshot(const AgiRuntime *r, const AgiRuntimeState *s)
{
    uint32_t i;
    AgiRuntimePending empty_pending = {0};
    AgiRuntimeSoundCallbacks scb = sound_callbacks(r);
    uint8_t views[256] = {0}, pictures[256] = {0};
    if (!logic_exists(r, s->logic) || s->pc > r->resources->logics[s->logic].code.size ||
        (s->status != AGI_RT_READY && s->status != AGI_RT_RETURN) ||
        (s->status == AGI_RT_READY && s->pc == r->resources->logics[s->logic].code.size) ||
        (s->status == AGI_RT_RETURN && (s->stack_depth || s->cycle_active)) ||
        memcmp(&s->pending, &empty_pending, sizeof(empty_pending)) || s->stack_depth > AGI_RT_STACK ||
        s->parsed_count > AGI_RT_WORDS || s->key_count > 256 ||
        s->menu_count > AGI_RT_MENUS || s->menu_item_count > AGI_RT_MENU_ITEMS ||
        s->script_capacity > AGI_RT_SCRIPT || s->script_count > s->script_capacity ||
        s->script_saved > s->script_count || s->sound_flag > 255 || s->sound_id > 255 ||
        s->view_order_count > 256 || s->picture_order_count > 256 ||
        !s->next_effect_id || s->graphics > 1 || s->cycle_active > 1 ||
        s->input_enabled > 1 || s->hold_key > 1 || s->foreground > 15 || s->background > 15 ||
        s->cursor > 255 || s->status_line > 1 || s->min_print_line > 255 || s->input_line > 255 ||
        s->status_line_row > 255 || s->window_open > 1 || s->dialogue > 1 || s->monitor > 1 ||
        s->upper_left_x > 255 || s->upper_left_y > 255 || s->picture_shown > 1 || s->picture_id > 255 ||
        s->menu_submitted > 1 || s->simple_save > 1 || s->trace_enabled > 1 || s->trace_logic > 255 ||
        s->trace_top > 255 || s->trace_height > 255 || s->keypress > 65535 ||
        agi_runtime_world_validate(&s->world) < 0 ||
        agi_runtime_sound_state_valid(&s->sound, &scb) < 0 ||
        s->sound_active != s->sound.active || s->sound_id != s->sound.resource ||
        s->sound_flag != s->sound.completion_flag || s->sound_remaining != s->sound.remaining ||
        !memchr(s->game_id, 0, sizeof(s->game_id)) ||
        !memchr(s->input, 0, sizeof(s->input)) || !memchr(s->echo, 0, sizeof(s->echo))) return false;
    for (i = 0; i < s->view_order_count; i++) {
        if (views[s->view_order[i]]) return false;
        views[s->view_order[i]] = 1;
    }
    for (i = 0; i < s->picture_order_count; i++) {
        if (pictures[s->picture_order[i]]) return false;
        pictures[s->picture_order[i]] = 1;
    }
    for (i = 0; i < 256; i++) {
        if (s->f[i] > 1 || s->controllers[i] > 1 || s->loaded_logics[i] > 1 ||
            s->loaded_pictures[i] > 1 || s->loaded_sounds[i] > 1 || s->world.loaded_views[i] > 1 ||
            (s->loaded_logics[i] && !logic_exists(r, i)) ||
            (s->loaded_pictures[i] && !r->resources->pictures[i].data) ||
            (s->loaded_sounds[i] && !r->resources->sounds[i].data) ||
            (s->world.loaded_views[i] && !r->resources->views[i].data) ||
            views[i] != s->world.loaded_views[i] || pictures[i] != s->loaded_pictures[i] ||
            (s->scan_start[i] && (!logic_exists(r, i) || s->scan_start[i] >= r->resources->logics[i].code.size)) ||
            (i >= s->view_order_count && s->view_order[i]) ||
            (i >= s->picture_order_count && s->picture_order[i])) return false;
    }
    for (i = 0; i < s->stack_depth; i++) if (!logic_exists(r, s->stack[i].logic) ||
        s->stack[i].pc >= r->resources->logics[s->stack[i].logic].code.size) return false;
    for (i = 0; i < AGI_RT_STRINGS; i++) if (!memchr(s->strings[i], 0, AGI_RT_STRING_BYTES)) return false;
    for (i = 0; i < AGI_RT_WORDS; i++) if (!memchr(s->parsed_words[i], 0, AGI_RT_STRING_BYTES)) return false;
    for (i = 0; i < AGI_RT_MENUS; i++) if (!memchr(s->menus[i].text, 0, AGI_RT_STRING_BYTES) ||
        s->menus[i].first_item > s->menu_item_count || s->menus[i].item_count > s->menu_item_count - s->menus[i].first_item) return false;
    for (i = 0; i < AGI_RT_MENU_ITEMS; i++) if (!memchr(s->menu_items[i].text, 0, AGI_RT_STRING_BYTES) ||
        s->menu_items[i].controller > 255 || s->menu_items[i].enabled > 1) return false;
    for (i = 0; i < 25 * 40; i++) if (((const uint8_t *)s->text_fg)[i] > 15 ||
        ((const uint8_t *)s->text_bg)[i] > 15) return false;
    for (i = 0; i < s->script_count; i++) {
        uint32_t j, kind = s->script[i].opcode;
        if (kind > 8) return false;
        if (kind == 5 && s->script_count - i < 4) return false;
        for (j = i; j <= i + (kind == 5 ? 3 : 0); j++) {
            static const uint8_t zeros[6] = {0};
            if (s->script[j].opcode > 255 || memcmp(s->script[j].args + 1, zeros, 6)) return false;
        }
        if (kind == 5) i += 3;
    }
    for (i = 0; i < AGI_RUNTIME_PLANE_BYTES; i++) if (s->picture_visual[i] > 15 || s->picture_priority[i] > 15) return false;
    return true;
}
bool agi_runtime_restore(AgiRuntime *r, uint64_t id, const void *snapshot, size_t size)
{
    AgiRuntimeSnapshotHeader header;
    AgiRuntimeState candidate;
    uint64_t next;
    if (!snapshot || size != agi_runtime_snapshot_size() || r->state.status != AGI_RT_PENDING ||
        r->state.pending.opcode != 126 || r->state.pending.id != id) return false;
    memcpy(&header, snapshot, sizeof(header));
    if (memcmp(header.magic, "FDBAGIS1", 8) || header.version != 1 ||
        header.size != sizeof(candidate) || header.endian != 0x01020304 ||
        memcmp(header.resource_sha256, r->resources->sha256, 65)) return false;
    memcpy(&candidate, (const uint8_t *)snapshot + sizeof(header), sizeof(candidate));
    if (!valid_snapshot(r, &candidate)) return false;
    next = r->state.next_effect_id;
    r->state = candidate;
    if (r->state.next_effect_id < next) r->state.next_effect_id = next;
    r->state.f[12] = 1;
    r->state.scene_revision++;
    agi_runtime_clear_events(r);
    return true;
}

static int view_source(void *opaque, uint8_t view, const uint8_t **data, size_t *length)
{
    const AgiRuntime *r = opaque;
    const AgiRuntimeBlob *b = &r->resources->views[view];
    if (!b->data || !b->size) return 0;
    *data = b->data; *length = b->size;
    return 1;
}
bool agi_runtime_scene(const AgiRuntime *r, uint8_t *visual, uint8_t *priority, size_t size)
{
    return agi_runtime_scene_compose(&r->state.world, r->state.picture_visual,
        r->state.picture_priority, size, view_source, (void *)r, visual, priority, NULL) == AGI_RS_SUCCESS;
}
