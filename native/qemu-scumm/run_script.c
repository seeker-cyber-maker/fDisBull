/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Standalone bounded probe; never supplies external effects or skips faults. */
#include "overlay/target/scumm/early.h"
#include <stdio.h>
#include <stdlib.h>
#include <inttypes.h>
int main(int argc,char **argv)
{
 if(argc!=3)return 2;
 char *end=NULL;unsigned long ver=strtoul(argv[1],&end,10);
 if(*end||ver>2)return 2;
 uint8_t *code=malloc(SCUMM_CODE_MAX+1);ScummTrace *trace=calloc(1,sizeof(*trace));
 if(!code||!trace){free(code);free(trace);return 2;}
 FILE *fp=fopen(argv[2],"rb");if(!fp){free(code);free(trace);return 2;}
 size_t n=fread(code,1,SCUMM_CODE_MAX+1,fp);int bad=ferror(fp);fclose(fp);
 if(bad||!n||n>SCUMM_CODE_MAX){free(code);free(trace);return 2;}
 ScummState state={0};ScummInsn i;
 unsigned decoded=0;uint32_t pc=0;
 while(pc<n&&decoded<100000&&scumm_decode(ver,code,n,pc,&i)){
  ++decoded;pc=i.next;
 }
 trace->mask=3;trace->capacity=SCUMM_EVENT_MAX;
 while(state.retired<10000&&scumm_step(ver,code,n,&state,trace)){
  if(state.status==S_RETURN||state.status==S_WAIT)break;
 }
 printf("{\"size\":%zu,\"static_prefix\":%u,\"static_end\":%u,\"retired\":%" PRIu64 ",\"pc\":%u,\"status\":%u,\"fault\":%u,\"opcode\":%u,\"retire_events\":%" PRIu64 ",\"scene_events\":%" PRIu64 "}\n",n,decoded,pc,state.retired,state.pc,state.status,state.fault,state.fault_opcode,trace->eligible[0],trace->eligible[1]);
 free(code);free(trace);return 0;
}
