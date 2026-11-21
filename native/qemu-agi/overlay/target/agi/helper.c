/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "qemu/osdep.h"
#include "qemu/timer.h"
#include "exec/exec-all.h"
#include "exec/helper-proto.h"
#include "system/runstate.h"
#include "cpu.h"

void agi_finish_clock(CPUArchState *env)
{
    if (env->timer_active) {
        env->elapsed_ns += get_clock() - env->segment_start_ns;
        env->timer_active = false;
    }
}

static G_NORETURN void agi_stop(CPUArchState *env, AgiStatus status)
{
    CPUState *cs = env_cpu(env);
    env->status = status;
    agi_finish_clock(env);
    /* A guest budget/return/fault is a VM pause, not a debugger trap. */
    vm_stop(RUN_STATE_PAUSED);
    cs->exception_index = EXCP_INTERRUPT;
    cpu_loop_exit(cs);
}

void helper_agi_fault(CPUArchState *env, uint32_t pc, uint32_t opcode,
                      uint32_t code)
{
    env->pc = pc;
    env->fault_code = code;
    env->fault_pc = pc;
    env->fault_opcode = opcode;
    agi_stop(env, AGI_FAULT);
}

void helper_agi_retire(CPUArchState *env, uint32_t returning)
{
    env->retired++;
    env->run_retired++;
    if (returning) {
        agi_stop(env, AGI_RETURN);
    }
    if (env->run_retired >= env->step_budget) {
        agi_stop(env, AGI_BUDGET);
    }
}

static void agi_append(CPUArchState *env, unsigned channel, uint32_t pc,
                       uint32_t meta, uint32_t actor, const AgiActor *before)
{
    AgiCPU *cpu = AGI_CPU(env_cpu(env));
    AgiEvent *event;
    uint64_t seq;

    env->obs_eligible[channel]++;
    seq = env->obs_eligible[0] + env->obs_eligible[1];
    if (env->obs_count >= env->obs_capacity) {
        env->obs_dropped[channel]++;
        return;
    }
    event = &cpu->events[env->obs_count++];
    memset(event, 0, sizeof(*event));
    event->seq = seq;
    event->retired = env->retired + 1;
    event->control_generation = env->control_generation;
    event->kind = channel;
    event->pc = pc;
    event->opcode = meta & 255;
    event->length = (meta >> 8) & 255;
    event->next_pc = env->pc;
    if (channel == 1) {
        event->actor = actor;
        event->before = *before;
        event->after = env->actors[actor];
    }
    env->obs_stored[channel]++;
}

void helper_agi_observe(CPUArchState *env, uint32_t pc, uint32_t meta,
                        uint32_t actor, uint32_t packed_before)
{
    unsigned mask = (meta >> 16) & AGI_OBS_MASK;
    env->obs_helper_calls++;
    if (mask & AGI_OBS_DISASM) {
        agi_append(env, 0, pc, meta, 0, NULL);
    }
    if ((mask & AGI_OBS_SCENE) && actor < AGI_ACTORS) {
        AgiActor before = {
            .x = packed_before & 255,
            .y = (packed_before >> 8) & 255,
            .prev_x = (packed_before >> 16) & 255,
            .prev_y = packed_before >> 24,
        };
        if (before.x != env->actors[actor].x ||
            before.y != env->actors[actor].y ||
            before.prev_x != env->actors[actor].prev_x ||
            before.prev_y != env->actors[actor].prev_y) {
            agi_append(env, 1, pc, meta, actor, &before);
        }
    }
}
