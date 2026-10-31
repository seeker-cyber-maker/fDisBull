; Native 6502 renderer for the source-event audio engine.
; Original implementation: direct indexed state, no per-tick ROM callbacks.
; Must run only from the non-nesting audio IRQ owner.
.setcpu "6502"
.export _audio_render_tick, _audio_render_reset
.import _audio_gate, _audio_envelope, _audio_pan, _audio_duty
.import _audio_attack_ticks, _audio_decay_ticks, _audio_sustain, _audio_release_ticks
.import _audio_envelope_phase, _audio_release_peak, _audio_envelope_counter
.import _audio_psg_level, _audio_psg_tl, _audio_psg_ar, _audio_psg_sl
.import _audio_psg_dr, _audio_psg_sr, _audio_psg_rr, _audio_sfx_phase
.import _audio_attenuation, _audio_owner, _audio_current_volume
.import _audio_pitch, _audio_pulse_period, _audio_triangle_period
.import _audio_psg_pulse_period, _audio_psg_triangle_period
.import _audio_round_robin, _audio_arpeggio_count
.import _audio_pcm_ticks, _audio_pcm_generation
.import _audio_dmc_address, _audio_dmc_length, _audio_dmc_rate
.import _audio_dmc_delivered, _audio_dmc_generation, _audio_dmc_source, _audio_dmc_playing
.import _audio_dmc_slot, _audio_dmc_channel, _audio_pcm_dropped, _audio_pcm_preempted

.segment "BSS"
af_counter: .res 1
af_duration: .res 1
af_delta: .res 1
af_target: .res 1
af_channel: .res 1
af_index: .res 1
af_lead: .res 1
af_bass: .res 1
af_other: .res 1
af_minimum: .res 2
af_tones: .res 10
af_count: .res 1
af_control: .res 1
af_period: .res 2
af_last_period: .res 6
af_last_voice: .res 3
af_oscillator: .res 1

.segment "AUDIOFAST"
af_gain:
.byte 15,14,13,12,11,10,9,8,8,7,6,6,5,5,4,4
.byte 4,3,3,3,3,2,2,2,2,2,2,1,1,1,1,1
.byte 1,1,1,1,1,1,1,1
.repeat 88
.byte 0
.endrepeat
af_product:
.repeat 16, V
  .repeat 16, G
    .byte ((V*G+7)>>4)
  .endrepeat
.endrepeat
af_psg_gain: .byte 15,12,9,8,6,5,4,3,2,2,2,1,1,1,1,0

_audio_render_reset:
    lda #255
    ldx #5
@periods:
    sta af_last_period,x
    dex
    bpl @periods
    ldx #2
@voices:
    sta af_last_voice,x
    dex
    bpl @voices
    rts

_audio_render_tick:
    ; Keep the original reverse traversal order, while removing per-voice
    ; table lookup and loop bookkeeping. The PSG clock phase is invariant
    ; during this renderer call.
    lda _audio_sfx_phase
    bne :+
.repeat 4, I
    ldx #(27-I)
    jsr af_psg_envelope
.endrepeat
:
.repeat 3, I
    ldx #(22-I)
    jsr af_fm_envelope
.endrepeat
.repeat 3, I
    ldx #(18-I)
    jsr af_fm_envelope
.endrepeat
    lda _audio_sfx_phase
    bne :+
.repeat 4, I
    ldx #(11-I)
    jsr af_psg_envelope
.endrepeat
:
.repeat 3, I
    ldx #(6-I)
    jsr af_fm_envelope
.endrepeat
.repeat 3, I
    ldx #(2-I)
    jsr af_fm_envelope
.endrepeat

    ldy #11
@volumes:
    sty af_channel
    tya
    ldx _audio_owner,y
    beq :+
    ora #16
:   tax
    lda _audio_pan,x
    beq @mute
    cpy #8
    bcs @psg_volume
    lda _audio_envelope,x
    beq @mute
    ldy _audio_attenuation,x
    lda af_gain,y
    sta af_delta
    lda _audio_envelope,x
    asl a
    asl a
    asl a
    asl a
    ora af_delta
    tax
    lda af_product,x
    jmp @volume_ready
@psg_volume:
    lda _audio_psg_level,x
    cmp #16
    bcc @mute
    lsr a
    lsr a
    lsr a
    lsr a
    eor #15
    sta af_delta
    lda _audio_attenuation,x
    cmp #41
    bcc :+
    lda #40
:   sta af_duration
    asl a
    clc
    adc af_duration
    lsr a
    lsr a
    lsr a
    clc
    adc af_delta
    cmp #16
    bcc :+
    lda #15
:   tax
    lda af_psg_gain,x
    jmp @volume_ready
@mute:
    lda #0
