/* Clear player movement during combat, source B574 table selection.
 * Requires the captured party attribute/equipment/event branch; fallback,
 * special vector handling and zero-contact behavior remain separate. */
u8 shadowrun_player_combat_attribute,shadowrun_player_combat_walk_supported;
u16 shadowrun_player_combat_global;
void shadowrun_player_combat_walk(void) {
    u16 delta;u16 heading;u16 rotated;u16 ordinal;u16 offset;u16 x;u16 y;u16 i;u32 table;
    shadowrun_player_combat_walk_supported=0;
    if (shadowrun_player_kind!=3U || (shadowrun_player_flags & 10U)!=10U ||
        (shadowrun_global_vector_flags & 1U) || (shadowrun_player_equipment_flags & 32U) ||
        (shadowrun_player_event_flags & 128U) || shadowrun_global_special_mode ||
        !shadowrun_player_contact || !shadowrun_player_combat_global || shadowrun_player_combat_attribute!=3U) return;
    heading=shadowrun_player_heading;delta=heading-shadowrun_player_target_heading;
    if (delta & 32768U) {if (delta<63488U) heading+=2048U;else heading=shadowrun_player_target_heading;}
    else if (delta) {if (delta<2048U) heading=shadowrun_player_target_heading;else heading-=2048U;}
    rotated=(u16)((heading<<3)|(heading>>13));ordinal=rotated&7U;offset=ordinal<<2;
    table=rom32(0,0xbdf2UL+(u32)shadowrun_player_combat_attribute*4UL);
    x=shadowrun_player_x+rom16(0,table+offset);y=shadowrun_player_y+rom16(0,table+offset+2UL);
    shadowrun_fixed_x=x;shadowrun_fixed_y=y;shadowrun_probe_flags=shadowrun_player_flags;
    shadowrun_collision_check();if (shadowrun_collision_status) return;
    shadowrun_player_heading=heading;shadowrun_player_move_state=1U;
    shadowrun_player_step_timer=rom16(0,table+4UL);shadowrun_player_direction=ordinal<<1;
    shadowrun_player_proposed_x=x;shadowrun_player_proposed_y=y;
    shadowrun_player_x=x;shadowrun_player_y=y;shadowrun_player_collision_movement_state=4096U;
    shadowrun_player_event_flags &= 254U;
    for(i=0;i<4U;i+=1U)shadowrun_player_record_corners[i]=shadowrun_probe_corners[i];
    shadowrun_player_combat_walk_supported=1;
}
