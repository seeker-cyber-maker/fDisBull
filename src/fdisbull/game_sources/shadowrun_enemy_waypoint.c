/* Captured actor waypoint-arrival continuation, $1460e -> $142dc. */
u32 shadowrun_ai_waypoint_table;
u16 shadowrun_ai_waypoint_index;
u8 shadowrun_ai_waypoint_supported;
void shadowrun_ai_waypoint_arrival(void) {
    u16 dx; u16 dy; u16 t; u16 metric; u16 index; u16 next_x; u16 next_y;
    shadowrun_ai_waypoint_supported=0;
    if (shadowrun_ai_kind!=11U || shadowrun_ai_flags!=37U ||
        !(shadowrun_ai_equipment_flags & 32U) || (shadowrun_ai_equipment_flags & 76U) ||
        (shadowrun_ai_event_flags & 192U) || shadowrun_ai_service_pause ||
        shadowrun_ai_service_timer || shadowrun_ai_service_contact || shadowrun_ai_combat_global ||
        (shadowrun_ai_waypoint_table!=0x172d58UL && shadowrun_ai_waypoint_table!=0x172d68UL &&
         shadowrun_ai_waypoint_table!=0x172d78UL) || shadowrun_ai_waypoint_index>8U ||
        (shadowrun_ai_waypoint_index & 3U)) return;
    if (rom16(0,shadowrun_ai_waypoint_table) & 32768U) return;
    if (shadowrun_ai_x>=shadowrun_ai_waypoint_x) dx=shadowrun_ai_x-shadowrun_ai_waypoint_x;
    else dx=shadowrun_ai_waypoint_x-shadowrun_ai_x;
    if (shadowrun_ai_y>=shadowrun_ai_waypoint_y) dy=shadowrun_ai_y-shadowrun_ai_waypoint_y;
    else dy=shadowrun_ai_waypoint_y-shadowrun_ai_y;
    if (dx>32767U || dy>32767U) return;
    if (dy>dx) {t=dx;dx=dy;dy=t;}
    metric=dx+((dy+1U)>>1);
    if (metric>=480U) return;
    index=shadowrun_ai_waypoint_index+4U;
    next_x=rom16(0,shadowrun_ai_waypoint_table+(u32)index);
    if (!next_x) {index=0;next_x=rom16(0,shadowrun_ai_waypoint_table);}
    next_y=rom16(0,shadowrun_ai_waypoint_table+(u32)index+2UL);
    shadowrun_ai_service_timer=20U;
    shadowrun_ai_event_flags=(shadowrun_ai_event_flags & 128U) | 4U;
    shadowrun_ai_service_direction=0;
    shadowrun_ai_callback=0xb45cUL;
    shadowrun_ai_waypoint_index=index;
    shadowrun_ai_waypoint_x=next_x;shadowrun_ai_waypoint_y=next_y;
    shadowrun_ai_waypoint_supported=1;
}
