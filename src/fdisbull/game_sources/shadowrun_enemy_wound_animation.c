/* Type-11 wounded animation state, source counter $5FDC..$600C and negative
 * count selector $600E..$605C. Sprite upload is an external pending effect. */
u16 shadowrun_ai_wound_accumulator,shadowrun_ai_wound_increment;
u16 shadowrun_ai_wound_threshold,shadowrun_ai_wound_index;
u8 shadowrun_ai_wound_anim_supported,shadowrun_ai_wound_graphics_pending;
void shadowrun_ai_wound_advance(void) {
    u16 value;
    shadowrun_ai_wound_anim_supported=0;shadowrun_ai_wound_graphics_pending=0;
    if (shadowrun_ai_kind!=11U || shadowrun_ai_callback!=0xb07eUL ||
        (shadowrun_ai_animation!=0x7cU && shadowrun_ai_animation!=0x807cU) ||
        shadowrun_ai_wound_threshold!=4096U || shadowrun_ai_wound_increment!=768U ||
        shadowrun_ai_wound_accumulator>=4096U || shadowrun_ai_wound_index>1U) return;
    value=shadowrun_ai_wound_accumulator+shadowrun_ai_wound_increment;
    if (value>=shadowrun_ai_wound_threshold) {
        shadowrun_ai_wound_index+=1U;
        shadowrun_ai_flags_low |= 1U;
        shadowrun_ai_wound_graphics_pending=1;
        value-=shadowrun_ai_wound_threshold;
    }
    shadowrun_ai_wound_accumulator=value;shadowrun_ai_wound_anim_supported=1;
}
void shadowrun_ai_wound_select(void) {
    u32 table;u32 sequence;u16 count;
    shadowrun_ai_wound_anim_supported=0;
    if (shadowrun_ai_kind!=11U || shadowrun_ai_callback!=0xb07eUL ||
        (shadowrun_ai_animation!=0x7cU && shadowrun_ai_animation!=0x807cU) ||
        shadowrun_ai_wound_index>2U) return;
    table=rom32(0,0x62acUL+44UL);
    sequence=rom32(0,table+(u32)(shadowrun_ai_animation & 32767U));
    count=rom16(0,sequence);
    if (!(count & 32768U) || (count & 32767U)!=2U) return;
    count &= 32767U;
    if (shadowrun_ai_wound_index>=count) {
        shadowrun_ai_animation |= 32768U;
        shadowrun_ai_wound_index=count-1U;
    }
    shadowrun_ai_wound_increment=rom16(0,sequence+2UL);
    shadowrun_ai_wound_anim_supported=1;
}
