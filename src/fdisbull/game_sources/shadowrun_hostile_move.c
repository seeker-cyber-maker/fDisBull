/* Clear movement service $B574..$B6E2 for prepared kind-8 hostile actors.
 * Shares scalar actor and terrain fields with shadowrun_enemy_move.c. */
u8 shadowrun_hostile_move_supported;
void shadowrun_hostile_move_tick(void) {
    u16 delta;u16 heading;u16 rotated;u16 offset;u16 x;u16 y;u16 i;u32 table;
    shadowrun_hostile_move_supported=0;
    if (shadowrun_ai_kind!=8U || shadowrun_ai_callback!=0xb574UL ||
        shadowrun_ai_flags!=5U || (shadowrun_ai_equipment_flags & 32U) ||
        (shadowrun_ai_event_flags & 128U) || shadowrun_ai_attribute!=5U ||
        !shadowrun_ai_combat_global) return;
    heading=shadowrun_ai_heading;delta=heading-shadowrun_ai_target_heading;
    if (delta & 0x8000U) {
        if (delta<0xf800U) heading+=0x0800U;
        else heading=shadowrun_ai_target_heading;
    } else if (delta!=0) {
        if (delta<0x0800U) heading=shadowrun_ai_target_heading;
        else heading-=0x0800U;
    }
    table=rom32(0,0xbdf2UL+20UL);
    if (shadowrun_ai_distance<0x460U) table=0xbd72UL;
    if (shadowrun_ai_distance<0x360U) table=0xbd92UL;
    if (shadowrun_ai_distance<0x200U) table=0xbdb2UL;
    if (shadowrun_ai_distance<0x100U) table=0xbdd2UL;
    rotated=(u16)((heading<<3)|(heading>>13));offset=(rotated&7U)*4U;
    x=shadowrun_ai_x+rom16(0,table+offset);y=shadowrun_ai_y+rom16(0,table+offset+2UL);
    shadowrun_fixed_x=x;shadowrun_fixed_y=y;shadowrun_probe_flags=shadowrun_ai_flags;
    shadowrun_collision_check();
    if (shadowrun_collision_status!=0 || (x==shadowrun_ai_x && y==shadowrun_ai_y)) return;
    shadowrun_ai_heading=heading;shadowrun_ai_x=x;shadowrun_ai_y=y;
    shadowrun_ai_move_state=1U;shadowrun_ai_collision_state=4096U;
    shadowrun_ai_event_flags &= 254U;shadowrun_ai_speed=rom16(0,table+4UL);
    for(i=0;i<4;i=i+1)shadowrun_ai_corners[i]=shadowrun_probe_corners[i];
    if (shadowrun_ai_flags_low & 4U) rotated=(u16)((shadowrun_ai_transition_heading<<3)|(shadowrun_ai_transition_heading>>13));
    shadowrun_ai_animation=rom16(0,0xc062UL+((rotated&7U)<<1));
    shadowrun_hostile_move_supported=1;
}
