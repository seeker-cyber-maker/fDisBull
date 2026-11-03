/* Authored Genesis hardware boundary. Game rules are compiled from GameIL. */
#include "game_api.h"

typedef char require_int16[(sizeof(int)==2)?1:-1];
typedef char require_long32[(sizeof(long)==4)?1:-1];
typedef char require_ptr32[(sizeof(void*)==4)?1:-1];
extern const u8 genesis_source_rom[524288UL];
extern void genesis_renderer_init(void);
extern void genesis_render_stage(void);
extern void genesis_present(void);
extern void genesis_enable_interrupts(void);
extern void genesis_debug_dispatch(void);
extern void genesis_publish_state(void);
extern volatile u8 genesis_frame_buttons;
volatile u8 genesis_frame_buttons;
volatile u16 genesis_render_epoch;

#define FRAME (*(volatile u16*)0xff1f00UL)
#define EPOCH (*(volatile u16*)0xff1f02UL)
#define DEBUG_MODE (*(volatile u8*)0xff1f04UL)
#define DEBUG_COMMAND (*(volatile u8*)0xff1f05UL)
#define HV_COUNT (*(volatile u8*)0xff1f1cUL)
#define HV_POSITION (*(volatile u8*)0xff1f1dUL)
#define SOUND_INPUT (*(volatile u8*)0xff1f1eUL)
#define FAULT (*(volatile u8*)0xff1f1fUL)
#define EVENT_COUNT (*(volatile u16*)0xff1f20UL)
#define EVENT_KIND (*(volatile u8*)0xff1f22UL)
#define EVENT_ID (*(volatile u8*)0xff1f23UL)
#define LAST_SOUND (*(volatile u8*)0xff1f24UL)
#define INPUT_FRAME (*(volatile u16*)0xff1f26UL)
#define HV_TAPE ((volatile u16*)0xff1e00UL)
#define VDP_CTRL (*(volatile u16*)0xc00004UL)
#define VDP_DATA (*(volatile u16*)0xc00000UL)

void *memcpy(void *d,const void *s,unsigned long n) {
    u8 *a=(u8*)d;const u8 *b=(const u8*)s;
    while(n!=0){*a++=*b++;n--;}return d;
}
void *memset(void *d,int c,unsigned long n) {
    u8 *a=(u8*)d;while(n!=0){*a++=(u8)c;n--;}return d;
}

u8 rom8(u8 region,u32 offset) {
    if(region!=0 || offset>=524288UL){FAULT=1;return 0;}
    return genesis_source_rom[offset];
}
u16 rom16(u8 region,u32 offset) {
    return ((u16)rom8(region,offset)<<8)|rom8(region,offset+1);
}
u32 rom32(u8 region,u32 offset) {
    return ((u32)rom16(region,offset)<<16)|rom16(region,offset+2);
}
u16 hv16(void) {
    u16 value;
    u8 at=HV_POSITION;
    if(DEBUG_MODE!=0) {
        if(HV_COUNT==0){HV_POSITION=at+1;return 0;}
        if(at>=HV_COUNT || at>=32){FAULT=4;return 0;}
        value=HV_TAPE[at];
    } else {
        if(at>=32){FAULT=9;return 0;}
        value=*(volatile u16*)0xc00008UL;
        HV_TAPE[at]=value;
    }
    HV_POSITION=at+1;
    return value;
}
u8 sound_busy(void) {
    u8 value=DEBUG_MODE!=0?SOUND_INPUT:audio_busy();
    LAST_SOUND=value;
    return value;
}
void emit(u8 kind,u8 id) {
    EVENT_COUNT++;
    EVENT_KIND=kind;EVENT_ID=id;
    if(DEBUG_MODE==0)audio_request(kind,id);
}

/* Normalized input ABI matches GameIL: right,left,up,down,A,B,Start,C.
 * C occupies the same bit as the NES adapter's Select button. */
static u8 read_pad(void) {
    u8 high,low,buttons=0;
    *(volatile u8*)0xa10003UL=0x40;
    __asm__ volatile("nop\n\tnop\n\tnop" ::: "memory");
    high=*(volatile u8*)0xa10003UL;
    *(volatile u8*)0xa10003UL=0;
    __asm__ volatile("nop\n\tnop\n\tnop" ::: "memory");
    low=*(volatile u8*)0xa10003UL;
    *(volatile u8*)0xa10003UL=0x40;
    if(!(high&8))buttons|=1;
    if(!(high&4))buttons|=2;
    if(!(high&1))buttons|=4;
    if(!(high&2))buttons|=8;
    if(!(low&16))buttons|=16;
    if(!(high&16))buttons|=32;
    if(!(low&32))buttons|=64;
    if(!(high&32))buttons|=128;
    return buttons;
}
void genesis_vblank_c(void) {
    (void)VDP_CTRL;
    FRAME++;
    genesis_frame_buttons=read_pad();
}
static void wait_frame(void) {
    u16 frame=FRAME;
    while(FRAME==frame){}
}
static void hardware_init(void) {
    u16 i;
    static const u16 registers[19]={
        0x8004,0x8104,0x8230,0x833c,0x8407,0x8568,0x8600,
        0x8700,0x8800,0x8900,0x8a00,0x8b00,0x8c81,0x8d3f,
        0x8e00,0x8f02,0x9001,0x9100,0x9200};
    if((*(volatile u8*)0xa10001UL&15)!=0)
        *(volatile u32*)0xa14000UL=0x53454741UL;
    *(volatile u8*)0xa10009UL=0x40;
    *(volatile u8*)0xa10003UL=0x40;
    for(i=0;i<19;i++)VDP_CTRL=registers[i];
    *(volatile u32*)0xc00004UL=0x40000000UL;
    for(i=0;i<32768U;i++)VDP_DATA=0;
}
void genesis_main(void) {
    u16 previous,sampled;
    u8 buttons;
    hardware_init();
    genesis_renderer_init();
    audio_init();
    game_boot();
    genesis_render_stage();
    genesis_present();
    VDP_CTRL=0x8174;
    genesis_enable_interrupts();
    previous=FRAME;
    for(;;) {
        if(DEBUG_MODE!=0) {
            if(DEBUG_COMMAND!=0) {
                EVENT_COUNT=0;HV_POSITION=0;FAULT=0;
                genesis_debug_dispatch();
                EPOCH++;
                DEBUG_COMMAND=0;
            }
            continue;
        }
        do{sampled=FRAME;buttons=genesis_frame_buttons;}while(sampled!=FRAME);
        if(sampled==previous)continue;
        previous=sampled;INPUT_FRAME=sampled;
        input_buttons=buttons;HV_POSITION=0;EVENT_COUNT=0;LAST_SOUND=0;
        game_frame();EPOCH++;genesis_publish_state();
        genesis_render_epoch=EPOCH;genesis_render_stage();
        wait_frame();genesis_present();
    }
}