@volume_ready:
    ldy af_channel
    sta _audio_current_volume,y
    dey
    bpl @volumes

    lda #255
    sta af_lead
    sta af_bass
    sta af_other
    ldy #10
@first_lead:
    lda _audio_current_volume,y
    beq :+
    sty af_lead
:   dey
    bpl @first_lead
    lda af_lead
    cmp #255
    bne :+
    jmp @selected
:
    ; Lowest numbered audible effect channel has lead priority.
    ldy #10
@effect_lead:
    lda _audio_current_volume,y
    beq :+
    lda _audio_owner,y
    beq :+
    sty af_lead
:   dey
    bpl @effect_lead
    lda #255
    sta af_minimum
    sta af_minimum+1
    ldy #0
@find_bass:
    cpy af_lead
    beq @next_bass
    lda _audio_current_volume,y
    beq @next_bass
    jsr af_effective_pitch_index
    lda _audio_pitch+1,x
    cmp af_minimum+1
    bcc @lower
    bne @next_bass
    lda _audio_pitch,x
    cmp af_minimum
    bcs @next_bass
@lower:
    lda _audio_pitch,x
    sta af_minimum
    lda _audio_pitch+1,x
    sta af_minimum+1
    sty af_bass
@next_bass:
    iny
    cpy #11
    bcc @find_bass
    lda #0
    sta af_count
    ldy #0
@find_others:
    cpy af_lead
    beq @next_other
    cpy af_bass
    beq @next_other
    lda _audio_current_volume,y
    beq @next_other
    ldx af_count
    tya
    sta af_tones,x
    inc af_count
@next_other:
    iny
    cpy #11
    bcc @find_others
    lda af_count
    beq @selected
    ldx _audio_round_robin
    cpx af_count
    bcc :+
    ldx #0
:   lda af_tones,x
    sta af_other
    inx
    stx _audio_round_robin
    lda af_count
    cmp #2
    bcc @selected
    inc _audio_arpeggio_count
    bne @selected
    inc _audio_arpeggio_count+1
@selected:
    lda #0
    sta af_oscillator
    lda af_lead
    jsr af_pulse
    lda #1
    sta af_oscillator
    lda af_other
    jsr af_pulse
    lda af_bass
    cmp #255
    bne @triangle
    lda #128
    sta $4008
    jmp @noise
@triangle:
    tay
    jsr af_effective_pitch_index
    cpy #8
    bcc @fm_triangle_period
    txa
    and #6
    sta af_delta
    txa
    and #32
    lsr a
    lsr a
    ora af_delta
    tax
    lda _audio_psg_triangle_period,x
    sta af_period
    lda _audio_psg_triangle_period+1,x
    jmp @triangle_period_ready
@fm_triangle_period:
    lda _audio_triangle_period,x
    sta af_period
    lda _audio_triangle_period+1,x
@triangle_period_ready:
    sta af_period+1
    lda #255
    sta $4008
    lda af_period
    sta $400a
    lda af_last_voice+2
    cmp af_bass
    bne @triangle_high
    lda af_last_period+4
    cmp af_period
    bne @triangle_high
    lda af_last_period+5
    cmp af_period+1
    beq @noise
@triangle_high:
    lda af_bass
    sta af_last_voice+2
    lda af_period
    sta af_last_period+4
    lda af_period+1
    sta af_last_period+5
    and #7
    ora #248
    sta $400b
@noise:
    lda _audio_current_volume+11
    ora #48
    sta $400c
    ldy #11
    jsr af_effective_pitch_index
    lda _audio_pitch,x
    and #3
    sta af_delta
    asl a
    clc
    adc af_delta
    adc #2
    sta af_delta
    lda _audio_pitch,x
    and #4
    bne @white_noise
    lda #128
    bne @noise_control
@white_noise:
    lda #0
@noise_control:
    ora af_delta
    sta $400e
    lda #248
    sta $400f
    jmp af_pcm

af_effective_pitch_index:
    tya
    ldx _audio_owner,y
    beq :+
    ora #16
:   asl a
    tax
    rts

af_pulse:
    sta af_channel
    cmp #255
    bne @active
    lda #48
    ldx af_oscillator
    beq :+
    sta $4004
    rts
:   sta $4000
    rts
@active:
    tay
    tya
    ldx _audio_owner,y
    beq :+
    ora #16
:   tax
    lda _audio_duty,x
    ror a
    ror a
    ror a
    and #192
    ora #48
    ora _audio_current_volume,y
    sta af_control
    cpy #8
    bcc @fm_period
    txa
    and #3
    asl a
    sta af_delta
    txa
    and #16
    lsr a
    ora af_delta
    tax
    lda _audio_psg_pulse_period,x
    sta af_period
    lda _audio_psg_pulse_period+1,x
    jmp @period_ready
