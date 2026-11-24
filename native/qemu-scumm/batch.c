#include "overlay/target/scumm/early.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
static unsigned seed=0x5343554d;
static unsigned next_rand(void){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
int main(void){
 ScummTrace *t=calloc(1,sizeof(*t));assert(t);
 unsigned total=0, good=0, truncated=0, faults=0, random_count=0;
 for(unsigned ver=0;ver<3;ver++){
  unsigned supported=0;
  for(unsigned op=0;op<256;op++){
   uint8_t c[8]={0};c[0]=op;ScummInsn i;
   bool ok=scumm_decode(ver,c,sizeof(c),0,&i);total++;
   if(ok){good++;supported++;assert(i.size>=1&&i.size<=sizeof(c)&&i.next==i.size);
    for(unsigned k=1;k<i.size;k++){ScummInsn partial;assert(!scumm_decode(ver,c,k,0,&partial)&&partial.fault==S_TRUNCATED);truncated++;}
   }else{assert(i.fault==S_OPCODE||i.fault==S_BAD_VAR||i.fault==S_TRUNCATED);faults++;}
  }
  printf("v%u: %u admitted opcode encodings, %u unadmitted\n",ver,supported,256-supported);
  for(unsigned k=0;k<20000;k++){
   uint8_t c[8];for(unsigned j=0;j<sizeof(c);j++)c[j]=(uint8_t)next_rand();
   unsigned len=next_rand()%9;
   ScummState a={0},b={0};
   a.pc=b.pc=next_rand()%10;
   for(unsigned j=0;j<256;j++)a.vars[j]=b.vars[j]=(uint16_t)next_rand();
   t->mask=3;t->capacity=1;t->count=0;t->sequence=0;memset(t->eligible,0,sizeof(t->eligible));memset(t->dropped,0,sizeof(t->dropped));
   bool ra=scumm_step(ver,c,len,&a,NULL),rb=scumm_step(ver,c,len,&b,t);
   assert(ra==rb&&a.pc==b.pc&&a.status==b.status&&a.retired==b.retired&&a.fault==b.fault&&a.fault_opcode==b.fault_opcode);
   assert(!memcmp(a.vars,b.vars,sizeof(a.vars)));
   assert(a.default_talk_color==b.default_talk_color);
   assert(!memcmp(a.actors,b.actors,sizeof(a.actors)));
   if(!ra)assert(!a.retired&&!t->count);
   random_count++;
  }
 }
 printf("%u opcode/version probes (%u admitted, %u rejected), %u truncated prefix probes, %u randomized paired single-step trials\n",total,good,faults,truncated,random_count);
 free(t);return 0;
}
