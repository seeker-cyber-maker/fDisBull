/* Source post-launch shooting pose through the captured first sprite pass.
 * Caller attests the additional actor pass caused by the player-hit loop
 * continuation; later source target-selection +11bit4 remains external. */
u8 shadowrun_attack_first_supported;
void shadowrun_hostile_attack_first_pass(void) {
    u16 anim;u16 sum;u16 index;u16 i;u16 range;u32 table;u32 sequence;u32 frame;
    shadowrun_attack_first_supported=0;anim=shadowrun_attack_animation;
    if (shadowrun_attack_profile!=1U || shadowrun_attack_kind!=8U || shadowrun_attack_flags!=5U ||
        shadowrun_attack_flags_low!=1U || !shadowrun_attack_hp || !shadowrun_attack_max_hp ||
        shadowrun_attack_item!=10U || (shadowrun_attack_slot & 128U) || shadowrun_attack_gear!=38U ||
        shadowrun_attack_attr_a!=5U || shadowrun_attack_attr_b!=4U || shadowrun_attack_speed!=65535U ||
        shadowrun_attack_callback!=0xb3eeUL || anim<64U || anim>92U || (anim & 3U) ||
        shadowrun_attack_service_timer!=20U || shadowrun_attack_action_timer!=47U ||
        shadowrun_attack_counter!=6U || shadowrun_attack_event || !shadowrun_attack_global_de ||
        shadowrun_attack_global_e0 || (shadowrun_attack_alert && shadowrun_attack_ammo==40U) ||
        shadowrun_attack_target!=0xff0100UL || shadowrun_attack_threshold!=4096U ||
        shadowrun_attack_increment!=4096U || shadowrun_attack_accumulator || shadowrun_attack_index) return;
    shadowrun_linked_source_x=shadowrun_attack_x;shadowrun_linked_source_y=shadowrun_attack_y;
    shadowrun_linked_target_x=shadowrun_attack_player_x;shadowrun_linked_target_y=shadowrun_attack_player_y;
    shadowrun_linked_measure();if (!shadowrun_linked_supported) return;
    range=rom16(0,0x13e7cUL+(u32)rom8(0,0xd4540UL+9UL*48UL+39UL)*4UL);
    if (shadowrun_linked_metric>=range) return;
    table=rom32(0,0x62acUL+32UL);sequence=rom32(0,table+(u32)anim);
    if (rom16(0,sequence)!=0x8001U) return;
    frame=rom32(0,sequence+4UL);if (rom16(0,frame)!=0x8002U) return;
    /* Initial service tail then two identical B3EE actor passes. */
    shadowrun_attack_counter-=1U;shadowrun_attack_event|=16U;shadowrun_attack_action_timer-=1U;
    shadowrun_attack_move_state=0;
    shadowrun_fixed_x=shadowrun_attack_x;shadowrun_fixed_y=shadowrun_attack_y;
    shadowrun_probe_flags=shadowrun_attack_flags;shadowrun_collision_check();
    for(i=0;i<4U;i+=1U)shadowrun_attack_corners[i]=shadowrun_probe_corners[i];
    sum=shadowrun_attack_accumulator+shadowrun_attack_increment;index=shadowrun_attack_index;
    if (sum>=4096U) {sum-=4096U;index+=1U;shadowrun_attack_flags_low|=1U;}
    if (index>=1U) {index=0;shadowrun_attack_animation|=32768U;}
    shadowrun_attack_accumulator=sum;shadowrun_attack_index=index;
    shadowrun_attack_increment=rom16(0,sequence+2UL);
    shadowrun_attack_flags_low &= 254U;shadowrun_attack_graphics_pending=1;
    shadowrun_attack_first_supported=1;
}
