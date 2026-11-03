/* $55948..$55A60 and $3674..$36F0 for the captured party member.
 * Incoming projectile effect is supplied after the original attack roll.
 * The source HUD write, hit animation and death continuation are separate. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u8 rom8(u8 region, u32 offset);
u8 shadowrun_player_damage_profile;
u8 shadowrun_player_damage_item;
u8 shadowrun_player_damage_effect;
u8 shadowrun_player_damage_armor;
u8 shadowrun_player_damage_hp;
u16 shadowrun_player_damage_rng;
u8 shadowrun_player_damage_supported;
u8 shadowrun_player_damage_amount;
u8 shadowrun_player_damage_successes;
u8 shadowrun_player_damage_depleted;
void shadowrun_player_hit(void) {
    u16 i; u16 j; u16 total; u16 roll; u16 done;
    u16 successes; u16 difficulty; u16 level; u16 amount;
    u16 armor; u32 rng; u32 row;
    shadowrun_player_damage_supported = 0;
    /* Profile 1 attests party index 0, flags $0F, attributes 3/2/4,
     * posture 2, defense bonus 4, no cyber/defense inventory, word +$90=4,
     * projectile byte +$11 bit5 clear and no item39 mitigation. */
    if (shadowrun_player_damage_profile != 1 ||
        shadowrun_player_damage_item < 1 || shadowrun_player_damage_item > 12 ||
        shadowrun_player_damage_effect > 12 ||
        shadowrun_player_damage_armor > 7 ||
        shadowrun_player_damage_hp < 1 || shadowrun_player_damage_hp > 10) return;
    row = 0xD4540UL + (shadowrun_player_damage_item - 1U) * 48UL;
    level = rom8(0, row + 37UL);
    difficulty = rom8(0, row + 38UL);
    if (level > 2 || difficulty < 2 || difficulty > 127) return;
    amount = (256U - rom8(0, 0x166AD4UL + level)) & 255U;
    rng = shadowrun_player_damage_rng;
    successes = 0;
    /* $55ED6/$55F20: (3+2+4)/2=4, posture share=2, bonus=4:
     * six exploding-d6 defensive trials. $55786 is inactive in profile1. */
    for (i = 0; i < 6; i = i + 1) {
        total = 0; done = 0;
        for (j = 0; j < 32; j = j + 1) {
            rng = (rng * 8421UL + 1UL) & 65535UL;
            roll = (rng * 6UL) / 65536UL + 1U;
            total = total + roll;
            if (roll != 6) { done = 1; break; }
        }
        if (!done) return;
        if (total >= difficulty) successes = successes + 1;
    }
    shadowrun_player_damage_rng = rng;
    shadowrun_player_damage_successes = successes;
    shadowrun_player_damage_amount = 0;
    shadowrun_player_damage_depleted = 0;
    shadowrun_player_damage_supported = 1;
    if (shadowrun_player_damage_effect >= successes) {
        amount += shadowrun_player_damage_effect - successes;
        if (amount > 10) amount = 10;
    } else {
        if (successes - shadowrun_player_damage_effect >= amount) return;
        amount -= successes - shadowrun_player_damage_effect;
    }
    armor = 0;
    if (shadowrun_player_damage_armor != 0) {
        row = 0xD4D50UL + (shadowrun_player_damage_armor - 1U) * 48UL;
        armor = rom8(0, row + 37UL);
    }
    if (armor >= amount) return;
    amount -= armor;
    if (amount >= shadowrun_player_damage_hp) {
        shadowrun_player_damage_amount = shadowrun_player_damage_hp;
        shadowrun_player_damage_hp = 0;
        shadowrun_player_damage_depleted = 1;
    } else {
        shadowrun_player_damage_hp -= amount;
        shadowrun_player_damage_amount = amount;
    }
}
