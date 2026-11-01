/* Prepared projectile encounter: $1517A/$38AC/$15A8C, $15ABA and
 * $14E6E/$55948. The projectile coordinates and source record are supplied
 * at the collision boundary; movement and dispatcher are not represented. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u8 shadowrun_field_supported;
u8 shadowrun_field_actor_index; /* +$3E */
u8 shadowrun_field_item; /* equipped +$57; 1 or 2 */
u8 shadowrun_field_equipped_slot; /* +$56 */
u8 shadowrun_field_source_flags; /* +$10 */
u8 shadowrun_field_ammo;
u8 shadowrun_field_slots_busy; /* bits 0..5, slots $FF0B00..$FF1000 */
u16 shadowrun_field_projectile_x;
u16 shadowrun_field_projectile_y;
u16 shadowrun_field_target_x;
u16 shadowrun_field_target_y;
u8 shadowrun_field_target_flags;
u8 shadowrun_field_target_flags_b0;
u8 shadowrun_field_target_flags_9e;
u8 shadowrun_field_target_flags_9a;
u8 shadowrun_field_target_type; /* +$9B */
u8 shadowrun_field_target_defense_bonus; /* +$77 */
u8 shadowrun_field_target_depleted;
u8 shadowrun_field_death_timer; /* $FFF0CE, supported 0..127 */
u8 shadowrun_field_type13_deaths; /* $FFFBFA, supported 0..8 */
u8 shadowrun_field_party_counter_a; /* $FF018D */
u8 shadowrun_field_party_counter_b; /* $FF028D */
u8 shadowrun_field_party_counter_c; /* $FF038D */
u8 shadowrun_field_target_hp;
u8 shadowrun_field_target_a;
u8 shadowrun_field_target_b;
u8 shadowrun_field_target_c;
u8 shadowrun_field_target_posture;
u8 shadowrun_field_source_effect;
u16 shadowrun_field_rng;
u8 shadowrun_field_outcome; /* 0 no ammo; 1 no slot; 2 miss; 3 hit, no HP change; 4 HP reduced */
u8 shadowrun_field_slot;
void shadowrun_field_fire(void) {
    u16 i; u16 j; u16 trials; u16 roll; u16 total; u16 successes;
    u16 amount; u16 difficulty; u16 found; u16 finished; u16 target_hp; u16 previous_slot; u16 previous_outcome; u16 previous_ammo;
    u32 rng;
    previous_slot = shadowrun_field_slot; previous_outcome = shadowrun_field_outcome; previous_ammo = shadowrun_field_ammo;
    shadowrun_field_supported = 0;
    /* Admitted: source kind 3/item 1, target kind 3, no armor, no dynamic
     * effects or cyberware, no inventory defenses, normal HP, no override,
     * scene and animation gates clear, target is first and only candidate. */
    if (shadowrun_field_actor_index > 3 ||
        (shadowrun_field_item != 1 && shadowrun_field_item != 2) ||
        shadowrun_field_equipped_slot > 7 || !(shadowrun_field_source_flags & 1U) ||
        shadowrun_field_ammo > 127 || shadowrun_field_slots_busy > 63 ||
        shadowrun_field_target_x < 144 || shadowrun_field_target_x > 65391U ||
        shadowrun_field_target_y < 144 || shadowrun_field_target_y > 65391U ||
        shadowrun_field_target_hp < 1 || shadowrun_field_target_hp > 127 ||
        shadowrun_field_target_defense_bonus > 16 ||
        (shadowrun_field_target_hp <= 10 && (shadowrun_field_target_type != 19 ||
          shadowrun_field_death_timer > 127 || shadowrun_field_type13_deaths > 8)) ||
        shadowrun_field_target_a > 85 || shadowrun_field_target_b > 85 ||
        shadowrun_field_target_c > 85 || shadowrun_field_target_posture > 4 ||
        shadowrun_field_source_effect > 127) return;
    trials = ((shadowrun_field_target_a + shadowrun_field_target_b + shadowrun_field_target_c) & 255U) / 2U;
    trials = trials - (trials * shadowrun_field_target_posture * 25U) / 100U;
    if (trials + shadowrun_field_target_defense_bonus > 127) return;
    rng = shadowrun_field_rng;
    target_hp = shadowrun_field_target_hp;
    shadowrun_field_target_depleted = 0;
    shadowrun_field_supported = 1;
    shadowrun_field_outcome = 0;
    if (shadowrun_field_ammo == 0) return;
    shadowrun_field_ammo = shadowrun_field_ammo - 1U;
    /* $36FC clamps a party member's loaded rounds to item +$24. */
    if (shadowrun_field_actor_index < 3) {
        if (shadowrun_field_item == 1 && shadowrun_field_ammo > 6) shadowrun_field_ammo = 6;
        if (shadowrun_field_item == 2 && shadowrun_field_ammo > 12) shadowrun_field_ammo = 12;
    }
    found = 0;
    for (i = 0; i < 6; i = i + 1) {
        if (!found && !(shadowrun_field_slots_busy & (1U << i))) {
            shadowrun_field_slot = i + 9U;
            found = 1;
        }
    }
    shadowrun_field_outcome = 1;
    if (!found) return;
    shadowrun_field_outcome = 2;
    if (!(shadowrun_field_target_flags & 1U) || (shadowrun_field_target_flags & 80U)) return;
    /* Projectile inherits source +$10 bit 3 in $1504C. */
    if ((shadowrun_field_source_flags & 8U) &&
        ((shadowrun_field_target_flags_b0 & 128U) || (shadowrun_field_target_flags & 8U) ||
         (shadowrun_field_target_flags_9e & 16U))) return;
    if (shadowrun_field_projectile_x < shadowrun_field_target_x - 144U ||
        shadowrun_field_projectile_x >= shadowrun_field_target_x + 144U ||
        shadowrun_field_projectile_y < shadowrun_field_target_y - 144U ||
        shadowrun_field_projectile_y >= shadowrun_field_target_y + 144U) return;
    /* $55ED6 uses byte-wrapped sum; $55F20 selects defensive share. */
    trials = ((shadowrun_field_target_a + shadowrun_field_target_b + shadowrun_field_target_c) & 255U) / 2U;
    trials = trials - (trials * shadowrun_field_target_posture * 25U) / 100U;
    trials = trials + shadowrun_field_target_defense_bonus;
    if (trials == 0) trials = 1;
    difficulty = 4;
    if (shadowrun_field_item == 2) difficulty = 6;
    successes = 0;
    for (i = 0; i < trials; i = i + 1) {
        total = 0; finished = 0;
        for (j = 0; j < 32; j = j + 1) {
            if (!finished) {
                rng = (rng * 8421U + 1U) & 65535U;
                roll = (rng * 6U) / 65536U + 1U;
                total = total + roll;
                if (roll != 6U) { finished = 1; break; }
            }
        }
        if (!finished) {
            shadowrun_field_ammo = previous_ammo;
            shadowrun_field_slot = previous_slot;
            shadowrun_field_outcome = previous_outcome;
            shadowrun_field_supported = 0; return;
        }
        if (total >= difficulty) successes = successes + 1U;
    }
    shadowrun_field_rng = rng;
    shadowrun_field_outcome = 3;
    if (shadowrun_field_source_effect + 1U <= successes) return;
    amount = shadowrun_field_source_effect + 1U - successes;
    if (amount > 10) amount = 10;
    if (shadowrun_field_target_flags_9a & 128U) amount = 1;
    if (amount >= target_hp) {
        shadowrun_field_target_hp = 0;
        shadowrun_field_target_depleted = 1;
        /* Only type $13 is admitted when depletion can occur. */
        if (shadowrun_field_death_timer == 0) {
            shadowrun_field_death_timer = 15;
            shadowrun_field_party_counter_a += 1U;
            shadowrun_field_party_counter_b += 1U;
            shadowrun_field_party_counter_c += 1U;
        } else shadowrun_field_death_timer -= 1U;
        if (shadowrun_field_type13_deaths < 8) shadowrun_field_type13_deaths += 1U;
    } else shadowrun_field_target_hp = target_hp - amount;
    shadowrun_field_outcome = 4;
}
/* $55640 shot trial for the exact scene-005999 player profile described in
 * the Python evidence: item 2, actor index 0, six dice, threshold four.
 * The caller must attest that full profile and provide a separately established
 * collision-boundary projectile position. This is an assisted composition:
 * allocation/rendering, combat globals and motion are not simulated here. */
