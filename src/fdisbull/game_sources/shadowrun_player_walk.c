/* Direct zero-collision branch of the guarded normal-player movement path.
 * A nonzero collision status is refused; the original fallback/event paths
 * are not represented and must not be called a blocked player movement. */
u8 shadowrun_player_walk_supported;
u8 shadowrun_player_event_flags;
u8 shadowrun_player_record_corners[4];
u16 shadowrun_player_collision_movement_state;
void shadowrun_player_walk_direct(void) {
    u8 i;
    shadowrun_player_walk_supported = 0;
    shadowrun_player_propose();
    if (!shadowrun_player_proposal_supported) return;
    shadowrun_fixed_x = shadowrun_player_proposed_x;
    shadowrun_fixed_y = shadowrun_player_proposed_y;
    shadowrun_collision_check();
    for (i = 0; i < 4; i = i + 1)
        shadowrun_player_record_corners[i] = shadowrun_probe_corners[i];
    if (shadowrun_collision_status != 0) return;
    shadowrun_player_collision_movement_state = 0x1000U;
    shadowrun_player_event_flags &= 0xfeU;
    shadowrun_player_x = shadowrun_player_proposed_x;
    shadowrun_player_y = shadowrun_player_proposed_y;
    shadowrun_player_walk_supported = 1;
}
