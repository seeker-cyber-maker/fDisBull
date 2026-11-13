/* SPDX-License-Identifier: MIT
 * Copyright (c) 2026 fDisBull contributors
 *
 * Authored Win64 leaf F(x,out): if unsigned x<=10, store/return x+constant;
 * otherwise return UINT64_MAX without writing out. It spills/restores RBX,
 * balances its local stack, and returns through the actual caller return word.
 * Main changes the reachable constant from 1 to 2 through a guest instruction.
 */
.intel_syntax noprefix
.text
.globl mainCRTStartup
mainCRTStartup:
    sub rsp, 40
    mov rcx, 3
    lea rdx, [rip + smc_output]
    call smc_gate
    mov qword ptr [rip + first_value], rax
    call smc_before_write
    call smc_writer
    call qword ptr [rip + __imp_GetCurrentProcess]
    mov rcx, rax
    lea rdx, [rip + smc_function]
    lea r8, [rip + smc_function_end]
    sub r8, rdx
    call qword ptr [rip + __imp_FlushInstructionCache]
    call smc_after_write
    mov rcx, 3
    lea rdx, [rip + smc_output]
    call smc_gate
    mov qword ptr [rip + second_value], rax
    mov rax, 0x8877665544332211
    mov qword ptr [rip + smc_output], rax
    mov rcx, 11
    lea rdx, [rip + smc_output]
    call smc_gate
    mov qword ptr [rip + rejected_value], rax
    mov rax, qword ptr [rip + smc_output]
    mov qword ptr [rip + rejected_output], rax
    call smc_done
    xor ecx, ecx
    call qword ptr [rip + __imp_ExitProcess]
    add rsp, 40
    ret

.p2align 5
.globl smc_checkpoint
.globl smc_before_write
smc_checkpoint:
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
    mov byte ptr [rip + smc_constant_immediate], 2
    ret

.data
.p2align 3
.globl smc_output
smc_output:
    .quad 0x8877665544332211
.globl first_value
first_value:
    .quad 0
.globl second_value
second_value:
    .quad 0
.globl rejected_value
rejected_value:
    .quad 0
.globl rejected_output
rejected_output:
    .quad 0

/* The fixture builder makes this dedicated main-image section ERW. The
 * return boundary sits in the same captured executable span as the function.
 */
.section .smc,"xrw"
.p2align 5
.globl smc_function
smc_function:
    sub rsp, 16
    mov qword ptr [rsp + 8], rbx
    mov rbx, rcx
    cmp rcx, 10
    ja smc_reject
.globl smc_constant
smc_constant:
    /* Exactly ten bytes: MOV EAX,1 followed by five ordinary NOPs. */
    .byte 0xb8
.globl smc_constant_immediate
smc_constant_immediate:
    .long 1
    .fill 5, 1, 0x90
    add rax, rcx
    mov qword ptr [rdx], rax
    jmp smc_epilogue
.globl smc_reject
smc_reject:
    mov rax, -1
.globl smc_epilogue
smc_epilogue:
    mov rbx, qword ptr [rsp + 8]
    add rsp, 16
    ret
.globl smc_function_end
smc_function_end:
.globl smc_gate
smc_gate:
    call smc_function
.globl smc_gate_return
smc_gate_return:
    nop
    ret

.section .drectve,"yn"
.ascii " /EXPORT:smc_function /EXPORT:smc_function_end /EXPORT:smc_constant"
.ascii " /EXPORT:smc_constant_immediate /EXPORT:smc_reject /EXPORT:smc_epilogue"
.ascii " /EXPORT:smc_gate /EXPORT:smc_gate_return /EXPORT:smc_writer"
.ascii " /EXPORT:smc_checkpoint /EXPORT:smc_before_write /EXPORT:smc_after_write /EXPORT:smc_done"
.ascii " /EXPORT:smc_output,DATA /EXPORT:first_value,DATA /EXPORT:second_value,DATA"
.ascii " /EXPORT:rejected_value,DATA /EXPORT:rejected_output,DATA"
