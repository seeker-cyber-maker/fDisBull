#include "memory-desktop.h"
#include <stdio.h>
#include <string.h>
static int command(void *context,const FdbHostCommand *c,const uint32_t *payload) {
    FdbHost *h=(FdbHost*)context;(void)payload;
    switch(c->kind) {
    case FDB_CMD_KEY:return fdb_host_key(h,c->a,c->b,(int)c->c,c->clock);
    case FDB_CMD_POINTER:return fdb_host_pointer(h,c->a,c->b,(int32_t)c->c,(int32_t)c->d,c->clock);
    case FDB_CMD_CLOCK:return fdb_host_tick(h,c->clock);
    case FDB_CMD_SELECT:return fdb_host_select(h,c->a,c->b);
    case FDB_CMD_RESIZE:return fdb_host_resize(h,(int)c->a,(int)c->b);
    case FDB_CMD_FOCUS:return fdb_host_focus(h,(int)c->a,c->clock);
    default:return 1;
    }
}
static int capture(void *context,uint8_t *out,uint32_t w,uint32_t h) {
    return fdb_host_render((FdbHost*)context,out,w,h);
}
int main(int argc,char **argv) {
    if(argc!=4 || strcmp(argv[1],"--adapter-test"))return 2;
    FdbHost h;if(fdb_host_open(&h,0))return 3;
    FdbHostPlatform p={command,capture};
    int result=fdb_host_study(&h,argv[2],argv[3],&p,&h);
    fdb_host_destroy(&h);return result;
}
