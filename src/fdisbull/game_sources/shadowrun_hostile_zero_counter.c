/* Source service with depleted hostile activity counter. Counter remains zero;
 * the existing bounded projection has no other dependence on its magnitude. */
void shadowrun_hostile_attack_zero_counter_step(void) {
    shadowrun_attack_supported=0;
    if (shadowrun_attack_counter) return;
    shadowrun_attack_counter=1U;
    if (shadowrun_attack_action_timer==65535U) shadowrun_hostile_attack_expired_step();
    else shadowrun_hostile_attack_step();
    shadowrun_attack_counter=0;
}
void shadowrun_hostile_idle_zero_counter_step(void) {
    shadowrun_hostile_idle_supported=0;
    if (shadowrun_attack_counter) return;
    shadowrun_attack_counter=1U;
    shadowrun_hostile_idle_step();
    shadowrun_attack_counter=0;
}
void shadowrun_hostile_relaunch_zero_counter(void) {
    shadowrun_attack_relaunch_supported=0;
    if (shadowrun_attack_counter) return;
    shadowrun_attack_counter=1U;
    shadowrun_hostile_relaunch_first();
    shadowrun_attack_counter=0;
}
/* When a source player hit returns the actor loop to this shooter, the actor
 * pass runs twice while the sprite pass runs once. The caller attests that
 * source loop re-entry, as established by the source writer trace. */
void shadowrun_hostile_positive_reentry_step(void) {
    shadowrun_hostile_attack_positive_step();
    if (!shadowrun_attack_positive_supported) return;
    if (!(shadowrun_attack_action_timer & 32768U)) shadowrun_attack_action_timer-=1U;
}
