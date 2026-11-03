/* Segmented, owned Win16 memory and host services. C89; no huge objects.
 * FDB16_HOST_TEST replaces only GlobalAlloc/GlobalLock with host allocation;
 * it qualifies portable logic, never Win16 loading, GDI, or message delivery.
 * M16HOST.H also declares:
 * Fdb16Arena *fdb16_load_initial(const char *,FdbU32,FdbU32);
 */
#define _POSIX_C_SOURCE 200809L
#include "M16HOST.H"
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <errno.h>
#ifdef FDB16_HOST_TEST
#include <unistd.h>
#ifndef O_BINARY
#define O_BINARY 0
#endif
#else
#include <io.h>
#endif

#define FDB16_PAGE_WORDS 8192UL
#define FDB16_MAX_PAGES 32
#define FDB16_SOURCE_WORDS 131072UL
#define FDB16_PATH_BYTES 256

struct Fdb16Arena {
    FdbU32 words;
    FdbU16 pages;
    HGLOBAL handles[FDB16_MAX_PAGES];
    FdbU32 FAR *data[FDB16_MAX_PAGES];
};

/* The OW1.9/Wine16 FILE implementation returned successful counts with wrong
 * bytes in native probes; CRT transfers also truncated movable far pointers.
 * This owned 4096-byte buffer uses exclusive CRT open, native far _lread/_lwrite
 * transfers, and CRT close. The portable branch uses POSIX read/write. */
struct Fdb16File {
    int descriptor,writing,failed;
    FdbU16 at,used;
    unsigned char bytes[4096];
};
Fdb16File *fdb16_file_open(const char *path,int write_new) {
    Fdb16File *file;int descriptor;
    if(!path || (write_new!=0 && write_new!=1))return NULL;
    descriptor=open(path,write_new?O_WRONLY|O_CREAT|O_EXCL|O_BINARY:O_RDONLY|O_BINARY,0600);
    if(descriptor<0)return NULL;
    file=(Fdb16File *)calloc(1,sizeof(Fdb16File));if(!file){close(descriptor);return NULL;}
    file->descriptor=descriptor;file->writing=write_new;return file;
}
static int file_flush(Fdb16File *file) {
    unsigned int at;int wrote;
    if(!file || !file->writing || file->failed)return 1;
    at=0;
    while(at<file->used) {
#ifdef FDB16_HOST_TEST
        wrote=write(file->descriptor,file->bytes+at,(unsigned int)(file->used-at));
        if(wrote<0 && errno==EINTR)continue;
#else
        wrote=(int)_lwrite((HFILE)file->descriptor,(LPCSTR)(file->bytes+at),(unsigned int)(file->used-at));
#endif
        if(wrote<=0){file->failed=1;return 1;}at+=(unsigned int)wrote;
    }
    file->used=0;return 0;
}
static int file_fill(Fdb16File *file) {
    int got;
    if(!file || file->writing || file->failed)return -1;
#ifdef FDB16_HOST_TEST
    do {got=read(file->descriptor,file->bytes,sizeof(file->bytes));}while(got<0 && errno==EINTR);
#else
    got=(int)_lread((HFILE)file->descriptor,file->bytes,sizeof(file->bytes));
#endif
    if(got<0){file->failed=1;return -1;}
    file->at=0;file->used=(FdbU16)got;return got?1:0;
}
int fdb16_file_read(Fdb16File *file,void *bytes,FdbU32 count) {
    unsigned char FAR *out;FdbU32 at;unsigned int chunk;
    if(!file || file->writing || file->failed || (count && !bytes) || count>65520UL)return 1;
    out=(unsigned char FAR *)bytes;at=0;
    while(at<count) {
        if(file->at==file->used && file_fill(file)!=1)return 1;
        chunk=(unsigned int)(count-at);if(chunk>file->used-file->at)chunk=file->used-file->at;
        memcpy(out+(unsigned int)at,file->bytes+file->at,chunk);file->at+=(FdbU16)chunk;at+=chunk;
    }
    return 0;
}
int fdb16_file_eof(Fdb16File *file) {
    int result;
    if(!file || file->writing || file->failed)return -1;
    if(file->at<file->used)return 0;result=file_fill(file);
    return result<0?-1:result==0;
}
int fdb16_file_close(Fdb16File *file) {
    int failed;if(!file)return 1;
    failed=file->failed;if(file->writing && file_flush(file))failed=1;
    if(close(file->descriptor))failed=1;free(file);return failed?1:0;
}

