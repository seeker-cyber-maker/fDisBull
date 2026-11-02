/* Captured type-11 idle callback $B45C..$B48A. */
u8 shadowrun_ai_idle_supported;
void shadowrun_ai_idle_tick(void) {
    u16 rotated; u16 i;
    shadowrun_ai_idle_supported=0;
    if (shadowrun_ai_kind!=11U || shadowrun_ai_callback!=0xb45cUL ||
        shadowrun_ai_flags!=37U || !(shadowrun_ai_equipment_flags & 32U)) return;
    rotated=(u16)((shadowrun_ai_heading<<3)|(shadowrun_ai_heading>>13));
    if (rotated & 32768U) rotated+=1U;
    shadowrun_fixed_x=shadowrun_ai_x;shadowrun_fixed_y=shadowrun_ai_y;
    shadowrun_probe_flags=shadowrun_ai_flags;
    shadowrun_collision_check();
    shadowrun_ai_move_state=0;
    shadowrun_ai_animation=rom16(0,0xc052UL+((rotated & 7U)<<1));
    for(i=0;i<4;i=i+1)shadowrun_ai_corners[i]=shadowrun_probe_corners[i];
    shadowrun_ai_idle_supported=1;
}
