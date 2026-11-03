/* Private NES opening experiment. The GameIL supplies bounded movement; this
 * adapter supplies captured state, source-table reads and a diagnostic view.
 * Bounded camera coverage and unsupported actions are explicit in its manifest. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef signed int i16;
typedef unsigned long u32;
extern const u8 shadowrun_scene[];
extern const u8 shadowrun_initial_map[2816];
extern const u8 shadowrun_table_input[32];
extern const u8 shadowrun_table_move[32];
extern const u8 shadowrun_table_stand[16];
extern const u8 shadowrun_table_camera[320];
extern const u8 shadowrun_camera_valid[];
extern const u8 shadowrun_table_rectangles[320];
extern u8 shadowrun_terrain_map[2816];
extern u16 shadowrun_pad_held,shadowrun_pad_sample,shadowrun_direction_angle;
extern u16 shadowrun_player_x,shadowrun_player_y,shadowrun_player_heading,shadowrun_player_target_heading;
extern u16 shadowrun_player_kind,shadowrun_player_contact,shadowrun_global_special_mode;
extern u8 shadowrun_player_flags,shadowrun_player_equipment_flags,shadowrun_global_vector_flags;
extern u16 shadowrun_x_min,shadowrun_x_max,shadowrun_y_min,shadowrun_y_max;
extern u32 shadowrun_rect_base;
extern u8 shadowrun_player_event_flags,shadowrun_opening_status;
extern void shadowrun_opening_frame(u8);
#ifdef SHADOWRUN_STOKER
extern void shadowrun_opening_stoker_frame(u8);
extern u8 shadowrun_stoker_ui_mode;
extern u8 shadowrun_stoker_ui_unsupported;
#endif
#ifdef SHADOWRUN_STOKER_VISUAL
extern const u8 shadowrun_ui_scenes[];
#endif
extern u16 shadowrun_camera_x,shadowrun_camera_y,shadowrun_camera_scroll_ax,shadowrun_camera_scroll_ay;
extern u8 shadowrun_camera_supported;
extern void shadowrun_seed_scene(void);
#define PPUCTRL (*(volatile u8*)0x2000)
#define PPUMASK (*(volatile u8*)0x2001)
#define PPUSTATUS (*(volatile u8*)0x2002)
#define PPUADDR (*(volatile u8*)0x2006)
#define PPUDATA (*(volatile u8*)0x2007)
#define PPUSCROLL (*(volatile u8*)0x2005)
#define PAD (*(volatile u8*)0x4016)
#define OAMADDR (*(volatile u8*)0x2003)
#define OAMDMA (*(volatile u8*)0x4014)
#define OAM ((volatile u8*)0x0200)
#define PUBLICATION ((volatile u8*)0x0700)
extern const u16 shadowrun_seed_x,shadowrun_seed_y,shadowrun_atlas_origin_x,shadowrun_atlas_origin_y;
extern const u8 shadowrun_sprite_count,shadowrun_camera_y_max,shadowrun_fast_sprite;
extern const u16 shadowrun_scene_background_size;
static u8 rom_fault;
u16 rom16(u8 region,u32 offset) {
    const u8 *table;
    u16 i;
    if (region != 0) {rom_fault = 1;return 0;}
    if (offset >= 0x172daaUL && offset < 0x172ee9UL) {
        table=shadowrun_table_rectangles;i=(u16)(offset-0x172daaUL);
    } else if (offset >= 0x19d2UL && offset < 0x19f1UL) {
        table=shadowrun_table_input;i=(u16)(offset-0x19d2UL);
    } else if (offset >= 0xbec2UL && offset < 0xbee1UL) {
        table=shadowrun_table_move;i=(u16)(offset-0xbec2UL);
    } else if (offset >= 0xc052UL && offset < 0xc061UL) {
        table=shadowrun_table_stand;i=(u16)(offset-0xc052UL);
    } else if (offset >= 0x15e16UL && offset < 0x15f55UL) {
        table=shadowrun_table_camera;i=(u16)(offset-0x15e16UL);
    } else {rom_fault = 1;return 0;}
    return ((u16)table[i]<<8)|table[i+1];
}
static void wait_vblank(void) {
    while(PPUSTATUS & 0x80) {}
    while(!(PPUSTATUS & 0x80)) {}
}
static u8 read_pad(void) {
    u8 i,v=0;
    static const u8 bits[8]={0x40,0x10,0x20,0x80,1,2,4,8};
    PAD=1;PAD=0;
    for(i=0;i<8;i++)if(PAD&1)v|=bits[i];
    return v;
}
static i16 rounded_sixteenth(i16 value) {
    i16 whole;
    whole = value >> 4;
    if (((u16)value & 8U) != 0) whole++;
    return whole;
}
static void place_actor(void) {
    u8 i;
    u8 base_x,base_y;
    i16 origin_x,origin_y,x,y;
    const u8 *sprite=shadowrun_scene+shadowrun_scene_background_size+32;
    volatile u8 *oam=OAM;
    origin_x=rounded_sixteenth((i16)(shadowrun_player_x-shadowrun_camera_x))-12;
    origin_y=rounded_sixteenth((i16)(shadowrun_player_y-shadowrun_camera_y))-25;
    if (shadowrun_fast_sprite && origin_x>=0 && origin_x<=224 && origin_y>=0 && origin_y<=192) {
        base_x=(u8)(origin_x-130);base_y=(u8)(origin_y-50);
        for(i=0;i<shadowrun_sprite_count;i++) {
            oam[0]=base_y+sprite[0];oam[3]=base_x+sprite[3];
            sprite+=4;oam+=4;
        }
        return;
    }
    for(i=0;i<shadowrun_sprite_count;i++) {
        x=origin_x+(i16)sprite[3]-130;
        y=origin_y+(i16)sprite[0]-50;
        if (x<0 || x>255 || y<0 || y>223) oam[0]=0xf0;
        else {oam[0]=(u8)y;oam[3]=(u8)x;}
        sprite+=4;oam+=4;
    }
}
static u8 view_allowed(u16 x,u16 y) {
    if (x>255 || y>shadowrun_camera_y_max) return 0;
    return (shadowrun_camera_valid[(y<<5)+(x>>3)] & (1U<<(x&7))) != 0;
}
#ifdef SHADOWRUN_STOKER_VISUAL
static void show_mode(u8 mode,u16 view_x,u16 view_y) {
    u16 i,offset;
    wait_vblank();PPUMASK=0;
    if (mode) {
        offset=(u16)(mode-1)*1040U;
        PPUADDR=0x20;PPUADDR=0;
        for(i=0;i<1024;i++)PPUDATA=shadowrun_ui_scenes[offset+i];
        PPUADDR=0x3f;PPUADDR=0;
        for(i=0;i<16;i++)PPUDATA=shadowrun_ui_scenes[offset+1024+i];
        PPUCTRL=8;PPUSCROLL=0;PPUSCROLL=0;PPUMASK=0x0a;
    } else {
        PPUADDR=0x20;PPUADDR=0;
        for(i=0;i<shadowrun_scene_background_size;i++)PPUDATA=shadowrun_scene[i];
        PPUADDR=0x3f;PPUADDR=0;
        for(i=0;i<32;i++)PPUDATA=shadowrun_scene[shadowrun_scene_background_size+i];
        PPUCTRL=8|(view_y>=240?2:0);PPUSCROLL=(u8)view_x;
        PPUSCROLL=(u8)(view_y>=240?view_y-240:view_y);PPUMASK=0x1e;
    }
}
#endif

void main(void) {
    u16 i;
    u8 pad;
    u8 view_fault=0;
#ifdef SHADOWRUN_STOKER_VISUAL
    u8 prior_ui=0,display_ui=0,notice=0,reentry_wait=0,reentry_ticks=0;
#endif
    u16 view_x,view_y;
    PPUMASK=0;PPUCTRL=0;
    PUBLICATION[22]=0;PUBLICATION[23]=0;
    for(i=0;i<2816;i++)shadowrun_terrain_map[i]=shadowrun_initial_map[i];
    shadowrun_seed_scene();
    wait_vblank();
    PPUADDR=0x3f;PPUADDR=0;
    for(i=0;i<32;i++)PPUDATA=shadowrun_scene[shadowrun_scene_background_size+i];
    PPUADDR=0x20;PPUADDR=0;
    for(i=0;i<shadowrun_scene_background_size;i++)PPUDATA=shadowrun_scene[i];
    for(i=0;i<256;i++)OAM[i]=shadowrun_scene[shadowrun_scene_background_size+32+i];
    OAMADDR=0;OAMDMA=2;
    view_x=(shadowrun_camera_x>>4)-shadowrun_atlas_origin_x;
    view_y=(shadowrun_camera_y>>4)-shadowrun_atlas_origin_y;
    if (!view_allowed(view_x,view_y)) view_fault=1;
    PPUCTRL=8|(view_y>=240?2:0);PPUSCROLL=(u8)view_x;PPUSCROLL=(u8)(view_y>=240?view_y-240:view_y);PPUMASK=0x1e;
    for(;;) {
        wait_vblank();pad=read_pad();
        if (!view_fault) {
#ifdef SHADOWRUN_STOKER
#ifdef SHADOWRUN_STOKER_VISUAL
            shadowrun_opening_stoker_frame(reentry_wait?0:pad);
#else
            shadowrun_opening_stoker_frame(pad);
#endif
#else
            shadowrun_opening_frame(pad);
#endif
        }
        view_x=(shadowrun_camera_x>>4)-shadowrun_atlas_origin_x;
        view_y=(shadowrun_camera_y>>4)-shadowrun_atlas_origin_y;
#ifdef SHADOWRUN_STOKER_VISUAL
        if (!view_fault && prior_ui && !shadowrun_stoker_ui_mode && !notice && !reentry_wait) {
            reentry_wait=1;reentry_ticks=0;PPUMASK=0;
        }
        if (reentry_wait) {
            if (view_allowed(view_x,view_y)) reentry_wait=0;
            else {
                reentry_ticks++;
                if (reentry_ticks>=240) {reentry_wait=0;view_fault=1;}
            }
        }
        if (!shadowrun_camera_supported || (!reentry_wait && !view_allowed(view_x,view_y))) view_fault=1;
#else
        if (!shadowrun_camera_supported || !view_allowed(view_x,view_y)) view_fault=1;
#endif
        PUBLICATION[22]++;
        PUBLICATION[0]=0x53;PUBLICATION[1]=0x57;PUBLICATION[2]=view_fault?5:shadowrun_opening_status;PUBLICATION[3]=rom_fault;
        PUBLICATION[4]=(u8)shadowrun_player_x;PUBLICATION[5]=(u8)(shadowrun_player_x>>8);
        PUBLICATION[6]=(u8)shadowrun_player_y;PUBLICATION[7]=(u8)(shadowrun_player_y>>8);
        PUBLICATION[8]=(u8)shadowrun_player_heading;PUBLICATION[9]=(u8)(shadowrun_player_heading>>8);
        PUBLICATION[10]=(u8)shadowrun_pad_sample;PUBLICATION[11]=(u8)(shadowrun_pad_sample>>8);
        PUBLICATION[12]=(u8)shadowrun_direction_angle;PUBLICATION[13]=(u8)(shadowrun_direction_angle>>8);
        PUBLICATION[14]=(u8)shadowrun_camera_x;PUBLICATION[15]=(u8)(shadowrun_camera_x>>8);
        PUBLICATION[16]=(u8)shadowrun_camera_y;PUBLICATION[17]=(u8)(shadowrun_camera_y>>8);
        PUBLICATION[18]=(u8)shadowrun_camera_scroll_ax;PUBLICATION[19]=(u8)(shadowrun_camera_scroll_ax>>8);
        PUBLICATION[20]=(u8)shadowrun_camera_scroll_ay;PUBLICATION[21]=(u8)(shadowrun_camera_scroll_ay>>8);
#ifdef SHADOWRUN_STOKER_VISUAL
        PUBLICATION[24]=reentry_wait;PUBLICATION[25]=reentry_ticks;
#else
        PUBLICATION[24]=0;PUBLICATION[25]=0;
#endif
        PUBLICATION[23]++;
        PUBLICATION[22]++;
        if (!view_fault) {
#ifdef SHADOWRUN_STOKER_VISUAL
            if (shadowrun_stoker_ui_unsupported) notice=45;
            else if (notice) notice--;
            display_ui=notice?4:(shadowrun_stoker_ui_mode>3?3:shadowrun_stoker_ui_mode);
            if (!reentry_wait && prior_ui!=display_ui) {
                show_mode(display_ui,view_x,view_y);
                prior_ui=display_ui;
            }
            if (!display_ui && !reentry_wait) {
#endif
            place_actor();OAMADDR=0;OAMDMA=2;
            PPUCTRL=8|(view_y>=240?2:0);PPUSCROLL=(u8)view_x;PPUSCROLL=(u8)(view_y>=240?view_y-240:view_y);}
#ifdef SHADOWRUN_STOKER_VISUAL
        }
#endif
    }
}
