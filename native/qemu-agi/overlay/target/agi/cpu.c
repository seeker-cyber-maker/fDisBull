/*
 * SPDX-License-Identifier: GPL-2.0-or-later
 * QOM control/observation surface for the isolated AGI experiment.
 */
#include "qemu/osdep.h"
#include "qemu/timer.h"
#include "qapi/error.h"
#include "qapi/visitor.h"
#include "exec/exec-all.h"
#include "exec/cputlb.h"
#include "exec/helper-proto.h"
#include "gdbstub/helpers.h"
#include "hw/core/sysemu-cpu-ops.h"
#include "accel/tcg/cpu-ops.h"
#include "system/runstate.h"
#include "system/tcg.h"
#include "cpu.h"

static const char *const status_names[] = {
    "ready", "running", "budget", "return", "fault", "external"
};
static const char *const fault_names[] = {
    "none", "unsupported_opcode", "truncated_instruction", "invalid_actor",
    "invalid_branch_target", "unsupported_condition", "fetch_out_of_bounds",
    "condition_limit"
};

void agi_clear_observation(CPUArchState *env)
{
    env->obs_count = 0;
    memset(env->obs_eligible, 0, sizeof(env->obs_eligible));
    memset(env->obs_stored, 0, sizeof(env->obs_stored));
    memset(env->obs_dropped, 0, sizeof(env->obs_dropped));
    env->obs_helper_calls = 0;
    env->trace_epoch++;
}

void agi_restart(CPUArchState *env)
{
    memset(env->v, 0, sizeof(env->v));
    memset(env->f, 0, sizeof(env->f));
    memset(env->actors, 0, sizeof(env->actors));
    env->pc = 0;
    env->status = AGI_READY;
    env->fault_code = env->fault_pc = env->fault_opcode = 0;
    env->retired = env->run_retired = env->elapsed_ns = 0;
    env->timer_active = false;
    agi_clear_observation(env);
}

static bool agi_require_stopped(Object *obj, Error **errp)
{
    CPUState *cs = CPU(obj);
    if (!tcg_enabled() || runstate_is_running() ||
        qemu_get_cpu(0) != cs || qemu_get_cpu(1)) {
        error_setg(errp, "AGI_CONTROL_PRECONDITION: one stopped TCG CPU required");
        return false;
    }
    return true;
}

static bool agi_control_available(CPUArchState *env, Error **errp)
{
    if (env->control_generation == UINT64_MAX || env->trace_epoch == UINT64_MAX) {
        error_setg(errp, "AGI_CONTROL_PRECONDITION: generation exhausted");
        return false;
    }
    return true;
}

static void agi_get_uint(Object *obj, Visitor *v, const char *name,
                          void *opaque, Error **errp)
{
    CPUArchState *env = &AGI_CPU(obj)->env;
    unsigned field = (uintptr_t)opaque;
    uint64_t value;
    if (!agi_require_stopped(obj, errp)) {
        return;
    }
    value = field == 0 ? env->obs_mask :
            field == 1 ? env->obs_capacity : env->step_budget;
    visit_type_uint64(v, name, &value, errp);
}

static void agi_set_uint(Object *obj, Visitor *v, const char *name,
                          void *opaque, Error **errp)
{
    CPUArchState *env = &AGI_CPU(obj)->env;
    unsigned field = (uintptr_t)opaque;
    uint64_t value;
    if (!visit_type_uint64(v, name, &value, errp) ||
        !agi_require_stopped(obj, errp) || !agi_control_available(env, errp)) {
        return;
    }
    if ((field == 0 && value > AGI_OBS_MASK) ||
        (field == 1 && (value > AGI_EVENT_MAX || value < env->obs_count)) ||
        (field == 2 && (value == 0 || value > 1000000000))) {
        error_setg(errp, "AGI_CONTROL_PRECONDITION: invalid value for %s", name);
        return;
    }
    if (field == 0) {
        env->obs_mask = value;
    } else if (field == 1) {
        env->obs_capacity = value;
    } else {
        env->step_budget = value;
    }
    env->control_generation++;
    /* obs_mask participates in the TB key: cached variants remain valid. */
}

static void agi_set_restart(Object *obj, bool value, Error **errp)
{
    CPUArchState *env = &AGI_CPU(obj)->env;
    if (!value) {
        error_setg(errp, "AGI_CONTROL_PRECONDITION: restart accepts true only");
        return;
    }
    if (!agi_require_stopped(obj, errp) || !agi_control_available(env, errp)) {
        return;
    }
    agi_restart(env);
    CPU(obj)->exception_index = -1;
    CPU(obj)->halted = 0;
    env->control_generation++;
}

