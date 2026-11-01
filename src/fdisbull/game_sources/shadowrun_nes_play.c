/* Symbolic target projection of the captured terrain byte grid. Categories
 * are numeric, not a passability map. Movement and collision remain GameIL. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef signed int i16;
typedef unsigned long u32;
extern const u8 shadowrun_scene[],shadowrun_initial_map[],shadowrun_table_input[],shadowrun_table_move[],shadowrun_table_stand[],shadowrun_table_rectangles[],shadowrun_table_camera[];
extern const u8 shadowrun_play_screen[],shadowrun_play_hex[],shadowrun_weapon_table[],shadowrun_linked_tables[];
extern u8 shadowrun_terrain_map[],shadowrun_play_menu,shadowrun_play_refused,shadowrun_play_debug,shadowrun_debug_result;
extern u8 shadowrun_play_shot_eligible,shadowrun_play_shot_pending,shadowrun_play_shot_used,shadowrun_play_shot_armed;
extern u16 shadowrun_play_shot_timer;
extern u8 shadowrun_field_supported,shadowrun_field_motion_state,shadowrun_field_motion_lifetime,shadowrun_field_motion_steps,shadowrun_linked_motion_state,shadowrun_linked_motion_lifetime,shadowrun_linked_motion_steps,shadowrun_actors_hit_slot;
extern u16 shadowrun_field_rng,shadowrun_field_projectile_x,shadowrun_field_projectile_y;
extern u32 shadowrun_field_motion_y_fixed,shadowrun_linked_x_fixed,shadowrun_linked_y_fixed;
extern u8 shadowrun_field_outcome;
extern u16 shadowrun_debug_x,shadowrun_debug_y;
extern u16 shadowrun_target_x[],shadowrun_target_y[],shadowrun_target_height[],shadowrun_target_contact[],shadowrun_target_marker[],shadowrun_target_index[];
extern u8 shadowrun_play_actor_hp[];
extern u8 shadowrun_field_death_timer,shadowrun_field_type13_deaths,shadowrun_field_party_counter_a,shadowrun_field_party_counter_b,shadowrun_field_party_counter_c;
extern u8 shadowrun_target_flags[],shadowrun_target_flags_low[],shadowrun_target_flags_b0[],shadowrun_target_backlink[],shadowrun_target_special_callback[];
extern u8 shadowrun_target_selected,shadowrun_target_supported,shadowrun_target_result,shadowrun_target_player_backlink;
extern u8 shadowrun_inventory_row,shadowrun_inventory_column,shadowrun_inventory_item,shadowrun_inventory_equipped_armor;
extern u8 shadowrun_play_weapon_slot,shadowrun_play_weapon_item,shadowrun_play_ammo,shadowrun_play_weapon_aux;
extern u8 shadowrun_play_phase0,shadowrun_play_phase1,shadowrun_play_phase2,shadowrun_play_phase3,shadowrun_play_phase4,shadowrun_play_phase5,shadowrun_play_phase6,shadowrun_play_phase7,shadowrun_play_action_gate;
extern u8 shadowrun_inventory_cell0,shadowrun_inventory_cell1,shadowrun_inventory_cell2,shadowrun_inventory_cell3,shadowrun_inventory_cell4,shadowrun_inventory_cell5,shadowrun_inventory_cell6,shadowrun_inventory_cell7;
extern u8 shadowrun_opening_status,shadowrun_camera_supported;
extern u16 shadowrun_x_min,shadowrun_x_max,shadowrun_y_min,shadowrun_y_max;
extern u16 shadowrun_player_x,shadowrun_player_y,shadowrun_player_heading,shadowrun_pad_sample,shadowrun_direction_angle,shadowrun_camera_x,shadowrun_camera_y,shadowrun_camera_scroll_ax,shadowrun_camera_scroll_ay;
extern void shadowrun_play_frame(u8),shadowrun_seed_scene(void);
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
static u8 rom_fault,field_initialized;
u8 rom8(u8 region,u32 offset) {
    if(region==0 && offset>=0x15a4cUL && offset<0x16396UL) return shadowrun_linked_tables[(u16)(offset-0x15a4cUL)];
    rom_fault=1;return 0;
}
u16 rom16(u8 region,u32 offset) {
    const u8 *table;u16 i;
    if(region!=0) {rom_fault=1;return 0;}
    if(offset>=0x15a4cUL && offset<0x16395UL) {table=shadowrun_linked_tables;i=(u16)(offset-0x15a4cUL);}
    else if(offset>=0xd4594UL && offset<0xd4595UL) {table=shadowrun_weapon_table;i=(u16)(offset-0xd4594UL);}
    else if(offset>=0x172daaUL && offset<0x172ee9UL) {table=shadowrun_table_rectangles;i=(u16)(offset-0x172daaUL);}
    else if(offset>=0x19d2UL && offset<0x19f1UL) {table=shadowrun_table_input;i=(u16)(offset-0x19d2UL);}
    else if(offset>=0xbec2UL && offset<0xbee1UL) {table=shadowrun_table_move;i=(u16)(offset-0xbec2UL);}
    else if(offset>=0xc052UL && offset<0xc061UL) {table=shadowrun_table_stand;i=(u16)(offset-0xc052UL);}
    else if(offset>=0x15e16UL && offset<0x15f55UL) {table=shadowrun_table_camera;i=(u16)(offset-0x15e16UL);}
    else {rom_fault=1;return 0;}
    return ((u16)table[i]<<8)|table[i+1];
}
static void wait_vblank(void) {while(PPUSTATUS&0x80){} while(!(PPUSTATUS&0x80)){} }
static u8 read_pad(void) {u8 i,v=0;static const u8 bits[8]={0x40,0x10,0x20,0x80,1,2,4,8};PAD=1;PAD=0;for(i=0;i<8;i++)if(PAD&1)v|=bits[i];return v;}
static void play_screen(u8 menu) {
    u16 i,x,y,cell,lo_x,hi_x,lo_y,hi_y;u8 nt,xx,yy,v,tile;
    wait_vblank();PPUMASK=0;PPUADDR=0x20;PPUADDR=0;
    if(menu) {
        for(i=0;i<1024;i++)PPUDATA=shadowrun_play_screen[i];
        PPUADDR=0x3f;PPUADDR=0;for(i=0;i<16;i++)PPUDATA=shadowrun_play_screen[1024+i];
        for(i=0;i<52;i+=4)OAM[i]=0xf0;
        OAMADDR=0;OAMDMA=2;PPUCTRL=8;PPUSCROLL=0;PPUSCROLL=0;PPUMASK=0x1e;
    } else {
        lo_x=shadowrun_x_min>>5;hi_x=(shadowrun_x_max-1U)>>5;
        lo_y=shadowrun_y_min>>5;hi_y=(shadowrun_y_max-1U)>>5;
        /* The menu overwrites only nametable zero; preserve the other three. */
        for(nt=0;nt<(field_initialized?1:4);nt++) {
            for(yy=0;yy<30;yy++) {
                y=(u16)(nt>>1)*30U+yy;
                for(xx=0;xx<32;xx++) {
                    x=(u16)(nt&1U)*32U+xx;tile=0;
                    if(y<44 && x>=lo_x && x<=hi_x && y>=lo_y && y<=hi_y) {
                        cell=y*64U+x;v=shadowrun_terrain_map[cell];tile=4;
                        if(v==0)tile=1;else if(v==127)tile=2;else if(v<127)tile=3;
                    }
                    PPUDATA=tile;
                }
            }
            for(i=0;i<64;i++)PPUDATA=0;
        }
        field_initialized=1;
        PPUADDR=0x3f;PPUADDR=0;for(i=0;i<32;i++)PPUDATA=shadowrun_scene[i];
    }
}
static void play_selection(void) {
    u8 i,slot,vals[8];
    vals[0]=shadowrun_inventory_cell0;vals[1]=shadowrun_inventory_cell1;vals[2]=shadowrun_inventory_cell2;vals[3]=shadowrun_inventory_cell3;
    vals[4]=shadowrun_inventory_cell4;vals[5]=shadowrun_inventory_cell5;vals[6]=shadowrun_inventory_cell6;vals[7]=shadowrun_inventory_cell7;
    slot=shadowrun_inventory_row*2+shadowrun_inventory_column;wait_vblank();PPUMASK=0;
    for(i=0;i<8;i++) {u16 addr=0x20c3U+(u16)(i>>1)*96U+(i&1U)*12U;
        PPUADDR=(u8)(addr>>8);PPUADDR=(u8)addr;PPUDATA=shadowrun_play_hex[i==slot?16:17];
        PPUDATA=shadowrun_play_hex[vals[i]>>4];PPUDATA=shadowrun_play_hex[vals[i]&15];}
    PPUADDR=0x22;PPUADDR=0x4a;
    PPUDATA=shadowrun_play_hex[shadowrun_inventory_equipped_armor>>4];PPUDATA=shadowrun_play_hex[shadowrun_inventory_equipped_armor&15];
    PPUADDR=0x22;PPUADDR=0x8f;
    PPUDATA=shadowrun_play_hex[shadowrun_play_weapon_item>>4];PPUDATA=shadowrun_play_hex[shadowrun_play_weapon_item&15];
    PPUDATA=shadowrun_play_hex[17];PPUDATA=shadowrun_play_hex[shadowrun_play_ammo>>4];PPUDATA=shadowrun_play_hex[shadowrun_play_ammo&15];
    PPUCTRL=8;PPUSCROLL=0;PPUSCROLL=0;PPUMASK=0x1e;
}
void main(void) {
    u16 i,x,y,view_x,view_y;u8 pad,prior_menu=0,prior_row=255,prior_col=255,prior_armor=255,prior_weapon=255,notice=0;
    PPUMASK=0;PPUCTRL=0;PUBLICATION[22]=0;PUBLICATION[23]=0;for(i=0;i<2816;i++)shadowrun_terrain_map[i]=shadowrun_initial_map[i];
    shadowrun_seed_scene();
    /* PLAY_SEED */
    for(i=0;i<256;i++)OAM[i]=0xf0;
    play_screen(0);
    for(;;) {
        wait_vblank();pad=read_pad();shadowrun_play_frame(pad);
        x=shadowrun_player_x>>6;y=shadowrun_player_y>>6;
        if(shadowrun_play_debug) {view_x=shadowrun_debug_x>>6;view_y=shadowrun_debug_y>>6;}
        else {view_x=x;view_y=y;}
        view_x=view_x>128?view_x-128:0;if(view_x>256)view_x=256;
        view_y=view_y>112?view_y-112:0;if(view_y>128)view_y=128;
        PUBLICATION[22]++;PUBLICATION[0]=0x53;PUBLICATION[1]=0x57;
        PUBLICATION[2]=shadowrun_opening_status;PUBLICATION[3]=rom_fault;
        PUBLICATION[4]=(u8)shadowrun_player_x;PUBLICATION[5]=(u8)(shadowrun_player_x>>8);
        PUBLICATION[6]=(u8)shadowrun_player_y;PUBLICATION[7]=(u8)(shadowrun_player_y>>8);
        PUBLICATION[8]=(u8)shadowrun_player_heading;PUBLICATION[9]=(u8)(shadowrun_player_heading>>8);
        PUBLICATION[10]=(u8)shadowrun_pad_sample;PUBLICATION[11]=(u8)(shadowrun_pad_sample>>8);
        PUBLICATION[12]=(u8)shadowrun_direction_angle;PUBLICATION[13]=(u8)(shadowrun_direction_angle>>8);
        PUBLICATION[14]=(u8)shadowrun_camera_x;PUBLICATION[15]=(u8)(shadowrun_camera_x>>8);
        PUBLICATION[16]=(u8)shadowrun_camera_y;PUBLICATION[17]=(u8)(shadowrun_camera_y>>8);
        PUBLICATION[18]=(u8)shadowrun_camera_scroll_ax;PUBLICATION[19]=(u8)(shadowrun_camera_scroll_ax>>8);
        PUBLICATION[20]=(u8)shadowrun_camera_scroll_ay;PUBLICATION[21]=(u8)(shadowrun_camera_scroll_ay>>8);
        PUBLICATION[26]=shadowrun_play_menu;PUBLICATION[27]=shadowrun_inventory_row;PUBLICATION[28]=shadowrun_inventory_column;
        PUBLICATION[29]=shadowrun_inventory_item;PUBLICATION[30]=shadowrun_play_refused;PUBLICATION[31]=shadowrun_inventory_equipped_armor;PUBLICATION[32]=shadowrun_play_weapon_slot;PUBLICATION[33]=shadowrun_play_weapon_item;PUBLICATION[34]=shadowrun_play_ammo;PUBLICATION[35]=shadowrun_play_debug;PUBLICATION[36]=shadowrun_debug_result;PUBLICATION[37]=(u8)shadowrun_debug_x;PUBLICATION[38]=(u8)(shadowrun_debug_x>>8);PUBLICATION[39]=(u8)shadowrun_debug_y;PUBLICATION[40]=(u8)(shadowrun_debug_y>>8);
        PUBLICATION[41]=shadowrun_play_shot_pending;PUBLICATION[42]=shadowrun_play_shot_used;
        PUBLICATION[43]=shadowrun_field_supported;PUBLICATION[44]=shadowrun_field_motion_state;
        PUBLICATION[45]=shadowrun_field_motion_lifetime;PUBLICATION[46]=shadowrun_field_motion_steps;
        PUBLICATION[47]=(u8)shadowrun_field_motion_y_fixed;PUBLICATION[48]=(u8)(shadowrun_field_motion_y_fixed>>8);
        PUBLICATION[49]=(u8)(shadowrun_field_motion_y_fixed>>16);PUBLICATION[50]=(u8)(shadowrun_field_motion_y_fixed>>24);
        PUBLICATION[51]=(u8)shadowrun_field_rng;PUBLICATION[52]=(u8)(shadowrun_field_rng>>8);PUBLICATION[53]=(u8)shadowrun_play_shot_timer;PUBLICATION[54]=(u8)(shadowrun_play_shot_timer>>8);PUBLICATION[55]=shadowrun_target_selected;PUBLICATION[56]=shadowrun_target_supported;PUBLICATION[57]=shadowrun_target_result;PUBLICATION[58]=(u8)shadowrun_target_contact[1];PUBLICATION[59]=(u8)(shadowrun_target_contact[1]>>8);
        PUBLICATION[60]=(u8)shadowrun_target_marker[1];PUBLICATION[61]=(u8)(shadowrun_target_marker[1]>>8);
        PUBLICATION[62]=shadowrun_target_flags_low[1];PUBLICATION[63]=shadowrun_target_backlink[1];
        for(i=0;i<7;i++)PUBLICATION[64+i]=shadowrun_play_actor_hp[i];
        PUBLICATION[71]=shadowrun_linked_motion_state;PUBLICATION[72]=shadowrun_linked_motion_lifetime;
        PUBLICATION[73]=shadowrun_linked_motion_steps;PUBLICATION[74]=shadowrun_actors_hit_slot;
        PUBLICATION[75]=(u8)shadowrun_linked_x_fixed;PUBLICATION[76]=(u8)(shadowrun_linked_x_fixed>>8);
        PUBLICATION[77]=(u8)(shadowrun_linked_x_fixed>>16);PUBLICATION[78]=(u8)(shadowrun_linked_x_fixed>>24);
        PUBLICATION[79]=(u8)shadowrun_linked_y_fixed;PUBLICATION[80]=(u8)(shadowrun_linked_y_fixed>>8);
        PUBLICATION[81]=(u8)(shadowrun_linked_y_fixed>>16);PUBLICATION[82]=(u8)(shadowrun_linked_y_fixed>>24);
        PUBLICATION[83]=shadowrun_field_outcome;
        PUBLICATION[23]++;PUBLICATION[22]++;
        if(shadowrun_play_refused)notice=45;else if(notice)notice--;
        if(notice) {OAM[40]=8;OAM[41]=1;OAM[42]=1;OAM[43]=240;} else OAM[40]=0xf0;
        if(prior_menu!=shadowrun_play_menu) {play_screen(shadowrun_play_menu);prior_menu=shadowrun_play_menu;prior_row=255;prior_col=255;prior_armor=255;prior_weapon=255;}
        if(shadowrun_play_menu) {
            if(prior_row!=shadowrun_inventory_row || prior_col!=shadowrun_inventory_column || prior_armor!=shadowrun_inventory_equipped_armor || prior_weapon!=shadowrun_play_weapon_item) {
                play_selection();prior_row=shadowrun_inventory_row;prior_col=shadowrun_inventory_column;prior_armor=shadowrun_inventory_equipped_armor;prior_weapon=shadowrun_play_weapon_item;}
            OAMADDR=0;OAMDMA=2;
        } else {
            if(x>=view_x && x<view_x+256U && y>=view_y && y<view_y+224U) {
                OAM[0]=(u8)(y-view_y-4);OAM[1]=0;OAM[2]=0;OAM[3]=(u8)(x-view_x-4);
            } else OAM[0]=0xf0;
            if(shadowrun_play_debug && (shadowrun_debug_x>>6)>=view_x && (shadowrun_debug_x>>6)<view_x+256U &&
               (shadowrun_debug_y>>6)>=view_y && (shadowrun_debug_y>>6)<view_y+224U) {
                OAM[4]=(u8)((shadowrun_debug_y>>6)-view_y-4);OAM[5]=0;OAM[6]=1;
                OAM[7]=(u8)((shadowrun_debug_x>>6)-view_x-4);
            } else OAM[4]=0xf0;
            if((shadowrun_field_motion_state==1 || shadowrun_linked_motion_state==1) && (shadowrun_field_projectile_x>>6)>=view_x &&
               (shadowrun_field_projectile_x>>6)<view_x+256U && (shadowrun_field_projectile_y>>6)>=view_y &&
               (shadowrun_field_projectile_y>>6)<view_y+224U) {
                OAM[8]=(u8)((shadowrun_field_projectile_y>>6)-view_y-4);OAM[9]=0;OAM[10]=2;
                OAM[11]=(u8)((shadowrun_field_projectile_x>>6)-view_x-4);
            } else OAM[8]=0xf0;
            for(i=0;i<7;i++) {
                u16 ax=shadowrun_target_x[i]>>6,ay=shadowrun_target_y[i]>>6,at=12U+i*4U;
                if ((shadowrun_target_flags[i]&1U) && ax>=view_x && ax<view_x+256U && ay>=view_y && ay<view_y+224U) {
                    OAM[at]=(u8)(ay-view_y-4);OAM[at+1]=0;OAM[at+2]=(i==shadowrun_target_selected)?1:2;OAM[at+3]=(u8)(ax-view_x-4);
                } else OAM[at]=0xf0;
            }
            if(shadowrun_target_selected<7U) {
                OAM[44]=8;OAM[45]=2+(shadowrun_play_actor_hp[shadowrun_target_selected]>>4);OAM[46]=0;OAM[47]=216;
                OAM[48]=8;OAM[49]=2+(shadowrun_play_actor_hp[shadowrun_target_selected]&15);OAM[50]=0;OAM[51]=224;
            } else {OAM[44]=0xf0;OAM[48]=0xf0;}
            OAMADDR=0;OAMDMA=2;
            PPUCTRL=8|(view_x>=256?1:0);PPUSCROLL=(u8)view_x;PPUSCROLL=(u8)view_y;PPUMASK=0x1e;
        }
    }
}
