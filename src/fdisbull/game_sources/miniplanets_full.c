/* Reviewed, altered Miniplanets game authoring source for the UIL-v2 compiler.
 * This is not the original game's C source: its 68000 rules are expressed here
 * as a bounded state machine, with target presentation supplied separately.
 * Original Miniplanets: Javier Degirolmo, 2016/2022, zlib license.
 *
 * Copyright 2016, 2022 Javier Degirolmo
 *
 * This software is provided 'as-is', without any express or implied
 * warranty.  In no event will the authors be held liable for any damages
 * arising from the use of this software.
 *
 * Permission is granted to anyone to use this software for any purpose,
 * including commercial applications, and to alter it and redistribute it
 * freely, subject to the following restrictions:
 *
 * 1. The origin of this software must not be misrepresented; you must not
 *    claim that you wrote the original software. If you use this software
 *    in a product, an acknowledgment in the product documentation would be
 *    appreciated but is not required.
 * 2. Altered source versions must be plainly marked as such, and must not be
 *    misrepresented as being the original software.
 * 3. This notice may not be removed or altered from any source distribution.
 */
typedef unsigned char u8;
typedef signed char i8;
typedef unsigned short u16;
typedef signed short i16;
typedef unsigned long u32;
typedef signed long i32;

u8 rom8(u8 region, u32 offset);
u16 rom16(u8 region, u32 offset);
u32 rom32(u8 region, u32 offset);
void emit(u8 kind, u8 id);
u8 sound_busy(void);
u16 hv16(void);

u8 input_buttons;
u8 joy_hold;
u8 joy_press;
u8 previous_joy;
u8 player_x;
u8 player_y;
u8 player_angle;
u8 player_action;
u8 player_jump;
u8 player_spring;
u8 player_win;
u8 player_die;
u8 keys_left;
u8 stage;
u8 stage_name;
u8 lives;
u8 time_secs;
u8 time_frames;
u8 time_setting;
u8 life_setting;
u8 ingame_status;
u8 end_game;
u8 shake_timer;
u8 ending_phase;
u8 ending_fade;
u8 ending_timer;
u8 muteki;
u8 timer_ok;
u8 belt_ok;
u8 invict;
u8 debug_ok;
u8 sound_test;
u8 bgm_to_play;
u8 sfx_to_play;
u8 current_bgm;
u8 current_sfx;
u8 bcd_carry;
u8 world[256];
u16 anim;
u16 subpixel;
u16 rng_seed;
u32 score;
u32 next_life;

/* Mode numbers are the target's explicit menu/presentation state machine:
 * 0 title, 1 level, 2 stage-clear, 3 game-over, 4 continue, 5 password,
 * 6 options, 7 credits, 8 stage-intro, 9 debug-menu (HAS_EDITOR=0).
 * Original logic timers are retained.
 */
u8 mode;
u8 title_option;
u8 title_show_menu;
u8 title_cheat[8];
u16 title_timer;
u8 option_selected;
u8 continue_option;
u8 password_dial;
u8 password_delay;
u8 password_quit;
u8 password_dial_anim[10];
u16 password_timer;
u32 entered_password;
u8 clear_phase;
u8 clear_timer;
i16 clear_qisha_pos;
u32 stage_bonus;
u8 clear_then_credits;
u16 mode_timer;
u8 credits_phase;
u8 credits_delay;
u8 credits_line;
u8 credits_column;
u8 credits_text[48];
u16 credits_reset_timer;
u32 credits_source;
u16 credits_spin;
i16 credits_scroll;
u8 debug_option;
u8 attract_mode;
u8 attract_seq;
u8 attract_timer;
u8 attract_input;
u32 attract_ptr;

/* Actor implementation in the separately reviewed authoring unit. */
void init_objects(void);
u8 add_object(u8 type, u8 x, u8 y, u8 data);
void run_objects(void);

void play_sfx(u8 id) {
    if (id >= current_sfx) {
        current_sfx = id;
        sfx_to_play = id;
    }
}

void play_bgm(u8 id) {
    if (id != current_bgm) {
        bgm_to_play = id;
        current_bgm = id;
    }
}

void stop_bgm(void) {
    bgm_to_play = 255;
    current_bgm = 0;
}

void update_sound(void) {
    u8 id;
    if (bgm_to_play != 0) {
        id = bgm_to_play;
        bgm_to_play = 0;
        if (id == 255) {
            emit(3, 0);
        } else {
            emit(1, id);
        }
        return;
    }
    if (sfx_to_play != 0) {
        id = sfx_to_play;
        sfx_to_play = 0;
        current_sfx = id;
        emit(2, id);
        return;
    }
    if (sound_busy() == 0) {
        current_sfx = 0;
    }
}

