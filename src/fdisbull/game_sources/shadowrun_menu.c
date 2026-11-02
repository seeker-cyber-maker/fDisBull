/* Original menu choices and cursor updates. Input is the source's edge bits
 * in FFDD22, not a host controller mask. Video, sound, the load menu, and the
 * archetype initializer are deliberately outside this bounded transition. */
typedef unsigned char u8;
typedef unsigned int u16;
u8 shadowrun_menu_phase; /* 0 start options, 1 archetype, 2 initialize, 3 load */
u8 shadowrun_menu_cursor;
u8 shadowrun_menu_preview;
u8 shadowrun_menu_archetype;
u8 shadowrun_menu_supported;
u16 shadowrun_menu_pressed;
void shadowrun_menu_tick(void) {
    u8 maximum;
    shadowrun_menu_supported = 0;
    if (shadowrun_menu_phase > 1U) return;
    maximum = 1U;
    if (shadowrun_menu_phase == 1U) maximum = 2U;
    if (shadowrun_menu_cursor > maximum) return;
    if (shadowrun_menu_phase == 1U && shadowrun_menu_preview != shadowrun_menu_cursor) return;
    if (shadowrun_menu_pressed & 0x0100U) {
        if (shadowrun_menu_cursor == 0U) shadowrun_menu_cursor = maximum;
        else shadowrun_menu_cursor -= 1U;
    } else if (shadowrun_menu_pressed & 0x0200U) {
        if (shadowrun_menu_cursor == maximum) shadowrun_menu_cursor = 0U;
        else shadowrun_menu_cursor += 1U;
    }
    if (shadowrun_menu_phase == 1U) shadowrun_menu_preview = shadowrun_menu_cursor;
    if (shadowrun_menu_pressed & 0x7000U) {
        if (shadowrun_menu_phase == 0U) {
            if (shadowrun_menu_cursor == 0U) {
                shadowrun_menu_phase = 1U;
                shadowrun_menu_cursor = 0U;
                shadowrun_menu_preview = 0U;
            } else shadowrun_menu_phase = 3U;
        } else {
            shadowrun_menu_archetype = shadowrun_menu_cursor;
            shadowrun_menu_phase = 2U;
        }
    }
    shadowrun_menu_supported = 1;
}
