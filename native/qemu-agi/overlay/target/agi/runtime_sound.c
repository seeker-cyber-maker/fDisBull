/* Portable AGI 2.917 sound sequencer. SPDX-License-Identifier: GPL-2.0-or-later
 * Independently implemented from the attributed behavioral contracts in
 * RUNTIME_SOUND_PROVENANCE.md; no host audio or interpreter globals. */
#include "runtime_sound.h"

#include <stdbool.h>
#include <string.h>

static const uint8_t envelope[] = {
    0xfe, 0xfd, 0xfe, 0xff, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2,
    2, 2, 3, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5,
    5, 6, 6, 6, 6, 6, 7, 7, 7, 7, 8, 8, 8, 8, 9, 9,
    9, 9, 10, 10, 10, 10, 11, 11, 11, 11, 11, 11, 12, 12, 12, 12,
    12, 12, 13, 0x80
};
static const uint8_t selectors[AGI_SOUND_CHANNELS] = { 0x90, 0xb0, 0xd0, 0xf0 };

static uint32_t word(const uint8_t *p)
{ return (uint32_t)p[0] | (uint32_t)p[1] << 8; }
static uint32_t channel_count(uint32_t device)
{ return device == 0 || device == 8 ? 1 : 4; }
static uint32_t duration(uint32_t value)
{ return value ? value : 65536; }
static bool overlaps(const void *a, size_t an, const void *b, size_t bn)
{
    uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
    return x <= y ? y - x < an : x - y < bn;
}
static bool arguments(const AgiRuntimeSound *s, const uint8_t *flags)
{ return s && flags && !overlaps(s, sizeof(*s), flags, 256); }

void agi_runtime_sound_init(AgiRuntimeSound *s)
{
    unsigned i;
    if (!s) return;
    memset(s, 0, sizeof(*s));
    for (i = 0; i < AGI_SOUND_CHANNELS; i++) {
        s->channels[i].finished = 1;
        s->channels[i].base_attenuation = s->channels[i].attenuation = 15;
        s->channels[i].envelope_index = AGI_SOUND_ENVELOPE_DISABLED;
    }
}

/* At most length/5 events per stream: offsets only move forward. */
static bool stream(const uint8_t *data, size_t length, uint32_t at,
                    uint64_t *ticks, uint32_t target, bool *boundary)
{
    uint64_t sum = 0;
    if (boundary) *boundary = false;
    for (;;) {
        uint32_t n;
        if (at > length || length - at < 2) return false;
        if (boundary && at == target) *boundary = true;
        n = word(data + at);
        if (n == 65535) break;
        if (length - at < 5) return false;
        sum += duration(n);
        at += 5;
    }
    *ticks = sum;
    return true;
}

int agi_runtime_sound_validate(const uint8_t *data, size_t length,
                               AgiRuntimeSoundInfo *out)
{
    AgiRuntimeSoundInfo info;
    unsigned i;
    if (!data || length < 10 || length > AGI_SOUND_MAX_BYTES ||
        (out && overlaps(data, length, out, sizeof(*out)))) return AGI_SOUND_RESOURCE;
    memset(&info, 0, sizeof(info));
    for (i = 0; i < AGI_SOUND_CHANNELS; i++) {
        uint32_t at = word(data + i * 2);
        if (at < 8 || !stream(data, length, at, &info.durations[i], 0, NULL))
            return AGI_SOUND_RESOURCE;
        info.offsets[i] = at;
        info.durations[i]++; /* the first record is read on sound tick one */
    }
    if (out) *out = info;
    return AGI_SOUND_OK;
}

