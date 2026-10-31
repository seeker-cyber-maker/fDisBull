; Authored MMC3 native startup, interrupt boundary and coherent view uploader.
; Mapper0 scalar/level backends remain separate and byte-stable.
.setcpu "6502"
.import _main, zerobss, copydata, callptr4, incsp1, incsp2
.importzp sp, sreg, ptr1, ptr4, tmp1, tmp2, tmp4
.import _display_plane, _display_hud, _display_attributes
.import _video_ready, _render_phase, _active_nt, _render_oam_page
.import _irq_phase, _frame_buttons, _irq_audio
.import _upload_count, _upload_cursor, _upload_target_nt, _upload_lo, _upload_hi
.import _audio_due_slots, _audio_served_slots, _audio_physical_entries
.export _select_data, _banked_call
.export _begin_state, _publish_state
.export _rom8
.export _object_projection_pair
.import _point_obj_bank, _point_obj_lo, _point_obj_hi
.import _point_raft_bank, _point_raft_lo, _point_raft_hi
.import _source_page_banks
.import _input_buttons, _joy_hold, _joy_press, _mode, _stage, _stage_name
.import _player_x, _player_y, _player_angle, _player_action, _player_jump
.import _player_spring, _player_win, _player_die, _keys_left, _ingame_status
.import _end_game, _time_secs, _time_frames, _lives, _score, _anim, _subpixel
.import _rng_seed, _shake_timer, _ending_phase, _ending_timer, _ending_fade
.import _current_sfx, _sfx_to_play, _current_bgm, _bgm_to_play
.import _clear_phase, _clear_timer
.export __STARTUP__ : absolute = 1

.segment "BSS"
code_bank: .res 1
data_bank: .res 1
mapper_select: .res 1
saved_a: .res 1
saved_x: .res 1
upload_high: .res 1
upload_attr_high: .res 1
pad_bits: .res 1
oam_page: .res 1
upload_first: .res 1

.segment "CODE"
; cc65 fastcall: source offset in EAX, region byte on software stack.
; Keep source words big-endian in the C rom16/rom32 composition layer.
_rom8:
    pha
    stx tmp1
    ldy #0
    lda (sp),y
    bne @badregion
    lda sreg+1
    bne @badregion
    lda sreg
    cmp #8
    bcs @badregion
    asl a
    asl a
    asl a
    sta tmp2
    txa
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    ora tmp2
    tax
    lda _source_page_banks,x
    cmp #255
    beq @unmapped
    jsr _select_data
    pla
    sta ptr1
    lda tmp1
    and #$1f
    ora #$a0
    sta ptr1+1
    ldy #0
    lda (ptr1),y
    ldx #0
    jmp incsp1
@badregion:
    lda #1
    bne @fault
@unmapped:
    lda #2
@fault:
    sta $07ed
    pla
    lda #0
    ldx #0
    jmp incsp1

; x/y are the unchanged front-hemisphere indices64..192; raft is in A.
; Return dx in A and the transposed dy in X, preserving their signed bits.
_object_projection_pair:
    pha
    ldy #1
    lda (sp),y
    sec
    sbc #64
    tax
    pla
    bne @raft
    lda _point_obj_bank,x
    jsr _select_data
    lda _point_obj_lo,x
    sta ptr1
    lda _point_obj_hi,x
    jmp @row
@raft:
    lda _point_raft_bank,x
    jsr _select_data
    lda _point_raft_lo,x
    sta ptr1
    lda _point_raft_hi,x
@row:
    sta ptr1+1
    ldy #0
    lda (sp),y
    sec
    sbc #64
    asl a
    bcc :+
    inc ptr1+1
:
    tay
    lda (ptr1),y
    pha
    iny
    lda (ptr1),y
    tax
    pla
    jmp incsp2

_select_data:
    ; An IRQ must see the mapper and its software shadow as one transaction.
    ; NMI never touches these bank registers; preserve the caller's I flag.
    php
    sei
    cmp data_bank
    beq data_selected
    pha
    lda #7
    sta mapper_select
    sta $8000
    pla
    sta data_bank
    sta $8001