static void FAR *locked_alloc(FdbU32 bytes,HGLOBAL *handle) {
    void FAR *result;
#ifdef FDB16_HOST_TEST
    result=calloc(1,(unsigned int)bytes);*handle=(HGLOBAL)result;
#else
    *handle=GlobalAlloc(GMEM_MOVEABLE|GMEM_ZEROINIT,bytes);
    result=*handle?GlobalLock(*handle):NULL;
    if(!result && *handle){GlobalFree(*handle);*handle=0;}
#endif
    return result;
}
static void locked_free(HGLOBAL handle) {
    if(!handle)return;
#ifdef FDB16_HOST_TEST
    free((void *)handle);
#else
    GlobalUnlock(handle);GlobalFree(handle);
#endif
}
Fdb16Arena *fdb16_create(FdbU32 words) {
    Fdb16Arena *arena;FdbU16 page;FdbU32 count;
    if(words>FDB16_PAGE_WORDS*FDB16_MAX_PAGES)return NULL;
    arena=(Fdb16Arena *)calloc(1,sizeof(Fdb16Arena));if(!arena)return NULL;
    arena->words=words;arena->pages=(FdbU16)((words+FDB16_PAGE_WORDS-1UL)/FDB16_PAGE_WORDS);
    for(page=0;page<arena->pages;page++) {
        count=words-(FdbU32)page*FDB16_PAGE_WORDS;
        if(count>FDB16_PAGE_WORDS)count=FDB16_PAGE_WORDS;
        arena->data[page]=(FdbU32 FAR *)locked_alloc(count*4UL,&arena->handles[page]);
        if(!arena->data[page]){fdb16_release(arena);return NULL;}
    }
    return arena;
}
FdbU32 fdb16_word_count(const Fdb16Arena *arena){return arena?arena->words:0UL;}
int fdb16_read(const Fdb16Arena *arena,FdbU32 index,FdbU32 *value) {
    if(!arena || !value || index>=arena->words)return 1;
    *value=arena->data[(FdbU16)(index/FDB16_PAGE_WORDS)][(FdbU16)(index%FDB16_PAGE_WORDS)];return 0;
}
int fdb16_write(Fdb16Arena *arena,FdbU32 index,FdbU32 value) {
    if(!arena || index>=arena->words)return 1;
    arena->data[(FdbU16)(index/FDB16_PAGE_WORDS)][(FdbU16)(index%FDB16_PAGE_WORDS)]=value;return 0;
}
void fdb16_release(Fdb16Arena *arena) {
    FdbU16 page;if(!arena)return;
    for(page=0;page<arena->pages;page++)locked_free(arena->handles[page]);
    free(arena);
}
int fdb16_copy(Fdb16Arena *destination,const Fdb16Arena *source) {
    FdbU16 page;FdbU32 count;
    if(!destination || !source || destination->words!=source->words)return 1;
    if(destination==source)return 0;
    for(page=0;page<source->pages;page++) {
        count=source->words-(FdbU32)page*FDB16_PAGE_WORDS;
        if(count>FDB16_PAGE_WORDS)count=FDB16_PAGE_WORDS;
        memcpy(destination->data[page],source->data[page],(unsigned int)(count*4UL));
    }
    return 0;
}
Fdb16Arena *fdb16_clone(const Fdb16Arena *source) {
    Fdb16Arena *result;if(!source)return NULL;
    result=fdb16_create(source->words);if(result && fdb16_copy(result,source)){fdb16_release(result);return NULL;}
    return result;
}
int fdb16_equal(const Fdb16Arena *left,const Fdb16Arena *right) {
    FdbU16 page;FdbU32 count;
    if(!left || !right || left->words!=right->words)return 0;
    for(page=0;page<left->pages;page++) {
        count=left->words-(FdbU32)page*FDB16_PAGE_WORDS;
        if(count>FDB16_PAGE_WORDS)count=FDB16_PAGE_WORDS;
        if(memcmp(left->data[page],right->data[page],(unsigned int)(count*4UL)))return 0;
    }
    return 1;
}
static int ranges_valid(FdbU32 words,const Fdb16Range *ranges,FdbU16 count) {
    FdbU16 i;if(count && !ranges)return 0;
    for(i=0;i<count;i++)if(ranges[i].start>words || ranges[i].count>words-ranges[i].start)return 0;
    return 1;
}
int fdb16_copy_ranges(Fdb16Arena *destination,const Fdb16Arena *source,const Fdb16Range *ranges,FdbU16 count) {
    FdbU16 r,page,offset;FdbU32 at,left,chunk;
    if(!destination || !source || destination->words!=source->words || !ranges_valid(source->words,ranges,count))return 1;
    if(destination==source)return 0;
    for(r=0;r<count;r++) {
        at=ranges[r].start;left=ranges[r].count;
        while(left) {
            page=(FdbU16)(at/FDB16_PAGE_WORDS);offset=(FdbU16)(at%FDB16_PAGE_WORDS);
            chunk=FDB16_PAGE_WORDS-offset;if(chunk>left)chunk=left;
            memcpy(destination->data[page]+offset,source->data[page]+offset,(unsigned int)(chunk*4UL));
            at+=chunk;left-=chunk;
        }
    }
    return 0;
}
int fdb16_footprint(const Fdb16Arena *before,const Fdb16Arena *after,const Fdb16Range *ranges,FdbU16 count) {
    FdbU32 i,words;FdbU16 page,offset,r;int admitted;
    if(!before || !after || before->words!=after->words || !ranges_valid(before->words,ranges,count))return 1;
    for(page=0;page<before->pages;page++) {
        words=before->words-(FdbU32)page*FDB16_PAGE_WORDS;if(words>FDB16_PAGE_WORDS)words=FDB16_PAGE_WORDS;
        if(!memcmp(before->data[page],after->data[page],(unsigned int)(words*4UL)))continue;
        for(offset=0;offset<(FdbU16)words;offset++)if(before->data[page][offset]!=after->data[page][offset]) {
            i=(FdbU32)page*FDB16_PAGE_WORDS+offset;admitted=0;
            for(r=0;r<count;r++)if(i>=ranges[r].start && i-ranges[r].start<ranges[r].count){admitted=1;break;}
            if(!admitted)return 1;
        }
    }
    return 0;
}
int fdb16_read32(Fdb16File *stream,FdbU32 *value) {
    unsigned char bytes[4];if(!stream || !value || fdb16_file_read(stream,bytes,4UL))return 1;
    *value=(FdbU32)bytes[0]|((FdbU32)bytes[1]<<8)|((FdbU32)bytes[2]<<16)|((FdbU32)bytes[3]<<24);return 0;
}
int fdb16_write32(Fdb16File *stream,FdbU32 value) {
    unsigned char bytes[4];bytes[0]=(unsigned char)value;bytes[1]=(unsigned char)(value>>8);
    bytes[2]=(unsigned char)(value>>16);bytes[3]=(unsigned char)(value>>24);
    return fdb16_write_bytes(stream,bytes,4UL);
}
int fdb16_write_bytes(Fdb16File *stream,const void *bytes,FdbU32 count) {
    const unsigned char FAR *source;FdbU32 at;unsigned int chunk;
    if(!stream || !stream->writing || stream->failed || (count && !bytes) || count>65520UL)return 1;
    source=(const unsigned char FAR *)bytes;at=0;
    while(at<count) {
        chunk=(unsigned int)(count-at);if(chunk>sizeof(stream->bytes)-stream->used)chunk=sizeof(stream->bytes)-stream->used;
        memcpy(stream->bytes+stream->used,source+(unsigned int)at,chunk);stream->used+=(FdbU16)chunk;at+=chunk;
        if(stream->used==sizeof(stream->bytes) && file_flush(stream))return 1;
    }
    return 0;
}
int fdb16_dump_words(Fdb16File *stream,const Fdb16Arena *arena) {
    FdbU32 i,value;if(!arena)return 1;
    for(i=0;i<arena->words;i++)if(fdb16_read(arena,i,&value) || fdb16_write32(stream,value))return 1;
    return 0;
}
Fdb16Arena *fdb16_load_initial(const char *path,FdbU32 words,FdbU32 expected_crc) {
    Fdb16File *stream;Fdb16Arena *arena;char magic[8];FdbU32 count,i,value,crc,byte;FdbU16 j,bit;int failed;
    if(!path || !words || words>FDB16_SOURCE_WORDS)return NULL;
    stream=fdb16_file_open(path,0);if(!stream)return NULL;
    failed=fdb16_file_read(stream,magic,8UL) || memcmp(magic,"FDBINI1\0",8) || fdb16_read32(stream,&count) || count!=words;
    arena=failed?NULL:fdb16_create(words);if(!arena){fdb16_file_close(stream);return NULL;}
    crc=0xffffffffUL;
    for(i=0;i<words && !failed;i++) {
        if(fdb16_read32(stream,&value) || fdb16_write(arena,i,value)){failed=1;break;}
        for(j=0;j<4;j++) {
            byte=(value>>(8*j))&255UL;crc^=byte;
            for(bit=0;bit<8;bit++)crc=(crc>>1)^((crc&1UL)?0xedb88320UL:0UL);
        }
    }
    if(!failed && (fdb16_file_eof(stream)!=1 || (crc^0xffffffffUL)!=expected_crc))failed=1;
    if(fdb16_file_close(stream))failed=1;
    if(failed){fdb16_release(arena);return NULL;}return arena;
}

