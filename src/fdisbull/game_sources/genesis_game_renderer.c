/* Authored Genesis presentation adapter for the reviewed Miniplanets game UIL.
 * It intentionally uses the same quantized globe, font and authored icons as
 * the NES adapter; this does not claim original-Genesis pixel fidelity.
 * Game state is read, never modified. All asset arrays are private build inputs.
 */
#include "game_api.h"

extern const u8 genesis_projection[65536UL];
extern const u8 genesis_terrain[40320UL];
extern const u8 genesis_object_projection[65536UL];
extern const u8 genesis_raft_projection[65536UL];
extern const u8 genesis_ending_projection[12288];
extern const u8 genesis_ending_ids[48];
extern const u8 genesis_tile_palette[35];
extern const u8 genesis_chr[8192];
extern volatile u16 genesis_render_epoch;

#define VDP_DATA16 (*(volatile u16 *)0xC00000UL)
#define VDP_DATA32 (*(volatile u32 *)0xC00000UL)
#define VDP_CONTROL16 (*(volatile u16 *)0xC00004UL)
#define VDP_CONTROL32 (*(volatile u32 *)0xC00004UL)

/* Public staging allows a native diagnostic to compare the complete adapter
 * state without reading VDP registers. Each sprite has x,y,tile,palette. */
u8 genesis_plane[256] __attribute__((aligned(4)));
u8 genesis_palettes[256] __attribute__((aligned(4)));
u8 genesis_hud[24];
u8 genesis_sprites[252] __attribute__((aligned(4)));
u8 genesis_sprite_count;
u8 genesis_sprite_overflow;

static void genesis_vram_write(u16 address) {
    VDP_CONTROL32=0x40000000UL | ((u32)(address & 0x3fffU)<<16) | ((u32)address>>14);
}

/* The backend configures a 64x32 plane A at $c000, SAT at $d000, increment 2,
 * and 320x224 display. Call once after VDP initialization while display is off.
 * NES 2bpp pixels become identical 0..3 Genesis 4bpp indices. */
void genesis_renderer_init(void) {
    u16 tile;
    u8 row;
    u8 bit;
    u8 lo;
    u8 hi;
    u16 i;
    u32 pixel_word;
    static const u16 colors[16]={
        0x0000,0x0a40,0x0620,0x0eee,
        0x0000,0x0c40,0x0c86,0x0eee,
        0x0000,0x00ae,0x06ee,0x0eee,
        0x0000,0x000c,0x066e,0x0eee
    };
    VDP_CONTROL16=0x8f02;
    genesis_vram_write(0);
    for(tile=0;tile<512;tile=tile+1) {
        for(row=0;row<8;row=row+1) {
            lo=genesis_chr[(u32)tile*16UL+row];
            hi=genesis_chr[(u32)tile*16UL+row+8];
            pixel_word=0;
            for(bit=0;bit<8;bit=bit+1) {
                pixel_word=(pixel_word<<4)|((lo>>7)&1)|(((hi>>7)&1)<<1);
                lo=lo<<1;hi=hi<<1;
            }
            VDP_DATA32=pixel_word;
        }
    }
    VDP_CONTROL32=0xc0000000UL;
    for(i=0;i<64;i=i+1) {
        if((i & 15)<4) VDP_DATA16=colors[(i>>4)*4+(i & 3)];
        else VDP_DATA16=0;
    }
}

static void genesis_text(u8 x,u8 y,const char *text) {
    u8 at=(u8)(y*16+x);
    while(*text && x<16) {
        genesis_plane[at]=(u8)*text;
        genesis_palettes[at]=0;
        text++;at++;x++;
    }
}
static void genesis_hex(u8 x,u8 y,u8 digit) {
    genesis_plane[y*16+x]=(digit & 15)+48;
}
static void genesis_sprite(u8 x,u8 y,u8 tile,u8 palette) {
    u16 at;
    if(genesis_sprite_count>=63) {genesis_sprite_overflow=1;return;}
    at=(u16)genesis_sprite_count*4;
    genesis_sprites[at]=x;genesis_sprites[at+1]=y;
    genesis_sprites[at+2]=tile;genesis_sprites[at+3]=palette & 3;
    genesis_sprite_count++;
}

