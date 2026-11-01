/* Linked projectile with source-order collision scanning for the three
 * qualified captured actors at $FF0400..$FF0600. Target arrays, HP and the
 * captured player/scene profile are supplied by the caller. */
u8 shadowrun_actors_profile;
u8 shadowrun_actors_hit_slot; /* 0..6, or 255 when no actor was hit */
void shadowrun_actors_load(u16 slot) {
    shadowrun_field_target_x=shadowrun_target_x[slot];shadowrun_field_target_y=shadowrun_target_y[slot];
    shadowrun_field_target_flags=shadowrun_target_flags[slot];shadowrun_field_target_flags_b0=shadowrun_target_flags_b0[slot];
    shadowrun_field_target_flags_9e=0x20U;shadowrun_field_target_flags_9a=0;
    shadowrun_field_target_type=19;shadowrun_field_target_defense_bonus=2;
    shadowrun_field_target_a=1;shadowrun_field_target_b=2;shadowrun_field_target_c=2;shadowrun_field_target_posture=2;
    shadowrun_field_target_hp=shadowrun_play_actor_hp[slot];
}
void shadowrun_actors_tick(void) {
    u16 i;u16 k;u16 px;u16 py;u16 at;u16 flags;u16 old_ammo;u16 old_busy;u16 old_slot;
    u32 nx;u32 ny;u32 delta;
    if (shadowrun_actors_profile!=1 || shadowrun_linked_motion_state!=1 ||
        shadowrun_field_source_flags!=15 || shadowrun_field_item!=2) {shadowrun_field_supported=0;return;}
    shadowrun_field_supported=0;
    /* Captured actor identities, non-wrapping bounds and normal HP; caller
     * attests no earlier eligible party actor and unchanged hidden fields. */
    for(k=0;k<3;k=k+1) {
        if ((shadowrun_target_flags[k]&1U) && shadowrun_play_actor_hp[k]) {
            if (shadowrun_play_actor_hp[k]>127 || shadowrun_target_x[k]<144 || shadowrun_target_x[k]>65391U ||
                shadowrun_target_y[k]<144 || shadowrun_target_y[k]>65391U) return;
        }
    }
    if (shadowrun_field_death_timer>127 || shadowrun_field_type13_deaths>8) return;
    shadowrun_field_supported=1;shadowrun_actors_hit_slot=255;
    for(i=0;i<4;i=i+1) {
        nx=shadowrun_linked_x_fixed;ny=shadowrun_linked_y_fixed;
        if (shadowrun_linked_velocity_x&0x8000U) {
            delta=(u32)(u16)(0U-shadowrun_linked_velocity_x)*256UL;
            if(nx<delta) {shadowrun_field_supported=0;return;}nx-=delta;
        } else {delta=(u32)shadowrun_linked_velocity_x*256UL;nx+=delta;if(nx<shadowrun_linked_x_fixed){shadowrun_field_supported=0;return;}}
        if (shadowrun_linked_velocity_y&0x8000U) {
            delta=(u32)(u16)(0U-shadowrun_linked_velocity_y)*256UL;
            if(ny<delta) {shadowrun_field_supported=0;return;}ny-=delta;
        } else {delta=(u32)shadowrun_linked_velocity_y*256UL;ny+=delta;if(ny<shadowrun_linked_y_fixed){shadowrun_field_supported=0;return;}}
        shadowrun_fixed_x=nx/65536UL;shadowrun_fixed_y=ny/65536UL;px=shadowrun_fixed_x>>4;py=shadowrun_fixed_y>>4;
        if(px>=shadowrun_x_min && px<shadowrun_x_max && py>=shadowrun_y_min && py<shadowrun_y_max) {
            at=(((py<<1)&65472U)+(px>>5));if(at>=2816){shadowrun_field_supported=0;return;}
        }
        shadowrun_probe_flags=9;shadowrun_collision_check();
        if(shadowrun_collision_status!=0 && shadowrun_slope_mode==0) {shadowrun_linked_motion_state=3;shadowrun_field_outcome=6;return;}
        if(shadowrun_linked_motion_lifetime==0) {shadowrun_linked_motion_state=4;shadowrun_field_outcome=7;return;}
        shadowrun_linked_x_fixed=nx;shadowrun_linked_y_fixed=ny;
        shadowrun_linked_motion_steps+=1U;shadowrun_linked_motion_lifetime-=1U;
        shadowrun_field_projectile_x=nx/65536UL;shadowrun_field_projectile_y=ny/65536UL;
        for(k=0;k<7;k=k+1) {
            flags=shadowrun_target_flags[k];
            if((flags&1U) && !(flags&0x58U) && !(shadowrun_target_flags_b0[k]&128U) && shadowrun_play_actor_hp[k]) {
                if (shadowrun_target_x[k]<144 || shadowrun_target_x[k]>65391U ||
                    shadowrun_target_y[k]<144 || shadowrun_target_y[k]>65391U) {shadowrun_field_supported=0;return;}
                if(shadowrun_field_projectile_x>=shadowrun_target_x[k]-144U &&
                   shadowrun_field_projectile_x<shadowrun_target_x[k]+144U &&
                   shadowrun_field_projectile_y>=shadowrun_target_y[k]-144U &&
                   shadowrun_field_projectile_y<shadowrun_target_y[k]+144U) {
                    if(k>=3) {shadowrun_field_supported=0;return;}
                    shadowrun_actors_load(k);shadowrun_actors_hit_slot=k;
                    if(shadowrun_field_source_effect==0) shadowrun_field_outcome=3;
                    else {
                        old_ammo=shadowrun_field_ammo;old_busy=shadowrun_field_slots_busy;old_slot=shadowrun_field_slot;
                        shadowrun_field_ammo=1;shadowrun_field_slots_busy=0;shadowrun_field_fire();
                        shadowrun_field_ammo=old_ammo;shadowrun_field_slots_busy=old_busy;shadowrun_field_slot=old_slot;
                        if(!shadowrun_field_supported)return;
                        shadowrun_play_actor_hp[k]=shadowrun_field_target_hp;
                    }
                    shadowrun_linked_x_fixed=((u32)shadowrun_target_x[k]*65536UL)+(nx&65535UL);
                    shadowrun_linked_y_fixed=((u32)(shadowrun_target_y[k]+16U)*65536UL)+(ny&65535UL);
                    shadowrun_field_projectile_x=shadowrun_target_x[k];shadowrun_field_projectile_y=shadowrun_target_y[k]+16U;
                    shadowrun_linked_motion_state=2;return;
                }
            }
        }
    }
    shadowrun_field_outcome=5;
}
void shadowrun_actors_launch(void) {
    u16 flags;u16 slot;
    shadowrun_field_supported=0;
    if(shadowrun_actors_profile!=1 || shadowrun_linked_profile!=1 || shadowrun_target_selected>=3U)return;
    slot=shadowrun_target_selected;
    if(!(shadowrun_target_flags[slot]&1U) || !shadowrun_play_actor_hp[slot])return;
    shadowrun_actors_load(slot);
    shadowrun_linked_target_x=shadowrun_field_target_x;shadowrun_linked_target_y=shadowrun_field_target_y;
    shadowrun_linked_measure();if(!shadowrun_linked_supported)return;
    shadowrun_spawn_source_x=shadowrun_linked_source_x;shadowrun_spawn_source_y=shadowrun_linked_source_y;
    shadowrun_spawn_heading=shadowrun_linked_heading;shadowrun_linked_spawn();if(!shadowrun_spawn_supported)return;
    flags=shadowrun_field_target_flags;shadowrun_field_target_flags=0;
    shadowrun_field_captured_fire();shadowrun_field_target_flags=flags;
    if(!shadowrun_field_supported || shadowrun_field_outcome!=2)return;
    shadowrun_linked_x_fixed=(u32)shadowrun_spawn_x*65536UL;shadowrun_linked_y_fixed=(u32)shadowrun_spawn_y*65536UL;
    shadowrun_linked_velocity_x=shadowrun_spawn_velocity_x;shadowrun_linked_velocity_y=shadowrun_spawn_velocity_y;
    shadowrun_linked_motion_steps=0;shadowrun_linked_motion_lifetime=127;shadowrun_linked_motion_state=1;
    shadowrun_actors_tick();
}
