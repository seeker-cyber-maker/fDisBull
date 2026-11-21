/*
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Authored AGI observation experiment, using the fDisBull CHIP-8/QEMU scaffold.
 */
#ifndef AGI_CPU_H
#define AGI_CPU_H
#include "cpu-qom.h"
#include "decode.h"
#include "exec/cpu-defs.h"
#include "qapi/error.h"

#define CPU_RESOLVING_TYPE TYPE_AGI_CPU
#define AGI_ACTORS 16
#define AGI_EVENT_MAX 65536
#define AGI_PROFILE "agi-2917-scalar-position-pilot-1"
#define AGI_BINDING_PROFILE "agi-2917-view-binding-pilot-1"
#define AGI_INTENT_PROFILE "agi-2917-draw-intent-pilot-1"
#define AGI_CATALOG_MAX_BYTES 65536
#define AGI_CATALOG_MAX_LOOPS 1024
#define AGI_CATALOG_MAX_CELS 4096
#define AGI_OBS_DISASM 1
#define AGI_OBS_SCENE 2
#define AGI_OBS_MASK 3
#define AGI_TB_BINDING 4
#define AGI_TB_DRAW_INTENT 8
#define MMU_USER_IDX 0

typedef enum AgiStatus {
    AGI_READY, AGI_RUNNING, AGI_BUDGET, AGI_RETURN, AGI_FAULT, AGI_EXTERNAL,
    AGI_EFFECT
} AgiStatus;

typedef struct AgiActor {
    uint32_t x, y, prev_x, prev_y;
    uint32_t view_bound, view, loop, cel, width, height;
    uint32_t animated, update, cycling, ignore_horizon, update_pos;
    uint32_t view_replaced, motion, cycle, direction;
} AgiActor;

typedef struct AgiCatalogCel {
    uint32_t width, height;
} AgiCatalogCel;

typedef struct AgiCatalogLoop {
    uint32_t first_cel, cel_count;
} AgiCatalogLoop;

typedef struct AgiCatalogView {
    bool present;
    uint32_t first_loop, loop_count;
    char source_sha256[65];
} AgiCatalogView;

typedef struct AgiViewCatalog {
    uint32_t size, horizon, view_count, loop_count, cel_count;
    char sha256[65];
    AgiCatalogView views[256];
    AgiCatalogLoop loops[AGI_CATALOG_MAX_LOOPS];
    AgiCatalogCel cels[AGI_CATALOG_MAX_CELS];
} AgiViewCatalog;

enum { AGI_EVENT_RETIRE, AGI_EVENT_POSITION, AGI_EVENT_ACTOR, AGI_EVENT_VIEW_LOAD };
enum { AGI_PENDING_NONE, AGI_PENDING_DRAW };

typedef struct AgiEvent {
    uint64_t seq, retired, control_generation;
    uint32_t kind, pc, opcode, length, next_pc, actor;
    uint32_t resolved_value, resolved_x, resolved_y, before_loaded, after_loaded;
    AgiActor before, after;
} AgiEvent;

typedef struct CPUArchState {
    uint32_t v[256], f[256];
    AgiActor actors[AGI_ACTORS];
    uint32_t binding_profile, horizon, loaded_views[256];
    uint32_t draw_intent, pending_kind, pending_pc, pending_actor;
    /* Diagnostic scratch is neither architectural state nor a guest register. */
    AgiActor observed_actor;
    uint32_t observed_loaded;
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
    AgiViewCatalog *catalog;
    /* Immutable machine selection, restored to env at every guest restart. */
    bool draw_intent;
    /* Host-only static query selectors; restarting the guest preserves them. */
    uint32_t decode_pc, decode_limit;
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
bool agi_load_view_catalog(AgiCPU *cpu, const char *filename, Error **errp);

static inline void cpu_get_tb_cpu_state(CPUArchState *env, vaddr *pc,
                                        uint64_t *cs_base, uint32_t *pflags)
{
    *pc = env->pc;
    *cs_base = 0;
    *pflags = (env->obs_mask & AGI_OBS_MASK) |
              (env->binding_profile ? AGI_TB_BINDING : 0) |
              (env->draw_intent ? AGI_TB_DRAW_INTENT : 0);
}

#include "exec/cpu-all.h"
#endif