@fm_period:
    txa
    asl a
    tax
    lda _audio_pulse_period,x
    sta af_period
    lda _audio_pulse_period+1,x
@period_ready:
    sta af_period+1
    ldx af_oscillator
    beq @pulse1
    lda af_control
    sta $4004
    lda #8
    sta $4005
    lda af_period
    sta $4006
    jmp @test_high
@pulse1:
    lda af_control
    sta $4000
    lda #8
    sta $4001
    lda af_period
    sta $4002
@test_high:
    lda af_last_voice,x
    cmp af_channel
    bne @high
    txa
    asl a
    tay
    lda af_last_period,y
    cmp af_period
    bne @high
    lda af_last_period+1,y
    cmp af_period+1
    beq @done
@high:
    lda af_channel
    sta af_last_voice,x
    txa
    asl a
    tay
    lda af_period
    sta af_last_period,y
    lda af_period+1
    sta af_last_period+1,y
    and #7
    ora #248
    cpx #0
    beq :+
    sta $4007
    rts
:   sta $4003
@done:
    rts

af_fm_envelope:
    lda _audio_envelope_phase,x
    cmp #1
    beq @attack
    cmp #2
    beq @decay
    cmp #4
    bne :+
    jmp @release
:
    rts
@attack:
    lda _audio_gate,x
    beq @done
    lda _audio_attack_ticks,x
    cmp #2
    bcs :+
    ; Qualified source attack counters start at zero; a one-tick attack
    ; reaches full level immediately without fifteen subtract iterations.
    lda #15
    sta _audio_envelope,x
    jmp @attack_done
:   sta af_duration
    lda #15
    sta af_target
    sta af_delta
    jsr af_add_counter
@attack_loop:
    lda _audio_envelope,x
    cmp #15
    bcs @attack_done
    jsr af_consume_counter
    bcc @done
    inc _audio_envelope,x
    jmp @attack_loop
@attack_done:
    lda #2
    sta _audio_envelope_phase,x
    txa
    asl a
    tay
    lda #0
    sta _audio_envelope_counter,y
    sta _audio_envelope_counter+1,y
@done:
    rts
@decay:
    lda _audio_gate,x
    beq @done
    lda _audio_decay_ticks,x
    bne :+
    lda #1
:   sta af_duration
    lda #15
    sec
    sbc _audio_sustain,x
    sta af_delta
    jsr af_add_counter
@decay_loop:
    lda _audio_envelope,x
    cmp _audio_sustain,x
    beq @sustain
    bcc @sustain
    jsr af_consume_counter
    bcc @done
    dec _audio_envelope,x
    jmp @decay_loop
@sustain:
    lda #3
    sta _audio_envelope_phase,x
    rts
@release:
    lda _audio_envelope,x
    beq @done
    lda _audio_release_ticks,x
    bne :+
    lda #1
:   sta af_duration
    lda _audio_release_peak,x
    sta af_delta
    jsr af_add_counter
@release_loop:
    lda _audio_envelope,x
    beq @done
    jsr af_consume_counter
    bcc @done
    dec _audio_envelope,x
    jmp @release_loop

af_add_counter:
    txa
    asl a
    tay
    lda _audio_envelope_counter,y
    clc
    adc af_delta
    sta _audio_envelope_counter,y
    bcc :+
    lda _audio_envelope_counter+1,y
    adc #0
    sta _audio_envelope_counter+1,y
:   rts

af_consume_counter:
    lda _audio_envelope_counter+1,y
    bne @consume
    lda _audio_envelope_counter,y
    cmp af_duration
    bcc @no
@consume:
    lda _audio_envelope_counter,y
    sec
    sbc af_duration
    sta _audio_envelope_counter,y
    lda _audio_envelope_counter+1,y
    sbc #0
    sta _audio_envelope_counter+1,y
    sec
    rts
@no:
    clc
    rts

af_psg_envelope:
    ; Original square-PSG pitch output shares the /2 SFX/envelope clock.
    stx af_index
    txa
    and #3
    asl a
    sta af_delta
    txa
    and #16
    lsr a
    ora af_delta
    tay
    txa
    asl a
    tax
    lda _audio_pulse_period,x
    sta _audio_psg_pulse_period,y
    lda _audio_pulse_period+1,x
    sta _audio_psg_pulse_period+1,y
    lda _audio_triangle_period,x
    sta _audio_psg_triangle_period,y
    lda _audio_triangle_period+1,x
    sta _audio_psg_triangle_period+1,y
    ldx af_index
    lda _audio_envelope_phase,x
    cmp #1
    beq @attack
    cmp #2
    beq @decay
    cmp #3
    beq @sustain
    lda _audio_psg_rr,x
    jmp @subtract
@sustain:
    lda _audio_psg_sr,x