u16 rand16(void) {
    u16 n;
    u16 sample;
    n = (u16)((rng_seed << 3) | (rng_seed >> 13));
    n = (u16)(n ^ 255);
    n = (u16)((n >> 4) | (n << 12));
    sample = hv16();
    n = (u16)(n + sample);
    n = (u16)((n << 2) | (n >> 14));
    n = (u16)(n ^ 255);
    sample = hv16();
    n = (u16)(n - sample);
    rng_seed = n;
    return n;
}

u8 get_tile(u8 x, u8 y) {
    u8 index;
    index = (u8)((y & 240) | (x >> 4));
    return world[index];
}

u8 get_collision(u8 x, u8 y) {
    u8 tile;
    tile = get_tile(x, y);
    return rom8(0, 0xA514UL + tile);
}

void set_tile(u8 x, u8 y, u8 tile) {
    u8 index;
    index = (u8)((y & 240) | (x >> 4));
    world[index] = tile;
}

u8 collides_player(u8 x, u8 y, u8 radius_x, u8 radius_y) {
    i8 dx;
    i8 dy;
    if (player_jump != 0 && player_jump != 48) {
        return 0;
    }
    if (player_die != 0) {
        return 0;
    }
    dx = (i8)(u8)(x - player_x);
    dy = (i8)(u8)(y - player_y);
    if (dx > (i8)radius_x || dx < -(i8)radius_x) {
        return 0;
    }
    if (dy > (i8)radius_y || dy < -(i8)radius_y) {
        return 0;
    }
    return 1;
}

void hurt_player(u8 action) {
    if (muteki != 0 || player_win != 0 || player_die != 0 || shake_timer != 0) {
        return;
    }
    player_die = 1;
    player_action = action;
    player_angle = 255;
    play_sfx((u8)(11 + action - 5));
}

void win_stage(void) {
    if (player_win == 0) {
        player_win = 1;
        ingame_status = (u8)(ingame_status | 2);
        play_sfx(18);
    }
}

u8 bcd_add8(u8 left, u8 right) {
    u8 low;
    u8 high;
    low = (u8)((left & 15) + (right & 15));
    high = (u8)((left >> 4) + (right >> 4));
    if (low >= 10) {
        low = (u8)(low - 10);
        high = (u8)(high + 1);
    }
    bcd_carry = 0;
    if (high >= 10) {
        bcd_carry = 1;
        high = (u8)(high - 10);
    }
    return (u8)((high << 4) | low);
}

u8 bcd_sub8(u8 left, u8 right) {
    i16 low;
    i16 high;
    low = (i16)(left & 15) - (i16)(right & 15);
    high = (i16)(left >> 4) - (i16)(right >> 4);
    if (low < 0) {
        low = (i16)(low + 10);
        high = (i16)(high - 1);
    }
    bcd_carry = 0;
    if (high < 0) {
        bcd_carry = 1;
        high = (i16)(high + 10);
    }
    return (u8)((high << 4) | low);
}

u32 bcd_add32(u32 left, u32 right) {
    u8 i;
    u8 digit;
    u8 carry;
    u32 result;
    carry = 0;
    result = 0;
    for (i = 0; i < 8; i = i + 1) {
        digit = (u8)((left & 15UL) + (right & 15UL) + carry);
        carry = 0;
        if (digit >= 10) {
            digit = (u8)(digit - 10);
            carry = 1;
        }
        result = (result >> 4) | ((u32)digit << 28);
        left = left >> 4;
        right = right >> 4;
    }
    bcd_carry = carry;
    return result;
}

u32 bcd_sub32(u32 left, u32 right) {
    u8 i;
    i16 digit;
    u8 borrow;
    u32 result;
    borrow = 0;
    result = 0;
    for (i = 0; i < 8; i = i + 1) {
        digit = (i16)(left & 15UL) - (i16)(right & 15UL) - borrow;
        borrow = 0;
        if (digit < 0) {
            digit = (i16)(digit + 10);
            borrow = 1;
        }
        result = (result >> 4) | ((u32)digit << 28);
        left = left >> 4;
        right = right >> 4;
    }
    bcd_carry = borrow;
    return result;
}

void add_score(u32 points) {
    u32 total;
    u32 increment;
    u8 life;
    total = bcd_add32(score, points);
    if (total >= 0x01000000UL) {
        score = 0x00999999UL;
    } else {
        score = total;
    }
    if (score >= next_life) {
        increment = rom32(0, 0x41320UL + (u32)life_setting * 4UL);
        next_life = bcd_add32(next_life, increment);
        life = bcd_add8(lives, 1);
        if (bcd_carry != 0) {
            life = 0x99;
        }
        lives = life;
        play_sfx(17);
    }
}

