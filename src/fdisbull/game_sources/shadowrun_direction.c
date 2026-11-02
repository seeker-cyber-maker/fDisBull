/* The original field callback selector stores a source-address identity;
 * it is data here, not a target-CPU function pointer. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u16 shadowrun_direction_angle;
u16 shadowrun_player_target_heading;
u8 shadowrun_player_flags_low;
u32 shadowrun_player_callback;
void shadowrun_select_direction(void) {
    if (shadowrun_direction_angle == 0xffffU) {
        if (shadowrun_player_callback != 0xb45cUL) {
            shadowrun_player_flags_low |= 1U;
            shadowrun_player_callback = 0xb45cUL;
        }
    } else {
        shadowrun_player_target_heading = shadowrun_direction_angle;
        shadowrun_player_callback = 0xb574UL;
    }
}
