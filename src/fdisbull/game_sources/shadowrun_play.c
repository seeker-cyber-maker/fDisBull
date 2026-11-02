/* Target-only modal control for a captured inventory. The grid lookup is the
 * separately qualified source leaf; item dispatch and equipment are unknown. */
u8 shadowrun_play_menu;
u8 shadowrun_play_debug;
u8 shadowrun_play_previous;
u8 shadowrun_play_action_gate;
u8 shadowrun_play_phase0,shadowrun_play_phase1,shadowrun_play_phase2,shadowrun_play_phase3;
u8 shadowrun_play_phase4,shadowrun_play_phase5,shadowrun_play_phase6,shadowrun_play_phase7;
/* Only item 44 is qualified for this composition. The original signed
 * +$F09F gate must be non-positive; all other item dispatch stays unknown. */
void shadowrun_play_equip(void) {
    u16 capacity;
    u16 percent;
    u16 rounds;
    shadowrun_play_refused = 1;
    if (shadowrun_play_action_gate > 0 && shadowrun_play_action_gate < 128) return;
    if (!shadowrun_inventory_valid) return;
    if (shadowrun_inventory_item == 2 && shadowrun_inventory_slot == 0) {
        /* Captured item 2 only. Refuse unqualified existing equipment or
         * invalid source domains. $36FC requires actor flag bit 0. */
        capacity = rom16(0, 0xd4594UL) >> 8;
        if (capacity != 12 || !(shadowrun_player_flags & 1U)) return;
        if (shadowrun_play_weapon_slot == 0 && shadowrun_play_weapon_item == 2) {
            if (shadowrun_play_ammo > capacity) return;
            percent = ((u16)shadowrun_play_ammo * 100U + capacity - 1U) / capacity;
            shadowrun_play_ammo = (u8)percent;
            shadowrun_play_weapon_slot = 127;
            shadowrun_play_weapon_item = 0;
        } else if (shadowrun_play_weapon_slot == 127 && shadowrun_play_weapon_item == 0) {
            if (shadowrun_play_ammo > 100) return;
            percent = shadowrun_play_ammo;
            rounds = (percent * capacity + 50U) / 100U;
            shadowrun_play_weapon_aux = 0;
            shadowrun_play_weapon_slot = 0;
            shadowrun_play_weapon_item = 2;
            shadowrun_play_ammo = (u8)rounds;
        } else return;
        shadowrun_play_refused = 0;
        return;
    }
    if (shadowrun_inventory_item != 44) return;
    if (shadowrun_inventory_slot == 0) shadowrun_inventory_selected_phase=shadowrun_play_phase0;
    if (shadowrun_inventory_slot == 1) shadowrun_inventory_selected_phase=shadowrun_play_phase1;
    if (shadowrun_inventory_slot == 2) shadowrun_inventory_selected_phase=shadowrun_play_phase2;
    if (shadowrun_inventory_slot == 3) shadowrun_inventory_selected_phase=shadowrun_play_phase3;
    if (shadowrun_inventory_slot == 4) shadowrun_inventory_selected_phase=shadowrun_play_phase4;
    if (shadowrun_inventory_slot == 5) shadowrun_inventory_selected_phase=shadowrun_play_phase5;
    if (shadowrun_inventory_slot == 6) shadowrun_inventory_selected_phase=shadowrun_play_phase6;
    if (shadowrun_inventory_slot == 7) shadowrun_inventory_selected_phase=shadowrun_play_phase7;
    shadowrun_inventory_armor_branch();
    if (shadowrun_inventory_slot == 0) shadowrun_play_phase0=shadowrun_inventory_selected_phase;
    if (shadowrun_inventory_slot == 1) shadowrun_play_phase1=shadowrun_inventory_selected_phase;
    if (shadowrun_inventory_slot == 2) shadowrun_play_phase2=shadowrun_inventory_selected_phase;
    if (shadowrun_inventory_slot == 3) shadowrun_play_phase3=shadowrun_inventory_selected_phase;
    if (shadowrun_inventory_slot == 4) shadowrun_play_phase4=shadowrun_inventory_selected_phase;
    if (shadowrun_inventory_slot == 5) shadowrun_play_phase5=shadowrun_inventory_selected_phase;
    if (shadowrun_inventory_slot == 6) shadowrun_play_phase6=shadowrun_inventory_selected_phase;
    if (shadowrun_inventory_slot == 7) shadowrun_play_phase7=shadowrun_inventory_selected_phase;
    shadowrun_play_refused = 0;
}
void shadowrun_play_frame(u8 pad) {
    u8 pressed;
    pressed = pad & (shadowrun_play_previous ^ 255U);
    shadowrun_play_previous = pad;
    shadowrun_play_refused = 0;
    if (shadowrun_play_shot_pending || shadowrun_field_motion_state==1 || shadowrun_linked_motion_state==1) {
        if (pad & 176U) {
            shadowrun_play_refused=1;
            if (shadowrun_play_shot_pending) {
                shadowrun_play_shot_pending=0;
                shadowrun_play_shot_armed=0;
                shadowrun_play_shot_timer=37;
                shadowrun_opening_status=2;
                return;
            }
            /* Do not move or mutate the captured actor during the finite flight. */
            shadowrun_play_shot_step(0,0);
        } else shadowrun_play_shot_step(pad,pressed);
        if ((pad & 15U) && !shadowrun_play_refused) {
            shadowrun_opening_frame(pad & 15U);
        } else shadowrun_opening_status=9;
        return;
    }
    if (shadowrun_play_debug) {
        if (pressed & 16U || pressed & 32U) {
            shadowrun_play_debug=0;
            shadowrun_pad_held=0;
            shadowrun_opening_status=0;
            return;
        }
        if ((pressed & 1U) && shadowrun_debug_y>=512U) shadowrun_debug_y-=512U;
        if ((pressed & 2U) && shadowrun_debug_y<22016U) shadowrun_debug_y+=512U;
        if ((pressed & 4U) && shadowrun_debug_x>=512U) shadowrun_debug_x-=512U;
        if ((pressed & 8U) && shadowrun_debug_x<32256U) shadowrun_debug_x+=512U;
        if (pressed & 64U) {
            shadowrun_debug_assisted=1;
            shadowrun_debug_recenter=1;
            shadowrun_debug_place();
            if (shadowrun_debug_result==1) shadowrun_play_debug=0;
            else shadowrun_play_refused=1;
        }
        shadowrun_opening_status=8;
        return;
    }
    if (shadowrun_play_menu) {
        if (pressed & 128U || pressed & 16U) {
            shadowrun_play_menu = 0;
            shadowrun_pad_held = 0;
            shadowrun_opening_status = 0;
            return;
        }
        if ((pressed & 1U) && shadowrun_inventory_row > 0) shadowrun_inventory_row--;
        if ((pressed & 2U) && shadowrun_inventory_row < 3) shadowrun_inventory_row++;
        if (pressed & 4U) shadowrun_inventory_column = 0;
        if (pressed & 8U) shadowrun_inventory_column = 1;
        shadowrun_inventory_select();
        if (pressed & 64U) shadowrun_play_equip();
        shadowrun_opening_status = 7;
        return;
    }
    if (pressed & 16U) {
        /* Captured actor records are frozen target-side; no NPC AI is implied. */
        shadowrun_target_item=shadowrun_play_weapon_item;
        shadowrun_target_equipped_slot=shadowrun_play_weapon_slot;
        shadowrun_target_refresh();
        if (shadowrun_target_supported) shadowrun_target_cycle();
        if (shadowrun_target_supported && !shadowrun_target_result) shadowrun_play_refused=1;
        shadowrun_opening_status=10;
        if (!shadowrun_target_supported) shadowrun_opening_status=2;
        return;
    }
    if (pressed & 32U) {
        shadowrun_play_debug=1;
        shadowrun_debug_x=(shadowrun_player_x & 0xfe00U)+256U;
        shadowrun_debug_y=(shadowrun_player_y & 0xfe00U)+256U;
        shadowrun_debug_result=0;
        shadowrun_opening_status=8;
        return;
    }
    if (pressed & 128U) {
        shadowrun_play_menu = 1;
        shadowrun_inventory_select();
        shadowrun_opening_status = 7;
        return;
    }
    if (shadowrun_play_shot_armed || (pressed & 64U)) {
        shadowrun_play_shot_step(pad,pressed);
        if (shadowrun_play_refused) {shadowrun_opening_status=2;return;}
        if (shadowrun_play_shot_pending || shadowrun_field_motion_state==1 || (pad & 64U)) {
            shadowrun_opening_status=9;return;
        }
    }
    shadowrun_opening_frame(pad);
}
