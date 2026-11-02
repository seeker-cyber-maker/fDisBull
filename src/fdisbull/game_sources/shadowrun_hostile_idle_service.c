/* Prepared kind8 stationary B45C loop and DFDE-active timer expiry.
 * Selected +B3 and independent projectile RNG remain external. */
u8 shadowrun_hostile_idle_supported,shadowrun_hostile_idle_expired;
void shadowrun_hostile_idle_actor_pass(void) {
    u16 distance;u16 range;u16 i;
    shadowrun_hostile_idle_supported=0;shadowrun_hostile_idle_expired=0;
    if (shadowrun_attack_profile!=1U || shadowrun_attack_kind!=8U || shadowrun_attack_flags!=5U ||
        shadowrun_attack_flags_low!=16U || !shadowrun_attack_hp || !shadowrun_attack_max_hp ||
        shadowrun_attack_item!=10U || (shadowrun_attack_slot & 128U) || shadowrun_attack_gear!=38U ||
        shadowrun_attack_attr_a!=5U || shadowrun_attack_attr_b!=4U || shadowrun_attack_speed!=65535U ||
        shadowrun_attack_callback!=0xb45cUL || shadowrun_attack_animation!=24U ||
        shadowrun_attack_increment!=65520U || shadowrun_attack_threshold!=4096U ||
        shadowrun_attack_accumulator<16U || shadowrun_attack_accumulator>=4096U || shadowrun_attack_index ||
        shadowrun_attack_service_timer>20U ||
        (!shadowrun_attack_service_timer && (shadowrun_attack_action_timer & 32768U)) ||
        shadowrun_attack_event!=16U || !shadowrun_attack_counter ||
        !shadowrun_attack_global_de || shadowrun_attack_global_e0 ||
        (shadowrun_attack_alert && shadowrun_attack_ammo==40U) || shadowrun_attack_target!=0xff0100UL ||
        shadowrun_attack_x<=shadowrun_attack_player_x || shadowrun_attack_y!=shadowrun_attack_player_y) return;
    distance=shadowrun_attack_x-shadowrun_attack_player_x;
    range=rom16(0,0x13e7cUL+(u32)rom8(0,0xd4540UL+9UL*48UL+39UL)*4UL);
    if (distance>=range) return;
    if (!(shadowrun_attack_action_timer & 32768U)) shadowrun_attack_action_timer-=1U;
    if (shadowrun_attack_service_timer) shadowrun_attack_service_timer-=1U;
    else {shadowrun_attack_service_timer=20U;shadowrun_attack_counter-=1U;shadowrun_hostile_idle_expired=1;}
    shadowrun_attack_move_state=0;
    shadowrun_fixed_x=shadowrun_attack_x;shadowrun_fixed_y=shadowrun_attack_y;
    shadowrun_probe_flags=shadowrun_attack_flags;shadowrun_collision_check();
    for(i=0;i<4U;i+=1U)shadowrun_attack_corners[i]=shadowrun_probe_corners[i];
    shadowrun_attack_b3_unknown=1;
    shadowrun_hostile_idle_supported=1;
}
void shadowrun_hostile_idle_sprite_pass(void) {
    shadowrun_hostile_idle_supported=0;
    if (shadowrun_attack_callback!=0xb45cUL || shadowrun_attack_animation!=24U ||
        shadowrun_attack_increment!=65520U || shadowrun_attack_threshold!=4096U ||
        shadowrun_attack_accumulator<16U || shadowrun_attack_accumulator>=4096U ||
        shadowrun_attack_index || shadowrun_attack_flags_low!=16U) return;
    shadowrun_attack_accumulator-=16U;shadowrun_attack_graphics_pending=0;
    shadowrun_hostile_idle_supported=1;
}
void shadowrun_hostile_idle_step(void) {
    if (shadowrun_attack_callback!=0xb45cUL || shadowrun_attack_animation!=24U ||
        shadowrun_attack_increment!=65520U || shadowrun_attack_threshold!=4096U ||
        shadowrun_attack_accumulator<16U || shadowrun_attack_accumulator>=4096U ||
        shadowrun_attack_index || shadowrun_attack_flags_low!=16U) {shadowrun_hostile_idle_supported=0;return;}
    shadowrun_hostile_idle_actor_pass();if (!shadowrun_hostile_idle_supported) return;
    shadowrun_hostile_idle_sprite_pass();
}
