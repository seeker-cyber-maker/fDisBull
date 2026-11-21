/*
 * SPDX-License-Identifier: GPL-2.0-or-later
 * TCG lowering for the bounded AGI 2.917 scalar and optional binding profiles.
 */
#include "qemu/osdep.h"
#include "tcg/tcg.h"
#include "cpu.h"
#include "exec/translator.h"
#include "exec/translation-block.h"
#include "exec/helper-proto.h"
#include "exec/helper-gen.h"
#include "tcg/tcg-op.h"
#define HELPER_H "helper.h"
#include "exec/helper-info.c.inc"
#undef HELPER_H

typedef struct DisasContext {
    DisasContextBase base;
    CPUArchState *env;
    uint32_t obs_mask;
    bool binding_profile;
    bool draw_intent;
} DisasContext;

static void agi_init_context(DisasContextBase *db, CPUState *cs)
{
    DisasContext *ctx = container_of(db, DisasContext, base);
    ctx->env = cpu_env(cs);
    ctx->obs_mask = db->tb->flags & AGI_OBS_MASK;
    ctx->binding_profile = db->tb->flags & AGI_TB_BINDING;
    ctx->draw_intent = db->tb->flags & AGI_TB_DRAW_INTENT;
}

static void agi_tb_start(DisasContextBase *db, CPUState *cs) { }
static void agi_insn_start(DisasContextBase *db, CPUState *cs)
{
    tcg_gen_insn_start(db->pc_next);
}

static TCGv_i32 agi_load(size_t offset)
{
    TCGv_i32 value = tcg_temp_new_i32();
    tcg_gen_ld_i32(value, tcg_env, offset);
    return value;
}

static size_t agi_var(unsigned index) { return offsetof(CPUArchState, v) + index * 4; }
static size_t agi_flag(unsigned index) { return offsetof(CPUArchState, f) + index * 4; }
static size_t agi_actor(unsigned index)
{
    return offsetof(CPUArchState, actors) + index * sizeof(AgiActor);
}

static void agi_emit_fault(uint32_t pc, uint32_t opcode, uint32_t fault)
{
    gen_helper_agi_fault(tcg_env, tcg_constant_i32(pc),
                         tcg_constant_i32(opcode), tcg_constant_i32(fault));
}

static uint8_t agi_translate_read(void *opaque, uint32_t pc)
{
    DisasContext *ctx = opaque;
    return translator_ldub(ctx->env, &ctx->base, pc);
}

/* Lower the canonical, already validated predicate tokens in bytecode order. */
static void agi_if(const AgiDecodedInstruction *insn, TCGv_i32 next)
{
    uint32_t i, op, a, b;
    bool in_or = false, negate = false;
    TCGv_i32 all = tcg_temp_new_i32();
    TCGv_i32 group = tcg_temp_new_i32();
    TCGv_i32 value = tcg_temp_new_i32();
    TCGv_i32 left, right;
    tcg_gen_movi_i32(all, 1);
    tcg_gen_movi_i32(group, 0);

    for (i = 0; i < insn->condition_count; i++) {
        const AgiDecodedCondition *token = &insn->conditions[i];
        if (token->kind == AGI_CONDITION_NOT) {
            negate = true;
            continue;
        }
        if (token->kind == AGI_CONDITION_OR_BEGIN) {
            tcg_gen_movi_i32(group, 0);
            in_or = true;
            continue;
        }
        if (token->kind == AGI_CONDITION_OR_END) {
            tcg_gen_and_i32(all, all, group);
            in_or = false;
            continue;
        }
        op = token->opcode;
        a = token->operands[0].value;
        if (op == 7) {
            left = agi_load(agi_flag(a));
            tcg_gen_setcondi_i32(TCG_COND_NE, value, left, 0);
        } else {
            b = token->operands[1].value;
            left = agi_load(agi_var(a));
            right = token->operands[1].kind == AGI_OPERAND_VARIABLE ?
                    agi_load(agi_var(b)) : tcg_constant_i32(b);
            tcg_gen_setcond_i32(op <= 2 ? TCG_COND_EQ :
                               op <= 4 ? TCG_COND_LTU : TCG_COND_GTU,
                               value, left, right);
        }
        if (negate) {
            tcg_gen_xori_i32(value, value, 1);
            negate = false;
        }
        if (in_or) {
            tcg_gen_or_i32(group, group, value);
        } else {
            tcg_gen_and_i32(all, all, value);
        }
    }
    if (!insn->successors[1].in_range) {
        TCGLabel *taken = gen_new_label();
        tcg_gen_brcondi_i32(TCG_COND_NE, all, 0, taken);
        agi_emit_fault(insn->pc, 0xff, AGI_FAULT_BRANCH);
        gen_set_label(taken);
        tcg_gen_movi_i32(next, insn->successors[0].pc);
    } else {
        tcg_gen_movcond_i32(TCG_COND_NE, next, all, tcg_constant_i32(0),
                           tcg_constant_i32(insn->successors[0].pc),
                           tcg_constant_i32(insn->successors[1].pc));
    }
}