static void genesis_draw_terrain(void) {
    u8 phase=(u8)((player_y<<4)|(player_x & 15));
    u16 i;
    u8 pos;
    u8 mapoff;
    u8 mapindex;
    u8 tile;
    u8 palette;
    u8 shape;
    const u8 *projection=genesis_projection+(u32)phase*256UL+256;
    const u8 *frame=genesis_terrain+(u32)((u8)anim & 31)*1260UL;
    const u8 *pattern;
    u8 map_y=player_y & 240;
    u8 map_x=player_x>>4;
    for(i=0;i<64;i=i+1) {
        projection-=4;
        pos=projection[0];mapoff=projection[1];shape=projection[2];
        mapindex=(u8)(((mapoff+map_y) & 240)|((mapoff+map_x) & 15));
        tile=world[mapindex];if(tile>=35)tile=0;
        pattern=frame+(u16)tile*36U+shape;
        palette=genesis_tile_palette[tile];
        genesis_plane[pos]=pattern[0];
        genesis_plane[(u16)pos+1]=pattern[1];
        genesis_plane[(u16)pos+16]=pattern[2];
        genesis_plane[(u16)pos+17]=pattern[3];
        genesis_palettes[pos]=palette;genesis_palettes[(u16)pos+1]=palette;
        genesis_palettes[(u16)pos+16]=palette;genesis_palettes[(u16)pos+17]=palette;
    }
}
static void genesis_ending(void) {
    u8 i;
    u16 at;
    u8 graphic;
    i16 column;
    i16 row;
    u8 destination;
    if(ending_timer>=64)return;
    for(i=0;i<64;i=i+1) {
        at=(u16)ending_timer*64U+i;
        column=(i16)(120+(i8)genesis_ending_projection[at]+4)/8-8;
        row=(i16)(144+(i8)genesis_ending_projection[4096U+at]+4)/8-12;
        graphic=genesis_ending_projection[8192U+at];
        if(column>=0 && column<15 && row>=0 && row<15 && graphic<48) {
            destination=(u8)(row*16+column);
            genesis_plane[destination]=genesis_ending_ids[graphic];
            genesis_plane[destination+1]=genesis_ending_ids[graphic+2];
            genesis_plane[destination+16]=genesis_ending_ids[graphic+1];
            genesis_plane[destination+17]=genesis_ending_ids[graphic+3];
        }
    }
}
static void genesis_objects(void) {
    u8 i,slot,p,type,x,y,rx,ry,raft,first,screen_y,palette;
    u32 offset;
    const u8 *table;
    first=(u8)genesis_render_epoch;
    if(first>=192)first-=192;if(first>=96)first-=96;if(first>=48)first-=48;
    screen_y=(u8)(144-player_jump/4);palette=player_die ? 3 : 0;
    genesis_sprite(120,screen_y,32,palette);genesis_sprite(128,screen_y,33,palette);
    genesis_sprite(120,(u8)(screen_y+8),34,palette);genesis_sprite(128,(u8)(screen_y+8),35,palette);
    for(i=0;i<48;i=i+1) {
        slot=(u8)(i+first);if(slot>=48)slot-=48;p=slot*4;
        type=objects[p];if(type==0 || type>27)continue;
        x=objects[p+1];y=objects[p+2];
        if(type==6 || type==7){x=mace_x(slot);y=mace_y(slot);}
        rx=(u8)(x-player_x);ry=(u8)(y-player_y);
        if((i8)rx < -64 || (i8)rx > 64 || (i8)ry < -64 || (i8)ry > 64)continue;
        rx+=128;ry+=128;raft=(type>=2 && type<=5);
        table=raft ? genesis_raft_projection : genesis_object_projection;
        offset=(u32)rx*256UL+ry;x=(u8)(124+table[offset]);
        offset=(u32)ry*256UL+rx;y=(u8)(148+table[offset]);
        if(raft){
            x-=4;y-=4;
            genesis_sprite(x,y,36,1);genesis_sprite((u8)(x+8),y,37,1);
            genesis_sprite(x,(u8)(y+8),38,1);genesis_sprite((u8)(x+8),(u8)(y+8),39,1);
        }else genesis_sprite(x,y,type,type & 3);
    }
}
static void genesis_menu(void) {
    u8 i,value;
    if(mode==0){
        genesis_text(2,1,"MINIPLANETS");genesis_text(2,3,"REMIX");
        if(title_show_menu){genesis_text(3,6,"PLAY");genesis_text(3,8,"PASSWORD");genesis_text(3,10,"OPTIONS");genesis_text(1,(u8)(6+title_option*2),"-");}
        else genesis_text(3,8,"PRESS START");
    }else if(mode==2){
        genesis_text(2,3,"STAGE CLEAR");genesis_text(2,6,"BONUS");
        for(i=0;i<6;i++)genesis_hex(5+i,8,(u8)(stage_bonus>>((5-i)*4)));
    }else if(mode==3)genesis_text(3,5,"GAME OVER");
    else if(mode==4){genesis_text(3,2,"CONTINUE");genesis_text(4,6,"YES");genesis_text(4,9,"NO");genesis_text(2,continue_option==0?6:9,"-");}
    else if(mode==5){
        genesis_text(3,2,"PASSWORD");for(i=0;i<4;i++)genesis_hex(5+i,6,(u8)(entered_password>>((3-i)*4)));
        for(i=0;i<10;i++)genesis_hex(i+3,9,i);if(password_dial<10)genesis_text(password_dial+3,10,"-");
        genesis_text(1,12,"A ENTER B CLEAR");genesis_text(3,14,"START EXIT");
    }else if(mode==6){
        genesis_text(3,1,"OPTIONS");genesis_text(3,4,"TIME");genesis_hex(11,4,time_setting);
        genesis_text(3,6,"EXTRA LIFE");genesis_hex(14,6,life_setting);
        genesis_text(3,8,"SOUND");genesis_hex(11,8,sound_test>>4);genesis_hex(12,8,sound_test);
        genesis_text(3,10,"EXIT");genesis_text(1,(u8)(4+option_selected*2),"-");
    }else if(mode==7){
        genesis_text(4,1,"CREDITS");for(i=0;i<48;i++){
            value=credits_text[i];if(value>=97 && value<=122)value-=32;
            if(value>=32 && value<91)genesis_plane[64+i]=value;
        }genesis_text(1,13,"THANKS FOR PLAYING");
    }else if(mode==8 || mode==9){
        genesis_text(4,3,mode==9?"SELECT STAGE":"STAGE");genesis_hex(6,6,stage_name>>4);
        genesis_text(7,6,"-");genesis_hex(8,6,stage_name);genesis_text(1,10,"PRESS START");
    }
}
static void genesis_make_hud(void) {
    u8 i;
    for(i=0;i<24;i++)genesis_hud[i]=32;
    for(i=0;i<6;i++)genesis_hud[i]=(u8)((score>>((5-i)*4)) & 15)+48;
    genesis_hud[7]=76;genesis_hud[8]=(lives>>4)+48;genesis_hud[9]=(lives & 15)+48;
    genesis_hud[11]=84;genesis_hud[12]=(time_secs>>4)+48;genesis_hud[13]=(time_secs & 15)+48;
    genesis_hud[15]=(stage_name>>4)+48;genesis_hud[16]=45;genesis_hud[17]=(stage_name & 15)+48;
    genesis_hud[19]=75;genesis_hud[20]=keys_left+48;
}

