/* Authored NES presentation adapter. Uses source projection/terrain data;
 * menus, font, icons, palette quantization and view buffering are adapted.
 * Game state is never modified by rendering.
 */
#include "game_api.h"
extern const u8 ending_ids[48];
extern const u8 tile_palette[35];
extern u8 upload_terrain_cached,upload_terrain_valid,upload_terrain_overlay;
const u8 *terrain_pointer(u8 phase);
u8 projection_bank(u8 phase);
void select_data(u8 bank);
u16 object_projection_pair(u8 x,u8 y,u8 raft);
u8 ending_projection(u16 offset);

volatile u8 display_plane[256];
u8 display_palettes[256];
volatile u8 display_attributes[16];
volatile u8 display_hud[24];
volatile u8 video_ready;
volatile u8 render_phase;
volatile u8 active_nt;
volatile u8 render_oam_page;
volatile u8 irq_phase;
volatile u8 frame_buttons;
volatile u8 request_kind[16];
volatile u8 request_id[16];
volatile u8 request_head;
volatile u8 request_tail;
u8 render_oam_index;
u8 oam_overflow;
u16 render_epoch;
u8 projection_cache[256];
/* BSS validity is cleared at reset; no other routine writes this cache. */
u8 projection_cache_valid;
u8 projection_cache_phase;
u8 globe_source_hi;
u8 globe_rowbase;
u8 globe_colbase;
u16 globe_atlas_pointer;
void globe_clear(void);
void globe_clear_planes(void);
void globe_clear_oam(void);
u8 globe_restore_terrain(void);
void globe_save_terrain(void);
void globe_copy_projection(void);
void globe_paint_terrain(void);
void globe_hud_attributes(void);
void prepare_upload(void);

void put_text(u8 x,u8 y,const char *text) {
    u8 at;
    at=y*16+x;
    for (;*text != 0 && x<16;text=text+1) {
        display_plane[at]=*text;
        display_palettes[at]=0;
        at=at+1;
        x=x+1;
    }
}

void hex_digit(u8 x,u8 y,u8 digit) {
    display_plane[y*16+x]=(digit & 15)+48;
}

void draw_sprite(u8 x,u8 y,u8 tile,u8 palette);

void draw_terrain(void) {
    u8 phase;
    phase=(u8)((player_y<<4)|(player_x & 15));
    select_data(projection_bank(phase));
    globe_source_hi=(u8)(0xA0+(phase & 31));
    if (!projection_cache_valid || phase!=projection_cache_phase) {
        globe_copy_projection();
        projection_cache_phase=phase;
        projection_cache_valid=1;
    }
    globe_atlas_pointer=(u16)terrain_pointer((u8)anim);
    globe_rowbase=player_y & 240;
    globe_colbase=player_x>>4;
    upload_terrain_cached=globe_restore_terrain();
    if (upload_terrain_cached) return;
    upload_terrain_valid=0;
    globe_clear_planes();
    globe_paint_terrain();
    globe_save_terrain();
}

void draw_ending_planet(void) {
    u8 i;
    u16 at;
    u8 graphic;
    i16 column;
    i16 row;
    u8 destination;
    if (ending_timer>=64) return;
    for (i=0;i<64;i=i+1) {
        at=(u16)ending_timer*64+i;
        column=(i16)(120+(i8)ending_projection(at)+4)/8-8;
        row=(i16)(144+(i8)ending_projection(4096U+at)+4)/8-12;
        graphic=ending_projection(8192U+at);
        if (column>=0 && column<15 && row>=0 && row<15 && graphic<48) {
            destination=(u8)(row*16+column);
            display_plane[destination]=ending_ids[graphic];
            display_plane[destination+1]=ending_ids[graphic+2];
            display_plane[destination+16]=ending_ids[graphic+1];
            display_plane[destination+17]=ending_ids[graphic+3];
        }
    }
}

