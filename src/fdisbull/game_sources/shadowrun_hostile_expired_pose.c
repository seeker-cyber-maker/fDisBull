/* Source B3EE stationary service with an already-expired action timer.
 * The underlying bounded service decrements a nonnegative timer; entering
 * with zero yields the source's stable FFFF sentinel during this call. */
void shadowrun_hostile_attack_expired_step(void) {
    shadowrun_attack_supported=0;
    if (shadowrun_attack_action_timer!=65535U) return;
    shadowrun_attack_action_timer=0;
    shadowrun_hostile_attack_step();
    if (!shadowrun_attack_supported) shadowrun_attack_action_timer=65535U;
}
