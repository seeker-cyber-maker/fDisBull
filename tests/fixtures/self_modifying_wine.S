/* SPDX-License-Identifier: MIT
 * Copyright (c) 2026 fDisBull contributors
 *
 * Authored PE64 self-modification fixture. Main observes the physical victim
 * immediate, executes it, writes a new immediate through a separate text page,
 * flushes the Windows instruction cache, then executes the changed victim.
 * smc_self_writer is an additional explicit debugger-only probe: its effective
 * immediate can rewrite its own original guarded byte. Main never calls it.
 */
.intel_syntax noprefix
.text
.globl mainCRTStartup
mainCRTStartup:
    sub rsp, 40
    call smc_begin
    movzx eax, byte ptr [rip + smc_target + 1]
    mov dword ptr [rip + data_read], eax
    call smc_target
    mov dword ptr [rip + first_value], eax
    call smc_before_write
    call smc_writer
    call qword ptr [rip + __imp_GetCurrentProcess]
    mov rcx, rax
    lea rdx, [rip + smc_target]
    mov r8d, 6
    call qword ptr [rip + __imp_FlushInstructionCache]
    call smc_after_write
    call smc_target
    mov dword ptr [rip + second_value], eax
    call smc_done
    xor ecx, ecx
    call qword ptr [rip + __imp_ExitProcess]
    /* ExitProcess does not return; retain a balanced fallback epilogue. */
    add rsp, 40
    ret

/* Marker entries remain outside every writer patch's 15-byte guard window. */
.p2align 5
.globl smc_begin
smc_begin:
    nop
    ret
.p2align 5
.globl smc_before_write
smc_before_write:
    nop
    ret
.p2align 5
.globl smc_after_write
smc_after_write:
    nop
    ret
.p2align 5
.globl smc_done
smc_done:
    nop
    ret

.p2align 5
.globl smc_writer
smc_writer:
    mov byte ptr [rip + smc_target + 1], 2
.globl smc_writer_immediate
.set smc_writer_immediate, . - 1
    ret

.data
.p2align 2
.globl data_read
data_read:
    .long 0
.globl first_value
first_value:
    .long 0
.globl second_value
second_value:
    .long 0

/* The linker additionally sets this dedicated page to execute/read/write. */
.section .smc,"xrw"
.p2align 5
.globl smc_target
smc_target:
    mov eax, 1
    ret
.p2align 5
.globl smc_self_writer
smc_self_writer:
    mov byte ptr [rip + smc_self_writer + 6], 1
.globl smc_self_writer_immediate
.set smc_self_writer_immediate, . - 1
    ret

.section .drectve,"yn"
.ascii " /EXPORT:smc_target /EXPORT:smc_writer /EXPORT:smc_writer_immediate"
.ascii " /EXPORT:smc_begin /EXPORT:smc_before_write /EXPORT:smc_after_write /EXPORT:smc_done"
.ascii " /EXPORT:smc_self_writer /EXPORT:smc_self_writer_immediate"
.ascii " /EXPORT:data_read,DATA /EXPORT:first_value,DATA /EXPORT:second_value,DATA"
