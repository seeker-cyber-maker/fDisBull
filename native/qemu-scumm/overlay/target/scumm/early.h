/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef FDB_SCUMM_EARLY_H
#define FDB_SCUMM_EARLY_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define SCUMM_CODE_MAX 65536u
#define SCUMM_ACTORS 32u
#define SCUMM_EVENT_MAX 4096u
#define SCUMM_INSN_MAX 514u
#define SCUMM_RESOURCE_TYPES 4u
#define SCUMM_RESOURCE_SLOTS 256u
#define SCUMM_OBS_DISASM 1u
#define SCUMM_OBS_SCENE 2u
#define SCUMM_OBS_MASK (SCUMM_OBS_DISASM | SCUMM_OBS_SCENE)
enum ScummOp { S_STOP,S_YIELD,S_MOVE,S_ADD,S_SUB,S_INC,S_DEC,S_JUMP,
 S_EQ,S_NE,S_ZERO,S_NONZERO,S_GE,S_LE,S_LT,S_GT,S_PLACE,S_RANGE,S_ACTOR_CONFIG,S_RESOURCE,S_START_SCRIPT,
 S_STOP_SCRIPT,S_CHAIN_SCRIPT,S_LOAD_ROOM,S_ACTOR_ROOM,S_NOP,
 S_CUTSCENE,S_CURSOR,S_LIGHTS,S_ANIMATE,S_WALK,S_PRINT,S_VERB,S_OVERRIDE,
 S_MOVE_IND,S_ADD_IND,S_SUB_IND,S_UNKNOWN };
enum ScummStatus { S_READY,S_RUNNING,S_BUDGET,S_RETURN,S_WAIT,S_FAULT,S_BLOCKED };
enum ScummFault { S_OK,S_OPCODE,S_TRUNCATED,S_BAD_VERSION,S_BAD_PC,
 S_BAD_VAR,S_BAD_ACTOR,S_BAD_BRANCH,S_BAD_RESOURCE };
enum ScummResourceType { S_RES_COSTUME,S_RES_ROOM,S_RES_SCRIPT,S_RES_SOUND };
enum ScummBlockReason { S_BLOCK_NONE,S_BLOCK_UNIMPLEMENTED,
 S_BLOCK_RESOURCE_MISSING,S_BLOCK_ROOM_MAPPER,S_BLOCK_CUTSCENE_NESTED,
 S_BLOCK_SENTENCE_OWNER };
enum ScummOperand { S_IMM,S_VAR,S_DEST };
typedef struct ScummArg { uint16_t value; uint8_t kind,width; } ScummArg;
typedef struct ScummInsn {
 uint32_t pc,next; int32_t target;
 uint16_t size,payload_size;
 uint32_t payload_pc;
 uint8_t opcode,count,op,fault,conditional,subop;
 ScummArg arg[3];
} ScummInsn;
typedef struct ScummActor {
 uint16_t x,y;
 uint8_t bound,sound,costume,talk_color,room;
 uint32_t name_pc;
 uint16_t name_size;
 uint8_t palette[32],palette_known[32];
} ScummActor;
typedef struct ScummState {
 uint16_t vars[256];
 ScummActor actors[SCUMM_ACTORS];
 uint32_t pc,status,fault,fault_opcode;
 uint8_t default_talk_color;
 uint64_t retired;
} ScummState;
/* A declared, isolated Amiga v2 context. Only this global script is active;
 * there are no other script slots or queued sentences. It is not boot state.
 * Available bytes are immutable and verified by the embedding byte bank.
 * Logical residency and locking are independent of physical bank storage. */
typedef struct ScummResource {
 uint32_t size;
 uint8_t available,resident,locked;
} ScummResource;
typedef struct ScummRuntime {
 uint8_t enabled;
 uint16_t script_id,counts[SCUMM_RESOURCE_TYPES];
 ScummResource resources[SCUMM_RESOURCE_TYPES][SCUMM_RESOURCE_SLOTS];
 /* Reset clears from user_state onward, preserving the immutable catalog. */
 uint8_t user_state,user_put,cursor_visible,current_room,camera_mode;
 uint8_t cutscene_active,saved_user_state,saved_room,saved_camera_mode;
 uint16_t saved_cursor;
 uint32_t override_pc;
 uint16_t override_script,sentence_count;
 /* A UI invalidation revision, not a count of rendered frames or callbacks. */
 uint64_t ui_revision;
 uint32_t blocked_reason;
} ScummRuntime;
/* Observer-only snapshots. None of these fields drive guest execution. */
typedef struct ScummControl {
 uint8_t user_state,user_put,cursor_visible,current_room,camera_mode;
 uint8_t cutscene_active,saved_user_state,saved_room,saved_camera_mode;
 uint16_t saved_cursor;
 uint32_t override_pc;
 uint16_t override_script,sentence_count;
 uint64_t ui_revision;
 /* Exact variable values at this control operation: 21,26,27,28,29,38. */
 uint16_t vars[6];
} ScummControl;
enum ScummEventKind { S_EVENT_RETIRE,S_EVENT_ACTOR,S_EVENT_DEFAULT_COLOR,
 S_EVENT_RESOURCE,S_EVENT_CONTROL };
typedef struct ScummEvent {
 uint64_t seq,retired,control_generation;
 uint32_t pc,next;
 uint16_t size;
 uint8_t channel,opcode,actor,kind,bytes[SCUMM_INSN_MAX];
 ScummInsn insn;
 /* Historical operand-resolution values, never resolved from a later snapshot. */
 uint16_t resolved[3],destination,destination_before,destination_after;
 uint8_t has_destination,branch_taken;
 ScummActor before,after;
 uint8_t before_color,after_color,resource_type;
 uint16_t resource_id;
 ScummResource before_resource,after_resource;
 ScummControl before_control,after_control;
} ScummEvent;
typedef struct ScummTrace {
 uint32_t mask,capacity,count;
 uint64_t eligible[2],stored[2],dropped[2],sequence;
 uint64_t epoch,control_generation,helper_calls;
 ScummEvent events[SCUMM_EVENT_MAX];
} ScummTrace;
const char *scumm_op_name(unsigned op);
bool scumm_decode(unsigned version,const uint8_t *code,size_t len,
                  uint32_t pc,ScummInsn *out);
bool scumm_step(unsigned version,const uint8_t *code,size_t len,
                ScummState *s,ScummTrace *trace);
void scumm_runtime_reset(ScummRuntime *runtime);
const char *scumm_block_reason(unsigned reason);
bool scumm_step_runtime(unsigned version,const uint8_t *code,size_t len,
                       ScummState *s,ScummTrace *trace,ScummRuntime *runtime);
bool scumm_scene_op(unsigned op);
void scumm_control_snapshot(const ScummState *state,const ScummRuntime *runtime,
                            ScummControl *out);
/* Native TCG separates mandatory execution from optional observation. A
 * successful capture is private until scumm_observe commits its records. */
bool scumm_execute_runtime(unsigned version,const uint8_t *code,size_t len,
                           ScummState *s,unsigned mask,ScummEvent *capture,
                           ScummRuntime *runtime);
void scumm_observe(ScummTrace *trace,const ScummEvent *capture,
                   const uint8_t *code);
void scumm_trace_clear(ScummTrace *trace);
#endif
