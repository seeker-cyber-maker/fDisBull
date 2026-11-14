/* SPDX-License-Identifier: MIT
 * Copyright (c) 2026 fDisBull contributors
 *
 * Homegrown no-CRT EXE imports SMCINIT.dll through the genuine PE import table.
 * DLL TLS/process attach must occur before this entry. dll_report appends the
 * 0x33 event and returns its loader-modified constant (3). The EXE round-trips
 * DWORD values 0, 1, 0xffffffff, and 0x1234 through the last-error API pair,
 * stores all four results, and terminates via ExitProcess(7).
 */
.intel_syntax noprefix
.macro API_PAIR index, value
    mov ecx, \value
.globl smc_set_last_error_call_\index
smc_set_last_error_call_\index:
.if \index == 3
.globl smc_set_last_error_call
smc_set_last_error_call:
.endif
    call qword ptr [rip + __imp_SetLastError]
.globl smc_set_last_error_return_\index
.globl smc_get_last_error_call_\index
smc_set_last_error_return_\index:
smc_get_last_error_call_\index:
.if \index == 3
.globl smc_set_last_error_return
.globl smc_get_last_error_call
smc_set_last_error_return:
smc_get_last_error_call:
.endif
    call qword ptr [rip + __imp_GetLastError]
.globl smc_get_last_error_return_\index
smc_get_last_error_return_\index:
.if \index == 3
.globl smc_get_last_error_return
smc_get_last_error_return:
.endif
    mov dword ptr [rip + api_results + \index*4], eax
.endm
.section .smc,"xrw"
.p2align 5
.globl mainCRTStartup
.globl smc_module_entry
mainCRTStartup:
smc_module_entry:
    sub rsp, 40
    mov dword ptr [rip + module_entry_seen], 1
    mov qword ptr [rip + observed_last_error], 0
.globl smc_dll_report_call
smc_dll_report_call:
    call qword ptr [rip + __imp_dll_report]
.globl smc_dll_report_return
smc_dll_report_return:
    mov dword ptr [rip + observed_dll_report], eax
    API_PAIR 0, 0
    API_PAIR 1, 1
    API_PAIR 2, 0xffffffff
    API_PAIR 3, 0x1234
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
.globl smc_module_end
smc_module_end:

.data
.p2align 3
.globl smc_data_start
.globl module_entry_seen
smc_data_start:
module_entry_seen:
    .long 0
.globl observed_dll_report
observed_dll_report:
    .long 0xaaaaaaaa
.globl observed_last_error
observed_last_error:
    .quad 0xbbbbbbbbbbbbbbbb
.globl api_results
api_results:
    .fill 4, 4, 0xcccccccc
.globl smc_data_end
smc_data_end:

.section .drectve,"yn"
.ascii " /EXPORT:smc_module_entry /EXPORT:smc_module_end /EXPORT:smc_module_before_exit /EXPORT:smc_module_unreachable"
.ascii " /EXPORT:smc_dll_report_call /EXPORT:smc_dll_report_return"
.ascii " /EXPORT:smc_set_last_error_call /EXPORT:smc_set_last_error_return"
.ascii " /EXPORT:smc_get_last_error_call /EXPORT:smc_get_last_error_return /EXPORT:smc_exit_process_call"
.ascii " /EXPORT:smc_set_last_error_call_0 /EXPORT:smc_set_last_error_return_0 /EXPORT:smc_get_last_error_call_0 /EXPORT:smc_get_last_error_return_0"
.ascii " /EXPORT:smc_set_last_error_call_1 /EXPORT:smc_set_last_error_return_1 /EXPORT:smc_get_last_error_call_1 /EXPORT:smc_get_last_error_return_1"
.ascii " /EXPORT:smc_set_last_error_call_2 /EXPORT:smc_set_last_error_return_2 /EXPORT:smc_get_last_error_call_2 /EXPORT:smc_get_last_error_return_2"
.ascii " /EXPORT:smc_set_last_error_call_3 /EXPORT:smc_set_last_error_return_3 /EXPORT:smc_get_last_error_call_3 /EXPORT:smc_get_last_error_return_3"
.ascii " /EXPORT:smc_data_start,DATA /EXPORT:smc_data_end,DATA /EXPORT:module_entry_seen,DATA"
.ascii " /EXPORT:observed_dll_report,DATA /EXPORT:observed_last_error,DATA /EXPORT:api_results,DATA"
