/* Observation-backed ordering: move the player first, then update the normal
 * follow camera. Unknown action/event paths do not advance the camera here. */
void shadowrun_opening_frame(u8 normalized_pad) {
    shadowrun_opening_tick(normalized_pad);
    if (shadowrun_opening_status == 2U || shadowrun_opening_status == 3U) return;
    shadowrun_camera_player_x = shadowrun_player_x;
    shadowrun_camera_player_y = shadowrun_player_y;
    shadowrun_camera_heading = shadowrun_player_heading;
    shadowrun_camera_tick();
}
