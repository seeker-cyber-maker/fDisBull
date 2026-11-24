/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "scheduler.h"
#include <assert.h>
#include <stdio.h>
typedef struct Probe {unsigned calls,order[128],count;enum ScummSchedResult next[SCUMM_SCHED_MAX_SLOTS];} Probe;
static enum ScummSchedResult run(ScummSchedSlot *s,uint32_t budget,void *opaque)
{Probe *p=opaque;assert(budget);++p->calls;if(p->count<128)p->order[p->count++]=s->script_id;s->pc+=budget;return p->next[s->script_id%SCUMM_SCHED_MAX_SLOTS];}
int main(void)
{
 ScummScheduler s;Probe p={0};scumm_sched_init(&s,8,128,7);uint16_t locals[]={11,22};
 p.next[1]=SCUMM_RUN_YIELD;p.next[2]=SCUMM_RUN_CONTINUE;p.next[3]=SCUMM_RUN_RETURN;
 int a=scumm_sched_start(&s,1,SCUMM_SCOPE_GLOBAL,0,99,locals,2,run,&p,3);
 int b=scumm_sched_start(&s,2,SCUMM_SCOPE_ROOM,0,7,NULL,0,run,&p,3);
 assert(a==0&&b==1&&p.calls==2&&s.slots[a].status==SCUMM_SLOT_WAITING);
 assert(s.slots[a].room_id==0&&s.slots[b].room_id==7&&s.slots[a].locals[1]==22);
 int c=scumm_sched_start(&s,3,SCUMM_SCOPE_OBJECT,44,7,NULL,0,run,&p,3);
 assert(c==2&&s.slots[c].status==SCUMM_SLOT_STOPPED&&scumm_sched_wake(&s,a)&&!scumm_sched_wake(&s,a));
 p.next[1]=SCUMM_RUN_CONTINUE;p.next[2]=SCUMM_RUN_YIELD;scumm_sched_cycle(&s,run,&p,2);
 assert(p.order[p.count-2]==1&&p.order[p.count-1]==2);
 assert(s.slots[a].status==SCUMM_SLOT_RUNNABLE&&s.slots[b].status==SCUMM_SLOT_WAITING);
 scumm_sched_room_teardown(&s,7);assert(s.slots[a].status==SCUMM_SLOT_RUNNABLE);
 assert(s.slots[b].status==SCUMM_SLOT_STOPPED&&s.slots[c].status==SCUMM_SLOT_STOPPED);
 p.next[4]=SCUMM_RUN_YIELD;int d=scumm_sched_start(&s,4,SCUMM_SCOPE_GLOBAL,0,0,NULL,0,run,&p,1);
 assert(d==1&&scumm_sched_chain(&s,d,5,run,&p,1)&&s.slots[d].script_id==5);
 uint16_t nested[]={77};uint16_t outer=s.slots[d].script_id;uint32_t pc=s.slots[d].pc;
 assert(scumm_sched_push(&s,d,9,123,nested,1)&&s.slots[d].script_id==9&&s.slots[d].locals[0]==77);
 assert(scumm_sched_pop(&s,d)&&s.slots[d].script_id==outer&&s.slots[d].pc==pc);
 for(unsigned k=0;k<SCUMM_SCHED_MAX_CALL_DEPTH;k++)assert(scumm_sched_push(&s,d,9,k,NULL,0));
 assert(!scumm_sched_push(&s,d,9,0,NULL,0));
 for(unsigned k=0;k<SCUMM_SCHED_MAX_CALL_DEPTH;k++)assert(scumm_sched_pop(&s,d));
 assert(!scumm_sched_pop(&s,d)&&!scumm_sched_chain(&s,d,0,run,&p,1));
 assert(scumm_sched_start(&s,6,SCUMM_SCOPE_ROOM,0,8,NULL,0,run,&p,1)==-1);
 p.next[1]=SCUMM_RUN_YIELD;scumm_sched_init(&s,1,1,1);
 assert(scumm_sched_start(&s,1,SCUMM_SCOPE_GLOBAL,0,0,NULL,0,run,&p,1)==0);
 assert(scumm_sched_start(&s,2,SCUMM_SCOPE_GLOBAL,0,0,NULL,0,run,&p,1)==-1);
 assert(s.event_count==1&&s.dropped>0);
 puts("SCUMM scheduler model checks passed");return 0;
}
