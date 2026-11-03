/* fDisBull source-event audio runtime. Original songs/samples are supplied as
 * private generated data, not distributed with this source.
 *
 * SonaStream semantics are recovered from Sona 0.50 (Sik, zlib license), the
 * Miniplanets REV04 streams and original-CPU observations. This is an original
 * implementation. FM/PSG timbre and excess polyphony are explicitly arranged
 * for pulse1, pulse2, triangle, noise and one DMC voice.
 *
 * The owner calls audio_tick twice per NTSC NES frame. A phase accumulator
 * follows the original Timer-B rate (118.89964 Hz); SFX uses every second tick.
 * Requests and ticks must have one owner
 * (the IRQ/NMI drain); the game submits requests through its separate queue.
 * The IRQ wrapper must preserve cc65 zero page, software stack and bank state.
 */

extern unsigned char audio_stream_byte(unsigned char track, unsigned int offset);
extern unsigned int audio_stream_size(unsigned char track);
extern unsigned char audio_instrument_byte(unsigned char audio_instrument, unsigned char field);
/* oscillator: 0=pulse/FM, 1=triangle/FM, 2=pulse/PSG, 3=triangle/PSG. */
extern unsigned int audio_period(unsigned int pitch16, unsigned char oscillator);
#ifndef FDISBULL_AUDIO_HOST
extern void audio_render_reset(void);
#endif

#ifdef FDISBULL_AUDIO_HOST
extern void audio_hw_write(unsigned int address, unsigned char value);
#define AWRITE(address,value) audio_hw_write((address),(unsigned char)(value))
#else
#define AWRITE(address,value) (*(volatile unsigned char *)(address) = (unsigned char)(value))
#endif

unsigned char audio_error;
unsigned char audio_bgm_id;
unsigned char audio_sfx_id;
unsigned char audio_stream_active[2];
unsigned int audio_tick_count;
unsigned int audio_interrupt_count;
unsigned int audio_command_count;
unsigned int audio_note_count;
unsigned int audio_arpeggio_count;
unsigned int audio_event_crc;

static unsigned char track[2];
static unsigned int stream_size[2];
static unsigned int pc[2], loop_pc[2], delay_ticks[2];
static unsigned int bgm_phase;
static unsigned int nes_phase;
static unsigned char bgm_speed, sfx_priority;
unsigned char audio_sfx_phase;
static unsigned char status_busy;
unsigned int audio_pitch[32];
unsigned int audio_pulse_period[32], audio_triangle_period[32];
unsigned int audio_psg_pulse_period[8], audio_psg_triangle_period[8];
unsigned char audio_instrument[32], audio_attenuation[32];
unsigned char audio_gate[32], audio_envelope[32], audio_pan[32];
unsigned char audio_duty[32];
unsigned char audio_attack_ticks[32], audio_decay_ticks[32], audio_sustain[32], audio_release_ticks[32];
unsigned char audio_envelope_phase[32], audio_release_peak[32];
unsigned int audio_envelope_counter[32];
unsigned char audio_psg_level[32], audio_psg_tl[32], audio_psg_ar[32];
unsigned char audio_psg_sl[32], audio_psg_dr[32], audio_psg_sr[32], audio_psg_rr[32];
unsigned char audio_metadata[476];
unsigned char audio_owner[16];
unsigned int audio_pcm_ticks[4], audio_pcm_generation[4];
unsigned char audio_pcm_instrument[4];
unsigned char audio_round_robin;
unsigned char audio_current_volume[12];
#define P(slot,channel) ((unsigned char)(((slot)<<1)|(channel)))
#define G(slot,channel) ((unsigned char)(((slot)<<2)|((channel)-8)))
#define V(slot,channel) ((unsigned char)(((slot)<<4)|(channel)))
#define effective_slot(channel) (audio_owner[(channel)] ? 1 : 0)
static unsigned char last_voice[3];
static unsigned int last_period[3];
unsigned int audio_dmc_generation;
unsigned int audio_dmc_delivered[4];
unsigned int audio_pcm_dropped, audio_pcm_preempted;
unsigned char audio_dmc_source, audio_dmc_playing;
unsigned char audio_dmc_address[4],audio_dmc_length[4],audio_dmc_rate[4];
unsigned char audio_dmc_slot, audio_dmc_channel;

