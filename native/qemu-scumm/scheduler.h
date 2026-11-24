/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef FDB_SCUMM_SCHEDULER_H
#define FDB_SCUMM_SCHEDULER_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define SCUMM_SCHED_MAX_SLOTS 64u
#define SCUMM_SCHED_MAX_LOCALS 32u
#define SCUMM_SCHED_MAX_CALL_DEPTH 16u
#define SCUMM_SCHED_MAX_EVENTS 4096u
enum ScummSchedScope { SCUMM_SCOPE_GLOBAL=1, SCUMM_SCOPE_ROOM=2, SCUMM_SCOPE_OBJECT=3 };
enum ScummSchedStatus { SCUMM_SLOT_FREE=0, SCUMM_SLOT_RUNNABLE=1, SCUMM_SLOT_WAITING=2, SCUMM_SLOT_STOPPED=3 };
enum ScummSchedResult { SCUMM_RUN_CONTINUE=0, SCUMM_RUN_YIELD=1, SCUMM_RUN_RETURN=2, SCUMM_RUN_FAULT=3 };
enum ScummSchedEventKind { SCUMM_EVENT_START=1, SCUMM_EVENT_YIELD=2, SCUMM_EVENT_RETURN=3, SCUMM_EVENT_STOP=4, SCUMM_EVENT_CHAIN=5, SCUMM_EVENT_ROOM_TEARDOWN=6, SCUMM_EVENT_BUDGET=7 };
typedef struct ScummSchedFrame { uint16_t script_id; uint32_t pc; uint8_t locals_count; uint16_t locals[SCUMM_SCHED_MAX_LOCALS]; } ScummSchedFrame;
typedef struct ScummSchedSlot {
 uint8_t status,scope,priority,call_depth;
 uint16_t script_id,owner_id,room_id;
 uint32_t pc;
 uint64_t starts,cycles,retired;
 uint16_t locals[SCUMM_SCHED_MAX_LOCALS];
 uint8_t locals_count;
 ScummSchedFrame stack[SCUMM_SCHED_MAX_CALL_DEPTH];
} ScummSchedSlot;
typedef struct ScummSchedEvent { uint64_t seq,cycle; uint16_t slot,script_id,room_id,owner_id; uint8_t kind,scope,status; uint32_t pc; } ScummSchedEvent;
typedef struct ScummScheduler {
 ScummSchedSlot slots[SCUMM_SCHED_MAX_SLOTS];
 ScummSchedEvent events[SCUMM_SCHED_MAX_EVENTS];
 uint64_t cycle,event_seq,dropped;
 uint32_t event_count,event_capacity,slot_capacity;
 uint16_t current_room;
 uint8_t running;
} ScummScheduler;
typedef enum ScummSchedResult (*ScummSchedRun)(ScummSchedSlot *,uint32_t,void *);
void scumm_sched_init(ScummScheduler *,uint32_t,uint32_t,uint16_t);
int scumm_sched_start(ScummScheduler *,uint16_t,uint8_t,uint16_t,uint16_t,const uint16_t *,uint8_t,ScummSchedRun,void *,uint32_t);
bool scumm_sched_stop(ScummScheduler *,uint16_t);
bool scumm_sched_chain(ScummScheduler *,uint16_t,uint16_t,ScummSchedRun,void *,uint32_t);
bool scumm_sched_wake(ScummScheduler *,uint16_t);
bool scumm_sched_push(ScummScheduler *,uint16_t,uint16_t,uint32_t,const uint16_t *,uint8_t);
bool scumm_sched_pop(ScummScheduler *,uint16_t);
void scumm_sched_cycle(ScummScheduler *,ScummSchedRun,void *,uint32_t);
void scumm_sched_room_teardown(ScummScheduler *,uint16_t);
#endif