void draw_objects(void) {
    u8 i;
    u8 slot;
    u8 p;
    u8 type;
    u8 x;
    u8 y;
    u8 relative_x;
    u8 relative_y;
    u8 raft;
    u8 first;
    u8 player_screen_y;
    u8 player_palette;
    u16 projected;
    first=(u8)render_epoch;
    if (first>=192) first=first-192;
    if (first>=96) first=first-96;
    if (first>=48) first=first-48;
    /* Deliberate NES art adapter: give the 16px player first scanline
     * priority, then retain the rotating order of all original actors.
     */
    player_screen_y=(u8)(144-player_jump/4);
    player_palette=player_die!=0 ? 3 : 0;
    draw_sprite(120,player_screen_y,32,player_palette);
    draw_sprite(128,player_screen_y,33,player_palette);
    draw_sprite(120,(u8)(player_screen_y+8),34,player_palette);
    draw_sprite(128,(u8)(player_screen_y+8),35,player_palette);
    /* Rotate actor order so NES's eight-sprites-per-scanline limit does not
     * permanently hide one actor. Terrain uses background, not sprite slots.
     */
    for (i=0;i<48;i=i+1) {
        slot=(u8)(i+first);
        if (slot>=48) slot=slot-48;
        p=slot*4;
        type=objects[p];
        if (type==0 || type>27) continue;
        x=objects[p+1];y=objects[p+2];
        if (type==6 || type==7) { x=mace_x(slot);y=mace_y(slot); }
        relative_x=(u8)(x-player_x);
        relative_y=(u8)(y-player_y);
        /* Original Add3DSprite front hemisphere cull. */
        if ((i8)relative_x<-64 || (i8)relative_x>64 || (i8)relative_y<-64 || (i8)relative_y>64) continue;
        relative_x=relative_x+128;
        relative_y=relative_y+128;
        raft=(type>=2 && type<=5);
        projected=object_projection_pair(relative_x,relative_y,raft);
        x=(u8)(124+(u8)projected);
        y=(u8)(148+(u8)(projected>>8));
        if (raft) {
            x=(u8)(x-4);y=(u8)(y-4);
            draw_sprite(x,y,36,1);
            draw_sprite((u8)(x+8),y,37,1);
            draw_sprite(x,(u8)(y+8),38,1);
            draw_sprite((u8)(x+8),(u8)(y+8),39,1);
        } else draw_sprite(x,y,type,(u8)(type & 3));
    }
}

void draw_menu(void) {
    u8 i;
    u8 value;
    if (mode==0) {
        put_text(2,1,"MINIPLANETS");
        put_text(2,3,"REMIX / NES");
        if (title_show_menu!=0) {
            put_text(3,6,"PLAY");put_text(3,8,"PASSWORD");put_text(3,10,"OPTIONS");
            put_text(1,(u8)(6+title_option*2),"-");
        } else put_text(3,8,"PRESS START");
    } else if (mode==2) {
        put_text(2,3,"STAGE CLEAR");put_text(2,6,"BONUS");
        for (i=0;i<6;i=i+1) hex_digit(5+i,8,(u8)(stage_bonus >> ((5-i)*4)));
    } else if (mode==3) {
        put_text(3,5,"GAME OVER");
    } else if (mode==4) {
        put_text(3,2,"CONTINUE");put_text(4,6,"YES");put_text(4,9,"NO");
        put_text(2,continue_option==0 ? 6 : 9,"-");
    } else if (mode==5) {
        put_text(3,2,"PASSWORD");
        for (i=0;i<4;i=i+1) hex_digit(5+i,6,(u8)(entered_password >> ((3-i)*4)));
        for (i=0;i<10;i=i+1) hex_digit(i+3,9,i);
        if (password_dial<10) put_text(password_dial+3,10,"-");
        put_text(1,12,"A ENTER B CLEAR");put_text(3,14,"START EXIT");
    } else if (mode==6) {
        put_text(3,1,"OPTIONS");put_text(3,4,"TIME");hex_digit(11,4,time_setting);
        put_text(3,6,"EXTRA LIFE");hex_digit(14,6,life_setting);
        put_text(3,8,"SOUND");hex_digit(11,8,sound_test>>4);hex_digit(12,8,sound_test);
        put_text(3,10,"EXIT");put_text(1,(u8)(4+option_selected*2),"-");
    } else if (mode==7) {
        put_text(4,1,"CREDITS");
        for (i=0;i<48;i=i+1) {
            value=credits_text[i];if (value>=97 && value<=122) value=value-32;
            if (value>=32 && value<91) display_plane[64+i]=value;
        }
        put_text(1,13,"THANKS FOR PLAYING");
    } else if (mode==8 || mode==9) {
        put_text(4,3,mode==9 ? "SELECT STAGE" : "STAGE");
        hex_digit(6,6,stage_name>>4);put_text(7,6,"-");hex_digit(8,6,stage_name);
        put_text(1,10,"PRESS START");
    }
}

void draw_game(void) {
    if (video_ready!=0) return;
    upload_terrain_cached=0;
    upload_terrain_overlay=ingame_status & 1;
    render_epoch=*(volatile u16*)0x7D2;
    render_oam_page=render_oam_page==2 ? 3 : 2;
    globe_clear_oam();
    if (mode!=1 || ending_phase==3) globe_clear_planes();
    render_oam_index=0;oam_overflow=0;
    if (mode==1) {
        if (ending_phase==3) draw_ending_planet();else draw_terrain();
        draw_objects();
        if ((ingame_status & 1)!=0) put_text(5,0,"PAUSED");
    } else draw_menu();
    globe_hud_attributes();
    prepare_upload();
    render_phase=0;
    video_ready=1;
}