data_selected:
    plp
    rts

select_code:
    php
    sei
    pha
    lda #6
    sta mapper_select
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

; Four48-byte completed-state records. A reader validates the even sequence,
; version and logical epoch, rather than treating live working RAM as a tick.
.macro published source, offset
    lda source
    sta $0700+offset,x
.endmacro
_begin_state:
    lda $07d2
    clc
    adc #1
    jsr publication_slot
    inc $0700,x
    rts

publication_slot:
    and #3
    asl a
    asl a
    asl a
    asl a
    sta tmp1
    asl a
    clc
    adc tmp1
    tax
    rts

_publish_state:
    lda $07d2
    jsr publication_slot
    lda #1
    sta $0701,x
    published $07d2,2
    published $07d3,3
    published _input_buttons,4
    published _joy_hold,5
    published _joy_press,6
    published _mode,7
    published _stage,8
    published _stage_name,9
    published _player_x,10
    published _player_y,11
    published _player_angle,12
    published _player_action,13
    published _player_jump,14
    published _player_spring,15
    published _player_win,16
    published _player_die,17
    published _keys_left,18
    published _ingame_status,19
    published _end_game,20
    published _time_secs,21
    published _time_frames,22
    published _lives,23
    published _score,24
    published _score+1,25
    published _score+2,26
    published _score+3,27
    published _anim,28
    published _anim+1,29
    published _subpixel,30
    published _subpixel+1,31
    published _rng_seed,32
    published _rng_seed+1,33
    published _shake_timer,34
    published _ending_phase,35
    published _ending_timer,36
    published _current_sfx,37
    published _sfx_to_play,38
    published _current_bgm,39
    published _bgm_to_play,40
    published $07eb,41
    published _ending_fade,42
    published _clear_phase,43
    published _clear_timer,44
    published $07fa,45
    published $07f8,46
    published $07f9,47
    inc $0700,x
    lda $07d2
    sta $07c0
    lda $07d3
    sta $07c1
    rts

.segment "STARTUP"
reset:
    sei
    cld
    ldx #$40
    stx $4017
    ldx #$ff
    txs
    inx
    stx $2000
    stx $2001
    stx $4010
    stx $e000
    bit $2002
@wait1: bit $2002
    bpl @wait1
    lda #0
    ldx #0
@clear:
    sta $0000,x
    sta $0100,x
    sta $0200,x
    sta $0300,x
    sta $0400,x
    sta $0500,x
    sta $0600,x
    sta $0700,x
    inx
    bne @clear
@wait2: bit $2002
    bpl @wait2
    lda #$80
    sta $a001
    lda #0
    sta $a000
    jsr select_code
    lda #1
    jsr _select_data
    ; 4KiB BG at0000 and4KiB sprites at1000, fixed first8KiB CHR.
    ldx #0
@chr:
    txa
    sta $8000
    lda chr_banks,x
    sta $8001
    inx
    cpx #6
    bne @chr
    lda #7
    sta mapper_select
    sta $8000
    lda #$00
    sta sp
    lda #$7e
    sta sp+1
    jsr zerobss
    jsr copydata
    ; zerobss cleared the software shadow after the initial R7=1 selection.
    ; Force the first post-initialization selection to write the real mapper.
    lda #$ff
    sta data_bank
    lda #$20
    sta $2006
    lda #0
    sta $2006
    lda #32
    ldx #8
    ldy #0
@nametables:
    sta $2007
    iny
    bne @nametables
    dex
    bne @nametables
    ; Attribute tables start with the ground palette.
    lda #$23
    sta $2006
    lda #$c0
    sta $2006
    lda #0
    ldx #64
@attr0: sta $2007
    dex
    bne @attr0
    lda #$27
    sta $2006
    lda #$c0
    sta $2006
    ldx #64
@attr1: sta $2007
    dex
    bne @attr1
    lda #$3f
    sta $2006
    lda #0
    sta $2006
    ldx #0
@palette:
    lda palette,x
    sta $2007
    inx
    cpx #32
    bne @palette
    lda #$23
    sta $2006
    lda #$a4
    sta $2006
    ldx #0
