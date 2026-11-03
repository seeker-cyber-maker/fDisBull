/* Source north-wall diagonal westward fallback after failed clear combat walk.
 * Caller invokes immediately after the guarded clear-walk proposal refused. */
u8 shadowrun_player_combat_slide_supported;
void shadowrun_player_combat_slide(void) {
    u16 x;u16 y;u16 i;u32 table;
    shadowrun_player_combat_slide_supported=0;
    if (shadowrun_player_combat_walk_supported || shadowrun_player_kind!=3U ||
        (shadowrun_player_flags&10U)!=10U || shadowrun_player_combat_attribute!=3U ||
        !shadowrun_player_combat_global || (shadowrun_player_equipment_flags&32U) ||
        (shadowrun_player_event_flags&128U) || shadowrun_global_special_mode ||
        (shadowrun_global_vector_flags&1U) || !shadowrun_player_contact ||
        (shadowrun_player_heading!=0U && shadowrun_player_heading!=0xf800U &&
         shadowrun_player_heading!=0xf000U && shadowrun_player_heading!=0xe800U) ||
        shadowrun_player_target_heading!=0xc000U ||
        shadowrun_collision_status!=127U) return;
    table=rom32(0,0xbdf2UL+(u32)shadowrun_player_combat_attribute*4UL);
    x=shadowrun_player_x+rom16(0,table+24UL);y=shadowrun_player_y+rom16(0,table+26UL);
    shadowrun_fixed_x=x;shadowrun_fixed_y=y;shadowrun_probe_flags=shadowrun_player_flags;
    shadowrun_collision_check();if (shadowrun_collision_status) return;
    shadowrun_player_heading-=2048U;shadowrun_player_direction=12U;
    shadowrun_player_transition_heading=0xc000U;shadowrun_player_flags_low|=4U;
    shadowrun_player_move_state=1U;shadowrun_player_collision_movement_state=6U;
    shadowrun_player_step_timer=rom16(0,table+4UL);shadowrun_player_x=x;shadowrun_player_y=y;
    shadowrun_player_proposed_x=x;shadowrun_player_proposed_y=y;shadowrun_player_event_flags &=254U;
    for(i=0;i<4U;i+=1U)shadowrun_player_record_corners[i]=shadowrun_probe_corners[i];
    shadowrun_player_combat_slide_supported=1;
}
