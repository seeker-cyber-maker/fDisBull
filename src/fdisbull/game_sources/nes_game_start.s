; Authored MMC3 native startup, interrupt boundary and coherent view uploader.
; Mapper0 scalar/level backends remain separate and byte-stable.
.setcpu "6502"
.import _main, zerobss, copydata, callptr4, incsp1, incsp2
.importzp sp, sreg, ptr1, ptr4, tmp1, tmp2, tmp4
.import _display_plane, _display_hud, _display_attributes
.import _video_ready, _render_phase, _active_nt, _render_oam_page
.import _irq_phase, _frame_buttons, _irq_audio
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

; Each NMI sends half of a private, completed16x16view into the inactive
; nametable. The view/palette/OAM changes become visible together after part2.
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
    ; serial byte A128,B64,Select32,Start16,U8,D4,L2,R1
    lda pad_bits
    and #$0f
    sta _frame_buttons
    lda pad_bits
    and #$80
    beq :+
    lda _frame_buttons
    ora #$10
    sta _frame_buttons
:
    lda pad_bits
    and #$40
    beq :+
    lda _frame_buttons
    ora #$20
    sta _frame_buttons
:
    lda pad_bits
    and #$10
    beq :+
    lda _frame_buttons
    ora #$40
    sta _frame_buttons
:
    lda pad_bits
    and #$20
    beq :+
    lda _frame_buttons
    ora #$80
    sta _frame_buttons
:
    ; Swap U/D nibble to the public profile's R,L,U,D order.
    lda _frame_buttons
    and #$f3
    sta pad_bits
    lda _frame_buttons
    and #4
    asl a
    ora pad_bits
    sta pad_bits
    lda _frame_buttons
    and #8
    lsr a
    ora pad_bits
    sta _frame_buttons
    lda _video_ready
    beq nmi_dma
    lda _active_nt
    eor #1
    asl a
    asl a
    ora #$21
    sta upload_high
    lda _render_phase
    bne @part1
    jmp upload0
@part1:
    jmp upload1

upload_done:
    inc _render_phase
    lda _render_phase
    cmp #2
    bne nmi_dma
    lda _active_nt
    eor #1
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

; Macro-generated bounded upload: 128terrain+12HUD+8attribute bytes.
.macro upload_half half
    .repeat 8,row
        lda _active_nt
        eor #1
        asl a
        asl a
        ora #>($2188+(half*8+row)*32)
        sta $2006
        lda #<($2188+(half*8+row)*32)
        sta $2006
        .repeat 16,col
            lda _display_plane+half*128+row*16+col
            sta $2007
        .endrepeat
    .endrepeat
    lda _active_nt
    eor #1
    asl a
    asl a
    ora #$21
    sta $2006
    lda #<(($2100+4)+half*12)
    sta $2006
    .repeat 12,col
        lda _display_hud+half*12+col
        sta $2007
    .endrepeat
    .repeat 2,row
        lda _active_nt
        eor #1
        asl a
        asl a
        ora #$23
        sta $2006
        lda #<($23da+(half*2+row)*8)
        sta $2006
        .repeat 4,col
            lda _display_attributes+half*8+row*4+col
            sta $2007
        .endrepeat
    .endrepeat
    jmp upload_done
.endmacro
upload0: upload_half 0
upload1: upload_half 1

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
chr_banks: .byte 0,2,4,5,6,7
palette:
    .byte $0f,$2a,$1a,$30,$0f,$12,$21,$30,$0f,$17,$27,$30,$0f,$16,$28,$30
    .byte $0f,$30,$28,$16,$0f,$17,$27,$30,$0f,$12,$21,$30,$0f,$16,$28,$30
footer: .byte "START PAUSE  SELECT C   "

.segment "VECTORS"
    .word nmi,reset,irq
