/*
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Canonical bounded decode for the existing three native AGI pilot profiles.
 * This module describes encodings; it neither executes nor resolves variables.
 */
#include "decode.h"

typedef struct AgiOpcode {
    const char *mnemonic, *operation;
    AgiEffectClass effect;
    AgiDecodeProfile minimum_profile;
    uint32_t size, operand_count;
    AgiDecodedOperand operands[AGI_DECODE_OPERANDS_MAX];
} AgiOpcode;

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
      .minimum_profile = AGI_DECODE_##profile_, .size = size_, \
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
    [30] = OP("load.view", "resource.load_view", RESOURCE, BINDING, 2, 1,
              ORD("view", VIEW)),
    [31] = OP("load.view.v", "resource.load_view", RESOURCE, BINDING, 2, 1,
              VAR("view", READ)),
    [33] = OP("animate.obj", "object.animate", ACTOR, BINDING, 2, 1, ACTOR),
    [35] = OP("draw", "object.draw", HOST, INTENT, 2, 1, ACTOR),
    [37] = OP("position", "object.position", ACTOR, SCALAR, 4, 3,
              ACTOR, IMM("x"), IMM("y")),
    [38] = OP("position.v", "object.position", ACTOR, SCALAR, 4, 3,
              ACTOR, VAR("x", READ), VAR("y", READ)),
    [39] = OP("get.posn", "object.get_position", ACTOR, SCALAR, 4, 3,
              ACTOR, VAR("x", WRITE), VAR("y", WRITE)),
    [41] = OP("set.view", "object.set_view", ACTOR, BINDING, 3, 2,
              ACTOR, ORD("view", VIEW)),
    [42] = OP("set.view.v", "object.set_view", ACTOR, BINDING, 3, 2,
              ACTOR, VAR("view", READ)),
    [43] = OP("set.loop", "object.set_loop", ACTOR, BINDING, 3, 2,
              ACTOR, ORD("loop", LOOP)),
    [44] = OP("set.loop.v", "object.set_loop", ACTOR, BINDING, 3, 2,
              ACTOR, VAR("loop", READ)),
    [47] = OP("set.cel", "object.set_cel", ACTOR, BINDING, 3, 2,
              ACTOR, ORD("cel", CEL)),
    [48] = OP("set.cel.v", "object.set_cel", ACTOR, BINDING, 3, 2,
              ACTOR, VAR("cel", READ)),
    [70] = OP("stop.cycling", "object.stop_cycling", ACTOR, INTENT, 2, 1,
              ACTOR),
    [71] = OP("start.cycling", "object.start_cycling", ACTOR, INTENT, 2, 1,
              ACTOR),
    [0xfe] = OP("goto", "control.goto", CONTROL, SCALAR, 3, 1,
                ARG("displacement", S16, 16, READ)),
    [0xff] = OP("if", "control.if", CONTROL, SCALAR, 0, 1,
                ARG("displacement", U16, 16, READ)),
};

static const AgiOpcode predicates[8] = {
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
};

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

/* Match the native predicate framing and its fault precedence. In particular,
 * the byte bound is checked before the next token fetch, not after its operands.
 */
static bool agi_decode_if(AgiDecodeRead read, void *opaque, uint32_t code_size,
                          AgiDecodedInstruction *out)
{
    uint32_t at = out->pc + 1, tests = 0, group_tests = 0;
    uint32_t op, token_pc, i, skip;
    bool in_or = false, negate = false;
    AgiDecodedCondition *token;
    const AgiOpcode *predicate;

    for (;;) {
        if (at - out->pc >= AGI_INSN_MAX - 2) {
            return agi_decode_fault(out, AGI_FAULT_CONDITION_LIMIT);
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
        if (op < 1 || op > 7) {
            return agi_decode_fault(out, AGI_FAULT_CONDITION);
        }
        if (++tests > AGI_DECODE_PREDICATES_MAX) {
            return agi_decode_fault(out, AGI_FAULT_CONDITION_LIMIT);
        }
        predicate = &predicates[op];
        if (!agi_extent(code_size, at, predicate->size - 1)) {
            return agi_decode_fault(out, AGI_FAULT_TRUNCATED);
        }
        token = &out->conditions[out->condition_count++];
        token->kind = AGI_CONDITION_PREDICATE;
        token->pc = token_pc;
        token->opcode = op;
        token->mnemonic = predicate->mnemonic;
        token->operand_count = predicate->operand_count;
        for (i = 0; i < token->operand_count; i++) {
            token->operands[i] = predicate->operands[i];
            token->operands[i].value = agi_byte(read, opaque, out, at++);
        }
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
    agi_edge(out, AGI_SUCCESSOR_TRUE, at, code_size);
    agi_edge(out, AGI_SUCCESSOR_FALSE, (int64_t)at + skip, code_size);
    return true;
}

bool agi_decode(AgiDecodeRead read, void *opaque, uint32_t code_size,
                uint32_t pc, AgiDecodeProfile profile,
                AgiDecodedInstruction *out)
{
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
    out->execution_support = profile < action->minimum_profile ||
                             profile > AGI_DECODE_INTENT ?
                             AGI_EXEC_UNSUPPORTED_PROFILE :
                             action->effect == AGI_EFFECT_HOST ?
                             AGI_EXEC_PENDING_HOST : AGI_EXEC_NATIVE;
    out->operand_count = action->operand_count;
    for (i = 0; i < out->operand_count; i++) {
        out->operands[i] = action->operands[i];
    }
    if (out->opcode == 0xff) {
        return agi_decode_if(read, opaque, code_size, out);
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
    } else if (out->opcode != 0) {
        agi_edge(out, AGI_SUCCESSOR_FALLTHROUGH, (int64_t)pc + out->size,
                  code_size);
    }
    return true;
}

const char *agi_operand_kind_name(AgiOperandKind kind)
{
    static const char *const names[] = {
        "variable", "flag", "actor", "view", "loop", "cel", "u8", "u16", "s16",
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
    static const char *const names[] = { "fallthrough", "branch", "true", "false" };
    return names[kind];
}

const char *agi_effect_class_name(AgiEffectClass effect)
{
    static const char *const names[] = {
        "scalar", "flag", "control", "resource", "actor", "host",
    };
    return names[effect];
}

const char *agi_execution_support_name(AgiExecutionSupport support)
{
    static const char *const names[] = { "native", "pending_host", "unsupported_profile" };
    return names[support];
}
