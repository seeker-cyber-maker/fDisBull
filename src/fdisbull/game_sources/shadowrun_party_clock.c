/* Captured kind-3 party normal idle/walking pose and sprite clock. Movement
 * supplies the current heading/speed; graphics uploads are an external effect.
 * Source $B45C/$B6BA, $5FDC, $600E and positive selector $6060..$60AE. */
typedef unsigned long u32;
u16 rom16(u8 region,u32 offset);u32 rom32(u8 region,u32 offset);
u16 shadowrun_party_heading,shadowrun_party_transition_heading,shadowrun_party_speed;
u16 shadowrun_party_pose,shadowrun_party_kind;
u32 shadowrun_party_callback;
u8 shadowrun_party_flags_low,shadowrun_party_clock_supported,shadowrun_party_graphics_due;
void shadowrun_party_pose_tick(void) {
    u16 h,rotated;u32 table;
    shadowrun_party_clock_supported=0;
    if (shadowrun_party_kind!=3U) return;
    h=shadowrun_party_heading;
    if (shadowrun_party_callback==0xb45cUL) {
        rotated=(u16)((h<<3)|(h>>13));
        if (rotated & 32768U) rotated+=1U;
        table=0xc052UL;
    } else if (shadowrun_party_callback==0xb574UL) {
        if (shadowrun_party_flags_low & 4U) h=shadowrun_party_transition_heading;
        rotated=(u16)((h<<3)|(h>>13));table=0xc062UL;
    } else return;
    shadowrun_party_pose=rom16(0,table+((rotated&7U)<<1));
    shadowrun_party_clock_supported=1;
}
void shadowrun_party_clock_tick(void) {
    u32 table,sequence;u16 count;
    shadowrun_party_clock_supported=0;shadowrun_party_graphics_due=0;
    if (shadowrun_party_kind!=3U ||
        (shadowrun_party_callback!=0xb45cUL && shadowrun_party_callback!=0xb574UL) ||
        (shadowrun_party_pose&32768U)) return;
    if ((shadowrun_party_pose&3U) ||
        (shadowrun_party_callback==0xb45cUL && shadowrun_party_pose>28U) ||
        (shadowrun_party_callback==0xb574UL &&
         (shadowrun_party_pose<32U || shadowrun_party_pose>60U))) return;
    table=rom32(0,0x62acUL+12UL);sequence=rom32(0,table+shadowrun_party_pose);
    count=rom16(0,sequence);
    if (!count || (count&32768U)) return;
    shadowrun_anim_flags=shadowrun_party_flags_low;
    shadowrun_animation_tick();
    shadowrun_anim_positive_count=count;shadowrun_animation_positive_wrap();
    if (shadowrun_party_speed<22U) shadowrun_anim_increment=shadowrun_party_speed*28U;
    else shadowrun_anim_increment=shadowrun_party_speed*16U;
    shadowrun_party_graphics_due=(shadowrun_anim_flags&1U)!=0;
    shadowrun_party_flags_low=shadowrun_anim_flags&254U;
    shadowrun_party_clock_supported=1;
}
