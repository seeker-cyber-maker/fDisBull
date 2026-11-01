/* Sprite-only pass after a hit that occurred after the player actor pass,
 * plus the captured no-input $ACAE -> $AE40 -> $B45C idle continuation.
 * Sound and graphics transfers remain explicit external effects. */
u8 shadowrun_reaction_sprite_supported,shadowrun_reaction_resume_supported;
u8 shadowrun_reaction_cursor,shadowrun_reaction_attr_a,shadowrun_reaction_attr_b;
u16 shadowrun_reaction_gear,shadowrun_reaction_speed;
u16 shadowrun_reaction_input_flags,shadowrun_reaction_input_heading,shadowrun_reaction_global_e6,shadowrun_reaction_global_3a;
u8 shadowrun_reaction_global_18a,shadowrun_reaction_global_18b;
void shadowrun_reaction_sprite_only(void) {
    u16 anim;u16 index;u16 sum;u16 dirty;u32 table;u32 sequence;u32 frame;
    shadowrun_reaction_sprite_supported=0;
    anim=shadowrun_reaction_animation & 32767U;
    if (shadowrun_reaction_kind!=3U || shadowrun_reaction_flags!=15U ||
        (shadowrun_reaction_flags_low & 254U) || !shadowrun_reaction_hp || !shadowrun_reaction_max_hp ||
        shadowrun_reaction_callback!=0xb07eUL || (shadowrun_reaction_animation & 32768U) ||
        anim<96U || anim>124U || (anim & 3U) || shadowrun_reaction_threshold!=4096U ||
        shadowrun_reaction_increment>4096U || shadowrun_reaction_accumulator>=4096U || shadowrun_reaction_index>1U) return;
    table=rom32(0,0x62acUL+12UL);sequence=rom32(0,table+(u32)anim);
    if (rom16(0,sequence)!=0x8002U) return;
    sum=shadowrun_reaction_accumulator+shadowrun_reaction_increment;
    index=shadowrun_reaction_index;dirty=shadowrun_reaction_flags_low & 1U;
    if (sum>=shadowrun_reaction_threshold) {index+=1U;dirty=1U;}
    if (index>=2U) index=1U;
    frame=rom32(0,sequence+4UL+(u32)index*4UL);
    if (dirty && rom16(0,frame)!=0x8002U) return;
    shadowrun_reaction_advance();shadowrun_reaction_select();
    if (dirty) {shadowrun_reaction_flags_low &= 254U;shadowrun_reaction_graphics_pending=1;}
    shadowrun_reaction_sprite_supported=1;
}
void shadowrun_reaction_resume_idle(void) {
    u16 rotated;u16 anim;u16 sum;u16 index;u16 d1;u16 cooldown;u16 i;u32 table;u32 sequence;u32 frame;
    shadowrun_reaction_resume_supported=0;
    if (shadowrun_reaction_kind!=3U || shadowrun_reaction_flags!=15U ||
        (shadowrun_reaction_flags_low & 254U) || !shadowrun_reaction_hp || !shadowrun_reaction_max_hp ||
        shadowrun_reaction_callback!=0xb07eUL || !(shadowrun_reaction_animation & 32768U) ||
        shadowrun_reaction_input_flags || shadowrun_reaction_input_heading!=65535U ||
        shadowrun_reaction_global_e6 || shadowrun_reaction_global_3a ||
        shadowrun_reaction_global_18a || shadowrun_reaction_global_18b ||
        shadowrun_reaction_gear!=4U || shadowrun_reaction_attr_a!=3U || shadowrun_reaction_attr_b!=2U ||
        shadowrun_reaction_speed!=30U || shadowrun_reaction_threshold!=4096U ||
        shadowrun_reaction_increment>4096U || shadowrun_reaction_accumulator>=4096U || shadowrun_reaction_index>1U) return;
    rotated=(u16)((shadowrun_reaction_heading<<3)|(shadowrun_reaction_heading>>13));
    if (rotated & 32768U) rotated+=1U;
    anim=rom16(0,0xc052UL+((rotated & 7U)<<1));
    table=rom32(0,0x62acUL+12UL);sequence=rom32(0,table+(u32)anim);
    if (rom16(0,sequence)!=1U) return;
    frame=rom32(0,sequence+4UL);if (rom16(0,frame)!=0x8002U) return;
    if (shadowrun_reaction_action_timer & 32768U) {
        d1=(shadowrun_reaction_attr_a+shadowrun_reaction_attr_b)/2U;
        if (d1) d1-=1U;
        cooldown=(106U-d1*4U)/2U;if (cooldown<15U) cooldown=15U;
        shadowrun_reaction_action_timer=cooldown;shadowrun_reaction_cursor+=1U;
    }
    shadowrun_reaction_callback=0xb45cUL;shadowrun_reaction_flags_low|=1U;
    shadowrun_fixed_x=shadowrun_reaction_x;shadowrun_fixed_y=shadowrun_reaction_y;
    shadowrun_probe_flags=shadowrun_reaction_flags;shadowrun_collision_check();
    shadowrun_reaction_move_state=0;shadowrun_reaction_animation=anim;
    for(i=0;i<4U;i+=1U)shadowrun_reaction_corners[i]=shadowrun_probe_corners[i];
    sum=shadowrun_reaction_accumulator+shadowrun_reaction_increment;index=shadowrun_reaction_index;
    if (sum>=shadowrun_reaction_threshold) {index+=1U;sum-=shadowrun_reaction_threshold;}
    if (index>=1U) index=0;
    shadowrun_reaction_accumulator=sum;shadowrun_reaction_index=index;
    shadowrun_reaction_increment=shadowrun_reaction_speed*16U;
    shadowrun_reaction_flags_low &= 254U;shadowrun_reaction_graphics_pending=1;
    shadowrun_reaction_resume_supported=1;
}
