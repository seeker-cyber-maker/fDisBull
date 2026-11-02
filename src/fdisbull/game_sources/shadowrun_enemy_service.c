/* Bounded actor service $13904, $142ae, $145a2. The caller services each
 * captured actor in source order and supplies the live source globals. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u16 shadowrun_ai_service_timer, shadowrun_ai_service_contact;
u16 shadowrun_ai_waypoint_x, shadowrun_ai_waypoint_y;
u8 shadowrun_ai_service_direction, shadowrun_ai_service_pause;
u8 shadowrun_ai_service_supported, shadowrun_ai_service_result;
void shadowrun_ai_service_tick(void) {
    u16 dx; u16 dy; u16 t; u16 metric;
    shadowrun_ai_service_supported=0; shadowrun_ai_service_result=0;
    if (shadowrun_ai_kind!=11U || shadowrun_ai_flags!=37U || !(shadowrun_ai_equipment_flags & 32U) ||
        (shadowrun_ai_equipment_flags & 76U) || (shadowrun_ai_event_flags & 192U) ||
        shadowrun_ai_service_pause || shadowrun_ai_service_timer>20U ||
        (shadowrun_ai_combat_global!=0U && shadowrun_ai_combat_global!=65535U)) return;
    if (shadowrun_ai_service_timer) {
        shadowrun_ai_service_timer=shadowrun_ai_service_timer-1U;
        shadowrun_ai_service_supported=1; return;
    }
    /* Offscreen/contact-zero branch. Visibility, combat pursuit, alternate
       event handlers and near-waypoint advancement require separate lifts. */
    if (shadowrun_ai_service_contact) return;
    if (shadowrun_ai_combat_global) {
        shadowrun_ai_service_timer=20U;
        if (shadowrun_ai_animation<=60U || shadowrun_ai_animation>=32768U) {
            shadowrun_ai_callback=0xb45cUL; shadowrun_ai_service_result=2;
        } else shadowrun_ai_service_result=3;
        shadowrun_ai_service_supported=1; return;
    }
    if (shadowrun_ai_event_flags & 2U) return;
    if (!(shadowrun_ai_event_flags & 4U) && shadowrun_ai_collision_state!=4096U) return;
    if (shadowrun_ai_x>=shadowrun_ai_waypoint_x) dx=shadowrun_ai_x-shadowrun_ai_waypoint_x;
    else dx=shadowrun_ai_waypoint_x-shadowrun_ai_x;
    if (shadowrun_ai_y>=shadowrun_ai_waypoint_y) dy=shadowrun_ai_y-shadowrun_ai_waypoint_y;
    else dy=shadowrun_ai_waypoint_y-shadowrun_ai_y;
    if (dx>32767U || dy>32767U) return;
    if (dy>dx) {t=dx;dx=dy;dy=t;}
    metric=dx+((dy+1U)>>1);
    if (metric<480U) return;
    if (shadowrun_ai_animation>60U && shadowrun_ai_animation<32768U) {
        shadowrun_ai_service_timer=20U; shadowrun_ai_service_result=3;
        shadowrun_ai_service_supported=1; return;
    }
    shadowrun_linked_source_x=shadowrun_ai_x; shadowrun_linked_source_y=shadowrun_ai_y;
    shadowrun_linked_target_x=shadowrun_ai_waypoint_x; shadowrun_linked_target_y=shadowrun_ai_waypoint_y;
    shadowrun_linked_measure(); if (!shadowrun_linked_supported) return;
    if (shadowrun_ai_event_flags & 4U) {
        shadowrun_ai_event_flags=shadowrun_ai_event_flags & 251U;
        shadowrun_ai_service_direction=0;
        if (shadowrun_ai_waypoint_x>=shadowrun_ai_x) shadowrun_ai_service_direction|=1U;
        if (shadowrun_ai_waypoint_y>=shadowrun_ai_y) shadowrun_ai_service_direction|=2U;
    }
    shadowrun_ai_target_heading=shadowrun_linked_heading;
    shadowrun_ai_distance=shadowrun_linked_metric;
    shadowrun_ai_callback=0xb574UL;
    shadowrun_ai_service_timer=20U;
    shadowrun_ai_service_result=1; shadowrun_ai_service_supported=1;
}
