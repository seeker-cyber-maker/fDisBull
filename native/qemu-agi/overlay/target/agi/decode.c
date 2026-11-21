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

/* Fixed encoding facts reused from fDisBull's agi_layout.py and agi_scenes.py
 * at 1b27110bb43fe91fec5d09b4cffa7227771cb5e9. These project tables describe
 * the explicit 2.917 layout, not executable engine implementations. Opcode
 * 149 remains a contextual-layout boundary despite its nominal zero width.
 */
typedef struct AgiCatalogEntry {
    const char *mnemonic;
    uint8_t operand_count;
} AgiCatalogEntry;

static const AgiCatalogEntry catalog[174] = {
    [0] = { "return", 0 },
    [1] = { "increment", 1 },
    [2] = { "decrement", 1 },
    [3] = { "assignn", 2 },
    [4] = { "assignv", 2 },
    [5] = { "addn", 2 },
    [6] = { "addv", 2 },
    [7] = { "subn", 2 },
    [8] = { "subv", 2 },
    [9] = { "lindirectv", 2 },
    [10] = { "rindirect", 2 },
    [11] = { "lindirectn", 2 },
    [12] = { "set", 1 },
    [13] = { "reset", 1 },
    [14] = { "toggle", 1 },
    [15] = { "set.v", 1 },
    [16] = { "reset.v", 1 },
    [17] = { "toggle.v", 1 },
    [18] = { "new.room", 1 },
    [19] = { "new.room.v", 1 },
    [20] = { "load.logics", 1 },
    [21] = { "load.logics.v", 1 },
    [22] = { "call", 1 },
    [23] = { "call.v", 1 },
    [24] = { "load.pic", 1 },
    [25] = { "draw.pic", 1 },
    [26] = { "show.pic", 0 },
    [27] = { "discard.pic", 1 },
    [28] = { "overlay.pic", 1 },
    [29] = { "show.pri.screen", 0 },
    [30] = { "load.view", 1 },
    [31] = { "load.view.v", 1 },
    [32] = { "discard.view", 1 },
    [33] = { "animate.obj", 1 },
    [34] = { "unanimate.all", 0 },
    [35] = { "draw", 1 },
    [36] = { "erase", 1 },
    [37] = { "position", 3 },
    [38] = { "position.v", 3 },
    [39] = { "get.posn", 3 },
    [40] = { "reposition", 3 },
    [41] = { "set.view", 2 },
    [42] = { "set.view.v", 2 },
    [43] = { "set.loop", 2 },
    [44] = { "set.loop.v", 2 },
    [45] = { "fix.loop", 1 },
    [46] = { "release.loop", 1 },
    [47] = { "set.cel", 2 },
    [48] = { "set.cel.v", 2 },
    [49] = { "last.cel", 2 },
    [50] = { "current.cel", 2 },
    [51] = { "current.loop", 2 },
    [52] = { "current.view", 2 },
    [53] = { "number.of.loops", 2 },
    [54] = { "set.priority", 2 },
    [55] = { "set.priority.v", 2 },
    [56] = { "release.priority", 1 },
    [57] = { "get.priority", 2 },
    [58] = { "stop.update", 1 },
    [59] = { "start.update", 1 },
    [60] = { "force.update", 1 },
    [61] = { "ignore.horizon", 1 },
    [62] = { "observe.horizon", 1 },
    [63] = { "set.horizon", 1 },
    [64] = { "object.on.water", 1 },
    [65] = { "object.on.land", 1 },
    [66] = { "object.on.anything", 1 },
    [67] = { "ignore.objs", 1 },
    [68] = { "observe.objs", 1 },
    [69] = { "distance", 3 },
    [70] = { "stop.cycling", 1 },
    [71] = { "start.cycling", 1 },
    [72] = { "normal.cycle", 1 },
    [73] = { "end.of.loop", 2 },
    [74] = { "reverse.cycle", 1 },
    [75] = { "reverse.loop", 2 },
    [76] = { "cycle.time", 2 },
    [77] = { "stop.motion", 1 },
    [78] = { "start.motion", 1 },
    [79] = { "step.size", 2 },
    [80] = { "step.time", 2 },
    [81] = { "move.obj", 5 },
    [82] = { "move.obj.v", 5 },
    [83] = { "follow.ego", 3 },
    [84] = { "wander", 1 },
    [85] = { "normal.motion", 1 },
    [86] = { "set.dir", 2 },
    [87] = { "get.dir", 2 },
    [88] = { "ignore.blocks", 1 },
    [89] = { "observe.blocks", 1 },
    [90] = { "block", 4 },
    [91] = { "unblock", 0 },
    [92] = { "get", 1 },
    [93] = { "get.v", 1 },
    [94] = { "drop", 1 },
    [95] = { "put", 2 },
    [96] = { "put.v", 2 },
    [97] = { "get.room.v", 2 },
    [98] = { "load.sound", 1 },
    [99] = { "sound", 2 },
    [100] = { "stop.sound", 0 },
    [101] = { "print", 1 },
    [102] = { "print.v", 1 },
    [103] = { "display", 3 },
    [104] = { "display.v", 3 },
    [105] = { "clear.lines", 3 },
    [106] = { "text.screen", 0 },
    [107] = { "graphics", 0 },
    [108] = { "set.cursor.char", 1 },
    [109] = { "set.text.attribute", 2 },
    [110] = { "shake.screen", 1 },
    [111] = { "configure.screen", 3 },
    [112] = { "status.line.on", 0 },
    [113] = { "status.line.off", 0 },
    [114] = { "set.string", 2 },
    [115] = { "get.string", 5 },
    [116] = { "word.to.string", 2 },
    [117] = { "parse", 1 },
    [118] = { "get.num", 2 },
    [119] = { "prevent.input", 0 },
    [120] = { "accept.input", 0 },
    [121] = { "set.key", 3 },
    [122] = { "add.to.pic", 7 },
    [123] = { "add.to.pic.v", 7 },
    [124] = { "status", 0 },
    [125] = { "save.game", 0 },
    [126] = { "restore.game", 0 },
    [127] = { "init.disk", 0 },
    [128] = { "restart.game", 0 },
    [129] = { "show.obj", 1 },
    [130] = { "random", 3 },
    [131] = { "program.control", 0 },
    [132] = { "player.control", 0 },
    [133] = { "obj.status.v", 1 },
    [134] = { "quit", 1 },
    [135] = { "show.mem", 0 },
    [136] = { "pause", 0 },
    [137] = { "echo.line", 0 },
    [138] = { "cancel.line", 0 },
    [139] = { "init.joy", 0 },
    [140] = { "toggle.monitor", 0 },
    [141] = { "version", 0 },
    [142] = { "script.size", 1 },
    [143] = { "set.game.id", 1 },
    [144] = { "log", 1 },
    [145] = { "set.scan.start", 0 },
    [146] = { "reset.scan.start", 0 },
    [147] = { "reposition.to", 3 },
    [148] = { "reposition.to.v", 3 },
    [149] = { "trace.on", 0 },
    [150] = { "trace.info", 3 },
    [151] = { "print.at", 4 },
    [152] = { "print.at.v", 4 },
    [153] = { "discard.view.v", 1 },
    [154] = { "clear.text.rect", 5 },
    [155] = { "set.upper.left", 2 },
    [156] = { "set.menu", 1 },
    [157] = { "set.menu.item", 2 },
    [158] = { "submit.menu", 0 },
    [159] = { "enable.item", 1 },
    [160] = { "disable.item", 1 },
    [161] = { "menu.input", 0 },
    [162] = { "show.obj.v", 1 },
    [163] = { "open.dialogue", 0 },
    [164] = { "close.dialogue", 0 },
    [165] = { "mul.n", 2 },
    [166] = { "mul.v", 2 },
    [167] = { "div.n", 2 },
    [168] = { "div.v", 2 },
    [169] = { "close.window", 0 },
    [170] = { "set.simple", 1 },
    [171] = { "push.script", 0 },
    [172] = { "pop.script", 0 },
    [173] = { "hold.key", 0 },
};

