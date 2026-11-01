/* Source-bound procedural slice: context 2, Stoker sign prompt selection.
 * Inputs are the two field identifiers and the original signed phase byte.
 * Outputs are original-source resource references, not copied assets. */
typedef unsigned char u8;
typedef unsigned long u32;
u8 shadowrun_interaction_context;
u8 shadowrun_interaction_target;
u8 shadowrun_interaction_phase;
u8 shadowrun_interaction_supported;
u8 shadowrun_interaction_dialogue_id;
u32 shadowrun_interaction_prompt_offset;
u32 shadowrun_interaction_portrait_offset;

void shadowrun_select_interaction(void) {
    shadowrun_interaction_supported = 0;
    if (shadowrun_interaction_context != 2 || shadowrun_interaction_target != 2) return;
    shadowrun_interaction_supported = 1;
    shadowrun_interaction_dialogue_id = 20;
    shadowrun_interaction_portrait_offset = 0x121fa0UL;
    if (shadowrun_interaction_phase == 0)
        shadowrun_interaction_prompt_offset = 0xf4aa0UL;
    else if (shadowrun_interaction_phase & 0x80U)
        shadowrun_interaction_prompt_offset = 0xf4aecUL;
    else
        shadowrun_interaction_prompt_offset = 0xf4af4UL;
}

/* Original collision-word/event-number projection at $B858..$B866.
 * This is only a number derivation, not event dispatch or a Stoker decision. */
typedef unsigned int u16;
u16 shadowrun_interaction_raw_collision;
u16 shadowrun_interaction_actor_collision;
u16 shadowrun_interaction_event_index;
void shadowrun_decode_collision_event(void) {
    shadowrun_interaction_actor_collision = shadowrun_interaction_raw_collision;
    shadowrun_interaction_event_index = shadowrun_interaction_raw_collision & 31U;
}

/* Count signed-negative collision probes before field event handling.
 * A passing gate does not identify or execute a particular scene event. */
u8 shadowrun_interaction_corner0;
u8 shadowrun_interaction_corner1;
u8 shadowrun_interaction_corner2;
u8 shadowrun_interaction_corner3;
u8 shadowrun_interaction_negative_count;
u8 shadowrun_interaction_corner_gate;
void shadowrun_check_event_corners(void) {
    shadowrun_interaction_negative_count = 0;
    if (shadowrun_interaction_corner0 & 128U) shadowrun_interaction_negative_count++;
    if (shadowrun_interaction_corner1 & 128U) shadowrun_interaction_negative_count++;
    if (shadowrun_interaction_corner2 & 128U) shadowrun_interaction_negative_count++;
    if (shadowrun_interaction_corner3 & 128U) shadowrun_interaction_negative_count++;
    shadowrun_interaction_corner_gate = 0;
    if (shadowrun_interaction_negative_count >= 2) shadowrun_interaction_corner_gate = 1;
}

/* $BA3A..$BA7C: event target store and branch before activity dispatch. */
u16 shadowrun_interaction_scene_mode;
u16 shadowrun_interaction_event_mode;
u16 shadowrun_interaction_reaction_flag;
u8 shadowrun_interaction_visited_flag;
u8 shadowrun_interaction_source_target;
u8 shadowrun_interaction_source_proceeds;
void shadowrun_interaction_source_branch(void) {
    shadowrun_interaction_source_target = (u8)shadowrun_interaction_event_index;
    shadowrun_interaction_source_proceeds = 1;
    if (shadowrun_interaction_event_mode == 0 || shadowrun_interaction_scene_mode == 20) return;
    if (shadowrun_interaction_event_mode != 2 || shadowrun_interaction_event_index != 0) return;
    if (shadowrun_interaction_reaction_flag != 0 || shadowrun_interaction_visited_flag != 0)
        shadowrun_interaction_source_proceeds = 0;
}

