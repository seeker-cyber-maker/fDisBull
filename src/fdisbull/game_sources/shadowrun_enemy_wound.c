/* Captured nonlethal actor callback $B07E..$B0AA. Audio service is reported
 * as a pending external effect; collision state and sound hardware are not
 * claimed by this actor-state projection. */
u8 shadowrun_ai_wound_counter,shadowrun_ai_wound_supported,shadowrun_ai_wound_sound_due;
void shadowrun_ai_wound_tick(void) {
    u16 i;
    shadowrun_ai_wound_supported=0;shadowrun_ai_wound_sound_due=0;
    if (shadowrun_ai_kind!=11U || shadowrun_ai_callback!=0xb07eUL || shadowrun_ai_flags!=37U) return;
    shadowrun_ai_wound_counter-=1U;
    if (!shadowrun_ai_wound_counter) shadowrun_ai_wound_sound_due=1;
    shadowrun_fixed_x=shadowrun_ai_x;shadowrun_fixed_y=shadowrun_ai_y;
    shadowrun_probe_flags=shadowrun_ai_flags;shadowrun_collision_check();
    shadowrun_ai_move_state=0;
    for(i=0;i<4;i=i+1)shadowrun_ai_corners[i]=shadowrun_probe_corners[i];
    shadowrun_ai_wound_supported=1;
}
