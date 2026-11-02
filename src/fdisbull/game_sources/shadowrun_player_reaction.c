/* Captured party player nonlethal reaction: source $AFF2, $B07E,
 * $5FDC..$605C and outer $A8FC..$ACAE. Audio and sprite upload are external. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u16 rom16(u8 region,u32 offset);u32 rom32(u8 region,u32 offset);
u16 shadowrun_reaction_kind,shadowrun_reaction_x,shadowrun_reaction_y,shadowrun_reaction_heading;
u16 shadowrun_reaction_animation,shadowrun_reaction_increment,shadowrun_reaction_accumulator;
u16 shadowrun_reaction_threshold,shadowrun_reaction_index,shadowrun_reaction_move_state,shadowrun_reaction_action_timer;
u32 shadowrun_reaction_callback;
u8 shadowrun_reaction_flags,shadowrun_reaction_flags_low,shadowrun_reaction_hp,shadowrun_reaction_max_hp;
u8 shadowrun_reaction_counter,shadowrun_reaction_corners[4];
u8 shadowrun_reaction_supported,shadowrun_reaction_sound_due,shadowrun_reaction_graphics_pending,shadowrun_reaction_admitted;
void shadowrun_reaction_start(void) {
    u16 rotated;
    shadowrun_reaction_supported=0;
    if (shadowrun_reaction_kind!=3U || shadowrun_reaction_flags!=15U || !shadowrun_reaction_hp || !shadowrun_reaction_max_hp) return;
    rotated=(u16)((shadowrun_reaction_heading<<3)|(shadowrun_reaction_heading>>13));
    if (rotated & 32768U) rotated+=1U;
    shadowrun_reaction_callback=0xb07eUL;
    shadowrun_reaction_animation=rom16(0,0xc072UL+((rotated & 7U)<<1));
    shadowrun_reaction_accumulator=0;shadowrun_reaction_index=0;
    shadowrun_reaction_flags_low|=1U;shadowrun_reaction_counter=8U;shadowrun_reaction_supported=1;
}
void shadowrun_reaction_callback_tick(void) {
    u16 i;
    shadowrun_reaction_supported=0;shadowrun_reaction_sound_due=0;
    if (shadowrun_reaction_kind!=3U || shadowrun_reaction_flags!=15U || shadowrun_reaction_callback!=0xb07eUL) return;
    shadowrun_reaction_counter-=1U;
    if (!shadowrun_reaction_counter) shadowrun_reaction_sound_due=1;
    shadowrun_fixed_x=shadowrun_reaction_x;shadowrun_fixed_y=shadowrun_reaction_y;
    shadowrun_probe_flags=shadowrun_reaction_flags;shadowrun_collision_check();
    shadowrun_reaction_move_state=0;
    for (i=0;i<4U;i+=1U) shadowrun_reaction_corners[i]=shadowrun_probe_corners[i];
    shadowrun_reaction_supported=1;
}
void shadowrun_reaction_advance(void) {
    u16 value;u16 anim;
    shadowrun_reaction_supported=0;shadowrun_reaction_graphics_pending=0;
    anim=shadowrun_reaction_animation & 32767U;
    if (shadowrun_reaction_kind!=3U || shadowrun_reaction_callback!=0xb07eUL ||
        anim<96U || anim>124U || (anim & 3U) || shadowrun_reaction_threshold!=4096U ||
        shadowrun_reaction_increment>4096U || shadowrun_reaction_accumulator>=4096U || shadowrun_reaction_index>1U) return;
    value=shadowrun_reaction_accumulator+shadowrun_reaction_increment;
    if (value>=shadowrun_reaction_threshold) {
        shadowrun_reaction_index+=1U;shadowrun_reaction_flags_low|=1U;
        shadowrun_reaction_graphics_pending=1;value-=shadowrun_reaction_threshold;
    }
    shadowrun_reaction_accumulator=value;shadowrun_reaction_supported=1;
}
void shadowrun_reaction_select(void) {
    u32 table;u32 sequence;u16 count;u16 anim;
    shadowrun_reaction_supported=0;anim=shadowrun_reaction_animation & 32767U;
    if (shadowrun_reaction_kind!=3U || shadowrun_reaction_callback!=0xb07eUL ||
        anim<96U || anim>124U || (anim & 3U) || shadowrun_reaction_index>2U) return;
    table=rom32(0,0x62acUL+12UL);sequence=rom32(0,table+(u32)anim);
    count=rom16(0,sequence);
    if (!(count & 32768U) || (count & 32767U)!=2U) return;
    if (shadowrun_reaction_index>=2U) {
        shadowrun_reaction_animation|=32768U;shadowrun_reaction_index=1U;
    }
    shadowrun_reaction_increment=rom16(0,sequence+2UL);
    shadowrun_reaction_supported=1;
}
void shadowrun_reaction_outer_gate(void) {
    u16 anim;
    shadowrun_reaction_supported=0;shadowrun_reaction_admitted=0;
    anim=shadowrun_reaction_animation & 32767U;
    if (shadowrun_reaction_kind!=3U || shadowrun_reaction_flags!=15U ||
        (shadowrun_reaction_flags_low & 22U) || !shadowrun_reaction_hp || !shadowrun_reaction_max_hp ||
        shadowrun_reaction_callback!=0xb07eUL || anim<96U || anim>124U || (anim & 3U)) return;
    if (!(shadowrun_reaction_action_timer & 32768U)) shadowrun_reaction_action_timer-=1U;
    if (shadowrun_reaction_animation & 32768U) shadowrun_reaction_admitted=1;
    shadowrun_reaction_supported=1;
}
