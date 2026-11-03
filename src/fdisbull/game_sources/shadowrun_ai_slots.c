/* Explicit calls to the qualified movement service. This is not a scheduler. */
u16 shadowrun_ai_slot_heading[7], shadowrun_ai_slot_target_heading[7];
u16 shadowrun_ai_slot_transition_heading[7], shadowrun_ai_slot_kind[7];
u16 shadowrun_ai_slot_distance[7], shadowrun_ai_slot_move_state[7];
u16 shadowrun_ai_slot_collision_state[7], shadowrun_ai_slot_speed[7];
u16 shadowrun_ai_slot_animation[7];
u32 shadowrun_ai_slot_callback[7];
u8 shadowrun_ai_slot_equipment_flags[7], shadowrun_ai_slot_attribute[7];
u8 shadowrun_ai_slot_max_hp[7];
u8 shadowrun_ai_slot_corners[28], shadowrun_ai_slot_status[7];
u16 shadowrun_ai_slot_service_timer[7], shadowrun_ai_slot_waypoint_x[7], shadowrun_ai_slot_waypoint_y[7];
u16 shadowrun_ai_slot_action_timer[7];
u8 shadowrun_ai_slot_direction[7], shadowrun_ai_slot_b3_unknown[7];
u8 shadowrun_ai_slot_visible_class[7], shadowrun_ai_slot_visibility_unknown[7];

/* 0 = absent, 1 = current after a qualified service, 2 = unknown after a
 * refused service. Caller must supply fresh source-derived scheduler inputs. */
void shadowrun_ai_service_slot(u8 slot) {
    u16 i;
    if (slot >= 7 || shadowrun_ai_slot_status[slot] != 1) return;
    shadowrun_ai_x=shadowrun_target_x[slot]; shadowrun_ai_y=shadowrun_target_y[slot];
    shadowrun_ai_heading=shadowrun_ai_slot_heading[slot];
    shadowrun_ai_target_heading=shadowrun_ai_slot_target_heading[slot];
    shadowrun_ai_transition_heading=shadowrun_ai_slot_transition_heading[slot];
    shadowrun_ai_kind=shadowrun_ai_slot_kind[slot];
    shadowrun_ai_distance=shadowrun_ai_slot_distance[slot];
    shadowrun_ai_animation=shadowrun_ai_slot_animation[slot];
    shadowrun_ai_collision_state=shadowrun_ai_slot_collision_state[slot];
    shadowrun_ai_callback=shadowrun_ai_slot_callback[slot];
    shadowrun_ai_flags=shadowrun_target_flags[slot];
    shadowrun_ai_flags_low=shadowrun_target_flags_low[slot];
    shadowrun_ai_equipment_flags=shadowrun_ai_slot_equipment_flags[slot];
    shadowrun_ai_event_flags=shadowrun_target_flags_b0[slot];
    shadowrun_ai_attribute=shadowrun_ai_slot_attribute[slot];
    shadowrun_ai_actor_tick();
    if (!shadowrun_ai_supported) { shadowrun_ai_slot_status[slot]=2; return; }
    shadowrun_target_x[slot]=shadowrun_ai_x; shadowrun_target_y[slot]=shadowrun_ai_y;
    shadowrun_ai_slot_heading[slot]=shadowrun_ai_heading;
    shadowrun_ai_slot_move_state[slot]=shadowrun_ai_move_state;
    shadowrun_ai_slot_collision_state[slot]=shadowrun_ai_collision_state;
    shadowrun_ai_slot_speed[slot]=shadowrun_ai_speed;
    shadowrun_ai_slot_animation[slot]=shadowrun_ai_animation;
    shadowrun_target_flags_b0[slot]=shadowrun_ai_event_flags;
    for (i=0; i<4; i=i+1) shadowrun_ai_slot_corners[(u16)slot*4U+i]=shadowrun_ai_corners[i];
}

/* Scheduler and movement are deliberately separate calls: the caller must
 * qualify source actor-service timing and supply the live global mode. */
void shadowrun_ai_schedule_slot(u8 slot) {
    if (slot >= 7 || shadowrun_ai_slot_status[slot] != 1) return;
    shadowrun_ai_x=shadowrun_target_x[slot]; shadowrun_ai_y=shadowrun_target_y[slot];
    shadowrun_ai_kind=shadowrun_ai_slot_kind[slot];
    shadowrun_ai_heading=shadowrun_ai_slot_heading[slot];
    shadowrun_ai_flags=shadowrun_target_flags[slot];
    shadowrun_ai_equipment_flags=shadowrun_ai_slot_equipment_flags[slot];
    shadowrun_ai_event_flags=shadowrun_target_flags_b0[slot];
    shadowrun_ai_animation=shadowrun_ai_slot_animation[slot];
    shadowrun_ai_collision_state=shadowrun_ai_slot_collision_state[slot];
    shadowrun_ai_target_heading=shadowrun_ai_slot_target_heading[slot];
    shadowrun_ai_distance=shadowrun_ai_slot_distance[slot];
    shadowrun_ai_callback=shadowrun_ai_slot_callback[slot];
    shadowrun_ai_service_timer=shadowrun_ai_slot_service_timer[slot];
    shadowrun_ai_service_contact=shadowrun_target_contact[slot];
    shadowrun_ai_waypoint_x=shadowrun_ai_slot_waypoint_x[slot];
    shadowrun_ai_waypoint_y=shadowrun_ai_slot_waypoint_y[slot];
    shadowrun_ai_service_direction=shadowrun_ai_slot_direction[slot];
    shadowrun_ai_service_tick();
    if (!shadowrun_ai_service_supported) {
        shadowrun_ai_visible_player_x=shadowrun_player_x;
        shadowrun_ai_visible_player_y=shadowrun_player_y;
        shadowrun_ai_visible_class=shadowrun_ai_slot_visible_class[slot];
        shadowrun_ai_visible_service();
        if (shadowrun_ai_visible_scratch_unknown) shadowrun_ai_slot_visibility_unknown[slot]=1;
    }
    if (!shadowrun_ai_service_supported) { shadowrun_ai_slot_status[slot]=2; return; }
    shadowrun_ai_slot_service_timer[slot]=shadowrun_ai_service_timer;
    shadowrun_ai_slot_target_heading[slot]=shadowrun_ai_target_heading;
    shadowrun_ai_slot_distance[slot]=shadowrun_ai_distance;
    shadowrun_ai_slot_callback[slot]=shadowrun_ai_callback;
    shadowrun_target_flags_b0[slot]=shadowrun_ai_event_flags;
    shadowrun_ai_slot_direction[slot]=shadowrun_ai_service_direction;
    if (shadowrun_ai_callback!=0xb574UL) shadowrun_ai_slot_status[slot]=2;
}

