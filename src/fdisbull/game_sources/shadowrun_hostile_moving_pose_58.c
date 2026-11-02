/* Source moving-origin B3EE negative pose 8058 through idle admission.
 * Shares the source-qualified actor projection; retained speed/event are
 * restored after the common service. Unsupported profiles remain refused. */
u8 shadowrun_moving_pose_58_supported;
void shadowrun_hostile_moving_pose_58_step(void) {
    shadowrun_moving_pose_58_supported=0;
    if (shadowrun_attack_speed!=22U || shadowrun_attack_event!=18U ||
        shadowrun_attack_animation!=0x8058U) return;
    shadowrun_attack_speed=65535U;shadowrun_attack_event=16U;
    if (!shadowrun_attack_counter) shadowrun_hostile_attack_zero_counter_step();
    else if (shadowrun_attack_action_timer==65535U) shadowrun_hostile_attack_expired_step();
    else shadowrun_hostile_attack_step();
    shadowrun_attack_speed=22U;shadowrun_attack_event=18U;
    if (!shadowrun_attack_supported) return;
    if (shadowrun_attack_result==2U) shadowrun_attack_increment=352U;
    shadowrun_moving_pose_58_supported=1;
}