/* $BA82..$BA9E: only the carry-set branch's three source writes. The carry
 * comes from an unmodeled activity routine and is an explicit input. */
u8 shadowrun_interaction_dispatch_carry;
u16 shadowrun_interaction_transition_flag;
u16 shadowrun_interaction_transition_timer;
u16 shadowrun_interaction_trigger_busy;
void shadowrun_interaction_source_transition(void) {
    if (!shadowrun_interaction_dispatch_carry) return;
    shadowrun_interaction_transition_flag = 0xffffU;
    shadowrun_interaction_transition_timer = 16U;
    shadowrun_interaction_trigger_busy = 0xffffU;
}

/* Narrow evidence-backed Stoker request, with unknown routes refused. This
 * is not a lift of the activity dispatcher's opaque side effects. */
u8 shadowrun_interaction_actor_flags;
u8 shadowrun_interaction_event_latch;
u8 shadowrun_interaction_requested;
void shadowrun_request_stoker(void) {
    shadowrun_interaction_requested = 0;
    if (shadowrun_interaction_trigger_busy != 0 || (shadowrun_interaction_event_latch & 32U)) return;
    if (!(shadowrun_interaction_actor_flags & 2U) || (shadowrun_interaction_actor_flags & 80U)) return;
    if (shadowrun_interaction_scene_mode != 2 || shadowrun_interaction_event_mode != 0 ||
        shadowrun_interaction_reaction_flag != 0 || shadowrun_interaction_context != 2 ||
        shadowrun_interaction_phase != 0 || shadowrun_interaction_raw_collision != 0xffc2U || !shadowrun_interaction_dispatch_carry) return;
    shadowrun_check_event_corners();
    if (!shadowrun_interaction_corner_gate) return;
    shadowrun_decode_collision_event();
    shadowrun_interaction_source_branch();
    if (!shadowrun_interaction_source_proceeds || shadowrun_interaction_source_target != 2) return;
    shadowrun_interaction_target = shadowrun_interaction_source_target;
    shadowrun_select_interaction();
    if (!shadowrun_interaction_supported) return;
    shadowrun_interaction_event_latch |= 32U;
    shadowrun_interaction_source_transition();
    shadowrun_interaction_requested = 1;
}

/* Target-only projection of one observed A->B->A path. Modes 1..4 are sign,
 * manager choice, farewell, and wait for action release; 0 is field. Other
 * choices report unsupported rather than inventing a quest result. */
u8 shadowrun_stoker_ui_mode;
u8 shadowrun_stoker_ui_previous;
u8 shadowrun_stoker_ui_unsupported;
void shadowrun_stoker_ui_begin(u8 pad) {
    shadowrun_stoker_ui_mode = 1;
    shadowrun_stoker_ui_previous = pad;
    shadowrun_stoker_ui_unsupported = 0;
}
void shadowrun_stoker_ui_tick(u8 pad) {
    u8 pressed;
    pressed = (u8)((pad ^ shadowrun_stoker_ui_previous) & pad);
    shadowrun_stoker_ui_previous = pad;
    shadowrun_stoker_ui_unsupported = 0;
    if (shadowrun_stoker_ui_mode == 1) {
        if (pressed & 64U) shadowrun_stoker_ui_mode = 2;
        else if (pressed & 48U) shadowrun_stoker_ui_unsupported = 1;
    } else if (shadowrun_stoker_ui_mode == 2) {
        if (pressed & 16U) shadowrun_stoker_ui_mode = 3;
        else if (pressed & 96U) shadowrun_stoker_ui_unsupported = 1;
    } else if (shadowrun_stoker_ui_mode == 3) {
        if (pressed & 64U) shadowrun_stoker_ui_mode = 4;
        else if (pressed & 48U) shadowrun_stoker_ui_unsupported = 1;
    } else if (shadowrun_stoker_ui_mode == 4) {
        if (!(pad & 112U)) shadowrun_stoker_ui_mode = 0;
    }
}
