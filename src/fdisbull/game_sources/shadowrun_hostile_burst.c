/* Item-10 projectile $14F1C/$14F86. Caller advances the original animation
 * until the signed animation word is negative; this leaf does not invent a
 * frame schedule. Profile 1 attests the original kind-8 attacker at HP 10. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u16 rom16(u8 region,u32 offset);
u32 shadowrun_burst_x,shadowrun_burst_y;
u16 shadowrun_burst_origin_x,shadowrun_burst_origin_y,shadowrun_burst_heading;
u16 shadowrun_burst_vx,shadowrun_burst_vy,shadowrun_burst_rng,shadowrun_burst_animation;
u8 shadowrun_burst_profile,shadowrun_burst_supported,shadowrun_burst_counter;
u8 shadowrun_burst_flags,shadowrun_burst_flags_low,shadowrun_burst_lifetime;
u8 shadowrun_burst_effect,shadowrun_burst_shooter_effect,shadowrun_burst_waiting;
u16 shadowrun_burst_scaled(u16 word) {
    u32 magnitude;
    if (word & 32768U) {
        magnitude=(u16)(0U-word);magnitude=(magnitude*12UL+15UL)/16UL;
        return (u16)(0U-(u16)magnitude);
    }
    return (u16)(((u32)word*12UL)/16UL);
}
void shadowrun_burst_tick(void) {
    u16 i;u16 j;u16 done;u16 total;u16 roll;u16 successes;u16 heading;u16 vector;
    u32 rng;
    shadowrun_burst_supported=0;
    if (shadowrun_burst_profile!=1U || shadowrun_burst_counter>2U ||
        !(shadowrun_burst_flags & 1U) || !(shadowrun_burst_flags_low & 8U)) return;
    if (!(shadowrun_burst_animation & 32768U)) {
        shadowrun_burst_waiting=1;shadowrun_burst_supported=1;return;
    }
    if (!shadowrun_burst_counter) {
        shadowrun_burst_counter=255U;shadowrun_burst_flags&=254U;shadowrun_burst_waiting=0;
        shadowrun_burst_supported=1;return;
    }
    rng=shadowrun_burst_rng;successes=0;
    for (i=0;i<8U;i+=1U) {
        total=0;done=0;
        for (j=0;j<32U;j+=1U) {
            rng=(rng*8421U+1U)&65535U;roll=(rng*6U)/65536U+1U;total+=roll;
            if (roll!=6U) {done=1;break;}
        }
        if (!done) return;
        if (total>=6U) successes+=1U;
    }
    heading=shadowrun_burst_heading;
    if (shadowrun_burst_counter==1U) heading+=0x0800U;
    else heading-=0x0400U;
    vector=(heading>>8)&254U;
    shadowrun_burst_x=(u32)shadowrun_burst_origin_x*65536UL+(shadowrun_burst_x&65535UL);
    shadowrun_burst_y=(u32)shadowrun_burst_origin_y*65536UL+(shadowrun_burst_y&65535UL);
    shadowrun_burst_heading=heading;
    shadowrun_burst_vx=shadowrun_burst_scaled(rom16(0,0x15e56UL+vector));
    shadowrun_burst_vy=shadowrun_burst_scaled(rom16(0,0x15e16UL+vector));
    shadowrun_burst_counter-=1U;shadowrun_burst_flags_low&=247U;
    shadowrun_burst_rng=(u16)rng;shadowrun_burst_effect=(u8)successes;
    shadowrun_burst_shooter_effect=(u8)successes;
    shadowrun_burst_lifetime=32U;shadowrun_burst_animation=20U;shadowrun_burst_waiting=0;
    shadowrun_burst_supported=1;
}
