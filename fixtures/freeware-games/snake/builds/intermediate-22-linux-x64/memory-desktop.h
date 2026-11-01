#ifndef FDISBULL_MEMORY_DESKTOP_1
#define FDISBULL_MEMORY_DESKTOP_1
#include <stddef.h>
#include <stdint.h>
#include "memory-runtime.h"

typedef struct { const char *name; uint32_t ascii, scan; } FdbHostKey;
typedef struct {
    const char *name, *label;
    uint32_t count, default_index;
    const char *const *names, *const *labels;
} FdbHostRegion;
typedef struct { uint32_t index; uint8_t red, green, blue; } FdbHostColor;
typedef struct {
    uint32_t words, width, height, frame_offset;
    double tick_ms;
    uint32_t kind, ascii, scan, x, y, buttons, clock, quit_index;
    uint32_t keyboard_kind, pointer_kind, clock_kind;
    uint32_t key_count, color_count, region_count, function_count;
    const FdbHostKey *keys;
    const FdbHostColor *colors;
    const FdbHostRegion *regions;
    const char *const *function_names;
    const char *title, *help, *config_sha256;
} FdbHostConfig;
typedef struct {
    uint32_t *words;
    uint8_t *rgba;
    int view_width, view_height, rect_x, rect_y, rect_width, rect_height;
    int mouse_x, mouse_y;
    uint32_t buttons;
    int focused, closed, accepted, committed;
} FdbHost;

enum { FDB_MOD_COMMAND=1, FDB_MOD_CONTROL=2, FDB_MOD_OPTION=4,
       FDB_MOD_SHIFT=8, FDB_MOD_CAPS=16 };
enum { FDB_POINTER_MOVE=0, FDB_POINTER_DOWN=1, FDB_POINTER_UP=2,
       FDB_POINTER_DRAG=3 };
enum { FDB_CMD_SNAPSHOT=0, FDB_CMD_KEY=1, FDB_CMD_POINTER=2,
       FDB_CMD_CLOCK=3, FDB_CMD_SELECT=4, FDB_CMD_RESIZE=5,
       FDB_CMD_REPLACE=6, FDB_CMD_FOCUS=7, FDB_CMD_INITIALIZE=8,
       FDB_CMD_CLOSE=9, FDB_CMD_CALL=10 };
enum { FDB_CAPTURE_FRAME=1, FDB_CAPTURE_VIEW=2, FDB_EXPECT_REFUSAL=4 };
/* Nine little-endian u32 fields, followed by payload_count little-endian u32s.
 * KEY: a=key index,b=modifiers,c=focused. POINTER: a=phase,b=button,c/d=signed
 * view x/y. SELECT:a=slot,b=variant. RESIZE:a/b=width/height. REPLACE:prefix
 * payload. FOCUS:a=focused. CALL:a=function index,b=render,payload=index/value
 * pairs. clock is an explicit low16 service value for every event.
 */
typedef struct {
    uint32_t kind, a, b, c, d, e, clock, flags, payload_count;
} FdbHostCommand;
typedef struct {
    int (*command)(void *, const FdbHostCommand *, const uint32_t *);
    int (*capture_view)(void *, uint8_t *, uint32_t, uint32_t);
} FdbHostPlatform;

const FdbHostConfig *fdb_host_config(void);
int fdb_host_open(FdbHost *, uint32_t clock);
int fdb_host_initialize(FdbHost *, uint32_t clock);
int fdb_host_key(FdbHost *, uint32_t key_index, uint32_t modifiers,
                 int focused, uint32_t clock);
int fdb_host_pointer(FdbHost *, uint32_t phase, uint32_t button,
                     int view_x, int view_y, uint32_t clock);
int fdb_host_tick(FdbHost *, uint32_t clock);
int fdb_host_select(FdbHost *, uint32_t slot, uint32_t variant);
int fdb_host_focus(FdbHost *, int focused, uint32_t clock);
int fdb_host_resize(FdbHost *, int width, int height);
int fdb_host_replace_prefix(FdbHost *, const uint32_t *, size_t);
int fdb_host_sync(FdbHost *);
/* Render exact opaque RGBA into the requested viewport using the same fitted
 * integer rectangle as pointer conversion. Source pixel selection is floor of
 * pixel-center/source mapping, computed with integer arithmetic. */
int fdb_host_render(FdbHost *, uint8_t *, uint32_t width, uint32_t height);
void fdb_host_finish(FdbHost *);
void fdb_host_destroy(FdbHost *);
/* Binary input: "FDBEVT1\0", words,count,clock,x,y,buttons u32, then commands.
 * Output: "FDBOUT1\0",words,count,region_count,function_count u32, then region
 * variant counts. Each row has kind,accepted,
 * committed,closed,revision_low,revision_high,mouse_x,mouse_y,buttons,width,
 * height,flags u32, selected i32[region_count], function invocation counts u64,
 * per-region variant invocation counts u64, words u32[words], then optional
 * intrinsic RGBA and platform-captured view RGBA. No partial row is a result.
 * Snapshot pixels come from owned state or owned offscreen native surfaces.
 */
int fdb_host_study(FdbHost *, const char *input, const char *output,
                   const FdbHostPlatform *, void *platform_context);
#endif
