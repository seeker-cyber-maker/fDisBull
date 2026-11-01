/* One caller-scheduled original actor pass followed by one sprite pass for
 * an item-10 hostile projectile. Compose with the separately qualified burst,
 * flight, animation and player-damage leaves. A failed composition must be
 * discarded transactionally by the caller. */
u8 shadowrun_hostile_cycle_supported;
u8 shadowrun_hostile_cycle_reaction; /* 0 none, 1 player, 2 shooter, 3 terminal player hit */
void shadowrun_hostile_cycle_apply(void) {
    u8 impact;u8 prior_hp;
    shadowrun_hostile_cycle_supported=0;
    if (shadowrun_hostile_cycle_reaction) return;
    if (!(shadowrun_burst_flags&1U)) {shadowrun_hostile_cycle_supported=1;return;}
    if (shadowrun_burst_flags_low&8U) {
        /* Burst attack-roll profile was qualified with an unhurt shooter. */
        if ((shadowrun_burst_anim_word&32768U) && shadowrun_burst_counter &&
            shadowrun_play_actor_hp[0]!=10U) return;
        shadowrun_burst_animation=shadowrun_burst_anim_word;
        shadowrun_burst_tick();if (!shadowrun_burst_supported) return;
        if (!(shadowrun_burst_flags&1U)) {shadowrun_hostile_cycle_supported=1;return;}
        if (!shadowrun_burst_waiting) {
            shadowrun_burst_anim_word=shadowrun_burst_animation;
            shadowrun_burst_anim_increment=0;shadowrun_burst_anim_index=0;
            shadowrun_hostile_motion_continuation_required=0;
        }
    } else {
        shadowrun_hostile_motion_profile=1;shadowrun_hostile_motion_state=1;
        shadowrun_hostile_motion_x=shadowrun_burst_x;shadowrun_hostile_motion_y=shadowrun_burst_y;
        shadowrun_hostile_motion_vx=shadowrun_burst_vx;shadowrun_hostile_motion_vy=shadowrun_burst_vy;
        shadowrun_hostile_motion_lifetime=shadowrun_burst_lifetime;
        shadowrun_hostile_motion_effect=shadowrun_burst_effect;
        shadowrun_hostile_motion_tick();if (!shadowrun_hostile_motion_supported) return;
        /* Boundary and solid impact have different active-flag effects. The
         * wider terrain/impact continuation is left to a separate adapter. */
        if (shadowrun_hostile_motion_state==3U || shadowrun_hostile_motion_state==4U) return;
        shadowrun_burst_x=shadowrun_hostile_motion_x;shadowrun_burst_y=shadowrun_hostile_motion_y;
        shadowrun_burst_vx=shadowrun_hostile_motion_vx;shadowrun_burst_vy=shadowrun_hostile_motion_vy;
        shadowrun_burst_lifetime=shadowrun_hostile_motion_lifetime;
        if (shadowrun_hostile_motion_state==2U || shadowrun_hostile_motion_state==5U ||
            shadowrun_hostile_motion_state==6U || shadowrun_hostile_motion_state==7U) {
            shadowrun_burst_flags_low|=9U;shadowrun_burst_anim_word=0;impact=0;
            if (shadowrun_hostile_motion_state==2U) {
                shadowrun_player_damage_profile=1;shadowrun_player_damage_item=10;
                shadowrun_player_damage_effect=shadowrun_burst_effect;
                shadowrun_player_damage_rng=shadowrun_burst_rng;shadowrun_player_hit();
                if (!shadowrun_player_damage_supported) return;
                shadowrun_burst_rng=shadowrun_player_damage_rng;
                /* Stop at the confirmed HP/RNG boundary. Death animation,
                 * other source effects, and later projectile state remain
                 * unknown; the caller must present a terminal state. */
                if (shadowrun_player_damage_depleted) {
                    shadowrun_hostile_cycle_reaction=3U;
                    shadowrun_hostile_cycle_supported=1;
                    return;
                }
                impact=shadowrun_player_damage_amount;
                if (impact) {
                    shadowrun_hostile_cycle_reaction=1;
                    shadowrun_burst_anim_word=4U;
                    if (impact>=3U) shadowrun_burst_anim_word=12U;
                    if (impact>=6U) shadowrun_burst_anim_word=16U;
                }
            } else if (shadowrun_hostile_motion_state==6U) {
                prior_hp=shadowrun_play_actor_hp[0];shadowrun_selfhit_profile=1;
                shadowrun_selfhit_hp=prior_hp;shadowrun_selfhit_effect=shadowrun_burst_effect;
                shadowrun_selfhit_rng=shadowrun_burst_rng;shadowrun_hostile_self_hit();
                if (!shadowrun_selfhit_supported || shadowrun_selfhit_depleted) return;
                shadowrun_play_actor_hp[0]=shadowrun_selfhit_hp;shadowrun_burst_rng=shadowrun_selfhit_rng;
                impact=prior_hp-shadowrun_selfhit_hp;
                if (impact) {
                    shadowrun_hostile_cycle_reaction=2;
                    shadowrun_burst_anim_word=4U;
                    if (impact>=3U) shadowrun_burst_anim_word=12U;
                    if (impact>=6U) shadowrun_burst_anim_word=16U;
                }
            }
        }
    }
    shadowrun_burst_anim_profile=1;shadowrun_burst_anim_flags=shadowrun_burst_flags_low;
    shadowrun_burst_animation_tick();if (!shadowrun_burst_anim_supported) return;
    shadowrun_burst_flags_low=shadowrun_burst_anim_flags;
    shadowrun_hostile_cycle_supported=1;
}
