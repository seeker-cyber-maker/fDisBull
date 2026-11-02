/* Captured actor-loop prefix $A8FA..$AA70. This does not run the later
 * actor-actor collision pass $EB92 or the actor callback. D0 must be the
 * original live register at this actor's entry, not a synthesized value. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u8 shadowrun_ai_outer_flags, shadowrun_ai_outer_flags_low;
u8 shadowrun_ai_outer_hp, shadowrun_ai_outer_max_hp;
u8 shadowrun_ai_outer_selected_value, shadowrun_ai_outer_d0, shadowrun_ai_outer_d0_valid;
u16 shadowrun_ai_outer_kind, shadowrun_ai_outer_animation, shadowrun_ai_outer_action_timer;
u32 shadowrun_ai_outer_callback;
u8 shadowrun_ai_outer_supported, shadowrun_ai_outer_schedule;
void shadowrun_ai_outer_prepare(void) {
    u16 timer;
    shadowrun_ai_outer_supported=0; shadowrun_ai_outer_schedule=0;
    if (shadowrun_ai_outer_kind!=11U || shadowrun_ai_outer_flags!=37U ||
        !shadowrun_ai_outer_hp || !shadowrun_ai_outer_max_hp ||
        (shadowrun_ai_outer_flags_low & 6U) ||
        (shadowrun_ai_outer_animation & 32768U) ||
        (shadowrun_ai_outer_callback!=0xb574UL && shadowrun_ai_outer_callback!=0xb45cUL) ||
        ((shadowrun_ai_outer_flags_low & 16U) && !shadowrun_ai_outer_d0_valid)) return;
    timer=shadowrun_ai_outer_action_timer;
    if (!(timer & 32768U)) timer-=1U;
    shadowrun_ai_outer_action_timer=timer;
    if (shadowrun_ai_outer_flags_low & 16U) shadowrun_ai_outer_selected_value=shadowrun_ai_outer_d0;
    if (shadowrun_ai_outer_animation<=60U) shadowrun_ai_outer_schedule=1;
    shadowrun_ai_outer_supported=1;
}
