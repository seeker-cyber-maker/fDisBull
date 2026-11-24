/* SPDX-License-Identifier: GPL-2.0-or-later */
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
static void init(DisasContextBase *db,CPUState *cs){}
static void start(DisasContextBase *db,CPUState *cs){}
static void insn_start(DisasContextBase *db,CPUState *cs){tcg_gen_insn_start(db->pc_next);}
static void insn(DisasContextBase *db,CPUState *cs)
{
 ScummCPU *cpu=SCUMM_CPU(cs);ScummInsn decoded;
 bool ok=scumm_decode(cpu->env.version,cpu->code,cpu->env.code_size,db->pc_next,&decoded);
 unsigned size=ok?decoded.size:1;
 /* The canonical decoder reads the immutable script copy. Register its bytes
  * with QEMU too, including a second page for long instructions, so TB page
  * tracking and diagnostic disassembly cover the entire instruction. */
 for(unsigned n=0;n<size;n++) {
  translator_ldub(&cpu->env,db,db->pc_next+n);
 }
 /* Single semantic-helper TB; static decode and runtime share one authority. */
 gen_helper_scumm_step(tcg_env);
 db->pc_next+=size;db->is_jmp=DISAS_TOO_MANY;
}
static void stop(DisasContextBase *db,CPUState *cs){tcg_gen_exit_tb(NULL,0);}
static const TranslatorOps ops={.init_disas_context=init,.tb_start=start,.insn_start=insn_start,
 .translate_insn=insn,.tb_stop=stop};
void scumm_tcg_init(void){}
void scumm_cpu_translate_code(CPUState *cs,TranslationBlock *tb,int *max_insns,vaddr pc,void *host_pc)
{DisasContextBase dc={0};translator_loop(cs,tb,max_insns,pc,host_pc,&ops,&dc);}
