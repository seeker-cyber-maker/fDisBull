/*
 * Altered source version: Miniplanets actor logic expressed in the reviewed
 * C-shaped authoring subset for fDisBull UIL. This is not the original source.
 * Source: sikthehedgehog/miniplanets, commit
 * 0ac9c395289cc5d0837c96d45e61a27300e8eebc, src-68k actor files.
 * The original ROM, its tables, graphics, music and other assets stay private.
 * Pure drawing routines and RaftList sprite requests belong to presentation.
 * Mutable world tiles, player carrying and object-slot update order remain here.
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

u8 objects[192];
u8 actor_capacity_fault;

/* objects.68k: InitObjects, original ROM 0x4A26. */
void init_objects(void) {
    u16 i;
    for (i = 0; i < 48; i = i + 1) {
        objects[i * 4] = 0;
    }
}

/*
 * AddObject, ROM0x4A3C: first free slot. Original code scans beyond the pool
 * when full. This profile explicitly faults instead; capacity is a contract
 * assumption, not a claim of parity for the original's out-of-pool behaviour.
 */
u8 add_object(u8 object_type, u8 x, u8 y, u8 data) {
    u8 slot;
    u8 p;
    for (slot = 0; slot < 48; slot = slot + 1) {
        p = (u16)slot * 4;
        if (objects[p] == 0) {
            objects[p] = object_type;
            objects[p + 1] = x;
            objects[p + 2] = y;
            objects[p + 3] = data;
            if (object_type == 1 || object_type == 24) {
                keys_left = (u8)(keys_left + 1);
            }
            return slot;
        }
    }
    actor_capacity_fault = 1;
    return 255;
}

/* keys.68k: RunKey, ROM 0x4B90, shared by keys and crystals. */
void run_key(u8 slot) {
    u8 p;
    u16 i;
    u8 sound;
    p = (u16)slot * 4;
    if (collides_player(objects[p + 1], objects[p + 2], 8, 8) == 0) {
        return;
    }
    keys_left = (u8)(keys_left - 1);
    sound = 6;
    if (objects[p] != 1) {
        sound = 7;
    }
    if (keys_left == 0) {
        sound = (u8)(sound + 2);
    }
    play_sfx(sound);
    objects[p] = 0;
    if (keys_left == 0 && stage == 45) {
        ending_phase = 1;
        play_sfx(10);
        shake_timer = 64;
        player_jump = 0;
        for (i = 0; i < 192; i = i + 1) {
            objects[i] = 0;
        }
    }
}

/* maces.68k: GetMacePosition. The exact original signed sine words are read. */
u8 mace_x(u8 slot) {
    u8 p;
    i16 distance;
    p = (u16)slot * 4;
    distance = (i16)rom16(0, 0x658F8UL + (u16)objects[p + 3] * 2);
    distance = (i16)(distance >> 4);
    return (u8)(objects[p + 1] + distance);
}

u8 mace_y(u8 slot) {
    u8 p;
    i16 distance;
    p = (u16)slot * 4;
    distance = (i16)rom16(0, 0x65978UL + (u16)objects[p + 3] * 2);
    distance = (i16)(-distance);
    distance = (i16)(distance >> 4);
    return (u8)(objects[p + 2] + distance);
}

/* RunMace, ROM 0x4C5C. Angles advance by four, not by one. */
void run_mace(u8 slot) {
    u8 p;
    p = (u16)slot * 4;
    objects[p + 3] = (u8)(objects[p + 3] - 4);
    if (objects[p] != 6) {
        objects[p + 3] = (u8)(objects[p + 3] + 8);
    }
    if (collides_player(mace_x(slot), mace_y(slot), 8, 8) != 0) {
        hurt_player(5);
    }
}

