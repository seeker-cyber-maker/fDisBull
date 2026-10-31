; Authored native6502 compiler intrinsic for the reviewed game UIL profile.
; This generated mathematical LUT contains no copied original ROM bytes.
; The source operation is UpdateSubpixel: reverse Anim's low eight bits and
; store the resulting unsigned word. Anim's high byte is deliberately ignored.
; Root's backend retains the typed UIL procedure and its public procedure ID.
;
; cc65 ABI: A/X/Y, flags and temporary zero-page cells are caller-saved.
; UpdateSubpixel writes only its declared word; the mace/collision queries
; write no game state. SetTile writes one declared world byte.

.export _update_subpixel
.export _exact_update_subpixel
.import _anim, _subpixel
.export _mace_x, _mace_y
.export _exact_mace_x, _exact_mace_y
.import _objects, _native_sine_lo, _native_sine_hi
.export _get_tile, _get_collision, _set_tile, _collides_player
.import _world, _native_collision
.import _player_x, _player_y, _player_jump, _player_die
.export _run_objects, _run_fireball
.import _native_actor_lo, _native_actor_hi, _native_actor_bank
.import _banked_call
.import _muteki, _player_win, _shake_timer, _player_action, _player_angle
.import _current_sfx, _sfx_to_play
.import incsp1, incsp2, incsp3
.importzp c_sp, tmp1, tmp2, tmp3, tmp4, ptr4

.segment "GAMEFAST"

_exact_update_subpixel:
_update_subpixel:
    ldy _anim
    lda reverse8,y
    sta _subpixel
    lda #0
    sta _subpixel+1
    rts

; cc65 fastcall byte slot in A, legal range0..47. The byte result is
; center + low(ASR16(sine,4)), wrapped exactly like the typed source.
; Sine data are generated privately from the exact hash-bound original ROM.
; A/X/Y and tmp1..tmp3 are caller-saved; the game object array is read-only.
_exact_mace_x:
_mace_x:
    asl a
    asl a
    tax
    lda _objects+1,x
    sta tmp1
    ldy _objects+3,x
    lda _native_sine_lo,y
    lsr a
    lsr a
    lsr a
    lsr a
    sta tmp2
    lda _native_sine_hi,y
    asl a
    asl a
    asl a
    asl a
    ora tmp2
    clc
    adc tmp1
    ldx #0
    rts

; Cosine is the verified periodic extension at phase+64 (mod256).
; Negate the WORD before the arithmetic shift: -(v>>4) would round the
; negative fractions differently and is not the source operation.
_exact_mace_y:
_mace_y:
    asl a
    asl a
    tax
    lda _objects+2,x
    sta tmp1
    lda _objects+3,x
    clc
    adc #64
    tay
    lda _native_sine_lo,y
    eor #$ff
    clc
    adc #1
    sta tmp2
    lda _native_sine_hi,y
    eor #$ff
    adc #0
    asl a
    asl a
    asl a
    asl a
    sta tmp3
    lda tmp2
    lsr a
    lsr a
    lsr a
    lsr a
    ora tmp3
    clc
    adc tmp1
    ldx #0
    rts

; get_tile(x,y): y in A; x is the one byte on the software stack.
_get_tile:
    and #$f0
    sta tmp1
    ldy #0
    lda (c_sp),y
    lsr a
    lsr a
    lsr a
    lsr a
    ora tmp1
    tax
    lda _world,x
    ldx #0
    jmp incsp1

; The full256-byte collision window is bound privately, preserving all
; byte-class reads in the actual source (not clamping to35 tile IDs).
_get_collision:
    jsr _get_tile
    tax
    lda _native_collision,x
    ldx #0
    rts

; set_tile(x,y,tile): tile in A; y at stack0, x at stack1.
_set_tile:
    sta tmp1
    ldy #0
    lda (c_sp),y
    and #$f0
    sta tmp2
    iny
    lda (c_sp),y
    lsr a
    lsr a
    lsr a
    lsr a
    ora tmp2
    tax
    lda tmp1
    sta _world,x
    jmp incsp2

; collides_player(x,y,rx,ry): ry in A; rx/y/x at stack0/1/2.
; A negative signed-byte radius cannot satisfy both source comparisons.
; For0..127 the inclusive signed interval is exactly
;     (u8)(coordinate-player+radius) <= 2*radius.
_collides_player:
    cmp #128
    bcs collision_false
    sta tmp1
    ldx _player_die
    bne collision_false
    ldx _player_jump
    beq collision_jump_ok
    cpx #48
    bne collision_false
collision_jump_ok:
    ldy #0
    lda (c_sp),y
    bmi collision_false
    sta tmp2
    asl a
    sta tmp3
    ldy #2
    lda (c_sp),y
    sec
    sbc _player_x
    clc
    adc tmp2
    cmp tmp3
    bcc collision_x_ok
    beq collision_x_ok
collision_false:
    lda #0
    ldx #0
    jmp incsp3
collision_x_ok:
    lda tmp1
    asl a
    sta tmp3
    ldy #1
    lda (c_sp),y
    sec
    sbc _player_y
    clc
    adc tmp1
    cmp tmp3
    bcc collision_true
    beq collision_true
    jmp collision_false
collision_true:
    lda #1
    ldx #0
    jmp incsp3

