/* Bounded source $B574 eastward wall fallback, after failed clear proposal. */
u8 shadowrun_ai_east_slide_supported;
void shadowrun_ai_east_slide(void) {
    u16 heading;u16 delta;u16 x;u16 y;u16 i;u32 table;u16 rotated;
    shadowrun_ai_east_slide_supported=0;
    if (shadowrun_ai_supported || shadowrun_ai_kind!=11U || shadowrun_ai_callback!=0xb574UL ||
        shadowrun_ai_flags!=37U || !(shadowrun_ai_equipment_flags&32U) ||
        (shadowrun_ai_event_flags&128U) || shadowrun_ai_attribute!=1U ||
        shadowrun_ai_combat_global || shadowrun_ai_distance<0x460U ||
        (shadowrun_ai_heading!=0x1900U && shadowrun_ai_heading!=0x1100U && shadowrun_ai_heading!=0x0900U && shadowrun_ai_heading!=0x0500U) ||
        shadowrun_ai_target_heading!=0x0500U || shadowrun_collision_status!=127U) return;
    heading=shadowrun_ai_heading;delta=heading-shadowrun_ai_target_heading;
    if (delta && delta<0x800U) heading=shadowrun_ai_target_heading;else if (delta) heading-=0x800U;
    table=0xbe62UL;x=shadowrun_ai_x+rom16(0,table+8UL);y=shadowrun_ai_y+rom16(0,table+10UL);
    shadowrun_fixed_x=x;shadowrun_fixed_y=y;shadowrun_probe_flags=shadowrun_ai_flags;
    shadowrun_collision_check();if (shadowrun_collision_status) return;
    shadowrun_ai_x=x;shadowrun_ai_y=y;shadowrun_ai_heading=heading;
    shadowrun_ai_transition_heading=0x4000U;shadowrun_ai_flags_low|=4U;
    shadowrun_ai_move_state=1U;shadowrun_ai_collision_state=0U;
    shadowrun_ai_event_flags&=254U;shadowrun_ai_speed=rom16(0,table+4UL);
    for(i=0;i<4U;i+=1U)shadowrun_ai_corners[i]=shadowrun_probe_corners[i];
    rotated=(u16)((shadowrun_ai_transition_heading<<3)|(shadowrun_ai_transition_heading>>13));
    shadowrun_ai_animation=rom16(0,0xc062UL+((rotated&7U)<<1));
    shadowrun_ai_east_slide_supported=1U;
}
