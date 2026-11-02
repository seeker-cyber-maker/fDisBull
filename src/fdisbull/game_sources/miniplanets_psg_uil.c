/* Source-level UIL for the optimized eight-voice PSG envelope service.
 *
 * This is a semantic model of the PSG subroutine used by the Miniplanets NES
 * audio adapter. It does not model the surrounding stream parser, FM voices,
 * PCM/DMC scheduling, APU writes, or any original ROM region.
 */
typedef unsigned char u8;
typedef unsigned short u16;

u8 audio_sfx_phase;
u16 audio_pulse_period[32], audio_triangle_period[32];
u16 audio_psg_pulse_period[8], audio_psg_triangle_period[8];
u8 audio_envelope_phase[32];
u8 audio_psg_level[32], audio_psg_tl[32], audio_psg_ar[32];
u8 audio_psg_sl[32], audio_psg_dr[32], audio_psg_sr[32], audio_psg_rr[32];
u8 audio_envelope[32];
u8 audio_pan[32], audio_owner[16], audio_attenuation[32], audio_current_volume[12];
static const u8 psg_gain[16] = {15,12,9,8,6,5,4,3,2,2,2,1,1,1,1,0};
static const u8 psg_attenuation_gain[41] = {
    0,0,0,1,1,1,2,2,3,3,3,4,4,4,5,5,6,6,6,7,7,
    7,8,8,9,9,9,10,10,10,11,11,12,12,12,13,13,13,14,14,15
};

void audio_render_psg(void)
{
    u8 slot, channel, index, psg, phase, rate;
    u16 level;

    /* PSG periods and envelopes share a half-rate clock with SFX decoding. */
    if (audio_sfx_phase != 0) return;

    for (slot = 0; slot < 2; ++slot) {
        for (channel = 8; channel < 12; ++channel) {
            index = (u8)(slot * 16 + channel);
            psg = (u8)(slot * 4 + channel - 8);
            phase = audio_envelope_phase[index];
            level = audio_psg_level[index];

            audio_psg_pulse_period[psg] = audio_pulse_period[index];
            audio_psg_triangle_period[psg] = audio_triangle_period[index];

            if (phase == 1) {
                level += audio_psg_ar[index];
                if (level > 255 || level >= audio_psg_tl[index]) {
                    level = audio_psg_tl[index];
                    audio_envelope_phase[index] = 2;
                }
            } else if (phase == 2) {
                if (level < audio_psg_dr[index] ||
                    level - audio_psg_dr[index] < audio_psg_sl[index]) {
                    level = audio_psg_sl[index];
                    audio_envelope_phase[index] = 3;
                } else {
                    level -= audio_psg_dr[index];
                }
            } else {
                if (phase == 3) rate = audio_psg_sr[index];
                else rate = audio_psg_rr[index];
                if (level < rate) level = 0;
                else level -= rate;
            }

            /* Phase 4 at zero has the same observable writes as the ASM fast
             * path: the level is already zero and the derived envelope is 0. */
            audio_psg_level[index] = (u8)level;
            audio_envelope[index] = (u8)(level >> 4);
        }
    }
}

/* Exact PSG branch of af_volume_channel for channels 8 through 11. */
void audio_render_psg_volume(void)
{
    u8 channel, index, level, attenuation, volume;
    u16 amount;

    for (channel = 8; channel < 12; ++channel) {
        index = channel;
        if (audio_owner[channel] != 0) index = (u8)(channel + 16);
        volume = 0;
        if (audio_pan[index] != 0) {
            level = audio_psg_level[index];
            if (level >= 16) {
                attenuation = audio_attenuation[index];
                if (attenuation >= 41) attenuation = 40;
                amount = psg_attenuation_gain[attenuation];
                amount += (u16)(15 - (level >> 4));
                if (amount >= 16) amount = 15;
                volume = psg_gain[(u8)amount];
            }
        }
        audio_current_volume[channel] = volume;
    }
}
