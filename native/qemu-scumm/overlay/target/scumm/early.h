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
enum ScummOp { S_STOP,S_YIELD,S_MOVE,S_ADD,S_SUB,S_INC,S_DEC,S_JUMP,
 S_EQ,S_NE,S_ZERO,S_NONZERO,S_GE,S_LE,S_LT,S_GT,S_PLACE,S_RANGE,S_ACTOR_CONFIG,S_RESOURCE,S_START_SCRIPT,
 S_STOP_SCRIPT,S_CHAIN_SCRIPT,S_LOAD_ROOM,S_ACTOR_ROOM,S_NOP,
 S_CUTSCENE,S_CURSOR,S_LIGHTS,S_ANIMATE,S_WALK,S_PRINT,S_VERB,S_OVERRIDE,
 S_MOVE_IND,S_ADD_IND,S_SUB_IND,S_UNKNOWN };
enum ScummStatus { S_READY,S_RUNNING,S_BUDGET,S_RETURN,S_WAIT,S_FAULT,S_BLOCKED };
enum ScummFault { S_OK,S_OPCODE,S_TRUNCATED,S_BAD_VERSION,S_BAD_PC,
 S_BAD_VAR,S_BAD_ACTOR,S_BAD_BRANCH };
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
typedef struct ScummEvent {
 uint64_t seq,retired;
 uint32_t pc,next;
 uint16_t size;
 uint8_t channel,opcode,actor,bytes[SCUMM_INSN_MAX];
 ScummActor before,after;
} ScummEvent;
typedef struct ScummTrace {
 uint32_t mask,capacity,count;
 uint64_t eligible[2],dropped[2],sequence;
 ScummEvent events[SCUMM_EVENT_MAX];
} ScummTrace;
const char *scumm_op_name(unsigned op);
bool scumm_decode(unsigned version,const uint8_t *code,size_t len,
                  uint32_t pc,ScummInsn *out);
bool scumm_step(unsigned version,const uint8_t *code,size_t len,
                ScummState *s,ScummTrace *trace);
#endif
