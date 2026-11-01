/* Prepared hostile projectile trajectory and impact projection. */
void shadowrun_hostile_linked_tick(void) {
    u16 i;u16 px;u16 py;u16 at;u16 old_ammo;u16 old_busy;u16 old_slot;u16 old_outcome;
    u32 nx;u32 ny;u32 delta;
    if (shadowrun_linked_profile != 1 || shadowrun_linked_motion_state != 1) {shadowrun_field_supported=0;return;}
    if (shadowrun_hostile_received_profile!=1 || shadowrun_hostile_received_kind!=8U ||
        shadowrun_hostile_received_armor!=3U || shadowrun_field_actor_index!=0U ||
        shadowrun_field_item!=2U || shadowrun_field_equipped_slot!=0U || shadowrun_field_source_flags!=15U ||
        shadowrun_field_target_flags!=5U || shadowrun_field_target_flags_9e!=0U ||
        shadowrun_field_target_flags_9a>128U || shadowrun_field_target_type!=2U ||
        shadowrun_field_target_defense_bonus!=5U || shadowrun_field_target_a!=5U ||
        shadowrun_field_target_b!=4U || shadowrun_field_target_c!=3U || shadowrun_field_target_posture!=2U ||
        !shadowrun_field_target_hp || shadowrun_field_target_hp>10U || shadowrun_field_death_timer>127U ||
        shadowrun_field_target_x<144U || shadowrun_field_target_x>65391U ||
        shadowrun_field_target_y<144U || shadowrun_field_target_y>65391U) {shadowrun_field_supported=0;return;}
    shadowrun_field_supported=1;
    for (i=0;i<4;i=i+1) {
        nx=shadowrun_linked_x_fixed;ny=shadowrun_linked_y_fixed;
        if (shadowrun_linked_velocity_x & 0x8000U) {
            delta=(u32)(u16)(0U-shadowrun_linked_velocity_x)*256UL;
            if (nx<delta) {shadowrun_field_supported=0;return;}
            nx-=delta;
        } else {
            delta=(u32)shadowrun_linked_velocity_x*256UL;
            nx+=delta;if (nx<shadowrun_linked_x_fixed) {shadowrun_field_supported=0;return;}
        }
        if (shadowrun_linked_velocity_y & 0x8000U) {
            delta=(u32)(u16)(0U-shadowrun_linked_velocity_y)*256UL;
            if (ny<delta) {shadowrun_field_supported=0;return;}
            ny-=delta;
        } else {
            delta=(u32)shadowrun_linked_velocity_y*256UL;
            ny+=delta;if (ny<shadowrun_linked_y_fixed) {shadowrun_field_supported=0;return;}
        }
        shadowrun_fixed_x=nx / 65536UL;shadowrun_fixed_y=ny / 65536UL;
        px=shadowrun_fixed_x >> 4;py=shadowrun_fixed_y >> 4;
        if (px>=shadowrun_x_min && px<shadowrun_x_max && py>=shadowrun_y_min && py<shadowrun_y_max) {
            at=(((py<<1)&65472U)+(px>>5));if (at>=2816) {shadowrun_field_supported=0;return;}
        }
        shadowrun_probe_flags=9;shadowrun_collision_check();
        if (shadowrun_collision_status!=0 && shadowrun_slope_mode==0) {
            shadowrun_linked_motion_state=3;shadowrun_field_outcome=6;return;
        }
        if (shadowrun_linked_motion_lifetime==0) {shadowrun_linked_motion_state=4;shadowrun_field_outcome=7;return;}
        shadowrun_linked_x_fixed=nx;shadowrun_linked_y_fixed=ny;
        shadowrun_linked_motion_steps+=1U;shadowrun_linked_motion_lifetime-=1U;
        shadowrun_field_projectile_x=nx/65536UL;shadowrun_field_projectile_y=ny/65536UL;
        if (shadowrun_field_source_effect==0 && (shadowrun_field_target_flags&1U) &&
            !(shadowrun_field_target_flags&80U) && !((shadowrun_field_source_flags&8U) &&
            ((shadowrun_field_target_flags_b0&128U)||(shadowrun_field_target_flags&8U)||
             (shadowrun_field_target_flags_9e&16U))) &&
            shadowrun_field_projectile_x>=shadowrun_field_target_x-144U &&
            shadowrun_field_projectile_x<shadowrun_field_target_x+144U &&
            shadowrun_field_projectile_y>=shadowrun_field_target_y-144U &&
            shadowrun_field_projectile_y<shadowrun_field_target_y+144U) {
            shadowrun_linked_x_fixed=((u32)shadowrun_field_target_x*65536UL)+(nx&65535UL);
            shadowrun_linked_y_fixed=((u32)(shadowrun_field_target_y+16U)*65536UL)+(ny&65535UL);
            shadowrun_field_projectile_x=shadowrun_field_target_x;
            shadowrun_field_projectile_y=shadowrun_field_target_y+16U;
            shadowrun_field_outcome=3;shadowrun_linked_motion_state=2;return;
        }
        if ((shadowrun_field_target_flags_b0 & 128U) ||
            shadowrun_field_projectile_x<shadowrun_field_target_x-144U ||
            shadowrun_field_projectile_x>=shadowrun_field_target_x+144U ||
            shadowrun_field_projectile_y<shadowrun_field_target_y-144U ||
            shadowrun_field_projectile_y>=shadowrun_field_target_y+144U) continue;
        shadowrun_hostile_received_hit();
        if (!shadowrun_hostile_received_supported) {shadowrun_field_supported=0;return;}
        if (shadowrun_field_outcome==3 || shadowrun_field_outcome==4) {
            shadowrun_linked_x_fixed=((u32)shadowrun_field_target_x*65536UL)+(nx&65535UL);
            shadowrun_linked_y_fixed=((u32)(shadowrun_field_target_y+16U)*65536UL)+(ny&65535UL);
            shadowrun_field_projectile_x=shadowrun_field_target_x;
            shadowrun_field_projectile_y=shadowrun_field_target_y+16U;
            shadowrun_linked_motion_state=2;return;
        }
    }
    shadowrun_field_outcome=5;
}
void shadowrun_hostile_linked_launch(void) {
    u16 flags;u16 hp;
    shadowrun_field_supported=0;
    if (shadowrun_hostile_received_profile!=1 || shadowrun_hostile_received_kind!=8U ||
        shadowrun_hostile_received_armor!=3U || shadowrun_field_actor_index!=0U ||
        shadowrun_field_item!=2U || shadowrun_field_equipped_slot!=0U || shadowrun_field_source_flags!=15U ||
        shadowrun_field_target_flags!=5U || shadowrun_field_target_flags_9e!=0U ||
        shadowrun_field_target_flags_9a>128U || shadowrun_field_target_type!=2U ||
        shadowrun_field_target_defense_bonus!=5U || shadowrun_field_target_a!=5U ||
        shadowrun_field_target_b!=4U || shadowrun_field_target_c!=3U || shadowrun_field_target_posture!=2U ||
        !shadowrun_field_target_hp || shadowrun_field_target_hp>10U || shadowrun_field_death_timer>127U ||
        shadowrun_field_target_x<144U || shadowrun_field_target_x>65391U ||
        shadowrun_field_target_y<144U || shadowrun_field_target_y>65391U) {shadowrun_field_supported=0;return;}
    if (shadowrun_linked_profile!=1 || !(shadowrun_field_target_flags&1U)) return;
    shadowrun_linked_target_x=shadowrun_field_target_x;shadowrun_linked_target_y=shadowrun_field_target_y;
    shadowrun_linked_measure();if (!shadowrun_linked_supported) return;
    shadowrun_spawn_source_x=shadowrun_linked_source_x;shadowrun_spawn_source_y=shadowrun_linked_source_y;
    shadowrun_spawn_heading=shadowrun_linked_heading;shadowrun_linked_spawn();
    if (!shadowrun_spawn_supported) return;
    flags=shadowrun_field_target_flags;hp=shadowrun_field_target_hp;
    shadowrun_field_target_flags=0;shadowrun_field_target_hp=100U;
    shadowrun_field_captured_fire();shadowrun_field_target_flags=flags;shadowrun_field_target_hp=hp;
    if (!shadowrun_field_supported || shadowrun_field_outcome!=2) return;
    shadowrun_linked_x_fixed=(u32)shadowrun_spawn_x*65536UL;
    shadowrun_linked_y_fixed=(u32)shadowrun_spawn_y*65536UL;
    shadowrun_linked_velocity_x=shadowrun_spawn_velocity_x;shadowrun_linked_velocity_y=shadowrun_spawn_velocity_y;
    shadowrun_linked_motion_steps=0;shadowrun_linked_motion_lifetime=127;shadowrun_linked_motion_state=1;
    shadowrun_hostile_linked_tick();
}
