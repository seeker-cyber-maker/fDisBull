/* Prepared item-10 projectile striking its source-constructed kind-8 actor.
 * $15B32 zero-effect contacts skip damage; positive effect uses $55948. */
typedef unsigned char u8;typedef unsigned int u16;typedef unsigned long u32;
u8 rom8(u8 region,u32 offset);
u8 shadowrun_selfhit_profile,shadowrun_selfhit_supported,shadowrun_selfhit_effect,shadowrun_selfhit_hp;
u8 shadowrun_selfhit_override,shadowrun_selfhit_death_timer,shadowrun_selfhit_depleted;
u8 shadowrun_selfhit_party_a,shadowrun_selfhit_party_b,shadowrun_selfhit_party_c;
u16 shadowrun_selfhit_rng;
void shadowrun_hostile_self_hit(void) {
    u16 i;u16 j;u16 roll;u16 total;u16 done;u16 successes;u16 amount;u16 armor;u32 rng;
    shadowrun_selfhit_supported=0;
    if (shadowrun_selfhit_profile!=1U || !shadowrun_selfhit_hp || shadowrun_selfhit_hp>10U ||
        shadowrun_selfhit_effect>127U || shadowrun_selfhit_death_timer>127U) return;
    shadowrun_selfhit_depleted=0;
    if (!shadowrun_selfhit_effect) {shadowrun_selfhit_supported=1;return;}
    rng=shadowrun_selfhit_rng;successes=0;
    for(i=0;i<8U;i+=1U) {
        total=0;done=0;
        for(j=0;j<32U;j+=1U) {
            rng=(rng*8421U+1U)&65535U;roll=(rng*6U)/65536U+1U;total+=roll;
            if (roll!=6U) {done=1;break;}
        }
        if (!done) return;
        if (total>=6U) successes+=1U;
    }
    shadowrun_selfhit_rng=(u16)rng;
    amount=shadowrun_selfhit_effect+3U;
    if (amount<=successes) {shadowrun_selfhit_supported=1;return;}
    amount-=successes;if (amount>10U) amount=10U;
    armor=rom8(0,0xd4d50UL+2UL*48UL+37UL);
    if (amount<=armor) {shadowrun_selfhit_supported=1;return;}
    amount-=armor;if (shadowrun_selfhit_override & 128U) amount=1U;
    if (amount>=shadowrun_selfhit_hp) {
        shadowrun_selfhit_hp=0;shadowrun_selfhit_depleted=1;
        if (!shadowrun_selfhit_death_timer) {
            shadowrun_selfhit_death_timer=15U;
            shadowrun_selfhit_party_a+=1U;shadowrun_selfhit_party_b+=1U;shadowrun_selfhit_party_c+=1U;
        } else shadowrun_selfhit_death_timer-=1U;
    } else shadowrun_selfhit_hp-=amount;
    shadowrun_selfhit_supported=1;
}
