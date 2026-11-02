/* Shared bounded arena state and source-derived shot transitions. The frame
 * controller composes their admitted scheduling; unsupported states stop. */
u8 shadowrun_arena_profile,shadowrun_arena_hp,shadowrun_arena_armor;
u8 shadowrun_arena_supported,shadowrun_arena_depleted,shadowrun_arena_player_supported,shadowrun_arena_player_ready;
u8 shadowrun_arena_burst_active,shadowrun_arena_player_sprite_current,shadowrun_arena_hostile_pose_ready,shadowrun_arena_player_hit_event;
void shadowrun_arena_reaction_begin(void) {
    shadowrun_reaction_supported=0;
    if (!shadowrun_arena_player_sprite_current) return;
    shadowrun_reaction_kind=shadowrun_player_kind;shadowrun_reaction_flags=shadowrun_player_flags;
    shadowrun_reaction_hp=shadowrun_arena_hp;shadowrun_reaction_max_hp=10;
    shadowrun_reaction_x=shadowrun_player_x;shadowrun_reaction_y=shadowrun_player_y;
    shadowrun_reaction_heading=shadowrun_player_heading;
    shadowrun_reaction_flags_low=shadowrun_player_flags_low;
    shadowrun_reaction_action_timer=shadowrun_play_shot_timer;
    shadowrun_reaction_start();
}
void shadowrun_arena_launch(void) {
    u8 i;
    shadowrun_arena_supported=0;
    if (shadowrun_arena_profile!=1U || !shadowrun_arena_hp || shadowrun_arena_hp>10U || shadowrun_play_actor_hp[0]!=10U ||
        shadowrun_arena_armor>7U || shadowrun_hostile_motion_state==1U ||
        shadowrun_hostile_motion_continuation_required ||
        shadowrun_target_flags[0]!=5U || shadowrun_target_x[0]!=shadowrun_hostile_x || shadowrun_target_y[0]!=shadowrun_hostile_y ||
        (!shadowrun_hostile_timer && shadowrun_hostile_cooldown && shadowrun_hostile_cooldown<32768U)) return;
    for (i=1;i<7;i=i+1) if (shadowrun_target_flags[i]&1U) return;
    shadowrun_hostile_profile=1;
    shadowrun_hostile_player_x=shadowrun_player_x;
    shadowrun_hostile_player_y=shadowrun_player_y;
    shadowrun_hostile_tick();
    if (!shadowrun_hostile_supported || shadowrun_hostile_pursuit_required) return;
    if (shadowrun_hostile_fired) {
        if (shadowrun_target_selected==255U) {
            shadowrun_target_selected=0;shadowrun_target_flags_low[0]|=16U;
            shadowrun_target_marker[0]=0x8009U;shadowrun_target_backlink[0]=1;
            shadowrun_target_player_backlink=1;
        }
        shadowrun_hostile_motion_profile=1;
        shadowrun_hostile_motion_x=(u32)shadowrun_hostile_projectile_x*65536UL;
        shadowrun_hostile_motion_y=(u32)shadowrun_hostile_projectile_y*65536UL;
        shadowrun_hostile_motion_vx=shadowrun_hostile_velocity_x;
        shadowrun_hostile_motion_vy=shadowrun_hostile_velocity_y;
        shadowrun_hostile_motion_lifetime=shadowrun_hostile_lifetime;
        shadowrun_hostile_motion_effect=shadowrun_hostile_effect;
        shadowrun_hostile_motion_steps=0;
        shadowrun_hostile_motion_state=1;
    }
    shadowrun_arena_supported=1;
}
void shadowrun_arena_projectile_step(void) {
    shadowrun_arena_supported=0;
    if (shadowrun_arena_profile!=1U || !shadowrun_arena_hp || shadowrun_arena_hp>10U ||
        shadowrun_arena_armor>7U || shadowrun_hostile_motion_state!=1U) return;
    shadowrun_hostile_motion_player_x=shadowrun_player_x;
    shadowrun_hostile_motion_player_y=shadowrun_player_y;
    shadowrun_hostile_motion_tick();
    if (!shadowrun_hostile_motion_supported) return;
    if (shadowrun_hostile_motion_state==2U) {
        shadowrun_player_damage_profile=1;
        shadowrun_player_damage_item=10;
        shadowrun_player_damage_effect=shadowrun_hostile_motion_effect;
        shadowrun_player_damage_armor=shadowrun_arena_armor;
        shadowrun_player_damage_hp=shadowrun_arena_hp;
        shadowrun_player_damage_rng=shadowrun_hostile_rng;
        shadowrun_player_hit();
        if (!shadowrun_player_damage_supported) return;
        shadowrun_arena_hp=shadowrun_player_damage_hp;
        if (shadowrun_player_damage_amount) {
            shadowrun_arena_player_ready=0;
            shadowrun_play_shot_eligible=0;
            if (shadowrun_arena_hp) {
                shadowrun_arena_reaction_begin();
                if (!shadowrun_reaction_supported) return;
            }
        }
        shadowrun_hostile_rng=shadowrun_player_damage_rng;
        shadowrun_arena_depleted=shadowrun_player_damage_depleted;
    }
    shadowrun_arena_supported=1;
}
/* Qualified only for the assisted source-constructed initial encounter. */
void shadowrun_arena_same_loop(void) {
    shadowrun_arena_launch();
    if (shadowrun_arena_supported && shadowrun_hostile_fired)
        shadowrun_arena_projectile_step();
}
