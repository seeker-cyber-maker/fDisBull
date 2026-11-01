/* Reviewed field collision dispatch around the raw map probe. The caller
 * supplies a valid 2816-byte map and a source-ROM rectangle-table pointer.
 * This determines collision status only; it does not dispatch scene events. */
typedef signed int i16;
typedef unsigned long u32;
u16 shadowrun_fixed_x;
u16 shadowrun_fixed_y;
u16 shadowrun_x_min;
u16 shadowrun_x_max;
u16 shadowrun_y_min;
u16 shadowrun_y_max;
u16 shadowrun_boundary_hit;
u16 shadowrun_slope_mode;
u16 shadowrun_raw_status;
u16 shadowrun_collision_status;
u32 shadowrun_rect_base;

u8 shadowrun_rectangle_collision(u8 raw) {
    u32 at;
    i16 minx;
    i16 maxx;
    i16 miny;
    i16 maxy;
    at = shadowrun_rect_base + (u32)raw * 10UL;
    minx = (i16)(u16)(rom16(0,at) - 12U);
    maxx = (i16)(u16)(rom16(0,at + 2UL) + 12U);
    miny = (i16)(u16)(rom16(0,at + 4UL) - 7U);
    maxy = (i16)(u16)(rom16(0,at + 6UL) + 7U);
    if ((i16)shadowrun_probe_x < minx || (i16)shadowrun_probe_x > maxx) return 0;
    if ((i16)shadowrun_probe_y < miny || (i16)shadowrun_probe_y > maxy) return 0;
    return 1;
}

u8 shadowrun_slope_collision(u8 code, u16 x, u16 y) {
    u16 base_x;
    u16 base_y;
    u16 delta_x;
    u16 delta_y;
    u16 kind;
    base_x = (u16)((shadowrun_probe_map_offset & 63U) << 5);
    base_y = (u16)((shadowrun_probe_map_offset & 0xffc0U) >> 1);
    delta_x = (u16)(x - base_x);
    kind = code & 0x38U;
    if (kind == 0x20U || kind == 0x38U) {
        delta_y = (u16)(base_y + 31U - y);
        if (kind == 0x20U) return delta_x < delta_y;
        return delta_x >= delta_y;
    }
    delta_y = (u16)(y - base_y);
    if (kind == 0x28U) return delta_x >= delta_y;
    return delta_x < delta_y;
}

void shadowrun_collision_check(void) {
    u8 raw;
    u8 i;
    u16 x;
    u16 y;
    shadowrun_boundary_hit = 0;
    shadowrun_slope_mode = 0;
    shadowrun_probe_x = shadowrun_fixed_x >> 4;
    shadowrun_probe_y = shadowrun_fixed_y >> 4;
    if (shadowrun_probe_x >= shadowrun_x_max || shadowrun_probe_x < shadowrun_x_min ||
        shadowrun_probe_y >= shadowrun_y_max || shadowrun_probe_y < shadowrun_y_min) {
        shadowrun_boundary_hit = 0xffffU;
        shadowrun_probe_corners[0] = 0;
        shadowrun_probe_corners[1] = 127;
        shadowrun_probe_corners[2] = 0;
        shadowrun_probe_corners[3] = 127;
        shadowrun_collision_status = 127;
        return;
    }
    shadowrun_probe_terrain();
    raw = shadowrun_probe_result;
    shadowrun_raw_status = raw;
    if (raw & 0x80U) shadowrun_raw_status |= 0xff00U;
    shadowrun_collision_status = shadowrun_raw_status;
    if (raw == 0 || raw == 127U || (raw & 0x80U)) return;
    if (raw & 0x40U) {
        shadowrun_slope_mode = 0xffffU;
        if (raw == 126U || (raw & 0x20U) == 0) {
            shadowrun_collision_status = 127;
            return;
        }
    }
    if (raw & 0x20U) {
        for (i = 0; i < 4; i = i + 1) {
            if (shadowrun_probe_corners[i] & 0x20U) {
                if (i & 1U) x = (u16)(shadowrun_probe_x + 12U);
                else x = (u16)(shadowrun_probe_x - 12U);
                if (i & 2U) y = (u16)(shadowrun_probe_y + 7U);
                else y = (u16)(shadowrun_probe_y - 7U);
                if (shadowrun_slope_collision(shadowrun_probe_corners[i],x,y)) {
                    shadowrun_collision_status = 127;
                    return;
                }
            }
        }
    } else {
        if (shadowrun_rectangle_collision(raw)) {
            shadowrun_collision_status = 127;
            return;
        }
    }
    shadowrun_collision_status = 0;
}
