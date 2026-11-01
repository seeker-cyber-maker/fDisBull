/* Authored 68000 reset/VBlank boundary for the procedural game compiler. */
    .section .vectors,"a"
    .long 0x00fffe00
    .long genesis_reset
    .rept 28
    .long genesis_trap
    .endr
    .long genesis_vblank
    .long genesis_trap
    .rept 32
    .long genesis_trap
    .endr
    .space 256

    .section .text.startup,"ax"
    .globl genesis_reset
genesis_reset:
    move.w #0x2700,%sr
    movea.l #0x00fffe00,%sp
    movea.l #0x00ff0000,%a0
    moveq #0,%d0
    move.w #16383,%d1
1:  move.l %d0,(%a0)+
    dbra %d1,1b
    lea __data_load,%a0
    lea __data_start,%a1
    move.l #__data_end,%d0
    sub.l %a1,%d0
    beq 3f
2:  move.b (%a0)+,(%a1)+
    subq.l #1,%d0
    bne 2b
3:  jsr genesis_main
4:  bra 4b

    .globl genesis_enable_interrupts
genesis_enable_interrupts:
    move.w #0x2000,%sr
    rts

    .globl genesis_vblank
genesis_vblank:
    movem.l %d0-%d7/%a0-%a6,-(%sp)
    jsr genesis_vblank_c
    movem.l (%sp)+,%d0-%d7/%a0-%a6
    rte

    .globl genesis_trap
genesis_trap:
    move.b #0xee,0x00ff1f1f
5:  stop #0x2700
    bra 5b
