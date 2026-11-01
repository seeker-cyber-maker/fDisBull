/* Source $13D0C -> $145FC prepared kind-8/item-10 pursuit detour.
 * Restricts to the observed west-target/north-goal blocked-corridor branch.
 * The complete live terrain map is supplied separately. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u8 rom8(u8 region,u32 offset);
u16 rom16(u8 region,u32 offset);
u16 shadowrun_hostile_pursuit_x,shadowrun_hostile_pursuit_y;
u16 shadowrun_hostile_pursuit_player_x,shadowrun_hostile_pursuit_player_y;
u16 shadowrun_hostile_pursuit_kind,shadowrun_hostile_pursuit_animation;
u16 shadowrun_hostile_pursuit_collision,shadowrun_hostile_pursuit_path_index;
u16 shadowrun_hostile_pursuit_goal_x,shadowrun_hostile_pursuit_goal_y;
u16 shadowrun_hostile_pursuit_heading,shadowrun_hostile_pursuit_distance;
u16 shadowrun_hostile_pursuit_path0,shadowrun_hostile_pursuit_path1,shadowrun_hostile_pursuit_path2;
u16 shadowrun_hostile_pursuit_centre_x,shadowrun_hostile_pursuit_centre_y;
u16 shadowrun_hostile_pursuit_global_de,shadowrun_hostile_pursuit_global_e0;
u32 shadowrun_hostile_pursuit_callback,shadowrun_hostile_pursuit_target;
u8 shadowrun_hostile_pursuit_flags,shadowrun_hostile_pursuit_item,shadowrun_hostile_pursuit_slot;
u8 shadowrun_hostile_pursuit_ammo,shadowrun_hostile_pursuit_alert;
u8 shadowrun_hostile_pursuit_event,shadowrun_hostile_pursuit_direction,shadowrun_hostile_pursuit_counter;
u8 shadowrun_hostile_pursuit_supported;
void shadowrun_hostile_pursuit_tick(void) {
    u16 distance;u16 goal_y;u16 current;u16 candidate;u16 next;u16 row;u16 x;u16 y;u16 dx;u16 dy;u16 t;u16 range;u16 i;
    shadowrun_hostile_pursuit_supported=0;
    if (shadowrun_hostile_pursuit_kind!=8U || shadowrun_hostile_pursuit_item!=10U ||
        shadowrun_hostile_pursuit_flags!=5U || (shadowrun_hostile_pursuit_slot & 128U) ||
        (shadowrun_hostile_pursuit_alert && shadowrun_hostile_pursuit_ammo==40U) || shadowrun_hostile_pursuit_target!=0xff0100UL ||
        shadowrun_hostile_pursuit_counter!=6U || shadowrun_hostile_pursuit_event ||
        shadowrun_hostile_pursuit_direction || shadowrun_hostile_pursuit_collision ||
        shadowrun_hostile_pursuit_path_index || shadowrun_hostile_pursuit_global_de ||
        shadowrun_hostile_pursuit_global_e0 || shadowrun_hostile_pursuit_animation>60U ||
        shadowrun_hostile_pursuit_y!=shadowrun_hostile_pursuit_player_y ||
        shadowrun_hostile_pursuit_x<=shadowrun_hostile_pursuit_player_x) return;
    distance=shadowrun_hostile_pursuit_x-shadowrun_hostile_pursuit_player_x;
    if (distance>8191U || distance<240U || shadowrun_hostile_pursuit_y<=distance*2U) return;
    range=rom16(0,0x13e7cUL+(u32)rom8(0,0xd4540UL+9UL*48UL+39UL)*4UL);
    if (distance>=range) return;
    goal_y=shadowrun_hostile_pursuit_y-distance*2U;
    current=(u16)((((shadowrun_hostile_pursuit_y>>4)<<1)&0xffc0U)+(shadowrun_hostile_pursuit_x>>9));
    if (current<64U || current>=2816U || shadowrun_terrain_map[current] || !shadowrun_terrain_map[current-64U]) return;
    row=current & 0xffc0U;candidate=current;next=0;
    for(i=0;i<63U;i=i+1U) {
        if (!(candidate & 63U)) return;
        candidate-=1U;
        if ((candidate & 0xffc0U)!=row || shadowrun_terrain_map[candidate]) return;
        if (!shadowrun_terrain_map[candidate-64U]) {next=candidate-64U;break;}
    }
    if (!next) return;
    x=(candidate & 63U)*512U+256U;y=(candidate>>6)*512U+256U;
    if (shadowrun_hostile_pursuit_x<x || shadowrun_hostile_pursuit_y<y) return;
    dx=shadowrun_hostile_pursuit_x-x;dy=shadowrun_hostile_pursuit_y-y;
    if (dy>dx) {t=dx;dx=dy;dy=t;}
    shadowrun_hostile_pursuit_goal_x=shadowrun_hostile_pursuit_x;
    shadowrun_hostile_pursuit_goal_y=goal_y;
    shadowrun_hostile_pursuit_event=18U;shadowrun_hostile_pursuit_direction=4U;
    shadowrun_hostile_pursuit_counter=5U;
    shadowrun_hostile_pursuit_path0=candidate;shadowrun_hostile_pursuit_path1=next;shadowrun_hostile_pursuit_path2=65535U;
    shadowrun_hostile_pursuit_centre_x=x;shadowrun_hostile_pursuit_centre_y=y;
    shadowrun_hostile_pursuit_heading=0xc000U;shadowrun_hostile_pursuit_distance=dx+((dy+1U)>>1);
    shadowrun_hostile_pursuit_callback=0xb574UL;shadowrun_hostile_pursuit_supported=1;
}