static bool shape_valid(const AgiRuntimeSound *s)
{
    unsigned i;
    uint64_t maximum = 0;
    if (!s || s->active > 1 || s->resource > 255 || s->completion_flag > 255 ||
        s->device > 255 || s->resource_size > AGI_SOUND_MAX_BYTES ||
        (s->channel_count && s->channel_count != channel_count(s->device)) ||
        s->last_output.count > AGI_SOUND_OUTPUT_MAX ||
        (s->active && (!s->channel_count || s->resource_size < 10))) return false;
    for (i = 0; i < AGI_SOUND_CHANNELS; i++) {
        const AgiRuntimeSoundChannel *c = &s->channels[i];
        if (c->finished > 1 || c->countdown > 65536 || c->tone > 65535 ||
            c->divisor > 12276 || c->base_attenuation > 15 || c->attenuation > 15 ||
            c->envelope_value > 15 ||
            (c->envelope_index != AGI_SOUND_ENVELOPE_DISABLED &&
             c->envelope_index >= sizeof(envelope)) ||
            (c->finished && (c->countdown || c->remaining)) ||
            (!c->finished && (!s->active || i >= s->channel_count ||
                              !c->countdown || !c->remaining))) return false;
        if (i < s->channel_count && c->remaining > maximum) maximum = c->remaining;
    }
    return s->remaining == maximum && (!s->active || maximum != 0);
}

static bool resource(const AgiRuntimeSoundCallbacks *cb, uint32_t id,
                      const uint8_t **data, size_t *length)
{
    *data = NULL; *length = 0;
    return cb && cb->resource && cb->resource(cb->opaque, id, data, length) == 1 &&
           *data && *length >= 10 && *length <= AGI_SOUND_MAX_BYTES;
}

int agi_runtime_sound_state_valid(const AgiRuntimeSound *s,
                                  const AgiRuntimeSoundCallbacks *cb)
{
    const uint8_t *data;
    size_t length;
    AgiRuntimeSoundInfo info;
    unsigned i;
    if (!shape_valid(s)) return AGI_SOUND_STATE;
    if (!s->active) return AGI_SOUND_OK;
    if (!resource(cb, s->resource, &data, &length) || length != s->resource_size ||
        agi_runtime_sound_validate(data, length, &info) != AGI_SOUND_OK)
        return AGI_SOUND_RESOURCE;
    for (i = 0; i < s->channel_count; i++) {
        const AgiRuntimeSoundChannel *c = &s->channels[i];
        uint64_t ignored, suffix;
        bool boundary;
        if (!stream(data, length, info.offsets[i], &ignored, c->offset, &boundary) ||
            !boundary || !stream(data, length, c->offset, &suffix, 0, NULL) ||
            (c->finished ? word(data + c->offset) != 65535 :
             c->remaining != suffix + c->countdown)) return AGI_SOUND_STATE;
    }
    return AGI_SOUND_OK;
}

static void emit(AgiRuntimeSound *s, uint32_t kind, unsigned channel,
                  uint32_t value, uint32_t enabled)
{
    AgiRuntimeSoundEvent *e = &s->last_output.events[s->last_output.count++];
    e->sequence = ++s->output_sequence;
    e->tick = s->ticks;
    e->kind = kind; e->channel = channel; e->value = value; e->enabled = enabled;
}
static void silence(AgiRuntimeSound *s)
{
    unsigned i;
    if (s->channel_count == 1) emit(s, AGI_SOUND_SPEAKER, 0, 0, 0);
    else for (i = 0; i < AGI_SOUND_CHANNELS; i++)
        emit(s, AGI_SOUND_COMMAND, i, selectors[i] | 15, 0);
    for (i = 0; i < AGI_SOUND_CHANNELS; i++) {
        s->channels[i].finished = 1;
        s->channels[i].countdown = 0;
        s->channels[i].remaining = 0;
        s->channels[i].base_attenuation = s->channels[i].attenuation = 15;
    }
    s->active = 0; s->remaining = 0;
}
static void publish(AgiRuntimeSound *s, const AgiRuntimeSound *next,
                     const AgiRuntimeSoundCallbacks *cb)
{
    *s = *next;
    if (cb && cb->output && s->last_output.count) cb->output(cb->opaque, &s->last_output);
}

