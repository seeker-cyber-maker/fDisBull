/* Direct clear-terrain branch of a reviewed 68000 field-record step.
 * A nonzero collision status selects source paths not modeled here;
 * supported=0 is a refusal, not a claim that the player is blocked. */
u8 shadowrun_walk_supported;
u8 shadowrun_walk_event_flags;
u8 shadowrun_walk_record_corners[4];
u16 shadowrun_walk_movement_state;
void shadowrun_walk_direct(void) {
    u8 i;
    shadowrun_walk_supported = 0;
    shadowrun_propose_move();
    shadowrun_fixed_x = shadowrun_proposed_x;
    shadowrun_fixed_y = shadowrun_proposed_y;
    shadowrun_collision_check();
    for (i = 0; i < 4; i = i + 1)
        shadowrun_walk_record_corners[i] = shadowrun_probe_corners[i];
    if (shadowrun_collision_status != 0) return;
    shadowrun_walk_movement_state = 0x1000U;
    shadowrun_walk_event_flags &= 0xfeU;
    shadowrun_position_x = shadowrun_proposed_x;
    shadowrun_position_y = shadowrun_proposed_y;
    shadowrun_walk_supported = 1;
}
