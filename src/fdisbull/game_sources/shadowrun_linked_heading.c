/* $15D3C..$15DCA, target-minus-source signed-word direction and metric.
 * Lookup tables remain in the caller's exact external ROM region. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u8 rom8(u8 region,u32 offset);
u16 rom16(u8 region,u32 offset);
u16 shadowrun_linked_source_x, shadowrun_linked_source_y;
u16 shadowrun_linked_target_x, shadowrun_linked_target_y;
u16 shadowrun_linked_heading, shadowrun_linked_metric;
u8 shadowrun_linked_supported;
void shadowrun_linked_measure(void) {
    u16 dx; u16 dy; u16 major; u16 minor; u16 t; u16 quadrant; u16 entry; u16 i; u8 exchanged;
    shadowrun_linked_supported=0;
    if (shadowrun_linked_target_x >= shadowrun_linked_source_x) {
        dx=shadowrun_linked_target_x-shadowrun_linked_source_x;
        quadrant=0;
        if (dx==0) quadrant=1;
    } else { dx=shadowrun_linked_source_x-shadowrun_linked_target_x; quadrant=2; }
    if (shadowrun_linked_target_y >= shadowrun_linked_source_y) {
        dy=shadowrun_linked_target_y-shadowrun_linked_source_y;
        if (dy==0) quadrant += 4U;
    } else { dy=shadowrun_linked_source_y-shadowrun_linked_target_y; quadrant += 8U; }
    if (dx>32767U || dy>32767U) return;
    major=dy; minor=dx; exchanged=0;
    if (minor>=major) {t=major;major=minor;minor=t;exchanged=1;}
    shadowrun_linked_metric=major+(minor >> 1);
    for (i=0;i<16;i=i+1) {
        if (major<32) break;
        major=major >> 1; minor=minor >> 1;
    }
    if (exchanged) {t=major;major=minor;minor=t;}
    entry=rom16(0, 0x15df6UL + (u32)quadrant*2UL);
    if (!(entry & 64U)) {t=major;major=minor;minor=t;}
    entry=(entry+rom8(0,0x15f96UL + (u32)major*32UL + minor)) & 255U;
    shadowrun_linked_heading=entry*256U;
    shadowrun_linked_supported=1;
}
