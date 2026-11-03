/* Source-constructed scene-54 kind-8/item-10 actor. The caller supplies the
 * shared scene terrain, bounds, and source camera contact. This is
 * a bounded actor-tick slice, not a scene loader or autonomous encounter. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u8 rom8(u8 region,u32 offset);
u16 rom16(u8 region,u32 offset);
extern u8 shadowrun_terrain_map[2816];
extern u16 shadowrun_x_min,shadowrun_x_max,shadowrun_y_min,shadowrun_y_max;
u16 shadowrun_hostile_x,shadowrun_hostile_y,shadowrun_hostile_player_x,shadowrun_hostile_player_y;
u16 shadowrun_hostile_timer,shadowrun_hostile_cooldown,shadowrun_hostile_contact,shadowrun_hostile_rng;
u16 shadowrun_hostile_heading,shadowrun_hostile_projectile_x,shadowrun_hostile_projectile_y;
u16 shadowrun_hostile_velocity_x,shadowrun_hostile_velocity_y;
u16 shadowrun_hostile_combat_timer,shadowrun_hostile_combat_mode;
u8 shadowrun_hostile_ammo,shadowrun_hostile_target_existing,shadowrun_hostile_los_clear;
u8 shadowrun_hostile_los_result; /* 0 unknown, 1 clear, 2 blocked */
u8 shadowrun_hostile_profile,shadowrun_hostile_supported,shadowrun_hostile_fired,shadowrun_hostile_effect;
u8 shadowrun_hostile_lifetime,shadowrun_hostile_target_selected,shadowrun_hostile_target_timer;
u8 shadowrun_hostile_pursuit_required;
u8 shadowrun_hostile_player_attacker;
u8 shadowrun_hostile_burst_remaining,shadowrun_hostile_burst_mode;
u16 shadowrun_hostile_scaled(u16 word) {
    u32 magnitude;
    if (word & 32768U) {
        magnitude=(u16)(0U-word); magnitude=(magnitude*12UL+15UL)/16UL;
        return (u16)(0U-(u16)magnitude);
    }
    return (u16)(((u32)word*12UL)/16UL);
}
void shadowrun_hostile_tick(void) {
    u16 dx;u16 dy;u16 major;u16 minor;u16 t;u16 quadrant;u16 entry;u16 i;u16 j;
    u16 rotated;u16 offset;u16 vector;u16 total;u16 roll;u16 done;u16 successes;u16 cooldown;
    u16 startx;u16 starty;u16 vx;u16 vy;u16 px;u16 py;u16 at;u16 terrain;
    u32 rng;u32 nx;u32 ny;u32 delta;
    shadowrun_hostile_supported=0;shadowrun_hostile_los_result=0;shadowrun_hostile_los_clear=0;
    /* profile=1 attests the exact source constructor fields and item-10
     * attributes, active player target, one candidate, combat enabled, no
     * special events and two free projectile slots. Unknown terrain and
     * other paths are rejected before mutating actor or projectile state. */
    if (shadowrun_hostile_profile!=1U || shadowrun_hostile_pursuit_required ||
        shadowrun_hostile_timer>20U ||
        shadowrun_hostile_target_existing>1U ||
        shadowrun_hostile_ammo>48U) return;
    cooldown=shadowrun_hostile_cooldown;
    if (!(cooldown & 32768U)) cooldown=(u16)(cooldown-1U);
    if (shadowrun_hostile_timer) {
        shadowrun_hostile_timer-=1U; shadowrun_hostile_cooldown=cooldown;
        shadowrun_hostile_fired=0; shadowrun_hostile_supported=1; return;
    }
    if (!shadowrun_hostile_contact || !shadowrun_hostile_ammo) return;
    if (shadowrun_hostile_player_x>=shadowrun_hostile_x) {
        dx=shadowrun_hostile_player_x-shadowrun_hostile_x; quadrant=0;
        if (!dx) quadrant=1;
    } else {dx=shadowrun_hostile_x-shadowrun_hostile_player_x;quadrant=2;}
    if (shadowrun_hostile_player_y>=shadowrun_hostile_y) {
        dy=shadowrun_hostile_player_y-shadowrun_hostile_y;
        if (!dy) quadrant+=4U;
    } else {dy=shadowrun_hostile_y-shadowrun_hostile_player_y;quadrant+=8U;}
    if (dx>32767U || dy>32767U) return;
    major=dy;minor=dx;done=0;
    if (minor>=major) {t=major;major=minor;minor=t;done=1;}
    for (i=0;i<16U;i+=1U) {if (major<32U) break;major>>=1;minor>>=1;}
    if (done) {t=major;major=minor;minor=t;}
    entry=rom16(0,0x15df6UL+(u32)quadrant*2UL);
    if (!(entry & 64U)) {t=major;major=minor;minor=t;}
    entry=(entry+rom8(0,0x15f96UL+(u32)major*32UL+minor)) & 255U;
    /* $14D8E simulates at most 27 projectile substeps. Each substep samples
     * source terrain first, then the one attested player rectangle. Complex
     * rectangle/slope tiles remain unknown; solid and empty cells are exact. */
    if (shadowrun_hostile_player_x<144U || shadowrun_hostile_player_x>65391U ||
        shadowrun_hostile_player_y<144U || shadowrun_hostile_player_y>65391U ||
        shadowrun_x_min>=shadowrun_x_max || shadowrun_y_min>=shadowrun_y_max) return;
    t=(u16)(entry*256U);rotated=(u16)((t<<3)|(t>>13));
    if (rotated & 32768U) rotated+=1U;
    offset=(rotated & 7U)*4U;
    startx=shadowrun_hostile_x+rom16(0,0x15a4cUL+offset);
    starty=shadowrun_hostile_y+rom16(0,0x15a4eUL+offset);
    vector=(t>>8)&254U;
    vx=shadowrun_hostile_scaled(rom16(0,0x15e56UL+vector));
    vy=shadowrun_hostile_scaled(rom16(0,0x15e16UL+vector));
    nx=(u32)startx*65536UL;ny=(u32)starty*65536UL;
    for (i=0;i<27U;i+=1U) {
        if (vx & 32768U) {delta=(u32)(u16)(0U-vx)*256UL;nx-=delta;}
        else nx+=(u32)vx*256UL;
        if (vy & 32768U) {delta=(u32)(u16)(0U-vy)*256UL;ny-=delta;}
        else ny+=(u32)vy*256UL;
        px=(u16)(nx/65536UL);py=(u16)(ny/65536UL);
        t=px>>4;at=py>>4;
        if (t<shadowrun_x_min || t>=shadowrun_x_max ||
            at<shadowrun_y_min || at>=shadowrun_y_max) {
            shadowrun_hostile_los_result=2;return;
        }
        at=((at<<1)&65472U)+(t>>5);
        if (at>=2816U) return;
        terrain=shadowrun_terrain_map[at];
        if (terrain==127U || (terrain & 128U)) {shadowrun_hostile_los_result=2;return;}
        if (terrain!=0U) return;
        if (px>=shadowrun_hostile_player_x-144U && px<shadowrun_hostile_player_x+144U &&
            py>=shadowrun_hostile_player_y-144U && py<shadowrun_hostile_player_y+144U) break;
    }
    shadowrun_hostile_los_result=1;
    rng=shadowrun_hostile_rng;
    /* A one-entry target list consumes a source RNG step only when the
     * existing target pointer is absent. $55640 then rolls eight dice at 6. */
    if (!shadowrun_hostile_target_existing) rng=(rng*8421U+1U)&65535U;
    if (!(cooldown & 32768U)) {
        /* $1415E returns to an outer pursuit routine that is not lifted here.
         * Report that boundary explicitly; the caller must not skip pursuit. */
        if (!shadowrun_hostile_target_existing) shadowrun_hostile_target_timer=6U;
        shadowrun_hostile_target_existing=1;shadowrun_hostile_target_selected=1;
        shadowrun_hostile_rng=(u16)rng;shadowrun_hostile_timer=20U;
        shadowrun_hostile_cooldown=cooldown;shadowrun_hostile_fired=0;
        shadowrun_hostile_los_clear=1;shadowrun_hostile_pursuit_required=1;
        shadowrun_hostile_supported=1;return;
    }
    successes=0;
    for (i=0;i<8U;i+=1U) {
        total=0;done=0;
        for (j=0;j<32U;j+=1U) {
            rng=(rng*8421U+1U)&65535U;roll=(rng*6U)/65536U+1U;total+=roll;
            if (roll!=6U) {done=1;break;}
        }
        if (!done) return;
        if (total>=6U) successes+=1U;
    }
    shadowrun_hostile_heading=entry*256U;
    shadowrun_hostile_projectile_x=startx;shadowrun_hostile_projectile_y=starty;
    shadowrun_hostile_velocity_x=vx;shadowrun_hostile_velocity_y=vy;
    shadowrun_hostile_los_clear=1;
    shadowrun_hostile_rng=(u16)rng;shadowrun_hostile_timer=20U;
    shadowrun_hostile_cooldown=cooldown;shadowrun_hostile_ammo-=1U;
    if (!shadowrun_hostile_target_existing) shadowrun_hostile_target_timer=6U;
    shadowrun_hostile_target_existing=1;shadowrun_hostile_target_selected=1;
    shadowrun_hostile_effect=(u8)successes;
    /* Item 10 sets $FFDD3A and takes $152FA before the projectile callback. */
    shadowrun_hostile_lifetime=32;shadowrun_hostile_burst_remaining=2;
    shadowrun_hostile_burst_mode=1;shadowrun_hostile_fired=1;
    shadowrun_hostile_combat_timer=120U;shadowrun_hostile_combat_mode=1U;
    shadowrun_hostile_player_attacker=1;
    shadowrun_hostile_pursuit_required=0;shadowrun_hostile_supported=1;
}
