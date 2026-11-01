; MMC3 procedure-bank call shim, adapted from nes_game_start.s. Platform and
; read-only source tables remain in the two fixed upper windows.
.setcpu "6502"
.import callptr4
.importzp ptr4, tmp4
.export _shadowrun_bank_init, _shadowrun_data_select, _shadowrun_arena_restart, _banked_call
.segment "BSS"
code_bank: .res 1
data_bank: .res 1
saved_a: .res 1
saved_x: .res 1
.segment "CODE"
; Target-authored restart; no source death or story continuation is implied.
_shadowrun_arena_restart:
    jmp ($fffc)
_shadowrun_bank_init:
    sei
    lda #$80
    sta $a001
    lda #$06
    sta $8000
    lda #$00
    sta $8001
    sta code_bank
    lda #$ff
    sta data_bank
    ldx #0
@chr:
    stx $8000
    lda chr_banks,x
    sta $8001
    inx
    cpx #6
    bne @chr
    rts
; Fastcall byte is the physical 8 KiB data-bank number in A.
_shadowrun_data_select:
    php
    sei
    cmp data_bank
    beq @selected
    pha
    lda #7
    sta $8000
    pla
    sta data_bank
    sta $8001
@selected:
    plp
    rts
select_code:
    php
    sei
    pha
    lda #6
    sta $8000
    pla
    sta code_bank
    sta $8001
    plp
    rts
_banked_call:
    sta saved_a
    stx saved_x
    lda tmp4
    cmp code_bank
    bne @switch
    lda saved_a
    ldx saved_x
    jmp callptr4
@switch:
    lda code_bank
    pha
    lda tmp4
    jsr select_code
    lda saved_a
    ldx saved_x
    jsr callptr4
    sta saved_a
    stx saved_x
    pla
    jsr select_code
    lda saved_a
    ldx saved_x
    rts
.segment "RODATA"
chr_banks: .byte 0,2,4,5,6,7