@footer0:
    lda footer,x
    sta $2007
    inx
    cpx #24
    bne @footer0
    lda #$27
    sta $2006
    lda #$a4
    sta $2006
    ldx #0
@footer1:
    lda footer,x
    sta $2007
    inx
    cpx #24
    bne @footer1
    lda #2
    sta oam_page
    sta _render_oam_page
    lda #0
    sta $2005
    sta $2005
    cli
    jsr _main
@forever: jmp @forever

; Each NMI sends a bounded chunk of dirty regions into the inactive
; nametable. View/palette/OAM become visible together after the last job.
nmi:
    pha
    txa
    pha
    tya
    pha
    inc $07d0
    bne :+
    inc $07d1
:
    lda #1
    sta $4016
    lda #0
    sta $4016
    sta pad_bits
    ldx #8
@readpad:
    lda $4016
    lsr a
    rol pad_bits
    dex
    bne @readpad
    ; The public pad mapping is a pure authored lookup, with the same sampled
    ; physical frame as before. Avoid spending vblank on repeated bit shifts.
    ldx pad_bits
    lda normalized_pad,x
    sta _frame_buttons
    lda _video_ready
    bne upload_pending
    jmp nmi_dma
upload_pending:
    bit $2002
    lda _upload_cursor
    cmp _upload_count
    bcc upload_chunk
    jmp upload_complete
upload_chunk:
    sta upload_first
    ; At most seven <=16-byte jobs. Push targets in reverse order and RTS
    ; through their fixed, unrolled ROM routines; no cc65 ZP is touched.
    clc
    adc #7
    cmp _upload_count
    bcc :+
    lda _upload_count
:
    sta _upload_cursor
    tax
    lda #>(upload_return-1)
    pha
    lda #<(upload_return-1)
    pha
@push_job:
    dex
    lda _upload_hi,x
    pha
    lda _upload_lo,x
    pha
    cpx upload_first
    bne @push_job
    lda _upload_target_nt
    asl a
    asl a
    tay
    rts
upload_return:
    inc _render_phase
    lda _upload_cursor
    cmp _upload_count
    beq upload_complete
    jmp nmi_dma
upload_complete:
    lda _upload_target_nt
    sta _active_nt
    lda _render_oam_page
    sta oam_page
    lda #0
    sta _video_ready
nmi_dma:
    lda #0
    sta $2003
    lda oam_page
    sta $4014
    bit $2002
    lda #0
    sta $2005
    sta $2005
    lda _active_nt
    ora #$88
    sta $2000
    lda #0
    sta _irq_phase
    sta $c000
    sta $c001
    sta $e000
    lda $07d4
    bne @clock_paused
    clc
    lda _audio_due_slots
    adc #2
    sta _audio_due_slots
    bcc :+
    inc _audio_due_slots+1
:
    sta $e001
    jmp @nmi_end
@clock_paused:
    lda _audio_served_slots
    sta _audio_due_slots
    lda _audio_served_slots+1
    sta _audio_due_slots+1
@nmi_end:
    pla
    tay
    pla
    tax
    pla
    rti

; Fixed ROM jobs target the inactive nametable selected in Y (0 or 4).
; RTS consumes the next job target or NMI continuation prepared above.
.macro upload_region label, source, address, length
    .export label
label:
    tya
    ora #>address
    sta $2006
    lda #<address
    sta $2006
    .repeat length, col
        lda source+col
        sta $2007
    .endrepeat
    rts
