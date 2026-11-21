/*
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Authored AGI observation experiment, using the fDisBull CHIP-8/QEMU scaffold.
 */
#ifndef AGI_CPU_H
#define AGI_CPU_H
#include "cpu-qom.h"
#include "exec/cpu-defs.h"

#define CPU_RESOLVING_TYPE TYPE_AGI_CPU
#define AGI_CODE_MAX 65536
#define AGI_ACTORS 16
#define AGI_EVENT_MAX 65536
#define AGI_INSN_MAX 64
#define AGI_PROFILE "agi-2917-scalar-position-pilot-1"
#define AGI_OBS_DISASM 1
#define AGI_OBS_SCENE 2
#define AGI_OBS_MASK 3
#define MMU_USER_IDX 0

typedef enum AgiStatus {
    AGI_READY, AGI_RUNNING, AGI_BUDGET, AGI_RETURN, AGI_FAULT, AGI_EXTERNAL
} AgiStatus;

typedef enum AgiFault {
    AGI_FAULT_NONE,
    AGI_FAULT_OPCODE,
    AGI_FAULT_TRUNCATED,
    AGI_FAULT_ACTOR,
    AGI_FAULT_BRANCH,
    AGI_FAULT_CONDITION,
    AGI_FAULT_FETCH,
    AGI_FAULT_CONDITION_LIMIT
} AgiFault;

typedef struct AgiActor {
    uint32_t x, y, prev_x, prev_y;
} AgiActor;

typedef struct AgiEvent {
    uint64_t seq, retired, control_generation;
    uint32_t kind, pc, opcode, length, next_pc, actor;
    AgiActor before, after;
} AgiEvent;

typedef struct CPUArchState {
    uint32_t v[256], f[256];
    AgiActor actors[AGI_ACTORS];
    uint32_t pc, code_size, status;
    uint32_t fault_code, fault_pc, fault_opcode;
    uint32_t obs_mask, obs_capacity, obs_count;
    uint64_t step_budget, retired, run_retired, invocation;
    uint64_t elapsed_ns, segment_start_ns;
    bool timer_active;
    uint64_t control_generation, trace_epoch;
    uint64_t obs_eligible[2], obs_stored[2], obs_dropped[2];
    uint64_t obs_helper_calls;
} CPUArchState;

struct ArchCPU {
    CPUState parent_obj;
    CPUArchState env;
    uint8_t code[AGI_CODE_MAX + 1];
    char source_sha256[65];
    AgiEvent *events;
};

struct AgiCPUClass {
    CPUClass parent_class;
    DeviceRealize parent_realize;
    ResettablePhases parent_phases;
};

void agi_tcg_init(void);
void agi_cpu_translate_code(CPUState *cs, TranslationBlock *tb,
                            int *max_insns, vaddr pc, void *host_pc);
void agi_finish_clock(CPUArchState *env);
void agi_clear_observation(CPUArchState *env);
void agi_restart(CPUArchState *env);

static inline void cpu_get_tb_cpu_state(CPUArchState *env, vaddr *pc,
                                        uint64_t *cs_base, uint32_t *pflags)
{
    *pc = env->pc;
    *cs_base = 0;
    *pflags = env->obs_mask & AGI_OBS_MASK;
}

#include "exec/cpu-all.h"
#endif
