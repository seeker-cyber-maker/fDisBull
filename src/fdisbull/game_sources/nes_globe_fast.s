; Authored 6502 hot loops for the NES presentation adapter.
; All inputs and outputs match the preceding C loops. No game state is written.
; Linked in the same RENDERFAST 8KiB bank as the renderer C procedures.
.setcpu "6502"
.export _globe_clear, _globe_copy_projection, _globe_paint_terrain, _globe_hud_attributes
.export _draw_sprite, _draw_objects
.import _display_plane, _display_palettes, _projection_cache
.import _render_oam_page, _render_oam_index, _oam_overflow
.import _globe_source_hi, _globe_atlas_pointer
.import _globe_rowbase, _globe_colbase, _world, _tile_palette
.import _display_hud, _display_attributes, _score, _lives, _time_secs
.import _stage_name, _keys_left
.import _render_epoch, _player_x, _player_y, _player_jump, _player_die, _objects
.import _object_projection_pair, _mace_x, _mace_y, _banked_call
.import pusha
.import incsp3
.importzp sp, ptr1, ptr4, tmp1, tmp2, tmp3, tmp4

.segment "BSS"
globe_tile_lo: .res 35
globe_tile_hi: .res 35

.segment "RENDERFAST"

; Clear the two 256-byte staging planes and selected OAM page (2 or 3).
_globe_clear:
    lda #0
    ldx #0
@planes:
    .repeat 8, chunk
        sta _display_plane + chunk*32,x
        sta _display_palettes + chunk*32,x
    .endrepeat
    inx
    cpx #32
    bne @planes
    ; The renderer selects only physical OAM page $02 or $03. Absolute
    ; indexed stores avoid incrementing an indirect pointer for every byte.
    lda #$ff
    ldx #0
    ldy _render_oam_page
    cpy #2
    beq @oam2
    cpy #3
    beq @oam3
    ; Retain the generic routine for callers selecting another page.
    ldx #0
    stx ptr1
    sty ptr1+1
    ldy #0
@oam_generic:
    .repeat 16
        sta (ptr1),y
        iny
    .endrepeat
    bne @oam_generic
    rts
@oam2:
    .repeat 16, chunk
        sta $0200+chunk*16,x
    .endrepeat
    inx
    cpx #16
    bne @oam2
    rts
@oam3:
    .repeat 16, chunk
        sta $0300+chunk*16,x
    .endrepeat
    inx
    cpx #16
    bne @oam3
    rts

; Source is one full page in the selected A000..BFFF immutable data window.
_globe_copy_projection:
    lda #0
    sta ptr1
    lda _globe_source_hi
    sta ptr1+1
    ldy #0
@copy:
    .repeat 8
        lda (ptr1),y
        sta _projection_cache,y
        iny
    .endrepeat
    bne @copy
    rts

; Cached records are {position,map offset,shape offset,unused}. The original
; C renderer traverses records63..0, writing all four quadrant bytes and the
; same palette byte. This preserves its existing tile-level composition.
_globe_paint_terrain:
    lda _globe_atlas_pointer
    sta ptr1
    lda _globe_atlas_pointer+1
    sta ptr1+1
    ldy #0
@rows:
    lda ptr1
    sta globe_tile_lo,y
    lda ptr1+1
    sta globe_tile_hi,y
    clc
    lda ptr1
    adc #36
    sta ptr1
    bcc :+
    inc ptr1+1
:
    iny
    cpy #35
    bne @rows
    lda #252
    sta tmp3
@record:
    ldx tmp3
    lda _projection_cache+1,x
    clc
    adc _globe_rowbase
    and #$f0
    sta tmp1
    lda _projection_cache+1,x
    clc
    adc _globe_colbase
    and #$0f
    ora tmp1
    tay
    lda _world,y
    cmp #35
    bcc :+
    lda #0