/* rafts.68k: direction wrappers 0x4CEC/4D0A/4D28/4D46; common 0x4D64. */
void run_raft(u8 slot) {
    u8 p;
    u8 object_type;
    u8 x;
    u8 y;
    i8 dx;
    i8 dy;
    i16 ox;
    i16 oy;
    u8 i;
    u8 tile;
    p = (u16)slot * 4;
    object_type = objects[p];
    if (objects[p + 3] != 0) {
        if ((objects[p + 3] & 128) != 0) {
            return;
        }
        objects[p + 3] = (u8)(anim & 15);
        if (objects[p + 3] != 0) {
            return;
        }
    }
    dx = 0;
    dy = 0;
    if (object_type == 2) { dy = -1; }
    if (object_type == 3) { dy = 1; }
    if (object_type == 4) { dx = -1; }
    if (object_type == 5) { dx = 1; }
    x = objects[p + 1];
    y = objects[p + 2];
    for (i = 0; i < 6; i = i + 1) {
        if (object_type < 4) {
            ox = (i16)(i / 3) * 16 - 16;
            oy = (i16)(i % 3) * 16 - 16;
        } else {
            ox = (i16)(i % 3) * 16 - 16;
            oy = (i16)(i / 3) * 16 - 16;
        }
        set_tile((u8)(x + ox), (u8)(y + oy), 3);
    }
    x = (u8)(x + dx);
    y = (u8)(y + dy);
    objects[p + 1] = x;
    objects[p + 2] = y;
    if (collides_player(x, y, 16, 16) != 0) {
        player_x = (u8)(player_x + dx);
        player_y = (u8)(player_y + dy);
    }
    for (i = 0; i < 6; i = i + 1) {
        if (object_type < 4) {
            ox = (i16)(i / 3) * 16 - 16;
            oy = (i16)(i % 3) * 16 - 16;
        } else {
            ox = (i16)(i % 3) * 16 - 16;
            oy = (i16)(i / 3) * 16 - 16;
        }
        tile = (u8)(23 + (object_type - 2) * 3 + i % 3);
        set_tile((u8)(x + ox), (u8)(y + oy), tile);
    }
}

/* bombs.68k: DetonateBomb; blast offsets are the original 4-by-4 table. */
void detonate_bomb(u8 slot) {
    u8 p;
    u8 x;
    u8 y;
    u8 fill;
    u8 i;
    i16 ox;
    i16 oy;
    p = (u16)slot * 4;
    fill = objects[p + 3];
    x = objects[p + 1];
    y = objects[p + 2];
    for (i = 0; i < 16; i = i + 1) {
        ox = (i16)(i % 4) * 16 - 32;
        oy = (i16)(i / 4) * 16 - 32;
        set_tile((u8)(x + ox), (u8)(y + oy), fill);
    }
    play_sfx(10);
    objects[p] = 26;
    objects[p + 3] = 0;
    shake_timer = 32;
}

/* switches.68k: RunSwitch, ROM 0x4F36. Only the following N slots change. */
void run_switch(u8 slot) {
    u8 p;
    u16 next;
    u8 count;
    u8 i;
    u8 object_type;
    p = (u16)slot * 4;
    if (collides_player(objects[p + 1], objects[p + 2], 8, 8) == 0) {
        return;
    }
    count = objects[p + 3];
    for (i = 0; i < 48; i = i + 1) {
        if (i < count) {
            next = ((u16)slot + 1 + i) * 4;
            object_type = objects[next];
            if (object_type == 8) {
                detonate_bomb((u8)(slot + 1 + i));
            } else {
                if (object_type >= 2 && object_type <= 5) {
                    objects[next + 3] = (u8)(-objects[next + 3]);
                }
            }
        }
    }
    objects[p] = 0;
}

/* RunBomb, ROM 0x4F9A. Damage precedes the explosion/shake immunity. */
void run_bomb(u8 slot) {
    u8 p;
    p = (u16)slot * 4;
    if (collides_player(objects[p + 1], objects[p + 2], 8, 8) != 0) {
        hurt_player(10);
        detonate_bomb(slot);
    }
}

