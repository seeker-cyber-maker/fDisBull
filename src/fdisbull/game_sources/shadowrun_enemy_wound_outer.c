/* Wounded actor-loop movement projection, $A8FA..$AA70. As in the calm
 * projection, selected +B3 is unknown because inherited D0 is unavailable. */
void shadowrun_ai_outer_wounded_projection(void) {
    u16 timer;
    shadowrun_ai_outer_supported=0;shadowrun_ai_outer_schedule=0;shadowrun_ai_outer_b3_unknown=0;
    if (shadowrun_ai_outer_kind!=11U || shadowrun_ai_outer_flags!=37U ||
        !shadowrun_ai_outer_hp || !shadowrun_ai_outer_max_hp ||
        (shadowrun_ai_outer_flags_low & 6U) || shadowrun_ai_outer_callback!=0xb07eUL ||
        (shadowrun_ai_outer_animation!=0x7cU && shadowrun_ai_outer_animation!=0x807cU)) return;
    timer=shadowrun_ai_outer_action_timer;
    if (!(timer & 32768U)) timer-=1U;
    shadowrun_ai_outer_action_timer=timer;
    if (shadowrun_ai_outer_flags_low & 16U) shadowrun_ai_outer_b3_unknown=1;
    if (shadowrun_ai_outer_animation & 32768U) shadowrun_ai_outer_schedule=1;
    shadowrun_ai_outer_supported=1;
}
