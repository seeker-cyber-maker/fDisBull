/* Portable AGI 2.917 sound sequencer. SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef AGI_RUNTIME_SOUND_H
#define AGI_RUNTIME_SOUND_H

#include <stddef.h>
#include <stdint.h>

#define AGI_SOUND_CHANNELS 4u
#define AGI_SOUND_MAX_BYTES (2u * 1024u * 1024u)
#define AGI_SOUND_TICKS_PER_SECOND 60u
#define AGI_SOUND_OUTPUT_MAX 16u
#define AGI_SOUND_ENVELOPE_DISABLED UINT32_MAX

enum AgiRuntimeSoundResult {
    AGI_SOUND_OK = 0,
    AGI_SOUND_ARGUMENT = -1,
    AGI_SOUND_RESOURCE = -2,
    AGI_SOUND_STATE = -3,
    AGI_SOUND_LIMIT = -4
};
enum AgiRuntimeSoundOutputKind {
    AGI_SOUND_SPEAKER = 1, /* value=integer PIT divisor, enabled=gate */
    AGI_SOUND_COMMAND = 2  /* value=one SN76489 command byte */
};
typedef struct AgiRuntimeSoundEvent {
    uint64_t sequence, tick;
    uint32_t kind, channel, value, enabled;
} AgiRuntimeSoundEvent;
typedef struct AgiRuntimeSoundOutput {
    uint32_t count;
    AgiRuntimeSoundEvent events[AGI_SOUND_OUTPUT_MAX];
} AgiRuntimeSoundOutput;
typedef struct AgiRuntimeSoundChannel {
    uint32_t offset, countdown, finished;
    uint32_t tone, divisor, base_attenuation, attenuation;
    uint32_t envelope_index, envelope_value;
    uint64_t remaining;
} AgiRuntimeSoundChannel;
typedef struct AgiRuntimeSound {
    uint32_t active, resource, completion_flag, device, channel_count;
    uint32_t resource_size;
    uint64_t ticks, output_sequence, remaining;
    AgiRuntimeSoundChannel channels[AGI_SOUND_CHANNELS];
    AgiRuntimeSoundOutput last_output;
} AgiRuntimeSound;
typedef struct AgiRuntimeSoundInfo {
    uint32_t offsets[AGI_SOUND_CHANNELS];
    uint64_t durations[AGI_SOUND_CHANNELS]; /* includes the first read tick */
} AgiRuntimeSoundInfo;

/* Return 1 and immutable bytes for a resource, or 0 if unavailable. The source
 * and bytes must remain immutable for the runtime's lifetime. output observes
 * committed ordered commands only and must not mutate/reenter this sequencer.
 * It may be NULL; last_output always retains the latest operation's commands.
 * No host clock, mixer, device I/O, allocation, or global state is used. */
typedef struct AgiRuntimeSoundCallbacks {
    int (*resource)(void *opaque, uint8_t number,
                    const uint8_t **data, size_t *length);
    void (*output)(void *opaque, const AgiRuntimeSoundOutput *output);
    void *opaque;
} AgiRuntimeSoundCallbacks;

void agi_runtime_sound_init(AgiRuntimeSound *sound);
int agi_runtime_sound_validate(const uint8_t *data, size_t length,
                               AgiRuntimeSoundInfo *info);
int agi_runtime_sound_state_valid(const AgiRuntimeSound *sound,
                                  const AgiRuntimeSoundCallbacks *callbacks);
int agi_runtime_sound_start(AgiRuntimeSound *sound, uint8_t resource,
                            uint8_t completion_flag, uint8_t device,
                            uint8_t flags[256],
                            const AgiRuntimeSoundCallbacks *callbacks);
/* Exactly one 1/60-second sound tick. Independent of motion and clock ticks.
 * The global attenuation adjustment is unsigned and clamped after envelope.
 * All error returns preserve sound, flags, and external output atomically. */
int agi_runtime_sound_tick(AgiRuntimeSound *sound, uint8_t flags[256],
                           uint8_t global_attenuation,
                           const AgiRuntimeSoundCallbacks *callbacks);
int agi_runtime_sound_stop(AgiRuntimeSound *sound, uint8_t flags[256],
                           const AgiRuntimeSoundCallbacks *callbacks);
/* Reconstruct the current device output after restoring/rebinding a snapshot.
 * Does not advance time, notes, envelopes, completion, or caller flags. Only
 * output_sequence/last_output change, after full state/resource validation.
 * Inactive and not-yet-read channels are explicitly silenced. The state device
 * must identify the target hardware, including an inactive initial snapshot.
 * Passing callbacks->output=NULL stages the committed commands for the caller. */
int agi_runtime_sound_resync(AgiRuntimeSound *sound,
                             const AgiRuntimeSoundCallbacks *callbacks);

#endif
