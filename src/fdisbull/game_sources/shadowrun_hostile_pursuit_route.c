/* Per-frame B574 movement and animation for the prepared kind-8 chase.
 * On expiry the source service may fire; this leaf returns unsupported before
 * making actor changes and the caller dispatches that service separately. */
u16 shadowrun_pursuit_route_service_timer,shadowrun_pursuit_route_action_timer;
u16 shadowrun_pursuit_route_sprite_increment,shadowrun_pursuit_route_sprite_accumulator;
u16 shadowrun_pursuit_route_sprite_threshold,shadowrun_pursuit_route_sprite_index;
u8 shadowrun_pursuit_route_supported;
void shadowrun_hostile_pursuit_route_step(void) {
    u16 heading;u16 delta;u16 rotated;u16 anim;u16 sum;u16 index;u32 table;u32 sequence;
    shadowrun_pursuit_route_supported=0;
    if (!shadowrun_pursuit_route_service_timer || shadowrun_pursuit_route_service_timer>20U ||
        shadowrun_pursuit_route_sprite_threshold!=4096U ||
        shadowrun_pursuit_route_sprite_accumulator>=4096U ||
        shadowrun_pursuit_route_sprite_increment>4096U || shadowrun_pursuit_route_sprite_index>=4U ||
        shadowrun_ai_kind!=8U || shadowrun_ai_callback!=0xb574UL || shadowrun_ai_flags!=5U ||
        shadowrun_ai_attribute!=5U || shadowrun_ai_combat_global!=1U ||
        (shadowrun_ai_flags_low & 238U)) return;
    heading=shadowrun_ai_heading;delta=heading-shadowrun_ai_target_heading;
    if (delta & 32768U) {if (delta<63488U) heading+=2048U;else heading=shadowrun_ai_target_heading;}
    else if (delta) {if (delta<2048U) heading=shadowrun_ai_target_heading;else heading-=2048U;}
    rotated=(u16)((heading<<3)|(heading>>13));
    if (shadowrun_ai_flags_low & 4U) rotated=(u16)((shadowrun_ai_transition_heading<<3)|(shadowrun_ai_transition_heading>>13));
    anim=rom16(0,0xc062UL+((u32)(rotated&7U)*2UL));
    table=rom32(0,0x62acUL+32UL);sequence=rom32(0,table+(u32)anim);
    if (rom16(0,sequence)!=4U) return;
    shadowrun_hostile_move_tick();if (!shadowrun_hostile_move_supported) return;
    shadowrun_pursuit_route_service_timer-=1U;
    if (!(shadowrun_pursuit_route_action_timer & 32768U)) shadowrun_pursuit_route_action_timer-=1U;
    sum=shadowrun_pursuit_route_sprite_accumulator+shadowrun_pursuit_route_sprite_increment;
    index=shadowrun_pursuit_route_sprite_index;
    if (sum>=4096U) {sum-=4096U;index+=1U;}
    if (index>=4U) index=0;
    shadowrun_pursuit_route_sprite_accumulator=sum;shadowrun_pursuit_route_sprite_index=index;
    shadowrun_pursuit_route_sprite_increment=shadowrun_ai_speed*16U;
    shadowrun_pursuit_route_supported=1;
}
/* Sprite pass immediately after the bounded constructor's first movement. */
void shadowrun_hostile_pursuit_first_sprite(void) {
    u32 table;u32 sequence;
    shadowrun_pursuit_route_supported=0;
    if (shadowrun_ai_kind!=8U || shadowrun_ai_flags!=5U || shadowrun_ai_callback!=0xb574UL ||
        shadowrun_ai_animation!=60U || shadowrun_ai_speed!=22U ||
        shadowrun_pursuit_route_sprite_increment!=4096U || shadowrun_pursuit_route_sprite_accumulator ||
        shadowrun_pursuit_route_sprite_threshold!=4096U || shadowrun_pursuit_route_sprite_index) return;
    table=rom32(0,0x62acUL+32UL);sequence=rom32(0,table+(u32)shadowrun_ai_animation);
    if (rom16(0,sequence)!=4U) return;
    shadowrun_pursuit_route_sprite_accumulator=0;shadowrun_pursuit_route_sprite_index=1U;
    shadowrun_pursuit_route_sprite_increment=shadowrun_ai_speed*16U;
    shadowrun_pursuit_route_supported=1;
}
