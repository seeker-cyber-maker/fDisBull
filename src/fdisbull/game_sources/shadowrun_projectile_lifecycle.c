/* Original $14F1C/$14F86/$14FF0 and $AC4E retirement gates.
 * The caller supplies the original animation word; this does not infer when
 * an animation completes. Rearming a projectile is deliberately refused. */
typedef unsigned char u8;
typedef unsigned int u16;
u16 shadowrun_lifecycle_animation;
u8 shadowrun_lifecycle_flags;
u8 shadowrun_lifecycle_repeat;
u8 shadowrun_lifecycle_supported;
void shadowrun_lifecycle_primary(void) {
    shadowrun_lifecycle_supported=0;
    if ((shadowrun_lifecycle_animation & 0x8000U) && shadowrun_lifecycle_repeat != 0) return;
    shadowrun_lifecycle_supported=1;
    if (shadowrun_lifecycle_animation & 0x8000U) {
        shadowrun_lifecycle_repeat=255;
        shadowrun_lifecycle_flags &= 254U;
    }
}
void shadowrun_lifecycle_secondary(void) {
    shadowrun_lifecycle_supported=1;
    if (shadowrun_lifecycle_animation & 0x8000U) shadowrun_lifecycle_flags &= 254U;
}
/* Captured wall-impact actor type 1 / animation index 0: original descriptor
 * is count 3, rate $0800 and period $1000. This models one animation service
 * invocation, not its scheduling or frame presentation. */
u8 shadowrun_lifecycle_profile;
u8 shadowrun_lifecycle_flags_low;
u16 shadowrun_lifecycle_accumulator;
u16 shadowrun_lifecycle_frame;
void shadowrun_lifecycle_animate(void) {
    u16 accumulator;
    shadowrun_lifecycle_supported=0;
    if (shadowrun_lifecycle_profile!=1 || shadowrun_lifecycle_accumulator>=4096 ||
        shadowrun_lifecycle_frame>2 || shadowrun_lifecycle_animation != 0) return;
    accumulator=shadowrun_lifecycle_accumulator+2048U;
    if (accumulator>=4096U) {
        accumulator-=4096U;
        shadowrun_lifecycle_frame+=1U;
        shadowrun_lifecycle_flags_low|=1U;
    }
    shadowrun_lifecycle_accumulator=accumulator;
    if (shadowrun_lifecycle_frame>=3U) {
        shadowrun_lifecycle_animation|=0x8000U;
        shadowrun_lifecycle_frame=2;
    }
    shadowrun_lifecycle_supported=1;
}