#ifdef FDISBULL_AUDIO_HOST
static const unsigned char gain[128] = {
    15,14,13,12,11,10,9,8,8,7,6,6,5,5,4,4,
    4,3,3,3,3,2,2,2,2,2,2,1,1,1,1,1,
    1,1,1,1,1,1,1,1,0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
};
static const unsigned char psg_gain[16]={15,12,9,8,6,5,4,3,2,2,2,1,1,1,1,0};

#endif

static unsigned char read_byte(unsigned char slot)
{
    unsigned char value;
    if (pc[slot] >= stream_size[slot]) {
        audio_error = 1;
        audio_stream_active[slot] = 0;
        return 255;
    }
    value = audio_stream_byte(track[slot],pc[slot]);
    pc[slot]++;
    return value;
}

static unsigned char channel_number(unsigned char value)
{
    if (value == 3) return 2;
    return value;
}

static unsigned int read_pitch(unsigned char slot, unsigned char channel)
{
    unsigned char first, second, octave, semitone;
    unsigned int value, distance;
    first = read_byte(slot);
    if (first == 128) return audio_pitch[V(slot,channel)];
    if (first < 112) {
        octave = first & 7;
        if (channel >= 8) octave += 2;
        value = ((unsigned int)octave * 12 + (first >> 3)) * 16;
    } else if (first < 128) {
        second = read_byte(slot);
        octave = second & 7;
        if (channel >= 8) octave += 2;
        value = ((unsigned int)octave * 12 + ((second >> 3) & 15)) * 16 + (first & 15);
    } else {
        if (first < 240) {
            octave = first & 3;
            semitone = (first >> 3) & 15;
            distance = ((unsigned int)octave * 12 + semitone) * 16;
            second = first & 4;
        } else {
            second = read_byte(slot);
            distance = ((unsigned int)(second & 7) * 12 + ((second >> 3) & 15)) * 16 + (first & 15);
            second &= 128;
        }
        if (second) {
            value = audio_pitch[V(slot,channel)] < distance ? 0 : audio_pitch[V(slot,channel)] - distance;
        } else value = audio_pitch[V(slot,channel)] + distance;
    }
    return value > 1535 ? 1535 : value;
}

static void free_sfx(void)
{
    unsigned char channel;
    audio_stream_active[1] = 0;
    sfx_priority = 0;
    for (channel=0; channel<16; channel++) {
        if (audio_owner[channel]) { audio_gate[V(0,channel)]=0; audio_envelope[V(0,channel)]=0; audio_psg_level[V(0,channel)]=0; audio_envelope_phase[V(0,channel)]=4; }
        audio_owner[channel] = 0;
        audio_gate[V(1,channel)] = 0;
        audio_envelope[V(1,channel)] = 0;
    }
    audio_pcm_ticks[P(1,0)] = audio_pcm_ticks[P(1,1)] = 0;
}

void audio_stopall(void)
{
    unsigned char slot, channel;
    for (slot=0; slot<2; slot++) {
        audio_stream_active[slot] = 0;
        for (channel=0; channel<16; channel++) {
            audio_gate[V(slot,channel)] = 0;
            audio_envelope[V(slot,channel)] = 0;
            audio_psg_level[V(slot,channel)] = 0;
            audio_envelope_phase[V(slot,channel)] = 4;
            audio_attenuation[V(slot,channel)] = 0;
            audio_pan[V(slot,channel)] = 192;
        }
        for (channel=0; channel<2; channel++) audio_pcm_ticks[P(slot,channel)] = 0;
    }
    free_sfx();
    audio_bgm_id = audio_sfx_id = 0;
    audio_dmc_playing=0;
    audio_dmc_source=255;
    for(channel=0;channel<4;channel++) audio_dmc_delivered[channel]=audio_pcm_generation[channel];
    AWRITE(0x4000,48);AWRITE(0x4004,48);
    AWRITE(0x4008,128);AWRITE(0x400c,48);
    AWRITE(0x4015,15);
}

