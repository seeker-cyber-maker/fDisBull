/* Bounded translation of original $5A56/$5A62 normal screen projection and
 * $1DC4C..$1DD2C ordinary NPC targeting. The actor records and camera are
 * supplied by the caller; NPC AI and line-of-sight are not represented.
 * Slots 0..6 correspond to $FF0400..$FF0A00. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef signed int i16;
u16 shadowrun_target_x[7],shadowrun_target_y[7],shadowrun_target_height[7];
u16 shadowrun_target_contact[7],shadowrun_target_marker[7],shadowrun_target_index[7];
u8 shadowrun_target_flags[7],shadowrun_target_flags_low[7],shadowrun_target_flags_b0[7];
u8 shadowrun_target_backlink[7],shadowrun_target_special_callback[7];
u8 shadowrun_target_selected=255U,shadowrun_target_item,shadowrun_target_equipped_slot;
u8 shadowrun_target_player_backlink,shadowrun_target_d1_magic,shadowrun_target_player_43;
u8 shadowrun_target_supported,shadowrun_target_result;
extern u16 shadowrun_camera_x,shadowrun_camera_y;

/* Signed word arithmetic and original asr #4 followed by carry rounding. */
i16 shadowrun_target_relative(u16 position,u16 camera) {
    u16 difference;
    i16 rounded;
    difference=position-camera;
    rounded=(i16)difference >> 4;
    if (difference & 8U) rounded++;
    return rounded;
}

void shadowrun_target_refresh(void) {
    u8 i;
    i16 sx,sy;
    shadowrun_target_supported=0;
    for(i=0;i<7;i++) {
        if ((shadowrun_target_flags[i]&1U) && shadowrun_target_special_callback[i]) return;
    }
    for(i=0;i<7;i++) {
        if (shadowrun_target_flags[i]&1U) {
            sx=shadowrun_target_relative(shadowrun_target_x[i],shadowrun_camera_x)+128;
            sy=shadowrun_target_relative(shadowrun_target_y[i],shadowrun_camera_y)+128+shadowrun_target_height[i];
            if (sx<112 || sx>429 || sy<99 || sy>=378) shadowrun_target_contact[i]=0;
            else shadowrun_target_contact[i]=(u16)sy;
        }
    }
    shadowrun_target_supported=1;
}

void shadowrun_target_cycle(void) {
    u8 slot,i,previous;
    shadowrun_target_supported=0;shadowrun_target_result=0;
    if ((shadowrun_target_equipped_slot&128U) &&
        (shadowrun_target_item==4U || shadowrun_target_item==11U || shadowrun_target_item==12U)) return;
    /* Alternate reciprocal-target and special d1 routes are separate paths. */
    if (shadowrun_target_player_backlink || shadowrun_target_d1_magic) return;
    if (shadowrun_target_selected!=255U && shadowrun_target_selected>=7U) return;
    previous=shadowrun_target_selected;
    slot=0;
    if(previous!=255U) {
        shadowrun_target_flags_low[previous]&=239U;
        shadowrun_target_selected=255U;
        slot=previous+1U;
        if(slot>=7U) slot=0;
    }
    for(i=0;i<8;i++) {
        if(shadowrun_target_index[slot]<3U) slot=0;
        if ((shadowrun_target_flags[slot]&1U) &&
            !(shadowrun_target_flags[slot]&0x50U) &&
            !(shadowrun_target_flags_b0[slot]&0x80U) &&
            shadowrun_target_contact[slot]) {
            shadowrun_target_player_43=0;
            shadowrun_target_flags_low[slot]|=16U;
            shadowrun_target_selected=slot;
            shadowrun_target_backlink[slot]=1;
            shadowrun_target_marker[slot]=0x8009U;
            shadowrun_target_result=1;
            break;
        }
        slot++;
        if(slot>=7U) slot=0;
    }
    shadowrun_target_supported=1;
}
