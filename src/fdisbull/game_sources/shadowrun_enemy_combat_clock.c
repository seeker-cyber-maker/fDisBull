/* Combat-global start $1DBAA and timer/clear $1DE00..$1DE3E.
 * A nonzero tail result requires the caller to execute target processing. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u16 shadowrun_ai_clock_combat,shadowrun_ai_clock_timer,shadowrun_ai_clock_scene;
u32 shadowrun_ai_clock_long_mode;
u8 shadowrun_ai_clock_scene_override,shadowrun_ai_clock_pause1,shadowrun_ai_clock_pause2;
u32 shadowrun_ai_clock_target[10],shadowrun_ai_clock_attacker[10];
u8 shadowrun_ai_clock_selected_value[10],shadowrun_ai_clock_event_flags[10],shadowrun_ai_clock_flags_low[10];
u8 shadowrun_ai_clock_supported,shadowrun_ai_clock_result;
void shadowrun_ai_clock_start(void) {
    shadowrun_ai_clock_supported=1;shadowrun_ai_clock_result=0;
    if (shadowrun_ai_clock_scene==54U && !shadowrun_ai_clock_scene_override) return;
    if (!shadowrun_ai_clock_combat) shadowrun_ai_clock_combat=65535U;
    if (shadowrun_ai_clock_long_mode) shadowrun_ai_clock_timer=600U;
    else shadowrun_ai_clock_timer=120U;
    shadowrun_ai_clock_result=1;
}
void shadowrun_ai_clock_tick(void) {
    u8 i;
    shadowrun_ai_clock_supported=0;shadowrun_ai_clock_result=0;
    if (!shadowrun_ai_clock_combat) {shadowrun_ai_clock_supported=1;return;}
    if (shadowrun_ai_clock_timer>600U) return;
    if (shadowrun_ai_clock_pause1 || shadowrun_ai_clock_pause2 || shadowrun_ai_clock_scene==20U) {
        shadowrun_ai_clock_supported=1;shadowrun_ai_clock_result=1;return;
    }
    if (shadowrun_ai_clock_timer) {
        shadowrun_ai_clock_timer-=1U;
        shadowrun_ai_clock_supported=1;shadowrun_ai_clock_result=1;return;
    }
    shadowrun_ai_clock_timer=65535U;shadowrun_ai_clock_combat=0;
    for(i=0;i<10;i=i+1) {
        shadowrun_ai_clock_target[i]=0;shadowrun_ai_clock_attacker[i]=0;
        shadowrun_ai_clock_selected_value[i]=0;
        shadowrun_ai_clock_event_flags[i] &= 191U;
        shadowrun_ai_clock_flags_low[i] &= 239U;
    }
    shadowrun_ai_clock_supported=1;shadowrun_ai_clock_result=2;
}
