/* Reviewed controller-state boundary, Shadowrun (U), after the hardware read.
 * The actual direction table remains in the separately supplied source ROM.
 * This is a component of the opening scene, not a field movement model. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;

u16 shadowrun_pad_held;
u16 shadowrun_pad_sample;
u16 shadowrun_direction_angle;

void shadowrun_input_tick(u8 normalized_pad) {
    u16 previous;
    u16 current;
    previous = shadowrun_pad_held;
    current = normalized_pad;
    shadowrun_pad_held = current;
    shadowrun_pad_sample = (u16)((((previous ^ current) & current) << 8) | current);
    shadowrun_direction_angle = rom16(0, 0x19d2UL + ((current & 15) << 1));
}