#define ARG(role_, kind_, width_, access_) \
    { .role = role_, .kind = AGI_OPERAND_##kind_, .width = width_, \
      .access = AGI_ACCESS_##access_ }
#define VAR(role_, access_) ARG(role_, VARIABLE, 8, access_)
#define IMM(role_) ARG(role_, U8, 8, READ)
#define ACTOR ARG("actor", ACTOR, 8, REFERENCE)
#define ORD(role_, kind_) ARG(role_, kind_, 8, REFERENCE)
#define FLAG(access_) ARG("flag", FLAG, 1, access_)
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
    [122] = META("add.to.pic", "scene.add_to_picture", HOST, 8, 7,
                 ORD("view", VIEW), ORD("loop", LOOP), ORD("cel", CEL),
                 IMM("x"), IMM("y"), IMM("priority"), IMM("control")),
    [123] = META("add.to.pic.v", "scene.add_to_picture", HOST, 8, 7,
                 VAR("view", READ), VAR("loop", READ), VAR("cel", READ),
                 VAR("x", READ), VAR("y", READ), VAR("priority", READ),
                 VAR("control", READ)),
    [129] = META("show.obj", "scene.show_object", HOST, 2, 1, ORD("view", VIEW)),
    [145] = META("set.scan.start", "control.set_scan_start", CONTROL, 1, 0, { 0 }),
    [146] = META("reset.scan.start", "control.reset_scan_start", CONTROL, 1, 0, { 0 }),
    [147] = META("reposition.to", "object.reposition_to", ACTOR, 4, 3,
                 ACTOR, IMM("x"), IMM("y")),
    [148] = META("reposition.to.v", "object.reposition_to", ACTOR, 4, 3,
                 ACTOR, VAR("x", READ), VAR("y", READ)),
    [153] = META("discard.view.v", "resource.discard_view", RESOURCE, 2, 1,
                 VAR("view", READ)),
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
    [12] = META("controller", "", CONTROL, 2, 1, IMM("controller")),
    [13] = META("have.key", "", CONTROL, 1, 0, { 0 }),
    [14] = META("said", "", CONTROL, 0, 0, { 0 }),
    [15] = META("compare.strings", "", CONTROL, 3, 2,
                IMM("left_string"), IMM("right_string")),
    [16] = META("obj.in.box", "", CONTROL, 6, 5,
                ACTOR, IMM("x1"), IMM("y1"), IMM("x2"), IMM("y2")),
    [17] = META("center.posn", "", CONTROL, 6, 5,
                ACTOR, IMM("x1"), IMM("y1"), IMM("x2"), IMM("y2")),
    [18] = META("right.posn", "", CONTROL, 6, 5,
                ACTOR, IMM("x1"), IMM("y1"), IMM("x2"), IMM("y2")),
};

