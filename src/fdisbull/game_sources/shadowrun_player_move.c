/* Source player step proposal for the explicitly checked normal-walk branch.
 * Unknown player states are refused; collision and commit are separate. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u16 shadowrun_player_x;
u16 shadowrun_player_y;
u16 shadowrun_player_heading;
u16 shadowrun_player_target_heading;
u16 shadowrun_player_kind;
u16 shadowrun_player_contact;
u8 shadowrun_player_flags;
u8 shadowrun_player_equipment_flags;
u16 shadowrun_global_special_mode;
u8 shadowrun_global_vector_flags;
u16 shadowrun_player_move_state;
u16 shadowrun_player_step_timer;
u16 shadowrun_player_direction;
u16 shadowrun_player_proposed_x;
u16 shadowrun_player_proposed_y;
u8 shadowrun_player_proposal_supported;
void shadowrun_player_propose(void) {
    u16 delta;
    u16 rotated;
    u16 ordinal;
    u16 offset;
    shadowrun_player_proposal_supported = 0;
    if (shadowrun_player_kind == 13U || (shadowrun_player_flags & 10U) != 10U ||
        (shadowrun_global_vector_flags & 1U) || (shadowrun_player_equipment_flags & 32U) ||
        shadowrun_global_special_mode != 0 || shadowrun_player_contact == 0) return;
    shadowrun_player_move_state = 1;
    delta = (u16)(shadowrun_player_heading - shadowrun_player_target_heading);
    if (delta & 0x8000U) {
        if (delta < 0xf800U) shadowrun_player_heading = (u16)(shadowrun_player_heading + 0x0800U);
        else shadowrun_player_heading = shadowrun_player_target_heading;
    } else if (delta != 0) {
        if (delta < 0x0800U) shadowrun_player_heading = shadowrun_player_target_heading;
        else shadowrun_player_heading = (u16)(shadowrun_player_heading - 0x0800U);
    }
    rotated = (u16)((shadowrun_player_heading << 3) | (shadowrun_player_heading >> 13));
    ordinal = rotated & 7U;
    offset = ordinal << 2;
    shadowrun_player_step_timer = rom16(0, 0xbec6UL);
    shadowrun_player_direction = ordinal << 1;
    shadowrun_player_proposed_x = (u16)(shadowrun_player_x + rom16(0, 0xbec2UL + offset));
    shadowrun_player_proposed_y = (u16)(shadowrun_player_y + rom16(0, 0xbec4UL + offset));
    shadowrun_player_proposal_supported = 1;
}
