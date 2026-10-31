#!/usr/bin/env python3
"""Check the 6502 audio renderer against C under the pinned sim65 CPU oracle.

Fixtures are authored state vectors, not game assets. This exercises actual
assembled 6502 instructions and records their CPU cost separately from NES
integration, mapper overhead, source parsing and actual APU waveform behavior.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


HARNESS=r'''
#include <stdio.h>
#include <string.h>
#include <sim65.h>
typedef unsigned char u8;
typedef unsigned int u16;
extern u8 audio_gate[32],audio_envelope[32],audio_pan[32],audio_duty[32];
extern u8 audio_attack_ticks[32],audio_decay_ticks[32],audio_sustain[32],audio_release_ticks[32];
extern u8 audio_envelope_phase[32],audio_release_peak[32];
extern u16 audio_envelope_counter[32];
extern u8 audio_psg_level[32],audio_psg_tl[32],audio_psg_ar[32],audio_psg_sl[32];
extern u8 audio_psg_dr[32],audio_psg_sr[32],audio_psg_rr[32],audio_sfx_phase;
extern u8 audio_attenuation[32],audio_owner[16],audio_current_volume[12];
extern u16 audio_pitch[32],audio_pulse_period[32],audio_triangle_period[32];
extern u16 audio_psg_pulse_period[8],audio_psg_triangle_period[8];
extern u8 audio_round_robin;
extern u16 audio_arpeggio_count;
extern u16 audio_pcm_ticks[4],audio_pcm_generation[4];
extern u8 audio_dmc_address[4],audio_dmc_length[4],audio_dmc_rate[4];
extern u16 audio_dmc_delivered[4],audio_dmc_generation,audio_pcm_dropped,audio_pcm_preempted;
extern u8 audio_dmc_source,audio_dmc_playing,audio_dmc_slot,audio_dmc_channel;
void audio_render_reference(void);
void audio_render_tick(void);
void audio_render_reset(void);
void audio_init(void);
void audio_stopall(void);
u8 audio_stream_byte(u8 t,u16 p){return 255;}
u16 audio_stream_size(u8 t){return 1;}
u8 audio_instrument_byte(u8 i,u8 f){return 0;}
u16 audio_period(u16 p,u8 o){return 100;}
void audio_hw_write(u16 a,u8 v){*(volatile u8*)a=v;}
struct Snapshot {
    u8 envelope[32],phase[32],psg[32],volume[12],rr;
    u16 counter[32],pcm[4],arpeggio,psg_pulse[8],psg_triangle[8];
    u16 delivered[4],dmc_generation,dropped,preempted;
    u8 dmc_source,dmc_playing,dmc_slot,dmc_channel;
};
static struct Snapshot before,expected,actual;
static u8 apu_before[24],apu_expected[24];
static u16 random_state;
static u8 random8(void){random_state^=random_state<<7;random_state^=random_state>>9;random_state^=random_state<<8;return (u8)random_state;}
static void save(struct Snapshot *s){
    memcpy(s->envelope,audio_envelope,32);memcpy(s->phase,audio_envelope_phase,32);
    memcpy(s->psg,audio_psg_level,32);memcpy(s->volume,audio_current_volume,12);
    memcpy(s->counter,audio_envelope_counter,64);memcpy(s->pcm,audio_pcm_ticks,8);
    s->rr=audio_round_robin;s->arpeggio=audio_arpeggio_count;
    memcpy(s->psg_pulse,audio_psg_pulse_period,16);memcpy(s->psg_triangle,audio_psg_triangle_period,16);
    memcpy(s->delivered,audio_dmc_delivered,8);s->dmc_generation=audio_dmc_generation;
    s->dropped=audio_pcm_dropped;s->preempted=audio_pcm_preempted;
    s->dmc_source=audio_dmc_source;s->dmc_playing=audio_dmc_playing;s->dmc_slot=audio_dmc_slot;s->dmc_channel=audio_dmc_channel;
}
static void restore(struct Snapshot *s){
    memcpy(audio_envelope,s->envelope,32);memcpy(audio_envelope_phase,s->phase,32);
    memcpy(audio_psg_level,s->psg,32);memcpy(audio_current_volume,s->volume,12);
    memcpy(audio_envelope_counter,s->counter,64);memcpy(audio_pcm_ticks,s->pcm,8);
    audio_round_robin=s->rr;audio_arpeggio_count=s->arpeggio;
    memcpy(audio_psg_pulse_period,s->psg_pulse,16);memcpy(audio_psg_triangle_period,s->psg_triangle,16);
    memcpy(audio_dmc_delivered,s->delivered,8);audio_dmc_generation=s->dmc_generation;
    audio_pcm_dropped=s->dropped;audio_pcm_preempted=s->preempted;
    audio_dmc_source=s->dmc_source;audio_dmc_playing=s->dmc_playing;audio_dmc_slot=s->dmc_slot;audio_dmc_channel=s->dmc_channel;
}
static unsigned long cycles(void){peripherals.counter.latch=0;peripherals.counter.select=0;return peripherals.counter.value32[0];}
int main(void){
    u16 test,i,j;unsigned long start,cost,fast_total,reference_total,fast_max;
    random_state=0x1234;fast_total=reference_total=fast_max=0;
    /* A newly decoded PSG pitch must wait for its physical /2 clock. */
    audio_pan[8]=192;audio_gate[8]=1;audio_psg_level[8]=255;audio_envelope_phase[8]=3;
    audio_pulse_period[8]=123;audio_triangle_period[8]=456;
    audio_psg_pulse_period[0]=321;audio_psg_triangle_period[0]=654;
    for(test=0;test<2;test++){
        audio_sfx_phase=(u8)(1-test);
        save(&before);memcpy(apu_before,(void*)0x4000,24);
        audio_render_reference();save(&expected);memcpy(apu_expected,(void*)0x4000,24);
        if(audio_psg_pulse_period[0]!=(test==0 ? 321 : 123) || audio_psg_triangle_period[0]!=(test==0 ? 654 : 456)){
            puts("PSG physical clock latch regression");return 3;
        }
        restore(&before);memcpy((void*)0x4000,apu_before,24);audio_render_tick();save(&actual);
        if(memcmp(&actual,&expected,sizeof(actual)) || memcmp((void*)0x4000,apu_expected,24)){
            puts("PSG physical clock ASM regression");return 4;
        }
    }
    /* Source PCM0 survives logically while PCM1 preempts it physically.
       It must never restart late; a new blocked PCM0 hit is counted/dropped. */
    audio_dmc_address[0]=16;audio_dmc_address[1]=32;audio_dmc_address[3]=48;
    audio_dmc_rate[0]=audio_dmc_rate[1]=9;audio_dmc_length[0]=audio_dmc_length[1]=3;
    for(test=0;test<9;test++){
        if(test==0){audio_pcm_ticks[0]=10;audio_pcm_generation[0]=1;}
        if(test==1){audio_pcm_ticks[1]=3;audio_pcm_generation[1]=1;}
        if(test==4){audio_pcm_ticks[0]=10;audio_pcm_generation[0]=2;audio_pcm_ticks[3]=3;audio_pcm_generation[3]=1;}
        if(test==5){audio_pcm_ticks[0]=10;audio_pcm_generation[0]=3;}
        if(test==7){audio_pcm_ticks[1]=3;audio_pcm_generation[1]=3;}
        if(test==8){audio_pcm_ticks[0]=10;audio_pcm_generation[0]=4;}
        save(&before);memcpy(apu_before,(void*)0x4000,24);
        audio_render_reference();save(&expected);memcpy(apu_expected,(void*)0x4000,24);
        if((test==3 || test==6) && (audio_dmc_playing || ((u8*)0x4000)[18]!=(test==3 ? 32 : 48) || (((u8*)0x4000)[21]&16))){
            puts("PCM late replay regression");return 5;
        }
        if(test==3 && audio_pcm_preempted!=1){puts("PCM truncation count regression");return 6;}
        if(test==6 && audio_pcm_dropped!=2){puts("PCM drop count regression");return 7;}
        if(test==8 && (!audio_dmc_playing || audio_dmc_source!=0 || audio_pcm_preempted!=2)){
            puts("PCM new music hit rhythm regression");return 9;
        }
        restore(&before);memcpy((void*)0x4000,apu_before,24);audio_render_tick();save(&actual);
        if(memcmp(&actual,&expected,sizeof(actual)) || memcmp((void*)0x4000,apu_expected,24)){
            puts("PCM preemption ASM regression");return 8;
        }
    }
    /* Repeated initialization/stop/restart retains monotonic logical IDs,
       consumes stopped generations, and forces fresh tonal high-register I/O. */
    for(test=0;test<3;test++){
        audio_stopall();
        for(i=0;i<4;i++)if(audio_dmc_delivered[i]!=audio_pcm_generation[i]){
            puts("PCM stop generation reset regression");return 10;
        }
        if(audio_dmc_playing || audio_dmc_source!=255){puts("PCM stop physical reset regression");return 11;}
        audio_init();audio_render_reset();
        audio_pcm_generation[0]++;audio_pcm_ticks[0]=8;
        audio_dmc_address[0]=16;audio_dmc_rate[0]=9;audio_dmc_length[0]=3;
        audio_gate[0]=1;audio_envelope[0]=15;audio_envelope_phase[0]=3;
        audio_pan[0]=192;audio_pulse_period[0]=321;audio_triangle_period[0]=654;
        ((u8*)0x4000)[3]=0;
        save(&before);memcpy(apu_before,(void*)0x4000,24);
        audio_render_reference();save(&expected);memcpy(apu_expected,(void*)0x4000,24);
        if(!audio_dmc_playing || audio_dmc_source!=0 || ((u8*)0x4000)[3]!=249){puts("Audio restart output regression");return 12;}
        restore(&before);memcpy((void*)0x4000,apu_before,24);audio_render_tick();save(&actual);
        if(memcmp(&actual,&expected,sizeof(actual)) || memcmp((void*)0x4000,apu_expected,24)){
            puts("Audio restart ASM regression");return 13;
        }
    }
    for(test=0;test<512;test++){
        for(i=0;i<32;i++){
            audio_gate[i]=random8()&1;audio_envelope[i]=random8()&15;audio_pan[i]=192;
            audio_duty[i]=random8()&3;audio_attack_ticks[i]=(random8()&7)+1;
            audio_decay_ticks[i]=(random8()&31)+1;audio_sustain[i]=random8()&15;
            audio_release_ticks[i]=(random8()&31)+1;audio_envelope_phase[i]=(random8()&3)+1;
            audio_release_peak[i]=(random8()&15)+1;audio_envelope_counter[i]=random8();
            audio_psg_level[i]=random8();audio_psg_tl[i]=random8();audio_psg_ar[i]=random8();
            audio_psg_sl[i]=random8();audio_psg_dr[i]=random8();audio_psg_sr[i]=random8();audio_psg_rr[i]=random8();
            audio_attenuation[i]=random8()&31;audio_pitch[i]=(u16)random8()*5;
            audio_pulse_period[i]=8+(u16)random8()*7;audio_triangle_period[i]=2+(u16)random8()*7;
            if((i&15)==3 || (i&15)==7 || (i&15)>=12){audio_gate[i]=0;audio_envelope[i]=0;audio_envelope_phase[i]=4;}
        }
        for(i=0;i<16;i++)audio_owner[i]=random8()&1;
        for(i=0;i<8;i++){audio_psg_pulse_period[i]=8+(u16)random8()*7;audio_psg_triangle_period[i]=2+(u16)random8()*7;}
        for(i=0;i<4;i++){
            audio_pcm_ticks[i]=random8()&7;audio_pcm_generation[i]=test+1;
            audio_dmc_address[i]=(u8)i*16;audio_dmc_length[i]=3;audio_dmc_rate[i]=9;
        }
        audio_sfx_phase=test&1;audio_round_robin=random8()&7;
        save(&before);memcpy(apu_before,(void*)0x4000,24);
        start=cycles();audio_render_reference();cost=cycles()-start;reference_total+=cost;
        save(&expected);memcpy(apu_expected,(void*)0x4000,24);
        restore(&before);memcpy((void*)0x4000,apu_before,24);
        start=cycles();audio_render_tick();cost=cycles()-start;fast_total+=cost;if(cost>fast_max)fast_max=cost;
        save(&actual);
        if(memcmp(&actual,&expected,sizeof(actual))){
            for(j=0;j<sizeof(actual);j++)if(((u8*)&actual)[j]!=((u8*)&expected)[j]){
                printf("state mismatch case%u byte%u actual%u expected%u\n",test,j,((u8*)&actual)[j],((u8*)&expected)[j]);
                if(j<32)printf("before level%u phase%u gate%u attack%u decay%u sustain%u counter%u\n",before.envelope[j],before.phase[j],audio_gate[j],audio_attack_ticks[j],audio_decay_ticks[j],audio_sustain[j],before.counter[j]);
                return 1;
            }
        }
        if(memcmp((void*)0x4000,apu_expected,24)){
            for(j=0;j<24;j++)if(((u8*)0x4000)[j]!=apu_expected[j]){
                printf("APU mismatch case%u register%u actual%u expected%u\n",test,j,((u8*)0x4000)[j],apu_expected[j]);return 2;
            }
        }
    }
    printf("PASS 512 %lu %lu %lu\n",fast_total,reference_total,fast_max);
    return 0;
}
'''


def verify(root,output):
    root=Path(root).resolve();output=Path(output).resolve()
    if output.exists() or any((p/'.git').exists() for p in (output,*output.parents)):
        raise ValueError('choose a fresh output outside Git')
    output.mkdir(parents=True)
    sources=Path(__file__).resolve().parents[1]/'src/fdisbull/game_sources'
    c=sources/'miniplanets_audio_nes.c';assembly=sources/'miniplanets_audio_fast.s'
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (c,assembly)}
    config=(root/'cfg/sim6502.cfg').read_text().replace('start = $0200, size = $FFC0 - $0200 - __STACKSIZE__','start = $8000, size = $FFC0 - $8000 - __STACKSIZE__')
    config=config.replace('    HEADER:','    RAM: file = "", start = $0200, size = $3D00;\n    HEADER:')
    config=config.replace('    BSS:      load = MAIN','    AUDIOFAST: load = MAIN, type = ro;\n    BSS:      load = RAM')
    (output/'sim.cfg').write_text(config);(output/'harness.c').write_text(HARNESS)
    command=[str(root/'bin/cl65'),'-t','sim6502','-Oirs','--static-locals','-DFDISBULL_AUDIO_HOST','-C',str(output/'sim.cfg'),'-o',str(output/'check'),str(c),str(assembly),str(output/'harness.c')]
    # cc65 places intermediates beside inputs unless copied first.
    (output/c.name).write_bytes(c.read_bytes());(output/assembly.name).write_bytes(assembly.read_bytes())
    command[-3:]=[str(output/c.name),str(output/assembly.name),str(output/'harness.c')]
    build=subprocess.run(command,capture_output=True,text=True,timeout=60)
    (output/'build.txt').write_text(build.stdout+build.stderr)
    if build.returncode:raise RuntimeError(build.stderr[-3000:])
    run=subprocess.run([str(root/'bin/sim65'),'-c',str(output/'check')],capture_output=True,text=True,timeout=60)
    (output/'run.txt').write_text(run.stdout+run.stderr)
    if run.returncode:raise RuntimeError(run.stdout+run.stderr)
    line=next(row for row in run.stdout.splitlines() if row.startswith('PASS '));_,count,total,reference,maximum=line.split()
    receipt={'format':'fdisbull-audio-6502-check-1','cases':int(count),'psg_clock_latch_cases':2,'pcm_preemption_cases':9,'restart_cases':3,'source_hashes':hashes,
             'fast_mean_cycles':int(total)/int(count),'reference_mean_cycles':int(reference)/int(count),
             'fast_max_cycles':int(maximum),'passed':True,
             'claim':'actual 6502 instructions versus portable C on authored voice/envelope/PCM state; excludes bank/IRQ overhead and APU waveform parity'}
    if any(hashlib.sha256(p.read_bytes()).hexdigest()!=hashes[p.name] for p in (c,assembly)):raise RuntimeError('audio source changed during test')
    (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--cc65-root',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();print(json.dumps(verify(args.cc65_root,args.output),indent=2))