/* RunBombFx, ROM 0x5036: original BLS keeps smoke through distance32. */
void run_bomb_fx(u8 slot) {
    u8 p;
    p = (u16)slot * 4;
    objects[p + 3] = (u8)(objects[p + 3] + 1);
    if (objects[p + 3] > 32) {
        objects[p] = 0;
    }
}

/* electricity.68k: both beam orientations use the same point collision. */
void run_electricity(u8 slot) {
    u8 p;
    p = (u16)slot * 4;
    if (collides_player(objects[p + 1], objects[p + 2], 8, 8) != 0) {
        hurt_player(9);
    }
}

/* balls.68k: BallImpact uses signed wrapped distances, inclusive +/-80. */
void ball_impact(u8 slot) {
    u8 p;
    i8 dx;
    i8 dy;
    p = (u16)slot * 4;
    dx = (i8)(objects[p + 1] - player_x);
    dy = (i8)(objects[p + 2] - player_y);
    if (dx > 80 || dx < -80 || dy > 80 || dy < -80) {
        return;
    }
    play_sfx(4);
}

/* RunBall{Up,Down,Left,Right}, ROM 0x511A/513E/5162/5186. */
void run_ball(u8 slot) {
    u8 p;
    u8 object_type;
    p = (u16)slot * 4;
    object_type = objects[p];
    if (object_type == 12) { objects[p + 2] = (u8)(objects[p + 2] - 1); }
    if (object_type == 13) { objects[p + 2] = (u8)(objects[p + 2] + 1); }
    if (object_type == 14) { objects[p + 1] = (u8)(objects[p + 1] - 1); }
    if (object_type == 15) { objects[p + 1] = (u8)(objects[p + 1] + 1); }
    if (get_collision(objects[p + 1], objects[p + 2]) == 1) {
        objects[p] = (u8)(object_type ^ 1);
        ball_impact(slot);
    }
    if (collides_player(objects[p + 1], objects[p + 2], 10, 10) != 0) {
        hurt_player(5);
    }
}

/* RunFireball{Up,Down,Left,Right}, ROM 0x53F6/53FE/5406/540E. */
void run_fireball(u8 slot) {
    u8 p;
    u8 object_type;
    p = (u16)slot * 4;
    object_type = objects[p];
    if (object_type == 20) { objects[p + 2] = (u8)(objects[p + 2] - 1); }
    if (object_type == 21) { objects[p + 2] = (u8)(objects[p + 2] + 1); }
    if (object_type == 22) { objects[p + 1] = (u8)(objects[p + 1] - 1); }
    if (object_type == 23) { objects[p + 1] = (u8)(objects[p + 1] + 1); }
    if (collides_player(objects[p + 1], objects[p + 2], 10, 10) != 0) {
        hurt_player(7);
    }
}

/* children.68k: RunChild, ROM 0x544E. The child remains during the win. */
void run_child(u8 slot) {
    u8 p;
    p = (u16)slot * 4;
    if (keys_left != 0) {
        return;
    }
    if (collides_player(objects[p + 1], objects[p + 2], 8, 8) != 0) {
        win_stage();
    }
}

/* springs.68k: RunSpringFx, ROM 0x54D4. Zero input wraps to255. */
void run_spring_fx(u8 slot) {
    u8 p;
    p = (u16)slot * 4;
    objects[p + 3] = (u8)(objects[p + 3] - 1);
    if (objects[p + 3] == 0) {
        objects[p] = 0;
    }
}

/*
 * orbs.68k: RunOrb at0x5212; AI table0x532A points to red0x5344,
 * pink0x5352, blue0x5380 and orange0x53A2. The shipped pink AI always
 * selects offset0 (+48X), regardless of player angle; that quirk remains.
 * Orange gets targetY from the first Rand call and targetX from the second.
 * rand16() binds hardware HV samples through the shared explicit input API.
 */