void audio_init(void)
{
    unsigned char i,field;
    unsigned int offset;
    audio_error = 0;
    audio_tick_count = audio_interrupt_count = audio_command_count = audio_note_count = 0;
    audio_arpeggio_count = audio_event_crc = 0;
    audio_pcm_dropped = audio_pcm_preempted = 0;
    bgm_phase = nes_phase = 0;
    audio_sfx_phase = 0;
    status_busy = 0;
    bgm_speed = 32;
    audio_round_robin = 0;
    for (i=0; i<3; i++) { last_voice[i] = 255; last_period[i] = 65535U; }
    audio_dmc_slot = audio_dmc_channel = 255;
    audio_dmc_generation = 65535U;
    for(i=0;i<4;i++) audio_dmc_delivered[i]=audio_pcm_generation[i];
    AWRITE(0x4017,64);
    AWRITE(0x4010,9);
    AWRITE(0x4011,64);
    offset=0;
    for (i=0;i<28;i++) for (field=0;field<17;field++) audio_metadata[offset++]=audio_instrument_byte(i,field);
    audio_stopall();
#ifndef FDISBULL_AUDIO_HOST
    audio_render_reset();
#endif
}

void audio_request(unsigned char kind, unsigned char ident)
{
    unsigned char priority;
    if (kind == 3 || (kind == 1 && ident == 255)) {
        audio_stopall();
    } else if (kind == 1 && ident >= 1 && ident <= 13) {
        audio_stopall();
        audio_bgm_id = ident;
        track[0] = ident - 1;
        stream_size[0] = audio_stream_size(track[0]);
        pc[0] = loop_pc[0] = 0;
        delay_ticks[0] = 1;
        audio_stream_active[0] = 1;
        bgm_phase = 0;
        bgm_speed = 32;
    } else if (kind == 2 && ident >= 1 && ident <= 19) {
        priority = (ident - 1) * 4;
        if (audio_stream_active[1] && priority < sfx_priority) return;
        free_sfx();
        audio_sfx_id = ident;
        sfx_priority = priority;
        track[1] = ident + 12;
        stream_size[1] = audio_stream_size(track[1]);
        pc[1] = loop_pc[1] = 0;
        delay_ticks[1] = 1;
        audio_stream_active[1] = 1;
    }
}

unsigned char audio_busy(void)
{
    return status_busy;
}

