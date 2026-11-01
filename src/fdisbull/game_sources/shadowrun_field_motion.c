/* Scene-005999 source player, heading $8000, initialized projectile; collision
 * is the shared reviewed $E7C8 GameIL. The caller supplies the live scene map,
 * bounds and rectangle table, and attests the captured source profile. */
u8 shadowrun_field_path_profile;
u8 shadowrun_field_motion_state; /* 0 inactive, 1 flight, 2 actor hit, 3 terrain */
u8 shadowrun_field_motion_steps;
u8 shadowrun_field_motion_lifetime;
u32 shadowrun_field_motion_y_fixed;
void shadowrun_field_captured_tick(void) {
    u16 i; u16 old_ammo; u16 old_busy; u16 old_slot; u16 old_outcome;
    u16 px; u16 py; u16 at; u32 proposed;
    if (shadowrun_field_path_profile != 1 || shadowrun_field_motion_state != 1 ||
        shadowrun_field_motion_steps >= 127) { shadowrun_field_supported = 0; return; }
    old_ammo=shadowrun_field_ammo; old_outcome=shadowrun_field_outcome;
    shadowrun_field_ammo=0;
    shadowrun_field_fire();
    shadowrun_field_ammo=old_ammo; shadowrun_field_outcome=old_outcome;
    if (!shadowrun_field_supported) return;
    for (i=0; i<4; i=i+1) {
        proposed=shadowrun_field_motion_y_fixed + 6291200UL; /* signed $5FFF << 8 */
        if (proposed < shadowrun_field_motion_y_fixed) { shadowrun_field_supported=0; return; }
        shadowrun_fixed_x=15584;
        shadowrun_fixed_y=proposed / 65536UL;
        px=shadowrun_fixed_x >> 4; py=shadowrun_fixed_y >> 4;
        if (px >= shadowrun_x_min && px < shadowrun_x_max && py >= shadowrun_y_min && py < shadowrun_y_max) {
            at=(((py << 1) & 65472U) + (px >> 5));
            if (at >= 2816) { shadowrun_field_supported=0; return; }
        }
        shadowrun_probe_flags=9; /* projectile +$10 from source initializer */
        shadowrun_collision_check();
        if (shadowrun_collision_status != 0 && shadowrun_slope_mode == 0) {
            shadowrun_field_motion_state=3; shadowrun_field_outcome=6; return;
        }
        if (shadowrun_field_motion_lifetime == 0) { shadowrun_field_supported=0; return; }
        shadowrun_field_motion_y_fixed=proposed;
        shadowrun_field_motion_steps += 1U;
        shadowrun_field_motion_lifetime -= 1U;
        shadowrun_field_projectile_x=15584;
        shadowrun_field_projectile_y=shadowrun_field_motion_y_fixed / 65536UL;
        /* $15B32: zero projectile success takes carry-set contact with D1=0,
         * then $14E60, skipping effect resolution and its RNG draws. */
        if (shadowrun_field_source_effect == 0 &&
            (shadowrun_field_target_flags & 1U) && !(shadowrun_field_target_flags & 80U) &&
            !((shadowrun_field_source_flags & 8U) &&
              ((shadowrun_field_target_flags_b0 & 128U) || (shadowrun_field_target_flags & 8U) ||
               (shadowrun_field_target_flags_9e & 16U))) &&
            shadowrun_field_projectile_x >= shadowrun_field_target_x - 144U &&
            shadowrun_field_projectile_x < shadowrun_field_target_x + 144U &&
            shadowrun_field_projectile_y >= shadowrun_field_target_y - 144U &&
            shadowrun_field_projectile_y < shadowrun_field_target_y + 144U) {
            shadowrun_field_projectile_x=shadowrun_field_target_x;
            shadowrun_field_projectile_y=shadowrun_field_target_y + 16U;
            shadowrun_field_motion_y_fixed=((u32)shadowrun_field_projectile_y * 65536UL) +
                                            (shadowrun_field_motion_y_fixed & 65535UL);
            shadowrun_field_outcome=3; shadowrun_field_motion_state=2; return;
        }
        old_ammo=shadowrun_field_ammo; old_busy=shadowrun_field_slots_busy;
        old_slot=shadowrun_field_slot;
        shadowrun_field_ammo=1; shadowrun_field_slots_busy=0;
        shadowrun_field_fire();
        shadowrun_field_ammo=old_ammo; shadowrun_field_slots_busy=old_busy;
        shadowrun_field_slot=old_slot;
        if (!shadowrun_field_supported) return;
        if (shadowrun_field_outcome == 3 || shadowrun_field_outcome == 4) {
            /* $14E6E aligns the high words to the target while retaining
             * the motion substep's fractional low words. */
            shadowrun_field_projectile_x=shadowrun_field_target_x;
            shadowrun_field_projectile_y=shadowrun_field_target_y + 16U;
            shadowrun_field_motion_y_fixed=((u32)shadowrun_field_projectile_y * 65536UL) +
                                            (shadowrun_field_motion_y_fixed & 65535UL);
            shadowrun_field_motion_state=2; return;
        }
    }
    shadowrun_field_outcome=5; /* still flying */
}
void shadowrun_field_captured_launch(void) {
    u16 flags;
    shadowrun_field_supported=0;
    if (shadowrun_field_path_profile != 1) return;
    flags=shadowrun_field_target_flags;
    shadowrun_field_target_flags=0;
    shadowrun_field_captured_fire();
    shadowrun_field_target_flags=flags;
    if (!shadowrun_field_supported || shadowrun_field_outcome != 2) return;
    shadowrun_field_motion_state=1;
    shadowrun_field_motion_steps=0;
    shadowrun_field_motion_lifetime=127;
    shadowrun_field_motion_y_fixed=746192896UL; /* $2C7A0000 */
    shadowrun_field_projectile_x=15584;
    shadowrun_field_projectile_y=11386;
    shadowrun_field_captured_tick();
}
