/* One actor's source-order $EB92 scan. Caller invokes once at each original
 * actor dispatch, including first-party actors, with all live slots. */
u8 shadowrun_ai_overlap_slot;
void shadowrun_ai_overlap_check_one(void) {
    u8 i;u8 j;u16 x;u16 y;u16 extent;u32 ai;u32 aj;
    shadowrun_ai_overlap_supported=0;
    i=shadowrun_ai_overlap_slot;
    if (i>=10U || !(shadowrun_ai_overlap_flags[i]&1U)) return;
    if ((shadowrun_ai_overlap_flags[i]&64U) || i==9U) {shadowrun_ai_overlap_supported=1;return;}
    x=shadowrun_ai_overlap_x[i];y=shadowrun_ai_overlap_y[i];
    if (x<256U || y<256U || x>65279U || y>65279U) return;
    ai=0xff0100UL+(u32)i*256UL;
    for(j=i+1U;j<10U;j=j+1) {
        if (!(shadowrun_ai_overlap_flags[j]&1U) || (shadowrun_ai_overlap_flags[j]&64U)) continue;
        x=shadowrun_ai_overlap_x[j];y=shadowrun_ai_overlap_y[j];
        if (x<256U || y<256U || x>65279U || y>65279U) return;
        aj=0xff0100UL+(u32)j*256UL;
        extent=64U;
        if (shadowrun_ai_overlap_target[j]==ai || shadowrun_ai_overlap_target[i]==aj ||
            shadowrun_ai_overlap_attacker[j]==ai || shadowrun_ai_overlap_attacker[i]==aj) extent=256U;
        if (shadowrun_ai_overlap_x[i]>=x-extent && shadowrun_ai_overlap_x[i]<x+extent &&
            shadowrun_ai_overlap_y[i]>=y-extent && shadowrun_ai_overlap_y[i]<y+extent) return;
    }
    shadowrun_ai_overlap_supported=1;
}