@subtract:
    sta af_delta
    lda _audio_psg_level,x
    sec
    sbc af_delta
    bcs @store
    lda #0
    jmp @store
@attack:
    lda _audio_psg_level,x
    clc
    adc _audio_psg_ar,x
    bcs @attack_done
    cmp _audio_psg_tl,x
    bcc @store
@attack_done:
    lda #2
    sta _audio_envelope_phase,x
    lda _audio_psg_tl,x
    jmp @store
@decay:
    lda _audio_psg_level,x
    sec
    sbc _audio_psg_dr,x
    bcc @decay_done
    cmp _audio_psg_sl,x
    bcs @store
@decay_done:
    lda #3
    sta _audio_envelope_phase,x
    lda _audio_psg_sl,x
@store:
    sta _audio_psg_level,x
    lsr a
    lsr a
    lsr a
    lsr a
    sta _audio_envelope,x
    rts

af_pcm:
    ldx #6
@timers:
    lda _audio_pcm_ticks,x
    ora _audio_pcm_ticks+1,x
    beq @next_timer
    lda _audio_pcm_ticks,x
    bne :+
    dec _audio_pcm_ticks+1,x
:   dec _audio_pcm_ticks,x
@next_timer:
    dex
    dex
    bpl @timers
    lda _audio_dmc_playing
    beq @choose
    lda _audio_dmc_source
    asl a
    tax
    lda _audio_pcm_ticks,x
    ora _audio_pcm_ticks+1,x
    bne @choose
    lda #15
    sta $4015
    lda #0
    sta _audio_dmc_playing
@choose:
    ldx #6
@select:
    lda _audio_pcm_ticks,x
    ora _audio_pcm_ticks+1,x
    beq @next_candidate
    lda _audio_pcm_generation,x
    cmp _audio_dmc_delivered,x
    bne @selected
    lda _audio_pcm_generation+1,x
    cmp _audio_dmc_delivered+1,x
    bne @selected
@next_candidate:
    dex
    dex
    bpl @select
    lda #255
    sta af_index
    jmp @mark_delivered
@selected:
    stx af_index
    cpx #4
    bcs @candidate_allowed
    lda _audio_dmc_playing
    beq @candidate_allowed
    lda _audio_dmc_source
    cmp #2
    bcc @candidate_allowed
    asl a
    tay
    lda _audio_pcm_generation,y
    cmp _audio_dmc_generation
    bne @candidate_allowed
    lda _audio_pcm_generation+1,y
    cmp _audio_dmc_generation+1
    bne @candidate_allowed
    lda #255
    sta af_index
    jmp @mark_delivered
@candidate_allowed:
    lda _audio_pcm_generation,x
    cmp _audio_dmc_delivered,x
    bne @new_note
    lda _audio_pcm_generation+1,x
    cmp _audio_dmc_delivered+1,x
    bne @new_note
    jmp @mark_delivered
@new_note:
    lda _audio_dmc_playing
    beq @trigger
    txa
    lsr a
    cmp _audio_dmc_source
    beq @trigger
    lda _audio_dmc_source
    asl a
    tay
    lda _audio_pcm_generation,y
    cmp _audio_dmc_generation
    bne @trigger
    lda _audio_pcm_generation+1,y
    cmp _audio_dmc_generation+1
    bne @trigger
    inc _audio_pcm_preempted
    bne @trigger
    inc _audio_pcm_preempted+1
@trigger:
    ldx af_index
    lda _audio_pcm_generation,x
    sta _audio_dmc_generation
    lda _audio_pcm_generation+1,x
    sta _audio_dmc_generation+1
    txa
    lsr a
    tax
    stx _audio_dmc_source
    txa
    lsr a
    sta _audio_dmc_slot
    txa
    and #1
    sta _audio_dmc_channel
    lda #1
    sta _audio_dmc_playing
    lda #15
    sta $4015
    lda _audio_dmc_rate,x
    sta $4010
    lda #64
    sta $4011
    lda _audio_dmc_address,x
    sta $4012
    lda _audio_dmc_length,x
    sta $4013
    lda #31
    sta $4015
@mark_delivered:
    ldx #6
@mark_loop:
    cpx af_index
    beq @copy_generation
    lda _audio_pcm_generation,x
    cmp _audio_dmc_delivered,x
    bne @dropped
    lda _audio_pcm_generation+1,x
    cmp _audio_dmc_delivered+1,x
    beq @copy_generation
@dropped:
    inc _audio_pcm_dropped
    bne @copy_generation
    inc _audio_pcm_dropped+1
@copy_generation:
    lda _audio_pcm_generation,x
    sta _audio_dmc_delivered,x
    lda _audio_pcm_generation+1,x
    sta _audio_dmc_delivered+1,x
    dex
    dex
    bpl @mark_loop
    rts
