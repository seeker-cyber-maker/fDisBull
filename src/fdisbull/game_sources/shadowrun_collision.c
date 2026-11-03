/* Reviewed raw terrain-sampling boundary. Caller must ensure every computed
 * offset is in this 2816-byte scene map. This does not resolve rectangle
 * collisions, movement acceptance, event actions, or scene changes. */
typedef unsigned char u8;
typedef unsigned int u16;
u8 shadowrun_terrain_map[2816];
u8 shadowrun_probe_flags;
u16 shadowrun_probe_x;
u16 shadowrun_probe_y;
u8 shadowrun_probe_corners[4];
u16 shadowrun_probe_map_offset;
u16 shadowrun_probe_special;
u8 shadowrun_probe_result;
u16 shadowrun_terrain_offset(u16 x, u16 y) {
    return (u16)((((u16)(y << 1)) & 0xffc0U) + (x >> 5));
}
void shadowrun_probe_terrain(void) {
    u16 x;
    u16 y;
    u16 at;
    u8 current;
    u8 result;
    u8 i;
    x = shadowrun_probe_x;
    y = shadowrun_probe_y;
    shadowrun_probe_special = 0;
    if ((shadowrun_probe_flags & 4U) == 0) {
        at = shadowrun_terrain_offset(x,y);
        shadowrun_probe_map_offset = at;
        shadowrun_probe_corners[0] = shadowrun_terrain_map[at];
        shadowrun_probe_result = shadowrun_probe_corners[0];
        return;
    }
    result = 0;
    for (i = 0; i < 4; i = i + 1) {
        if (i & 1U) x = (u16)(shadowrun_probe_x + 12U);
        else x = (u16)(shadowrun_probe_x - 12U);
        if (i & 2U) y = (u16)(shadowrun_probe_y + 7U);
        else y = (u16)(shadowrun_probe_y - 7U);
        at = shadowrun_terrain_offset(x,y);
        current = shadowrun_terrain_map[at];
        shadowrun_probe_corners[i] = current;
        if (current == 127U) shadowrun_probe_special = 0x7f00U;
        if (i == 0 || current >= result) {
            result = current;
            shadowrun_probe_map_offset = at;
        }
    }
    if (shadowrun_probe_special != 0) result = 127U;
    shadowrun_probe_result = result;
}
