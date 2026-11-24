/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "overlay/target/scumm/early.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static void blocked(unsigned v,const uint8_t *code,size_t n,unsigned op)
{
 ScummState s={0};ScummInsn i;
 assert(scumm_decode(v,code,n,0,&i)&&i.op==op&&i.size==n);
 assert(!scumm_step(v,code,n,&s,NULL)&&s.status==S_BLOCKED&&s.pc==0&&s.retired==0);
 assert(!scumm_step(v,code,n,&s,NULL)&&s.status==S_BLOCKED&&s.pc==0);
}
int main(void)
{
 ScummTrace *t=calloc(1,sizeof(*t));assert(t);t->mask=3;t->capacity=SCUMM_EVENT_MAX;
 ScummState s={0};ScummInsn i;
 uint8_t range[]={0x26,20,3,1,2,3};
 assert(scumm_step(2,range,sizeof(range),&s,t));assert(s.vars[20]==1&&s.vars[22]==3);
 uint8_t words[]={0xa6,20,2,0xff,0xff,0x34,0x12};s=(ScummState){0};
 assert(scumm_step(2,words,sizeof(words),&s,t)&&s.vars[20]==65535&&s.vars[21]==0x1234);
 uint8_t max_range[513]={0xa6,1,255};s=(ScummState){0};max_range[512]=0x12;
 assert(scumm_step(2,max_range,sizeof(max_range),&s,t)&&s.vars[255]==0x1200);
 assert(t->events[t->count-1].size==513&&t->events[t->count-1].bytes[512]==0x12);
 uint8_t bad_range[]={0x26,255,2,1,2};s=(ScummState){0};s.vars[255]=42;
 assert(!scumm_step(2,bad_range,sizeof(bad_range),&s,t)&&s.fault==S_BAD_VAR&&s.vars[255]==42);
 uint8_t empty[]={0x26,1,0};s=(ScummState){0};
 assert(!scumm_step(2,empty,sizeof(empty),&s,t)&&s.fault==S_BAD_VAR);
 uint8_t indirect[]={0x0a,20,0x34,0x12,0x2a,20,1,0,0x6a,20,2,0};s=(ScummState){0};s.vars[20]=21;
 for(unsigned k=0;k<3;k++)assert(scumm_step(2,indirect,sizeof(indirect),&s,t));
 assert(s.vars[21]==0x1233&&s.vars[20]==21);
 s=(ScummState){0};s.vars[20]=256;assert(!scumm_step(2,indirect,sizeof(indirect),&s,t)&&s.fault==S_BAD_VAR);
 uint8_t actor[]={0x13,0,9,5,0x13,2,4,4,0x13,2,7,2,1,0x13,2,0,3,'B','o','b',0,0x01,2,5,6,0};
 s=(ScummState){0};for(unsigned k=0;k<6;k++)assert(scumm_step(2,actor,sizeof(actor),&s,t));
 assert(s.default_talk_color==9&&s.actors[2].costume==4&&s.actors[2].palette[1]==7&&s.actors[2].palette_known[1]);
 assert(s.actors[2].name_size==3&&s.actors[2].x==5&&s.actors[2].y==6&&s.status==S_RETURN);
 uint8_t p1[]={0x13,2,7,2};s=(ScummState){0};assert(scumm_step(1,p1,sizeof(p1),&s,t)&&s.actors[2].palette[2]==7);
 assert(!scumm_decode(0,p1,sizeof(p1),0,&i)&&i.fault==S_OPCODE);
 assert(!scumm_decode(2,p1,sizeof(p1),0,&i)&&i.fault==S_TRUNCATED);
 uint8_t p2[]={0x14,2,'a',4,0,'b',0};blocked(2,p2,sizeof(p2),S_PRINT);
 uint8_t verb[]={0x7a,1,2,3,4,5,'a',0};blocked(2,verb,sizeof(verb),S_VERB);
 uint8_t cutscene[]={0x40};blocked(2,cutscene,sizeof(cutscene),S_CUTSCENE);
 uint8_t res[]={0x0c,6,0x63};blocked(2,res,sizeof(res),S_RESOURCE);
 uint8_t start[]={0x42,2};blocked(2,start,sizeof(start),S_START_SCRIPT);
 uint8_t override[]={0x58,0x18,2,0};blocked(2,override,sizeof(override),S_OVERRIDE);
 for(unsigned k=1;k<sizeof(p2);k++)assert(!scumm_decode(2,p2,k,0,&i));
 free(t);puts("extended core fixtures passed");return 0;
}
