/* SPDX-License-Identifier: MIT
 * Copyright (c) 2026 fDisBull contributors
 *
 * Homegrown no-CRT/no-TLS Win64 module. Its entry initializes ordinary data,
 * reads the PE-initialized input (3), runs accepted and rejected paths of the
 * nested-call self-modifying function, round-trips thread last-error state
 * through the real SetLastError/GetLastError imports, and calls ExitProcess(7).
 * Expected outputs: accepted pair {4,5}, return 5; rejected sentinel pair
 * unchanged, return UINT64_MAX; observed last-error 0x1234; process exit 7.
 * Initialization deliberately overwrites nonzero PE defaults, so source data
 * initialization and instructions that initialize runtime state remain distinct.
 * Build this dedicated .smc section ERW. No target or external DLL code is
 * copied here: the three imports resolve through the platform loader.
 */
.intel_syntax noprefix
.section .smc,"xrw"
.p2align 5
.globl mainCRTStartup
.globl smc_module_entry
mainCRTStartup:
smc_module_entry:
    sub rsp, 40
    mov rax, 0x8877665544332211
    mov qword ptr [rip + smc_output], rax
    mov qword ptr [rip + rejected_output], rax
    mov rax, 0x1122334455667788
    mov qword ptr [rip + smc_output + 8], rax
    mov qword ptr [rip + rejected_output + 8], rax
    mov qword ptr [rip + accepted_value], 0
    mov qword ptr [rip + rejected_value], 0
    mov qword ptr [rip + observed_last_error], 0
    mov rcx, qword ptr [rip + smc_input]
    lea rdx, [rip + smc_output]
    call smc_function
.globl smc_module_accepted_return
smc_module_accepted_return:
    mov qword ptr [rip + accepted_value], rax
    mov rcx, 11
    lea rdx, [rip + rejected_output]
    call smc_function
.globl smc_module_rejected_return
smc_module_rejected_return:
    mov qword ptr [rip + rejected_value], rax
    mov ecx, 0x1234
.globl smc_set_last_error_call
smc_set_last_error_call:
    call qword ptr [rip + __imp_SetLastError]
.globl smc_set_last_error_return
smc_set_last_error_return:
.globl smc_get_last_error_call
smc_get_last_error_call:
    call qword ptr [rip + __imp_GetLastError]
.globl smc_get_last_error_return
smc_get_last_error_return:
    mov dword ptr [rip + observed_last_error], eax
    mov ecx, 7
.globl smc_module_before_exit
smc_module_before_exit:
    nop
.globl smc_exit_process_call
smc_exit_process_call:
    call qword ptr [rip + __imp_ExitProcess]
.globl smc_module_unreachable
smc_module_unreachable:
    ud2

.globl smc_function
smc_function:
    sub rsp, 24
    mov qword ptr [rsp + 16], rbx
    mov rbx, rcx
    cmp rcx, 10
    ja smc_reject
    call smc_value
.globl smc_first_return
smc_first_return:
    mov qword ptr [rdx], rax
    call smc_prepare
.globl smc_prepare_return
smc_prepare_return:
    call smc_value
.globl smc_second_return
smc_second_return:
    mov qword ptr [rdx + 8], rax
    jmp smc_epilogue
.globl smc_reject
smc_reject:
    mov rax, -1
.globl smc_epilogue
smc_epilogue:
    mov rbx, qword ptr [rsp + 16]
    add rsp, 24
    ret
.globl smc_prepare
smc_prepare:
    call smc_writer
.globl smc_writer_return
smc_writer_return:
    ret
.globl smc_writer
smc_writer:
    mov byte ptr [rip + smc_constant_immediate], 2
.globl smc_after_store
smc_after_store:
    ret
.globl smc_value
.globl smc_constant
smc_value:
smc_constant:
    .byte 0xb8
.globl smc_constant_immediate
smc_constant_immediate:
    .long 1
    .fill 5, 1, 0x90
    add rax, rcx
    ret
.globl smc_function_end
.globl smc_module_end
smc_function_end:
smc_module_end:

.data
.p2align 3
.globl smc_data_start
.globl smc_input
smc_data_start:
smc_input:
    .quad 3
.globl smc_output
smc_output:
    .quad 0xaaaaaaaaaaaaaaaa
    .quad 0xbbbbbbbbbbbbbbbb
.globl rejected_output
rejected_output:
    .quad 0xcccccccccccccccc
    .quad 0xdddddddddddddddd
.globl accepted_value
accepted_value:
    .quad 0xeeeeeeeeeeeeeeee
.globl rejected_value
rejected_value:
    .quad 0xffffffffffffffff
.globl observed_last_error
observed_last_error:
    .quad 0x5555555555555555
.globl smc_data_end
smc_data_end:

.section .drectve,"yn"
.ascii " /EXPORT:smc_module_entry /EXPORT:smc_module_end /EXPORT:smc_module_before_exit"
.ascii " /EXPORT:smc_module_accepted_return /EXPORT:smc_module_rejected_return /EXPORT:smc_module_unreachable"
.ascii " /EXPORT:smc_set_last_error_call /EXPORT:smc_set_last_error_return"
.ascii " /EXPORT:smc_get_last_error_call /EXPORT:smc_get_last_error_return /EXPORT:smc_exit_process_call"
.ascii " /EXPORT:smc_function /EXPORT:smc_function_end /EXPORT:smc_constant /EXPORT:smc_constant_immediate"
.ascii " /EXPORT:smc_value /EXPORT:smc_reject /EXPORT:smc_epilogue /EXPORT:smc_writer /EXPORT:smc_prepare"
.ascii " /EXPORT:smc_first_return /EXPORT:smc_prepare_return /EXPORT:smc_second_return"
.ascii " /EXPORT:smc_writer_return /EXPORT:smc_after_store"
.ascii " /EXPORT:smc_data_start,DATA /EXPORT:smc_data_end,DATA /EXPORT:smc_input,DATA"
.ascii " /EXPORT:smc_output,DATA /EXPORT:rejected_output,DATA /EXPORT:accepted_value,DATA"
.ascii " /EXPORT:rejected_value,DATA /EXPORT:observed_last_error,DATA"
