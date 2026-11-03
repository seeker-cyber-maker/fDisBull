/* Between-service idle of the captured moving-origin hostile. */
u8 shadowrun_moving_idle_18_supported;
void shadowrun_hostile_moving_idle_18_step(void) {
    u16 sum;u16 i;u32 table;u32 sequence;
    shadowrun_moving_idle_18_supported=0;
    if (shadowrun_attack_profile!=1U || shadowrun_attack_kind!=8U || shadowrun_attack_flags!=5U ||
        shadowrun_attack_flags_low!=16U || !shadowrun_attack_hp || !shadowrun_attack_max_hp ||
        shadowrun_attack_item!=10U || (shadowrun_attack_slot & 128U) || shadowrun_attack_gear!=38U ||
        shadowrun_attack_attr_a!=5U || shadowrun_attack_attr_b!=4U || shadowrun_attack_speed!=22U ||
        shadowrun_attack_callback!=0xb45cUL || shadowrun_attack_animation!=24U ||
        !shadowrun_attack_service_timer || shadowrun_attack_service_timer>20U ||
        shadowrun_attack_action_timer!=65535U || shadowrun_attack_event!=18U ||
        !shadowrun_attack_global_de || shadowrun_attack_global_e0 ||
        shadowrun_attack_target!=0xff0100UL || shadowrun_attack_increment!=352U ||
        shadowrun_attack_threshold!=4096U || shadowrun_attack_accumulator>=4096U || shadowrun_attack_index) return;
    table=rom32(0,0x62acUL+32UL);sequence=rom32(0,table+24UL);
    if (rom16(0,sequence)!=1U) return;
    shadowrun_attack_service_timer-=1U;shadowrun_attack_move_state=0;
    shadowrun_fixed_x=shadowrun_attack_x;shadowrun_fixed_y=shadowrun_attack_y;
    shadowrun_probe_flags=shadowrun_attack_flags;shadowrun_collision_check();
    for(i=0;i<4U;i+=1U)shadowrun_attack_corners[i]=shadowrun_probe_corners[i];
    sum=shadowrun_attack_accumulator+shadowrun_attack_increment;
    shadowrun_attack_graphics_pending=0;
    if (sum>=4096U) {sum-=4096U;shadowrun_attack_graphics_pending=1;}
    shadowrun_attack_accumulator=sum;shadowrun_attack_b3_unknown=1;
    shadowrun_moving_idle_18_supported=1;
}
