/* No-input reaction recovery after captured combat walking. The party sprite
 * service supplies speed28 separately from the last movement step speed16. */
u16 shadowrun_reaction_normal_sprite_speed;
u8 shadowrun_reaction_idle_walk_supported;
void shadowrun_reaction_resume_idle_walk(void) {
    shadowrun_reaction_idle_walk_supported=0;
    if (shadowrun_reaction_speed!=16U || shadowrun_reaction_normal_sprite_speed!=28U ||
        (shadowrun_reaction_action_timer & 32768U)) return;
    shadowrun_reaction_speed=30U;
    shadowrun_reaction_resume_idle();
    shadowrun_reaction_speed=16U;
    if (!shadowrun_reaction_resume_supported) return;
    shadowrun_reaction_increment=shadowrun_reaction_normal_sprite_speed*16U;
    shadowrun_reaction_idle_walk_supported=1;
}
