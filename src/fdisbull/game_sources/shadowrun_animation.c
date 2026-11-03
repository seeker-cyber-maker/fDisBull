/* Reviewed Shadowrun 68000 actor counter at 0x5fee..0x600c and normal
 * positive-count selector at 0x6060..0x606c. Fields are 16-bit words.
 * The flag is actor byte +0x11. This does not perform graphics upload or
 * implement the negative-count selector, table lookup, or actor mode changes. */
typedef unsigned int u16;
typedef unsigned char u8;
u16 shadowrun_anim_accumulator;
u16 shadowrun_anim_increment;
u16 shadowrun_anim_threshold;
u16 shadowrun_anim_index;
u16 shadowrun_anim_positive_count;
u8 shadowrun_anim_flags;
void shadowrun_animation_tick(void) {
    u16 value;
    value = (u16)(shadowrun_anim_accumulator + shadowrun_anim_increment);
    if ((u16)(value ^ 0x8000U) >= (u16)(shadowrun_anim_threshold ^ 0x8000U)) {
        shadowrun_anim_index = (u16)(shadowrun_anim_index + 1U);
        shadowrun_anim_flags = (u8)(shadowrun_anim_flags | 1U);
        value = (u16)(value - shadowrun_anim_threshold);
    }
    shadowrun_anim_accumulator = value;
}
void shadowrun_animation_positive_wrap(void) {
    if ((u16)(shadowrun_anim_positive_count ^ 0x8000U) <=
        (u16)(shadowrun_anim_index ^ 0x8000U)) shadowrun_anim_index = 0U;
}
