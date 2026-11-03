/* Independent transcription of bounded original 68000 operations. The caller
 * must validate the field-command cursor and item dispatch before invoking. */
typedef unsigned char u8;
u8 shadowrun_inventory_row;
u8 shadowrun_inventory_column;
u8 shadowrun_inventory_slot;
u8 shadowrun_inventory_cell0;
u8 shadowrun_inventory_cell1;
u8 shadowrun_inventory_cell2;
u8 shadowrun_inventory_cell3;
u8 shadowrun_inventory_cell4;
u8 shadowrun_inventory_cell5;
u8 shadowrun_inventory_cell6;
u8 shadowrun_inventory_cell7;
u8 shadowrun_inventory_item;
u8 shadowrun_inventory_valid;
void shadowrun_inventory_select(void) {
    shadowrun_inventory_valid = 0;
    if (shadowrun_inventory_row > 3 || shadowrun_inventory_column > 1) return;
    shadowrun_inventory_slot = shadowrun_inventory_row * 2U + shadowrun_inventory_column;
    if (shadowrun_inventory_slot == 0) shadowrun_inventory_item = shadowrun_inventory_cell0;
    if (shadowrun_inventory_slot == 1) shadowrun_inventory_item = shadowrun_inventory_cell1;
    if (shadowrun_inventory_slot == 2) shadowrun_inventory_item = shadowrun_inventory_cell2;
    if (shadowrun_inventory_slot == 3) shadowrun_inventory_item = shadowrun_inventory_cell3;
    if (shadowrun_inventory_slot == 4) shadowrun_inventory_item = shadowrun_inventory_cell4;
    if (shadowrun_inventory_slot == 5) shadowrun_inventory_item = shadowrun_inventory_cell5;
    if (shadowrun_inventory_slot == 6) shadowrun_inventory_item = shadowrun_inventory_cell6;
    if (shadowrun_inventory_slot == 7) shadowrun_inventory_item = shadowrun_inventory_cell7;
    shadowrun_inventory_valid = 1;
}
/* $1219C: caller has already dispatched to the armor branch. This does not
 * establish whether a particular item is legal or clear any other slot. */
u8 shadowrun_inventory_equipped_armor;
u8 shadowrun_inventory_selected_phase;
void shadowrun_inventory_armor_branch(void) {
    if (shadowrun_inventory_equipped_armor) {
        shadowrun_inventory_equipped_armor = 0;
        shadowrun_inventory_selected_phase = 0;
    } else {
        shadowrun_inventory_equipped_armor = shadowrun_inventory_item - 43U;
        shadowrun_inventory_selected_phase = shadowrun_inventory_equipped_armor;
    }
}
