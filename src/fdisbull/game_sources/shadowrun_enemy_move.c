/* Clear-terrain branch of source $B574..$B6E2 for captured type-11 actors.
 * The caller supplies callback state, captured actor flags/attributes and
 * shared terrain. This is a movement service call, not waypoint scheduling,
 * aggression, attack selection or a general NPC AI. Other branches refuse. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u16 rom16(u8 region,u32 offset);
u32 rom32(u8 region,u32 offset);
u16 shadowrun_ai_x,shadowrun_ai_y,shadowrun_ai_heading,shadowrun_ai_target_heading;
u16 shadowrun_ai_kind,shadowrun_ai_distance,shadowrun_ai_move_state,shadowrun_ai_collision_state;
u16 shadowrun_ai_transition_heading;
u16 shadowrun_ai_speed,shadowrun_ai_animation;
u32 shadowrun_ai_callback;
u8 shadowrun_ai_flags,shadowrun_ai_flags_low,shadowrun_ai_equipment_flags,shadowrun_ai_event_flags;
u8 shadowrun_ai_attribute,shadowrun_ai_supported,shadowrun_ai_result;
u16 shadowrun_ai_combat_global;
u8 shadowrun_ai_corners[4];
void shadowrun_ai_actor_tick(void) {
    u16 delta;u16 heading;u16 rotated;u16 ordinal;u16 offset;u16 x;u16 y;u16 i;u32 table;
    shadowrun_ai_supported=0;shadowrun_ai_result=0;
    if (shadowrun_ai_kind!=11 || shadowrun_ai_callback!=0xb574UL ||
        shadowrun_ai_flags!=0x25U || !(shadowrun_ai_equipment_flags & 32U) ||
        (shadowrun_ai_event_flags & 128U) || shadowrun_ai_attribute!=1U ||
        (shadowrun_ai_combat_global!=0 && shadowrun_ai_combat_global!=65535U)) return;
    heading=shadowrun_ai_heading;
    delta=heading-shadowrun_ai_target_heading;
    if (delta & 0x8000U) {
        if (delta<0xf800U) heading+=0x0800U;
        else heading=shadowrun_ai_target_heading;
    } else if (delta!=0) {
        if (delta<0x0800U) heading=shadowrun_ai_target_heading;
        else heading-=0x0800U;
    }
    if (shadowrun_ai_combat_global==0) table=0xbe62UL;
    else table=0xbe82UL; /* source equipment-bit-5 combat branch */
    if (shadowrun_ai_distance<0x460U) table=0xbd72UL;
    if (shadowrun_ai_distance<0x360U) table=0xbd92UL;
    if (shadowrun_ai_distance<0x200U) table=0xbdb2UL;
    if (shadowrun_ai_distance<0x100U) table=0xbdd2UL;
    rotated=(u16)((heading<<3)|(heading>>13));ordinal=rotated&7U;offset=ordinal<<2;
    x=shadowrun_ai_x+rom16(0,table+offset);y=shadowrun_ai_y+rom16(0,table+offset+2UL);
    shadowrun_fixed_x=x;shadowrun_fixed_y=y;shadowrun_probe_flags=shadowrun_ai_flags;
    shadowrun_collision_check();
    if (shadowrun_collision_status!=0 || (x==shadowrun_ai_x && y==shadowrun_ai_y)) return;
    shadowrun_ai_heading=heading;shadowrun_ai_x=x;shadowrun_ai_y=y;
    shadowrun_ai_move_state=1;shadowrun_ai_collision_state=0x1000U;
    shadowrun_ai_event_flags &= 254U;shadowrun_ai_speed=rom16(0,table+4UL);
    for(i=0;i<4;i=i+1)shadowrun_ai_corners[i]=shadowrun_probe_corners[i];
    if (shadowrun_ai_flags_low & 4U) rotated=(u16)((shadowrun_ai_transition_heading<<3)|(shadowrun_ai_transition_heading>>13));
    shadowrun_ai_animation=rom16(0,0xc062UL+((rotated&7U)<<1));
    shadowrun_ai_supported=1;shadowrun_ai_result=1;
}