static void source_tick(unsigned char slot)
{
    unsigned char op, category, channel, rawchannel, value, part, index;
    unsigned int budget, metadata_offset;
    if (!audio_stream_active[slot]) return;
    delay_ticks[slot]--;
    if (delay_ticks[slot]) return;
    budget = 2048;
    while (budget && audio_stream_active[slot]) {
        budget--;
        op = read_byte(slot);
        if (!audio_stream_active[slot]) return;
        audio_command_count++;
        audio_event_crc = ((audio_event_crc << 1) ^ op ^ pc[slot]) & 65535U;
        category = op >> 4;
        rawchannel = op & 15;
        channel = channel_number(rawchannel);
        index=V(slot,channel);
        if (category == 0) {
            value = read_byte(slot);
            if (value >= 28) { audio_error=2; audio_stream_active[slot]=0; return; }
            audio_instrument[index] = value;
            metadata_offset=(unsigned int)value*17;
            audio_duty[index] = audio_metadata[metadata_offset+1];
            audio_attack_ticks[index] = audio_metadata[metadata_offset+2];
            audio_decay_ticks[index] = audio_metadata[metadata_offset+3];
            audio_sustain[index] = audio_metadata[metadata_offset+4];
            audio_release_ticks[index] = audio_metadata[metadata_offset+5];
            if (channel>=8) {
                audio_psg_level[index]=0;
                audio_envelope_phase[index]=4;
                audio_psg_tl[index]=audio_metadata[metadata_offset+11];
                audio_psg_ar[index]=audio_metadata[metadata_offset+12];
                audio_psg_sl[index]=audio_metadata[metadata_offset+13];
                audio_psg_dr[index]=audio_metadata[metadata_offset+14];
                audio_psg_sr[index]=audio_metadata[metadata_offset+15];
                audio_psg_rr[index]=audio_metadata[metadata_offset+16];
            }
        } else if (category == 1 || category == 3) {
            if (channel >= 14) {
                value = read_byte(slot);
                metadata_offset=(unsigned int)value*17;
                if (value >= 28 || audio_metadata[metadata_offset] != 2) {
                    audio_error=3; audio_stream_active[slot]=0; return;
                }
                if ((slot && audio_owner[channel]) || (!slot && !audio_owner[channel])) {
                    audio_pcm_instrument[P(slot,channel-14)] = value;
                    audio_pcm_ticks[P(slot,channel-14)] = audio_metadata[metadata_offset+9] | ((unsigned int)audio_metadata[metadata_offset+10] << 8);
                    audio_pcm_generation[P(slot,channel-14)]++;
                    audio_dmc_address[P(slot,channel-14)]=audio_metadata[metadata_offset+6];
                    audio_dmc_length[P(slot,channel-14)]=audio_metadata[metadata_offset+7];
                    audio_dmc_rate[P(slot,channel-14)]=audio_metadata[metadata_offset+8];
                }
            } else {
                if (channel == 11) audio_pitch[index] = read_byte(slot);
                else {
                    for (part=0; part<(rawchannel == 3 ? 4 : 1); part++)
                        audio_pitch[index] = read_pitch(slot,channel);
                }
                if (channel != 11) {
                    audio_pulse_period[index]=audio_period(audio_pitch[index],channel>=8 ? 2 : 0);
                    audio_triangle_period[index]=audio_period(audio_pitch[index],channel>=8 ? 3 : 1);
                }
                if (category == 1) {
                    if ((slot && audio_owner[channel]) || (!slot && !audio_owner[channel])) {
                        audio_gate[index] = 1;
                        if (channel<8) audio_envelope[index] = 0;
                        audio_envelope_phase[index] = 1;
                        audio_envelope_counter[index] = 0;
                    }
                    audio_note_count++;
                }
            }
        } else if (category == 2) {
            if (channel >= 14) audio_pcm_ticks[P(slot,channel-14)] = 0;
            else {
                audio_gate[index] = 0;
                audio_envelope_phase[index] = 4;
                audio_envelope_counter[index] = 0;
                audio_release_peak[index] = audio_envelope[index];
            }
        } else if (category == 4) {
            value = read_byte(slot);
            if (value < 128) audio_attenuation[index] = value;
            else if (value < 192) {
                value = audio_attenuation[index] + (value & 63);
                audio_attenuation[index] = value > 127 ? 127 : value;
            } else {
                value &= 63;
                audio_attenuation[index] = value > audio_attenuation[index] ? 0 : audio_attenuation[index] - value;
            }
        } else if (category == 5) {
            value = read_byte(slot);
            if (rawchannel < 8) audio_pan[index] = value & 192;
        } else if (category == 13) {
            delay_ticks[slot] = rawchannel + 1;
            return;
        } else if (category == 14) {
            if (slot) {
                audio_owner[channel] = 1;
                audio_gate[V(0,channel)] = audio_envelope[V(0,channel)] = 0;
                if (channel>=14) audio_pcm_ticks[P(0,channel-14)]=0;
            }
        } else if (op == 250) bgm_speed = read_byte(slot);
        else if (op == 252) loop_pc[slot] = pc[slot];
        else if (op == 253) pc[slot] = loop_pc[slot];
        else if (op == 254) {
            delay_ticks[slot] = read_byte(slot);
            if (!delay_ticks[slot]) delay_ticks[slot] = 256;
            return;
        } else if (op == 255) {
            if (slot) free_sfx();
            else audio_stream_active[0] = 0;
            return;
        } else {
            audio_error = 4;
            audio_stream_active[slot] = 0;
            return;
        }
    }
    if (!budget && audio_stream_active[slot]) { audio_error=5; audio_stream_active[slot]=0; }
}

#ifdef FDISBULL_AUDIO_HOST
static void pulse(unsigned char number, unsigned char channel)
{
    unsigned char slot, volume, control;
    unsigned int period;
    if (channel == 255) { if (number) AWRITE(0x4004,48); else AWRITE(0x4000,48); return; }
    slot = effective_slot(channel);
    volume = audio_current_volume[channel];
    period = channel>=8 ? audio_psg_pulse_period[G(slot,channel)] : audio_pulse_period[V(slot,channel)];
    control = (audio_duty[V(slot,channel)] << 6) | 48 | volume;
    if (number) { AWRITE(0x4004,control); AWRITE(0x4005,8); AWRITE(0x4006,period); }
    else { AWRITE(0x4000,control); AWRITE(0x4001,8); AWRITE(0x4002,period); }
    if (last_period[number] != period || last_voice[number] != channel) {
        if (number) AWRITE(0x4007,((period >> 8)&7)|248);
        else AWRITE(0x4003,((period >> 8)&7)|248);
        last_period[number] = period;
        last_voice[number] = channel;
    }
}