static void agi_translate_insn(DisasContextBase *db, CPUState *cs)
{
    DisasContext *ctx = container_of(db, DisasContext, base);
    AgiDecodedInstruction insn;
    uint32_t pc = db->pc_next, op = 0, length = 1, a = 0, b = 0, c = 0;
    uint32_t actor = UINT32_MAX;
    int64_t target;
    size_t offset;
    bool scene_effect = false, decoded;
    TCGv_i32 x, y, value, prior, part;
    TCGv_i32 before = tcg_constant_i32(0);
    TCGv_i32 next = tcg_temp_new_i32();

    decoded = agi_decode(agi_translate_read, ctx, ctx->env->code_size, pc,
                          ctx->draw_intent ? AGI_DECODE_INTENT :
                          ctx->binding_profile ? AGI_DECODE_BINDING :
                          AGI_DECODE_SCALAR, &insn);
    op = insn.opcode;
    /* A disabled command faults as unsupported even if its operands are
     * truncated. Static inspection may still describe that known encoding.
     */
    if (insn.execution_support == AGI_EXEC_UNSUPPORTED_PROFILE) {
        agi_emit_fault(pc, op, AGI_FAULT_OPCODE);
        goto fault;
    }
    if (!decoded) {
        agi_emit_fault(pc, op, insn.fault);
        goto fault;
    }
    length = insn.size;
    if (op == 0xff) {
        agi_if(&insn, next);
        goto complete;
    }
    if (insn.operand_count >= 1) {
        a = insn.operands[0].value;
    }
    if (insn.operand_count >= 2) {
        b = insn.operands[1].value;
    }
    if (insn.operand_count >= 3) {
        c = insn.operands[2].value;
    }
    tcg_gen_movi_i32(next, pc + length);
    switch (op) {
    case 0:
        break;
    case 1:
    case 2:
        x = agi_load(agi_var(a));
        value = tcg_temp_new_i32();
        tcg_gen_addi_i32(value, x, op == 1 ? 1 : -1);
        tcg_gen_movcond_i32(TCG_COND_EQ, value, x,
                           tcg_constant_i32(op == 1 ? 255 : 0), x, value);
        tcg_gen_st_i32(value, tcg_env, agi_var(a));
        break;
    case 3:
    case 4:
        value = op == 3 ? tcg_constant_i32(b) : agi_load(agi_var(b));
        tcg_gen_st_i32(value, tcg_env, agi_var(a));
        break;
    case 5:
    case 6:
    case 7:
    case 8:
        x = agi_load(agi_var(a));
        y = (op & 1) ? tcg_constant_i32(b) : agi_load(agi_var(b));
        value = tcg_temp_new_i32();
        if (op <= 6) {
            tcg_gen_add_i32(value, x, y);
        } else {
            tcg_gen_sub_i32(value, x, y);
        }
        tcg_gen_andi_i32(value, value, 255);
        tcg_gen_st_i32(value, tcg_env, agi_var(a));
        break;
    case 12:
    case 13:
        tcg_gen_st_i32(tcg_constant_i32(op == 12), tcg_env, agi_flag(a));
        break;
    case 14:
        value = agi_load(agi_flag(a));
        tcg_gen_xori_i32(value, value, 1);
        tcg_gen_st_i32(value, tcg_env, agi_flag(a));
        break;
    case 30:
    case 31:
    case 33:
    case 41:
    case 42:
    case 43:
    case 44:
    case 47:
    case 48:
    case 70:
    case 71:
        scene_effect = true;
        if (op != 30 && op != 31) {
            actor = a;
        }
        gen_helper_agi_binding(tcg_env, tcg_constant_i32(pc),
                               tcg_constant_i32(op | (length << 8) |
                                                (ctx->obs_mask << 16)),
                               tcg_constant_i32(a), tcg_constant_i32(b));
        break;
    case 35:
        gen_helper_agi_draw(tcg_env, tcg_constant_i32(pc), tcg_constant_i32(a));
        db->pc_next = pc + length;
        db->is_jmp = DISAS_NORETURN;
        return;
    case 37:
    case 38:
    case 39:
        if (a >= AGI_ACTORS) {
            agi_emit_fault(pc, op, AGI_FAULT_ACTOR);
            goto fault;
        }
        offset = agi_actor(a);
        if (op == 39) {
            x = agi_load(offset + offsetof(AgiActor, x));
            y = agi_load(offset + offsetof(AgiActor, y));
            tcg_gen_st_i32(x, tcg_env, agi_var(b));
            tcg_gen_st_i32(y, tcg_env, agi_var(c));
            break;
        }
        scene_effect = true;
        actor = a;
        if (ctx->binding_profile && (ctx->obs_mask & AGI_OBS_SCENE)) {
            size_t field;
            /* No extra observer helper or snapshot work in the mask-0 TB.
             * Every actor member is a uint32_t and is initialized at reset.
             */
            for (field = 0; field < sizeof(AgiActor); field += sizeof(uint32_t)) {
                prior = agi_load(offset + field);
                tcg_gen_st_i32(prior, tcg_env,
                               offsetof(CPUArchState, observed_actor) + field);
            }
        } else if (ctx->obs_mask & AGI_OBS_SCENE) {
            prior = agi_load(offset + offsetof(AgiActor, x));
            part = agi_load(offset + offsetof(AgiActor, y));
            before = tcg_temp_new_i32();
            tcg_gen_shli_i32(part, part, 8);
            tcg_gen_or_i32(before, prior, part);
            part = agi_load(offset + offsetof(AgiActor, prev_x));
            tcg_gen_shli_i32(part, part, 16);
            tcg_gen_or_i32(before, before, part);
            part = agi_load(offset + offsetof(AgiActor, prev_y));
            tcg_gen_shli_i32(part, part, 24);
            tcg_gen_or_i32(before, before, part);
        }
        x = op == 37 ? tcg_constant_i32(b) : agi_load(agi_var(b));
        y = op == 37 ? tcg_constant_i32(c) : agi_load(agi_var(c));
        tcg_gen_st_i32(x, tcg_env, offset + offsetof(AgiActor, x));
        tcg_gen_st_i32(y, tcg_env, offset + offsetof(AgiActor, y));
        tcg_gen_st_i32(x, tcg_env, offset + offsetof(AgiActor, prev_x));
        tcg_gen_st_i32(y, tcg_env, offset + offsetof(AgiActor, prev_y));
        break;
    case 0xfe:
        target = insn.successors[0].pc;
        if (!insn.successors[0].in_range) {
            agi_emit_fault(pc, op, AGI_FAULT_BRANCH);
            goto fault;
        }
        tcg_gen_movi_i32(next, target);
        break;
    default:
        g_assert_not_reached();
    }
complete:
    tcg_gen_st_i32(next, tcg_env, offsetof(CPUArchState, pc));
    if ((ctx->obs_mask & AGI_OBS_DISASM) ||
        ((ctx->obs_mask & AGI_OBS_SCENE) && scene_effect)) {
        uint32_t meta = op | (length << 8) | (ctx->obs_mask << 16);
        gen_helper_agi_observe(tcg_env, tcg_constant_i32(pc),
                               tcg_constant_i32(meta), tcg_constant_i32(actor), before);
    }
    gen_helper_agi_retire(tcg_env, tcg_constant_i32(op == 0));
    db->pc_next = pc + length;
    db->is_jmp = DISAS_TOO_MANY;
    return;
fault:
    db->pc_next = pc + 1;
    db->is_jmp = DISAS_NORETURN;
}

static void agi_tb_stop(DisasContextBase *db, CPUState *cs)
{
    if (db->is_jmp != DISAS_NORETURN) {
        tcg_gen_exit_tb(NULL, 0);
    }
}

static const TranslatorOps agi_translator_ops = {
    .init_disas_context = agi_init_context,
    .tb_start = agi_tb_start,
    .insn_start = agi_insn_start,
    .translate_insn = agi_translate_insn,
    .tb_stop = agi_tb_stop,
};
void agi_tcg_init(void) { }
void agi_cpu_translate_code(CPUState *cs, TranslationBlock *tb,
                            int *max_insns, vaddr pc, void *host_pc)
{
    DisasContext dc = { 0 };
    translator_loop(cs, tb, max_insns, pc, host_pc, &agi_translator_ops, &dc.base);
}
