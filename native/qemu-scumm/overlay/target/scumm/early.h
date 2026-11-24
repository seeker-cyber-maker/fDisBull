/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef FDB_SCUMM_EARLY_H
#define FDB_SCUMM_EARLY_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define SCUMM_CODE_MAX 65536u
#define SCUMM_ACTORS 32u
#define SCUMM_EVENT_MAX 4096u
enum ScummOp { S_STOP,S_YIELD,S_MOVE,S_ADD,S_SUB,S_INC,S_DEC,S_JUMP,
 S_EQ,S_NE,S_ZERO,S_NONZERO,S_GE,S_LE,S_LT,S_GT,S_PLACE,S_UNKNOWN };
enum ScummStatus { S_READY,S_RUNNING,S_BUDGET,S_RETURN,S_WAIT,S_FAULT };
enum ScummFault { S_OK,S_OPCODE,S_TRUNCATED,S_BAD_VERSION,S_BAD_PC,
 S_BAD_VAR,S_BAD_ACTOR,S_BAD_BRANCH };
enum ScummOperand { S_IMM,S_VAR,S_DEST };
typedef struct ScummArg { uint16_t value; uint8_t kind,width; } ScummArg;
typedef struct ScummInsn {
 uint32_t pc,next; int32_t target;
 uint8_t opcode,size,count,op,fault,conditional;
 ScummArg arg[3];
} ScummInsn;
typedef struct ScummActor { uint16_t x,y; uint8_t bound; } ScummActor;
typedef struct ScummState {
 uint16_t vars[256];
 ScummActor actors[SCUMM_ACTORS];
 uint32_t pc,status,fault,fault_opcode;
 uint64_t retired;
} ScummState;
typedef struct ScummEvent {
 uint64_t seq,retired;
 uint32_t pc,next;
 uint8_t channel,opcode,size,actor,bytes[8];
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
