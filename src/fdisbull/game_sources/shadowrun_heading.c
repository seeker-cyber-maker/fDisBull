/* Reviewed 68000 field-record heading update; positions and collisions are not
 * represented here. Values are unsigned 16-bit words and wrap modulo 65536. */
typedef unsigned int u16;
u16 shadowrun_heading;
u16 shadowrun_heading_target;
void shadowrun_heading_tick(void) {
    u16 delta;
    delta = (u16)(shadowrun_heading - shadowrun_heading_target);
    if (delta == 0) return;
    if (delta & 0x8000U) {
        if (delta < 0xf800U) shadowrun_heading = (u16)(shadowrun_heading + 0x0800U);
        else shadowrun_heading = shadowrun_heading_target;
    } else {
        if (delta < 0x0800U) shadowrun_heading = shadowrun_heading_target;
        else shadowrun_heading = (u16)(shadowrun_heading - 0x0800U);
    }
}
