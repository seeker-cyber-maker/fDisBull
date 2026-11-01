/* Copy a bounded publication field. Distinct address registers preserve the
 * source and destination streams; 68000 longword transfers require even
 * addresses, so differing parity uses bytes and equal odd parity is aligned. */
    .section .text.genesis_copy_bytes,"ax"
    .globl genesis_copy_bytes
genesis_copy_bytes:
    movea.l 4(%sp),%a1
    movea.l 8(%sp),%a0
    move.w 12(%sp),%d0
    beq 6f
    move.l %a0,%d1
    btst #0,%d1
    beq 1f
    move.l %a1,%d1
    btst #0,%d1
    beq 4f
    move.b (%a0)+,(%a1)+
    subq.w #1,%d0
    beq 6f
    bra 2f
1:  move.l %a1,%d1
    btst #0,%d1
    bne 4f
2:  move.w %d0,%d1
    lsr.w #2,%d1
    beq 3f
    subq.w #1,%d1
5:  move.l (%a0)+,(%a1)+
    dbra %d1,5b
3:  andi.w #3,%d0
    beq 6f
4:  subq.w #1,%d0
7:  move.b (%a0)+,(%a1)+
    dbra %d0,7b
6:  rts