void run_tally(void) {
    u16 bonus;
    u8 next;
    if (time_secs == 0) {
        ingame_status = (u8)(ingame_status & 253);
        return;
    }
    bonus = rom16(0, 0x41334UL + (u32)time_setting * 2UL);
    next = (u8)(time_frames - 64);
    if (time_frames < 64) {
        add_score((u32)bonus);
        time_secs = bcd_sub8(time_secs, 1);
    }
    time_frames = next;
}

void update_subpixel(void) {
    u8 i;
    u8 value;
    u8 reversed;
    value = (u8)anim;
    reversed = 0;
    for (i = 0; i < 8; i = i + 1) {
        reversed = (u8)((reversed << 1) | (value & 1));
        value = (u8)(value >> 1);
    }
    subpixel = reversed;
}

void init_player(void) {
    player_x = 0;
    player_y = 0;
    player_angle = 2;
    player_action = 0;
    player_jump = 16;
    player_spring = 0;
    player_win = 0;
    player_die = 0;
}

void run_player(void) {
    u8 direction;
    u8 tile;
    u8 collision;
    u8 candidate;
    u8 action;
    u8 fake;
    i8 center_x;
    i8 center_y;
    i16 dx;
    i16 dy;
    i16 distance;
    if (ending_phase >= 2) {
        player_action = 12;
        if (ending_phase == 2) {
            player_action = 11;
        }
        player_angle = 255;
        return;
    }
    if (player_win != 0) {
        if (player_win == 28 && (ingame_status & 2) != 0) {
            run_tally();
            return;
        }
        player_win = (u8)(player_win + 1);
        player_angle = 255;
        player_action = 4;
        if (player_win == 64) {
            end_game = 1;
        }
        return;
    }
    if (player_die != 0) {
        player_die = (u8)(player_die + 1);
        if (player_die == 96) {
            end_game = 2;
        }
        return;
    }
    if (shake_timer != 0) {
        player_action = 3;
        return;
    }
    if (ending_phase == 1) {
        center_x = (i8)(u8)(((player_x + 32) & 63) - 32);
        center_y = (i8)(u8)(((player_y + 32) & 63) - 32);
        fake = 0;
        if (center_x < 0) { fake = (u8)(fake | 8); }
        if (center_x > 0) { fake = (u8)(fake | 4); }
        if (center_y < 0) { fake = (u8)(fake | 2); }
        if (center_y > 0) { fake = (u8)(fake | 1); }
        joy_hold = (u8)((joy_hold & 240) | fake);
        if (center_x == 0 && center_y == 0) {
            ending_phase = (u8)(ending_phase + 1);
            ending_timer = 64;
        }
    }
    player_action = 0;
    direction = rom8(0, 0x468AUL + (joy_hold & 15));
    if (direction < 128) {
        player_action = 1;
        player_angle = direction;
        distance = (i16)rom16(0, 0x65B88UL + (u32)direction * 2UL);
        dx = (i16)(distance + (i16)subpixel);
        dx = (i16)(dx >> 8);
        distance = (i16)rom16(0, 0x65B8CUL + (u32)direction * 2UL);
        dy = (i16)(distance + (i16)subpixel);
        dy = (i16)(dy >> 8);
        candidate = (u8)(player_x + dx);
        collision = get_collision(candidate, player_y);
        if (collision != 1) { player_x = candidate; }
        candidate = (u8)(player_y + dy);
        collision = get_collision(player_x, candidate);
        if (collision != 1) { player_y = candidate; }
    }
    if (player_jump != 0) {
        if (player_jump == 24 && player_spring != 0) {
            player_spring = (u8)(player_spring - 1);
            player_action = 2;
            return;
        }
        player_jump = (u8)(player_jump - 1);
        if (player_jump != 0) {
            player_action = 2;
            return;
        }
    }
    tile = get_tile(player_x, player_y);
    collision = rom8(0, 0xA514UL + tile);
    if (collision == 2) {
        action = 5;
        if (tile == 3) { action = 6; }
        if (tile == 15) { action = 8; }
        if (tile == 18) { action = 7; }
        hurt_player(action);
        return;
    }
    if (tile == 4 && keys_left == 0) {
        win_stage();
        return;
    }
    if (tile == 9) {
        player_jump = 48;
        player_spring = 40;
        play_sfx(5);
        add_object(27, (u8)((player_x & 240) + 8), (u8)((player_y & 240) + 8), 8);
        return;
    }
    if (belt_ok != 0) {
        if (tile == 11) { player_y = (u8)(player_y - 1); }
        if (tile == 12) { player_y = (u8)(player_y + 1); }
        if (tile == 13) { player_x = (u8)(player_x - 1); }
        if (tile == 14) { player_x = (u8)(player_x + 1); }
    }
    if ((joy_press & 112) != 0) {
        player_jump = 48;
        play_sfx(3);
    }
}

