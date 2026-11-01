/* Native directional-only adapter over the captured scene's source-bound actor
 * services. A refused movement or actor transition is a hard boundary; callers
 * publish only the preceding completed state. No combat or inventory is added. */
u8 shadowrun_arena_frame_status,shadowrun_arena_hp,shadowrun_courtyard_profile;
void shadowrun_arena_frame(u8 pad) {
    u8 i;
    if (shadowrun_arena_frame_status==2U || shadowrun_courtyard_profile!=1U) {
        shadowrun_arena_frame_status=2;return;
    }
    if (pad & 240U) {shadowrun_arena_frame_status=2;return;}
    shadowrun_ai_frame(pad);
    if (shadowrun_play_refused || shadowrun_opening_status==2U || shadowrun_opening_status==3U || shadowrun_opening_status==4U) {
        shadowrun_arena_frame_status=2;return;
    }
    for (i=0;i<3U;i++) if (shadowrun_ai_slot_status[i]!=1U) {shadowrun_arena_frame_status=2;return;}
    shadowrun_arena_frame_status=1;
}