void shadowrun_ai_overlap_refresh(void) {
    u8 i;u8 n;
    shadowrun_ai_overlap_flags[0]=shadowrun_player_flags;
    shadowrun_ai_overlap_x[0]=shadowrun_player_x;shadowrun_ai_overlap_y[0]=shadowrun_player_y;
    shadowrun_ai_overlap_target[0]=0;
    if (shadowrun_target_selected<7U)
        shadowrun_ai_overlap_target[0]=0xff0400UL+(u32)shadowrun_target_selected*256UL;
    for(i=0;i<7;i=i+1) {
        n=i+3U;
        shadowrun_ai_overlap_flags[n]=shadowrun_target_flags[i];
        shadowrun_ai_overlap_x[n]=shadowrun_target_x[i];shadowrun_ai_overlap_y[n]=shadowrun_target_y[i];
        shadowrun_ai_overlap_attacker[n]=0;
        if (shadowrun_target_backlink[i]) shadowrun_ai_overlap_attacker[n]=0xff0100UL;
    }
}

void shadowrun_ai_outer_slot(u8 slot) {
    shadowrun_ai_outer_kind=shadowrun_ai_slot_kind[slot];
    shadowrun_ai_outer_flags=shadowrun_target_flags[slot];
    shadowrun_ai_outer_flags_low=shadowrun_target_flags_low[slot];
    shadowrun_ai_outer_hp=shadowrun_play_actor_hp[slot];
    shadowrun_ai_outer_max_hp=shadowrun_ai_slot_max_hp[slot];
    shadowrun_ai_outer_animation=shadowrun_ai_slot_animation[slot];
    shadowrun_ai_outer_action_timer=shadowrun_ai_slot_action_timer[slot];
    shadowrun_ai_outer_callback=shadowrun_ai_slot_callback[slot];
    shadowrun_ai_outer_movement_projection();
    if (!shadowrun_ai_outer_supported) {shadowrun_ai_slot_status[slot]=2;return;}
    shadowrun_ai_slot_action_timer[slot]=shadowrun_ai_outer_action_timer;
    if (shadowrun_ai_outer_b3_unknown) shadowrun_ai_slot_b3_unknown[slot]=1;
    if (shadowrun_ai_outer_schedule) shadowrun_ai_schedule_slot(slot);
    shadowrun_ai_service_slot(slot);
}

/* This separate diagnostic profile admits only ordinary directional input.
 * Combat, menus, and assisted placement need their actor scheduling qualified. */
void shadowrun_ai_frame(u8 pad) {
    u8 i;
    if (pad & 240U) {
        shadowrun_opening_frame(pad & 15U);
        shadowrun_play_refused=1;
        for (i=0;i<3;i=i+1) shadowrun_ai_slot_status[i]=2;
        return;
    }
    shadowrun_ai_overlap_refresh();
    shadowrun_ai_overlap_slot=0;
    shadowrun_ai_overlap_check_one();
    if (!shadowrun_ai_overlap_supported || (shadowrun_ai_overlap_flags[1]&1U) ||
        (shadowrun_ai_overlap_flags[2]&1U)) {
        shadowrun_play_refused=1;
        for (i=0;i<3;i=i+1) shadowrun_ai_slot_status[i]=2;
        return;
    }
    shadowrun_play_refused=0;
    shadowrun_opening_frame(pad);
    for (i=0;i<3;i=i+1) {
        if (shadowrun_ai_slot_status[i]!=1U) break;
        shadowrun_ai_overlap_refresh();
        shadowrun_ai_overlap_slot=i+3U;
        shadowrun_ai_overlap_check_one();
        if (!shadowrun_ai_overlap_supported) {shadowrun_ai_slot_status[i]=2;break;}
        shadowrun_ai_outer_slot(i);
        if (shadowrun_ai_slot_status[i]!=1U) break;
    }
    if (i<3U) for (i=0;i<3;i=i+1) shadowrun_ai_slot_status[i]=2;
    shadowrun_target_refresh();
    if (!shadowrun_target_supported)
        for (i=0;i<3;i=i+1) shadowrun_ai_slot_status[i]=2;
}
