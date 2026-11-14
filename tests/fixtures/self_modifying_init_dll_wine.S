/* SPDX-License-Identifier: MIT
 * Copyright (c) 2026 fDisBull contributors
 *
 * Homegrown SMCINIT.dll, loaded through the real PE loader. The genuine PE64
 * TLS directory invokes dll_tls_callback before DllMain process attach. These
 * callbacks append process events and change a future MOV immediate 1->2->3.
 * dll_report records the EXE's later call and returns the modified constant.
 * Thread notifications are ignored. Process detach callbacks append distinct
 * events; their observed order is evidence, not an assumed source contract.
 * No imports, CRT, heap, I/O, or external DLL implementation is included here.
 */
.intel_syntax noprefix

.macro APPEND_EVENT marker
    mov eax, dword ptr [rip + dll_event_count]
    lea r9, [rip + dll_event_log]
    mov dword ptr [r9 + rax*4], \marker
    add eax, 1
    mov dword ptr [rip + dll_event_count], eax
.endm

.section .smc,"xrw"
.p2align 5
.globl dll_code_start
.globl dll_tls_callback
dll_code_start:
dll_tls_callback:
    cmp edx, 1
    je dll_tls_attach
    test edx, edx
    je dll_tls_detach
    ret
.globl dll_tls_attach
dll_tls_attach:
    APPEND_EVENT 0x11
.globl dll_tls_attach_logged
dll_tls_attach_logged:
    mov dword ptr [rip + dll_stage], 1
    mov byte ptr [rip + dll_report_constant_immediate], 2
.globl dll_tls_attached
dll_tls_attached:
    nop
    ret
.globl dll_tls_detach
dll_tls_detach:
    mov eax, dword ptr [rip + dll_stage]
    mov dword ptr [rip + dll_tls_detach_stage_seen], eax
    APPEND_EVENT 0x44
.globl dll_tls_detach_logged
dll_tls_detach_logged:
    or dword ptr [rip + dll_detach_flag], 1
.globl dll_tls_detached
dll_tls_detached:
    nop
    ret

.globl DllMain
.globl dll_entry
DllMain:
dll_entry:
    cmp edx, 1
    je dll_process_attach
    test edx, edx
    je dll_process_detach
    mov eax, 1
    ret
.globl dll_process_attach
dll_process_attach:
    mov eax, dword ptr [rip + dll_stage]
    mov dword ptr [rip + dll_seen_stage], eax
    APPEND_EVENT 0x22
.globl dll_attach_logged
dll_attach_logged:
    mov dword ptr [rip + dll_stage], 2
    mov byte ptr [rip + dll_report_constant_immediate], 3
.globl dll_attached
dll_attached:
    nop
    mov eax, 1
    ret
.globl dll_process_detach
dll_process_detach:
    mov eax, dword ptr [rip + dll_stage]
    mov dword ptr [rip + dll_dllmain_detach_stage_seen], eax
    APPEND_EVENT 0x55
.globl dll_detach_logged
dll_detach_logged:
    or dword ptr [rip + dll_detach_flag], 2
.globl dll_detached
dll_detached:
    nop
    mov eax, 1
    ret

.globl dll_report
dll_report:
    mov eax, dword ptr [rip + dll_stage]
    mov dword ptr [rip + dll_report_stage_seen], eax
    mov eax, dword ptr [rip + dll_event_count]
    mov dword ptr [rip + dll_report_count_seen], eax
    APPEND_EVENT 0x33
.globl dll_report_logged
dll_report_logged:
    mov dword ptr [rip + dll_stage], 3
.globl dll_report_constant
dll_report_constant:
    .byte 0xb8
.globl dll_report_constant_immediate
dll_report_constant_immediate:
    .long 1
.globl dll_report_return
dll_report_return:
    ret
.globl dll_code_end
dll_code_end:

.data
.p2align 3
.globl dll_data_start
.globl dll_event_count
dll_data_start:
dll_event_count:
    .long 0
.globl dll_stage
dll_stage:
    .long 0
.globl dll_seen_stage
dll_seen_stage:
    .long 0
.globl dll_detach_flag
dll_detach_flag:
    .long 0
.globl dll_report_stage_seen
dll_report_stage_seen:
    .long 0
.globl dll_report_count_seen
dll_report_count_seen:
    .long 0
.globl dll_tls_detach_stage_seen
dll_tls_detach_stage_seen:
    .long 0
.globl dll_dllmain_detach_stage_seen
dll_dllmain_detach_stage_seen:
    .long 0
.globl dll_event_log
dll_event_log:
    .fill 8, 4, 0
.globl dll_data_end
dll_data_end:
.p2align 2
.globl dll_tls_index
dll_tls_index:
    .long 0

/* The loader writes dll_tls_index and calls the callback array. Keep all TLS
 * directory fields as genuine relocated VAs, not an authored callback harness.
 */
.section .tls$AAA,"dw"
.globl dll_tls_start
dll_tls_start:
    .byte 0
.section .tls$ZZZ,"dw"
.globl dll_tls_end
dll_tls_end:
    .byte 0
.section .CRT$XLA,"dw"
dll_tls_callbacks_begin:
    .quad 0
.section .CRT$XLB,"dw"
.globl dll_tls_callbacks
dll_tls_callbacks:
    .quad dll_tls_callback
.section .CRT$XLZ,"dw"
    .quad 0
.section .rdata,"dr"
.p2align 3
.globl _tls_used
_tls_used:
    .quad dll_tls_start
    .quad dll_tls_end
    .quad dll_tls_index
    .quad dll_tls_callbacks
    .long 0
    .long 0

.section .drectve,"yn"
.ascii " /INCLUDE:_tls_used"
.ascii " /EXPORT:dll_report /EXPORT:dll_report_constant /EXPORT:dll_report_constant_immediate /EXPORT:dll_report_return"
.ascii " /EXPORT:dll_code_start /EXPORT:dll_code_end /EXPORT:dll_tls_callback /EXPORT:dll_entry"
.ascii " /EXPORT:dll_tls_attach /EXPORT:dll_tls_attach_logged /EXPORT:dll_tls_attached"
.ascii " /EXPORT:dll_tls_detach /EXPORT:dll_tls_detach_logged /EXPORT:dll_tls_detached"
.ascii " /EXPORT:dll_process_attach /EXPORT:dll_attach_logged /EXPORT:dll_attached"
.ascii " /EXPORT:dll_process_detach /EXPORT:dll_detach_logged /EXPORT:dll_detached /EXPORT:dll_report_logged"
.ascii " /EXPORT:dll_data_start,DATA /EXPORT:dll_data_end,DATA /EXPORT:dll_event_count,DATA /EXPORT:dll_event_log,DATA"
.ascii " /EXPORT:dll_stage,DATA /EXPORT:dll_seen_stage,DATA /EXPORT:dll_detach_flag,DATA"
.ascii " /EXPORT:dll_report_stage_seen,DATA /EXPORT:dll_report_count_seen,DATA"
.ascii " /EXPORT:dll_tls_detach_stage_seen,DATA /EXPORT:dll_dllmain_detach_stage_seen,DATA"
.ascii " /EXPORT:dll_tls_index,DATA /EXPORT:dll_tls_callbacks,DATA"
