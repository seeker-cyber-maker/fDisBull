/* Bounded field input-to-step composition. No-button ticks preserve position.
 * Action buttons and unresolved negative events refuse at this layer;
 * the guarded Stoker composition handles one reviewed event separately. */
u8 shadowrun_opening_status;
void shadowrun_opening_tick(u8 normalized_pad) {
    shadowrun_input_tick(normalized_pad);
    shadowrun_opening_status = 0;
    if (normalized_pad & 0xf0U) {
        shadowrun_opening_status = 2;
        return;
    }
    shadowrun_select_direction();
    if (shadowrun_direction_angle == 0xffffU) return;
    shadowrun_probe_flags = shadowrun_player_flags;
    shadowrun_player_walk_bounded();
    if (shadowrun_player_walk_result == 1) shadowrun_opening_status = 1;
    else if (shadowrun_player_walk_result == 2) shadowrun_opening_status = 4;
    else shadowrun_opening_status = 3;
}
