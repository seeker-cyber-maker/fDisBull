/* Source $13D0C -> $145E8 for prepared hostile after detour completion,
 * with clear B8=$1000 movement state and source event B0=$10. */
u8 shadowrun_hostile_direct_supported;
void shadowrun_hostile_direct_tick(void) {
    u16 distance;u16 angle;u16 vector;u16 goalx;u16 goaly;u16 range;
    shadowrun_hostile_direct_supported=0;
    if (shadowrun_hostile_pursuit_kind!=8U || shadowrun_hostile_pursuit_item!=10U ||
        shadowrun_hostile_pursuit_flags!=5U || (shadowrun_hostile_pursuit_slot & 128U) ||
        (shadowrun_hostile_pursuit_alert && shadowrun_hostile_pursuit_ammo==40U) ||
        shadowrun_hostile_pursuit_target!=0xff0100UL || shadowrun_hostile_pursuit_counter>5U ||
        shadowrun_hostile_pursuit_event!=16U || shadowrun_hostile_pursuit_direction>3U ||
        shadowrun_hostile_pursuit_collision!=4096U || shadowrun_hostile_pursuit_global_de ||
        shadowrun_hostile_pursuit_global_e0 || shadowrun_hostile_pursuit_animation>60U) return;
    shadowrun_linked_source_x=shadowrun_hostile_pursuit_x;shadowrun_linked_source_y=shadowrun_hostile_pursuit_y;
    shadowrun_linked_target_x=shadowrun_hostile_pursuit_player_x;shadowrun_linked_target_y=shadowrun_hostile_pursuit_player_y;
    shadowrun_linked_measure();if (!shadowrun_linked_supported) return;
    distance=shadowrun_linked_metric;
    range=rom16(0,0x13e7cUL+(u32)rom8(0,0xd4540UL+9UL*48UL+39UL)*4UL);
    if (distance<240U || distance>=range || distance>16383U) return;
    angle=shadowrun_linked_heading+0x4000U;vector=(angle>>8)&254U;
    goalx=shadowrun_hostile_pursuit_x+shadowrun_hostile_follow_scaled(rom16(0,0x15e56UL+vector),distance*2U);
    goaly=shadowrun_hostile_pursuit_y+shadowrun_hostile_follow_scaled(rom16(0,0x15e16UL+vector),distance*2U);
    shadowrun_linked_source_x=shadowrun_hostile_pursuit_x;shadowrun_linked_source_y=shadowrun_hostile_pursuit_y;
    shadowrun_linked_target_x=goalx;shadowrun_linked_target_y=goaly;
    shadowrun_linked_measure();if (!shadowrun_linked_supported) return;
    shadowrun_hostile_pursuit_goal_x=goalx;shadowrun_hostile_pursuit_goal_y=goaly;
    shadowrun_hostile_pursuit_heading=shadowrun_linked_heading;shadowrun_hostile_pursuit_distance=shadowrun_linked_metric;
    if (shadowrun_hostile_pursuit_counter) shadowrun_hostile_pursuit_counter-=1U;
    shadowrun_hostile_pursuit_callback=0xb574UL;shadowrun_hostile_direct_supported=1;
}
