/*
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Canonical bounded AGI decode for native execution and stopped inspection.
 * This module describes encodings; it neither executes nor resolves variables.
 */
#include "decode.h"

typedef struct AgiOpcode {
    const char *mnemonic, *operation;
    AgiEffectClass effect;
    AgiDecodeProfile minimum_profile;
    bool native;
    uint32_t size, operand_count;
    AgiDecodedOperand operands[AGI_DECODE_OPERANDS_MAX];
} AgiOpcode;

/* One descriptor table holds AGI 2.917 names, extents and typed operands.
 * Encoding facts: fDisBull agi_layout.py/agi_scenes.py at
 * 1b27110bb43fe91fec5d09b4cffa7227771cb5e9. Operand roles were checked against
 * ScummVM f7403b6efaae2f033e8abea80b3fb6bee5303369 op_cmd.cpp/op_test.cpp,
 * including cases where its display table has misleading parameter letters.
 * Only format facts were used, not upstream implementation code.
 * OPCODE_COVERAGE.md records the scope and contextual trace.on boundary.
 */
#define ARG(role_, kind_, width_, access_) \
    { .role = role_, .kind = AGI_OPERAND_##kind_, .width = width_, \
      .access = AGI_ACCESS_##access_ }
#define VAR(role_, access_) ARG(role_, VARIABLE, 8, access_)
#define IMM(role_) ARG(role_, U8, 8, READ)
#define ACTOR ARG("actor", ACTOR, 8, REFERENCE)
#define ORD(role_, kind_) ARG(role_, kind_, 8, REFERENCE)
#define FLAG(access_) ARG("flag", FLAG, 1, access_)
#define STRING(role_, access_) ARG(role_, STRING, 8, access_)
#define CONTROLLER(access_) ARG("controller", CONTROLLER, 8, access_)
#define OP(name_, operation_, effect_, profile_, size_, count_, ...) \
    { .mnemonic = name_, .operation = operation_, \
      .effect = AGI_EFFECT_##effect_, \
      .minimum_profile = AGI_DECODE_##profile_, .native = true, .size = size_, \
      .operand_count = count_, .operands = { __VA_ARGS__ } }

#define META(name_, operation_, effect_, size_, count_, ...) \
    { .mnemonic = name_, .operation = operation_, \
      .effect = AGI_EFFECT_##effect_, .size = size_, \
      .operand_count = count_, .operands = { __VA_ARGS__ } }

static const AgiOpcode actions[256] = {
    [0] = OP("return", "control.return", CONTROL, SCALAR, 1, 0, { 0 }),
    [1] = OP("increment", "scalar.increment", SCALAR, SCALAR, 2, 1,
             VAR("destination", READ_WRITE)),
    [2] = OP("decrement", "scalar.decrement", SCALAR, SCALAR, 2, 1,
             VAR("destination", READ_WRITE)),
    [3] = OP("assignn", "scalar.assign", SCALAR, SCALAR, 3, 2,
             VAR("destination", WRITE), IMM("value")),
    [4] = OP("assignv", "scalar.assign", SCALAR, SCALAR, 3, 2,
             VAR("destination", WRITE), VAR("value", READ)),
    [5] = OP("addn", "scalar.add", SCALAR, SCALAR, 3, 2,
             VAR("destination", READ_WRITE), IMM("value")),
    [6] = OP("addv", "scalar.add", SCALAR, SCALAR, 3, 2,
             VAR("destination", READ_WRITE), VAR("value", READ)),
    [7] = OP("subn", "scalar.subtract", SCALAR, SCALAR, 3, 2,
             VAR("destination", READ_WRITE), IMM("value")),
    [8] = OP("subv", "scalar.subtract", SCALAR, SCALAR, 3, 2,
             VAR("destination", READ_WRITE), VAR("value", READ)),
    [9] = META("lindirectv", "scalar.assign_indirect", SCALAR, 3, 2,
               VAR("destination_pointer", READ), VAR("value", READ)),
    [10] = META("rindirect", "scalar.read_indirect", SCALAR, 3, 2,
                VAR("destination", WRITE), VAR("source_pointer", READ)),
    [11] = META("lindirectn", "scalar.assign_indirect", SCALAR, 3, 2,
                VAR("destination_pointer", READ), IMM("value")),
    [12] = OP("set", "flag.set", FLAG, SCALAR, 2, 1, FLAG(WRITE)),
    [13] = OP("reset", "flag.reset", FLAG, SCALAR, 2, 1, FLAG(WRITE)),
    [14] = OP("toggle", "flag.toggle", FLAG, SCALAR, 2, 1, FLAG(READ_WRITE)),
    [15] = META("set.v", "flag.set_indirect", FLAG, 2, 1, VAR("flag", READ)),
    [16] = META("reset.v", "flag.reset_indirect", FLAG, 2, 1, VAR("flag", READ)),
    [17] = META("toggle.v", "flag.toggle_indirect", FLAG, 2, 1, VAR("flag", READ)),
    [18] = META("new.room", "control.new_room", CONTROL, 2, 1,
                ORD("room", ROOM)),
    [19] = META("new.room.v", "control.new_room", CONTROL, 2, 1,
                VAR("room", READ)),
    [20] = META("load.logics", "resource.load_logic", RESOURCE, 2, 1,
                ORD("logic", LOGIC)),
    [21] = META("load.logics.v", "resource.load_logic", RESOURCE, 2, 1,
                VAR("logic", READ)),
    [22] = META("call", "control.call", CONTROL, 2, 1, ORD("logic", LOGIC)),
    [23] = META("call.v", "control.call", CONTROL, 2, 1, VAR("logic", READ)),
    [24] = META("load.pic", "resource.load_picture", RESOURCE, 2, 1,
                VAR("picture", READ)),
    [25] = META("draw.pic", "scene.draw_picture", HOST, 2, 1,
                VAR("picture", READ)),
    [26] = META("show.pic", "scene.show_picture", HOST, 1, 0, { 0 }),
    [27] = META("discard.pic", "resource.discard_picture", RESOURCE, 2, 1,
                VAR("picture", READ)),
    [28] = META("overlay.pic", "scene.overlay_picture", HOST, 2, 1,
                VAR("picture", READ)),
    [29] = META("show.pri.screen", "scene.show_priority", HOST, 1, 0, { 0 }),
    [30] = OP("load.view", "resource.load_view", RESOURCE, BINDING, 2, 1,
              ORD("view", VIEW)),
    [31] = OP("load.view.v", "resource.load_view", RESOURCE, BINDING, 2, 1,
              VAR("view", READ)),
    [32] = META("discard.view", "resource.discard_view", RESOURCE, 2, 1,
                ORD("view", VIEW)),
    [33] = OP("animate.obj", "object.animate", ACTOR, BINDING, 2, 1, ACTOR),
    [34] = META("unanimate.all", "object.unanimate_all", ACTOR, 1, 0, { 0 }),
    [35] = OP("draw", "object.draw", HOST, INTENT, 2, 1, ACTOR),
    [36] = META("erase", "object.erase", HOST, 2, 1, ACTOR),
    [37] = OP("position", "object.position", ACTOR, SCALAR, 4, 3,
              ACTOR, IMM("x"), IMM("y")),
    [38] = OP("position.v", "object.position", ACTOR, SCALAR, 4, 3,
              ACTOR, VAR("x", READ), VAR("y", READ)),
    [39] = OP("get.posn", "object.get_position", ACTOR, SCALAR, 4, 3,
              ACTOR, VAR("x", WRITE), VAR("y", WRITE)),
    [40] = META("reposition", "object.reposition", ACTOR, 4, 3,
                ACTOR, VAR("delta_x", READ), VAR("delta_y", READ)),
    [41] = OP("set.view", "object.set_view", ACTOR, BINDING, 3, 2,
              ACTOR, ORD("view", VIEW)),
    [42] = OP("set.view.v", "object.set_view", ACTOR, BINDING, 3, 2,
              ACTOR, VAR("view", READ)),
    [43] = OP("set.loop", "object.set_loop", ACTOR, BINDING, 3, 2,
              ACTOR, ORD("loop", LOOP)),
    [44] = OP("set.loop.v", "object.set_loop", ACTOR, BINDING, 3, 2,
              ACTOR, VAR("loop", READ)),
    [45] = META("fix.loop", "object.fix_loop", ACTOR, 2, 1, ACTOR),
    [46] = META("release.loop", "object.release_loop", ACTOR, 2, 1, ACTOR),
    [47] = OP("set.cel", "object.set_cel", ACTOR, BINDING, 3, 2,
              ACTOR, ORD("cel", CEL)),
    [48] = OP("set.cel.v", "object.set_cel", ACTOR, BINDING, 3, 2,
              ACTOR, VAR("cel", READ)),
    [49] = META("last.cel", "object.last_cel", ACTOR, 3, 2,
                ACTOR, VAR("destination", WRITE)),
    [50] = META("current.cel", "object.current_cel", ACTOR, 3, 2,
                ACTOR, VAR("destination", WRITE)),
    [51] = META("current.loop", "object.current_loop", ACTOR, 3, 2,
                ACTOR, VAR("destination", WRITE)),
    [52] = META("current.view", "object.current_view", ACTOR, 3, 2,
                ACTOR, VAR("destination", WRITE)),
    [53] = META("number.of.loops", "object.number_of_loops", ACTOR, 3, 2,
                ACTOR, VAR("destination", WRITE)),
    [54] = META("set.priority", "object.set_priority", ACTOR, 3, 2,
                ACTOR, IMM("priority")),
    [55] = META("set.priority.v", "object.set_priority", ACTOR, 3, 2,
                ACTOR, VAR("priority", READ)),
    [56] = META("release.priority", "object.release_priority", ACTOR, 2, 1, ACTOR),
    [57] = META("get.priority", "object.get_priority", ACTOR, 3, 2,
                ACTOR, VAR("destination", WRITE)),
    [58] = META("stop.update", "object.stop_update", ACTOR, 2, 1, ACTOR),
    [59] = META("start.update", "object.start_update", ACTOR, 2, 1, ACTOR),
    [60] = META("force.update", "object.force_update", ACTOR, 2, 1, ACTOR),
    [61] = META("ignore.horizon", "object.ignore_horizon", ACTOR, 2, 1, ACTOR),
    [62] = META("observe.horizon", "object.observe_horizon", ACTOR, 2, 1, ACTOR),
    [63] = META("set.horizon", "scene.set_horizon", HOST, 2, 1, IMM("horizon")),
    [64] = META("object.on.water", "object.on_water", ACTOR, 2, 1, ACTOR),
    [65] = META("object.on.land", "object.on_land", ACTOR, 2, 1, ACTOR),
    [66] = META("object.on.anything", "object.on_anything", ACTOR, 2, 1, ACTOR),
    [67] = META("ignore.objs", "object.ignore_objects", ACTOR, 2, 1, ACTOR),
    [68] = META("observe.objs", "object.observe_objects", ACTOR, 2, 1, ACTOR),
    [69] = META("distance", "object.distance", ACTOR, 4, 3,
                ACTOR, ARG("other_actor", ACTOR, 8, REFERENCE),
                VAR("destination", WRITE)),
    [70] = OP("stop.cycling", "object.stop_cycling", ACTOR, INTENT, 2, 1,
              ACTOR),
    [71] = OP("start.cycling", "object.start_cycling", ACTOR, INTENT, 2, 1,
              ACTOR),
    [72] = META("normal.cycle", "object.normal_cycle", ACTOR, 2, 1, ACTOR),
    [73] = META("end.of.loop", "object.end_of_loop", ACTOR, 3, 2,
                ACTOR, FLAG(WRITE)),
    [74] = META("reverse.cycle", "object.reverse_cycle", ACTOR, 2, 1, ACTOR),
    [75] = META("reverse.loop", "object.reverse_loop", ACTOR, 3, 2,
                ACTOR, FLAG(WRITE)),
    [76] = META("cycle.time", "object.cycle_time", ACTOR, 3, 2,
                ACTOR, VAR("cycle_time", READ)),
    [77] = META("stop.motion", "object.stop_motion", ACTOR, 2, 1, ACTOR),
    [78] = META("start.motion", "object.start_motion", ACTOR, 2, 1, ACTOR),
    [79] = META("step.size", "object.step_size", ACTOR, 3, 2,
                ACTOR, VAR("step_size", READ)),
    [80] = META("step.time", "object.step_time", ACTOR, 3, 2,
                ACTOR, VAR("step_time", READ)),
    [81] = META("move.obj", "object.move", ACTOR, 6, 5,
                ACTOR, IMM("x"), IMM("y"), IMM("step_size"), FLAG(WRITE)),
    [82] = META("move.obj.v", "object.move", ACTOR, 6, 5,
                ACTOR, VAR("x", READ), VAR("y", READ),
                VAR("step_size", READ), FLAG(WRITE)),
    [83] = META("follow.ego", "object.follow_ego", ACTOR, 4, 3,
                ACTOR, IMM("step_size"), FLAG(WRITE)),
    [84] = META("wander", "object.wander", ACTOR, 2, 1, ACTOR),
    [85] = META("normal.motion", "object.normal_motion", ACTOR, 2, 1, ACTOR),
    [86] = META("set.dir", "object.set_direction", ACTOR, 3, 2,
                ACTOR, VAR("direction", READ)),
    [87] = META("get.dir", "object.get_direction", ACTOR, 3, 2,
                ACTOR, VAR("destination", WRITE)),
    [88] = META("ignore.blocks", "object.ignore_blocks", ACTOR, 2, 1, ACTOR),
    [89] = META("observe.blocks", "object.observe_blocks", ACTOR, 2, 1, ACTOR),
    [90] = META("block", "scene.block", HOST, 5, 4,
                IMM("x1"), IMM("y1"), IMM("x2"), IMM("y2")),
    [91] = META("unblock", "scene.unblock", HOST, 1, 0, { 0 }),
    [92] = META("get", "inventory.get", HOST, 2, 1,
                ORD("inventory_object", INVENTORY_OBJECT)),
    [93] = META("get.v", "inventory.get", HOST, 2, 1,
                VAR("inventory_object", READ)),
    [94] = META("drop", "inventory.drop", HOST, 2, 1,
                ORD("inventory_object", INVENTORY_OBJECT)),
    /* cmdPut reads the second byte as a variable despite the upstream
     * display table's "nn" shorthand. See OPCODE_COVERAGE.md. */
    [95] = META("put", "inventory.put", HOST, 3, 2,
                ORD("inventory_object", INVENTORY_OBJECT), VAR("room", READ)),
    [96] = META("put.v", "inventory.put", HOST, 3, 2,
                VAR("inventory_object", READ), VAR("room", READ)),
    [97] = META("get.room.v", "inventory.get_room", HOST, 3, 2,
                VAR("inventory_object", READ), VAR("destination", WRITE)),
    [98] = META("load.sound", "resource.load_sound", RESOURCE, 2, 1,
                ORD("sound", SOUND)),
    [99] = META("sound", "scene.play_sound", HOST, 3, 2,
                ORD("sound", SOUND), FLAG(WRITE)),
    [100] = META("stop.sound", "scene.stop_sound", HOST, 1, 0, { 0 }),
    [101] = META("print", "scene.print", HOST, 2, 1, ORD("message", MESSAGE)),
    [102] = META("print.v", "scene.print", HOST, 2, 1, VAR("message", READ)),
    [103] = META("display", "scene.display", HOST, 4, 3,
                 IMM("row"), IMM("column"), ORD("message", MESSAGE)),
    [104] = META("display.v", "scene.display", HOST, 4, 3,
                 VAR("row", READ), VAR("column", READ), VAR("message", READ)),
    [105] = META("clear.lines", "scene.clear_lines", HOST, 4, 3,
                 IMM("first_row"), IMM("last_row"), IMM("color")),
    [106] = META("text.screen", "scene.text_screen", HOST, 1, 0, { 0 }),
    [107] = META("graphics", "scene.graphics", HOST, 1, 0, { 0 }),
    [108] = META("set.cursor.char", "scene.set_cursor_char", HOST, 2, 1,
                 ORD("message", MESSAGE)),
    [109] = META("set.text.attribute", "scene.set_text_attribute", HOST, 3, 2,
                 IMM("foreground"), IMM("background")),
    [110] = META("shake.screen", "scene.shake_screen", HOST, 2, 1,
                 IMM("count")),
    [111] = META("configure.screen", "scene.configure_screen", HOST, 4, 3,
                 IMM("picture_row"), IMM("input_row"), IMM("status_row")),
    [112] = META("status.line.on", "scene.status_line_on", HOST, 1, 0, { 0 }),
    [113] = META("status.line.off", "scene.status_line_off", HOST, 1, 0, { 0 }),
    [114] = META("set.string", "string.assign", HOST, 3, 2,
                 STRING("destination", WRITE), ORD("message", MESSAGE)),
    [115] = META("get.string", "string.read_input", HOST, 6, 5,
                 STRING("destination", WRITE), ORD("message", MESSAGE),
                 IMM("row"), IMM("column"), IMM("maximum_length")),
    [116] = META("word.to.string", "string.from_word", HOST, 3, 2,
                 STRING("destination", WRITE), IMM("parsed_word_index")),
    [117] = META("parse", "parser.parse", HOST, 2, 1,
                 STRING("string", READ)),
    [118] = META("get.num", "input.get_number", HOST, 3, 2,
                 ORD("message", MESSAGE), VAR("destination", WRITE)),
    [119] = META("prevent.input", "input.prevent", HOST, 1, 0, { 0 }),
    [120] = META("accept.input", "input.accept", HOST, 1, 0, { 0 }),
    [121] = META("set.key", "input.set_key", HOST, 4, 3,
                 IMM("ascii"), IMM("scan_code"), CONTROLLER(WRITE)),
    [122] = META("add.to.pic", "scene.add_to_picture", HOST, 8, 7,
                 ORD("view", VIEW), ORD("loop", LOOP), ORD("cel", CEL),
                 IMM("x"), IMM("y"), IMM("priority"), IMM("control")),
    [123] = META("add.to.pic.v", "scene.add_to_picture", HOST, 8, 7,
                 VAR("view", READ), VAR("loop", READ), VAR("cel", READ),
                 VAR("x", READ), VAR("y", READ), VAR("priority", READ),
                 VAR("control", READ)),
    [124] = META("status", "inventory.show_status", HOST, 1, 0, { 0 }),
    [125] = META("save.game", "system.save_game", HOST, 1, 0, { 0 }),
    [126] = META("restore.game", "system.restore_game", CONTROL, 1, 0, { 0 }),
    [127] = META("init.disk", "system.init_disk", HOST, 1, 0, { 0 }),
    [128] = META("restart.game", "system.restart_game", CONTROL, 1, 0, { 0 }),
    [129] = META("show.obj", "scene.show_object", HOST, 2, 1, ORD("view", VIEW)),
    [130] = META("random", "scalar.random", SCALAR, 4, 3,
                 IMM("minimum"), IMM("maximum"), VAR("destination", WRITE)),
    [131] = META("program.control", "input.program_control", HOST, 1, 0, { 0 }),
    [132] = META("player.control", "input.player_control", HOST, 1, 0, { 0 }),
    [133] = META("obj.status.v", "debug.object_status", HOST, 2, 1,
                 VAR("actor", READ)),
    [134] = META("quit", "system.quit", CONTROL, 2, 1, IMM("without_prompt")),
    [135] = META("show.mem", "debug.show_memory", HOST, 1, 0, { 0 }),
    [136] = META("pause", "system.pause", HOST, 1, 0, { 0 }),
    [137] = META("echo.line", "input.echo_line", HOST, 1, 0, { 0 }),
    [138] = META("cancel.line", "input.cancel_line", HOST, 1, 0, { 0 }),
    [139] = META("init.joy", "input.init_joystick", HOST, 1, 0, { 0 }),
    [140] = META("toggle.monitor", "scene.toggle_monitor", HOST, 1, 0, { 0 }),
    [141] = META("version", "debug.show_version", HOST, 1, 0, { 0 }),
    [142] = META("script.size", "resource.script_size", RESOURCE, 2, 1,
                 IMM("capacity")),
    [143] = META("set.game.id", "system.set_game_id", HOST, 2, 1,
                 ORD("message", MESSAGE)),
    [144] = META("log", "debug.log", HOST, 2, 1, ORD("message", MESSAGE)),
    [145] = META("set.scan.start", "control.set_scan_start", CONTROL, 1, 0, { 0 }),
    [146] = META("reset.scan.start", "control.reset_scan_start", CONTROL, 1, 0, { 0 }),
    [147] = META("reposition.to", "object.reposition_to", ACTOR, 4, 3,
                 ACTOR, IMM("x"), IMM("y")),
    [148] = META("reposition.to.v", "object.reposition_to", ACTOR, 4, 3,
                 ACTOR, VAR("x", READ), VAR("y", READ)),
    [149] = META("trace.on", "debug.trace_on", HOST, 1, 0, { 0 }),
    [150] = META("trace.info", "debug.trace_info", HOST, 4, 3,
                 ORD("logic", LOGIC), IMM("first_row"), IMM("row_count")),
    [151] = META("print.at", "scene.print_at", HOST, 5, 4,
                 ORD("message", MESSAGE), IMM("row"), IMM("column"), IMM("width")),
    [152] = META("print.at.v", "scene.print_at", HOST, 5, 4,
                 VAR("message", READ), IMM("row"), IMM("column"), IMM("width")),
    [153] = META("discard.view.v", "resource.discard_view", RESOURCE, 2, 1,
                 VAR("view", READ)),
    [154] = META("clear.text.rect", "scene.clear_text_rect", HOST, 6, 5,
                 IMM("first_row"), IMM("first_column"), IMM("last_row"),
                 IMM("last_column"), IMM("color")),
    /* The 2.917 handler is a no-op; operands are retained as the command's
     * nominal coordinates, not claimed to change screen geometry. */
    [155] = META("set.upper.left", "scene.set_upper_left", HOST, 3, 2,
                 IMM("row"), IMM("column")),
    [156] = META("set.menu", "menu.add", HOST, 2, 1, ORD("message", MESSAGE)),
    [157] = META("set.menu.item", "menu.add_item", HOST, 3, 2,
                 ORD("message", MESSAGE), CONTROLLER(REFERENCE)),
    [158] = META("submit.menu", "menu.submit", HOST, 1, 0, { 0 }),
    [159] = META("enable.item", "menu.enable_item", HOST, 2, 1,
                 CONTROLLER(REFERENCE)),
    [160] = META("disable.item", "menu.disable_item", HOST, 2, 1,
                 CONTROLLER(REFERENCE)),
    [161] = META("menu.input", "menu.input", HOST, 1, 0, { 0 }),
    [162] = META("show.obj.v", "scene.show_object", HOST, 2, 1,
                 VAR("view", READ)),
    [163] = META("open.dialogue", "scene.open_dialogue", HOST, 1, 0, { 0 }),
    [164] = META("close.dialogue", "scene.close_dialogue", HOST, 1, 0, { 0 }),
    [165] = META("mul.n", "scalar.multiply", SCALAR, 3, 2,
                 VAR("destination", READ_WRITE), IMM("value")),
    [166] = META("mul.v", "scalar.multiply", SCALAR, 3, 2,
                 VAR("destination", READ_WRITE), VAR("value", READ)),
    [167] = META("div.n", "scalar.divide", SCALAR, 3, 2,
                 VAR("destination", READ_WRITE), IMM("value")),
    [168] = META("div.v", "scalar.divide", SCALAR, 3, 2,
                 VAR("destination", READ_WRITE), VAR("value", READ)),
    [169] = META("close.window", "scene.close_window", HOST, 1, 0, { 0 }),
    [170] = META("set.simple", "system.set_simple", HOST, 2, 1,
                 STRING("description", READ)),
    [171] = META("push.script", "resource.push_script", RESOURCE, 1, 0, { 0 }),
    [172] = META("pop.script", "resource.pop_script", RESOURCE, 1, 0, { 0 }),
    [173] = META("hold.key", "input.hold_key", HOST, 1, 0, { 0 }),
    [0xfe] = OP("goto", "control.goto", CONTROL, SCALAR, 3, 1,
                ARG("displacement", S16, 16, READ)),
    [0xff] = OP("if", "control.if", CONTROL, SCALAR, 0, 1,
                ARG("displacement", U16, 16, READ)),
};

static const AgiOpcode predicates[19] = {
    [0] = META("false", "", CONTROL, 1, 0, { 0 }),
    [1] = OP("equaln", "", CONTROL, SCALAR, 3, 2,
             VAR("left", READ), IMM("right")),
    [2] = OP("equalv", "", CONTROL, SCALAR, 3, 2,
             VAR("left", READ), VAR("right", READ)),
    [3] = OP("lessn", "", CONTROL, SCALAR, 3, 2,
             VAR("left", READ), IMM("right")),
    [4] = OP("lessv", "", CONTROL, SCALAR, 3, 2,
             VAR("left", READ), VAR("right", READ)),
    [5] = OP("greatern", "", CONTROL, SCALAR, 3, 2,
             VAR("left", READ), IMM("right")),
    [6] = OP("greaterv", "", CONTROL, SCALAR, 3, 2,
             VAR("left", READ), VAR("right", READ)),
    [7] = OP("isset", "", CONTROL, SCALAR, 2, 1, FLAG(READ)),
    [8] = META("isset.v", "", CONTROL, 2, 1, VAR("flag", READ)),
    [9] = META("has", "", CONTROL, 2, 1,
               ORD("inventory_object", INVENTORY_OBJECT)),
    [10] = META("obj.in.room", "", CONTROL, 3, 2,
                ORD("inventory_object", INVENTORY_OBJECT), VAR("room", READ)),
    [11] = META("posn", "", CONTROL, 6, 5,
                ACTOR, IMM("x1"), IMM("y1"), IMM("x2"), IMM("y2")),
    [12] = META("controller", "", CONTROL, 2, 1, CONTROLLER(READ)),
    [13] = META("have.key", "", CONTROL, 1, 0, { 0 }),
    [14] = META("said", "", CONTROL, 0, 0, { 0 }),
    [15] = META("compare.strings", "", CONTROL, 3, 2,
                STRING("left_string", READ), STRING("right_string", READ)),
    [16] = META("obj.in.box", "", CONTROL, 6, 5,
                ACTOR, IMM("x1"), IMM("y1"), IMM("x2"), IMM("y2")),
    [17] = META("center.posn", "", CONTROL, 6, 5,
                ACTOR, IMM("x1"), IMM("y1"), IMM("x2"), IMM("y2")),
    [18] = META("right.posn", "", CONTROL, 6, 5,
                ACTOR, IMM("x1"), IMM("y1"), IMM("x2"), IMM("y2")),
};

#undef META
#undef OP
#undef CONTROLLER
#undef STRING
#undef FLAG
#undef ORD
#undef ACTOR
#undef IMM
#undef VAR
#undef ARG

static bool agi_extent(uint32_t code_size, uint32_t pc, uint32_t size)
{
    return pc < code_size && size <= code_size - pc;
}

static uint32_t agi_byte(AgiDecodeRead read, void *opaque,
                         AgiDecodedInstruction *out, uint32_t pc)
{
    uint8_t value = read(opaque, pc);
    out->bytes[pc - out->pc] = value;
    return value;
}

static bool agi_decode_fault(AgiDecodedInstruction *out, AgiFault fault)
{
    out->fault = fault;
    return false;
}

static void agi_edge(AgiDecodedInstruction *out, AgiSuccessorKind kind,
                      int64_t pc, uint32_t code_size)
{
    out->successors[out->successor_count++] = (AgiDecodedSuccessor) {
        .kind = kind, .pc = pc, .in_range = pc >= 0 && pc < code_size,
    };
}

/* One framing parser with distinct admission limits. EXECUTION checks the
 * original byte bound before every token and rejects unimplemented predicates
 * before inspecting their payload. STRUCTURAL may describe those encodings,
 * but never feeds them to the native evaluator.
 */
static bool agi_decode_if(AgiDecodeRead read, void *opaque, uint32_t code_size,
                          AgiDecodePurpose purpose, bool runtime,
                          AgiDecodedInstruction *out)
{
    const bool structural = purpose == AGI_DECODE_STRUCTURAL || runtime;
    const uint32_t byte_limit = structural ? AGI_DECODE_BYTES_MAX : AGI_INSN_MAX;
    const uint32_t predicate_limit = structural ? AGI_DECODE_PREDICATES_MAX :
                                                AGI_EXEC_PREDICATES_MAX;
    uint32_t at = out->pc + 1, tests = 0, group_tests = 0;
    uint32_t op, token_pc, i, skip, count, payload_size, words = 0, value;
    bool in_or = false, negate = false, native_admitted = true;
    AgiDecodedCondition *token;
    AgiDecodedOperand *operand;
    const AgiOpcode *predicate;

    for (;;) {
        if (at - out->pc >= byte_limit - 2) {
            return agi_decode_fault(out, AGI_FAULT_CONDITION_LIMIT);
        }
        if (!runtime && at - out->pc >= AGI_INSN_MAX - 2) {
            native_admitted = false;
        }
        if (!agi_extent(code_size, at, 1)) {
            return agi_decode_fault(out, AGI_FAULT_TRUNCATED);
        }
        token_pc = at;
        op = agi_byte(read, opaque, out, at++);
        if (op == 0xff) {
            if (in_or || negate) {
                return agi_decode_fault(out, AGI_FAULT_CONDITION);
            }
            break;
        }
        if (op == 0xfd) {
            if (negate) {
                return agi_decode_fault(out, AGI_FAULT_CONDITION);
            }
            if (out->condition_count == AGI_DECODE_TOKENS_MAX) {
                return agi_decode_fault(out, AGI_FAULT_CONDITION_LIMIT);
            }
            out->conditions[out->condition_count++] = (AgiDecodedCondition) {
                .kind = AGI_CONDITION_NOT, .pc = token_pc,
            };
            negate = true;
            continue;
        }
        if (op == 0xfc) {
            if (negate || (in_or && group_tests == 0)) {
                return agi_decode_fault(out, AGI_FAULT_CONDITION);
            }
            if (out->condition_count == AGI_DECODE_TOKENS_MAX) {
                return agi_decode_fault(out, AGI_FAULT_CONDITION_LIMIT);
            }
            out->conditions[out->condition_count++] = (AgiDecodedCondition) {
                .kind = in_or ? AGI_CONDITION_OR_END : AGI_CONDITION_OR_BEGIN,
                .pc = token_pc,
            };
            if (!in_or) {
                group_tests = 0;
            }
            in_or = !in_or;
            continue;
        }
        if (op > 18 || (!structural && (op < 1 || op > 7))) {
            return agi_decode_fault(out, AGI_FAULT_CONDITION);
        }
        if (++tests > predicate_limit) {
            return agi_decode_fault(out, AGI_FAULT_CONDITION_LIMIT);
        }
        if (out->condition_count == AGI_DECODE_TOKENS_MAX) {
            return agi_decode_fault(out, AGI_FAULT_CONDITION_LIMIT);
        }
        predicate = &predicates[op];
        if (!runtime && (!predicate->native || tests > AGI_EXEC_PREDICATES_MAX)) {
            native_admitted = false;
        }
        count = predicate->operand_count;
        payload_size = op == 14 ? 0 : predicate->size - 1;
        if (op == 14) {
            /* said's byte count precedes ordered little-endian word IDs.
             * Word IDs remain symbols; no vocabulary or input state is read.
             */
            if (at - out->pc >= byte_limit) {
                return agi_decode_fault(out, AGI_FAULT_CONDITION_LIMIT);
            }
            if (!agi_extent(code_size, at, 1)) {
                return agi_decode_fault(out, AGI_FAULT_TRUNCATED);
            }
            words = agi_byte(read, opaque, out, at++);
            count = words + 1;
            payload_size = words * 2;
        }
        if (payload_size > byte_limit - (at - out->pc) ||
            count > AGI_DECODE_CONDITION_OPERANDS_MAX -
                    out->condition_operand_count) {
            return agi_decode_fault(out, AGI_FAULT_CONDITION_LIMIT);
        }
        if (payload_size && !agi_extent(code_size, at, payload_size)) {
            return agi_decode_fault(out, AGI_FAULT_TRUNCATED);
        }
        token = &out->conditions[out->condition_count++];
        token->kind = AGI_CONDITION_PREDICATE;
        token->pc = token_pc;
        token->opcode = op;
        token->mnemonic = predicate->mnemonic;
        token->operand_count = count;
        token->operand_start = out->condition_operand_count;
        operand = &out->condition_operands[out->condition_operand_count];
        if (op == 14) {
            *operand++ = (AgiDecodedOperand) {
                .role = "word_count", .kind = AGI_OPERAND_U8,
                .width = 8, .access = AGI_ACCESS_READ, .value = words,
            };
            for (i = 0; i < words; i++) {
                value = agi_byte(read, opaque, out, at++);
                value |= agi_byte(read, opaque, out, at++) << 8;
                *operand++ = (AgiDecodedOperand) {
                    .role = "word", .kind = AGI_OPERAND_WORD,
                    .width = 16, .access = AGI_ACCESS_REFERENCE, .value = value,
                };
            }
        } else {
            for (i = 0; i < count; i++) {
                operand[i] = predicate->operands[i];
                operand[i].value = agi_byte(read, opaque, out, at++);
            }
        }
        out->condition_operand_count += count;
        negate = false;
        if (in_or) {
            group_tests++;
        }
    }
    if (!agi_extent(code_size, at, 2)) {
        return agi_decode_fault(out, AGI_FAULT_TRUNCATED);
    }
    skip = agi_byte(read, opaque, out, at);
    skip |= agi_byte(read, opaque, out, at + 1) << 8;
    at += 2;
    out->size = at - out->pc;
    out->operands[0].value = skip;
    if (!native_admitted) {
        out->execution_support = AGI_EXEC_UNSUPPORTED_PROFILE;
    }
    agi_edge(out, AGI_SUCCESSOR_TRUE, at, code_size);
    agi_edge(out, AGI_SUCCESSOR_FALSE, (int64_t)at + skip, code_size);
    return true;
}

bool agi_decode(AgiDecodeRead read, void *opaque, uint32_t code_size,
                uint32_t pc, AgiDecodeProfile profile, AgiDecodePurpose purpose,
                AgiDecodedInstruction *out)
{
    const bool runtime = profile == AGI_DECODE_RUNTIME;
    const AgiOpcode *action;
    uint32_t i, at, value;

    *out = (AgiDecodedInstruction) { .pc = pc };
    if (code_size > AGI_CODE_MAX || !agi_extent(code_size, pc, 1)) {
        return agi_decode_fault(out, AGI_FAULT_FETCH);
    }
    out->opcode = agi_byte(read, opaque, out, pc);
    action = &actions[out->opcode];
    if (!action->mnemonic) {
        out->execution_support = AGI_EXEC_UNSUPPORTED_PROFILE;
        return agi_decode_fault(out, AGI_FAULT_OPCODE);
    }
    out->mnemonic = action->mnemonic;
    out->operation = action->operation;
    out->effect_class = action->effect;
    out->execution_support = !action->native ||
                             profile < action->minimum_profile ||
                             profile > AGI_DECODE_INTENT ?
                             AGI_EXEC_UNSUPPORTED_PROFILE :
                             action->effect == AGI_EFFECT_HOST ?
                             AGI_EXEC_PENDING_HOST : AGI_EXEC_NATIVE;
    if (runtime) {
        /* The runtime executes the fixed catalog. Device requests expose a
         * separate resumable capability, including conditional modal paths. */
        switch (out->opcode) {
        case 29: case 101: case 102: case 110: case 115: case 118:
        case 124: case 125: case 126: case 128: case 129:
        case 133: case 134: case 135: case 136: case 139: case 141:
        case 144: case 151: case 152: case 161: case 162:
            out->execution_support = AGI_EXEC_PENDING_HOST;
            break;
        default:
            out->execution_support = AGI_EXEC_NATIVE;
        }
    }
    /* Newly recognized metadata commands remain native unsupported-opcode
     * faults before fetching any operand, including truncated encodings.
     * Previously known profile-disabled commands retain their original path.
     */
    if (purpose == AGI_DECODE_EXECUTION && !action->native && !runtime) {
        return agi_decode_fault(out, AGI_FAULT_OPCODE);
    }
    /* Original-context trace.on can consume an extra byte when tracing is
     * already enabled. Immutable raw bytes do not supply that engine state.
     * Only the explicit runtime dialect selects the nominal zero-operand
     * policy; raw structural inspection and all legacy pilots retain the stop.
     */
    if (out->opcode == 149 && !runtime) {
        return agi_decode_fault(out, AGI_FAULT_CONTEXTUAL_LAYOUT);
    }
    out->operand_count = action->operand_count;
    for (i = 0; i < out->operand_count; i++) {
        out->operands[i] = action->operands[i];
    }
    if (out->opcode == 0xff) {
        return agi_decode_if(read, opaque, code_size, purpose, runtime, out);
    }
    if (!agi_extent(code_size, pc, action->size)) {
        return agi_decode_fault(out, AGI_FAULT_TRUNCATED);
    }
    at = pc + 1;
    for (i = 0; i < out->operand_count; i++) {
        value = agi_byte(read, opaque, out, at++);
        if (out->operands[i].width == 16) {
            value |= agi_byte(read, opaque, out, at++) << 8;
        }
        out->operands[i].value = out->operands[i].kind == AGI_OPERAND_S16 &&
                                 value >= 0x8000 ? (int32_t)value - 65536 :
                                 (int32_t)value;
    }
    out->size = action->size;
    if (out->opcode == 0xfe) {
        agi_edge(out, AGI_SUCCESSOR_BRANCH,
                  (int64_t)pc + out->size + out->operands[0].value, code_size);
    } else if (out->opcode == 22 || out->opcode == 23) {
        /* The typed LOGIC operand is external to this raw-code address space.
         * Following this continuation requires an unqualified callee return.
         */
        agi_edge(out, AGI_SUCCESSOR_ASSUMED_RETURN, (int64_t)pc + out->size,
                  code_size);
    } else if (out->opcode == 126 || out->opcode == 128 || out->opcode == 134) {
        /* A canceled/failed host transition may continue locally; successful
         * restoration, restart or exit does not imply this continuation. */
        agi_edge(out, AGI_SUCCESSOR_ASSUMED_FALLTHROUGH,
                  (int64_t)pc + out->size, code_size);
    } else if (out->opcode != 0 && out->opcode != 18 && out->opcode != 19) {
        agi_edge(out, action->effect == AGI_EFFECT_UNKNOWN ?
                  AGI_SUCCESSOR_ASSUMED_FALLTHROUGH : AGI_SUCCESSOR_FALLTHROUGH,
                  (int64_t)pc + out->size, code_size);
    }
    return true;
}

const char *agi_operand_kind_name(AgiOperandKind kind)
{
    static const char *const names[] = {
        "variable", "flag", "actor", "view", "loop", "cel", "u8", "u16", "s16",
        "picture", "logic", "room", "sound", "message", "inventory_object", "word",
        "string", "controller",
    };
    return names[kind];
}

const char *agi_operand_access_name(AgiOperandAccess access)
{
    static const char *const names[] = {
        "read", "write", "read_write", "reference",
    };
    return names[access];
}

const char *agi_condition_kind_name(AgiConditionKind kind)
{
    static const char *const names[] = { "predicate", "or_begin", "or_end", "not" };
    return names[kind];
}

const char *agi_successor_kind_name(AgiSuccessorKind kind)
{
    static const char *const names[] = {
        "fallthrough", "branch", "true", "false",
        "assumed_return", "assumed_fallthrough",
    };
    return names[kind];
}

const char *agi_effect_class_name(AgiEffectClass effect)
{
    static const char *const names[] = {
        "scalar", "flag", "control", "resource", "actor", "host", "unknown",
    };
    return names[effect];
}

const char *agi_execution_support_name(AgiExecutionSupport support)
{
    static const char *const names[] = { "native", "pending_host", "unsupported_profile" };
    return names[support];
}