static void agi_set_clear(Object *obj, bool value, Error **errp)
{
    CPUArchState *env = &AGI_CPU(obj)->env;
    if (!value) {
        error_setg(errp, "AGI_CONTROL_PRECONDITION: clear accepts true only");
        return;
    }
    if (!agi_require_stopped(obj, errp) || !agi_control_available(env, errp)) {
        return;
    }
    agi_clear_observation(env);
    env->control_generation++;
}

static void agi_json_source(GString *s, AgiCPU *cpu)
{
    g_string_append_printf(s, "{\"sha256\":\"%s\",\"size\":%u,"
                           "\"logic_id\":0,\"profile\":\"%s\"}",
                           cpu->source_sha256, cpu->env.code_size, AGI_PROFILE);
}

static void agi_json_actor(GString *s, const AgiActor *a)
{
    g_string_append_printf(s, "{\"x\":%u,\"y\":%u,\"prev_x\":%u,"
                           "\"prev_y\":%u}", a->x, a->y, a->prev_x, a->prev_y);
}

static char *agi_get_state(Object *obj, Error **errp)
{
    AgiCPU *cpu = AGI_CPU(obj);
    CPUArchState *env = &cpu->env;
    GString *s;
    unsigned i;
    if (!agi_require_stopped(obj, errp)) {
        return NULL;
    }
    s = g_string_new("{\"schema\":\"fdisbull-agi-native-state-1\",\"source\":");
    agi_json_source(s, cpu);
    g_string_append_printf(s, ",\"guest\":{\"pc\":%u,\"variables\":[", env->pc);
    for (i = 0; i < 256; i++) {
        g_string_append_printf(s, "%s%u", i ? "," : "", env->v[i]);
    }
    g_string_append(s, "],\"flags\":[");
    for (i = 0; i < 256; i++) {
        g_string_append_printf(s, "%s%u", i ? "," : "", env->f[i]);
    }
    g_string_append(s, "],\"actors\":[");
    for (i = 0; i < AGI_ACTORS; i++) {
        const AgiActor *a = &env->actors[i];
        g_string_append_printf(s, "%s{\"id\":%u,\"x\":%u,\"y\":%u,"
                               "\"prev_x\":%u,\"prev_y\":%u}",
                               i ? "," : "", i, a->x, a->y, a->prev_x, a->prev_y);
    }
    g_string_append_printf(s, "],\"status\":\"%s\",\"fault\":",
                           status_names[env->status]);
    if (env->fault_code) {
        g_string_append_printf(s, "{\"code\":%u,\"name\":\"%s\","
                               "\"pc\":%u,\"opcode\":%u}",
                               env->fault_code, fault_names[env->fault_code],
                               env->fault_pc, env->fault_opcode);
    } else {
        g_string_append(s, "null");
    }
    g_string_append_printf(s, ",\"retired\":%" PRIu64 "},\"observation\":{"
                           "\"mask\":%u,\"capacity\":%u,\"count\":%u,"
                           "\"eligible\":%" PRIu64 ",\"dropped\":%" PRIu64
                           ",\"per_channel\":{",
                           env->retired, env->obs_mask, env->obs_capacity,
                           env->obs_count, env->obs_eligible[0] + env->obs_eligible[1],
                           env->obs_dropped[0] + env->obs_dropped[1]);
    for (i = 0; i < 2; i++) {
        g_string_append_printf(s, "%s\"%s\":{\"eligible\":%" PRIu64
                               ",\"stored\":%" PRIu64 ",\"dropped\":%" PRIu64 "}",
                               i ? "," : "", i ? "scene" : "disasm",
                               env->obs_eligible[i], env->obs_stored[i],
                               env->obs_dropped[i]);
    }
    g_string_append_printf(s, "},\"helper_calls\":%" PRIu64
                           ",\"control_generation\":%" PRIu64
                           ",\"epoch\":%" PRIu64 "},\"run\":{"
                           "\"retired\":%" PRIu64 ",\"elapsed_ns\":%" PRIu64
                           ",\"invocation\":%" PRIu64 "}}",
                           env->obs_helper_calls, env->control_generation,
                           env->trace_epoch, env->run_retired, env->elapsed_ns,
                           env->invocation);
    return g_string_free(s, false);
}

