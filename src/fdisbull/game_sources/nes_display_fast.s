; Authored bounded dirty-region upload planner. No game state is modified.
; Each inactive nametable has its own shadow. Main owns the staging buffers
; and this plan until video_ready is published; NMI owns them until completion.
.setcpu "6502"
.export _prepare_upload, _upload_count, _upload_cursor, _upload_target_nt
.export _upload_lo, _upload_hi, _upload_shadow0, _upload_shadow1
.export _upload_terrain_cached, _upload_terrain_valid, _upload_terrain_overlay
.import _active_nt, _display_plane, _display_hud, _display_attributes
.importzp ptr1
.segment "BSS"
_upload_shadow0: .res 296
_upload_shadow1: .res 296
upload_valid: .res 2
_upload_count: .res 1
_upload_cursor: .res 1
_upload_target_nt: .res 1
_upload_lo: .res 22
_upload_hi: .res 22
upload_force: .res 1
; Producer certificate: restored terrain and identical pause overlay. Any
; terrain-cache miss invalidates both bits before painting a new image.
_upload_terrain_cached: .res 1
_upload_terrain_valid: .res 1
_upload_terrain_overlay: .res 1
upload_last_overlay: .res 2
upload_terrain_mask: .res 1
upload_reuse: .res 1

.segment "RENDERFAST"
; A region is copied in full when any byte differs. Region sizes are bounded
; by 16 bytes, so the NMI can schedule a fixed worst-case number of jobs.
.macro prepare_region source, offset, length, routine
    .local shadow1, selected, compare, changed, copy, done
    .import routine
    lda _upload_target_nt
    bne shadow1
    lda #<(_upload_shadow0+offset)
    ldx #>(_upload_shadow0+offset)
    jmp selected
shadow1:
    lda #<(_upload_shadow1+offset)
    ldx #>(_upload_shadow1+offset)
selected:
    sta ptr1
    stx ptr1+1
    ldy #0
    lda upload_force
    bne changed
compare:
    lda source,y
    cmp (ptr1),y
    bne changed
    iny
    cpy #length
    bne compare
    jmp done
changed:
    ldx _upload_count
    lda #<(routine-1)
    sta _upload_lo,x
    lda #>(routine-1)
    sta _upload_hi,x
    inc _upload_count
    ldy #0
copy:
    lda source,y
    sta (ptr1),y
    iny
    cpy #length
    bne copy
done:
.endmacro

_prepare_upload:
    lda #0
    sta _upload_count
    sta _upload_cursor
    lda _active_nt
    eor #1
    sta _upload_target_nt
    tax
    lda upload_valid,x
    eor #1
    sta upload_force
    lda #1
    cpx #0
    beq :+
    asl a
:
    sta upload_terrain_mask
    lda #0
    sta upload_reuse
    lda _upload_terrain_cached
    beq scan_terrain
    lda upload_force
    bne scan_terrain
    lda _upload_terrain_valid
    and upload_terrain_mask
    beq scan_terrain
    lda _upload_terrain_overlay
    cmp upload_last_overlay,x
    bne scan_terrain
    inc upload_reuse
    jmp terrain_done
scan_terrain:
    prepare_region _display_plane+0,0,16,upload_row0
    prepare_region _display_plane+16,16,16,upload_row1
    prepare_region _display_plane+32,32,16,upload_row2
    prepare_region _display_plane+48,48,16,upload_row3
    prepare_region _display_plane+64,64,16,upload_row4
    prepare_region _display_plane+80,80,16,upload_row5
    prepare_region _display_plane+96,96,16,upload_row6
    prepare_region _display_plane+112,112,16,upload_row7
    prepare_region _display_plane+128,128,16,upload_row8
    prepare_region _display_plane+144,144,16,upload_row9
    prepare_region _display_plane+160,160,16,upload_row10
    prepare_region _display_plane+176,176,16,upload_row11
    prepare_region _display_plane+192,192,16,upload_row12
    prepare_region _display_plane+208,208,16,upload_row13
    prepare_region _display_plane+224,224,16,upload_row14
    prepare_region _display_plane+240,240,16,upload_row15
terrain_done:
    prepare_region _display_hud+0,256,12,upload_hud0
    prepare_region _display_hud+12,268,12,upload_hud1
    lda upload_reuse
    beq scan_attributes
    jmp attributes_done
scan_attributes:
    prepare_region _display_attributes+0,280,4,upload_attr0
    prepare_region _display_attributes+4,284,4,upload_attr1
    prepare_region _display_attributes+8,288,4,upload_attr2
    prepare_region _display_attributes+12,292,4,upload_attr3
attributes_done:
    ldx _upload_target_nt
    lda _upload_terrain_cached
    beq forget_terrain
    lda _upload_terrain_valid
    ora upload_terrain_mask
    sta _upload_terrain_valid
    lda _upload_terrain_overlay
    sta upload_last_overlay,x
    jmp terrain_remembered
forget_terrain:
    lda upload_terrain_mask
    eor #$ff
    and _upload_terrain_valid
    sta _upload_terrain_valid
terrain_remembered:
    ldx _upload_target_nt
    lda #1
    sta upload_valid,x
    rts