static int color(FdbU32 index,unsigned char *out) {
    const Fdb16Config *config;FdbU16 i;config=fdb16_config();
    for(i=0;i<config->color_count;i++)if(config->colors[i].index==index) {
        out[0]=config->colors[i].red;out[1]=config->colors[i].green;out[2]=config->colors[i].blue;out[3]=255;return 0;
    }
    return 1;
}
int fdb16_host_resize(Fdb16Host *host,int width,int height) {
    const Fdb16Config *config;int rw,rh;
    config=fdb16_config();if(!host || width<1 || height<1 || width>4096 || height>4096)return 1;
    if((FdbU32)width*config->height<=(FdbU32)height*config->width) {
        rw=width;rh=(int)((FdbU32)width*config->height/config->width);
    } else {rh=height;rw=(int)((FdbU32)height*config->width/config->height);}
    if(rw<1 || rh<1)return 1;
    host->view_width=width;host->view_height=height;host->rect_width=rw;host->rect_height=rh;
    host->rect_x=(width-rw)/2;host->rect_y=(height-rh)/2;return 0;
}
int fdb16_host_sync(Fdb16Host *host) {
    const Fdb16Config *config;const Fdb16Arena *actual;FdbU32 i,value,pixels;unsigned char rgba[4];
    if(!host || !host->snapshot || !host->indexed || host->closed)return 1;
    config=fdb16_config();actual=fdb16_core_words();
    if(!actual || fdb16_copy(host->snapshot,actual))return 1;
    pixels=(FdbU32)config->width*config->height;
    for(i=0;i<pixels;i++) {
        if(fdb16_read(host->snapshot,config->frame_offset+i,&value) || value>255UL || color(value,rgba))return 1;
        host->indexed[(unsigned int)i]=(unsigned char)value;
    }
    return 0;
}
void fdb16_host_finish(Fdb16Host *host) {
    if(!host || host->closed)return;
    (void)fdb16_host_sync(host);fdb16_core_close();host->closed=1;
}
void fdb16_host_destroy(Fdb16Host *host) {
    if(!host)return;fdb16_host_finish(host);fdb16_release(host->snapshot);locked_free(host->indexed_handle);
    memset(host,0,sizeof(*host));host->closed=1;
}
static int committed(Fdb16Host *host,int status) {
    const Fdb16Config *config;FdbU32 quit;
    if(status){host->committed=0;return 1;}
    host->committed=1;if(fdb16_host_sync(host))return 1;
    config=fdb16_config();if(fdb16_read(host->snapshot,config->quit_index,&quit))return 1;
    if(quit)fdb16_host_finish(host);return 0;
}
int fdb16_host_initialize(Fdb16Host *host,FdbU32 clock) {
    if(!host || host->closed)return 1;
    host->accepted=1;host->committed=0;return committed(host,fdb16_core_initialize(clock&65535UL));
}
int fdb16_host_open(Fdb16Host *host,const char *initial_file,FdbU32 clock) {
    const Fdb16Config *config;FdbU32 pixels;
    if(!host)return 1;memset(host,0,sizeof(*host));host->closed=1;config=fdb16_config();
    if(!config || !config->words || config->words>FDB16_SOURCE_WORDS || !config->width || !config->height ||
       config->width>4096 || config->height>4096 || config->quit_index>=config->words)return 1;
    pixels=(FdbU32)config->width*config->height;
    if(pixels>65520UL || config->frame_offset>config->words || pixels>config->words-config->frame_offset)return 1;
    if(fdb16_core_open(initial_file))return 1;
    host->snapshot=fdb16_create(config->words);
    host->indexed=(unsigned char FAR *)locked_alloc(pixels,&host->indexed_handle);
    if(!host->snapshot || !host->indexed){fdb16_core_close();fdb16_release(host->snapshot);locked_free(host->indexed_handle);memset(host,0,sizeof(*host));host->closed=1;return 1;}
    host->closed=0;host->focused=1;
    if(fdb16_host_resize(host,(int)config->width,(int)config->height) || fdb16_host_initialize(host,clock)) {
        fdb16_host_destroy(host);return 1;
    }
    return 0;
}
static int dispatch(Fdb16Host *host,FdbU32 kind,FdbU32 ascii,FdbU32 scan,FdbU32 clock) {
    if(!host || host->closed)return 1;
    host->accepted=1;host->committed=0;
    return committed(host,fdb16_core_dispatch(kind,ascii,scan,(FdbU32)host->mouse_x,(FdbU32)host->mouse_y,host->buttons,clock&65535UL));
}
int fdb16_host_key(Fdb16Host *host,FdbU16 key,FdbU32 mods,int focused,FdbU32 clock) {
    const Fdb16Config *config;config=fdb16_config();
    if(!host || host->closed || key>=config->key_count || mods>31UL || (focused!=0 && focused!=1))return 1;
    host->accepted=host->committed=0;
    if(!focused || (mods&(FDB_MOD_COMMAND|FDB_MOD_CONTROL|FDB_MOD_OPTION)))return 0;
    return dispatch(host,config->keyboard_kind,config->keys[key].ascii,config->keys[key].scan,clock);
}
int fdb16_host_pointer(Fdb16Host *host,FdbU16 phase,FdbU16 button,int x,int y,FdbU32 clock) {
    const Fdb16Config *config;int inside,old_x,old_y,result;long dx,dy;FdbU32 old_buttons;
    config=fdb16_config();if(!host || host->closed || phase>FDB_POINTER_DRAG || button>2 ||
        (long)x<-32768L || (long)x>32767L || (long)y<-32768L || (long)y>32767L)return 1;
    host->accepted=host->committed=0;
    dx=(long)x-host->rect_x;dy=(long)y-host->rect_y;
    inside=dx>=0 && dy>=0 && dx<host->rect_width && dy<host->rect_height;
    if(!inside && !host->buttons)return 0;
    old_x=host->mouse_x;old_y=host->mouse_y;old_buttons=host->buttons;
    if(dx<0)dx=0;if(dy<0)dy=0;
    if(dx>=host->rect_width)dx=host->rect_width-1;
    if(dy>=host->rect_height)dy=host->rect_height-1;
    host->mouse_x=(int)((2UL*(FdbU32)dx+1UL)*config->width/(2UL*(FdbU32)host->rect_width));
    host->mouse_y=(int)((2UL*(FdbU32)dy+1UL)*config->height/(2UL*(FdbU32)host->rect_height));
    if(phase==FDB_POINTER_DOWN)host->buttons|=1UL<<button;
    if(phase==FDB_POINTER_UP)host->buttons&=~(1UL<<button);
    result=dispatch(host,config->pointer_kind,0UL,0UL,clock);
    if(result){host->mouse_x=old_x;host->mouse_y=old_y;host->buttons=old_buttons;}return result;
}
int fdb16_host_tick(Fdb16Host *host,FdbU32 clock){return dispatch(host,fdb16_config()->clock_kind,0UL,0UL,clock);}
int fdb16_host_select(Fdb16Host *host,FdbU16 slot,FdbU16 variant) {
    const Fdb16Config *config;config=fdb16_config();if(!host || host->closed)return 1;
    host->accepted=host->committed=0;
    if(slot>=config->region_count || variant>=config->regions[slot].count || fdb16_core_select(slot,variant))return 1;
    host->accepted=1;return 0;
}
int fdb16_host_focus(Fdb16Host *host,int focused,FdbU32 clock) {
    FdbU32 old;int result;
    if(!host || host->closed || (focused!=0 && focused!=1))return 1;
    host->accepted=host->committed=0;host->focused=focused;
    if(focused || !host->buttons)return 0;
    old=host->buttons;host->buttons=0;result=dispatch(host,fdb16_config()->pointer_kind,0UL,0UL,clock);
    if(result)host->buttons=old;return result;
}
int fdb16_host_replace(Fdb16Host *host,const Fdb16Arena *prefix) {
    Fdb16Arena *copy;FdbU32 i,count,value;int result;
    if(!host || host->closed || !prefix || fdb16_word_count(prefix)>fdb16_word_count(host->snapshot))return 1;
    copy=fdb16_clone(host->snapshot);if(!copy)return 1;
    count=fdb16_word_count(prefix);
    /* Prefix and full snapshots deliberately have different arena lengths. */
    for(i=0UL;i<count;i++) {
        if(fdb16_read(prefix,i,&value) || fdb16_write(copy,i,value)){fdb16_release(copy);return 1;}
    }
    host->accepted=1;host->committed=0;result=fdb16_core_replace(copy);fdb16_release(copy);return committed(host,result);
}
static int pixel(const Fdb16Host *host,int x,int y,unsigned char *out) {
    const Fdb16Config *config;FdbU32 sx,sy,index;
    if(!host || !host->indexed)return 1;
    if(x<host->rect_x || y<host->rect_y || x-host->rect_x>=host->rect_width || y-host->rect_y>=host->rect_height) {
        out[0]=out[1]=out[2]=0;out[3]=255;return 0;
    }
    config=fdb16_config();sx=(2UL*(FdbU32)(x-host->rect_x)+1UL)*config->width/(2UL*(FdbU32)host->rect_width);
    sy=(2UL*(FdbU32)(y-host->rect_y)+1UL)*config->height/(2UL*(FdbU32)host->rect_height);
    index=sy*config->width+sx;return color((FdbU32)host->indexed[(unsigned int)index],out);
}
int fdb16_host_bgr(Fdb16Host *host,unsigned char *buffer,FdbU16 width,FdbU16 height,FdbU16 top,FdbU16 rows) {
    FdbU32 stride,bytes,at;FdbU16 row,x;unsigned char rgba[4];
    if(!host || !buffer || width!=(FdbU16)host->view_width || height!=(FdbU16)host->view_height || !rows || top>=height || rows>height-top)return 1;
    stride=((FdbU32)width*3UL+3UL)&~3UL;bytes=stride*rows;if(bytes>32760UL)return 1;
    memset(buffer,0,(unsigned int)bytes);
    for(row=0;row<rows;row++)for(x=0;x<width;x++) {
        if(pixel(host,(int)x,(int)(top+row),rgba))return 1;
        at=(FdbU32)(rows-row-1)*stride+(FdbU32)x*3UL;
        buffer[(unsigned int)at]=rgba[2];buffer[(unsigned int)(at+1UL)]=rgba[1];buffer[(unsigned int)(at+2UL)]=rgba[0];
    }
    return 0;
}
int fdb16_host_frame(Fdb16File *stream,const Fdb16Host *host) {
    const Fdb16Config *config;FdbU32 i,pixels;unsigned char chunk[1024],rgba[4];unsigned int used;
    if(!stream || !host || !host->indexed)return 1;
    config=fdb16_config();pixels=(FdbU32)config->width*config->height;used=0;
    for(i=0;i<pixels;i++) {
        if(color((FdbU32)host->indexed[(unsigned int)i],rgba))return 1;
        memcpy(chunk+used,rgba,4);used+=4;
        if(used==sizeof(chunk)){if(fdb16_write_bytes(stream,chunk,(FdbU32)used))return 1;used=0;}
    }
    return used?fdb16_write_bytes(stream,chunk,(FdbU32)used):0;
}
static int write_count(Fdb16File *stream,Fdb16Count value){return fdb16_write32(stream,value.low) || fdb16_write32(stream,value.high);}
static int write_row(Fdb16File *stream,Fdb16Host *host,const Fdb16Command *command,const Fdb16Platform *platform,void *context) {
    const Fdb16Config *config;Fdb16Count revision;FdbU32 fields[12];FdbU16 i,j;
    config=fdb16_config();revision=fdb16_core_revision();
    fields[0]=command->kind;fields[1]=(FdbU32)host->accepted;fields[2]=(FdbU32)host->committed;fields[3]=(FdbU32)host->closed;
    fields[4]=revision.low;fields[5]=revision.high;fields[6]=(FdbU32)host->mouse_x;fields[7]=(FdbU32)host->mouse_y;
    fields[8]=host->buttons;fields[9]=(FdbU32)host->view_width;fields[10]=(FdbU32)host->view_height;fields[11]=command->flags;
    for(i=0;i<12;i++)if(fdb16_write32(stream,fields[i]))return 1;
    for(i=0;i<config->region_count;i++)if(fdb16_write32(stream,(FdbU32)fdb16_core_selected(i)))return 1;
    for(i=0;i<config->function_count;i++)if(write_count(stream,fdb16_core_calls(i)))return 1;
    for(i=0;i<config->region_count;i++)for(j=0;j<config->regions[i].count;j++)if(write_count(stream,fdb16_core_region_calls(i,j)))return 1;
    if(fdb16_dump_words(stream,host->snapshot))return 1;
    if((command->flags&FDB_CAPTURE_FRAME) && fdb16_host_frame(stream,host))return 1;
    if(command->flags&FDB_CAPTURE_VIEW) {
        if(!platform || !platform->capture_view || platform->capture_view(context,stream,(FdbU16)host->view_width,(FdbU16)host->view_height))return 1;
    }
    return 0;
}
static int signed_coordinate(FdbU32 value){return value<=32767UL || value>=0xffff8000UL;}
static int command_fields_valid(const Fdb16Command *command) {
    if(command->kind==FDB_CMD_KEY)return command->a<=65535UL && command->c<=1UL;
    if(command->kind==FDB_CMD_POINTER)return command->a<=3UL && command->b<=2UL && signed_coordinate(command->c) && signed_coordinate(command->d);
    if(command->kind==FDB_CMD_SELECT)return command->a<=65535UL && command->b<=65535UL;
    if(command->kind==FDB_CMD_RESIZE)return command->a<=4096UL && command->b<=4096UL;
    if(command->kind==FDB_CMD_FOCUS)return command->a<=1UL;
    return 1;
}
int fdb16_host_study(Fdb16Host *host,const char *input,const char *output,const Fdb16Platform *platform,void *context) {
    const Fdb16Config *config;Fdb16File *in,*out;FdbU32 header[6],fields[9],row,index,value;
    Fdb16Command command;Fdb16Arena *payload;char magic[8];int failed,status;FdbU16 i;
    config=fdb16_config();if(!host || !input || !output)return 2;
    in=fdb16_file_open(input,0);if(!in)return 2;
    failed=fdb16_file_read(in,magic,8UL) || memcmp(magic,"FDBEVT1\0",8);
    for(i=0;i<6 && !failed;i++)failed=fdb16_read32(in,&header[i]);
    if(failed || header[0]!=config->words || header[1]>4096UL || header[2]>65535UL ||
       header[3]>=config->width || header[4]>=config->height || header[5]>7UL){fdb16_file_close(in);return 2;}
    host->mouse_x=(int)header[3];host->mouse_y=(int)header[4];host->buttons=header[5];
    if(fdb16_host_initialize(host,header[2])){fdb16_file_close(in);return 3;}
    out=fdb16_file_open(output,1);if(!out){fdb16_file_close(in);return 2;}
    failed=fdb16_write_bytes(out,"FDBOUT1\0",8UL) || fdb16_write32(out,config->words) ||
        fdb16_write32(out,header[1]) || fdb16_write32(out,config->region_count) || fdb16_write32(out,config->function_count);
    for(i=0;i<config->region_count && !failed;i++)failed=fdb16_write32(out,config->regions[i].count);
    for(row=0;row<header[1] && !failed;row++) {
        for(i=0;i<9;i++)if(fdb16_read32(in,&fields[i])){failed=1;break;}
        if(failed)break;
        command.kind=fields[0];command.a=fields[1];command.b=fields[2];command.c=fields[3];command.d=fields[4];
        command.e=fields[5];command.clock=fields[6];command.flags=fields[7];command.payload_count=fields[8];
        if(command.kind>FDB_CMD_CALL || command.clock>65535UL || (command.flags&~7UL) || command.payload_count>config->words*2UL ||
           (command.payload_count && command.kind!=FDB_CMD_REPLACE && command.kind!=FDB_CMD_CALL)){failed=1;break;}
        payload=fdb16_create(command.payload_count);if(!payload){failed=1;break;}
        for(index=0;index<command.payload_count;index++)if(fdb16_read32(in,&value) || fdb16_write(payload,index,value)){failed=1;break;}
        if(failed){fdb16_release(payload);break;}
        host->accepted=host->committed=0;status=0;
        if(!command_fields_valid(&command))status=1;
        else switch(command.kind) {
        case FDB_CMD_SNAPSHOT:break;
        case FDB_CMD_REPLACE:status=fdb16_host_replace(host,payload);break;
        case FDB_CMD_INITIALIZE:status=fdb16_host_initialize(host,command.clock);break;
        case FDB_CMD_CLOSE:fdb16_host_finish(host);break;
        case FDB_CMD_CALL:
            if(command.payload_count%2UL || command.b>1UL || command.a>65535UL)status=1;
            else {host->accepted=1;status=committed(host,fdb16_core_call((FdbU16)command.a,payload,command.payload_count/2UL,(int)command.b));}
            break;
        default:status=!platform || !platform->command || platform->command(context,&command,payload);break;
        }
        if(command.flags&FDB_EXPECT_REFUSAL) {
            if(!status)status=1;
            else status=host->closed?0:fdb16_host_sync(host);
        }
        fdb16_release(payload);failed=status;
        if(!failed)failed=write_row(out,host,&command,platform,context);
    }
    if(!failed && fdb16_file_eof(in)!=1)failed=1;
    if(fdb16_file_close(out))failed=1;if(fdb16_file_close(in))failed=1;return failed?3:0;
}

