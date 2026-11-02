/* Captured east-slide-to-clear transition, after successful clear actor tick. */
u8 shadowrun_ai_east_slide_exit_supported;
void shadowrun_ai_east_slide_exit(void) {
    u16 rotated;
    shadowrun_ai_east_slide_exit_supported=0;
    if (!shadowrun_ai_supported || shadowrun_ai_kind!=11U || shadowrun_ai_callback!=0xb574UL ||
        shadowrun_ai_flags!=37U || shadowrun_ai_flags_low!=4U ||
        shadowrun_ai_heading!=0x0500U || shadowrun_ai_target_heading!=0x0500U ||
        shadowrun_ai_transition_heading!=0x4000U || shadowrun_collision_status ||
        shadowrun_ai_collision_state!=0x1000U) return;
    shadowrun_ai_flags_low&=251U;
    rotated=(u16)((shadowrun_ai_heading<<3)|(shadowrun_ai_heading>>13));
    shadowrun_ai_animation=rom16(0,0xc062UL+((rotated&7U)<<1));
    shadowrun_ai_east_slide_exit_supported=1;
}
