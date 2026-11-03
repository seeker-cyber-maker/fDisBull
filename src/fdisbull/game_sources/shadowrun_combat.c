/* Source $12DD2 and $12D46 stat leaves; the caller supplies the skill byte
 * and D6 value computed by the original preceding routines. This is neither
 * damage nor the original combat action dispatcher. */
typedef unsigned char u8;
typedef unsigned int u16;
u16 shadowrun_combat_baseline;
u8 shadowrun_combat_skill;
u16 shadowrun_combat_attack_stat;
u8 shadowrun_combat_supported;
void shadowrun_combat_skill_stat(void) {
    shadowrun_combat_supported = 0;
    /* Source uses a signed word comparison; this bounded domain makes the
     * nonnegative comparison explicit. Unknown negative D6 is refused. */
    if (shadowrun_combat_baseline > 32767U) return;
    shadowrun_combat_attack_stat = shadowrun_combat_baseline;
    if (shadowrun_combat_skill < shadowrun_combat_attack_stat)
        shadowrun_combat_attack_stat = shadowrun_combat_skill;
    shadowrun_combat_attack_stat += shadowrun_combat_skill;
    if (shadowrun_combat_attack_stat == 0) shadowrun_combat_attack_stat = 1;
    shadowrun_combat_supported = 1;
}
/* $11AEE..$11B0E: only legal posture and one-step inputs. Delta uses
 * $FF for -1. Renderer and subsequent recalculation are separate calls. */
u8 shadowrun_combat_posture;
u8 shadowrun_combat_posture_delta;
u8 shadowrun_combat_posture_supported;
void shadowrun_combat_change_posture(void) {
    shadowrun_combat_posture_supported = 0;
    if (shadowrun_combat_posture > 4) return;
    if (shadowrun_combat_posture_delta != 0 && shadowrun_combat_posture_delta != 1 && shadowrun_combat_posture_delta != 255) return;
    if (shadowrun_combat_posture_delta == 255 && shadowrun_combat_posture > 0) shadowrun_combat_posture--;
    if (shadowrun_combat_posture_delta == 1 && shadowrun_combat_posture < 4) shadowrun_combat_posture++;
    shadowrun_combat_posture_supported = 1;
}
/* $559CE..$559F4: intermediate field-effect gate. The inputs are the
 * preexisting D5 word (restricted to 1..10), runner +$9F and $FFF0DD.
 * Their high-level meaning and the preceding random/helper calls are not
 * inferred. The source can return early when the adjusted byte is <= 0. */
u8 shadowrun_combat_effect_input;
u8 shadowrun_combat_effect_reference;
u8 shadowrun_combat_effect_value;
u8 shadowrun_combat_effect_proceeds;
u8 shadowrun_combat_effect_supported;
void shadowrun_combat_effect_adjust(void) {
    shadowrun_combat_effect_supported = 0;
    if (shadowrun_combat_effect_input > 127 || shadowrun_combat_effect_reference > 127 || shadowrun_combat_effect_value < 1 || shadowrun_combat_effect_value > 10) return;
    shadowrun_combat_effect_supported = 1;
    shadowrun_combat_effect_proceeds = 1;
    if (shadowrun_combat_effect_input < shadowrun_combat_effect_reference) {
        shadowrun_combat_effect_value = shadowrun_combat_effect_value - (shadowrun_combat_effect_reference - shadowrun_combat_effect_input);
        if (shadowrun_combat_effect_value == 0 || (shadowrun_combat_effect_value & 128U)) shadowrun_combat_effect_proceeds = 0;
    } else {
        shadowrun_combat_effect_value += shadowrun_combat_effect_input - shadowrun_combat_effect_reference;
        if (shadowrun_combat_effect_value > 10) shadowrun_combat_effect_value = 10;
    }
}
/* $55A62..$55A9E: one hit-point application leaf. The caller has already
 * selected this actor branch and supplied positive damage, before negation.
 * Stopping at zero means the original continues into separate side effects. */
u8 shadowrun_combat_hp_primary;
u8 shadowrun_combat_hp_alternate;
u8 shadowrun_combat_hp_selector;
u8 shadowrun_combat_hp_target_flags;
u8 shadowrun_combat_hp_damage;
u8 shadowrun_combat_hp_depleted;
u8 shadowrun_combat_hp_supported;
void shadowrun_combat_apply_hp(void) {
    u8 amount;
    shadowrun_combat_hp_supported = 0;
    if (shadowrun_combat_hp_primary > 127 || shadowrun_combat_hp_alternate > 127 || shadowrun_combat_hp_damage < 1 || shadowrun_combat_hp_damage > 10) return;
    amount = shadowrun_combat_hp_damage;
    if (shadowrun_combat_hp_target_flags & 128U) amount = 1;
    shadowrun_combat_hp_depleted = 0;
    if (shadowrun_combat_hp_selector) {
        shadowrun_combat_hp_selector = 0;
        if (shadowrun_combat_hp_alternate <= amount) {
            shadowrun_combat_hp_alternate = 0;
            shadowrun_combat_hp_depleted = 1;
        } else shadowrun_combat_hp_alternate -= amount;
    } else {
        if (shadowrun_combat_hp_primary <= amount) {
            shadowrun_combat_hp_primary = 0;
            shadowrun_combat_hp_depleted = 1;
        } else shadowrun_combat_hp_primary -= amount;
    }
    shadowrun_combat_hp_supported = 1;
}
