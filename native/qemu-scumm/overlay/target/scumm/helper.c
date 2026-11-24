/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "qemu/osdep.h"
#include "exec/exec-all.h"
#include "exec/helper-proto.h"
#include "system/runstate.h"
#include "cpu.h"
static G_NORETURN void pause_cpu(CPUArchState *env)
{
 CPUState *cs=env_cpu(env);vm_stop(RUN_STATE_PAUSED);
 cs->exception_index=EXCP_INTERRUPT;cpu_loop_exit(cs);
}
void helper_scumm_fetch_fault(CPUArchState *env)
{env->state.status=S_FAULT;env->state.fault=S_BAD_PC;pause_cpu(env);}
void helper_scumm_step(CPUArchState *env)
{
 ScummCPU *cpu=SCUMM_CPU(env_cpu(env));
 if(!scumm_step(env->version,cpu->code,env->code_size,&env->state,env->mask?cpu->trace:NULL))
  pause_cpu(env);
 ++env->run_retired;
 if(env->state.status==S_RETURN||env->state.status==S_WAIT)pause_cpu(env);
 if(env->run_retired>=env->budget){env->state.status=S_BUDGET;pause_cpu(env);}
}