void run_orb(u8 slot) {
    u8 p;
    u8 free_mask;
    u8 back;
    u8 direction;
    u8 best_distance;
    u8 candidate;
    u8 target_x;
    u8 target_y;
    u8 x;
    u8 y;
    p = (u16)slot * 4;
    x = objects[p + 1];
    y = objects[p + 2];
    if (collides_player(x, y, 10, 10) != 0) {
        hurt_player(5);
    }
    if (((x | y) & 31) == 0) {
        free_mask = 15;
        if (get_collision(x, (u8)(y - 32)) != 0) {
            free_mask = (u8)(free_mask & 14);
        }
        if (get_collision(x, (u8)(y + 32)) != 0) {
            free_mask = (u8)(free_mask & 13);
        }
        if (get_collision((u8)(x - 32), y) != 0) {
            free_mask = (u8)(free_mask & 11);
        }
        if (get_collision((u8)(x + 32), y) != 0) {
            free_mask = (u8)(free_mask & 7);
        }
        back = (u8)((objects[p + 3] & 3) ^ 1);
        free_mask = (u8)(free_mask & ~(1 << back));
        if (free_mask == 0) {
            free_mask = (u8)(free_mask | (1 << back));
        }
        target_x = player_x;
        target_y = player_y;
        if (objects[p] == 17) {
            target_x = (u8)(target_x + 48);
        }
        if (objects[p] == 18) {
            target_x = (u8)(2 * player_x - x);
            target_y = (u8)(2 * player_y - y);
        }
        if (objects[p] == 19) {
            target_y = (u8)rand16();
            target_x = (u8)rand16();
        }
        direction = 0;
        best_distance = 255;
        if ((free_mask & 1) != 0) {
            best_distance = (u8)(y - target_y);
        }
        if ((free_mask & 2) != 0) {
            candidate = (u8)(-best_distance);
            if (best_distance > candidate) {
                best_distance = candidate;
                direction = 1;
            }
        }
        candidate = (u8)(x - target_x);
        if ((free_mask & 4) != 0) {
            if (best_distance > candidate) {
                best_distance = candidate;
                direction = 2;
            }
        }
        if ((free_mask & 8) != 0) {
            candidate = (u8)(-candidate);
            if (best_distance > candidate) {
                direction = 3;
            }
        }
        objects[p + 3] = direction;
    }
    direction = objects[p + 3];
    if (direction == 0) { objects[p + 2] = (u8)(objects[p + 2] - 1); }
    if (direction == 1) { objects[p + 2] = (u8)(objects[p + 2] + 1); }
    if (direction == 2) { objects[p + 1] = (u8)(objects[p + 1] - 1); }
    if (direction == 3) { objects[p + 1] = (u8)(objects[p + 1] + 1); }
}

/*
 * objects.68k: RunObjects0x4A72, handler table0x4A7C..0x4AEC,
 * ScanObjects0x4B66..0x4B90. Read each type immediately before dispatch:
 * earlier actors may change later actors or create FX in a later free slot.
 */
void run_objects(void) {
    u8 slot;
    u8 object_type;
    for (slot = 0; slot < 48; slot = slot + 1) {
        object_type = objects[(u16)slot * 4];
        if (object_type == 0) { continue; }
        if (object_type == 1 || object_type == 24) { run_key(slot); }
        if (object_type >= 2 && object_type <= 5) { run_raft(slot); }
        if (object_type == 6 || object_type == 7) { run_mace(slot); }
        if (object_type == 8) { run_bomb(slot); }
        if (object_type == 9) { run_switch(slot); }
        if (object_type == 10 || object_type == 11) { run_electricity(slot); }
        if (object_type >= 12 && object_type <= 15) { run_ball(slot); }
        if (object_type >= 16 && object_type <= 19) { run_orb(slot); }
        if (object_type >= 20 && object_type <= 23) { run_fireball(slot); }
        if (object_type == 25) { run_child(slot); }
        if (object_type == 26) { run_bomb_fx(slot); }
        if (object_type == 27) { run_spring_fx(slot); }
    }
}
