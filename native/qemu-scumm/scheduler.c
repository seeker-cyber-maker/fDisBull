/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "scheduler.h"
#include <string.h>
static void emit(ScummScheduler *s,unsigned slot,unsigned kind)
{
 ScummSchedSlot *p=&s->slots[slot];++s->event_seq;
 if(s->event_count>=s->event_capacity||s->event_count>=SCUMM_SCHED_MAX_EVENTS){++s->dropped;return;}
 ScummSchedEvent *e=&s->events[s->event_count++];
 *e=(ScummSchedEvent){s->event_seq,s->cycle,(uint16_t)slot,p->script_id,p->room_id,p->owner_id,(uint8_t)kind,p->scope,p->status,p->pc};
}
static void clear_slot(ScummSchedSlot *p){memset(p,0,sizeof(*p));}
void scumm_sched_init(ScummScheduler *s,uint32_t slots,uint32_t capacity,uint16_t room)
{
 memset(s,0,sizeof(*s));s->slot_capacity=slots>SCUMM_SCHED_MAX_SLOTS?SCUMM_SCHED_MAX_SLOTS:slots;
 s->event_capacity=capacity>SCUMM_SCHED_MAX_EVENTS?SCUMM_SCHED_MAX_EVENTS:capacity;s->current_room=room;
}
static bool run_slot(ScummScheduler *s,unsigned n,ScummSchedRun run,void *opaque,uint32_t budget)
{
 ScummSchedSlot *p=&s->slots[n];if(p->status!=SCUMM_SLOT_RUNNABLE)return false;
 if(!run||!budget){p->status=SCUMM_SLOT_WAITING;emit(s,n,SCUMM_EVENT_BUDGET);return false;}
 enum ScummSchedResult r=run(p,budget,opaque);++p->cycles;
 switch(r){
 case SCUMM_RUN_CONTINUE:p->status=SCUMM_SLOT_RUNNABLE;break;
 case SCUMM_RUN_YIELD:p->status=SCUMM_SLOT_WAITING;emit(s,n,SCUMM_EVENT_YIELD);break;
 case SCUMM_RUN_RETURN:p->status=SCUMM_SLOT_STOPPED;emit(s,n,SCUMM_EVENT_RETURN);break;
 case SCUMM_RUN_FAULT:default:p->status=SCUMM_SLOT_STOPPED;emit(s,n,SCUMM_EVENT_STOP);break;
 }return true;
}
int scumm_sched_start(ScummScheduler *s,uint16_t id,uint8_t scope,uint16_t owner,uint16_t room,const uint16_t *locals,uint8_t count,ScummSchedRun run,void *opaque,uint32_t budget)
{
 if(!s||!id||scope<SCUMM_SCOPE_GLOBAL||scope>SCUMM_SCOPE_OBJECT||count>SCUMM_SCHED_MAX_LOCALS||(count&&!locals))return -1;
 if(scope==SCUMM_SCOPE_ROOM&&room!=s->current_room)return -1;if(scope==SCUMM_SCOPE_GLOBAL)room=0;
 unsigned n;for(n=0;n<s->slot_capacity;n++)if(s->slots[n].status==SCUMM_SLOT_FREE||s->slots[n].status==SCUMM_SLOT_STOPPED)break;
 if(n==s->slot_capacity)return -1;
 ScummSchedSlot *p=&s->slots[n];clear_slot(p);p->status=SCUMM_SLOT_RUNNABLE;p->scope=scope;p->script_id=id;
 p->owner_id=owner;p->room_id=room;p->locals_count=count;if(count)memcpy(p->locals,locals,count*sizeof(*locals));
 ++p->starts;emit(s,n,SCUMM_EVENT_START);
 /* startScript enters immediately; callback owns the interpreter context. */
 run_slot(s,n,run,opaque,budget);return (int)n;
}
bool scumm_sched_stop(ScummScheduler *s,uint16_t slot)
{
 if(!s||slot>=s->slot_capacity||s->slots[slot].status==SCUMM_SLOT_FREE)return false;
 s->slots[slot].status=SCUMM_SLOT_STOPPED;emit(s,slot,SCUMM_EVENT_STOP);return true;
}
bool scumm_sched_chain(ScummScheduler *s,uint16_t slot,uint16_t id,ScummSchedRun run,void *opaque,uint32_t budget)
{
 if(!s||slot>=s->slot_capacity||!id)return false;ScummSchedSlot *p=&s->slots[slot];
 if(p->status==SCUMM_SLOT_FREE||p->status==SCUMM_SLOT_STOPPED)return false;
 p->script_id=id;p->pc=0;p->call_depth=0;p->locals_count=0;
 memset(p->locals,0,sizeof(p->locals));memset(p->stack,0,sizeof(p->stack));
 p->status=SCUMM_SLOT_RUNNABLE;emit(s,slot,SCUMM_EVENT_CHAIN);run_slot(s,slot,run,opaque,budget);return true;
}
bool scumm_sched_push(ScummScheduler *s,uint16_t slot,uint16_t script,uint32_t entry,const uint16_t *locals,uint8_t count)
{
 if(!s||slot>=s->slot_capacity||!script||count>SCUMM_SCHED_MAX_LOCALS||(count&&!locals))return false;
 ScummSchedSlot *p=&s->slots[slot];if(p->status==SCUMM_SLOT_FREE||p->status==SCUMM_SLOT_STOPPED||p->call_depth>=SCUMM_SCHED_MAX_CALL_DEPTH)return false;
 ScummSchedFrame *f=&p->stack[p->call_depth++];f->script_id=p->script_id;f->pc=p->pc;f->locals_count=p->locals_count;
 memcpy(f->locals,p->locals,sizeof(f->locals));p->script_id=script;p->pc=entry;p->locals_count=count;
 memset(p->locals,0,sizeof(p->locals));if(count)memcpy(p->locals,locals,count*sizeof(*locals));return true;
}
bool scumm_sched_pop(ScummScheduler *s,uint16_t slot)
{
 if(!s||slot>=s->slot_capacity)return false;ScummSchedSlot *p=&s->slots[slot];
 if(p->status==SCUMM_SLOT_FREE||p->status==SCUMM_SLOT_STOPPED||!p->call_depth)return false;
 ScummSchedFrame *f=&p->stack[--p->call_depth];p->script_id=f->script_id;p->pc=f->pc;p->locals_count=f->locals_count;
 memcpy(p->locals,f->locals,sizeof(p->locals));memset(f,0,sizeof(*f));return true;
}
bool scumm_sched_wake(ScummScheduler *s,uint16_t slot)
{
 if(!s||slot>=s->slot_capacity||s->slots[slot].status!=SCUMM_SLOT_WAITING)return false;
 s->slots[slot].status=SCUMM_SLOT_RUNNABLE;return true;
}
void scumm_sched_cycle(ScummScheduler *s,ScummSchedRun run,void *opaque,uint32_t budget)
{
 if(!s)return;++s->cycle;for(unsigned n=0;n<s->slot_capacity;n++)run_slot(s,n,run,opaque,budget);
}
void scumm_sched_room_teardown(ScummScheduler *s,uint16_t room)
{
 if(!s)return;for(unsigned n=0;n<s->slot_capacity;n++){ScummSchedSlot *p=&s->slots[n];
  if(p->status!=SCUMM_SLOT_FREE&&p->scope!=SCUMM_SCOPE_GLOBAL&&p->room_id==room){p->status=SCUMM_SLOT_STOPPED;emit(s,n,SCUMM_EVENT_ROOM_TEARDOWN);}
 }
}
