/* Separate bounded CNROM adapter for the reviewed right-walk slice. Included
 * by the private build after the opening platform declarations. */
extern u16 shadowrun_anim_accumulator,shadowrun_anim_increment,shadowrun_anim_threshold;
extern u16 shadowrun_anim_index,shadowrun_anim_positive_count;
extern u8 shadowrun_anim_flags;
extern void shadowrun_animation_tick(void);
extern void shadowrun_animation_positive_wrap(void);
extern u16 shadowrun_player_step_timer,shadowrun_player_transition_heading;
extern u8 shadowrun_player_flags_low;
extern const u8 shadowrun_anim_oam[],shadowrun_anim_count[],shadowrun_anim_offsets[];
extern const u8 shadowrun_anim_selector_table[];
extern const u8 shadowrun_anim_bank_values[];
static u8 anim_started,anim_fault,anim_pending,anim_display,anim_ticks;
static i16 anim_base_x,anim_base_y;
static u8 anim_allow(u8 pad) {
    if (anim_fault) return 0;
    if (!anim_started && !pad) return 0;
    if (pad!=8) {anim_fault=1;return 0;}
    if (anim_ticks>=60) {anim_fault=2;return 0;}
    anim_started=1;
    anim_ticks++;
    anim_display=anim_pending;
    anim_base_x=rounded_sixteenth((i16)(shadowrun_player_x-shadowrun_camera_x));
    anim_base_y=rounded_sixteenth((i16)(shadowrun_player_y-shadowrun_camera_y));
    shadowrun_animation_tick();
    return 1;
}
static void anim_after(void) {
    u16 heading,ordinal,selector,speed;
    u8 pose=255;
    if (shadowrun_opening_status!=1) {anim_fault=1;return;}
    heading=(shadowrun_player_flags_low&4U)?shadowrun_player_transition_heading:shadowrun_player_heading;
    ordinal=(u16)(((heading<<3)|(heading>>13))&7U);
    selector=((u16)shadowrun_anim_selector_table[ordinal*2]<<8)|shadowrun_anim_selector_table[ordinal*2+1];
    /* All currently observed walking selector records have four frames. */
    shadowrun_anim_positive_count=4;
    shadowrun_animation_positive_wrap();
    if (selector==0x2cU) {
        if (shadowrun_anim_index==0) pose=1;
        else if (shadowrun_anim_index==1) pose=2;
    } else if (selector==0x28U) {
        if (shadowrun_anim_index==0) pose=6;
        else if (shadowrun_anim_index==1) pose=3;
        else if (shadowrun_anim_index==2) pose=4;
        else if (shadowrun_anim_index==3) pose=5;
    }
    if (pose==255) {anim_fault=1;return;}
    anim_pending=pose;
    speed=shadowrun_player_step_timer;
    shadowrun_anim_increment=(u16)(speed*(speed<22U?28U:16U));
}
static i16 anim_signed_byte(u8 v) {return v<128U?(i16)v:(i16)v-256;}
static void anim_place_actor(void) {
    u8 i,count=shadowrun_anim_count[anim_display];
    const u8 *p=shadowrun_anim_oam+(u16)anim_display*64U;
    i16 x,y,base_x=anim_base_x+anim_signed_byte(shadowrun_anim_offsets[anim_display*2]);
    i16 base_y=anim_base_y+anim_signed_byte(shadowrun_anim_offsets[anim_display*2+1]);
    for(i=0;i<64;i++) OAM[i*4]=0xf0;
    for(i=0;i<count;i++) {
        y=base_y+anim_signed_byte(p[0]);x=base_x+p[3];
        if(x>=0 && x<=255 && y>=0 && y<=223) {
            OAM[i*4]=(u8)y;OAM[i*4+1]=p[1];OAM[i*4+2]=p[2];OAM[i*4+3]=(u8)x;
        }
        p+=4;
    }
    /* Writing to a ROM byte with the same value tolerates CNROM bus conflicts. */
    *((volatile u8*)&shadowrun_anim_bank_values[anim_display])=anim_display;
}
