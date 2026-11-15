/* SPDX-License-Identifier: MIT
 * Copyright (c) 2026 fDisBull contributors
 *
 * Authored Win64 function with internal calls and execution-time mutation:
 *   F(x,out): if unsigned x>10 return UINT64_MAX, leaving out untouched.
 *   Otherwise out[0]=value(x); prepare(); out[1]=value(x); return out[1].
 *   value(x) returns x+constant. prepare calls writer, which changes constant
 *   from 1 to 2 in the value helper's MOV immediate. Thus the same instruction
 *   executes before and after its bytes change within one invocation of F.
 * F spills/restores RBX. Every CALL and RET uses the actual ordinary-RAM stack.
 * The fixture builder makes the dedicated .smc section ERW.
 */
.intel_syntax noprefix
.text
.globl mainCRTStartup
mainCRTStartup:
    sub rsp, 40
    call smc_before_write
    mov rcx, 3
    lea rdx, [rip + smc_output]
    call smc_gate
    mov qword ptr [rip + first_value], rax
    call smc_after_write
    mov rcx, 11
    lea rdx, [rip + rejected_output]
    call smc_gate
    mov qword ptr [rip + rejected_value], rax
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

.data
.p2align 3
.globl smc_output
smc_output:
    .quad 0x8877665544332211
    .quad 0x1122334455667788
.globl first_value
first_value:
    .quad 0
.globl rejected_value
rejected_value:
    .quad 0
.globl rejected_output
rejected_output:
    .quad 0x8877665544332211
    .quad 0x1122334455667788

.section .smc,"xrw"
.p2align 5
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
    /* Fixed ten-byte slot retained from the preceding authored fixture. */
    .byte 0xb8
.globl smc_constant_immediate
smc_constant_immediate:
    .long 1
    .fill 5, 1, 0x90
    add rax, rcx
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
.ascii " /EXPORT:smc_constant_immediate /EXPORT:smc_value /EXPORT:smc_reject /EXPORT:smc_epilogue"
.ascii " /EXPORT:smc_gate /EXPORT:smc_gate_return /EXPORT:smc_writer /EXPORT:smc_prepare"
.ascii " /EXPORT:smc_first_return /EXPORT:smc_prepare_return /EXPORT:smc_second_return"
.ascii " /EXPORT:smc_writer_return /EXPORT:smc_after_store"
.ascii " /EXPORT:smc_checkpoint /EXPORT:smc_before_write /EXPORT:smc_after_write /EXPORT:smc_done"
.ascii " /EXPORT:smc_output,DATA /EXPORT:first_value,DATA /EXPORT:rejected_value,DATA /EXPORT:rejected_output,DATA"
