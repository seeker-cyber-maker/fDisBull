/* Source held-DOWN admission after stagger with expired action timer. */
u8 shadowrun_reaction_direction_down_supported;
void shadowrun_reaction_resume_direction_down(void) {
    shadowrun_reaction_direction_down_supported=0;
    if (shadowrun_reaction_kind!=3U || shadowrun_reaction_flags!=15U ||
        (shadowrun_reaction_flags_low&254U) || !shadowrun_reaction_hp || !shadowrun_reaction_max_hp ||
        shadowrun_reaction_callback!=0xb07eUL || !(shadowrun_reaction_animation&32768U) ||
        shadowrun_reaction_input_flags!=2U || shadowrun_reaction_input_heading!=0x8000U ||
        shadowrun_reaction_global_e6 || shadowrun_reaction_global_3a ||
        shadowrun_reaction_global_18a || shadowrun_reaction_global_18b ||
        shadowrun_reaction_action_timer!=65535U) return;
    shadowrun_reaction_cursor=0;shadowrun_reaction_target_heading=shadowrun_reaction_input_heading;
    shadowrun_reaction_callback=0xb574UL;shadowrun_reaction_direction_down_supported=1;
}