static void render(void)
{
    unsigned char tones[10], count, channel, slot, lead, bass, other, i, selected;
    unsigned int period, minimum;
    count = 0;
    for (channel=0; channel<12; channel++) {
        slot=effective_slot(channel);
        if (!audio_pan[V(slot,channel)]) audio_current_volume[channel]=0;
        else if (channel>=8) {
            i=audio_attenuation[V(slot,channel)];
            if (i>40) i=40;
            i=(i*3)/8+15-(audio_psg_level[V(slot,channel)]>>4);
            if (i>15) i=15;
            audio_current_volume[channel]=psg_gain[i];
        }
        else audio_current_volume[channel]=(unsigned char)(((unsigned int)audio_envelope[V(slot,channel)]*gain[audio_attenuation[V(slot,channel)]]+7)>>4);
    }
    for (channel=0; channel<11; channel++) {
        if (channel == 3 || channel == 7) continue;
        if (audio_current_volume[channel]) tones[count++] = channel;
    }
    lead = bass = other = 255;
    if (count) {
        lead = tones[0];
        for (i=0; i<count; i++) if (audio_owner[tones[i]]) { lead=tones[i]; break; }
        if (count > 1) {
            minimum = 65535U;
            for (i=0; i<count; i++) {
                channel=tones[i]; slot=effective_slot(channel);
                if (channel!=lead && audio_pitch[V(slot,channel)]<minimum) { minimum=audio_pitch[V(slot,channel)]; bass=channel; }
            }
            count=0;
            for (channel=0; channel<11; channel++) {
                if (channel==3 || channel==7 || channel==lead || channel==bass) continue;
                if (audio_current_volume[channel]) tones[count++]=channel;
            }
            if (count) {
                if (audio_round_robin>=count) audio_round_robin=0;
                other=tones[audio_round_robin++];
                if (count>1) audio_arpeggio_count++;
            }
        }
    }
    pulse(0,lead); pulse(1,other);
    if (bass==255) AWRITE(0x4008,128);
    else {
        slot=effective_slot(bass);
        period=bass>=8 ? audio_psg_triangle_period[G(slot,bass)] : audio_triangle_period[V(slot,bass)];
        AWRITE(0x4008,255); AWRITE(0x400a,period);
        if (last_period[2]!=period || last_voice[2]!=bass) {
            AWRITE(0x400b,((period>>8)&7)|248);
            last_period[2]=period; last_voice[2]=bass;
        }
    }
    slot=effective_slot(11);
    AWRITE(0x400c,48|audio_current_volume[11]);
    AWRITE(0x400e,(audio_pitch[V(slot,11)]&4 ? 0 : 128)|((audio_pitch[V(slot,11)]&3)*3+2));
    AWRITE(0x400f,248);
    /* A source sample is delivered at most once, at its event time. Hardware
       preemption truncates; a blocked sample is dropped, never queued late. */
    if(audio_dmc_playing && !audio_pcm_ticks[audio_dmc_source]){
        AWRITE(0x4015,15);audio_dmc_playing=0;
    }
    selected=255;
    for(i=0;i<4;i++)if(audio_pcm_ticks[i] && audio_dmc_delivered[i]!=audio_pcm_generation[i])selected=i;
    if(selected<2 && audio_dmc_playing && audio_dmc_source>=2 &&
       audio_dmc_generation==audio_pcm_generation[audio_dmc_source])selected=255;
    if(selected!=255 && audio_dmc_delivered[selected]!=audio_pcm_generation[selected]){
        if(audio_dmc_playing && audio_dmc_source!=selected &&
           audio_dmc_generation==audio_pcm_generation[audio_dmc_source])audio_pcm_preempted++;
        AWRITE(0x4015,15);AWRITE(0x4010,audio_dmc_rate[selected]);
        AWRITE(0x4011,64);AWRITE(0x4012,audio_dmc_address[selected]);
        AWRITE(0x4013,audio_dmc_length[selected]);AWRITE(0x4015,31);
        audio_dmc_source=selected;audio_dmc_playing=1;
        audio_dmc_slot=selected>>1;audio_dmc_channel=selected&1;
        audio_dmc_generation=audio_pcm_generation[selected];
    }
    for(i=0;i<4;i++){
        if(i!=selected && audio_dmc_delivered[i]!=audio_pcm_generation[i])audio_pcm_dropped++;
        audio_dmc_delivered[i]=audio_pcm_generation[i];
    }
}

