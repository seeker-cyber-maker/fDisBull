/* Target adapter: captured player combat attributes, frozen captured NPCs,
 * original timer/latch arithmetic and one active projectile at a time. */
u8 shadowrun_play_refused;
u8 shadowrun_play_weapon_slot,shadowrun_play_weapon_item,shadowrun_play_ammo,shadowrun_play_weapon_aux;
u8 shadowrun_play_shot_eligible,shadowrun_play_shot_pending,shadowrun_play_shot_used,shadowrun_play_shot_armed;
u16 shadowrun_play_shot_timer;
u8 shadowrun_play_shot_admit(void) {
    if (!shadowrun_play_shot_eligible || shadowrun_player_flags!=15U || shadowrun_player_kind!=3U ||
        shadowrun_play_weapon_slot!=0U || shadowrun_play_weapon_item!=2U ||
        shadowrun_play_ammo==0U || shadowrun_play_ammo>12U) return 0;
    if (shadowrun_target_selected<3U) {
        if (!(shadowrun_target_flags[shadowrun_target_selected]&1U) || !shadowrun_play_actor_hp[shadowrun_target_selected]) return 0;
        return 1;
    }
    /* The no-target projectile profile is only qualified at this state. */
    if (shadowrun_target_selected!=255U || shadowrun_player_x!=15584U || shadowrun_player_y!=11210U ||
        shadowrun_player_heading!=32768U) return 0;
    return 1;
}
void shadowrun_play_shot_step(u8 pad,u8 pressed) {
    u16 old_rng,old_ammo;
    if (!shadowrun_play_shot_armed) {
        if (!(pressed & 64U)) return;
        if (!shadowrun_play_shot_admit()) {shadowrun_play_refused=1;return;}
        shadowrun_play_shot_armed=1;
    }
    if (shadowrun_field_motion_state==1) {
        shadowrun_field_captured_tick();
        if (!shadowrun_field_supported) {shadowrun_field_motion_state=0;shadowrun_play_refused=1;}
    }
    if (shadowrun_linked_motion_state==1) {
        shadowrun_actors_tick();
        if (!shadowrun_field_supported) {shadowrun_linked_motion_state=0;shadowrun_play_refused=1;}
    }
    if (shadowrun_play_shot_timer<32768U) shadowrun_play_shot_timer--;
    if (shadowrun_play_shot_timer<32768U) {
        if (pressed & 64U) shadowrun_play_shot_pending=1;
        return;
    }
    if (shadowrun_play_shot_pending || (pad & 64U)) {
        shadowrun_play_shot_pending=0;
        if (shadowrun_field_motion_state==1 || shadowrun_linked_motion_state==1) {
            shadowrun_play_shot_pending=1;return;
        }
        if (!shadowrun_play_shot_admit()) {shadowrun_play_refused=1;shadowrun_play_shot_timer=51;return;}
        old_rng=shadowrun_field_rng;old_ammo=shadowrun_play_ammo;
        shadowrun_field_captured_profile=1;shadowrun_field_path_profile=1;
        shadowrun_field_actor_index=0;shadowrun_field_item=2;
        shadowrun_field_equipped_slot=0;shadowrun_field_source_flags=15;
        shadowrun_field_ammo=shadowrun_play_ammo;shadowrun_field_slots_busy=0;
        if (shadowrun_target_selected<3U) {
            shadowrun_actors_profile=1;shadowrun_linked_profile=1;
            shadowrun_linked_source_x=shadowrun_player_x;shadowrun_linked_source_y=shadowrun_player_y;
            shadowrun_actors_launch();
        } else {
            shadowrun_field_target_x=512;shadowrun_field_target_y=512;
            shadowrun_field_target_flags=0;shadowrun_field_target_flags_b0=0;shadowrun_field_target_flags_9e=0;
            shadowrun_field_target_hp=50;shadowrun_field_target_a=5;shadowrun_field_target_b=5;
            shadowrun_field_target_c=5;shadowrun_field_target_posture=0;
            shadowrun_field_captured_launch();
        }
        if (shadowrun_field_supported) {
            shadowrun_play_ammo=shadowrun_field_ammo;shadowrun_play_shot_used++;
        } else {
            shadowrun_field_rng=old_rng;shadowrun_play_ammo=(u8)old_ammo;
            shadowrun_field_motion_state=0;shadowrun_linked_motion_state=0;shadowrun_play_refused=1;
        }
    }
    /* Captured $ABFC result; not generalized to other actor attributes. */
    shadowrun_play_shot_timer=51;
}
