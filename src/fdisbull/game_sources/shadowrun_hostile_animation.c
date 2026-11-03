/* Projectile kind 1 impact sprite pass: counter $5FDC and negative-count
 * selector $600E. Caller invokes this only on an original sprite pass. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u16 rom16(u8 region,u32 offset);
u16 shadowrun_burst_anim_word,shadowrun_burst_anim_increment,shadowrun_burst_anim_accumulator;
u16 shadowrun_burst_anim_threshold,shadowrun_burst_anim_index;
u8 shadowrun_burst_anim_flags,shadowrun_burst_anim_profile,shadowrun_burst_anim_supported;
void shadowrun_burst_animation_tick(void) {
    u16 id;u16 count;u16 value;u16 index;u16 flags;u32 table;u32 frame;
    shadowrun_burst_anim_supported=0;
    id=shadowrun_burst_anim_word&32767U;
    if (shadowrun_burst_anim_profile!=1U ||
        (id!=0U && id!=4U && id!=12U && id!=16U && id!=20U) ||
        (id==20U && (shadowrun_burst_anim_flags&8U)) ||
        (id!=20U && !(shadowrun_burst_anim_flags&8U)) ||
        shadowrun_burst_anim_threshold!=4096U || shadowrun_burst_anim_accumulator>=4096U ||
        (shadowrun_burst_anim_increment!=0U && shadowrun_burst_anim_increment!=2U &&
         shadowrun_burst_anim_increment!=1024U &&
         shadowrun_burst_anim_increment!=2048U) || shadowrun_burst_anim_index>5U) return;
    table=(u32)rom16(0,0x62b0UL)*65536UL+rom16(0,0x62b2UL);
    frame=(u32)rom16(0,table+id)*65536UL+rom16(0,table+id+2UL);
    count=rom16(0,frame);
    if (!(count & 32768U) || !(count & 32767U) || (count & 32767U)>5U) return;
    count&=32767U;value=shadowrun_burst_anim_accumulator+shadowrun_burst_anim_increment;
    index=shadowrun_burst_anim_index;flags=shadowrun_burst_anim_flags;
    if (value>=4096U) {index+=1U;flags|=1U;value-=4096U;}
    if (index>=count) {shadowrun_burst_anim_word|=32768U;index=count-1U;}
    shadowrun_burst_anim_accumulator=value;shadowrun_burst_anim_index=index;
    shadowrun_burst_anim_flags=(u8)flags;shadowrun_burst_anim_increment=rom16(0,frame+2UL);
    shadowrun_burst_anim_supported=1;
}
