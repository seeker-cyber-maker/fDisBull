/* Generic owned graphics/input adapter for the bounded-memory native profile. */
#define _POSIX_C_SOURCE 200809L
#include "memory-desktop.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#ifdef _WIN32
#include <io.h>
#define fdb_open_file _open
#define fdb_fdopen _fdopen
#define fdb_close_file _close
#else
#include <unistd.h>
#define fdb_open_file open
#define fdb_fdopen fdopen
#define fdb_close_file close
#ifndef O_BINARY
#define O_BINARY 0
#endif
#endif
#include "memory-host-config.h"
_Static_assert(sizeof(FdbHostCommand)==36,"Diagnostic command layout differs");
#ifndef FDB_ADAPTER_OUTPUT_LIMIT
#define FDB_ADAPTER_OUTPUT_LIMIT (UINT64_C(256)*1024u*1024u)
#endif
#ifndef FDB_ADAPTER_INPUT_LIMIT
#define FDB_ADAPTER_INPUT_LIMIT (UINT64_C(128)*1024u*1024u)
#endif
/* A study's aggregate output is bounded before command/capture allocation.
 * The compile-time override is for small authored budget-refusal fixtures. */
static int reserve_output(uint64_t *used,uint64_t amount) {
    uint64_t limit=(uint64_t)FDB_ADAPTER_OUTPUT_LIMIT;
    if(*used>limit || amount>limit-*used)return 1;
    *used+=amount;return 0;
}
static int reserve_row(uint64_t *used,const FdbHost *h,const FdbHostCommand *c) {
    uint64_t amount=48u;
    if(reserve_output(&amount,(uint64_t)fdb_config.region_count*4u) ||
       reserve_output(&amount,(uint64_t)fdb_config.function_count*8u) ||
       reserve_output(&amount,(uint64_t)fdb_config.words*4u))return 1;
    for(uint32_t slot=0;slot<fdb_config.region_count;slot++)
        if(reserve_output(&amount,(uint64_t)fdb_config.regions[slot].count*8u))return 1;
    if((c->flags&FDB_CAPTURE_FRAME) &&
       reserve_output(&amount,(uint64_t)fdb_config.width*fdb_config.height*4u))return 1;
    if(c->flags&FDB_CAPTURE_VIEW) {
        uint64_t pixels=(uint64_t)h->view_width*(uint64_t)h->view_height;
        /* A refused resize keeps the old view, so admit the larger possibility
         * before executing it, even for EXPECT_REFUSAL commands. */
        if(c->kind==FDB_CMD_RESIZE && c->a && c->b && c->a<=4096u && c->b<=4096u) {
            uint64_t next=(uint64_t)c->a*c->b;if(next>pixels)pixels=next;
        }
        if(reserve_output(&amount,pixels*4u))return 1;
    }
    return reserve_output(used,amount);
}


