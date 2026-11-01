/* Composition of the reviewed field model with the bounded Stoker request.
 * The external dispatch carry is an explicitly supplied observation, not a
 * recovered implementation of the activity routine. The modal input loop is
 * a target-only projection and does not implement the source dialogue engine. */
void shadowrun_opening_stoker_frame(u8 normalized_pad) {
    if (shadowrun_stoker_ui_mode != 0) {
        shadowrun_input_tick(normalized_pad);
        shadowrun_stoker_ui_tick(normalized_pad);
        if (shadowrun_stoker_ui_mode == 0) {
            /* Observed exit outcome; exact original exit routine is unmodeled. */
            shadowrun_interaction_trigger_busy = 0;
            shadowrun_camera_freeze_c = 0;
            shadowrun_player_event_flags &= 0xdfU;
            shadowrun_interaction_event_latch &= 0xdfU;
            /* Narrow target projection of the observed Stoker exit retreat. */
            shadowrun_player_y = 0x2bc0U;
            shadowrun_player_heading = 0x8000U;
            shadowrun_player_target_heading = 0x8000U;
            /* Observed scene-reentry alignment, projected rather than lifted. */
            shadowrun_camera_x &= 0xff80U;
            shadowrun_camera_y &= 0xff80U;
            shadowrun_camera_scroll_ax = 0;
            shadowrun_camera_scroll_ay = 0;
            shadowrun_camera_scroll_bx = 0;
            shadowrun_camera_scroll_by = 0;
            shadowrun_camera_stream_x = 0xffffU;
            shadowrun_camera_stream_y = 0xffffU;
        }
        shadowrun_opening_status = 6U;
        if (shadowrun_stoker_ui_unsupported) shadowrun_opening_status = 2U;
        return;
    }
    shadowrun_opening_frame(normalized_pad);
    if (shadowrun_opening_status != 3U || shadowrun_unresolved_event != 0xc2U) return;
    shadowrun_interaction_scene_mode = shadowrun_scene_mode;
    shadowrun_interaction_event_mode = shadowrun_event_mode;
    shadowrun_interaction_actor_flags = shadowrun_player_flags;
    shadowrun_interaction_event_latch = shadowrun_player_event_flags;
    shadowrun_interaction_raw_collision = shadowrun_collision_status;
    shadowrun_interaction_corner0 = shadowrun_probe_corners[0];
    shadowrun_interaction_corner1 = shadowrun_probe_corners[1];
    shadowrun_interaction_corner2 = shadowrun_probe_corners[2];
    shadowrun_interaction_corner3 = shadowrun_probe_corners[3];
    shadowrun_request_stoker();
    if (!shadowrun_interaction_requested) return;
    /* The observed contact path commits the collision proposal before camera. */
    shadowrun_player_x = shadowrun_player_proposed_x;
    shadowrun_player_y = shadowrun_player_proposed_y;
    shadowrun_player_event_flags = shadowrun_interaction_event_latch;
    shadowrun_camera_freeze_c = shadowrun_interaction_trigger_busy;
    shadowrun_stoker_ui_begin(normalized_pad);
    shadowrun_camera_player_x = shadowrun_player_x;
    shadowrun_camera_player_y = shadowrun_player_y;
    shadowrun_camera_heading = shadowrun_player_heading;
    shadowrun_camera_tick();
    shadowrun_opening_status = 6U;
}