int agi_runtime_sound_start(AgiRuntimeSound *s, uint8_t id,
                            uint8_t flag, uint8_t device, uint8_t flags[256],
                            const AgiRuntimeSoundCallbacks *cb)
{
    AgiRuntimeSound next;
    AgiRuntimeSoundInfo info;
    const uint8_t *data;
    size_t length;
    unsigned i;
    uint32_t old_flag, was_active;
    if (!arguments(s, flags)) return AGI_SOUND_ARGUMENT;
    if (!shape_valid(s)) return AGI_SOUND_STATE;
    if (UINT64_MAX - s->output_sequence < AGI_SOUND_OUTPUT_MAX) return AGI_SOUND_LIMIT;
    if (!resource(cb, id, &data, &length) || overlaps(s, sizeof(*s), data, length) ||
        agi_runtime_sound_validate(data, length, &info) != AGI_SOUND_OK)
        return AGI_SOUND_RESOURCE;
    next = *s;
    memset(&next.last_output, 0, sizeof(next.last_output));
    old_flag = next.completion_flag; was_active = next.active;
    if (next.active) silence(&next);
    next.active = 1; next.resource = id; next.completion_flag = flag;
    next.device = device; next.channel_count = channel_count(device);
    next.resource_size = length; next.remaining = 0;
    memset(next.channels, 0, sizeof(next.channels));
    for (i = 0; i < AGI_SOUND_CHANNELS; i++) {
        AgiRuntimeSoundChannel *c = &next.channels[i];
        c->offset = info.offsets[i];
        c->envelope_index = AGI_SOUND_ENVELOPE_DISABLED;
        c->base_attenuation = c->attenuation = 15;
        if (i < next.channel_count) {
            c->countdown = 1; c->remaining = info.durations[i];
            if (c->remaining > next.remaining) next.remaining = c->remaining;
        } else c->finished = 1;
    }
    if (was_active) flags[old_flag] = 1;
    flags[flag] = 0; /* even when f9 is clear; the next tick applies that gate */
    publish(s, &next, cb);
    return AGI_SOUND_OK;
}

static void attenuation(AgiRuntimeSound *s, unsigned i, uint32_t adjustment)
{
    AgiRuntimeSoundChannel *c = &s->channels[i];
    uint32_t value = c->base_attenuation;
    if (value != 15) {
        if (c->envelope_index != AGI_SOUND_ENVELOPE_DISABLED) {
            uint8_t entry = envelope[c->envelope_index];
            if (entry == 0x80) {
                c->envelope_index = AGI_SOUND_ENVELOPE_DISABLED;
                value = c->base_attenuation = c->envelope_value;
            } else {
                int delta = entry < 128 ? entry : (int)entry - 256;
                int result = (int)value + delta;
                value = result < 0 ? 0 : result > 15 ? 15 : result;
                c->envelope_value = value;
                c->envelope_index++;
            }
        }
        value += adjustment;
        if (value > 15) value = 15;
        if (s->device == 2 && value < 8) value += 2;
    }
    c->attenuation = value;
    emit(s, AGI_SOUND_COMMAND, i, selectors[i] | value, value != 15);
}

int agi_runtime_sound_tick(AgiRuntimeSound *s, uint8_t flags[256],
                           uint8_t adjustment, const AgiRuntimeSoundCallbacks *cb)
{
    AgiRuntimeSound next;
    const uint8_t *data;
    size_t length;
    unsigned i;
    if (!arguments(s, flags)) return AGI_SOUND_ARGUMENT;
    if (!shape_valid(s)) return AGI_SOUND_STATE;
    if (s->ticks == UINT64_MAX || UINT64_MAX - s->output_sequence < AGI_SOUND_OUTPUT_MAX)
        return AGI_SOUND_LIMIT;
    next = *s; next.ticks++;
    memset(&next.last_output, 0, sizeof(next.last_output));
    if (!next.active) { publish(s, &next, cb); return AGI_SOUND_OK; }
    if (!flags[9]) {
        silence(&next); flags[next.completion_flag] = 1;
        publish(s, &next, cb); return AGI_SOUND_OK;
    }
    if (!resource(cb, next.resource, &data, &length) || length != next.resource_size ||
        overlaps(s, sizeof(*s), data, length)) return AGI_SOUND_RESOURCE;
    next.remaining = 0;
    for (i = 0; i < next.channel_count; i++) {
        AgiRuntimeSoundChannel *c = &next.channels[i];
        uint32_t at = c->offset;
        if (c->finished) continue;
        c->remaining--; c->countdown--;
        if (!c->countdown) {
            uint32_t n;
            if (at > length || length - at < 2) return AGI_SOUND_RESOURCE;
            n = word(data + at);
            if (n == 65535) {
                if (c->remaining) return AGI_SOUND_STATE;
                c->finished = 1; c->base_attenuation = c->attenuation = 15;
                if (next.channel_count == 4) attenuation(&next, i, adjustment);
                continue;
            }
            if (length - at < 5 || !c->remaining) return AGI_SOUND_RESOURCE;
            c->countdown = duration(n); c->offset += 5;
            c->tone = word(data + at + 2);
            c->divisor = 12 * (((c->tone & 0x3f) << 4) + ((c->tone >> 8) & 15));
            c->base_attenuation = data[at + 4] & 15;
            if (i < 3) c->envelope_index = 0;
            if (next.channel_count == 1) {
                c->attenuation = c->base_attenuation;
                emit(&next, AGI_SOUND_SPEAKER, i,
                     c->base_attenuation != 15 ? c->divisor : 0,
                     c->base_attenuation != 15);
            } else {
                uint32_t high = c->tone >> 8;
                emit(&next, AGI_SOUND_COMMAND, i, high, 1);
                if ((high & 0xe0) != 0xe0) emit(&next, AGI_SOUND_COMMAND, i, c->tone & 255, 1);
            }
        }
        if (next.channel_count == 4) attenuation(&next, i, adjustment);
        if (c->remaining > next.remaining) next.remaining = c->remaining;
    }
    if (!next.remaining) { silence(&next); flags[next.completion_flag] = 1; }
    publish(s, &next, cb);
    return AGI_SOUND_OK;
}

