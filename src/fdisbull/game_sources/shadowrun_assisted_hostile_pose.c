void shadowrun_arena_hostile_first_pose(void) {
    shadowrun_arena_hostile_pose_ready=0;
    if (shadowrun_arena_hp!=5U || shadowrun_hostile_ammo!=47U || shadowrun_hostile_timer!=20U ||
        shadowrun_hostile_target_timer!=6U || shadowrun_player_damage_amount!=5U) return;
    shadowrun_attack_profile=1;shadowrun_attack_kind=8;shadowrun_attack_flags=5;shadowrun_attack_flags_low=0;
    shadowrun_attack_hp=10;shadowrun_attack_max_hp=10;shadowrun_attack_item=10;shadowrun_attack_slot=0;
    shadowrun_attack_gear=38;shadowrun_attack_attr_a=5;shadowrun_attack_attr_b=4;shadowrun_attack_speed=65535U;
    shadowrun_attack_x=shadowrun_hostile_x;shadowrun_attack_y=shadowrun_hostile_y;shadowrun_attack_heading=shadowrun_hostile_heading;
    shadowrun_attack_player_x=shadowrun_player_x;shadowrun_attack_player_y=shadowrun_player_y;
    shadowrun_attack_ammo=shadowrun_hostile_ammo;shadowrun_attack_target=0xff0100UL;
    shadowrun_attack_global_de=1;shadowrun_attack_global_e0=0;shadowrun_attack_alert=0;
    shadowrun_attack_service_timer=shadowrun_hostile_timer;shadowrun_attack_counter=shadowrun_hostile_target_timer;
    shadowrun_attack_event=0;shadowrun_attack_threshold=4096;shadowrun_attack_increment=4096;
    if (shadowrun_arena_moving_profile) {
        shadowrun_attack_flags_low=shadowrun_ai_flags_low;shadowrun_attack_speed=shadowrun_ai_speed;
        shadowrun_attack_counter=shadowrun_hostile_pursuit_counter;shadowrun_attack_event=shadowrun_ai_event_flags;
        shadowrun_attack_increment=shadowrun_pursuit_route_sprite_increment;
        shadowrun_attack_accumulator=shadowrun_pursuit_route_sprite_accumulator;
        shadowrun_attack_index=shadowrun_pursuit_route_sprite_index;
    }
    shadowrun_hostile_attack_start();if (!shadowrun_attack_supported) return;
    if (shadowrun_arena_moving_profile) {
        shadowrun_hostile_moving_attack_first();if (!shadowrun_moving_attack_supported) return;
    } else {shadowrun_hostile_attack_first_pass();if (!shadowrun_attack_first_supported) return;}
    shadowrun_attack_flags_low|=16U;shadowrun_arena_hostile_pose_ready=1;
}
/* Bounded source second service from the qualified stationary arena state. */
void shadowrun_arena_hostile_relaunch(void) {
    shadowrun_arena_supported=0;
    if (!shadowrun_arena_hostile_pose_ready || !shadowrun_arena_player_ready ||
        shadowrun_play_actor_hp[0]!=10U || shadowrun_attack_callback!=0xb45cUL ||
        shadowrun_attack_service_timer || shadowrun_attack_action_timer<32768U ||
        shadowrun_arena_burst_active || shadowrun_linked_motion_state==1U) return;
    if (shadowrun_arena_moving_profile) {
        if (shadowrun_player_x!=15168U || shadowrun_player_y!=11322U ||
            shadowrun_hostile_x!=15634U || shadowrun_hostile_y!=11122U) return;
    } else if (shadowrun_player_x!=15584U || shadowrun_player_y!=11210U ||
               shadowrun_hostile_x!=16096U || shadowrun_hostile_y!=11210U) return;
    shadowrun_hostile_timer=shadowrun_attack_service_timer;
    shadowrun_hostile_cooldown=shadowrun_attack_action_timer;
    shadowrun_hostile_target_existing=1;shadowrun_hostile_target_timer=shadowrun_attack_counter;
    shadowrun_arena_launch();
    if (!shadowrun_arena_supported || !shadowrun_hostile_fired) {shadowrun_arena_supported=0;return;}
    shadowrun_arena_projectile_step();
    if (!shadowrun_arena_supported ||
        (shadowrun_hostile_motion_state!=2U && shadowrun_hostile_motion_state!=5U) ||
        (shadowrun_hostile_motion_state==2U && shadowrun_player_damage_amount)) {
        shadowrun_arena_supported=0;return;
    }
    shadowrun_attack_ammo=shadowrun_hostile_ammo;shadowrun_attack_service_timer=shadowrun_hostile_timer;
    shadowrun_attack_heading=shadowrun_hostile_heading;
    shadowrun_hostile_attack_start();if (!shadowrun_attack_supported) {shadowrun_arena_supported=0;return;}
    if (shadowrun_arena_moving_profile) {
        shadowrun_hostile_moving_relaunch_first();
        if (!shadowrun_moving_relaunch_supported) {shadowrun_arena_supported=0;return;}
    } else if (shadowrun_attack_counter) shadowrun_hostile_relaunch_first();
    else shadowrun_hostile_relaunch_zero_counter();
    if (!shadowrun_arena_moving_profile && !shadowrun_attack_relaunch_supported) {shadowrun_arena_supported=0;return;}
    shadowrun_arena_burst_prepare();
    if (shadowrun_arena_supported) shadowrun_arena_burst_first_sprite();
}