; The reviewed source captures each slot's type once, then calls exactly one
; matching handler. Reload subsequent slots after the call: a newly inserted
; later-slot effect must run in this same scan. Types28..255 are no-ops in UIL.
; Save the byte offset on the hardware stack: every handler may clobber ZP.
; Authored handler-address/bank tables are linker relocations, not ROM assets.
_run_objects:
    ldx #0
objects_next:
    lda _objects,x
    beq objects_advance
    cmp #28
    bcs objects_advance
    tay
    txa
    pha
    lda _native_actor_lo,y
    sta ptr4
    lda _native_actor_hi,y
    sta ptr4+1
    lda _native_actor_bank,y
    sta tmp4
    txa
    lsr a
    lsr a
    jsr _banked_call
    pla
    tax
objects_advance:
    txa
    clc
    adc #4
    tax
    cpx #192
    bne objects_next
    rts

; RunFireball(slot), legal slot0..47. Move first, including byte wrap, then
; apply the exact pure CollidesPlayer(...,10,10) and HurtPlayer(7) predicates.
; The inlined source helper writes occur in their original order; PlaySFX(13)
; compares current_sfx only and replaces both fields when priority permits.
; No helper has an external event/hardware effect, so eliminating these calls
; preserves the public state/event contract. Unknown direct-call types do not
; move but still apply collision, exactly like the typed source procedure.
_run_fireball:
    asl a
    asl a
    tax
    lda _objects,x
    cmp #20
    beq fireball_up
    cmp #21
    beq fireball_down
    cmp #22
    beq fireball_left
    cmp #23
    bne fireball_check
    lda _objects+1,x
    clc
    adc #1
    sta _objects+1,x
    jmp fireball_check
fireball_up:
    lda _objects+2,x
    sec
    sbc #1
    sta _objects+2,x
    jmp fireball_check
fireball_down:
    lda _objects+2,x
    clc
    adc #1
    sta _objects+2,x
    jmp fireball_check
fireball_left:
    lda _objects+1,x
    sec
    sbc #1
    sta _objects+1,x
fireball_check:
    lda _player_jump
    beq fireball_grounded
    cmp #48
    bne fireball_return
fireball_grounded:
    lda _player_die
    ora _muteki
    ora _player_win
    ora _shake_timer
    bne fireball_return
    lda _objects+1,x
    sec
    sbc _player_x
    clc
    adc #10
    cmp #21
    bcs fireball_return
    lda _objects+2,x
    sec
    sbc _player_y
    clc
    adc #10
    cmp #21
    bcs fireball_return
    lda #1
    sta _player_die
    lda #7
    sta _player_action
    lda #255
    sta _player_angle
    lda #13
    cmp _current_sfx
    bcc fireball_return
    sta _current_sfx
    sta _sfx_to_play
fireball_return:
    rts

reverse8:
    .byte $00,$80,$40,$C0,$20,$A0,$60,$E0,$10,$90,$50,$D0,$30,$B0,$70,$F0
    .byte $08,$88,$48,$C8,$28,$A8,$68,$E8,$18,$98,$58,$D8,$38,$B8,$78,$F8
    .byte $04,$84,$44,$C4,$24,$A4,$64,$E4,$14,$94,$54,$D4,$34,$B4,$74,$F4
    .byte $0C,$8C,$4C,$CC,$2C,$AC,$6C,$EC,$1C,$9C,$5C,$DC,$3C,$BC,$7C,$FC
    .byte $02,$82,$42,$C2,$22,$A2,$62,$E2,$12,$92,$52,$D2,$32,$B2,$72,$F2
    .byte $0A,$8A,$4A,$CA,$2A,$AA,$6A,$EA,$1A,$9A,$5A,$DA,$3A,$BA,$7A,$FA
    .byte $06,$86,$46,$C6,$26,$A6,$66,$E6,$16,$96,$56,$D6,$36,$B6,$76,$F6
    .byte $0E,$8E,$4E,$CE,$2E,$AE,$6E,$EE,$1E,$9E,$5E,$DE,$3E,$BE,$7E,$FE
    .byte $01,$81,$41,$C1,$21,$A1,$61,$E1,$11,$91,$51,$D1,$31,$B1,$71,$F1
    .byte $09,$89,$49,$C9,$29,$A9,$69,$E9,$19,$99,$59,$D9,$39,$B9,$79,$F9
    .byte $05,$85,$45,$C5,$25,$A5,$65,$E5,$15,$95,$55,$D5,$35,$B5,$75,$F5
    .byte $0D,$8D,$4D,$CD,$2D,$AD,$6D,$ED,$1D,$9D,$5D,$DD,$3D,$BD,$7D,$FD
    .byte $03,$83,$43,$C3,$23,$A3,$63,$E3,$13,$93,$53,$D3,$33,$B3,$73,$F3
    .byte $0B,$8B,$4B,$CB,$2B,$AB,$6B,$EB,$1B,$9B,$5B,$DB,$3B,$BB,$7B,$FB
    .byte $07,$87,$47,$C7,$27,$A7,$67,$E7,$17,$97,$57,$D7,$37,$B7,$77,$F7
    .byte $0F,$8F,$4F,$CF,$2F,$AF,$6F,$EF,$1F,$9F,$5F,$DF,$3F,$BF,$7F,$FF
