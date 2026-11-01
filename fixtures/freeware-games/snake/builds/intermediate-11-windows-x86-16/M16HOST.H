#ifndef FDISBULL_WIN16_HOST_1
#define FDISBULL_WIN16_HOST_1
#include <windows.h>
#include "M16ABI.H"

typedef struct Fdb16File Fdb16File;
Fdb16File *fdb16_file_open(const char *path,int write_new);
int fdb16_file_read(Fdb16File *file,void *buffer,FdbU32 bytes);
int fdb16_file_eof(Fdb16File *file);
int fdb16_file_close(Fdb16File *file);

typedef struct { FdbU32 low,high; } Fdb16Count;
typedef struct { FdbU32 start,count; } Fdb16Range;
typedef struct { const char *name; FdbU32 ascii,scan; } Fdb16Key;
typedef struct { FdbU32 index; unsigned char red,green,blue; } Fdb16Color;
typedef struct {
    const char *name,*label;
    FdbU16 count,default_index;
    const char *const *names;
    const char *const *labels;
} Fdb16Region;
typedef struct {
    FdbU32 words,frame_offset;
    FdbU16 width,height;
    double tick_ms;
    FdbU32 kind,ascii,scan,x,y,buttons,clock,quit_index;
    FdbU32 keyboard_kind,pointer_kind,clock_kind;
    FdbU16 key_count,color_count,region_count,function_count;
    const Fdb16Key *keys;
    const Fdb16Color *colors;
    const Fdb16Region *regions;
    const char *const *function_names;
    const char *title,*help,*config_sha256;
    FdbU32 initial_crc32;
} Fdb16Config;
typedef struct {
    Fdb16Arena *snapshot;
    HGLOBAL indexed_handle;
    unsigned char FAR *indexed;
    int view_width,view_height,rect_x,rect_y,rect_width,rect_height;
    int mouse_x,mouse_y;
    FdbU32 buttons;
    int focused,closed,accepted,committed;
} Fdb16Host;
typedef struct {
    FdbU32 kind,a,b,c,d,e,clock,flags,payload_count;
} Fdb16Command;
typedef struct {
    int (*command)(void *,const Fdb16Command *,const Fdb16Arena *);
    int (*capture_view)(void *,Fdb16File *,FdbU16,FdbU16);
} Fdb16Platform;

#define FDB_MOD_COMMAND 1UL
#define FDB_MOD_CONTROL 2UL
#define FDB_MOD_OPTION 4UL
#define FDB_MOD_SHIFT 8UL
#define FDB_MOD_CAPS 16UL
#define FDB_POINTER_MOVE 0UL
#define FDB_POINTER_DOWN 1UL
#define FDB_POINTER_UP 2UL
#define FDB_POINTER_DRAG 3UL
#define FDB_CMD_SNAPSHOT 0UL
#define FDB_CMD_KEY 1UL
#define FDB_CMD_POINTER 2UL
#define FDB_CMD_CLOCK 3UL
#define FDB_CMD_SELECT 4UL
#define FDB_CMD_RESIZE 5UL
#define FDB_CMD_REPLACE 6UL
#define FDB_CMD_FOCUS 7UL
#define FDB_CMD_INITIALIZE 8UL
#define FDB_CMD_CLOSE 9UL
#define FDB_CMD_CALL 10UL
#define FDB_CAPTURE_FRAME 1UL
#define FDB_CAPTURE_VIEW 2UL
#define FDB_EXPECT_REFUSAL 4UL

Fdb16Arena *fdb16_create(FdbU32);
Fdb16Arena *fdb16_load_initial(const char *,FdbU32,FdbU32);
int fdb16_equal(const Fdb16Arena *,const Fdb16Arena *);
int fdb16_copy_ranges(Fdb16Arena *,const Fdb16Arena *,const Fdb16Range *,FdbU16);
int fdb16_footprint(const Fdb16Arena *,const Fdb16Arena *,const Fdb16Range *,FdbU16);
int fdb16_dump_words(Fdb16File *,const Fdb16Arena *);
int fdb16_read32(Fdb16File *,FdbU32 *);
int fdb16_write32(Fdb16File *,FdbU32);
int fdb16_write_bytes(Fdb16File *,const void *,FdbU32);
const Fdb16Config *fdb16_config(void);
int fdb16_core_open(const char *initial_file);
const Fdb16Arena *fdb16_core_words(void);
int fdb16_core_call(FdbU16,const Fdb16Arena *,FdbU32,int);
int fdb16_core_initialize(FdbU32);
int fdb16_core_dispatch(FdbU32,FdbU32,FdbU32,FdbU32,FdbU32,FdbU32,FdbU32);
int fdb16_core_replace(const Fdb16Arena *);
int fdb16_core_select(FdbU16,FdbU16);
int fdb16_core_selected(FdbU16);
Fdb16Count fdb16_core_revision(void);
Fdb16Count fdb16_core_calls(FdbU16);
Fdb16Count fdb16_core_region_calls(FdbU16,FdbU16);
const char *fdb16_core_error(void);
void fdb16_core_close(void);

int fdb16_host_open(Fdb16Host *,const char *initial_file,FdbU32);
void fdb16_host_destroy(Fdb16Host *);
void fdb16_host_finish(Fdb16Host *);
int fdb16_host_sync(Fdb16Host *);
int fdb16_host_initialize(Fdb16Host *,FdbU32);
int fdb16_host_key(Fdb16Host *,FdbU16,FdbU32,int,FdbU32);
int fdb16_host_pointer(Fdb16Host *,FdbU16,FdbU16,int,int,FdbU32);
int fdb16_host_tick(Fdb16Host *,FdbU32);
int fdb16_host_select(Fdb16Host *,FdbU16,FdbU16);
int fdb16_host_focus(Fdb16Host *,int,FdbU32);
int fdb16_host_resize(Fdb16Host *,int,int);
int fdb16_host_replace(Fdb16Host *,const Fdb16Arena *);
/* BGR rows are bottom-up within the requested chunk, with DWORD-aligned stride.
 * Buffer size is at most32760 bytes; the caller admits chunks accordingly. */
int fdb16_host_bgr(Fdb16Host *,unsigned char *,FdbU16,FdbU16,FdbU16,FdbU16);
int fdb16_host_frame(Fdb16File *,const Fdb16Host *);
int fdb16_host_study(Fdb16Host *,const char *,const char *,const Fdb16Platform *,void *);
/* Parse only the explicitly selected --adapter-test IN.BIN OUT.BIN form.
 * Returns0 for ordinary play,1 for study,negative for malformed arguments. */
int fdb16_arguments(const char *,char *,char *);
int fdb16_initial_path(HINSTANCE,char *);
#endif
