/* Other actors are excluded by the assisted setup, not by this hit helper. */
u8 shadowrun_arena_player_domain(void) {
    u8 i;
    if (shadowrun_arena_profile!=1U || !shadowrun_arena_hp || shadowrun_arena_hp>10U ||
        shadowrun_target_selected!=0U || shadowrun_target_flags[0]!=5U ||
        shadowrun_target_flags_b0[0]!=0U || !shadowrun_play_actor_hp[0] ||
        shadowrun_target_x[0]!=shadowrun_hostile_x || shadowrun_target_y[0]!=shadowrun_hostile_y) return 0;
    for (i=1;i<7;i=i+1) if (shadowrun_target_flags[i]&1U) return 0;
    return 1;
}
void shadowrun_arena_player_launch(void) {
    shadowrun_arena_player_supported=0;
    if (!shadowrun_arena_player_domain() || !shadowrun_arena_player_ready || !shadowrun_play_shot_eligible || shadowrun_play_weapon_slot!=0U ||
        shadowrun_play_weapon_item!=2U || !shadowrun_play_ammo ||
        shadowrun_linked_motion_state==1U) return;
    shadowrun_hostile_received_profile=1;shadowrun_hostile_received_kind=8;
    shadowrun_hostile_received_armor=3;shadowrun_linked_profile=1;
    shadowrun_field_captured_profile=1;shadowrun_field_actor_index=0;
    shadowrun_field_item=2;shadowrun_field_equipped_slot=0;shadowrun_field_source_flags=15;
    shadowrun_field_ammo=shadowrun_play_ammo;
    shadowrun_field_slots_busy=0;
    if (shadowrun_arena_burst_active) shadowrun_field_slots_busy=1;
    shadowrun_field_target_flags=5;shadowrun_field_target_flags_b0=0;
    shadowrun_field_target_flags_9e=0;shadowrun_field_target_flags_9a=0;
    shadowrun_field_target_type=2;shadowrun_field_target_defense_bonus=5;
    shadowrun_field_target_a=5;shadowrun_field_target_b=4;shadowrun_field_target_c=3;
    shadowrun_field_target_posture=2;shadowrun_field_target_hp=shadowrun_play_actor_hp[0];
    shadowrun_field_target_x=shadowrun_target_x[0];shadowrun_field_target_y=shadowrun_target_y[0];
    shadowrun_linked_source_x=shadowrun_player_x;shadowrun_linked_source_y=shadowrun_player_y;
    shadowrun_player_attack_hp=shadowrun_arena_hp;
    shadowrun_player_attack_alternate_hp=10;
    shadowrun_player_attack_threshold();
    if (!shadowrun_player_attack_supported) return;
    shadowrun_field_rng=shadowrun_hostile_rng;
    shadowrun_hostile_linked_launch();
    if (!shadowrun_field_supported) return;
    shadowrun_play_ammo=shadowrun_field_ammo;shadowrun_hostile_rng=shadowrun_field_rng;
    shadowrun_play_actor_hp[0]=shadowrun_field_target_hp;
    shadowrun_arena_player_supported=1;
}
void shadowrun_arena_player_step(void) {
    shadowrun_arena_player_supported=0;
    if (!shadowrun_arena_player_domain() || shadowrun_linked_motion_state!=1U ||
        shadowrun_target_x[0]!=shadowrun_field_target_x || shadowrun_target_y[0]!=shadowrun_field_target_y ||
        shadowrun_play_actor_hp[0]!=shadowrun_field_target_hp) return;
    shadowrun_field_rng=shadowrun_hostile_rng;
    shadowrun_hostile_linked_tick();
    if (!shadowrun_field_supported) return;
    shadowrun_hostile_rng=shadowrun_field_rng;shadowrun_play_actor_hp[0]=shadowrun_field_target_hp;
    shadowrun_arena_player_supported=1;
}
