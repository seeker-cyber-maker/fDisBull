/*
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Direct TCG lowering for the bounded AGI 2.917 scalar/position profile.
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
} DisasContext;

static void agi_init_context(DisasContextBase *db, CPUState *cs)
{
    DisasContext *ctx = container_of(db, DisasContext, base);
    ctx->env = cpu_env(cs);
    ctx->obs_mask = db->tb->flags & AGI_OBS_MASK;
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

static bool agi_extent(DisasContext *ctx, uint32_t pc, uint32_t length)
{
    return pc < ctx->env->code_size && length <= ctx->env->code_size - pc;
}

/* Pure predicates only. FC delimits an OR group, FD negates the next test.
 * Groups are not nested; all top-level terms are ANDed, in bytecode order.
 */
static bool agi_if(DisasContext *ctx, uint32_t pc, uint32_t *length,
                   TCGv_i32 next)
{
    DisasContextBase *db = &ctx->base;
    uint32_t at = pc + 1, tests = 0, group_tests = 0, op, a, b, width, skip;
    uint32_t fault = AGI_FAULT_TRUNCATED;
    bool in_or = false, negate = false;
    TCGv_i32 all = tcg_temp_new_i32();
    TCGv_i32 group = tcg_temp_new_i32();
    TCGv_i32 value = tcg_temp_new_i32();
    TCGv_i32 left, right;
    tcg_gen_movi_i32(all, 1);
    tcg_gen_movi_i32(group, 0);

    for (;;) {
        if (at - pc >= AGI_INSN_MAX - 2) {
            fault = AGI_FAULT_CONDITION_LIMIT;
            goto invalid;
        }
        if (!agi_extent(ctx, at, 1)) {
            goto invalid;
        }
        op = translator_ldub(ctx->env, db, at++);
        if (op == 0xff) {
            if (in_or || negate) {
                fault = AGI_FAULT_CONDITION;
                goto invalid;
            }
            break;
        }
        if (op == 0xfd) {
            if (negate) {
                fault = AGI_FAULT_CONDITION;
                goto invalid;
            }
            negate = true;
            continue;
        }
        if (op == 0xfc) {
            if (negate || (in_or && group_tests == 0)) {
                fault = AGI_FAULT_CONDITION;
                goto invalid;
            }
            if (in_or) {
                tcg_gen_and_i32(all, all, group);
            } else {
                group_tests = 0;
                tcg_gen_movi_i32(group, 0);
            }
            in_or = !in_or;
            continue;
        }
        if (op < 1 || op > 7) {
            fault = AGI_FAULT_CONDITION;
            goto invalid;
        }
        if (++tests > 8) {
            fault = AGI_FAULT_CONDITION_LIMIT;
            goto invalid;
        }
        width = op == 7 ? 1 : 2;
        if (!agi_extent(ctx, at, width)) {
            goto invalid;
        }
        a = translator_ldub(ctx->env, db, at++);
        if (op == 7) {
            left = agi_load(agi_flag(a));
            tcg_gen_setcondi_i32(TCG_COND_NE, value, left, 0);
        } else {
            b = translator_ldub(ctx->env, db, at++);
            left = agi_load(agi_var(a));
            right = (op & 1) ? tcg_constant_i32(b) : agi_load(agi_var(b));
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
            group_tests++;
        } else {
            tcg_gen_and_i32(all, all, value);
        }
    }
    if (!agi_extent(ctx, at, 2)) {
        goto invalid;
    }
    skip = translator_ldub(ctx->env, db, at) |
           (translator_ldub(ctx->env, db, at + 1) << 8);
    at += 2;
    *length = at - pc;
    if ((uint64_t)at + skip >= ctx->env->code_size) {
        TCGLabel *taken = gen_new_label();
        tcg_gen_brcondi_i32(TCG_COND_NE, all, 0, taken);
        agi_emit_fault(pc, 0xff, AGI_FAULT_BRANCH);
        gen_set_label(taken);
        tcg_gen_movi_i32(next, at);
    } else {
        tcg_gen_movcond_i32(TCG_COND_NE, next, all, tcg_constant_i32(0),
                           tcg_constant_i32(at), tcg_constant_i32(at + skip));
    }
    return true;
invalid:
    agi_emit_fault(pc, 0xff, fault);
    return false;
}

static void agi_translate_insn(DisasContextBase *db, CPUState *cs)
{
    DisasContext *ctx = container_of(db, DisasContext, base);
    uint32_t pc = db->pc_next, op = 0, length = 1, a = 0, b = 0, c = 0;
    uint32_t actor = UINT32_MAX;
    int64_t target;
    size_t offset;
    bool position = false;
    TCGv_i32 x, y, value, prior, part;
    TCGv_i32 before = tcg_constant_i32(0);
    TCGv_i32 next = tcg_temp_new_i32();

    if (!agi_extent(ctx, pc, 1)) {
        agi_emit_fault(pc, 0, AGI_FAULT_FETCH);
        goto fault;
    }
    op = translator_ldub(ctx->env, db, pc);
    if (op == 0xff) {
        if (!agi_if(ctx, pc, &length, next)) {
            goto fault;
        }
        goto complete;
    }
    if (op == 0) {
        length = 1;
    } else if (op == 1 || op == 2 || (op >= 12 && op <= 14)) {
        length = 2;
    } else if ((op >= 3 && op <= 8) || op == 0xfe) {
        length = 3;
    } else if (op >= 37 && op <= 39) {
        length = 4;
    } else {
        agi_emit_fault(pc, op, AGI_FAULT_OPCODE);
        goto fault;
    }
    if (!agi_extent(ctx, pc, length)) {
        agi_emit_fault(pc, op, AGI_FAULT_TRUNCATED);
        goto fault;
    }
    if (length >= 2) {
        a = translator_ldub(ctx->env, db, pc + 1);
    }
    if (length >= 3) {
        b = translator_ldub(ctx->env, db, pc + 2);
    }
    if (length >= 4) {
        c = translator_ldub(ctx->env, db, pc + 3);
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
        position = true;
        actor = a;
        if (ctx->obs_mask & AGI_OBS_SCENE) {
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
        target = (int64_t)pc + 3 + (int16_t)(a | (b << 8));
        if (target < 0 || target >= ctx->env->code_size) {
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
        ((ctx->obs_mask & AGI_OBS_SCENE) && position)) {
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