int agi_runtime_sound_stop(AgiRuntimeSound *s, uint8_t flags[256],
                           const AgiRuntimeSoundCallbacks *cb)
{
    AgiRuntimeSound next;
    if (!arguments(s, flags)) return AGI_SOUND_ARGUMENT;
    if (!shape_valid(s)) return AGI_SOUND_STATE;
    if (UINT64_MAX - s->output_sequence < AGI_SOUND_OUTPUT_MAX) return AGI_SOUND_LIMIT;
    next = *s;
    memset(&next.last_output, 0, sizeof(next.last_output));
    if (next.active) { silence(&next); flags[next.completion_flag] = 1; }
    publish(s, &next, cb);
    return AGI_SOUND_OK;
}

int agi_runtime_sound_resync(AgiRuntimeSound *s,
                             const AgiRuntimeSoundCallbacks *cb)
{
    AgiRuntimeSound next;
    const uint8_t *data = NULL;
    size_t length = 0;
    unsigned i;
    int result;
    if (!s) return AGI_SOUND_ARGUMENT;
    result = agi_runtime_sound_state_valid(s, cb);
    if (result != AGI_SOUND_OK) return result;
    if (UINT64_MAX - s->output_sequence < AGI_SOUND_OUTPUT_MAX)
        return AGI_SOUND_LIMIT;
    if (s->active && (!resource(cb, s->resource, &data, &length) ||
        length != s->resource_size || overlaps(s, sizeof(*s), data, length)))
        return AGI_SOUND_RESOURCE;
    next = *s;
    memset(&next.last_output, 0, sizeof(next.last_output));
    if (channel_count(next.device) == 1) {
        const AgiRuntimeSoundChannel *c = &next.channels[0];
        bool enabled = next.active && !c->finished && c->attenuation != 15;
        emit(&next, AGI_SOUND_SPEAKER, 0, enabled ? c->divisor : 0, enabled);
    } else {
        for (i = 0; i < AGI_SOUND_CHANNELS; i++) {
            const AgiRuntimeSoundChannel *c = &next.channels[i];
            uint32_t value = next.active && !c->finished ? c->attenuation : 15;
            /* Before the first tick, no note has been read. An ongoing muted
             * note still needs its tone restored: a later attenuation update
             * may unmute it without issuing another tone command. */
            if (next.active && !c->finished && c->offset != word(data + i * 2)) {
                uint32_t high = c->tone >> 8;
                emit(&next, AGI_SOUND_COMMAND, i, high, 1);
                if ((high & 0xe0) != 0xe0)
                    emit(&next, AGI_SOUND_COMMAND, i, c->tone & 255, 1);
            }
            emit(&next, AGI_SOUND_COMMAND, i, selectors[i] | value, value != 15);
        }
    }
    publish(s, &next, cb);
    return AGI_SOUND_OK;
}
