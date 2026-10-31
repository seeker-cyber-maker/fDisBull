/* Native NES hardware boundary. Game semantics live in the procedural UIL.
 * Original game/data are private external inputs; this file is authored glue.
 */
#include "game_api.h"
#include "game_data.h"

void select_data(u8 bank);
u8 rom8(u8 region,u32 offset);
void begin_state(void);
void publish_state(void);
#pragma wrapped-call(push,banked_call,bank)
void debug_dispatch(u8 id);
#pragma wrapped-call(pop)
extern u8 audio_stream_active[2];
extern u8 audio_error;
extern volatile u8 video_ready;
extern volatile u8 render_oam_page;
extern volatile u8 render_phase;
extern volatile u8 irq_phase;
extern volatile u8 active_nt;
extern volatile u8 frame_buttons;
extern volatile u8 request_kind[16];
extern volatile u8 request_id[16];
extern volatile u8 request_head;
extern volatile u8 request_tail;

/* Explicit addresses keep the private verifier independent of linker order. */
#define FRAME (*(volatile u16*)0x7D0)
#define EPOCH (*(volatile u16*)0x7D2)
#define DEBUG_MODE (*(volatile u8*)0x7D4)
#define DEBUG_COMMAND (*(volatile u8*)0x7D5)
#define DEBUG_PROC (*(volatile u8*)0x7D6)
#define HV_COUNT (*(volatile u8*)0x7EA)
#define HV_POSITION (*(volatile u8*)0x7EB)
#define SOUND_INPUT (*(volatile u8*)0x7EC)
#define FAULT (*(volatile u8*)0x7ED)

/* rom8 is the checked native 6502 leaf in nes_game_start.s. */

u16 rom16(u8 region,u32 offset) {
    u16 value;
    value=(u16)rom8(region,offset) << 8;
    return value | rom8(region,offset+1);
}

u32 rom32(u8 region,u32 offset) {
    u32 value;
    value=(u32)rom16(region,offset) << 16;
    return value | rom16(region,offset+2);
}

u8 sound_busy(void) {
    u8 busy;
    busy=DEBUG_MODE != 0 ? SOUND_INPUT : audio_busy();
    *(volatile u8*)0x7FA=busy;
    return busy;
}

u16 hv16(void) {
    u16 value;
    u16 destination;
    u8 at;
    if (DEBUG_MODE != 0) {
        at=HV_POSITION;
        if (HV_COUNT==0) {HV_POSITION=at+1;return 0;}
        if (at>=HV_COUNT || at>=128) { FAULT=4;return 0; }
        value=((u16)*(volatile u8*)(0x7F00U+(u16)at*2))<<8;
        value=value | *(volatile u8*)(0x7F01U+(u16)at*2);
        HV_POSITION=at+1;
        return value;
    }
    /* Declared portable environment adapter, not a Genesis hardware claim. */
    HV_POSITION=HV_POSITION+1;
    value=(u16)(FRAME*262U + EPOCH*17U + (u16)HV_POSITION*31U);
    if (HV_POSITION>32) {FAULT=9;return 0;}
    destination=0x7F00U+(u16)((EPOCH+1)&3)*64U+(u16)(HV_POSITION-1)*2U;
    *(volatile u8*)destination=(u8)(value>>8);
    *(volatile u8*)(destination+1)=(u8)value;
    return value;
}

u32 debug_arg(u8 index) {
    return *(volatile u32*)(0x7D9U+(u16)index*4);
}

u8 audio_stream_byte(u8 track,u16 offset) {
    if (track>=32 || offset>=audio_sizes[track]) { FAULT=5;return 255; }
    select_data(audio_banks[track]);
    return *(const u8*)(0xA000U+audio_starts[track]+offset);
}

u16 audio_stream_size(u8 track) {
    if (track>=32) return 0;
    return audio_sizes[track];
}

u8 audio_instrument_byte(u8 instrument,u8 field) {
    if (instrument>=28 || field>=17) { FAULT=6;return 0; }
    select_data(BANK_INSTRUMENTS);
    return *(const u8*)(0xA000U+OFFSET_INSTRUMENTS+(u16)instrument*17U+field);
}

u16 audio_period(u16 pitch,u8 oscillator) {
    u16 offset;
    u16 period;
    const u8 *address;
    if (pitch>=1536 || oscillator>=4) { FAULT=7;return 2047; }
    offset=(u16)oscillator*3072U+(u16)(pitch*2U);
    select_data(BANK_PERIODS+(u8)(offset>>13));
    address=(const u8*)(0xA000U+(offset & 8191));
    period=address[0];
    return period | ((u16)address[1]<<8);
}

u8 projection_bank(u8 phase) {
    return (u8)(DATA_PROJECTION >> 13)+(phase>>5);
}

const u8 *terrain_pointer(u8 phase) {
    u32 address;
    address=atlas_offsets[phase & 31];
    select_data((u8)(address>>13));
    return (const u8*)(0xA000U+((u16)address & 8191));
}

i8 object_projection(u8 x,u8 y,u8 raft) {
    u8 bank;
    bank=raft ? BANK_RAFTS : BANK_OBJECTS;
    select_data(bank+(x>>5));
    return *(const i8*)(0xA000U+((u16)(x & 31)<<8)+y);
}

u8 ending_projection(u16 offset) {
    if (offset>=12288) return 0;
    select_data(BANK_ENDING+(u8)(offset>>13));
    return *(const u8*)(0xA000U+(offset & 8191));
}

void main(void) {
    u16 previous;
    u16 sampled;
    EPOCH=0;
    FRAME=0;
    FAULT=0;
    game_boot();
    audio_init();
    draw_game();
    previous=FRAME;
    *(volatile u8*)0x2000=0x88;
    *(volatile u8*)0x2001=0x1E;
    for (;;) {
        if (DEBUG_MODE != 0) {
            if (DEBUG_COMMAND != 0) {
                begin_state();
                HV_POSITION=0;
                debug_dispatch(DEBUG_PROC);
                EPOCH=EPOCH+1;
                publish_state();
                DEBUG_COMMAND=0;
            }
            continue;
        }
        if (FRAME==previous) continue;
        if (FAULT != 0 || audio_error != 0) continue;
        do {
            sampled=FRAME;
            input_buttons=frame_buttons;
        } while (sampled!=FRAME);
        previous=sampled;
        *(volatile u16*)0x7F8=sampled;
        begin_state();
        HV_POSITION=0;
        HV_COUNT=0;
        game_frame();
        EPOCH=EPOCH+1;
        publish_state();
        if (actor_capacity_fault != 0) { FAULT=8;continue; }
        if (video_ready==0) draw_game();
    }
}