:
    tay
    lda globe_tile_lo,y
    sta ptr1
    lda globe_tile_hi,y
    sta ptr1+1
    lda _tile_palette,y
    sta tmp2
    ldy _projection_cache+2,x
    lda _projection_cache,x
    tax
    lda (ptr1),y
    sta _display_plane,x
    iny
    lda (ptr1),y
    sta _display_plane+1,x
    iny
    lda (ptr1),y
    sta _display_plane+16,x
    iny
    lda (ptr1),y
    sta _display_plane+17,x
    lda tmp2
    sta _display_palettes,x
    sta _display_palettes+1,x
    sta _display_palettes+16,x
    sta _display_palettes+17,x
    lda tmp3
    sec
    sbc #4
    sta tmp3
    bcs @record
    rts

; HUD digits use the original packed score nibbles and byte arithmetic.
; Values outside normal BCD are deliberately retained as the C code defines.
.macro hud_pair source, dest
    lda source
    lsr a
    lsr a
    lsr a
    lsr a
    clc
    adc #48
    sta _display_hud+dest
    lda source
    and #15
    clc
    adc #48
    sta _display_hud+dest+1
.endmacro

_globe_hud_attributes:
    lda #32
    .repeat 24, pos
        sta _display_hud+pos
    .endrepeat
    hud_pair _score+2, 0
    hud_pair _score+1, 2
    hud_pair _score, 4
    lda #76
    sta _display_hud+7
    hud_pair _lives, 8
    lda #84
    sta _display_hud+11
    hud_pair _time_secs, 12
    lda _stage_name
    lsr a
    lsr a
    lsr a
    lsr a
    clc
    adc #48
    sta _display_hud+15
    lda #45
    sta _display_hud+16
    lda _stage_name
    and #15
    clc
    adc #48
    sta _display_hud+17
    lda #75
    sta _display_hud+19
    lda _keys_left
    clc
    adc #48
    sta _display_hud+20

    ; Each output samples four palette cells. Shifts deliberately truncate
    ; to 8 bits, matching the C assignment even for non-palette input bytes.
    .repeat 4, row
        .repeat 4, col
            lda _display_palettes+row*64+col*4+51
            asl a
            asl a
            asl a
            asl a
            asl a
            asl a
            sta tmp1
            lda _display_palettes+row*64+col*4+49
            asl a
            asl a
            asl a
            asl a
            ora tmp1
            sta tmp1
            lda _display_palettes+row*64+col*4+19
            asl a
            asl a
            ora tmp1
            ora _display_palettes+row*64+col*4+17
            sta _display_attributes+row*4+col
        .endrepeat
    .endrepeat
    rts

; cc65 fastcall: palette in A; tile, y, x occupy stack bytes 0..2.
; Return with the same three-byte stack cleanup as the C procedure.
_draw_sprite:
    and #3
    sta tmp1
    lda _render_oam_index
    cmp #252
    bcc @room
    lda #1
    sta _oam_overflow
    jmp incsp3
@room:
    tay
    lda #0
    sta ptr1
    lda _render_oam_page
    sta ptr1+1
    tya
    pha
    ldy #1
    lda (sp),y
    sec
    sbc #1
    sta tmp2
    ldy #0
    lda (sp),y
    sta tmp3
    pla
    tay
    lda tmp2
    sta (ptr1),y
    iny
    lda tmp3
    sta (ptr1),y
    iny
    lda tmp1
    sta (ptr1),y
    iny
    tya
    pha
    ldy #2
    lda (sp),y
    sta tmp2
    pla
    tay
    lda tmp2
    sta (ptr1),y
    iny
    sty _render_oam_index
    jmp incsp3

; Retained actor order and exact byte wrapping of the C adapter. All temporary
; state is renderer-owned because called helpers may clobber zero page.
.segment "BSS"
obj_slot: .res 1
obj_remaining: .res 1
obj_type: .res 1
obj_x: .res 1
obj_y: .res 1
obj_raft: .res 1
obj_tile: .res 1
obj_palette: .res 1
.segment "RENDERFAST"
.macro call_mace func
    ldy #<.bank(func)
    sty tmp4
    ldy #<func
    sty ptr4
    ldy #>func
    sty ptr4+1
    jsr _banked_call
