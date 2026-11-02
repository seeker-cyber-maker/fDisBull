/* Authored target-only diagnostic placement, not a recovered game operation.
 * Caller supplies exact 1/16-pixel destination and assisted policy. The source
 * collision routine is used only for terrain/rectangle/slope; dynamic entity
 * collision and original reachability remain unknown. Result 1 is committed,
 * 2 is refused. Scratch state from collision probing is restored. */
u16 shadowrun_debug_x, shadowrun_debug_y;
u8 shadowrun_debug_assisted, shadowrun_debug_recenter, shadowrun_debug_result;
void shadowrun_debug_place(void) {
    u16 px,py,cx,cy,nx,ny,dx,dy;
    u16 old_fixed_x,old_fixed_y,old_probe_x,old_probe_y,old_offset,old_special,old_raw,old_status,old_boundary,old_slope;
    u8 old_flags,old_probe_result,c0,c1,c2,c3;
    shadowrun_debug_result=2;
    if (shadowrun_debug_assisted!=1U || shadowrun_debug_recenter>1U) return;
    px=shadowrun_debug_x>>4; py=shadowrun_debug_y>>4;
    if (px<12U || py<7U || px>=2036U || py>=1401U) return;
    if (px<shadowrun_x_min+12U || px+12U>=shadowrun_x_max ||
        py<shadowrun_y_min+7U || py+7U>=shadowrun_y_max) return;
    nx=shadowrun_camera_x;ny=shadowrun_camera_y;
    if (shadowrun_debug_recenter) {
        if (shadowrun_camera_mode==3U || shadowrun_camera_freeze_a ||
            shadowrun_camera_freeze_b || shadowrun_camera_freeze_c) return;
        if ((shadowrun_camera_x & 15U) || (shadowrun_camera_y & 15U) ||
            (shadowrun_camera_min_x & 15U) || (shadowrun_camera_max_x & 15U) ||
            (shadowrun_camera_min_y & 15U) || (shadowrun_camera_max_y & 15U) ||
            shadowrun_camera_min_x>shadowrun_camera_max_x || shadowrun_camera_min_y>shadowrun_camera_max_y) return;
        nx=0;ny=0;
        if (shadowrun_debug_x>=0x880U) nx=(shadowrun_debug_x-0x880U)&0xfff0U;
        if (shadowrun_debug_y>=0x700U) ny=(shadowrun_debug_y-0x700U)&0xfff0U;
        if(nx<shadowrun_camera_min_x) nx=shadowrun_camera_min_x;
        if(nx>shadowrun_camera_max_x) nx=shadowrun_camera_max_x;
        if(ny<shadowrun_camera_min_y) ny=shadowrun_camera_min_y;
        if(ny>shadowrun_camera_max_y) ny=shadowrun_camera_max_y;
    }
    cx=nx>>4;cy=ny>>4;
    if (px<cx+12U || px>=cx+244U || py<cy+7U || py>=cy+217U) return;
    old_fixed_x=shadowrun_fixed_x;old_fixed_y=shadowrun_fixed_y;
    old_probe_x=shadowrun_probe_x;old_probe_y=shadowrun_probe_y;
    old_flags=shadowrun_probe_flags;old_probe_result=shadowrun_probe_result;
    old_offset=shadowrun_probe_map_offset;old_special=shadowrun_probe_special;
    old_raw=shadowrun_raw_status;old_status=shadowrun_collision_status;
    old_boundary=shadowrun_boundary_hit;old_slope=shadowrun_slope_mode;
    c0=shadowrun_probe_corners[0];c1=shadowrun_probe_corners[1];
    c2=shadowrun_probe_corners[2];c3=shadowrun_probe_corners[3];
    shadowrun_fixed_x=shadowrun_debug_x;shadowrun_fixed_y=shadowrun_debug_y;
    shadowrun_probe_flags=shadowrun_player_flags;
    shadowrun_collision_check();
    px=shadowrun_collision_status;
    shadowrun_fixed_x=old_fixed_x;shadowrun_fixed_y=old_fixed_y;
    shadowrun_probe_x=old_probe_x;shadowrun_probe_y=old_probe_y;
    shadowrun_probe_flags=old_flags;shadowrun_probe_result=old_probe_result;
    shadowrun_probe_map_offset=old_offset;shadowrun_probe_special=old_special;
    shadowrun_raw_status=old_raw;shadowrun_collision_status=old_status;
    shadowrun_boundary_hit=old_boundary;shadowrun_slope_mode=old_slope;
    shadowrun_probe_corners[0]=c0;shadowrun_probe_corners[1]=c1;
    shadowrun_probe_corners[2]=c2;shadowrun_probe_corners[3]=c3;
    if (px!=0U) return;
    if (shadowrun_debug_recenter) {
        dx=(nx>>4)-(shadowrun_camera_x>>4);dy=(ny>>4)-(shadowrun_camera_y>>4);
        shadowrun_camera_scroll_ax-=dx;shadowrun_camera_scroll_bx-=dx;
        shadowrun_camera_scroll_ay+=dy;shadowrun_camera_scroll_by+=dy;
        shadowrun_camera_previous_x=0;shadowrun_camera_previous_y=0;
        shadowrun_camera_request_x=((nx&0xff80U)!=shadowrun_camera_stream_x);
        shadowrun_camera_request_y=((ny&0xff80U)!=shadowrun_camera_stream_y);
        shadowrun_camera_stream_x=nx&0xff80U;shadowrun_camera_stream_y=ny&0xff80U;
        shadowrun_camera_x=nx;shadowrun_camera_y=ny;
    }
    shadowrun_player_x=shadowrun_debug_x;shadowrun_player_y=shadowrun_debug_y;
    shadowrun_debug_result=1;
}
