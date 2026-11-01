/* Project $A8FA..$AA70 onto the reviewed movement read set. Selected +B3
 * receives unknown inherited D0 and must remain explicitly unknown; no later
 * unreviewed source consumer may use that value as though it were preserved. */
u8 shadowrun_ai_outer_b3_unknown;
void shadowrun_ai_outer_movement_projection(void) {
    u8 flags_low;
    flags_low=shadowrun_ai_outer_flags_low;
    shadowrun_ai_outer_flags_low=flags_low & 239U;
    shadowrun_ai_outer_prepare();
    shadowrun_ai_outer_flags_low=flags_low;
    shadowrun_ai_outer_b3_unknown=0;
    if (shadowrun_ai_outer_supported && (flags_low & 16U)) shadowrun_ai_outer_b3_unknown=1;
}