static char *agi_get_events(Object *obj, Error **errp)
{
    AgiCPU *cpu = AGI_CPU(obj);
    CPUArchState *env = &cpu->env;
    GString *s;
    unsigned i, j;
    if (!agi_require_stopped(obj, errp)) {
        return NULL;
    }
    s = g_string_new("{\"schema\":\"fdisbull-agi-native-events-1\",\"source\":");
    agi_json_source(s, cpu);
    g_string_append_printf(s, ",\"epoch\":%" PRIu64 ",\"events\":[", env->trace_epoch);
    for (i = 0; i < env->obs_count; i++) {
        const AgiEvent *e = &cpu->events[i];
        g_string_append_printf(s, "%s{\"seq\":%" PRIu64 ",\"kind\":\"%s\","
                               "\"control_generation\":%" PRIu64
                               ",\"pc\":%u,\"opcode\":%u,\"bytes\":[",
                               i ? "," : "", e->seq, e->kind ? "position" : "retire",
                               e->control_generation, e->pc, e->opcode);
        for (j = 0; j < e->length; j++) {
            g_string_append_printf(s, "%s%u", j ? "," : "", cpu->code[e->pc + j]);
        }
        g_string_append_printf(s, "],\"next_pc\":%u,\"retired\":%" PRIu64,
                               e->next_pc, e->retired);
        if (e->kind) {
            g_string_append_printf(s, ",\"actor\":%u,\"before\":", e->actor);
            agi_json_actor(s, &e->before);
            g_string_append(s, ",\"after\":");
            agi_json_actor(s, &e->after);
        }
        g_string_append_c(s, '}');
    }
    g_string_append(s, "]}");
    return g_string_free(s, false);
}

static vaddr agi_get_pc(CPUState *cs) { return AGI_CPU(cs)->env.pc; }
static void agi_set_pc(CPUState *cs, vaddr value) { AGI_CPU(cs)->env.pc = value; }
static void agi_sync_from_tb(CPUState *cs, const TranslationBlock *tb)
{
    AGI_CPU(cs)->env.pc = tb->pc;
}
static void agi_restore_state(CPUState *cs, const TranslationBlock *tb,
                               const uint64_t *data)
{
    AGI_CPU(cs)->env.pc = data[0];
}
static int agi_mmu_index(CPUState *cs, bool ifetch) { return MMU_USER_IDX; }
static bool agi_has_work(CPUState *cs) { return false; }
static bool agi_exec_interrupt(CPUState *cs, int request) { return false; }
static hwaddr agi_phys_debug(CPUState *cs, vaddr addr)
{
    return addr < AGI_CODE_MAX ? addr : (hwaddr)-1;
}

static bool agi_tlb_fill(CPUState *cs, vaddr addr, int size,
                         MMUAccessType access, int mmu_idx,
                         bool probe, uintptr_t retaddr)
{
    if (addr >= AGI_CODE_MAX || size < 1 ||
        (vaddr)size > AGI_CODE_MAX - addr || access == MMU_DATA_STORE) {
        if (!probe) {
            helper_agi_fault(cpu_env(cs), cpu_env(cs)->pc, 0, AGI_FAULT_FETCH);
        }
        return false;
    }
    tlb_set_page(cs, addr & TARGET_PAGE_MASK, addr & TARGET_PAGE_MASK,
                 PAGE_READ | PAGE_EXEC, mmu_idx, TARGET_PAGE_SIZE);
    return true;
}

static void agi_exec_enter(CPUState *cs)
{
    CPUArchState *env = cpu_env(cs);
    if (env->status == AGI_RETURN || env->status == AGI_FAULT) {
        env->run_retired = env->elapsed_ns = 0;
        env->invocation++;
        /* cpu_exec_enter precedes its setjmp: request, but do not longjmp. */
        vm_stop(RUN_STATE_PAUSED);
        cs->exception_index = EXCP_INTERRUPT;
        return;
    }
    if (env->status != AGI_RUNNING) {
        env->run_retired = env->elapsed_ns = 0;
        env->invocation++;
        env->status = AGI_RUNNING;
    }
    env->segment_start_ns = get_clock();
    env->timer_active = true;
}

static void agi_exec_exit(CPUState *cs)
{
    CPUArchState *env = cpu_env(cs);
    agi_finish_clock(env);
    if (env->status == AGI_RUNNING && (cs->stop || !runstate_is_running())) {
        env->status = AGI_EXTERNAL;
    }
}

