/* Item-10 projectile lifetime expiry and one source sprite pass. Caller must
 * discard the full attempted frame if this bounded continuation refuses. */
u8 shadowrun_hostile_expiry_supported;
void shadowrun_hostile_expiry_cycle(void) {
    shadowrun_hostile_expiry_supported=0;
    if (!(shadowrun_burst_flags&1U) || (shadowrun_burst_flags_low&8U) ||
        shadowrun_burst_lifetime || shadowrun_burst_effect>1U || shadowrun_hostile_cycle_reaction) return;
    shadowrun_hostile_motion_profile=1;shadowrun_hostile_motion_state=1;
    shadowrun_hostile_motion_x=shadowrun_burst_x;shadowrun_hostile_motion_y=shadowrun_burst_y;
    shadowrun_hostile_motion_vx=shadowrun_burst_vx;shadowrun_hostile_motion_vy=shadowrun_burst_vy;
    shadowrun_hostile_motion_lifetime=shadowrun_burst_lifetime;shadowrun_hostile_motion_effect=shadowrun_burst_effect;
    shadowrun_hostile_motion_tick();
    if (!shadowrun_hostile_motion_supported || shadowrun_hostile_motion_state!=4U) return;
    shadowrun_burst_x=shadowrun_hostile_motion_x;shadowrun_burst_y=shadowrun_hostile_motion_y;
    shadowrun_burst_vx=shadowrun_hostile_motion_vx;shadowrun_burst_vy=shadowrun_hostile_motion_vy;
    shadowrun_burst_lifetime=shadowrun_hostile_motion_lifetime;
    shadowrun_burst_flags_low|=9U;shadowrun_burst_anim_word=0;
    shadowrun_burst_anim_profile=1;shadowrun_burst_anim_flags=shadowrun_burst_flags_low;
    shadowrun_burst_animation_tick();if (!shadowrun_burst_anim_supported) return;
    shadowrun_burst_flags_low=shadowrun_burst_anim_flags;
    shadowrun_hostile_expiry_supported=1;
}
