/* $14E0A/$14F50: up to four hostile projectile substeps. Shared terrain and
 * bounds are supplied by the same world model as movement. Profile 1 attests
 * the captured player and inactive other party records. Non-player actors
 * are scanned from the live shared source-slot arrays. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
extern u8 shadowrun_terrain_map[2816];
extern u16 shadowrun_x_min,shadowrun_x_max,shadowrun_y_min,shadowrun_y_max;
extern u16 shadowrun_target_x[7],shadowrun_target_y[7];
extern u8 shadowrun_target_flags[7],shadowrun_play_actor_hp[7];
u32 shadowrun_hostile_motion_x,shadowrun_hostile_motion_y;
u16 shadowrun_hostile_motion_vx,shadowrun_hostile_motion_vy;
u16 shadowrun_hostile_motion_player_x,shadowrun_hostile_motion_player_y;
u8 shadowrun_hostile_motion_profile,shadowrun_hostile_motion_supported;
u8 shadowrun_hostile_motion_state; /* 1 flight, 2 player hit, 3 wall, 4 expiry, 5 miss, 6/7 shooter hit/miss */
u8 shadowrun_hostile_motion_lifetime,shadowrun_hostile_motion_effect,shadowrun_hostile_motion_steps;
u8 shadowrun_hostile_motion_continuation_required;
void shadowrun_hostile_motion_tick(void) {
    u16 i;u16 j;u16 px;u16 py;u16 tx;u16 ty;u16 at;u16 cell;u16 life;u16 steps;u16 state;
    u32 x;u32 y;u32 nx;u32 ny;u32 delta;
    shadowrun_hostile_motion_supported=0;
    if (shadowrun_hostile_motion_profile!=1U || shadowrun_hostile_motion_continuation_required ||
        shadowrun_hostile_motion_state!=1U ||
        shadowrun_hostile_motion_effect>8U || shadowrun_hostile_motion_player_x<144U ||
        shadowrun_hostile_motion_player_x>65391U || shadowrun_hostile_motion_player_y<144U ||
        shadowrun_hostile_motion_player_y>65391U || shadowrun_x_min>=shadowrun_x_max ||
        shadowrun_y_min>=shadowrun_y_max) return;
    x=shadowrun_hostile_motion_x;y=shadowrun_hostile_motion_y;
    life=shadowrun_hostile_motion_lifetime;steps=shadowrun_hostile_motion_steps;state=1;
    for (i=0;i<4U;i+=1U) {
        nx=x;ny=y;
        if (shadowrun_hostile_motion_vx & 32768U) {
            delta=(u32)(u16)(0U-shadowrun_hostile_motion_vx)*256UL;nx-=delta;
        } else nx+=(u32)shadowrun_hostile_motion_vx*256UL;
        if (shadowrun_hostile_motion_vy & 32768U) {
            delta=(u32)(u16)(0U-shadowrun_hostile_motion_vy)*256UL;ny-=delta;
        } else ny+=(u32)shadowrun_hostile_motion_vy*256UL;
        px=(u16)(nx/65536UL);py=(u16)(ny/65536UL);tx=px>>4;ty=py>>4;
        if (tx<shadowrun_x_min || tx>=shadowrun_x_max || ty<shadowrun_y_min || ty>=shadowrun_y_max) {
            state=3;break;
        }
        at=((ty<<1)&65472U)+(tx>>5);if (at>=2816U) return;
        cell=shadowrun_terrain_map[at];
        if (cell==127U || (cell & 128U)) {state=3;break;}
        if (cell!=0U) return;
        if (life==0U) {life=255U;state=4;break;}
        life-=1U;steps+=1U;x=nx;y=ny;
        if (px>=shadowrun_hostile_motion_player_x-144U && px<shadowrun_hostile_motion_player_x+144U &&
            py>=shadowrun_hostile_motion_player_y-144U && py<shadowrun_hostile_motion_player_y+144U) {
            x=(u32)shadowrun_hostile_motion_player_x*65536UL+(x&65535UL);
            y=(u32)(u16)(shadowrun_hostile_motion_player_y+16U)*65536UL+(y&65535UL);
            if (shadowrun_hostile_motion_effect) state=2;else state=5;
            break;
        }
        for (j=0;j<7U;j+=1U) {
            if ((shadowrun_target_flags[j]&1U) && !(shadowrun_target_flags[j]&80U) && shadowrun_play_actor_hp[j]) {
                tx=shadowrun_target_x[j];ty=shadowrun_target_y[j];
                if (tx<144U || tx>65391U || ty<144U || ty>65391U) return;
                if (px>=tx-144U && px<tx+144U && py>=ty-144U && py<ty+144U) {
                    if (j!=0U) return; /* another actor's damage is unknown */
                    x=(u32)tx*65536UL+(x&65535UL);
                    y=(u32)(u16)(ty+16U)*65536UL+(y&65535UL);
                    if (shadowrun_hostile_motion_effect) state=6;else state=7;
                    break;
                }
            }
        }
        if (state!=1U) break;
    }
    shadowrun_hostile_motion_x=x;shadowrun_hostile_motion_y=y;
    shadowrun_hostile_motion_lifetime=(u8)life;shadowrun_hostile_motion_steps=(u8)steps;
    if (state!=1U) {
        shadowrun_hostile_motion_vx=0;shadowrun_hostile_motion_vy=0;
        /* Item-10 projectile later enters unmodeled $14F86 burst handling. */
        shadowrun_hostile_motion_continuation_required=1;
    }
    shadowrun_hostile_motion_state=(u8)state;shadowrun_hostile_motion_supported=1;
}
