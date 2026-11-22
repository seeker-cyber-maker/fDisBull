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

/* The runtime TB is an operand-free native trampoline. Its immutable ROM
 * byte never changes; the canonical decoder reads the immutable LOGIC bank
 * in the semantic helper at the actual architectural LOGIC/PC. Consequently
 * cached TBs cannot retain bytes from another LOGIC or scan-start context. */
void helper_agi_runtime(CPUArchState *env, uint32_t mask)
{
    AgiRuntime *r = AGI_CPU(env_cpu(env))->runtime;
    int result;
    g_assert(r && r->obs_mask == mask && env->runtime_profile);
    result = agi_runtime_step(r);
    env->pc = 0;
    env->retired = r->state.retired;
    env->run_retired = r->run_retired;
    if (result < 0) agi_stop(env, AGI_FAULT);
    if (r->state.status == AGI_RT_PENDING) agi_stop(env, AGI_EFFECT);
    if (r->state.status == AGI_RT_RETURN || r->state.status == AGI_RT_QUIT) agi_stop(env, AGI_RETURN);
    if (r->run_retired >= env->step_budget) {
        r->state.status = AGI_RT_BUDGET;
        agi_stop(env, AGI_BUDGET);
    }
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

/* The nominal DOS 2.917 rule qualifies horizon repair inside top-edge repair.
 * In particular, an already-valid top edge below the horizon is left alone.
 * Geometry changes do not update the remembered position coordinates.
 */
static void agi_bind_geometry(CPUArchState *env, AgiActor *actor,
                              const AgiCatalogCel *cel)
{
    actor->width = cel->width;
    actor->height = cel->height;
    if (actor->x + actor->width > 160) {
        actor->x = 160 - actor->width;
        actor->update_pos = 1;
    }
    if (actor->y + 1 < actor->height) {
        actor->y = actor->height - 1;
        actor->update_pos = 1;
        if (actor->y <= env->horizon && !actor->ignore_horizon) {
            actor->y = env->horizon + 1;
        }
    }
}

/* This is a semantic helper, present independently of observation controls.
 * Validate on a private candidate before committing any architectural change.
 */
void helper_agi_binding(CPUArchState *env, uint32_t pc, uint32_t meta,
                        uint32_t a, uint32_t b)
{
    AgiCPU *cpu = AGI_CPU(env_cpu(env));
    const AgiViewCatalog *catalog = cpu->catalog;
    const AgiCatalogView *view;
    const AgiCatalogLoop *loop;
    AgiActor candidate;
    uint32_t op = meta & 255;
    uint32_t mask = (meta >> 16) & AGI_OBS_MASK;
    uint32_t value;

    g_assert(catalog && env->binding_profile);
    if (op == 30 || op == 31) {
        value = op == 30 ? a : env->v[a];
        if (!catalog->views[value].present) {
            helper_agi_fault(env, pc, op, AGI_FAULT_MISSING_VIEW);
        }
        if (mask & AGI_OBS_SCENE) {
            env->observed_loaded = env->loaded_views[value];
        }
        env->loaded_views[value] = 1;
        return;
    }
    if (a >= AGI_ACTORS) {
        helper_agi_fault(env, pc, op, AGI_FAULT_ACTOR);
    }
    candidate = env->actors[a];
    if (op == 70 || op == 71) {
        g_assert(env->draw_intent);
        candidate.cycling = op == 71;
        goto commit;
    }
    if (op == 33) {
        if (!candidate.animated) {
            candidate.animated = candidate.update = candidate.cycling = 1;
            candidate.ignore_horizon = candidate.update_pos = 0;
            candidate.motion = candidate.cycle = candidate.direction = 0;
        }
        goto commit;
    }
    value = (op == 42 || op == 44 || op == 48) ? env->v[b] : b;
    if (op == 41 || op == 42) {
        if (!catalog->views[value].present) {
            helper_agi_fault(env, pc, op, AGI_FAULT_MISSING_VIEW);
        }
        if (!env->loaded_views[value]) {
            helper_agi_fault(env, pc, op, AGI_FAULT_VIEW_NOT_LOADED);
        }
        candidate.view_bound = 1;
        candidate.view = value;
        candidate.view_replaced = 1;
        view = &catalog->views[value];
        if (candidate.loop >= view->loop_count) {
            candidate.loop = 0;
        }
    } else {
        if (!candidate.view_bound) {
            helper_agi_fault(env, pc, op, AGI_FAULT_VIEW_UNBOUND);
        }
        if (!env->loaded_views[candidate.view]) {
            helper_agi_fault(env, pc, op, AGI_FAULT_VIEW_NOT_LOADED);
        }
        view = &catalog->views[candidate.view];
        if (op == 43 || op == 44) {
            if (value >= view->loop_count) {
                helper_agi_fault(env, pc, op, AGI_FAULT_LOOP);
            }
            candidate.loop = value;
        } else {
            g_assert(op == 47 || op == 48);
        }
    }
    loop = &catalog->loops[view->first_loop + candidate.loop];
    if (!loop->cel_count) {
        helper_agi_fault(env, pc, op, AGI_FAULT_EMPTY_LOOP);
    }
    if (op == 47 || op == 48) {
        if (value >= loop->cel_count) {
            helper_agi_fault(env, pc, op, AGI_FAULT_CEL);
        }
        candidate.cel = value;
    } else if (candidate.cel >= loop->cel_count) {
        candidate.cel = 0;
    }
    agi_bind_geometry(env, &candidate,
                      &catalog->cels[loop->first_cel + candidate.cel]);
commit:
    if (mask & AGI_OBS_SCENE) {
        env->observed_actor = env->actors[a];
    }
    env->actors[a] = candidate;
}

/* Reaching draw is architectural intent, not completion of engine effects.
 * Validate its existing pose without changing coordinates, even off canvas.
 * The complete stopped actor/catalog snapshot supplies the pending inputs.
 */
void helper_agi_draw(CPUArchState *env, uint32_t pc, uint32_t actor)
{
    AgiCPU *cpu = AGI_CPU(env_cpu(env));
    const AgiViewCatalog *catalog = cpu->catalog;
    const AgiActor *a;
    const AgiCatalogView *view;
    const AgiCatalogLoop *loop;
    const AgiCatalogCel *cel;

    g_assert(catalog && env->binding_profile && env->draw_intent);
    if (actor >= AGI_ACTORS) {
        helper_agi_fault(env, pc, 35, AGI_FAULT_ACTOR);
    }
    a = &env->actors[actor];
    if (!a->view_bound) {
        helper_agi_fault(env, pc, 35, AGI_FAULT_VIEW_UNBOUND);
    }
    view = &catalog->views[a->view];
    if (!view->present) {
        helper_agi_fault(env, pc, 35, AGI_FAULT_MISSING_VIEW);
    }
    if (!env->loaded_views[a->view]) {
        helper_agi_fault(env, pc, 35, AGI_FAULT_VIEW_NOT_LOADED);
    }
    if (a->loop >= view->loop_count) {
        helper_agi_fault(env, pc, 35, AGI_FAULT_LOOP);
    }
    loop = &catalog->loops[view->first_loop + a->loop];
    if (!loop->cel_count) {
        helper_agi_fault(env, pc, 35, AGI_FAULT_EMPTY_LOOP);
    }
    if (a->cel >= loop->cel_count) {
        helper_agi_fault(env, pc, 35, AGI_FAULT_CEL);
    }
    cel = &catalog->cels[loop->first_cel + a->cel];
    /* Every admitted binding updates these cached dimensions atomically. */
    g_assert(a->width == cel->width && a->height == cel->height);
    env->pending_kind = AGI_PENDING_DRAW;
    env->pending_pc = pc;
    env->pending_actor = actor;
    env->pc = pc;
    agi_stop(env, AGI_EFFECT);
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
    event->kind = channel == 0 ? AGI_EVENT_RETIRE :
                  !env->binding_profile ? AGI_EVENT_POSITION :
                  ((meta & 255) == 30 || (meta & 255) == 31) ?
                  AGI_EVENT_VIEW_LOAD : AGI_EVENT_ACTOR;
    event->pc = pc;
    event->opcode = meta & 255;
    event->length = (meta >> 8) & 255;
    event->next_pc = env->pc;
    if (event->kind == AGI_EVENT_VIEW_LOAD) {
        event->actor = actor;
        event->before_loaded = env->observed_loaded;
        event->after_loaded = env->loaded_views[actor];
    } else if (channel == 1) {
        event->actor = actor;
        event->before = *before;
        event->after = env->actors[actor];
    } else if (env->binding_profile) {
        /* These commands leave variables unchanged. Resolve at retirement,
         * never when a later QOM read serializes the buffered event.
         */
        switch (event->opcode) {
        case 30:
        case 31:
            actor = cpu->code[pc + 1];
            event->resolved_value = event->opcode == 30 ? actor : env->v[actor];
            break;
        case 41:
        case 42:
        case 43:
        case 44:
        case 47:
        case 48:
            actor = cpu->code[pc + 2];
            event->resolved_value = (event->opcode & 1) ? actor : env->v[actor];
            break;
        case 37:
        case 38:
            actor = cpu->code[pc + 1];
            event->resolved_x = env->actors[actor].x;
            event->resolved_y = env->actors[actor].y;
            break;
        }
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
    if ((mask & AGI_OBS_SCENE) && env->binding_profile) {
        uint32_t op = meta & 255;
        if (op == 30 || op == 31) {
            AgiCPU *cpu = AGI_CPU(env_cpu(env));
            uint32_t view = cpu->code[pc + 1];
            if (op == 31) {
                view = env->v[view];
            }
            if (env->observed_loaded != env->loaded_views[view]) {
                agi_append(env, 1, pc, meta, view, NULL);
            }
        } else if (actor < AGI_ACTORS &&
                   memcmp(&env->observed_actor, &env->actors[actor],
                          sizeof(AgiActor))) {
            agi_append(env, 1, pc, meta, actor, &env->observed_actor);
        }
    } else if ((mask & AGI_OBS_SCENE) && actor < AGI_ACTORS) {
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