static int token(const char **cursor,char *out) {
    const char *at;unsigned int count;int quoted;
    at=*cursor;while(*at==' ' || *at=='\t')at++;
    if(!*at){*cursor=at;return 0;}
    quoted=*at=='"';if(quoted)at++;count=0;
    while(*at && (quoted?*at!='"':*at!=' ' && *at!='\t')) {
        if(count>=FDB16_PATH_BYTES-1)return -1;out[count++]=*at++;
    }
    if(quoted){if(*at!='"')return -1;at++;if(*at && *at!=' ' && *at!='\t')return -1;}
    if(!count)return -1;out[count]=0;*cursor=at;return 1;
}
int fdb16_arguments(const char *line,char *input,char *output) {
    char mode[FDB16_PATH_BYTES],extra[FDB16_PATH_BYTES];const char *at;int result;
    if(!line || !input || !output)return -1;at=line;result=token(&at,mode);
    if(result==0)return 0;
    if(result<0 || strcmp(mode,"--adapter-test") || token(&at,input)!=1 || token(&at,output)!=1 || token(&at,extra)!=0)return -1;
    return 1;
}
int fdb16_initial_path(HINSTANCE instance,char *out) {
#ifdef FDB16_HOST_TEST
    (void)instance;(void)out;return 1;
#else
    unsigned int length,i,base;if(!out)return 1;
    length=GetModuleFileName(instance,out,FDB16_PATH_BYTES);if(!length || length>=FDB16_PATH_BYTES-1)return 1;
    base=0;for(i=0;i<length;i++)if(out[i]=='\\' || out[i]=='/')base=i+1;
    if(!base || base+sizeof("INITIAL.BIN")>FDB16_PATH_BYTES)return 1;
    strcpy(out+base,"INITIAL.BIN");return 0;
#endif
}
