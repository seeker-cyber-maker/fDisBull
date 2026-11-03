/* Small stack-to-register bridges for the source ROM's original Sona 0.50
 * entrypoints. Keep these addresses paired with source-bound call-site guards.
 */
    .section .text
    .even

    .globl genesis_sona_init
genesis_sona_init:
    .word 0x4eb8, 0x0d5c
    rts

    .globl genesis_sona_play_bgm
genesis_sona_play_bgm:
    move.l 4(%sp),%a0
    move.l 8(%sp),%a1
    move.w 12(%sp),%d0
    .word 0x4eb8, 0x0ed0
    rts

    .globl genesis_sona_play_sfx
genesis_sona_play_sfx:
    move.l 4(%sp),%a0
    move.l 8(%sp),%a1
    move.w 12(%sp),%d0
    move.w 14(%sp),%d1
    .word 0x4eb8, 0x0ee4
    rts

    .globl genesis_sona_stop_all
genesis_sona_stop_all:
    .word 0x4eb8, 0x0f2c
    rts

    .globl genesis_sona_get_status
genesis_sona_get_status:
    .word 0x4eb8, 0x0fb6
    rts