.endmacro
; obj_x/y/tile/palette are the ordinary C draw_sprite arguments.
obj_emit:
    ldy _render_oam_index
    cpy #252
    bcc :+
    lda #1
    sta _oam_overflow
    rts
:
    lda #0
    sta ptr1
    lda _render_oam_page
    sta ptr1+1
    lda obj_y
    sec
    sbc #1
    sta (ptr1),y
    iny
    lda obj_tile
    sta (ptr1),y
    iny
    lda obj_palette
    and #3
    sta (ptr1),y
    iny
    lda obj_x
    sta (ptr1),y
    iny
    sty _render_oam_index
    rts

_draw_objects:
    lda _render_epoch
    cmp #192
    bcc :+
    sec
    sbc #192
:
    cmp #96
    bcc :+
    sec
    sbc #96
:
    cmp #48
    bcc :+
    sec
    sbc #48
:
    sta obj_slot
    lda #48
    sta obj_remaining
    lda _player_jump
    lsr a
    lsr a
    sta obj_y
    lda #144
    sec
    sbc obj_y
    sta obj_y
    lda _player_die
    beq :+
    lda #3
:
    sta obj_palette
    lda #120
    sta obj_x
    lda #32
    sta obj_tile
    jsr obj_emit
    lda #128
    sta obj_x
    inc obj_tile
    jsr obj_emit
    lda #120
    sta obj_x
    lda obj_y
    clc
    adc #8
    sta obj_y
    inc obj_tile
    jsr obj_emit
    lda #128
    sta obj_x
    inc obj_tile
    jsr obj_emit
@loop:
    lda obj_slot
    asl a
    asl a
    tax
    lda _objects,x
    beq @skip_early
    cmp #28
    bcc :+
@skip_early:
    jmp @next
:
    sta obj_type
    lda _objects+1,x
    sta obj_x
    lda _objects+2,x
    sta obj_y
    lda obj_type
    cmp #6
    beq @mace
    cmp #7
    bne @relative
@mace:
    lda obj_slot
    call_mace _mace_x
    sta obj_x
    lda obj_slot
    call_mace _mace_y
    sta obj_y
@relative:
    lda obj_x
    sec
    sbc _player_x
    cmp #65
    bcc :+
    cmp #192
    bcs :+
    jmp @next
:
    clc
    adc #128
    sta obj_x
    lda obj_y
    sec
    sbc _player_y
    cmp #65
    bcc :+
    cmp #192
    bcs :+
    jmp @next
:
    clc
    adc #128
    sta obj_y
    lda #0
    sta obj_raft
    lda obj_type
    cmp #2
    bcc :+
    cmp #6
    bcs :+
    inc obj_raft
:
    lda obj_x
    jsr pusha
    lda obj_y
    jsr pusha
    lda obj_raft
    jsr _object_projection_pair
    clc
    adc #124
    sta obj_x
    txa
    clc
    adc #148
    sta obj_y
    lda obj_raft
    bne @raft
    lda obj_type
    sta obj_tile
    and #3
    sta obj_palette
    jsr obj_emit
    jmp @next
@raft:
    lda obj_x
    sec
    sbc #4
    sta obj_x
    lda obj_y
    sec
    sbc #4
    sta obj_y
    lda #1
    sta obj_palette
    lda #36
    sta obj_tile
    jsr obj_emit
    lda obj_x
    clc
    adc #8
    sta obj_x
    inc obj_tile
    jsr obj_emit
    lda obj_x
    sec
    sbc #8
    sta obj_x
    lda obj_y
    clc
    adc #8
    sta obj_y
    inc obj_tile
    jsr obj_emit
    lda obj_x
    clc
    adc #8
    sta obj_x
    inc obj_tile
    jsr obj_emit
@next:
    inc obj_slot
    lda obj_slot
    cmp #48
    bcc :+
    lda #0
    sta obj_slot
:
    dec obj_remaining
    beq :+
    jmp @loop
:
    rts