const FdbHostConfig *fdb_host_config(void) { return &fdb_config; }
static int color(uint32_t index, uint8_t *out) {
    for (uint32_t i=0;i<fdb_config.color_count;i++) if(fdb_config.colors[i].index==index) {
        out[0]=fdb_config.colors[i].red;out[1]=fdb_config.colors[i].green;
        out[2]=fdb_config.colors[i].blue;out[3]=255;return 0;
    }
    return 1;
}
int fdb_host_resize(FdbHost *h,int width,int height) {
    if(width<1 || height<1 || width>4096 || height>4096)return 1;
    int rw,rh;
    if((uint64_t)width*fdb_config.height<=(uint64_t)height*fdb_config.width) {
        rw=width;rh=(int)((uint64_t)width*fdb_config.height/fdb_config.width);
    } else {rh=height;rw=(int)((uint64_t)height*fdb_config.width/fdb_config.height);}
    if(rw<1 || rh<1)return 1;
    h->view_width=width;h->view_height=height;
    h->rect_width=rw;h->rect_height=rh;h->rect_x=(width-rw)/2;h->rect_y=(height-rh)/2;
    return 0;
}
int fdb_host_sync(FdbHost *h) {
    if(!h || !h->words || !h->rgba || h->closed)return 1;
    if(fdb_copy_words(h->words,fdb_config.words))return 1;
    size_t count=(size_t)fdb_config.width*fdb_config.height;
    for(size_t i=0;i<count;i++)if(color(h->words[fdb_config.frame_offset+i],h->rgba+i*4))return 1;
    return 0;
}
void fdb_host_finish(FdbHost *h) {
    if(!h || h->closed)return;
    (void)fdb_host_sync(h);fdb_close();h->closed=1;
}
void fdb_host_destroy(FdbHost *h) {
    if(!h)return;
    fdb_host_finish(h);free(h->words);free(h->rgba);h->words=NULL;h->rgba=NULL;
}
static int committed(FdbHost *h,int status) {
    if(status){h->committed=0;return 1;}
    h->committed=1;if(fdb_host_sync(h))return 1;
    if(h->words[fdb_config.quit_index])fdb_host_finish(h);
    return 0;
}
int fdb_host_initialize(FdbHost *h,uint32_t clock) {
    if(!h || h->closed)return 1;
    h->accepted=1;h->committed=0;return committed(h,fdb_initialize(clock&65535u));
}
int fdb_host_open(FdbHost *h,uint32_t clock) {
    if(!h || fdb_config.words!=fdb_word_count() ||
       strcmp(fdb_config.config_sha256,fdb_config_sha256()))return 1;
    memset(h,0,sizeof(*h));
    h->words=(uint32_t*)malloc((size_t)fdb_config.words*4);
    h->rgba=(uint8_t*)malloc((size_t)fdb_config.width*fdb_config.height*4);
    if(!h->words || !h->rgba){free(h->words);free(h->rgba);memset(h,0,sizeof(*h));return 1;}
    h->focused=1;
    if(fdb_host_resize(h,(int)fdb_config.width,(int)fdb_config.height) || fdb_host_initialize(h,clock)) {
        fdb_host_destroy(h);return 1;
    }
    return 0;
}
static int dispatch(FdbHost *h,uint32_t kind,uint32_t ascii,uint32_t scan,uint32_t clock) {
    if(!h || h->closed)return 1;
    uint32_t i[]={fdb_config.kind,fdb_config.ascii,fdb_config.scan,fdb_config.x,
                  fdb_config.y,fdb_config.buttons,fdb_config.clock};
    uint32_t v[]={kind,ascii,scan,(uint32_t)h->mouse_x,(uint32_t)h->mouse_y,h->buttons,clock&65535u};
    h->accepted=1;h->committed=0;return committed(h,fdb_dispatch(i,v,7,1));
}
int fdb_host_key(FdbHost *h,uint32_t key,uint32_t mods,int focused,uint32_t clock) {
    if(!h || h->closed || key>=fdb_config.key_count || mods>31u || (focused!=0 && focused!=1))return 1;
    h->accepted=h->committed=0;
    if(!focused || (mods&(FDB_MOD_COMMAND|FDB_MOD_CONTROL|FDB_MOD_OPTION)))return 0;
    return dispatch(h,fdb_config.keyboard_kind,fdb_config.keys[key].ascii,fdb_config.keys[key].scan,clock);
}
int fdb_host_pointer(FdbHost *h,uint32_t phase,uint32_t button,int x,int y,uint32_t clock) {
    if(!h || h->closed || phase>FDB_POINTER_DRAG || button>2u ||
       x<-32768 || x>32767 || y<-32768 || y>32767)return 1;
    h->accepted=h->committed=0;
    int inside=x>=h->rect_x && y>=h->rect_y && x-h->rect_x<h->rect_width && y-h->rect_y<h->rect_height;
    if(!inside && !h->buttons)return 0;
    int old_x=h->mouse_x,old_y=h->mouse_y;uint32_t old_buttons=h->buttons;
    int dx=x-h->rect_x,dy=y-h->rect_y;
    if(dx<0)dx=0;
    if(dy<0)dy=0;
    if(dx>=h->rect_width)dx=h->rect_width-1;
    if(dy>=h->rect_height)dy=h->rect_height-1;
    h->mouse_x=(int)((uint64_t)(2*dx+1)*fdb_config.width/(2u*(uint32_t)h->rect_width));
    h->mouse_y=(int)((uint64_t)(2*dy+1)*fdb_config.height/(2u*(uint32_t)h->rect_height));
    if(phase==FDB_POINTER_DOWN)h->buttons|=1u<<button;
    if(phase==FDB_POINTER_UP)h->buttons&=~(1u<<button);
    int result=dispatch(h,fdb_config.pointer_kind,0,0,clock);
    if(result){h->mouse_x=old_x;h->mouse_y=old_y;h->buttons=old_buttons;}
    return result;
}
int fdb_host_tick(FdbHost *h,uint32_t clock) {
    if(!h || h->closed)return 1;
    return dispatch(h,fdb_config.clock_kind,0,0,clock);
}
int fdb_host_select(FdbHost *h,uint32_t slot,uint32_t variant) {
    if(!h || h->closed)return 1;
    h->accepted=h->committed=0;
    if(slot>=fdb_config.region_count || variant>=fdb_config.regions[slot].count)return 1;
    if(fdb_select_region(slot,variant))return 1;
    h->accepted=1;return 0;
}
int fdb_host_focus(FdbHost *h,int focused,uint32_t clock) {
    if(!h || h->closed || (focused!=0 && focused!=1))return 1;
    h->accepted=h->committed=0;h->focused=focused;
    if(focused || !h->buttons)return 0;
    uint32_t old=h->buttons;h->buttons=0;
    int result=dispatch(h,fdb_config.pointer_kind,0,0,clock);
    if(result)h->buttons=old;
    return result;
}
int fdb_host_replace_prefix(FdbHost *h,const uint32_t *prefix,size_t count) {
    if(!h || h->closed || !prefix || count>fdb_config.words)return 1;
    uint32_t *copy=(uint32_t*)malloc((size_t)fdb_config.words*4);if(!copy)return 1;
    memcpy(copy,h->words,(size_t)fdb_config.words*4);memcpy(copy,prefix,count*4);
    int result=fdb_replace_words(copy,fdb_config.words);free(copy);
    h->accepted=1;h->committed=0;if(result)return 1;return committed(h,0);
}
int fdb_host_render(FdbHost *h,uint8_t *rgba,uint32_t width,uint32_t height) {
    if(!h || !h->rgba || !rgba || width!=(uint32_t)h->view_width || height!=(uint32_t)h->view_height)return 1;
    for(uint32_t y=0;y<height;y++)for(uint32_t x=0;x<width;x++) {
        uint8_t *out=rgba+((size_t)y*width+x)*4;
        if((int)x<h->rect_x || (int)y<h->rect_y || (int)x-h->rect_x>=h->rect_width || (int)y-h->rect_y>=h->rect_height) {
            out[0]=out[1]=out[2]=0;out[3]=255;
        } else {
            uint32_t sx=(uint32_t)(((uint64_t)(2*(x-(uint32_t)h->rect_x)+1)*fdb_config.width)/(2u*(uint32_t)h->rect_width));
            uint32_t sy=(uint32_t)(((uint64_t)(2*(y-(uint32_t)h->rect_y)+1)*fdb_config.height)/(2u*(uint32_t)h->rect_height));
            memcpy(out,h->rgba+((size_t)sy*fdb_config.width+sx)*4,4);
        }
    }
    return 0;
}
static int read32(FILE *f,uint32_t *v) {
    uint8_t b[4];if(fread(b,1,4,f)!=4)return 1;
    *v=(uint32_t)b[0]|((uint32_t)b[1]<<8)|((uint32_t)b[2]<<16)|((uint32_t)b[3]<<24);return 0;
}
static int write32(FILE *f,uint32_t v) {
    uint8_t b[]={(uint8_t)v,(uint8_t)(v>>8),(uint8_t)(v>>16),(uint8_t)(v>>24)};
    return fwrite(b,1,4,f)!=4;
}
static int write_row(FILE *f,FdbHost *h,const FdbHostCommand *c,const FdbHostPlatform *p,void *context) {
    uint64_t rev=fdb_revision();
    uint32_t head[]={c->kind,(uint32_t)h->accepted,(uint32_t)h->committed,(uint32_t)h->closed,
       (uint32_t)rev,(uint32_t)(rev>>32),(uint32_t)h->mouse_x,(uint32_t)h->mouse_y,h->buttons,
       (uint32_t)h->view_width,(uint32_t)h->view_height,c->flags};
    for(size_t i=0;i<12;i++)if(write32(f,head[i]))return 1;
    for(uint32_t i=0;i<fdb_config.region_count;i++)if(write32(f,(uint32_t)fdb_selected_region(i)))return 1;
    for(uint32_t i=0;i<fdb_config.function_count;i++) {
        uint64_t value=fdb_invocation_count(i);
        if(write32(f,(uint32_t)value) || write32(f,(uint32_t)(value>>32)))return 1;
    }
    for(uint32_t i=0;i<fdb_config.region_count;i++)for(uint32_t j=0;j<fdb_config.regions[i].count;j++) {
        uint64_t value=fdb_region_invocation_count(i,j);
        if(write32(f,(uint32_t)value) || write32(f,(uint32_t)(value>>32)))return 1;
    }
    for(uint32_t i=0;i<fdb_config.words;i++)if(write32(f,h->words[i]))return 1;
    size_t bytes=(size_t)fdb_config.width*fdb_config.height*4;
    if((c->flags&FDB_CAPTURE_FRAME) && fwrite(h->rgba,1,bytes,f)!=bytes)return 1;
    if(c->flags&FDB_CAPTURE_VIEW) {
        bytes=(size_t)h->view_width*h->view_height*4;uint8_t *view=(uint8_t*)malloc(bytes);if(!view)return 1;
        int failed=!p || !p->capture_view || p->capture_view(context,view,(uint32_t)h->view_width,(uint32_t)h->view_height);
        if(!failed && fwrite(view,1,bytes,f)!=bytes)failed=1;
        free(view);if(failed)return 1;
    }
    return 0;
}
int fdb_host_study(FdbHost *h,const char *input,const char *output,const FdbHostPlatform *p,void *context) {
    FILE *in=fopen(input,"rb");if(!in)return 2;
    long input_length;
    if(fseek(in,0,SEEK_END) || (input_length=ftell(in))<0 ||
       (uint64_t)input_length>(uint64_t)FDB_ADAPTER_INPUT_LIMIT || input_length<32 ||
       fseek(in,0,SEEK_SET)){fclose(in);return 2;}
    uint64_t input_size=(uint64_t)input_length,input_used=32u;
    char magic[8];uint32_t header[6];int failed=fread(magic,1,8,in)!=8 || memcmp(magic,"FDBEVT1\0",8);
    for(size_t i=0;i<6 && !failed;i++)failed=read32(in,&header[i]);
    if(failed || header[0]!=fdb_config.words || header[1]>4096u || header[2]>65535u ||
       header[3]>=fdb_config.width || header[4]>=fdb_config.height || header[5]>7u){fclose(in);return 2;}
    uint64_t output_used=24u;
    if(reserve_output(&output_used,(uint64_t)fdb_config.region_count*4u)){fclose(in);return 2;}
    h->mouse_x=(int)header[3];h->mouse_y=(int)header[4];h->buttons=header[5];
    if(fdb_host_initialize(h,header[2])){fclose(in);return 3;}
    int fd=fdb_open_file(output,O_WRONLY|O_CREAT|O_EXCL|O_BINARY,0600);
    if(fd<0){fclose(in);return 2;}FILE *out=fdb_fdopen(fd,"wb");if(!out){fdb_close_file(fd);fclose(in);return 2;}
    failed=fwrite("FDBOUT1\0",1,8,out)!=8 || write32(out,fdb_config.words) || write32(out,header[1]) || write32(out,fdb_config.region_count) || write32(out,fdb_config.function_count);
    for(uint32_t i=0;i<fdb_config.region_count && !failed;i++)failed=write32(out,fdb_config.regions[i].count);
    for(uint32_t row=0;row<header[1] && !failed;row++) {
        FdbHostCommand c;uint32_t fields[9];
        if(input_used>input_size || 36u>input_size-input_used){failed=1;break;}
        input_used+=36u;
        for(size_t i=0;i<9;i++)if(read32(in,&fields[i])){failed=1;break;}
        if(failed)break;
        memcpy(&c,fields,sizeof(c));
        if(c.kind>FDB_CMD_CALL || c.clock>65535u || (c.flags&~7u) || c.payload_count>fdb_config.words*2u ||
           (c.payload_count && c.kind!=FDB_CMD_REPLACE && c.kind!=FDB_CMD_CALL)){failed=1;break;}
        uint64_t payload_bytes=(uint64_t)c.payload_count*4u;
        if(input_used>input_size || payload_bytes>input_size-input_used){failed=1;break;}
        input_used+=payload_bytes;
        if(reserve_row(&output_used,h,&c)){failed=1;break;}
        uint32_t *payload=(uint32_t*)malloc((c.payload_count?c.payload_count:1u)*4u);if(!payload){failed=1;break;}
        for(uint32_t i=0;i<c.payload_count;i++)if(read32(in,&payload[i])){failed=1;break;}
        if(failed){free(payload);break;}
        h->accepted=h->committed=0;
        if(!failed) switch(c.kind) {
        case FDB_CMD_SNAPSHOT:break;
        case FDB_CMD_REPLACE:failed=fdb_host_replace_prefix(h,payload,c.payload_count);break;
        case FDB_CMD_INITIALIZE:failed=fdb_host_initialize(h,c.clock);break;
        case FDB_CMD_CLOSE:fdb_host_finish(h);break;
        case FDB_CMD_CALL: {
            if(c.payload_count%2u || c.b>1u){failed=1;break;}
            size_t n=c.payload_count/2u;uint32_t *indices=(uint32_t*)malloc((n?n:1u)*4u),*values=(uint32_t*)malloc((n?n:1u)*4u);
            if(!indices || !values){free(indices);free(values);failed=1;break;}
            for(size_t i=0;i<n;i++){indices[i]=payload[2*i];values[i]=payload[2*i+1];}
            h->accepted=1;failed=committed(h,fdb_call(c.a,indices,values,n,(int)c.b));free(indices);free(values);break;
        }
        default:failed=!p || !p->command || p->command(context,&c,payload);break;
        }
        if(c.flags&FDB_EXPECT_REFUSAL) {
            if(!failed)failed=1;
            else failed=h->closed?0:fdb_host_sync(h);
        }
        free(payload);if(!failed)failed=write_row(out,h,&c,p,context);
    }
    if(!failed && (input_used!=input_size || fgetc(in)!=EOF))failed=1;
    if(ferror(in) || fflush(out))failed=1;
    if(fclose(out))failed=1;
    if(fclose(in))failed=1;
    return failed?3:0;
}