void run_ending(void) {
    if (ending_phase == 0) { return; }
    if (ending_fade != 60) { ending_fade = (u8)(ending_fade + 1); }
    if (ending_phase == 2) {
        ending_timer = (u8)(ending_timer - 1);
        if (ending_timer == 0) {
            ending_phase = (u8)(ending_phase + 1);
            ending_timer = 0;
        }
        return;
    }
    if (ending_phase == 3) {
        ending_timer = (u8)(ending_timer + 1);
        if (ending_timer == 32) { play_sfx(10); }
        if (ending_timer == 180) { end_game = 1; }
    }
}

void update_level_timer(void) {
    u8 next;
    if (player_win != 0 || player_die != 0 || end_game != 0 || ending_phase != 0 || timer_ok == 0) {
        return;
    }
    time_frames = (u8)(time_frames - 1);
    if (time_frames != 0) { return; }
    time_frames = 60;
    next = bcd_sub8(time_secs, 1);
    if (bcd_carry != 0) {
        hurt_player(5);
    } else {
        time_secs = next;
    }
}

/* The native presentation replaces decompression, fades and the publisher logo.
 * These procedures preserve the source game/menu decisions and logical timers.
 * A physical NTSC frame supplies one game_frame; PAL catch-up is not used.
 */
void init_level(void) {
    u32 base;
    u32 p;
    u16 i;
    u8 object_type;
    u8 x;
    u8 y;
    u8 data;
    u8 ended;
    anim = 0;
    ingame_status = 0;
    end_game = 0;
    shake_timer = 0;
    time_secs = rom8(0, 0x4131AUL + time_setting);
    time_frames = 60;
    ending_phase = 0;
    ending_fade = 0;
    keys_left = 0;
    init_objects();
    base = rom32(0, 0x655CAUL + (u32)stage * 8);
    for (i = 0; i < 256; i = i + 1) {
        world[i] = rom8(0, base + i);
    }
    p = base + 256;
    ended = 0;
    for (i = 0; i < 48; i = i + 1) {
        if (ended == 0) {
            object_type = rom8(0, p);
            if (object_type == 255) {
                ended = 1;
            } else {
                x = rom8(0, p + 1);
                y = rom8(0, p + 2);
                data = rom8(0, p + 3);
                add_object(object_type, x, y, data);
                p = p + 4;
            }
        }
    }
    init_player();
    mode = 1;
}

void begin_stage(u8 show_intro) {
    u8 music;
    stage_name = rom8(0, 0x655CEUL + (u32)stage * 8);
    music = rom8(0, 0x655CFUL + (u32)stage * 8);
    play_bgm(music);
    if (show_intro != 0 && (stage_name & 15) <= 1) {
        mode = 8;
        anim = 0;
    } else {
        init_level();
    }
}

void start_game(void) {
    lives = 5;
    score = 0;
    next_life = rom32(0, 0x41320UL + (u32)life_setting * 4);
    begin_stage(1);
}

void start_game_from_debug(void) {
    score = 0;
    next_life = rom32(0, 0x41320UL + (u32)life_setting * 4);
    begin_stage(1);
}

void enter_title(void) {
    u8 i;
    mode = 0;
    attract_mode = 0;
    invict = 0;
    anim = 0;
    title_option = 0;
    title_show_menu = 0;
    title_timer = 720;
    for (i = 0; i < 8; i = i + 1) {
        title_cheat[i] = 0;
    }
    play_bgm(9);
}

void enter_password(void) {
    u8 i;
    mode = 5;
    entered_password = 0xFFFFFFFFUL;
    password_dial = 0;
    password_delay = 0;
    password_quit = 0;
    password_timer = 0;
    for (i = 0; i < 10; i = i + 1) {
        password_dial_anim[i] = 0;
    }
}

void enter_options(void) {
    mode = 6;
    option_selected = 0;
    stop_bgm();
}

void enter_debug(void) {
    mode = 9;
    debug_option = 0;
    lives = 5;
    stop_bgm();
}

void enter_continue(void) {
    mode = 4;
    continue_option = 0;
    play_bgm(13);
}

void enter_game_over(void) {
    mode = 3;
    anim = 0;
    play_bgm(12);
}

