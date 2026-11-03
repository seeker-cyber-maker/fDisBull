/* Project one captured stationary-player reaction pass. Source sprite upload
 * and audio are reported, not performed. At ACAE admission the caller owns
 * the actual input handler and continuation; no callback is guessed here. */
u8 shadowrun_reaction_step_supported,shadowrun_reaction_step_result;
void shadowrun_reaction_step(void) {
    u16 anim;u16 index;u16 sum;u16 dirty;u32 table;u32 sequence;u32 frame;
    shadowrun_reaction_step_supported=0;shadowrun_reaction_step_result=0;
    anim=shadowrun_reaction_animation & 32767U;
    if (shadowrun_reaction_kind!=3U || shadowrun_reaction_flags!=15U ||
        (shadowrun_reaction_flags_low & 254U) || !shadowrun_reaction_hp || !shadowrun_reaction_max_hp ||
        shadowrun_reaction_callback!=0xb07eUL || anim<96U || anim>124U || (anim & 3U)) return;
    if (shadowrun_reaction_animation & 32768U) {
        shadowrun_reaction_outer_gate();
        if (!shadowrun_reaction_supported || !shadowrun_reaction_admitted) return;
        shadowrun_reaction_step_result=2;shadowrun_reaction_step_supported=1;return;
    }
    if (shadowrun_reaction_threshold!=4096U || shadowrun_reaction_increment>4096U ||
        shadowrun_reaction_accumulator>=4096U || shadowrun_reaction_index>1U) return;
    table=rom32(0,0x62acUL+12UL);sequence=rom32(0,table+(u32)anim);
    if (rom16(0,sequence)!=0x8002U) return;
    sum=shadowrun_reaction_accumulator+shadowrun_reaction_increment;
    index=shadowrun_reaction_index;dirty=shadowrun_reaction_flags_low & 1U;
    if (sum>=shadowrun_reaction_threshold) {index+=1U;dirty=1U;}
    if (index>=2U) index=1U;
    frame=rom32(0,sequence+4UL+(u32)index*4UL);
    if (dirty && rom16(0,frame)!=0x8002U) return;
    shadowrun_reaction_outer_gate();
    shadowrun_reaction_callback_tick();
    shadowrun_reaction_advance();
    shadowrun_reaction_select();
    if (dirty) {shadowrun_reaction_flags_low &= 254U;shadowrun_reaction_graphics_pending=1;}
    shadowrun_reaction_step_result=1;shadowrun_reaction_step_supported=1;
}