static int agi_gdb_read(CPUState *cs, GByteArray *buf, int reg)
{
    return reg == 0 ? gdb_get_reg32(buf, cpu_env(cs)->pc) : 0;
}
static int agi_gdb_write(CPUState *cs, uint8_t *buf, int reg) { return 0; }
static const char *agi_gdb_arch(CPUState *cs) { return "agi"; }

static void agi_reset_hold(Object *obj, ResetType type)
{
    AgiCPUClass *acc = AGI_CPU_GET_CLASS(obj);
    if (acc->parent_phases.hold) {
        acc->parent_phases.hold(obj, type);
    }
    agi_restart(&AGI_CPU(obj)->env);
}

static void agi_realize(DeviceState *dev, Error **errp)
{
    CPUState *cs = CPU(dev);
    AgiCPUClass *acc = AGI_CPU_GET_CLASS(dev);
    Error *local_err = NULL;
    cpu_exec_realizefn(cs, &local_err);
    if (local_err) {
        error_propagate(errp, local_err);
        return;
    }
    qemu_init_vcpu(cs);
    cpu_reset(cs);
    acc->parent_realize(dev, errp);
}

static void agi_instance_init(Object *obj)
{
    AgiCPU *cpu = AGI_CPU(obj);
    cpu->events = g_new0(AgiEvent, AGI_EVENT_MAX);
    cpu->env.obs_capacity = 4096;
    cpu->env.step_budget = 1000000;
    object_property_add(obj, "agi-observation-mask", "uint64", agi_get_uint,
                         agi_set_uint, NULL, (void *)(uintptr_t)0);
    object_property_add(obj, "agi-observation-capacity", "uint64", agi_get_uint,
                         agi_set_uint, NULL, (void *)(uintptr_t)1);
    object_property_add(obj, "agi-step-budget", "uint64", agi_get_uint,
                         agi_set_uint, NULL, (void *)(uintptr_t)2);
    object_property_add_bool(obj, "agi-restart", NULL, agi_set_restart);
    object_property_add_bool(obj, "agi-observation-clear", NULL, agi_set_clear);
    object_property_add_str(obj, "agi-state-json", agi_get_state, NULL);
    object_property_add_str(obj, "agi-events-json", agi_get_events, NULL);
}

static void agi_instance_finalize(Object *obj) { g_free(AGI_CPU(obj)->events); }

static const struct SysemuCPUOps agi_sysemu_ops = {
    .has_work = agi_has_work,
    .get_phys_page_debug = agi_phys_debug,
};
static const TCGCPUOps agi_tcg_ops = {
    .initialize = agi_tcg_init,
    .translate_code = agi_cpu_translate_code,
    .synchronize_from_tb = agi_sync_from_tb,
    .restore_state_to_opc = agi_restore_state,
    .cpu_exec_enter = agi_exec_enter,
    .cpu_exec_exit = agi_exec_exit,
    .cpu_exec_halt = agi_has_work,
    .cpu_exec_interrupt = agi_exec_interrupt,
    .tlb_fill = agi_tlb_fill,
};

static void agi_class_init(ObjectClass *oc, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(oc);
    CPUClass *cc = CPU_CLASS(oc);
    AgiCPUClass *acc = AGI_CPU_CLASS(oc);
    ResettableClass *rc = RESETTABLE_CLASS(oc);
    device_class_set_parent_realize(dc, agi_realize, &acc->parent_realize);
    resettable_class_set_parent_phases(rc, NULL, agi_reset_hold, NULL,
                                       &acc->parent_phases);
    cc->mmu_index = agi_mmu_index;
    cc->get_pc = agi_get_pc;
    cc->set_pc = agi_set_pc;
    cc->gdb_read_register = agi_gdb_read;
    cc->gdb_write_register = agi_gdb_write;
    cc->gdb_core_xml_file = "agi-core.xml";
    cc->gdb_arch_name = agi_gdb_arch;
    cc->tcg_ops = &agi_tcg_ops;
    cc->sysemu_ops = &agi_sysemu_ops;
}

static const TypeInfo agi_cpu_type = {
    .name = TYPE_AGI_CPU,
    .parent = TYPE_CPU,
    .instance_size = sizeof(AgiCPU),
    .instance_init = agi_instance_init,
    .instance_finalize = agi_instance_finalize,
    .class_size = sizeof(AgiCPUClass),
    .class_init = agi_class_init,
};
static void agi_register_types(void) { type_register_static(&agi_cpu_type); }
type_init(agi_register_types)
