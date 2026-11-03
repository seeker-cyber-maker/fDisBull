/* Source-bound prompt selection boundary; caller supplies record targets.
   Does not execute commands, decode text, or own the game display. */
typedef unsigned char u8;
typedef unsigned long u32;
u8 shadowrun_dialogue_buttons;
u8 shadowrun_dialogue_option_count;
u8 shadowrun_dialogue_terminal;
u32 shadowrun_dialogue_target_a;
u32 shadowrun_dialogue_target_b;
u32 shadowrun_dialogue_target_c;
/* 0 wait, 1 opaque command, 2 record, 3 terminal, 4 unsupported. */
u8 shadowrun_dialogue_result;
u32 shadowrun_dialogue_value;
void shadowrun_dialogue_select(void) {
    u32 target;
    shadowrun_dialogue_result = 0;
    shadowrun_dialogue_value = 0;
    if (shadowrun_dialogue_terminal) {
        shadowrun_dialogue_result = 3;
        shadowrun_dialogue_value = 0xfbUL;
        return;
    }
    if (shadowrun_dialogue_option_count < 1 || shadowrun_dialogue_option_count > 3) {
        shadowrun_dialogue_result = 4;
        return;
    }
    if (shadowrun_dialogue_buttons & 64U) target = shadowrun_dialogue_target_a;
    else if (shadowrun_dialogue_buttons & 16U) {
        if (shadowrun_dialogue_option_count < 2) return;
        target = shadowrun_dialogue_target_b;
    } else if (shadowrun_dialogue_buttons & 32U) {
        if (shadowrun_dialogue_option_count < 3) return;
        target = shadowrun_dialogue_target_c;
    } else return;
    if (target & 0x80000000UL) {
        shadowrun_dialogue_result = 4;
        return;
    }
    shadowrun_dialogue_value = target;
    if (target < 0xfaUL) shadowrun_dialogue_result = 1;
    else shadowrun_dialogue_result = 2;
}

/* 0x21458: caller supplies original wallet and byte charge/marker. */
u32 shadowrun_dialogue_wallet;
u8 shadowrun_dialogue_charge;
u32 shadowrun_dialogue_response;
void shadowrun_dialogue_pay(void) {
    u32 balance;
    balance = shadowrun_dialogue_wallet - shadowrun_dialogue_charge;
    if (balance & 0x80000000UL) {
        shadowrun_dialogue_response = 0xf5af8UL;
        return;
    }
    shadowrun_dialogue_wallet = balance;
    shadowrun_dialogue_charge = 255U;
    shadowrun_dialogue_response = 0xf5ab8UL;
}

/* Selected source command leaves. Unknown commands remain unsupported. */
u32 shadowrun_dialogue_flag30;
u8 shadowrun_dialogue_flag27;
void shadowrun_dialogue_dispatch(void) {
    u32 command;
    if (shadowrun_dialogue_result != 1) return;
    command = shadowrun_dialogue_value;
    shadowrun_dialogue_result = 4;
    shadowrun_dialogue_value = 0;
    if (command == 6UL) {
        shadowrun_dialogue_pay();
        shadowrun_dialogue_value = shadowrun_dialogue_response;
        shadowrun_dialogue_result = 2;
    } else if (command == 0x30UL) {
        shadowrun_dialogue_flag30 |= 2UL;
        shadowrun_dialogue_value = 0xf4e8cUL;
        shadowrun_dialogue_result = 2;
    } else if (command == 0x31UL) {
        shadowrun_dialogue_flag27 |= 1U;
        shadowrun_dialogue_value = 0xf5ab0UL;
        shadowrun_dialogue_result = 2;
    }
}