void enter_credits(void) {
    if (invict != 0 && stage == 45) {
        stage = 46;
        begin_stage(1);
        return;
    }
    mode = 7;
    credits_text[0] = 0;
    credits_text[24] = 0;
    credits_line = 0;
    credits_column = 0;
    credits_delay = 150;
    credits_source = 0x4912CUL;
    credits_scroll = -192;
    credits_phase = 0;
}

void enter_clear(u8 then_credits) {
    mode = 2;
    stage_bonus = rom32(0, 0x4133EUL + (u32)((stage_name >> 4) - 1) * 4);
    clear_qisha_pos = -384;
    clear_phase = 0;
    clear_timer = 0;
    clear_then_credits = then_credits;
    play_bgm(11);
}

void finish_clear(void) {
    if (clear_then_credits != 0) {
        enter_credits();
    } else {
        stage = (u8)(stage + 1);
        begin_stage(1);
    }
}

void level_over(void) {
    if (attract_mode != 0) {
        enter_title();
        return;
    }
    if (end_game == 2) {
        lives = bcd_sub8(lives, 1);
        if (lives == 0) {
            enter_game_over();
        } else {
            invict = 0;
            begin_stage(0);
        }
        return;
    }
    if (end_game != 1) {
        begin_stage(1);
        return;
    }
    if (stage == 45 || stage == 54) {
        enter_clear(1);
    } else {
        if ((stage_name & 15) == 9) {
            enter_clear(0);
        } else {
            stage = (u8)(stage + 1);
            begin_stage(1);
        }
    }
}

void start_attract(void) {
    attract_ptr = rom32(0, 0x65782UL + (u32)attract_seq * 4);
    attract_seq = (u8)(attract_seq + 1);
    if (attract_seq == 6) {
        attract_seq = 0;
    }
    stage = rom8(0, attract_ptr);
    attract_ptr = attract_ptr + 1;
    attract_mode = 255;
    attract_timer = 1;
    start_game();
}

void update_attract(void) {
    u8 pressed;
    if (attract_mode == 0) {
        return;
    }
    pressed = 0;
    attract_timer = (u8)(attract_timer - 1);
    if (attract_timer == 0) {
        attract_timer = rom8(0, attract_ptr);
        pressed = rom8(0, attract_ptr + 1);
        attract_ptr = attract_ptr + 2;
        attract_input = pressed & 15;
    }
    joy_press = (joy_press & 128) | pressed;
    joy_hold = joy_press | attract_input;
}

/* One original active/pause in-game update, followed by its render-side shake.
 * The frame after ENDGAME is set performs the source screen transition. */
void run_level(void) {
    if (end_game != 0) {
        level_over();
        return;
    }
    if ((joy_press & 128) != 0 && attract_mode == 0) {
        ingame_status = ingame_status ^ 1;
        if ((ingame_status & 1) == 0 && (joy_hold & 112) == 112) {
            enter_title();
            return;
        }
        play_sfx(19);
    }
    if (debug_ok != 0 && (ingame_status & 1) != 0 && (joy_press & 64) != 0) {
        if (stage == 45) {
            keys_left = 0;
            add_object(24, player_x, player_y, 0);
            player_jump = 0;
        } else {
            end_game = 1;
        }
        ingame_status = ingame_status & 254;
    }
    if ((ingame_status & 1) == 0) {
        update_attract();
        if (attract_mode != 0 && (joy_press & 128) != 0) {
            enter_title();
            return;
        }
        update_subpixel();
        run_player();
        run_objects();
        run_ending();
        anim = (u16)(anim + 1);
        update_level_timer();
    }
    if (shake_timer != 0) {
        shake_timer = (u8)(shake_timer - 1);
    }
}

void update_clear_all(void) {
    u8 t;
    if (clear_phase == 0) {
        if (clear_qisha_pos < 0) {
            clear_qisha_pos = (i16)(clear_qisha_pos + 4);
            if (clear_qisha_pos == 0) {
                clear_phase = 1;
                clear_timer = 0;
            }
        }
    } else {
        if (clear_phase == 1) {
            t = (u8)(clear_timer + 1);
            if (t == 120 && stage_bonus != 0) {
                add_score(0x500UL);
                stage_bonus = bcd_sub32(stage_bonus, 0x500UL);
                t = (u8)(t - 3);
            }
            if (t == 240) {
                clear_phase = 2;
                clear_timer = 0;
            }
            /* Original overwrites the preceding CLR with d0=240. */
            clear_timer = t;
        } else {
            if (clear_phase == 2) {
                clear_timer = (u8)(clear_timer + 1);
                if (clear_timer == 128) {
                    clear_phase = 3;
                    clear_timer = 0;
                }
            } else {
                if (clear_phase == 3) {
                    if (clear_timer != 32) {
                        clear_timer = (u8)(clear_timer + 1);
                    } else {
                        clear_qisha_pos = (i16)(clear_qisha_pos + 4);
                        if (clear_qisha_pos >= 384) {
                            clear_phase = 4;
                            clear_timer = 0;
                        }
                    }
                }
            }
        }
    }
}

