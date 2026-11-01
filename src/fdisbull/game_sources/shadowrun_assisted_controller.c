/* Assisted controller preparation. Status 2 is a hard boundary: do not
 * advance stale actors or silently skip an unmodeled combat continuation. */
u8 shadowrun_arena_frame_status,shadowrun_arena_previous_pad,shadowrun_arena_player_pending;
void shadowrun_arena_frame(u8 pad) {
    u8 pressed;u8 was_ready;u8 had_burst;u8 hostile_idle_pass;u8 hostile_idle_zero;u8 hostile_moving_idle;u8 hostile_positive_pass;u8 relaunched;u8 pursuing;u8 recovered_direction;
    pressed=pad & (shadowrun_arena_previous_pad ^ 255U);
    shadowrun_arena_previous_pad=pad;
    if (shadowrun_arena_frame_status==3U) {shadowrun_play_refused=1;return;}
    if (shadowrun_arena_frame_status==2U || shadowrun_arena_profile!=1U) {
        shadowrun_arena_frame_status=2;shadowrun_play_refused=1;return;
    }
    shadowrun_arena_frame_status=1;
    was_ready=shadowrun_arena_player_ready;
    had_burst=shadowrun_arena_burst_active;
    hostile_idle_pass=0;hostile_idle_zero=0;hostile_moving_idle=0;hostile_positive_pass=0;relaunched=0;pursuing=0;recovered_direction=0;shadowrun_arena_player_hit_event=0;
    if (shadowrun_hostile_motion_continuation_required && !shadowrun_arena_burst_active && !shadowrun_arena_hostile_pose_ready) {
        shadowrun_arena_frame_status=2;shadowrun_play_refused=1;return;
    }
    if (pad & 32U) {shadowrun_play_refused=1;return;}
    if (shadowrun_linked_motion_state==1U && (pad & 240U)) {
        pad &= 15U;pressed &= 15U;shadowrun_play_refused=1;
    }
    if (shadowrun_arena_player_ready && (shadowrun_play_menu || (pressed & 128U))) {
        /* Target adaptation: the isolated arena is paused in inventory. */
        shadowrun_play_frame(pad);
        shadowrun_arena_armor=shadowrun_inventory_equipped_armor;
        return;
    }
    if (shadowrun_linked_motion_state==1U && shadowrun_arena_burst_active &&
        (!(shadowrun_burst_flags_low&8U) || (shadowrun_burst_anim_word&32768U))) {
        shadowrun_arena_frame_status=2;shadowrun_play_refused=1;return;
    }
    if (!shadowrun_arena_player_ready) {
        shadowrun_reaction_step();
        if (!shadowrun_reaction_step_supported) {shadowrun_arena_frame_status=2;shadowrun_play_refused=1;return;}
        if (shadowrun_reaction_step_result==2U) {
            if (pad==64U && shadowrun_arena_player_pending && shadowrun_reaction_action_timer==65535U) {
                shadowrun_reaction_input_flags=64U;shadowrun_reaction_global_e6=65535U;
                shadowrun_reaction_resume_held();
                if (!shadowrun_reaction_held_supported) {shadowrun_arena_frame_status=2;shadowrun_play_refused=1;return;}
            } else if (!pad && !shadowrun_arena_player_pending) {
                shadowrun_reaction_input_flags=0;shadowrun_reaction_input_heading=65535U;shadowrun_reaction_global_e6=0;
                if (shadowrun_arena_moving_profile && shadowrun_reaction_speed==16U) {
                    shadowrun_reaction_normal_sprite_speed=28;shadowrun_reaction_resume_idle_walk();
                    if (!shadowrun_reaction_idle_walk_supported) {shadowrun_arena_frame_status=2;shadowrun_play_refused=1;return;}
                } else {
                    shadowrun_reaction_resume_idle();
                    if (!shadowrun_reaction_resume_supported) {shadowrun_arena_frame_status=2;shadowrun_play_refused=1;return;}
                }
            } else if (shadowrun_arena_moving_profile && pad==4U && !shadowrun_arena_player_pending) {
                shadowrun_reaction_input_flags=4;shadowrun_reaction_input_heading=0xc000U;
                shadowrun_reaction_resume_direction();
                if (!shadowrun_reaction_direction_supported) {shadowrun_arena_frame_status=2;shadowrun_play_refused=1;return;}
                recovered_direction=1;
            } else {shadowrun_arena_frame_status=2;shadowrun_play_refused=1;return;}
            shadowrun_arena_player_ready=1;shadowrun_play_shot_eligible=1;
            shadowrun_arena_player_sprite_current=1;
            shadowrun_play_shot_timer=shadowrun_reaction_action_timer;
            shadowrun_player_flags_low=shadowrun_reaction_flags_low;
            shadowrun_player_callback=shadowrun_reaction_callback;
            if (shadowrun_arena_moving_profile) {
                shadowrun_anim_increment=shadowrun_reaction_increment;shadowrun_anim_accumulator=shadowrun_reaction_accumulator;
                shadowrun_anim_threshold=shadowrun_reaction_threshold;shadowrun_anim_index=shadowrun_reaction_index;
            }
            if (recovered_direction) {
                shadowrun_player_target_heading=shadowrun_reaction_target_heading;
                shadowrun_opening_frame(pad & 15U);
            }
        }
    } else if (shadowrun_linked_motion_state==1U) shadowrun_opening_frame(pad & 15U);
    else shadowrun_play_frame(pad & 191U);
    if (was_ready && (shadowrun_opening_status==2U || shadowrun_opening_status==3U || shadowrun_opening_status==4U)) {
        shadowrun_arena_frame_status=2;shadowrun_play_refused=1;return;
    }
    if (shadowrun_arena_moving_profile && (was_ready || recovered_direction) && (pad & 15U) &&
        !shadowrun_player_combat_walk_supported) {shadowrun_arena_frame_status=2;shadowrun_play_refused=1;return;}
    if ((was_ready || recovered_direction) && shadowrun_arena_moving_profile) {
        shadowrun_party_kind=3;shadowrun_party_heading=shadowrun_player_heading;
        shadowrun_party_transition_heading=shadowrun_player_transition_heading;
        shadowrun_party_callback=shadowrun_player_callback;shadowrun_party_flags_low=shadowrun_player_flags_low;
        shadowrun_party_speed=shadowrun_player_step_timer;
        if (!shadowrun_party_speed) shadowrun_party_speed=shadowrun_reaction_speed;
        shadowrun_reaction_speed=shadowrun_party_speed;
        shadowrun_party_pose_tick();
        if (!shadowrun_party_clock_supported) {shadowrun_arena_frame_status=2;shadowrun_play_refused=1;return;}
        shadowrun_reaction_increment=shadowrun_anim_increment;shadowrun_reaction_accumulator=shadowrun_anim_accumulator;
        shadowrun_reaction_threshold=shadowrun_anim_threshold;shadowrun_reaction_index=shadowrun_anim_index;
        shadowrun_arena_player_sprite_current=1;
    } else if (was_ready && (pad & 15U)) shadowrun_arena_player_sprite_current=0;
    if (shadowrun_linked_motion_state==1U) {
        shadowrun_arena_player_step();
        if (!shadowrun_arena_player_supported) {shadowrun_arena_frame_status=2;shadowrun_play_refused=1;return;}
    }
    if (was_ready && shadowrun_play_shot_timer<32768U) shadowrun_play_shot_timer-=1U;
    if (was_ready && (pressed & 64U)) shadowrun_arena_player_pending=1;
    if (shadowrun_play_shot_timer>=32768U && !shadowrun_arena_player_pending && !(pad & 64U))
        shadowrun_play_shot_timer=51;
    if (was_ready && shadowrun_arena_player_ready && shadowrun_play_shot_timer>=32768U && (shadowrun_arena_player_pending || (pad & 64U))) {
        if ((shadowrun_arena_burst_active && (!(shadowrun_burst_flags_low&8U) ||
            (shadowrun_burst_anim_word&32768U))) || shadowrun_linked_motion_state==1U) shadowrun_play_refused=1;
        else {
            shadowrun_arena_player_launch();
            if (!shadowrun_arena_player_supported) {shadowrun_arena_frame_status=2;shadowrun_play_refused=1;return;}
            shadowrun_arena_player_pending=0;
            shadowrun_reaction_global_e6=0;
            shadowrun_play_shot_timer=51;
        }
    }
    if (shadowrun_arena_moving_profile && !shadowrun_arena_hostile_pose_ready &&
        (!shadowrun_arena_pursuit_started || shadowrun_pursuit_route_service_timer)) {
        shadowrun_arena_pursuit_step();pursuing=1;
        if (!shadowrun_arena_supported) {shadowrun_arena_frame_status=2;shadowrun_play_refused=1;return;}
    }
    if (shadowrun_arena_hostile_pose_ready) {
        shadowrun_attack_x=shadowrun_hostile_x;shadowrun_attack_y=shadowrun_hostile_y;
        shadowrun_attack_player_x=shadowrun_player_x;shadowrun_attack_player_y=shadowrun_player_y;
        shadowrun_attack_hp=shadowrun_play_actor_hp[0];shadowrun_attack_ammo=shadowrun_hostile_ammo;
        if (shadowrun_attack_callback==0xb3eeUL) {
            if (shadowrun_attack_animation & 32768U) {
                if (shadowrun_arena_moving_profile) {
                    shadowrun_hostile_moving_pose_step();
                    if (!shadowrun_moving_pose_supported) {shadowrun_arena_frame_status=2;shadowrun_play_refused=1;return;}
                }
                else if (!shadowrun_attack_counter) shadowrun_hostile_attack_zero_counter_step();
                else if (shadowrun_attack_action_timer==65535U) shadowrun_hostile_attack_expired_step();
                else shadowrun_hostile_attack_step();
                if (!shadowrun_attack_supported) {shadowrun_arena_frame_status=2;shadowrun_play_refused=1;return;}
            } else {
                hostile_positive_pass=1;
            }
        } else if (shadowrun_attack_callback==0xb45cUL) {
            if (shadowrun_arena_moving_profile) {
                shadowrun_hostile_moving_idle_step();hostile_moving_idle=1;
                if (!shadowrun_moving_idle_supported) {
                    shadowrun_arena_hostile_relaunch();
                    if (!shadowrun_arena_supported) {shadowrun_arena_frame_status=2;shadowrun_play_refused=1;return;}
                    relaunched=1;
                }
            } else if (!shadowrun_attack_counter) {
                shadowrun_hostile_idle_zero_counter_step();hostile_idle_zero=1;
            } else shadowrun_hostile_idle_actor_pass();
            if (hostile_moving_idle) { }
            else if (!shadowrun_hostile_idle_supported) {
                shadowrun_arena_hostile_relaunch();
                if (!shadowrun_arena_supported) {shadowrun_arena_frame_status=2;shadowrun_play_refused=1;return;}
                relaunched=1;
            } else if (!hostile_idle_zero) hostile_idle_pass=1;
        } else {shadowrun_arena_frame_status=2;shadowrun_play_refused=1;return;}
    }
    if (pursuing) shadowrun_arena_supported=1;
    else if (relaunched) shadowrun_arena_supported=1;
    else if (shadowrun_arena_burst_active) shadowrun_arena_burst_step();
    else if (shadowrun_hostile_motion_state==1U) shadowrun_arena_projectile_step();
    else if (shadowrun_arena_hostile_pose_ready) shadowrun_arena_supported=1;
    else shadowrun_arena_same_loop();
    if (shadowrun_arena_depleted) {shadowrun_arena_frame_status=3;shadowrun_play_refused=1;return;}
    if (hostile_positive_pass && shadowrun_arena_supported) {
        if (shadowrun_arena_player_hit_event) shadowrun_hostile_positive_reentry_step();
        else shadowrun_hostile_attack_positive_step();
        if (!shadowrun_attack_positive_supported) shadowrun_arena_supported=0;
    }
    if (!shadowrun_arena_hostile_pose_ready && !had_burst && !shadowrun_arena_burst_active && shadowrun_arena_supported && shadowrun_hostile_motion_state==2U) {
        shadowrun_arena_burst_prepare();
        if (shadowrun_arena_supported) shadowrun_arena_burst_first_sprite();
        if (shadowrun_arena_supported) {
            shadowrun_reaction_sprite_only();
            if (!shadowrun_reaction_sprite_supported) shadowrun_arena_supported=0;
        }
        if (shadowrun_arena_supported) {
            shadowrun_arena_hostile_first_pose();
            if (!shadowrun_arena_hostile_pose_ready) shadowrun_arena_supported=0;
        }
    }
    if (hostile_idle_pass && shadowrun_arena_supported) {
        if (shadowrun_arena_player_hit_event) shadowrun_hostile_idle_actor_pass();
        if (!shadowrun_hostile_idle_supported) shadowrun_arena_supported=0;
        if (shadowrun_arena_supported) {
            shadowrun_hostile_idle_sprite_pass();
            if (!shadowrun_hostile_idle_supported) shadowrun_arena_supported=0;
        }
    }
    if (hostile_idle_zero && shadowrun_arena_player_hit_event) shadowrun_arena_supported=0;
    if (hostile_moving_idle && shadowrun_arena_player_hit_event) shadowrun_arena_supported=0;
    if (shadowrun_arena_moving_profile && (was_ready || recovered_direction) && shadowrun_arena_player_ready && shadowrun_arena_supported) {
        shadowrun_party_clock_tick();
        if (!shadowrun_party_clock_supported) shadowrun_arena_supported=0;
    }
    if (!shadowrun_arena_burst_active && !had_burst && shadowrun_hostile_motion_continuation_required && !shadowrun_arena_hostile_pose_ready) shadowrun_arena_supported=0;
    if (!shadowrun_arena_supported) {shadowrun_arena_frame_status=2;shadowrun_play_refused=1;}
}
