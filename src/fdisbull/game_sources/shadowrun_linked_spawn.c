/* $1509A..$15116 spawn positions and signed velocity from a source heading.
 * Original lookup tables are read from the caller's exact external ROM. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u16 rom16(u8 region,u32 offset);
u16 shadowrun_spawn_source_x,shadowrun_spawn_source_y,shadowrun_spawn_heading;
u16 shadowrun_spawn_x,shadowrun_spawn_y,shadowrun_spawn_secondary_x,shadowrun_spawn_secondary_y;
u16 shadowrun_spawn_velocity_x,shadowrun_spawn_velocity_y;
u8 shadowrun_spawn_supported;
u16 shadowrun_spawn_scaled(u16 word) {
    u32 magnitude;
    if (word & 0x8000U) {
        magnitude=(u16)(0U-word);
        magnitude=(magnitude*12UL+15UL)/16UL;
        return (u16)(0U-(u16)magnitude);
    }
    magnitude=((u32)word*12UL)/16UL;
    return (u16)magnitude;
}
void shadowrun_linked_spawn(void) {
    u16 rotated;u16 offset;u16 vector;
    shadowrun_spawn_supported=0;
    rotated=(u16)((shadowrun_spawn_heading<<3)|(shadowrun_spawn_heading>>13));
    if (rotated & 0x8000U) rotated += 1U;
    offset=(rotated & 7U)*4U;
    shadowrun_spawn_x=shadowrun_spawn_source_x+rom16(0,0x15a4cUL+offset);
    shadowrun_spawn_y=shadowrun_spawn_source_y+rom16(0,0x15a4eUL+offset);
    shadowrun_spawn_secondary_x=shadowrun_spawn_source_x+rom16(0,0x15a6cUL+offset);
    shadowrun_spawn_secondary_y=shadowrun_spawn_source_y+rom16(0,0x15a6eUL+offset);
    vector=(shadowrun_spawn_heading >> 8) & 254U;
    shadowrun_spawn_velocity_x=shadowrun_spawn_scaled(rom16(0,0x15e56UL+vector));
    shadowrun_spawn_velocity_y=shadowrun_spawn_scaled(rom16(0,0x15e16UL+vector));
    shadowrun_spawn_supported=1;
}
