/* $D5A..$D92: wound modifiers added to the captured pistol's threshold4.
 * Other source difficulty modifiers and the attack roll are separate. */
typedef unsigned char u8;
u8 shadowrun_player_attack_hp;
u8 shadowrun_player_attack_alternate_hp;
u8 shadowrun_player_attack_difficulty;
u8 shadowrun_player_attack_supported;
void shadowrun_player_attack_threshold(void) {
    shadowrun_player_attack_supported = 0;
    if (shadowrun_player_attack_hp < 1 || shadowrun_player_attack_hp > 10 ||
        shadowrun_player_attack_alternate_hp < 1 ||
        shadowrun_player_attack_alternate_hp > 10) return;
    shadowrun_player_attack_difficulty = 4;
    if (shadowrun_player_attack_hp < 8) {
        if (shadowrun_player_attack_hp < 5) shadowrun_player_attack_difficulty += 2;
        else shadowrun_player_attack_difficulty += 1;
    }
    if (shadowrun_player_attack_alternate_hp < 8) {
        if (shadowrun_player_attack_alternate_hp < 5) shadowrun_player_attack_difficulty += 2;
        else shadowrun_player_attack_difficulty += 1;
    }
    shadowrun_player_attack_supported = 1;
}
