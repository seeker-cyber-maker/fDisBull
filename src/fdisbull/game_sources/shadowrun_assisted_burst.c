/* Prepare the source impact animation state after a validated first hit.
 * The caller invokes the first sprite pass separately in source order. */
void shadowrun_arena_burst_prepare(void) {
    u8 impact;
    shadowrun_arena_supported=0;
    if (shadowrun_arena_profile!=1U || (shadowrun_hostile_motion_state!=2U && shadowrun_hostile_motion_state!=5U) ||
        !shadowrun_hostile_motion_continuation_required || shadowrun_play_actor_hp[0]!=10U ||
        (shadowrun_hostile_motion_state==2U && (!shadowrun_player_damage_supported || shadowrun_player_damage_depleted)) ||
        (shadowrun_hostile_motion_state==5U && shadowrun_hostile_motion_effect)) return;
    shadowrun_burst_profile=1;shadowrun_burst_x=shadowrun_hostile_motion_x;
    shadowrun_burst_y=shadowrun_hostile_motion_y;
    shadowrun_burst_origin_x=shadowrun_hostile_projectile_x;shadowrun_burst_origin_y=shadowrun_hostile_projectile_y;
    shadowrun_burst_heading=shadowrun_hostile_heading;
    shadowrun_burst_vx=shadowrun_hostile_motion_vx;shadowrun_burst_vy=shadowrun_hostile_motion_vy;
    shadowrun_burst_rng=shadowrun_hostile_rng;shadowrun_burst_counter=shadowrun_hostile_burst_remaining;
    shadowrun_burst_flags=1;shadowrun_burst_flags_low=9;
    shadowrun_burst_lifetime=shadowrun_hostile_motion_lifetime;shadowrun_burst_effect=shadowrun_hostile_motion_effect;
    shadowrun_burst_shooter_effect=shadowrun_hostile_effect;
    impact=0;if (shadowrun_hostile_motion_state==2U) impact=shadowrun_player_damage_amount;
    shadowrun_burst_anim_word=0;
    if (impact) {shadowrun_burst_anim_word=4;if (impact>=3U) shadowrun_burst_anim_word=12;if (impact>=6U) shadowrun_burst_anim_word=16;}
    shadowrun_burst_anim_increment=0;shadowrun_burst_anim_accumulator=0;
    shadowrun_burst_anim_threshold=4096;shadowrun_burst_anim_index=0;
    shadowrun_arena_burst_active=1;shadowrun_arena_supported=1;
}
void shadowrun_arena_burst_first_sprite(void) {
    shadowrun_arena_supported=0;
    if (!shadowrun_arena_burst_active) return;
    shadowrun_burst_anim_profile=1;shadowrun_burst_anim_flags=shadowrun_burst_flags_low;
    shadowrun_burst_animation_tick();
    if (!shadowrun_burst_anim_supported) return;
    shadowrun_burst_flags_low=shadowrun_burst_anim_flags;shadowrun_arena_supported=1;
}
void shadowrun_arena_burst_step(void) {
    shadowrun_arena_supported=0;
    if (!shadowrun_arena_burst_active || shadowrun_arena_profile!=1U) return;
    shadowrun_burst_rng=shadowrun_hostile_rng;
    shadowrun_hostile_motion_player_x=shadowrun_player_x;shadowrun_hostile_motion_player_y=shadowrun_player_y;
    shadowrun_player_damage_hp=shadowrun_arena_hp;shadowrun_player_damage_armor=shadowrun_arena_armor;
    shadowrun_hostile_cycle_tick();
    if (!shadowrun_hostile_cycle_supported) return;
    shadowrun_hostile_rng=shadowrun_burst_rng;shadowrun_arena_hp=shadowrun_player_damage_hp;
    if (shadowrun_hostile_cycle_reaction==3U) {
        shadowrun_arena_depleted=1;shadowrun_arena_player_ready=0;shadowrun_play_shot_eligible=0;
        shadowrun_arena_supported=1;return;
    }
    if (shadowrun_hostile_cycle_reaction==2U) return;
    if (shadowrun_hostile_cycle_reaction==1U) {
        if (!shadowrun_arena_player_ready || !shadowrun_arena_hp) return;
        shadowrun_arena_player_ready=0;shadowrun_play_shot_eligible=0;
        shadowrun_arena_reaction_begin();if (!shadowrun_reaction_supported) return;
        shadowrun_reaction_sprite_only();if (!shadowrun_reaction_sprite_supported) return;
        shadowrun_arena_player_hit_event=1;
        shadowrun_hostile_cycle_reaction=0;
    }
    if (!(shadowrun_burst_flags&1U)) {
        shadowrun_arena_burst_active=0;
        shadowrun_hostile_motion_state=0;shadowrun_hostile_motion_continuation_required=0;
    }
    shadowrun_arena_supported=1;
}