void audio_render_reference(void)
{
    unsigned char slot, channel, duration, stage;
    unsigned int level;
    for (slot=0; slot<2; slot++) {
        for (channel=0; channel<12; channel++) {
            if (channel==3 || channel==7) continue;
            if (channel>=8 && audio_sfx_phase) continue;
            stage=audio_envelope_phase[V(slot,channel)];
            if (channel>=8) {
                audio_psg_pulse_period[G(slot,channel)]=audio_pulse_period[V(slot,channel)];
                audio_psg_triangle_period[G(slot,channel)]=audio_triangle_period[V(slot,channel)];
                level=audio_psg_level[V(slot,channel)];
                if (stage==1) {
                    level+=audio_psg_ar[V(slot,channel)];
                    if (level>255 || level>=audio_psg_tl[V(slot,channel)]) {
                        level=audio_psg_tl[V(slot,channel)];audio_envelope_phase[V(slot,channel)]=2;
                    }
                } else if (stage==2) {
                    duration=audio_psg_dr[V(slot,channel)];
                    if (level<duration || level-duration<audio_psg_sl[V(slot,channel)]) {
                        level=audio_psg_sl[V(slot,channel)];audio_envelope_phase[V(slot,channel)]=3;
                    } else level-=duration;
                } else {
                    duration=stage==3 ? audio_psg_sr[V(slot,channel)] : audio_psg_rr[V(slot,channel)];
                    level=level<duration ? 0 : level-duration;
                }
                audio_psg_level[V(slot,channel)]=(unsigned char)level;
                audio_envelope[V(slot,channel)]=(unsigned char)(level>>4);
                continue;
            }
            if (stage==1 && audio_gate[V(slot,channel)]) {
                duration=audio_attack_ticks[V(slot,channel)];
                if (!duration) duration=1;
                audio_envelope_counter[V(slot,channel)]+=15;
                while (audio_envelope_counter[V(slot,channel)]>=duration && audio_envelope[V(slot,channel)]<15) {
                    audio_envelope_counter[V(slot,channel)]-=duration;
                    audio_envelope[V(slot,channel)]++;
                }
                if (audio_envelope[V(slot,channel)]==15) { audio_envelope_phase[V(slot,channel)]=2; audio_envelope_counter[V(slot,channel)]=0; }
            } else if (stage==2 && audio_gate[V(slot,channel)]) {
                duration=audio_decay_ticks[V(slot,channel)];
                if (!duration) duration=1;
                audio_envelope_counter[V(slot,channel)]+=15-audio_sustain[V(slot,channel)];
                while (audio_envelope_counter[V(slot,channel)]>=duration && audio_envelope[V(slot,channel)]>audio_sustain[V(slot,channel)]) {
                    audio_envelope_counter[V(slot,channel)]-=duration;
                    audio_envelope[V(slot,channel)]--;
                }
                if (audio_envelope[V(slot,channel)]<=audio_sustain[V(slot,channel)]) audio_envelope_phase[V(slot,channel)]=3;
            } else if (stage==4 && audio_envelope[V(slot,channel)]) {
                duration=audio_release_ticks[V(slot,channel)];
                if (!duration) duration=1;
                audio_envelope_counter[V(slot,channel)]+=audio_release_peak[V(slot,channel)];
                while (audio_envelope_counter[V(slot,channel)]>=duration && audio_envelope[V(slot,channel)]) {
                    audio_envelope_counter[V(slot,channel)]-=duration;
                    audio_envelope[V(slot,channel)]--;
                }
            }
        }
        for (channel=0; channel<2; channel++) if (audio_pcm_ticks[P(slot,channel)]) audio_pcm_ticks[P(slot,channel)]--;
    }
    render();
}

#endif
#ifndef FDISBULL_AUDIO_HOST
extern void audio_render_tick(void);
#endif

void audio_tick(void)
{
    unsigned int previous;
    audio_interrupt_count++;
    previous=nes_phase;
    nes_phase=(nes_phase+64828U)&65535U;
    if (nes_phase>=previous) return;
    audio_tick_count++;
    bgm_phase += (unsigned int)bgm_speed * 4;
    while (bgm_phase>=256) { bgm_phase-=256; source_tick(0); }
    audio_sfx_phase^=1;
    if (!audio_sfx_phase) {
        source_tick(1);
        status_busy=audio_stream_active[1];
    }
#ifdef FDISBULL_AUDIO_HOST
    audio_render_reference();
#else
    audio_render_tick();
#endif
}
