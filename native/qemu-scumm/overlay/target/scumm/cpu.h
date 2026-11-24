/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef SCUMM_CPU_H
#define SCUMM_CPU_H
#include "cpu-qom.h"
#include "exec/cpu-defs.h"
#include "early.h"
#define CPU_RESOLVING_TYPE TYPE_SCUMM_CPU
#define MMU_USER_IDX 0
typedef struct CPUArchState {
 ScummState state;
 uint32_t version,code_size,mask;
 uint64_t budget,run_retired;
} CPUArchState;
struct ArchCPU {
 CPUState parent_obj;
 CPUArchState env;
 uint8_t code[SCUMM_CODE_MAX+1];
 char sha256[65];
 ScummTrace *trace;
 uint32_t decode_pc;
};
struct ScummCPUClass {
 CPUClass parent_class;
 DeviceRealize parent_realize;
 ResettablePhases parent_phases;
};
void scumm_tcg_init(void);
void scumm_cpu_translate_code(CPUState *,TranslationBlock *,int *,vaddr,void *);
static inline void cpu_get_tb_cpu_state(CPUArchState *env,vaddr *pc,uint64_t *base,uint32_t *flags)
{*pc=env->state.pc;*base=0;*flags=env->mask;}
#include "exec/cpu-all.h"
#endif
