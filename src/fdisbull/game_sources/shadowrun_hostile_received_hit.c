/* Prepared collision against the source-constructed kind8/type2 hostile.
 * The damage arithmetic before depletion is shared with $55948. This leaf
 * preserves source effect/RNG behavior and type2-specific zero-HP counters. */
u8 rom8(u8 region,u32 offset);
u8 shadowrun_hostile_received_supported,shadowrun_hostile_received_kind,shadowrun_hostile_received_armor,shadowrun_hostile_received_profile;
void shadowrun_hostile_received_hit(void) {
    u16 hp;u16 old_ammo;u16 old_slot;u16 old_busy;u16 old_override;u16 old_outcome;u16 amount;
    shadowrun_hostile_received_supported=0;
    if (shadowrun_hostile_received_profile!=1U || shadowrun_field_actor_index!=0U ||
        shadowrun_field_item!=2U || shadowrun_field_equipped_slot!=0U || shadowrun_field_source_flags!=15U ||
        shadowrun_hostile_received_kind!=8U || shadowrun_hostile_received_armor!=3U || shadowrun_field_target_type!=2U ||
        shadowrun_field_target_flags!=5U || shadowrun_field_target_flags_9e!=0U ||
        shadowrun_field_target_defense_bonus!=5U || shadowrun_field_target_a!=5U ||
        shadowrun_field_target_b!=4U || shadowrun_field_target_c!=3U ||
        shadowrun_field_target_posture!=2U || !shadowrun_field_source_effect ||
        !shadowrun_field_target_hp || shadowrun_field_target_hp>10U ||
        shadowrun_field_death_timer>127U) return;
    hp=shadowrun_field_target_hp;old_ammo=shadowrun_field_ammo;
    old_slot=shadowrun_field_slot;old_busy=shadowrun_field_slots_busy;old_override=shadowrun_field_target_flags_9a;old_outcome=shadowrun_field_outcome;
    shadowrun_field_target_hp=100U;shadowrun_field_target_flags_9a=0;shadowrun_field_ammo=1U;shadowrun_field_slots_busy=0;
    shadowrun_field_fire();
    shadowrun_field_target_flags_9a=old_override;shadowrun_field_ammo=old_ammo;shadowrun_field_slot=old_slot;shadowrun_field_slots_busy=old_busy;
    if (!shadowrun_field_supported || shadowrun_field_outcome<3U) {
        shadowrun_field_target_hp=hp;shadowrun_field_outcome=old_outcome;return;
    }
    amount=100U-shadowrun_field_target_hp;
    if (amount<=rom8(0,0xd4d50UL+2UL*48UL+37UL)) {
        shadowrun_field_target_hp=hp;shadowrun_field_outcome=3U;
        shadowrun_hostile_received_supported=1;return;
    }
    amount-=rom8(0,0xd4d50UL+2UL*48UL+37UL);
    if (old_override & 128U) amount=1U;
    if (amount>=hp) {
        shadowrun_field_target_hp=0;shadowrun_field_target_depleted=1;
        if (!shadowrun_field_death_timer) {
            shadowrun_field_death_timer=15U;
            shadowrun_field_party_counter_a+=1U;shadowrun_field_party_counter_b+=1U;shadowrun_field_party_counter_c+=1U;
        } else shadowrun_field_death_timer-=1U;
    } else shadowrun_field_target_hp=hp-amount;
    shadowrun_hostile_received_supported=1;
}
