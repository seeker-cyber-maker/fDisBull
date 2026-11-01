/* Bounded NES audio-service clock. Game/audio event semantics live elsewhere.
 * NMI accrues scheduled slots independently of observed mapper IRQ entries.
 * The IRQ owner catches up old slots; a source request is timestamped so it
 * cannot be advanced through logical ticks preceding its production.
 */
#ifdef FDISBULL_CLOCK_HOST
typedef unsigned char u8;
typedef unsigned short u16;
void audio_request(u8 kind,u8 id);
void audio_tick(void);
#else
#include "game_api.h"
#endif

extern volatile u8 irq_phase;
extern volatile u8 request_kind[16];
extern volatile u8 request_id[16];
extern volatile u8 request_head;
extern volatile u8 request_tail;

volatile u16 request_slot[16];
volatile u16 audio_due_slots;
volatile u16 audio_served_slots;
volatile u16 audio_physical_entries;
volatile u16 audio_catchup_slots;
volatile u16 audio_late_calls;
volatile u16 audio_max_owed;
volatile u16 audio_late_requests;

#define FRAME (*(volatile u16*)0x7D0)
#define DEBUG_MODE (*(volatile u8*)0x7D4)
#define FAULT (*(volatile u8*)0x7ED)

/* phase0: first slot; phase1: second; phase2: next frame's first slot.
 * Reading both words under FRAME validation also handles a NMI crossing a
 * 16-bit access. Mapper IRQ cannot interrupt its own C owner.
 */
u16 audio_clock_limit(u8 producer) {
    u16 frame;
    u16 due;
    u8 phase;
    do {
        frame=FRAME;
        due=audio_due_slots;
        phase=irq_phase;
    } while (frame!=FRAME);
    if (phase==0) return due-1;
    if (producer!=0 && phase>=2) return due+1;
    return due;
}

void emit(u8 kind,u8 id) {
    u8 next;
    if (DEBUG_MODE!=0) {
        *(volatile u16*)0x7EE = *(volatile u16*)0x7EE + 1;
        *(volatile u8*)0x7F4=kind;
        *(volatile u8*)0x7F5=id;
        return;
    }
    next=(u8)((request_head+1)&15);
    if (next==request_tail) {FAULT=3;return;}
    request_kind[request_head]=kind;
    request_id[request_head]=id;
    request_slot[request_head]=audio_clock_limit(1);
    request_head=next;
}

void irq_audio(void) {
    u8 service;
    u8 queued;
    u16 frontier;
    u16 owed;
    u16 candidate;
    u16 target;
    if (DEBUG_MODE!=0) return;
    for (service=0;service<4;service=service+1) {
        frontier=audio_clock_limit(0);
        owed=(u16)(frontier-audio_served_slots);
        if (owed==0 || owed>=32768U) break;
        if (owed>audio_max_owed) audio_max_owed=owed;
        candidate=(u16)(audio_served_slots+1);
        for (queued=0;queued<15;queued=queued+1) {
            if (request_tail==request_head) break;
            target=request_slot[request_tail];
            if ((u16)(candidate-target)>=32768U) break;
            if (target!=candidate) audio_late_requests=audio_late_requests+1;
            audio_request(request_kind[request_tail],request_id[request_tail]);
            request_tail=(u8)((request_tail+1)&15);
        }
        audio_tick();
        audio_served_slots=candidate;
        if (service!=0) audio_catchup_slots=audio_catchup_slots+1;
        if (DEBUG_MODE!=0) break;
    }
    frontier=audio_clock_limit(0);
    owed=(u16)(frontier-audio_served_slots);
    if (owed!=0 && owed<32768U) audio_late_calls=audio_late_calls+1;
}
