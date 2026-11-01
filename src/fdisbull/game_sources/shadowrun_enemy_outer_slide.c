/* Source actor prefix on captured civilian east-slide continuation. */
void shadowrun_ai_outer_east_slide_projection(void) {
    u8 low;
    low=shadowrun_ai_outer_flags_low;
    shadowrun_ai_outer_supported=0;shadowrun_ai_outer_schedule=0;shadowrun_ai_outer_b3_unknown=0;
    if (low!=4U || shadowrun_ai_outer_callback!=0xb574UL ||
        shadowrun_ai_outer_animation!=0x28U || !(shadowrun_ai_outer_action_timer&0x8000U)) return;
    shadowrun_ai_outer_flags_low=0;
    shadowrun_ai_outer_movement_projection();
    shadowrun_ai_outer_flags_low=low;
}
