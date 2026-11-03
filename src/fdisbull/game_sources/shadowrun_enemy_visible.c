/* Bounded source $13EF4/$13F76 contact-visible movement projection.  The
 * visibility projectile and collision temporaries are deliberately omitted;
 * the caller must regard those scratch globals as unknown afterwards. */
u16 shadowrun_ai_visible_player_x,shadowrun_ai_visible_player_y;
u8 shadowrun_ai_visible_class,shadowrun_ai_visible_alert;
u8 shadowrun_ai_visible_supported,shadowrun_ai_visible_scratch_unknown;
void shadowrun_ai_visible_service(void) {
    u16 contact;u16 delta;
    shadowrun_ai_visible_supported=0;shadowrun_ai_visible_scratch_unknown=0;
    if (!shadowrun_ai_service_contact || shadowrun_ai_service_timer ||
        shadowrun_ai_combat_global || shadowrun_ai_visible_class>2U ||
        shadowrun_ai_visible_alert || shadowrun_ai_flags!=37U) return;
    if (!(shadowrun_ai_equipment_flags & 1U)) {
        shadowrun_linked_source_x=shadowrun_ai_x;shadowrun_linked_source_y=shadowrun_ai_y;
        shadowrun_linked_target_x=shadowrun_ai_visible_player_x;shadowrun_linked_target_y=shadowrun_ai_visible_player_y;
        shadowrun_linked_measure();if (!shadowrun_linked_supported) return;
        delta=shadowrun_ai_heading-shadowrun_linked_heading;
        if (delta & 32768U) delta=0U-delta;
        /* Even clear sight cannot enter the awareness branch at this angle;
         * blocked sight also returns with the same projected actor effects. */
        if (delta<16384U) return;
        shadowrun_ai_visible_scratch_unknown=1;
    }
    contact=shadowrun_ai_service_contact;
    shadowrun_ai_service_contact=0;
    shadowrun_ai_service_tick();
    shadowrun_ai_service_contact=contact;
    if (!shadowrun_ai_service_supported) return;
    shadowrun_ai_visible_supported=1;
}