u8 shadowrun_field_captured_profile;
u8 shadowrun_field_first_slot;
u8 shadowrun_field_second_slot;
void shadowrun_field_captured_fire(void) {
    u16 i; u16 j; u16 found; u16 successes; u16 total; u16 roll; u16 done;
    u16 old_rng; u16 old_effect; u16 original_busy; u16 old_first; u16 old_second; u32 rng;
    old_rng = shadowrun_field_rng; old_effect = shadowrun_field_source_effect;
    old_first = shadowrun_field_first_slot; old_second = shadowrun_field_second_slot;
    original_busy = shadowrun_field_slots_busy;
    shadowrun_field_supported = 0;
    if (shadowrun_field_captured_profile != 1 || shadowrun_field_actor_index != 0 ||
        shadowrun_field_item != 2 || shadowrun_field_equipped_slot != 0 ||
        shadowrun_field_source_flags != 15 || shadowrun_field_slots_busy > 63) return;
    if (shadowrun_field_ammo == 0 || shadowrun_field_slots_busy == 63) {
        shadowrun_field_fire();
        return;
    }
    found = 0;
    for (i = 0; i < 6; i = i + 1) {
        if (!(original_busy & (1U << i))) {
            if (found == 0) shadowrun_field_first_slot = i + 9U;
            if (found == 1) shadowrun_field_second_slot = i + 9U;
            found = found + 1U;
        }
    }
    rng = shadowrun_field_rng; successes = 0;
    for (i = 0; i < 6; i = i + 1) {
        total = 0; done = 0;
        for (j = 0; j < 32; j = j + 1) {
            rng = (rng * 8421U + 1U) & 65535U;
            roll = (rng * 6U) / 65536U + 1U;
            total = total + roll;
            if (roll != 6U) { done = 1; break; }
        }
        if (!done) return;
        if (total >= 4) successes = successes + 1U;
    }
    shadowrun_field_source_effect = successes;
    shadowrun_field_rng = rng;
    /* $151EE fails after first actor initialization and the shot roll when
     * only one slot is free. Actual actor/global side effects are excluded. */
    if (found == 1) shadowrun_field_slots_busy = 63;
    shadowrun_field_fire();
    shadowrun_field_slots_busy = original_busy;
    if (!shadowrun_field_supported) {
        shadowrun_field_rng = old_rng;
        shadowrun_field_source_effect = old_effect;
        shadowrun_field_first_slot = old_first; shadowrun_field_second_slot = old_second;
    }
}