.endmacro
upload_region upload_row0,_display_plane+0,$2188,16
upload_region upload_row1,_display_plane+16,$21a8,16
upload_region upload_row2,_display_plane+32,$21c8,16
upload_region upload_row3,_display_plane+48,$21e8,16
upload_region upload_row4,_display_plane+64,$2208,16
upload_region upload_row5,_display_plane+80,$2228,16
upload_region upload_row6,_display_plane+96,$2248,16
upload_region upload_row7,_display_plane+112,$2268,16
upload_region upload_row8,_display_plane+128,$2288,16
upload_region upload_row9,_display_plane+144,$22a8,16
upload_region upload_row10,_display_plane+160,$22c8,16
upload_region upload_row11,_display_plane+176,$22e8,16
upload_region upload_row12,_display_plane+192,$2308,16
upload_region upload_row13,_display_plane+208,$2328,16
upload_region upload_row14,_display_plane+224,$2348,16
upload_region upload_row15,_display_plane+240,$2368,16
upload_region upload_hud0,_display_hud+0,$2104,12
upload_region upload_hud1,_display_hud+12,$2110,12
upload_region upload_attr0,_display_attributes+0,$23da,4
upload_region upload_attr1,_display_attributes+4,$23e2,4
upload_region upload_attr2,_display_attributes+8,$23ea,4
upload_region upload_attr3,_display_attributes+12,$23f2,4

irq:
    pha
    txa
    pha
    tya
    pha
    sta $e000
    inc _audio_physical_entries
    bne :+
    inc _audio_physical_entries+1
:
    ; cc65 C is reentrant here only with its complete ZP context and the
    ; trampoline temporaries preserved. Hardware/software stacks stay nested.
    ldx #$19
@savezp:
    lda $02,x
    pha
    dex
    bpl @savezp
    lda saved_a
    pha
    lda saved_x
    pha
    lda code_bank
    pha
    lda data_bank
    pha
    lda mapper_select
    pha
    jsr _irq_audio
    pla
    tay
    pla
    jsr _select_data
    pla
    jsr select_code
    sty mapper_select
    sty $8000
    pla
    sta saved_x
    pla
    sta saved_a
    ldx #0
@restorezp:
    pla
    sta $02,x
    inx
    cpx #$1a
    bne @restorezp
    lda _irq_phase
    bne @second_done
    sta $e000
    inc _irq_phase
    lda #119
    sta $c000
    lda #0
    sta $c001
    sta $e001
    jmp @endirq
@second_done:
    lda #2
    sta _irq_phase
    sta $e000
@endirq:
    pla
    tay
    pla
    tax
    pla
    rti

.segment "RODATA"
normalized_pad:
    .byte 0,1,2,3,8,9,10,11,4,5,6,7,12,13,14,15
    .byte 64,65,66,67,72,73,74,75,68,69,70,71,76,77,78,79
    .byte 128,129,130,131,136,137,138,139,132,133,134,135,140,141,142,143
    .byte 192,193,194,195,200,201,202,203,196,197,198,199,204,205,206,207
    .byte 32,33,34,35,40,41,42,43,36,37,38,39,44,45,46,47
    .byte 96,97,98,99,104,105,106,107,100,101,102,103,108,109,110,111
    .byte 160,161,162,163,168,169,170,171,164,165,166,167,172,173,174,175
    .byte 224,225,226,227,232,233,234,235,228,229,230,231,236,237,238,239
    .byte 16,17,18,19,24,25,26,27,20,21,22,23,28,29,30,31
    .byte 80,81,82,83,88,89,90,91,84,85,86,87,92,93,94,95
    .byte 144,145,146,147,152,153,154,155,148,149,150,151,156,157,158,159
    .byte 208,209,210,211,216,217,218,219,212,213,214,215,220,221,222,223
    .byte 48,49,50,51,56,57,58,59,52,53,54,55,60,61,62,63
    .byte 112,113,114,115,120,121,122,123,116,117,118,119,124,125,126,127
    .byte 176,177,178,179,184,185,186,187,180,181,182,183,188,189,190,191
    .byte 240,241,242,243,248,249,250,251,244,245,246,247,252,253,254,255
chr_banks: .byte 0,2,4,5,6,7
palette:
    .byte $0f,$2a,$1a,$30,$0f,$12,$21,$30,$0f,$17,$27,$30,$0f,$16,$28,$30
    .byte $0f,$30,$28,$16,$0f,$17,$27,$30,$0f,$12,$21,$30,$0f,$16,$28,$30
footer: .byte "START PAUSE  SELECT C   "

.segment "VECTORS"
    .word nmi,reset,irq
