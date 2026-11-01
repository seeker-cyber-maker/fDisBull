/* Reviewed pre-collision portion of the Shadowrun field movement path.
 * Coordinates and vectors are wrapping 16-bit 12.4 fixed-point values.
 * This procedure does not accept/commit a step or model collision/events. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u16 shadowrun_position_x;
u16 shadowrun_position_y;
u16 shadowrun_move_heading;
u16 shadowrun_move_record_offset;
u16 shadowrun_move_step_timer;
u16 shadowrun_move_direction;
u16 shadowrun_proposed_x;
u16 shadowrun_proposed_y;
void shadowrun_propose_move(void) {
    u16 rotated;
    u16 ordinal;
    u16 offset;
    rotated = (u16)((shadowrun_move_heading << 3) | (shadowrun_move_heading >> 13));
    if (rotated & 0x8000U) rotated = (u16)(rotated + 1U);
    ordinal = rotated & 7U;
    offset = ordinal << 2;
    shadowrun_move_record_offset = 0xfff4U;
    shadowrun_move_step_timer = rom16(0, 0xc006UL);
    shadowrun_move_direction = ordinal << 1;
    shadowrun_proposed_x = (u16)(shadowrun_position_x + rom16(0, 0xc002UL + offset));
    shadowrun_proposed_y = (u16)(shadowrun_position_y + rom16(0, 0xc004UL + offset));
}
