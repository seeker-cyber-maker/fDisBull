/* Private NES opening experiment. The GameIL supplies bounded movement; this
 * adapter supplies captured state, source-table reads and a diagnostic view.
 * Static camera and unsupported actions are explicit in its manifest. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef signed int i16;
typedef unsigned long u32;
extern const u8 shadowrun_scene[1312];
extern const u8 shadowrun_initial_map[2816];
extern const u8 shadowrun_table_input[32];
extern const u8 shadowrun_table_move[32];
extern const u8 shadowrun_table_stand[16];
extern const u8 shadowrun_table_rectangles[320];
extern u8 shadowrun_terrain_map[2816];
extern u16 shadowrun_pad_held,shadowrun_pad_sample,shadowrun_direction_angle;
extern u16 shadowrun_player_x,shadowrun_player_y,shadowrun_player_heading,shadowrun_player_target_heading;
extern u16 shadowrun_player_kind,shadowrun_player_contact,shadowrun_global_special_mode;
extern u8 shadowrun_player_flags,shadowrun_player_equipment_flags,shadowrun_global_vector_flags;
extern u16 shadowrun_x_min,shadowrun_x_max,shadowrun_y_min,shadowrun_y_max;
extern u32 shadowrun_rect_base;
extern u8 shadowrun_player_event_flags,shadowrun_opening_status;
extern void shadowrun_opening_tick(u8);
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
extern const u16 shadowrun_seed_x,shadowrun_seed_y;
extern const u8 shadowrun_sprite_count;
static u8 rom_fault;
u16 rom16(u8 region,u32 offset) {
    const u8 *table;
    u16 i;
    if (region != 0) {rom_fault = 1;return 0;}
    if (offset >= 0x19d2UL && offset < 0x19f1UL) {
        table=shadowrun_table_input;i=(u16)(offset-0x19d2UL);
    } else if (offset >= 0xbec2UL && offset < 0xbee1UL) {
        table=shadowrun_table_move;i=(u16)(offset-0xbec2UL);
    } else if (offset >= 0xc052UL && offset < 0xc061UL) {
        table=shadowrun_table_stand;i=(u16)(offset-0xc052UL);
    } else if (offset >= 0x172daaUL && offset < 0x172ee9UL) {
        table=shadowrun_table_rectangles;i=(u16)(offset-0x172daaUL);
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
static void place_actor(void) {
    u8 i;
    i16 dx,dy;
    dx=(i16)(shadowrun_player_x-shadowrun_seed_x)/16;
    dy=(i16)(shadowrun_player_y-shadowrun_seed_y)/16;
    for(i=0;i<shadowrun_sprite_count;i++) {
        OAM[(u16)i*4]=(u8)(shadowrun_scene[1056+(u16)i*4]+dy);
        OAM[(u16)i*4+3]=(u8)(shadowrun_scene[1059+(u16)i*4]+dx);
    }
}
void main(void) {
    u16 i;
    u8 pad;
    PPUMASK=0;PPUCTRL=0;
    for(i=0;i<2816;i++)shadowrun_terrain_map[i]=shadowrun_initial_map[i];
    shadowrun_seed_scene();
    wait_vblank();
    PPUADDR=0x3f;PPUADDR=0;
    for(i=0;i<32;i++)PPUDATA=shadowrun_scene[1024+i];
    PPUADDR=0x20;PPUADDR=0;
    for(i=0;i<1024;i++)PPUDATA=shadowrun_scene[i];
    for(i=0;i<256;i++)OAM[i]=shadowrun_scene[1056+i];
    OAMADDR=0;OAMDMA=2;
    PPUSCROLL=0;PPUSCROLL=0;PPUCTRL=8;PPUMASK=0x1e;
    for(;;) {
        wait_vblank();pad=read_pad();shadowrun_opening_tick(pad);
        PUBLICATION[0]=0x53;PUBLICATION[1]=0x57;PUBLICATION[2]=shadowrun_opening_status;PUBLICATION[3]=rom_fault;
        PUBLICATION[4]=(u8)shadowrun_player_x;PUBLICATION[5]=(u8)(shadowrun_player_x>>8);
        PUBLICATION[6]=(u8)shadowrun_player_y;PUBLICATION[7]=(u8)(shadowrun_player_y>>8);
        PUBLICATION[8]=(u8)shadowrun_player_heading;PUBLICATION[9]=(u8)(shadowrun_player_heading>>8);
        PUBLICATION[10]=(u8)shadowrun_pad_sample;PUBLICATION[11]=(u8)(shadowrun_pad_sample>>8);
        PUBLICATION[12]=(u8)shadowrun_direction_angle;PUBLICATION[13]=(u8)(shadowrun_direction_angle>>8);
        place_actor();OAMADDR=0;OAMDMA=2;
    }
}
