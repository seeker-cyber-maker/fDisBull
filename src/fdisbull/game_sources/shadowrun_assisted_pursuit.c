/* Source-constructed cooldown-2 arena: scheduler, pursuit and clear movement.
 * The constructor and its relocation are assisted; no captured future position
 * is consulted. Unknown pursuit or collision continuations remain refused. */
u8 shadowrun_arena_pursuit_started;
void shadowrun_arena_pursuit_step(void) {
    shadowrun_arena_supported=0;
    if (shadowrun_arena_moving_profile!=1U || shadowrun_arena_hostile_pose_ready) return;
    if (!shadowrun_arena_pursuit_started) {
        shadowrun_hostile_profile=1;
        shadowrun_hostile_player_x=shadowrun_player_x;shadowrun_hostile_player_y=shadowrun_player_y;
        shadowrun_hostile_tick();
        if (!shadowrun_hostile_supported || !shadowrun_hostile_pursuit_required) return;
        shadowrun_hostile_pursuit_x=shadowrun_hostile_x;shadowrun_hostile_pursuit_y=shadowrun_hostile_y;
        shadowrun_hostile_pursuit_player_x=shadowrun_player_x;shadowrun_hostile_pursuit_player_y=shadowrun_player_y;
        shadowrun_hostile_pursuit_kind=8;shadowrun_hostile_pursuit_flags=5;
        shadowrun_hostile_pursuit_item=10;shadowrun_hostile_pursuit_slot=0;
        shadowrun_hostile_pursuit_ammo=shadowrun_hostile_ammo;shadowrun_hostile_pursuit_alert=1;
        shadowrun_hostile_pursuit_target=0xff0100UL;
        shadowrun_hostile_pursuit_counter=shadowrun_hostile_target_timer;
        shadowrun_hostile_pursuit_tick();
        if (!shadowrun_hostile_pursuit_supported) return;
        shadowrun_ai_x=shadowrun_hostile_x;shadowrun_ai_y=shadowrun_hostile_y;
        shadowrun_ai_target_heading=shadowrun_hostile_pursuit_heading;
        shadowrun_ai_distance=shadowrun_hostile_pursuit_distance;
        shadowrun_ai_callback=shadowrun_hostile_pursuit_callback;
        shadowrun_ai_event_flags=shadowrun_hostile_pursuit_event;
        shadowrun_hostile_move_tick();
        if (!shadowrun_hostile_move_supported) return;
        shadowrun_hostile_pursuit_first_sprite();
        if (!shadowrun_pursuit_route_supported) return;
        shadowrun_ai_flags_low=16;
        shadowrun_pursuit_route_service_timer=shadowrun_hostile_timer;
        shadowrun_pursuit_route_action_timer=shadowrun_hostile_cooldown;
        shadowrun_hostile_pursuit_required=0;shadowrun_arena_pursuit_started=1;
    } else {
        shadowrun_hostile_pursuit_route_step();
        if (!shadowrun_pursuit_route_supported) return;
    }
    shadowrun_hostile_x=shadowrun_ai_x;shadowrun_hostile_y=shadowrun_ai_y;
    shadowrun_target_x[0]=shadowrun_ai_x;shadowrun_target_y[0]=shadowrun_ai_y;
    shadowrun_target_refresh();
    if (!shadowrun_target_supported) return;
    shadowrun_hostile_contact=shadowrun_target_contact[0];
    shadowrun_hostile_timer=shadowrun_pursuit_route_service_timer;
    shadowrun_hostile_cooldown=shadowrun_pursuit_route_action_timer;
    shadowrun_arena_supported=1;
}