/* Stage without hardware writes for deterministic adapter verification. */
void genesis_render_stage(void) {
    u16 i;
    typedef u32 alias_u32 __attribute__((may_alias));
    alias_u32 *plane=(alias_u32*)genesis_plane;
    alias_u32 *palettes=(alias_u32*)genesis_palettes;
    alias_u32 *sprites=(alias_u32*)genesis_sprites;
    for(i=0;i<64;i++){plane[i]=0;palettes[i]=0;}
    for(i=0;i<63;i++)sprites[i]=0xffffffffUL;
    genesis_sprite_count=0;genesis_sprite_overflow=0;
    if(mode==1){
        if(ending_phase==3)genesis_ending();else genesis_draw_terrain();
        genesis_objects();if(ingame_status & 1)genesis_text(5,0,"PAUSED");
    }else genesis_menu();
    genesis_make_hud();
}

/* Caller schedules this at a VBlank boundary. No approximation is made to
 * game state; finite VDP timing and visible-output checks remain separate. */
void genesis_present(void) {
    u8 row,col,index;
    u16 at,attr;
    const u8 *tile=genesis_plane;
    const u8 *palette=genesis_palettes+17;
    for(row=0;row<16;row++){
        genesis_vram_write((u16)(0xc000U+(12U+row)*128U+12U*2U));
        for(col=0;col<16;col+=2){
            attr=(u16)(palette[col] & 3)<<13;
            VDP_DATA16=attr | *tile++;
            VDP_DATA16=attr | *tile++;
        }
        if((row & 1) && row<15)palette+=32;
    }
    genesis_vram_write((u16)(0xc000U+8U*128U+8U*2U));
    for(col=0;col<24;col++)VDP_DATA16=genesis_hud[col];
    genesis_vram_write(0xd000);
    if(genesis_sprite_count==0){VDP_DATA16=0;VDP_DATA16=0;VDP_DATA16=0;VDP_DATA16=0;}
    else for(index=0;index<genesis_sprite_count;index++){
        at=(u16)index*4;
        VDP_DATA16=(u16)genesis_sprites[at+1]+128;
        VDP_DATA16=(index+1<genesis_sprite_count)?(u16)(index+1):0;
        VDP_DATA16=((u16)(genesis_sprites[at+3]&3)<<13) | (u16)(256+genesis_sprites[at+2]);
        VDP_DATA16=(u16)genesis_sprites[at]+160;
    }
}
void draw_game(void) {genesis_render_stage();genesis_present();}
