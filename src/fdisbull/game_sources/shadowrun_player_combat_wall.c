/* Source northward combat wall stop when both candidate edge corners block.
 * Invoke only immediately after combat_walk refused its proposed step. */
u8 shadowrun_player_combat_wall_supported;
void shadowrun_player_combat_wall_stop(void) {
    shadowrun_player_combat_wall_supported=0;
    if (shadowrun_player_combat_walk_supported || shadowrun_player_kind!=3U ||
        (shadowrun_player_flags&10U)!=10U || shadowrun_player_combat_attribute!=3U ||
        !shadowrun_player_combat_global || (shadowrun_player_equipment_flags&32U) ||
        (shadowrun_player_event_flags&128U) || shadowrun_global_special_mode ||
        (shadowrun_global_vector_flags&1U) || !shadowrun_player_contact ||
        shadowrun_player_heading || shadowrun_player_target_heading ||
        shadowrun_collision_status!=127U || shadowrun_probe_corners[0]!=127U ||
        shadowrun_probe_corners[1]!=127U) return;
    shadowrun_player_collision_movement_state=65535U;
    shadowrun_player_stop();
    shadowrun_player_combat_wall_supported=1;
}
