/* SPDX-License-Identifier: GPL-2.0-or-later
 * Native AGI runtime. Opcode framing belongs exclusively to decode.c.
 */
#ifndef FDISBULL_AGI_RUNTIME_H
#define FDISBULL_AGI_RUNTIME_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "decode.h"
#include "runtime_actor.h"
#include "runtime_sound.h"

#define AGI_RUNTIME_PROFILE "agi-2917-runtime-1"
#define AGI_RT_STRINGS 25u
#define AGI_RT_STRING_BYTES 41u
#define AGI_RT_TEXT_BYTES 4096u
#define AGI_RT_WORDS 20u
#define AGI_RT_STACK 64u
#define AGI_RT_MENUS 64u
#define AGI_RT_MENU_ITEMS 256u
#define AGI_RT_SCRIPT 4096u
#define AGI_RT_EVENTS_MAX 65536u

enum AgiRuntimeStatus {
    AGI_RT_READY, AGI_RT_RUNNING, AGI_RT_BUDGET, AGI_RT_RETURN,
    AGI_RT_PENDING, AGI_RT_FAULT, AGI_RT_QUIT
};
enum AgiRuntimeError {
    AGI_RT_OK, AGI_RT_DECODE, AGI_RT_RESOURCE, AGI_RT_RESOURCE_NOT_LOADED,
    AGI_RT_CALL_OVERFLOW, AGI_RT_BAD_PC, AGI_RT_STRING, AGI_RT_MESSAGE,
    AGI_RT_WORD, AGI_RT_INVENTORY, AGI_RT_DIV_ZERO, AGI_RT_ARGUMENT,
    AGI_RT_ACTOR, AGI_RT_SCENE, AGI_RT_LIMIT, AGI_RT_COMPLETION,
    AGI_RT_SNAPSHOT, AGI_RT_UNIMPLEMENTED
};
enum AgiRuntimeReply {
    AGI_RT_REPLY_ACK, AGI_RT_REPLY_TEXT, AGI_RT_REPLY_NUMBER,
    AGI_RT_REPLY_CHOICE, AGI_RT_REPLY_MENU, AGI_RT_REPLY_RESTORE
};

typedef struct AgiRuntimeBlob {
    const uint8_t *data;
    uint32_t size;
    char sha256[65];
} AgiRuntimeBlob;
typedef struct AgiRuntimeLogic {
    AgiRuntimeBlob code;
    const char *messages[256]; /* slot 0 is unused; messages are literal */
    uint32_t message_count;
} AgiRuntimeLogic;
typedef struct AgiRuntimeWord {
    const char *text;
    uint16_t id;
} AgiRuntimeWord;
typedef struct AgiRuntimeResources {
    AgiRuntimeLogic logics[256];
    AgiRuntimeBlob views[256], pictures[256], sounds[256];
    const AgiRuntimeWord *words;
    uint32_t word_count, object_count, entry_logic;
    const char *object_names[256];
    uint8_t object_rooms[256];
    char sha256[65];
} AgiRuntimeResources;
typedef struct AgiRuntimeFrame {
    uint32_t logic, pc;
} AgiRuntimeFrame;
typedef struct AgiRuntimePending {
    uint64_t id;
    uint32_t opcode, logic, pc, next_pc, reply, argc;
    uint8_t args[7];
    char text[AGI_RT_TEXT_BYTES];
} AgiRuntimePending;
typedef struct AgiRuntimeMenu {
    uint32_t first_item, item_count;
    char text[AGI_RT_STRING_BYTES];
} AgiRuntimeMenu;
typedef struct AgiRuntimeMenuItem {
    uint32_t controller, enabled;
    char text[AGI_RT_STRING_BYTES];
} AgiRuntimeMenuItem;
typedef struct AgiRuntimeScriptEntry {
    uint32_t opcode;
    uint8_t args[7];
} AgiRuntimeScriptEntry;

/* Pointer-free architectural state. Immutable resource bytes, observation,
 * host clocks and transport bookkeeping are deliberately outside it. */
