; Authored 6502 hot loops for the NES presentation adapter.
; All inputs and outputs match the preceding C loops. No game state is written.
; Linked in the same RENDERFAST 8KiB bank as the renderer C procedures.
.setcpu "6502"
.export _globe_clear, _globe_copy_projection, _globe_paint_terrain
.import _display_plane, _display_palettes, _projection_cache
.import _render_oam_page, _globe_source_hi, _globe_atlas_pointer
.import _globe_rowbase, _globe_colbase, _world, _tile_palette
.importzp ptr1, tmp1, tmp2, tmp3

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
    sta ptr1
    lda _render_oam_page
    sta ptr1+1
    lda #$ff
    ldy #0
@oam:
    .repeat 16
        sta (ptr1),y
        iny
    .endrepeat
    bne @oam
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
