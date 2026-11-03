/* B3EE negative pose and service expiry after the prepared moving shot.
 * The common stationary service uses the same actor operations; the source
 * retains the moving speed and event bits, including speed-based idle clock. */
u8 shadowrun_moving_pose_supported;
void shadowrun_hostile_moving_pose_step(void) {
    u16 speed;u8 event;
    shadowrun_moving_pose_supported=0;
    if (shadowrun_attack_speed!=22U || shadowrun_attack_event!=18U ||
        shadowrun_attack_animation!=0x8054U) return;
    speed=shadowrun_attack_speed;event=shadowrun_attack_event;
    shadowrun_attack_speed=65535U;shadowrun_attack_event=16U;
    if (shadowrun_attack_action_timer==65535U) shadowrun_hostile_attack_expired_step();
    else shadowrun_hostile_attack_step();
    shadowrun_attack_speed=speed;shadowrun_attack_event=event;
    if (!shadowrun_attack_supported) return;
    if (shadowrun_attack_result==2U) shadowrun_attack_increment=speed*16U;
    shadowrun_moving_pose_supported=1;
}
