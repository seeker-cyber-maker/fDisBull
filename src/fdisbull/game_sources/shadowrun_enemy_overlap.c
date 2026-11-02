/* Source $EB92..$EC4A no-overlap predicate over all ten actor records.
 * An overlap is deliberately refused; source response consumes RNG and has
 * additional effects. Caller supplies complete live source-order records. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u8 shadowrun_ai_overlap_flags[10];
u16 shadowrun_ai_overlap_x[10],shadowrun_ai_overlap_y[10];
u32 shadowrun_ai_overlap_target[10],shadowrun_ai_overlap_attacker[10];
u8 shadowrun_ai_overlap_supported;
void shadowrun_ai_overlap_check(void) {
    u8 i;u8 j;u16 x;u16 y;u16 extent;u32 ai;u32 aj;
    shadowrun_ai_overlap_supported=0;
    for(i=0;i<10;i=i+1) {
        if (!(shadowrun_ai_overlap_flags[i]&1U) || (shadowrun_ai_overlap_flags[i]&64U)) continue;
        x=shadowrun_ai_overlap_x[i];y=shadowrun_ai_overlap_y[i];
        if (x<256U || y<256U || x>65279U || y>65279U) return;
    }
    for(i=0;i<10;i=i+1) {
        if (!(shadowrun_ai_overlap_flags[i]&1U) || (shadowrun_ai_overlap_flags[i]&64U)) continue;
        for(j=i+1U;j<10;j=j+1) {
            if (!(shadowrun_ai_overlap_flags[j]&1U) || (shadowrun_ai_overlap_flags[j]&64U)) continue;
            ai=0xff0100UL+(u32)i*256UL;aj=0xff0100UL+(u32)j*256UL;
            extent=64U;
            if (shadowrun_ai_overlap_target[j]==ai || shadowrun_ai_overlap_target[i]==aj ||
                shadowrun_ai_overlap_attacker[j]==ai || shadowrun_ai_overlap_attacker[i]==aj) extent=256U;
            x=shadowrun_ai_overlap_x[j];y=shadowrun_ai_overlap_y[j];
            if (shadowrun_ai_overlap_x[i]>=x-extent && shadowrun_ai_overlap_x[i]<x+extent &&
                shadowrun_ai_overlap_y[i]>=y-extent && shadowrun_ai_overlap_y[i]<y+extent) return;
        }
    }
    shadowrun_ai_overlap_supported=1;
}
