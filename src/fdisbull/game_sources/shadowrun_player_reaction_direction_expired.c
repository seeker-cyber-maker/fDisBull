/* Source held-LEFT admission after stagger with expired action timer and no
 * queued attack. Movement and the party sprite pass are separate. */
u8 shadowrun_reaction_direction_expired_supported;
void shadowrun_reaction_resume_direction_expired(void) {
    shadowrun_reaction_direction_expired_supported=0;
    if (shadowrun_reaction_kind!=3U || shadowrun_reaction_flags!=15U ||
        (shadowrun_reaction_flags_low&254U) || !shadowrun_reaction_hp || !shadowrun_reaction_max_hp ||
        shadowrun_reaction_callback!=0xb07eUL || !(shadowrun_reaction_animation&32768U) ||
        shadowrun_reaction_input_flags!=4U || shadowrun_reaction_input_heading!=0xc000U ||
        shadowrun_reaction_global_e6 || shadowrun_reaction_global_3a ||
        shadowrun_reaction_global_18a || shadowrun_reaction_global_18b ||
        shadowrun_reaction_action_timer!=65535U) return;
    shadowrun_reaction_cursor=0;shadowrun_reaction_target_heading=0xc000U;
    shadowrun_reaction_callback=0xb574UL;shadowrun_reaction_direction_expired_supported=1;
}
