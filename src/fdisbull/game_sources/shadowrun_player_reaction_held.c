/* Captured party ACAE continuation with A held and an expired action timer.
 * Reuse the identical idle-pose continuation while preserving the held-input
 * state and the expired timer. The temporary substitutions are private to this
 * synchronous call; input dispatch and the next frame's shot remain separate. */
u8 shadowrun_reaction_held_supported;
void shadowrun_reaction_resume_held(void) {
    shadowrun_reaction_held_supported=0;
    if (shadowrun_reaction_input_flags!=64U || shadowrun_reaction_global_e6!=65535U ||
        shadowrun_reaction_action_timer!=65535U) return;
    shadowrun_reaction_input_flags=0;shadowrun_reaction_global_e6=0;
    shadowrun_reaction_action_timer=0;
    shadowrun_reaction_resume_idle();
    shadowrun_reaction_input_flags=64U;shadowrun_reaction_global_e6=65535U;
    shadowrun_reaction_action_timer=65535U;
    if (shadowrun_reaction_resume_supported) shadowrun_reaction_held_supported=1;
}
