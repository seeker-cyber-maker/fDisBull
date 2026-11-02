/* Normal-player wall handling from BADE/B732/BB86/B442. Negative initial
 * event statuses are explicitly left for the unresolved event dispatcher. */
u16 shadowrun_player_transition_heading;
u16 shadowrun_player_animation_selector;
u16 shadowrun_scene_mode;
u16 shadowrun_event_mode;
u16 shadowrun_fallback_direction;
u8 shadowrun_unresolved_event;
u8 shadowrun_player_walk_result;

void shadowrun_player_copy_corners(void) {
    u8 i;
    for (i=0;i<4;i=i+1) shadowrun_player_record_corners[i]=shadowrun_probe_corners[i];
}

u16 shadowrun_player_attempt(u8 ordinal) {
    u16 offset;
    offset=(u16)ordinal << 2;
    shadowrun_player_direction=(u16)ordinal << 1;
    shadowrun_player_proposed_x=(u16)(shadowrun_player_x+rom16(0,0xbec2UL+offset));
    shadowrun_player_proposed_y=(u16)(shadowrun_player_y+rom16(0,0xbec4UL+offset));
    shadowrun_fixed_x=shadowrun_player_proposed_x;
    shadowrun_fixed_y=shadowrun_player_proposed_y;
    shadowrun_collision_check();
    shadowrun_player_copy_corners();
    if ((shadowrun_collision_status & 0x8000U) && !(shadowrun_player_flags & 2U))
        return 127U;
    return shadowrun_collision_status;
}

u16 shadowrun_player_fallback_attempt(u8 ordinal) {
    u16 result;
    u16 event;
    result=shadowrun_player_attempt(ordinal);
    if (!(result & 0x8000U)) return result;
    event=result & 31U;
    if (shadowrun_global_special_mode != 0 || event >= 24U) return 127U;
    if ((shadowrun_scene_mode == 20U || shadowrun_event_mode == 2U) &&
        event >= 2U && event <= 5U) return 127U;
    return result;
}

void shadowrun_player_stop(void) {
    u16 rotated;
    u16 ordinal;
    shadowrun_player_event_flags &= 0xfdU;
    shadowrun_player_heading=shadowrun_player_target_heading;
    shadowrun_player_callback=0xb45cUL;
    shadowrun_player_flags_low |= 1U;
    shadowrun_player_move_state=0;
    rotated=(u16)((shadowrun_player_heading << 3) | (shadowrun_player_heading >> 13));
    if (rotated & 0x8000U) rotated=(u16)(rotated+1U);
    ordinal=rotated & 7U;
    shadowrun_player_animation_selector=rom16(0,0xc052UL+(ordinal << 1));
    shadowrun_fixed_x=shadowrun_player_x;
    shadowrun_fixed_y=shadowrun_player_y;
    shadowrun_collision_check();
    shadowrun_player_copy_corners();
    shadowrun_player_walk_result=2;
}

void shadowrun_player_walk_bounded(void) {
    u16 status;
    u16 rotated;
    u8 ordinal;
    u8 first;
    u8 second;
    u8 first_dir;
    u8 second_dir;
    u8 first_clear;
    u8 second_clear;
    u8 diagonal;
    shadowrun_player_walk_result=0;
    shadowrun_unresolved_event=0;
    shadowrun_player_propose();
    if (!shadowrun_player_proposal_supported) return;
    shadowrun_fixed_x=shadowrun_player_proposed_x;
    shadowrun_fixed_y=shadowrun_player_proposed_y;
    shadowrun_collision_check();
    shadowrun_player_copy_corners();
    status=shadowrun_collision_status;
    if (status & 0x8000U) {
        if (!(shadowrun_player_flags & 2U)) status=127;
        else {
            shadowrun_unresolved_event=(u8)status;
            shadowrun_player_walk_result=3;
            return;
        }
    }
    if (status==0) {
        shadowrun_player_collision_movement_state=0x1000U;
        shadowrun_player_event_flags &= 0xfeU;
        shadowrun_player_x=shadowrun_player_proposed_x;
        shadowrun_player_y=shadowrun_player_proposed_y;
        shadowrun_player_walk_result=1;
        return;
    }
    rotated=(u16)((shadowrun_player_heading << 3) | (shadowrun_player_heading >> 13));
    diagonal=(shadowrun_player_heading & 0x3fffU) != 0;
    if (diagonal) {
        ordinal=(u8)(rotated & 6U);
        shadowrun_fallback_direction=ordinal;
        shadowrun_player_collision_movement_state=ordinal;
        status=shadowrun_player_fallback_attempt(ordinal);
        if (status!=0 && !(status & 0x8000U)) {
            ordinal=(u8)((ordinal+2U)&7U);
            status=shadowrun_player_fallback_attempt(ordinal);
        }
    } else {
        ordinal=(u8)(rotated & 6U);
        if (ordinal==0) {first=0;second=1;first_dir=6;second_dir=2;}
        else if (ordinal==2) {first=1;second=3;first_dir=0;second_dir=4;}
        else if (ordinal==4) {first=2;second=3;first_dir=6;second_dir=2;}
        else {first=0;second=2;first_dir=0;second_dir=4;}
        first_clear=(shadowrun_probe_corners[first]==0 || (shadowrun_probe_corners[first]&0x80U));
        second_clear=(shadowrun_probe_corners[second]==0 || (shadowrun_probe_corners[second]&0x80U));
        if (first_clear) status=shadowrun_player_fallback_attempt(first_dir);
        else if (second_clear) status=shadowrun_player_fallback_attempt(second_dir);
        else status=127;
    }
    if (status==0 || (status & 0x8000U)) {
        if (diagonal) {
            shadowrun_player_transition_heading=(u16)((shadowrun_player_direction >> 4) |
                                                      (shadowrun_player_direction << 12));
            shadowrun_player_flags_low |= 4U;
        }
        shadowrun_player_event_flags &= 0xfeU;
        shadowrun_player_x=shadowrun_player_proposed_x;
        shadowrun_player_y=shadowrun_player_proposed_y;
        shadowrun_player_walk_result=1;
        return;
    }
    shadowrun_player_collision_movement_state=0xffffU;
    shadowrun_player_stop();
}
