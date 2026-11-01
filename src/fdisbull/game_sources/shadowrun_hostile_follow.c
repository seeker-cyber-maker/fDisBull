/* Source $13D0C -> $149C0 continuation using an existing westward path.
 * Shares actor fields with the initial hostile-pursuit leaf. */
u8 shadowrun_hostile_follow_supported;
u16 shadowrun_hostile_follow_scaled(u16 coefficient,u16 magnitude) {
    u32 product;
    if (coefficient & 32768U) {
        product=(u32)(u16)(0U-coefficient)*(u32)magnitude*2UL;
        return (u16)(0U-(u16)((product+65535UL)/65536UL));
    }
    product=(u32)coefficient*(u32)magnitude*2UL;
    return (u16)(product/65536UL);
}
void shadowrun_hostile_follow_tick(void) {
    u16 current;u16 path;u16 distance;u16 angle;u16 vector;u16 goalx;u16 goaly;u16 x;u16 y;u16 dx;u16 dy;u16 t;u16 range;
    shadowrun_hostile_follow_supported=0;
    if (shadowrun_hostile_pursuit_kind!=8U || shadowrun_hostile_pursuit_item!=10U ||
        shadowrun_hostile_pursuit_flags!=5U || (shadowrun_hostile_pursuit_slot & 128U) ||
        (shadowrun_hostile_pursuit_alert && shadowrun_hostile_pursuit_ammo==40U) ||
        shadowrun_hostile_pursuit_target!=0xff0100UL ||
        shadowrun_hostile_pursuit_counter==0U || shadowrun_hostile_pursuit_counter>5U ||
        shadowrun_hostile_pursuit_event!=18U || shadowrun_hostile_pursuit_direction!=4U ||
        shadowrun_hostile_pursuit_path_index || shadowrun_hostile_pursuit_global_de ||
        shadowrun_hostile_pursuit_global_e0 || shadowrun_hostile_pursuit_animation>60U) return;
    shadowrun_linked_source_x=shadowrun_hostile_pursuit_x;shadowrun_linked_source_y=shadowrun_hostile_pursuit_y;
    shadowrun_linked_target_x=shadowrun_hostile_pursuit_player_x;shadowrun_linked_target_y=shadowrun_hostile_pursuit_player_y;
    shadowrun_linked_measure();if (!shadowrun_linked_supported) return;
    distance=shadowrun_linked_metric;
    range=rom16(0,0x13e7cUL+(u32)rom8(0,0xd4540UL+9UL*48UL+39UL)*4UL);
    if (distance<240U || distance>=range || distance>16383U) return;
    current=(u16)((((shadowrun_hostile_pursuit_y>>4)<<1)&0xffc0U)+(shadowrun_hostile_pursuit_x>>9));
    path=shadowrun_hostile_pursuit_path0;
    if (path>=2816U || (current & 0xffc0U)!=(path & 0xffc0U) || (path & 63U)>=(current & 63U)) return;
    angle=shadowrun_linked_heading+0x4000U;vector=(angle>>8)&254U;
    x=shadowrun_hostile_follow_scaled(rom16(0,0x15e56UL+vector),distance*2U);
    y=shadowrun_hostile_follow_scaled(rom16(0,0x15e16UL+vector),distance*2U);
    goalx=shadowrun_hostile_pursuit_x+x;goaly=shadowrun_hostile_pursuit_y+y;
    x=(path & 63U)*512U+256U;y=(path>>6)*512U+256U;
    if (shadowrun_hostile_pursuit_x<x || shadowrun_hostile_pursuit_y<y) return;
    dx=shadowrun_hostile_pursuit_x-x;dy=shadowrun_hostile_pursuit_y-y;
    if (dy>dx) {t=dx;dx=dy;dy=t;}
    shadowrun_hostile_pursuit_goal_x=goalx;shadowrun_hostile_pursuit_goal_y=goaly;
    shadowrun_hostile_pursuit_centre_x=x;shadowrun_hostile_pursuit_centre_y=y;
    shadowrun_hostile_pursuit_heading=0xc000U;shadowrun_hostile_pursuit_distance=dx+((dy+1U)>>1);
    shadowrun_hostile_pursuit_counter-=1U;shadowrun_hostile_pursuit_callback=0xb574UL;
    shadowrun_hostile_follow_supported=1;
}
