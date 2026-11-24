/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "overlay/target/scumm/early.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(void)
{
 ScummTrace *t=calloc(1,sizeof(*t));assert(t);
 for(unsigned v=0;v<3;v++){
  const uint8_t p0[]={0x1a,20,7,0x5a,20,3,0x41,2,20,30,0x10,0};
  const uint8_t p12[]={0x1a,20,7,0,0x5a,20,3,0,0x41,2,20,30,0x80,0};
  const uint8_t *p=v?p12:p0;size_t n=v?sizeof(p12):sizeof(p0);
  ScummState baseline={0};
  for(unsigned mask=0;mask<4;mask++){
   ScummState s={0};memset(t,0,sizeof(*t));t->mask=mask;t->capacity=SCUMM_EVENT_MAX;
   for(unsigned k=0;k<4;k++)assert(scumm_step(v,p,n,&s,t));
   assert(s.status==S_WAIT&&s.vars[20]==10&&s.actors[2].x==10&&s.actors[2].y==30);
   assert(scumm_step(v,p,n,&s,t)&&s.status==S_RETURN&&s.retired==5);
   assert(t->eligible[0]==((mask&1)?5:0));assert(t->eligible[1]==((mask&2)?1:0));
   if(!mask)baseline=s;
   else{assert(s.pc==baseline.pc&&s.retired==baseline.retired&&s.status==baseline.status);
        assert(!memcmp(s.vars,baseline.vars,sizeof(s.vars)));
        assert(s.actors[2].x==baseline.actors[2].x&&s.actors[2].y==baseline.actors[2].y);}
  }
  ScummInsn i;uint8_t jump[]={0x18,0xfd,0xff};ScummState s={0};
  assert(scumm_decode(v,jump,sizeof(jump),0,&i)&&i.target==0);
  assert(scumm_step(v,jump,sizeof(jump),&s,NULL)&&s.pc==0);
  uint8_t bad[]={0x18,0x7f,0x7f};s=(ScummState){0};
  assert(!scumm_step(v,bad,sizeof(bad),&s,NULL)&&s.fault==S_BAD_BRANCH&&s.retired==0&&s.pc==0);
  uint8_t unsupported[]={0x02};s=(ScummState){0};
  assert(!scumm_step(v,unsupported,sizeof(unsupported),&s,NULL)&&s.fault==S_OPCODE);
  uint8_t truncated[]={0x1a,20};s=(ScummState){0};
  assert(!scumm_step(v,truncated,sizeof(truncated),&s,NULL)&&s.fault==S_TRUNCATED);
  uint8_t place[]={0x01,255,1,2};s=(ScummState){0};
  assert(!scumm_step(v,place,sizeof(place),&s,NULL)&&s.fault==S_BAD_ACTOR);
  uint8_t stop[]={0};s=(ScummState){0};memset(t,0,sizeof(*t));t->mask=3;
  assert(scumm_step(v,stop,sizeof(stop),&s,t)&&t->dropped[0]==1&&t->count==0);
  if(v){uint8_t indirect[]={0x9a,20,14,0};s=(ScummState){0};s.vars[14]=21;s.vars[21]=42;
   assert(scumm_step(v,indirect,sizeof(indirect),&s,NULL)&&s.vars[20]==42);}
 }
 free(t);puts("early SCUMM authored core checks passed");return 0;
}
