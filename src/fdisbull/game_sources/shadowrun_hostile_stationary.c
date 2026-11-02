/* Prepared kind8/item10 shooting pose $B39A/$B3EE and source service expiry.
 * Selected +B3, sound and graphics transfer payloads are explicitly external. */
u16 shadowrun_attack_kind,shadowrun_attack_x,shadowrun_attack_y,shadowrun_attack_heading;
u16 shadowrun_attack_animation,shadowrun_attack_increment,shadowrun_attack_accumulator,shadowrun_attack_threshold,shadowrun_attack_index;
u16 shadowrun_attack_move_state,shadowrun_attack_action_timer,shadowrun_attack_service_timer,shadowrun_attack_gear,shadowrun_attack_speed;
u16 shadowrun_attack_player_x,shadowrun_attack_player_y,shadowrun_attack_global_de,shadowrun_attack_global_e0;
u32 shadowrun_attack_callback,shadowrun_attack_target;
u8 shadowrun_attack_profile,shadowrun_attack_flags,shadowrun_attack_flags_low,shadowrun_attack_hp,shadowrun_attack_max_hp;
u8 shadowrun_attack_item,shadowrun_attack_slot,shadowrun_attack_ammo,shadowrun_attack_attr_a,shadowrun_attack_attr_b,shadowrun_attack_alert;
u8 shadowrun_attack_event,shadowrun_attack_counter,shadowrun_attack_corners[4];
u8 shadowrun_attack_supported,shadowrun_attack_result,shadowrun_attack_b3_unknown,shadowrun_attack_graphics_pending;
void shadowrun_hostile_attack_start(void) {
    u16 rotated;u16 d1;u16 cooldown;
    shadowrun_attack_supported=0;
    if (shadowrun_attack_profile!=1U || shadowrun_attack_kind!=8U || shadowrun_attack_flags!=5U ||
        shadowrun_attack_item!=10U || shadowrun_attack_gear!=38U || shadowrun_attack_attr_a!=5U || shadowrun_attack_attr_b!=4U) return;
    rotated=(u16)((shadowrun_attack_heading<<3)|(shadowrun_attack_heading>>13));
    if (rotated & 32768U) rotated+=1U;
    shadowrun_attack_callback=0xb3eeUL;shadowrun_attack_animation=rom16(0,0xc042UL+((rotated & 7U)<<1));
    d1=(shadowrun_attack_attr_a+shadowrun_attack_attr_b)/2U;if (d1) d1-=1U;
    cooldown=(106U-d1*4U)/2U;if (cooldown<15U) cooldown=15U;
    shadowrun_attack_action_timer=cooldown;shadowrun_attack_accumulator=0;shadowrun_attack_index=0;
    shadowrun_attack_flags_low|=1U;shadowrun_attack_supported=1;
}
void shadowrun_hostile_attack_step(void) {
    u16 anim;u16 sum;u16 index;u16 dirty;u16 rotated;u16 distance;u16 range;u16 i;
    u32 table;u32 sequence;u32 frame;
    shadowrun_attack_supported=0;shadowrun_attack_result=0;shadowrun_attack_b3_unknown=0;shadowrun_attack_graphics_pending=0;
    anim=shadowrun_attack_animation & 32767U;
    if (shadowrun_attack_profile!=1U || shadowrun_attack_kind!=8U || shadowrun_attack_flags!=5U ||
        (shadowrun_attack_flags_low & 238U) || !shadowrun_attack_hp || !shadowrun_attack_max_hp ||
        shadowrun_attack_item!=10U || (shadowrun_attack_slot & 128U) || shadowrun_attack_gear!=38U ||
        shadowrun_attack_attr_a!=5U || shadowrun_attack_attr_b!=4U || shadowrun_attack_speed!=65535U ||
        shadowrun_attack_callback!=0xb3eeUL || anim<64U || anim>92U || (anim & 3U) ||
        shadowrun_attack_service_timer>20U || shadowrun_attack_action_timer & 32768U ||
        shadowrun_attack_threshold!=4096U || shadowrun_attack_accumulator>=4096U ||
        shadowrun_attack_increment>4096U || shadowrun_attack_index>0U) return;
    table=rom32(0,0x62acUL+32UL);sequence=rom32(0,table+(u32)anim);
    if (rom16(0,sequence)!=0x8001U) return;
    sum=shadowrun_attack_accumulator+shadowrun_attack_increment;index=shadowrun_attack_index;
    dirty=shadowrun_attack_flags_low & 1U;if (sum>=4096U) {index+=1U;dirty=1U;}
    if (index>=1U) index=0;
    frame=rom32(0,sequence+4UL+(u32)index*4UL);
    if (dirty && rom16(0,frame)!=0x8002U) return;
    if (!shadowrun_attack_service_timer) {
        if (!(shadowrun_attack_animation & 32768U) || !shadowrun_attack_global_de || shadowrun_attack_global_e0 ||
            (shadowrun_attack_alert && shadowrun_attack_ammo==40U) || shadowrun_attack_target!=0xff0100UL ||
            !shadowrun_attack_counter || shadowrun_attack_event!=16U) return;
        shadowrun_linked_source_x=shadowrun_attack_x;shadowrun_linked_source_y=shadowrun_attack_y;
        shadowrun_linked_target_x=shadowrun_attack_player_x;shadowrun_linked_target_y=shadowrun_attack_player_y;
        shadowrun_linked_measure();if (!shadowrun_linked_supported) return;
        distance=shadowrun_linked_metric;
        range=rom16(0,0x13e7cUL+(u32)rom8(0,0xd4540UL+9UL*48UL+39UL)*4UL);
        if (distance>=range) return;
        rotated=(u16)((shadowrun_attack_heading<<3)|(shadowrun_attack_heading>>13));
        if (rotated & 32768U) rotated+=1U;
        anim=rom16(0,0xc052UL+((rotated & 7U)<<1));
        sequence=rom32(0,table+(u32)anim);
        if (rom16(0,sequence)!=1U || rom16(0,rom32(0,sequence+4UL))!=0x8002U) return;
        shadowrun_attack_action_timer-=1U;shadowrun_attack_service_timer=20U;
        shadowrun_attack_counter-=1U;shadowrun_attack_callback=0xb45cUL;
        shadowrun_attack_animation=anim;shadowrun_attack_event|=16U;
        shadowrun_attack_move_state=0;
        shadowrun_fixed_x=shadowrun_attack_x;shadowrun_fixed_y=shadowrun_attack_y;
        shadowrun_probe_flags=shadowrun_attack_flags;shadowrun_collision_check();
        for(i=0;i<4U;i+=1U)shadowrun_attack_corners[i]=shadowrun_probe_corners[i];
        if (sum>=4096U) sum-=4096U;
        shadowrun_attack_accumulator=sum;shadowrun_attack_index=0;shadowrun_attack_increment=65520U;
        shadowrun_attack_flags_low &= 254U;shadowrun_attack_graphics_pending=1;
        if (shadowrun_attack_flags_low & 16U) shadowrun_attack_b3_unknown=1;
        shadowrun_attack_result=2;shadowrun_attack_supported=1;return;
    }
    if (!(shadowrun_attack_animation & 32768U)) return;
    shadowrun_attack_action_timer-=1U;shadowrun_attack_service_timer-=1U;
    shadowrun_attack_move_state=0;
    shadowrun_fixed_x=shadowrun_attack_x;shadowrun_fixed_y=shadowrun_attack_y;
    shadowrun_probe_flags=shadowrun_attack_flags;shadowrun_collision_check();
    for(i=0;i<4U;i+=1U)shadowrun_attack_corners[i]=shadowrun_probe_corners[i];
    if (sum>=4096U) {sum-=4096U;shadowrun_attack_animation|=32768U;}
    shadowrun_attack_accumulator=sum;shadowrun_attack_index=0;shadowrun_attack_increment=rom16(0,sequence+2UL);
    if (dirty) {shadowrun_attack_flags_low &= 254U;shadowrun_attack_graphics_pending=1;}
    if (shadowrun_attack_flags_low & 16U) shadowrun_attack_b3_unknown=1;
    shadowrun_attack_result=1;shadowrun_attack_supported=1;
}
