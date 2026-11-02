#include "M16HOST.H"
#include <stdlib.h>
#pragma code_seg("FDBPROBE")
static int signed_coordinate(FdbU32 value,int *out) {
    if(value>32767UL && value<4294934528UL)return 1;
    *out=(int)(short)(FdbU16)(value&65535UL);return 0;
}
static int command(void *context,const Fdb16Command *c,const Fdb16Arena *payload) {
    Fdb16Host *h;int x,y;const Fdb16Config *cfg;
    (void)payload;h=(Fdb16Host*)context;cfg=fdb16_config();
    switch(c->kind) {
    case FDB_CMD_KEY:
        if(c->a>=cfg->key_count || c->c>1UL)return 1;
        return fdb16_host_key(h,(FdbU16)c->a,c->b,(int)c->c,c->clock);
    case FDB_CMD_POINTER:
        if(c->a>3UL || c->b>2UL || signed_coordinate(c->c,&x) || signed_coordinate(c->d,&y))return 1;
        return fdb16_host_pointer(h,(FdbU16)c->a,(FdbU16)c->b,x,y,c->clock);
    case FDB_CMD_CLOCK:return fdb16_host_tick(h,c->clock);
    case FDB_CMD_SELECT:
        if(c->a>=cfg->region_count || c->b>=cfg->regions[(unsigned int)c->a].count)return 1;
        return fdb16_host_select(h,(FdbU16)c->a,(FdbU16)c->b);
    case FDB_CMD_RESIZE:
        if(c->a<1UL || c->a>4096UL || c->b<1UL || c->b>4096UL)return 1;
        return fdb16_host_resize(h,(int)c->a,(int)c->b);
    case FDB_CMD_FOCUS:if(c->a>1UL)return 1;return fdb16_host_focus(h,(int)c->a,c->clock);
    default:return 1;
    }
}
static int capture(void *context,Fdb16File *out,FdbU16 width,FdbU16 height) {
    Fdb16Host *h;unsigned char *bgr,*rgba;FdbU32 stride;FdbU16 top,y,x,rows,capacity;int failed;
    h=(Fdb16Host*)context;stride=((FdbU32)width*3UL+3UL)&~3UL;
    capacity=(FdbU16)(32760UL/stride);if(!capacity)return 1;
    bgr=(unsigned char*)malloc((unsigned int)(stride*(FdbU32)capacity));
    rgba=(unsigned char*)malloc((unsigned int)((FdbU32)width*4UL));
    if(!bgr || !rgba){free(bgr);free(rgba);return 1;}
    failed=0;top=0;
    while(top<height && !failed){rows=(FdbU16)(height-top);if(rows>capacity)rows=capacity;
        if(fdb16_host_bgr(h,bgr,width,height,top,rows)){failed=1;break;}
        for(y=0;y<rows && !failed;y++){
            for(x=0;x<width;x++){
                FdbU32 at,dest;
                at=(FdbU32)(rows-1-y)*stride+(FdbU32)x*3UL;dest=(FdbU32)x*4UL;
                rgba[(unsigned int)dest]=bgr[(unsigned int)(at+2UL)];
                rgba[(unsigned int)(dest+1UL)]=bgr[(unsigned int)(at+1UL)];
                rgba[(unsigned int)(dest+2UL)]=bgr[(unsigned int)at];rgba[(unsigned int)(dest+3UL)]=255;
            }
            if(fdb16_write_bytes(out,rgba,(FdbU32)width*4UL))failed=1;
        }top=(FdbU16)(top+rows);
    }free(bgr);free(rgba);return failed;
}
int PASCAL WinMain(HINSTANCE instance,HINSTANCE previous,LPSTR line,int show) {
    Fdb16Host host;Fdb16Platform platform;char initial[256],input[256],output[256];int status;
    (void)previous;(void)show;
    if(fdb16_arguments(line,input,output)!=1 || fdb16_initial_path(instance,initial))return 2;
    if(fdb16_host_open(&host,initial,0UL))return 3;
    platform.command=command;platform.capture_view=capture;
    status=fdb16_host_study(&host,input,output,&platform,&host);fdb16_host_destroy(&host);return status;
}