void run_clear(void) {
    update_clear_all();
    anim = (u16)(anim + 1);
    if (clear_phase == 4) {
        finish_clear();
    }
}

void run_game_over(void) {
    if ((joy_press & 128) != 0 || anim >= 300) {
        if ((stage_name & 240) == 16) {
            enter_title();
        } else {
            enter_continue();
        }
    } else {
        anim = (u16)(anim + 1);
    }
}

void run_continue(void) {
    u8 world_number;
    if ((joy_press & 128) != 0) {
        if (continue_option == 0) {
            world_number = (u8)((stage_name >> 4) - 1);
            stage = rom8(0, 0x48FDFUL + (u32)world_number * 4);
            start_game();
        } else {
            enter_title();
        }
        return;
    }
    if ((joy_press & 12) != 0) {
        continue_option = continue_option ^ 1;
    }
}

void run_title(void) {
    u8 i;
    u8 cheat;
    if (title_timer == 0) {
        start_attract();
        return;
    }
    if (title_show_menu != 0 && (joy_press & 128) != 0) {
        if (debug_ok != 0 && (joy_hold & 64) != 0) {
            enter_credits();
            return;
        }
        if (title_option == 0) {
            stage = 0;
            if (debug_ok != 0) {
                enter_debug();
            } else {
                invict = 255;
                start_game();
            }
        } else {
            if (title_option == 1) {
                enter_password();
            } else {
                enter_options();
            }
        }
        return;
    }
    /* The last of 11 source logo letters starts with size84. */
    if (anim >= 83) {
        title_show_menu = 255;
    }
    if (joy_press != 0) {
        title_timer = 720;
        for (i = 0; i < 7; i = i + 1) {
            title_cheat[i] = title_cheat[i + 1];
        }
        title_cheat[7] = joy_press;
        cheat = 0;
        if (title_cheat[0] == 1 && title_cheat[1] == 1 && title_cheat[2] == 2 && title_cheat[3] == 2 && title_cheat[4] == 4 && title_cheat[5] == 8 && title_cheat[6] == 4 && title_cheat[7] == 8) {
            cheat = 1;
        }
        if (cheat != 0) {
            debug_ok = 255;
            play_sfx(17);
            for (i = 0; i < 8; i = i + 1) {
                title_cheat[i] = 0;
            }
        }
    }
    if (title_show_menu == 0) {
        if ((joy_press & 128) != 0) {
            title_show_menu = 255;
        }
    } else {
        if ((joy_press & 2) != 0) {
            title_option = (u8)(title_option + 1);
            if (title_option == 3) {
                title_option = 0;
            }
        }
        if ((joy_press & 1) != 0) {
            if (title_option == 0) {
                title_option = 3;
            }
            title_option = (u8)(title_option - 1);
        }
        title_timer = (u16)(title_timer - 1);
    }
    anim = (u16)(anim + 1);
}

void update_password_dial(void) {
    u8 i;
    u8 v;
    u8 found;
    u16 packed;
    u16 candidate;
    if (password_delay != 0) {
        password_delay = (u8)(password_delay - 1);
    } else {
        if ((joy_hold & 8) != 0) {
            password_delay = 6;
            password_dial = (u8)(password_dial + 1);
            if (password_dial == 10) {
                password_dial = 0;
            }
        }
        if ((joy_hold & 4) != 0) {
            password_delay = 6;
            if (password_dial == 0) {
                password_dial = 10;
            }
            password_dial = (u8)(password_dial - 1);
        }
    }
    if ((joy_press & 128) != 0) {
        /* Pack the original four byte-wide digits, including FF blanks. */
        packed = (u16)(((entered_password >> 24) & 15) << 12);
        packed = packed | (u16)(((entered_password >> 16) & 15) << 8);
        packed = packed | (u16)(((entered_password >> 8) & 15) << 4);
        packed = packed | (u16)(entered_password & 15);
        found = 0;
        for (i = 0; i < 8; i = i + 1) {
            candidate = rom16(0, 0x48FDCUL + (u32)i * 4);
            if (found == 0 && candidate == packed) {
                muteki = rom8(0, 0x48FDEUL + (u32)i * 4);
                stage = rom8(0, 0x48FDFUL + (u32)i * 4);
                password_quit = 1;
                found = 1;
            }
        }
        if (found == 0) {
            play_sfx(11);
            password_timer = 95;
        }
    } else {
        if ((joy_press & 16) != 0) {
            if ((u8)entered_password == 255) {
                password_quit = 255;
            } else {
                entered_password = (entered_password >> 8) | 0xFF000000UL;
                play_sfx(2);
            }
        }
        if (password_quit == 0) {
            if ((joy_press & 96) != 0 && entered_password >= 0xFF000000UL) {
                entered_password = (entered_password << 8) | password_dial;
                play_sfx(1);
            }
            for (i = 0; i < 10; i = i + 1) {
                v = password_dial_anim[i];
                if (i == password_dial) {
                    v = (u8)(v + 32);
                }
                password_dial_anim[i] = v >> 1;
            }
        }
    }
}