typedef struct AgiRuntimeState {
    uint8_t v[256], f[256], inventory[256];
    uint8_t loaded_logics[256], loaded_pictures[256], loaded_sounds[256];
    uint8_t view_order[256], picture_order[256];
    uint32_t view_order_count, picture_order_count;
    AgiRuntimeWorld world;
    uint32_t logic, pc, status, fault, fault_detail, fault_logic, fault_pc;
    uint32_t scan_start[256], stack_depth;
    AgiRuntimeFrame stack[AGI_RT_STACK];
    uint64_t retired, next_effect_id, scene_revision, presentation_revision;
    uint64_t cycle_count, clock_ticks;
    uint32_t cycle_active;
    AgiRuntimePending pending;
    char strings[AGI_RT_STRINGS][AGI_RT_STRING_BYTES];
    char input[AGI_RT_STRING_BYTES], echo[AGI_RT_STRING_BYTES], game_id[9];
    uint16_t word_ids[AGI_RT_WORDS];
    char parsed_words[AGI_RT_WORDS][AGI_RT_STRING_BYTES];
    uint32_t parsed_count;
    uint16_t keys[256];
    uint8_t key_controllers[256], controllers[256];
    uint32_t key_count, keypress, input_enabled, hold_key;
    uint32_t graphics, foreground, background, cursor, status_line;
    uint32_t min_print_line, input_line, status_line_row;
    uint32_t window_open, dialogue, monitor, upper_left_x, upper_left_y;
    uint8_t text[25][40], text_fg[25][40], text_bg[25][40];
    uint8_t picture_visual[AGI_RUNTIME_PLANE_BYTES];
    uint8_t picture_priority[AGI_RUNTIME_PLANE_BYTES];
    uint32_t picture_shown, picture_id;
    /* These summaries derive from sound, never drive the sequencer. */
    uint32_t sound_active, sound_id, sound_flag;
    uint64_t sound_remaining;
    AgiRuntimeSound sound;
    uint32_t menu_count, menu_item_count, menu_submitted;
    AgiRuntimeMenu menus[AGI_RT_MENUS];
    AgiRuntimeMenuItem menu_items[AGI_RT_MENU_ITEMS];
    uint32_t simple_save, script_capacity, script_count, script_saved;
    AgiRuntimeScriptEntry script[AGI_RT_SCRIPT];
    uint32_t trace_enabled, trace_logic, trace_top, trace_height;
} AgiRuntimeState;

typedef struct AgiRuntimeEvent {
    uint64_t seq, retired, scene_revision;
    uint32_t channel, logic, pc, opcode, next_logic, next_pc, size;
    uint32_t actor, kind, resolved[7];
    uint8_t bytes[AGI_DECODE_BYTES_MAX];
    AgiRuntimeActor before_actor, after_actor;
} AgiRuntimeEvent;
/* Complete ordered device commands, independent of optional observations.
 * Called only after commit. The sink must not mutate/reenter this runtime. */
typedef void (*AgiRuntimeSoundSink)(void *opaque,
    const AgiRuntimeSoundEvent *events, uint32_t count);
typedef struct AgiRuntime {
    AgiRuntimeState state;
    const AgiRuntimeResources *resources;
    AgiRuntimeEvent *events;
    uint32_t obs_mask, obs_capacity, obs_count, obs_limit;
    uint64_t obs_eligible[2], obs_dropped[2], obs_calls, epoch;
    uint64_t run_retired;
    AgiRuntimeSoundSink sound_output;
    void *sound_output_opaque;
} AgiRuntime;

/* Resources remain immutable/alive for the lifetime of the runtime. The
 * caller owns bounded event storage and may pass NULL with capacity zero. */
bool agi_runtime_init(AgiRuntime *runtime, const AgiRuntimeResources *resources,
                      AgiRuntimeEvent *events, uint32_t capacity);
void agi_runtime_restart(AgiRuntime *runtime);
int agi_runtime_step(AgiRuntime *runtime);
int agi_runtime_run(AgiRuntime *runtime, uint64_t budget);
bool agi_runtime_cycle(AgiRuntime *runtime);
bool agi_runtime_tick(AgiRuntime *runtime, uint32_t ticks);
bool agi_runtime_sound_ticks(AgiRuntime *runtime, uint32_t ticks);
void agi_runtime_set_sound_output(AgiRuntime *runtime,
                                  AgiRuntimeSoundSink sink, void *opaque);
bool agi_runtime_input(AgiRuntime *runtime, const char *text);
bool agi_runtime_key(AgiRuntime *runtime, uint16_t key, bool pressed);
bool agi_runtime_controller(AgiRuntime *runtime, uint8_t controller);
bool agi_runtime_complete(AgiRuntime *runtime, uint64_t id,
                          bool accepted, const char *text, uint32_t number);
bool agi_runtime_restore(AgiRuntime *runtime, uint64_t id,
                         const void *snapshot, size_t size);
size_t agi_runtime_snapshot_size(void);
bool agi_runtime_snapshot(const AgiRuntime *runtime, void *out, size_t size);
bool agi_runtime_scene(const AgiRuntime *runtime, uint8_t *visual,
                       uint8_t *priority, size_t size);
void agi_runtime_clear_events(AgiRuntime *runtime);
bool agi_runtime_observation(AgiRuntime *runtime, uint32_t mask,
                             uint32_t capacity);
const char *agi_runtime_status_name(uint32_t status);
const char *agi_runtime_error_name(uint32_t error);
const char *agi_runtime_reply_name(uint32_t reply);
#endif
