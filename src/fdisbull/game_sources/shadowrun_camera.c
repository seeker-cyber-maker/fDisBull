/* Camera state from normal field follow at 3a3c..3d16. The source graphics
 * streaming calls at 40e2/4018 are explicit requests, not executed here.
 * The alternate scripted camera mode 3 is outside this slice. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef signed int i16;
typedef unsigned long u32;
typedef signed long i32;
u16 shadowrun_camera_player_x;
u16 shadowrun_camera_player_y;
u16 shadowrun_camera_heading;
u16 shadowrun_camera_x;
u16 shadowrun_camera_y;
u16 shadowrun_camera_min_x;
u16 shadowrun_camera_max_x;
u16 shadowrun_camera_min_y;
u16 shadowrun_camera_max_y;
u16 shadowrun_camera_scroll_ax;
u16 shadowrun_camera_scroll_ay;
u16 shadowrun_camera_scroll_bx;
u16 shadowrun_camera_scroll_by;
u16 shadowrun_camera_stream_x;
u16 shadowrun_camera_stream_y;
u16 shadowrun_camera_freeze_a;
u16 shadowrun_camera_freeze_b;
u16 shadowrun_camera_freeze_c;
u8 shadowrun_camera_mode;
u8 shadowrun_camera_previous_x;
u8 shadowrun_camera_previous_y;
u8 shadowrun_camera_request_x;
u8 shadowrun_camera_request_y;
u8 shadowrun_camera_supported;

i16 shadowrun_camera_axis_step(u16 center, u16 target, u8 previous) {
    u16 magnitude;
    i16 one;
    i16 two;
    if (center >= target) {
        magnitude = center - target;
        one = -1;
        two = -2;
    } else {
        magnitude = target - center;
        one = 1;
        two = 2;
    }
    if (magnitude >= 0x300U) return two;
    if (magnitude >= 0x180U) {
        if (previous == (u8)two) return two;
        return one;
    }
    if (previous == (u8)one) return one;
    return 0;
}

void shadowrun_camera_tick(void) {
    u16 at;
    u16 target_x;
    u16 target_y;
    u16 candidate;
    i16 step_x;
    i16 step_y;
    i32 product;
    shadowrun_camera_request_x = 0;
    shadowrun_camera_request_y = 0;
    shadowrun_camera_supported = 0;
    if (shadowrun_camera_mode == 3U) return;
    at = (shadowrun_camera_heading >> 8) & 0xfeU;
    product = (i32)(i16)rom16(0, 0x15e16UL + at) * 960L;
    product = product * 2L;
    target_y = (u16)(product >> 16);
    product = (i32)(i16)rom16(0, 0x15e56UL + at) * 960L;
    product = product * 2L;
    target_x = (u16)(product >> 16);
    target_x = target_x + shadowrun_camera_player_x;
    target_y = target_y + shadowrun_camera_player_y;
    if (target_x & 0x8000U) target_x = 0;
    if (target_y & 0x8000U) target_y = 0;
    step_x = shadowrun_camera_axis_step(
        (u16)(shadowrun_camera_x + 0x880U), target_x,
        shadowrun_camera_previous_x);
    step_y = shadowrun_camera_axis_step(
        (u16)(shadowrun_camera_y + 0x700U), target_y,
        shadowrun_camera_previous_y);
    shadowrun_camera_previous_x = (u8)step_x;
    shadowrun_camera_previous_y = (u8)step_y;
    shadowrun_camera_supported = 1;
    if (shadowrun_camera_freeze_a || shadowrun_camera_freeze_b ||
            shadowrun_camera_freeze_c) return;
    if (step_x) {
        candidate = (u16)(shadowrun_camera_x + step_x * 16);
        if ((i16)candidate >= (i16)shadowrun_camera_min_x &&
                (i16)candidate <= (i16)shadowrun_camera_max_x) {
            shadowrun_camera_x = candidate;
            shadowrun_camera_scroll_ax = shadowrun_camera_scroll_ax - step_x;
            shadowrun_camera_scroll_bx = shadowrun_camera_scroll_bx - step_x;
            candidate = candidate & 0xff80U;
            if (candidate != shadowrun_camera_stream_x) {
                shadowrun_camera_stream_x = candidate;
                shadowrun_camera_request_x = 1;
            }
        }
    }
    if (step_y) {
        candidate = (u16)(shadowrun_camera_y + step_y * 16);
        if ((i16)candidate >= (i16)shadowrun_camera_min_y &&
                (i16)candidate <= (i16)shadowrun_camera_max_y) {
            shadowrun_camera_y = candidate;
            shadowrun_camera_scroll_ay = shadowrun_camera_scroll_ay + step_y;
            shadowrun_camera_scroll_by = shadowrun_camera_scroll_by + step_y;
            candidate = candidate & 0xff80U;
            if (candidate != shadowrun_camera_stream_y) {
                shadowrun_camera_stream_y = candidate;
                shadowrun_camera_request_y = 1;
            }
        }
    }
}