void run_password(void) {
    update_password_dial();
    if (password_timer != 0) {
        password_timer = (u16)(password_timer - 1);
    }
    anim = (u16)(anim + 1);
    if (password_quit == 1) {
        start_game();
    } else {
        if (password_quit == 255) {
            enter_title();
        }
    }
}

void play_sound_test(void) {
    if (sound_test == 0) {
        stop_bgm();
    } else {
        if (sound_test < 14) {
            current_bgm = 0;
            play_bgm(sound_test);
        } else {
            current_sfx = 0;
            play_sfx((u8)(sound_test - 13));
        }
    }
}

void run_options(void) {
    u8 quit;
    anim = (u16)(anim + 1);
    quit = 0;
    if ((joy_press & 2) != 0) {
        option_selected = (u8)(option_selected + 1);
        if (option_selected == 4) {
            option_selected = 0;
        }
    }
    if ((joy_press & 1) != 0) {
        if (option_selected == 0) {
            option_selected = 4;
        }
        option_selected = (u8)(option_selected - 1);
    }
    if ((joy_press & 128) != 0) {
        quit = 1;
    }
    if ((joy_press & 8) != 0) {
        if (option_selected == 0) {
            time_setting = (u8)(time_setting + 1);
            if (time_setting == 5) { time_setting = 0; }
        }
        if (option_selected == 1) {
            life_setting = (u8)(life_setting + 1);
            if (life_setting == 5) { life_setting = 0; }
        }
        if (option_selected == 2) {
            sound_test = (u8)(sound_test + 1);
            if (sound_test == 33) { sound_test = 0; }
        }
    }
    if ((joy_press & 4) != 0) {
        if (option_selected == 0) {
            if (time_setting == 0) { time_setting = 5; }
            time_setting = (u8)(time_setting - 1);
        }
        if (option_selected == 1) {
            if (life_setting == 0) { life_setting = 5; }
            life_setting = (u8)(life_setting - 1);
        }
        if (option_selected == 2) {
            if (sound_test == 0) { sound_test = 33; }
            sound_test = (u8)(sound_test - 1);
        }
    }
    if ((joy_press & 112) != 0) {
        if (option_selected == 2) { play_sound_test(); }
        if (option_selected == 3) { quit = 1; }
    }
    if (quit != 0) {
        enter_title();
    }
}

void run_debug(void) {
    if ((joy_press & 2) != 0) {
        debug_option = (u8)(debug_option + 1);
        if (debug_option == 5) { debug_option = 0; }
    }
    if ((joy_press & 1) != 0) {
        if (debug_option == 0) { debug_option = 5; }
        debug_option = (u8)(debug_option - 1);
    }
    if ((joy_press & 8) != 0) {
        if (debug_option == 0) {
            if (stage >= 54) { stage = 255; }
            stage = (u8)(stage + 1);
        }
        if (debug_option == 1) { lives = bcd_add8(lives, 1); }
        if (debug_option == 2) { muteki = muteki ^ 255; }
        if (debug_option == 3) { timer_ok = timer_ok ^ 255; }
        if (debug_option == 4) { belt_ok = belt_ok ^ 255; }
    }
    if ((joy_press & 4) != 0) {
        if (debug_option == 0) {
            if (stage == 0) { stage = 55; }
            stage = (u8)(stage - 1);
        }
        if (debug_option == 1) { lives = bcd_sub8(lives, 1); }
        if (debug_option == 2) { muteki = muteki ^ 255; }
        if (debug_option == 3) { timer_ok = timer_ok ^ 255; }
        if (debug_option == 4) { belt_ok = belt_ok ^ 255; }
    }
    if ((joy_press & 128) != 0) {
        start_game_from_debug();
    }
}