#undef META
#undef OP
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
                          AgiDecodePurpose purpose, AgiDecodedInstruction *out)
{
    const bool structural = purpose == AGI_DECODE_STRUCTURAL;
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
        if (at - out->pc >= AGI_INSN_MAX - 2) {
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
        if (!predicate->native || tests > AGI_EXEC_PREDICATES_MAX) {
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
    static const char *const argument_roles[AGI_DECODE_OPERANDS_MAX] = {
        "arg0", "arg1", "arg2", "arg3", "arg4", "arg5", "arg6",
    };
    const AgiOpcode *action;
    AgiOpcode catalog_action;
    uint32_t i, at, value;

    *out = (AgiDecodedInstruction) { .pc = pc };
    if (code_size > AGI_CODE_MAX || !agi_extent(code_size, pc, 1)) {
        return agi_decode_fault(out, AGI_FAULT_FETCH);
    }
    out->opcode = agi_byte(read, opaque, out, pc);
    action = &actions[out->opcode];
    if (!action->mnemonic && out->opcode < 174) {
        catalog_action = (AgiOpcode) {
            .mnemonic = catalog[out->opcode].mnemonic,
            .operation = "unmodeled", .effect = AGI_EFFECT_UNKNOWN,
            .size = catalog[out->opcode].operand_count + 1,
            .operand_count = catalog[out->opcode].operand_count,
        };
        for (i = 0; i < catalog_action.operand_count; i++) {
            catalog_action.operands[i] = (AgiDecodedOperand) {
                .role = argument_roles[i], .kind = AGI_OPERAND_U8,
                .width = 8, .access = AGI_ACCESS_READ,
            };
        }
        action = &catalog_action;
    }
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
    /* Newly recognized metadata commands remain native unsupported-opcode
     * faults before fetching any operand, including truncated encodings.
     * Previously known profile-disabled commands retain their original path.
     */
    if (purpose == AGI_DECODE_EXECUTION && !action->native) {
        return agi_decode_fault(out, AGI_FAULT_OPCODE);
    }
    /* In AGI 2.917 trace.on can consume an extra byte when tracing is already
     * enabled. Immutable raw bytes do not supply that engine state.
     */
    if (out->opcode == 149) {
        return agi_decode_fault(out, AGI_FAULT_CONTEXTUAL_LAYOUT);
    }
    out->operand_count = action->operand_count;
    for (i = 0; i < out->operand_count; i++) {
        out->operands[i] = action->operands[i];
    }
    if (out->opcode == 0xff) {
        return agi_decode_if(read, opaque, code_size, purpose, out);
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