void update_credits_text(void) {
    u8 c;
    u8 i;
    u8 done;
    credits_delay = (u8)(credits_delay - 1);
    if (credits_delay != 0) { return; }
    done = 0;
    /* Valid StaffRoll has at most two consecutive non-printing controls. */
    for (i = 0; i < 4; i = i + 1) {
        if (done == 0) {
            c = rom8(0, credits_source);
            if (c == 255) {
                done = 1;
            } else {
                credits_source = credits_source + 1;
                if (c == 12) {
                    /* Original clears the two terminators, leaving tails and
                     * the destination pointer untouched. */
                    credits_text[0] = 0;
                    credits_text[24] = 0;
                } else {
                    if (c == 13) {
                        credits_column = 0;
                        if (credits_line != 0) { credits_column = 24; }
                        credits_delay = 150;
                        done = 1;
                    } else {
                        if (c == 10) {
                            credits_line = credits_line ^ 255;
                            credits_column = 0;
                            if (credits_line == 0) {
                                credits_delay = 150;
                                done = 1;
                            } else {
                                credits_column = 24;
                            }
                        } else {
                            credits_text[credits_column] = c;
                            credits_column = (u8)(credits_column + 1);
                            credits_text[credits_column] = 0;
                            credits_delay = 6;
                            done = 1;
                        }
                    }
                }
            }
        }
    }
}

void run_credits(void) {
    u8 c;
    if (credits_phase == 0) {
        credits_spin = (u16)(credits_spin + 1);
        credits_scroll = (i16)(credits_scroll + 1);
        if (credits_scroll == -64) { play_sfx(11); }
        if (credits_scroll == 0) {
            credits_phase = 1;
            anim = 0;
        }
    } else {
        if (credits_phase == 1) {
            anim = (u16)(anim + 1);
            credits_spin = (u16)(credits_spin + 1);
            if (anim == 64) {
                credits_phase = 2;
                play_bgm(10);
                credits_reset_timer = 600;
                anim = 0;
            }
        } else {
            update_credits_text();
            anim = (u16)(anim + 1);
            credits_spin = (u16)(credits_spin + 1);
            c = rom8(0, credits_source);
            if (c == 255) {
                credits_reset_timer = (u16)(credits_reset_timer - 1);
                if (credits_reset_timer == 0) { enter_title(); }
            }
        }
    }
}

/* Input adapter: NES R,L,U,D,A,B,Start,Select to Genesis U,D,L,R,B,C,A,Start.
 * Select supplies the third Genesis button C; all three jump in gameplay.
 * Using the prior source Joy1Hold also preserves fake-input edge behavior.
 */
void read_buttons(void) {
    u8 raw;
    raw = 0;
    if ((input_buttons & 1) != 0) { raw = raw | 8; }
    if ((input_buttons & 2) != 0) { raw = raw | 4; }
    if ((input_buttons & 4) != 0) { raw = raw | 1; }
    if ((input_buttons & 8) != 0) { raw = raw | 2; }
    if ((input_buttons & 16) != 0) { raw = raw | 64; }
    if ((input_buttons & 32) != 0) { raw = raw | 16; }
    if ((input_buttons & 64) != 0) { raw = raw | 128; }
    if ((input_buttons & 128) != 0) { raw = raw | 32; }
    previous_joy = joy_hold;
    joy_press = raw & (u8)(joy_hold ^ 255);
    joy_hold = raw;
}

/* Boot RandSeed is an explicit environment input. The original InitRand mixes
 * pre-existing RAM noise and 64 sampled HV reads; the NES runtime provides its
 * declared boot-seed adapter rather than claiming to recover hardware noise.
 */
void game_boot(void) {
    muteki = 0;
    timer_ok = 255;
    belt_ok = 255;
    debug_ok = 0;
    time_setting = 2;
    life_setting = 2;
    sound_test = 1;
    attract_seq = 0;
    enter_title();
}

void game_frame(void) {
    read_buttons();
    update_sound();
    update_subpixel();
    if (mode == 0) { run_title(); return; }
    if (mode == 1) { run_level(); return; }
    if (mode == 2) { run_clear(); return; }
    if (mode == 3) { run_game_over(); return; }
    if (mode == 4) { run_continue(); return; }
    if (mode == 5) { run_password(); return; }
    if (mode == 6) { run_options(); return; }
    if (mode == 7) { run_credits(); return; }
    if (mode == 8) {
        if ((joy_press & 128) != 0 || anim >= 300) {
            init_level();
        } else {
            anim = (u16)(anim + 1);
        }
        return;
    }
    if (mode == 9) { run_debug(); }
}
