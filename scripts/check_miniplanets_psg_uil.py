#!/usr/bin/env python3
"""Compare PSG GameIL with the production C oracle and 6502 assembly path."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from fdisbull.game_il import GameMachine, canonical
from fdisbull.psg_il import lift_psg


HARNESS = r'''#include <stdio.h>
#include <string.h>
#include <sim65.h>
typedef unsigned char u8; typedef unsigned int u16;
extern u8 audio_envelope_phase[32],audio_envelope[32],audio_sfx_phase;
extern u8 audio_psg_level[32],audio_psg_tl[32],audio_psg_ar[32],audio_psg_sl[32];
extern u8 audio_psg_dr[32],audio_psg_sr[32],audio_psg_rr[32];
extern u16 audio_pulse_period[32],audio_triangle_period[32];
extern u16 audio_psg_pulse_period[8],audio_psg_triangle_period[8];
extern u8 audio_gate[32],audio_pan[32],audio_duty[32],audio_attack_ticks[32];
extern u8 audio_decay_ticks[32],audio_sustain[32],audio_release_ticks[32],audio_release_peak[32];
extern u16 audio_envelope_counter[32],audio_pitch[32];
extern u8 audio_attenuation[32],audio_owner[16],audio_current_volume[12],audio_round_robin;
extern u16 audio_arpeggio_count,audio_pcm_ticks[4],audio_pcm_generation[4];
extern u8 audio_dmc_address[4],audio_dmc_length[4],audio_dmc_rate[4];
extern u16 audio_dmc_delivered[4],audio_dmc_generation,audio_pcm_dropped,audio_pcm_preempted;
extern u8 audio_dmc_source,audio_dmc_playing,audio_dmc_slot,audio_dmc_channel;
void audio_render_reference(void); void audio_render_tick(void);
u8 audio_stream_byte(u8 t,u16 p){return 255;} u16 audio_stream_size(u8 t){return 1;}
u8 audio_instrument_byte(u8 i,u8 f){return 0;} u16 audio_period(u16 p,u8 o){return 100;}
void audio_hw_write(u16 a,u8 v){*(volatile u8*)a=v;}
static u8 expected_phase[8],expected_level[8],expected_envelope[8];
static u8 expected_volume[4];
static u16 expected_pulse[8],expected_triangle[8];
static u8 phase_value(unsigned char x){static const u8 p[7]={0,1,2,3,4,5,255};return p[x%7];}
static void init_case(u16 test){u8 v;u16 i;memset(audio_envelope_phase,0,32);memset(audio_envelope,0,32);
 memset(audio_psg_level,0,32);memset(audio_psg_tl,0,32);memset(audio_psg_ar,0,32);
 memset(audio_psg_sl,0,32);memset(audio_psg_dr,0,32);memset(audio_psg_sr,0,32);memset(audio_psg_rr,0,32);
 memset(audio_pulse_period,0,64);memset(audio_triangle_period,0,64);
 memset(audio_psg_pulse_period,0x5a,16);memset(audio_psg_triangle_period,0xa5,16);
 memset(audio_gate,0,32);memset(audio_pan,0,32);memset(audio_duty,0,32);
 memset(audio_attack_ticks,0,32);memset(audio_decay_ticks,0,32);memset(audio_sustain,0,32);
 memset(audio_release_ticks,0,32);memset(audio_release_peak,0,32);memset(audio_envelope_counter,0,64);
 memset(audio_pitch,0,64);memset(audio_attenuation,0,32);memset(audio_owner,0,16);
 memset(audio_current_volume,0,12);audio_round_robin=0;audio_arpeggio_count=0;
 memset(audio_pcm_ticks,0,8);memset(audio_pcm_generation,0,8);memset(audio_dmc_address,0,4);
 memset(audio_dmc_length,0,4);memset(audio_dmc_rate,0,4);memset(audio_dmc_delivered,0,8);
 audio_dmc_generation=audio_pcm_dropped=audio_pcm_preempted=0;audio_dmc_source=255;
 audio_dmc_playing=audio_dmc_slot=audio_dmc_channel=0;audio_sfx_phase=(u8)(test&1);
 for(v=0;v<8;v++){u8 index=(u8)((v<4?8:24)+(v&3));u8 channel=(u8)(8+(v&3));
  audio_envelope_phase[index]=phase_value((u8)(test+v*3));
  audio_psg_level[index]=(u8)(test*37+v*53);audio_psg_tl[index]=(u8)(test*11+v*7);
  audio_psg_ar[index]=(u8)(test*29+v*19);audio_psg_sl[index]=(u8)(test*5+v*17);
  audio_psg_dr[index]=(u8)(test*13+v*23);audio_psg_sr[index]=(u8)(test*31+v*3);
  audio_psg_rr[index]=(u8)(test*7+v*41);audio_pulse_period[index]=(u16)(test*293+v*257);
  audio_triangle_period[index]=(u16)(test*557+v*911);
  audio_owner[channel]=(u8)((test+v)%3);audio_pan[index]=(u8)((test+v*3)&255);
  audio_attenuation[index]=(u8)(test*13+index*11);}
 for(i=0;i<24;i++)((u8*)0x4000)[i]=0;}
int main(void){u16 test,v;for(test=0;test<128;test++){u8 index;
 init_case(test);audio_render_reference();
 for(v=0;v<8;v++){index=(u8)((v<4?8:24)+(v&3));expected_phase[v]=audio_envelope_phase[index];
  expected_level[v]=audio_psg_level[index];expected_envelope[v]=audio_envelope[index];
  expected_pulse[v]=audio_psg_pulse_period[v];expected_triangle[v]=audio_psg_triangle_period[v];}
 for(v=0;v<4;v++)expected_volume[v]=audio_current_volume[8+v];
 init_case(test);audio_render_tick();
 printf("ROW %u",test);
 for(v=0;v<8;v++){index=(u8)((v<4?8:24)+(v&3));
  if(audio_envelope_phase[index]!=expected_phase[v]||audio_psg_level[index]!=expected_level[v]||
     audio_envelope[index]!=expected_envelope[v]||audio_psg_pulse_period[v]!=expected_pulse[v]||
     audio_psg_triangle_period[v]!=expected_triangle[v]||
     audio_current_volume[8+(v&3)]!=expected_volume[v&3]){printf(" MISMATCH %u %u",v,index);return 3;}
  printf(" %u %u %u %u %u",audio_envelope_phase[index],audio_psg_level[index],
         audio_envelope[index],audio_psg_pulse_period[v],audio_psg_triangle_period[v]);
  if(v<4)printf(" %u",audio_current_volume[8+v]);}
 printf("\n");}puts("PASS 128 C_AND_6502");return 0;}
'''


def _state(test: int) -> dict:
    phase_values = (0, 1, 2, 3, 4, 5, 255)
    state = GameMachine(lift_psg()).snapshot()
    state['audio_sfx_phase'] = test & 1
    state['audio_psg_pulse_period'] = [0x5a5a] * 8
    state['audio_psg_triangle_period'] = [0xa5a5] * 8
    for voice in range(8):
        index = (8 if voice < 4 else 24) + (voice & 3)
        state['audio_envelope_phase'][index] = phase_values[(test + voice * 3) % 7]
        state['audio_psg_level'][index] = (test * 37 + voice * 53) & 255
        state['audio_psg_tl'][index] = (test * 11 + voice * 7) & 255
        state['audio_psg_ar'][index] = (test * 29 + voice * 19) & 255
        state['audio_psg_sl'][index] = (test * 5 + voice * 17) & 255
        state['audio_psg_dr'][index] = (test * 13 + voice * 23) & 255
        state['audio_psg_sr'][index] = (test * 31 + voice * 3) & 255
        state['audio_psg_rr'][index] = (test * 7 + voice * 41) & 255
        state['audio_pulse_period'][index] = (test * 293 + voice * 257) & 65535
        state['audio_triangle_period'][index] = (test * 557 + voice * 911) & 65535
        channel = 8 + (voice & 3)
        state['audio_owner'][channel] = (test + voice) % 3
        state['audio_pan'][index] = (test + voice * 3) & 255
        state['audio_attenuation'][index] = (test * 13 + index * 11) & 255
    return state


def verify(cc65_root: str | Path, output: str | Path) -> dict:
    root, output = Path(cc65_root).resolve(), Path(output).resolve()
    repo = Path(__file__).resolve().parents[1]
    sources = repo / 'src/fdisbull/game_sources'
    source_paths = (sources / 'miniplanets_audio_nes.c',
                    sources / 'miniplanets_audio_fast.s',
                    sources / 'miniplanets_psg_uil.c')
    if output.exists() or any((path / '.git').exists() for path in (output, *output.parents)):
        raise ValueError('choose a fresh output outside Git')
    if not (root / 'bin/cl65').is_file() or not (root / 'bin/sim65').is_file():
        raise ValueError('prepared cc65/sim65 toolchain required')
    output.mkdir(parents=True)
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths}
    cfg = (root / 'cfg/sim6502.cfg').read_text()
    cfg = cfg.replace('start = $0200, size = $FFC0 - $0200 - __STACKSIZE__',
                      'start = $8000, size = $FFC0 - $8000 - __STACKSIZE__')
    cfg = cfg.replace('    HEADER:', '    RAM: file = "", start = $0200, size = $3D00;\n    HEADER:')
    cfg = cfg.replace('    BSS:      load = MAIN', '    AUDIOFAST: load = MAIN, type = ro;\n    BSS:      load = RAM')
    (output / 'sim.cfg').write_text(cfg)
    (output / 'harness.c').write_text(HARNESS)
    local_c = output / source_paths[0].name
    local_s = output / source_paths[1].name
    local_c.write_bytes(source_paths[0].read_bytes())
    local_s.write_bytes(source_paths[1].read_bytes())
    build = subprocess.run([str(root / 'bin/cl65'), '-t', 'sim6502', '-Oirs',
        '--static-locals', '-DFDISBULL_AUDIO_HOST', '-C', str(output / 'sim.cfg'),
        '-o', str(output / 'check'), str(local_c), str(local_s), str(output / 'harness.c')],
        capture_output=True, text=True, timeout=60)
    (output / 'build.txt').write_text(build.stdout + build.stderr)
    if build.returncode:
        raise RuntimeError(build.stderr[-3000:])
    run = subprocess.run([str(root / 'bin/sim65'), '-c', str(output / 'check')],
                         capture_output=True, text=True, timeout=60)
    (output / 'run.txt').write_text(run.stdout + run.stderr)
    if run.returncode or 'PASS 128 C_AND_6502' not in run.stdout:
        raise RuntimeError(run.stdout + run.stderr)
    program = lift_psg()
    program_sha256 = hashlib.sha256(canonical(program)).hexdigest()
    machine = GameMachine(program)
    compared = 0
    for line in run.stdout.splitlines():
        if not line.startswith('ROW '):
            continue
        fields = list(map(int, line.split()[1:]))
        test = fields[0]
        machine.set_state(_state(test))
        machine.call('audio_render_psg')
        machine.call('audio_render_psg_volume')
        after = machine.snapshot()
        expected = []
        for voice in range(8):
            index = (8 if voice < 4 else 24) + (voice & 3)
            expected.extend((after['audio_envelope_phase'][index],
                             after['audio_psg_level'][index], after['audio_envelope'][index],
                             after['audio_psg_pulse_period'][voice],
                             after['audio_psg_triangle_period'][voice]))
            if voice < 4:
                expected.append(after['audio_current_volume'][8 + voice])
        if fields[1:] != expected:
            raise AssertionError(f'GameIL and native PSG output diverged in case {test}')
        compared += 1
    if compared != 128:
        raise AssertionError(f'expected 128 native PSG cases, observed {compared}')
    if any(hashlib.sha256(path.read_bytes()).hexdigest() != hashes[path.name]
           for path in source_paths):
        raise RuntimeError('production audio source changed during checker run')
    receipt = {'format': 'fdisbull-miniplanets-psg-game-il-native-1',
        'passed': True, 'cases': compared,
        'game_il_program_sha256': program_sha256,
        'comparisons': ['GameIL interpreter', 'portable production C reference',
                        'production 6502 assembly'],
        'coverage': 'phase gate, eight PSG voices, period copy, attack/decay/sustain/release/default phases, 8-bit carry/borrow and zero release; PSG owner/pan/attenuation volume selection; deterministic 128-state matrix',
        'source_sha256': hashes,
        'claim': 'the isolated PSG service subroutine matches the bounded native C and 6502 assembly cases; not the full audio driver or waveform parity'}
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc65-root', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.cc65_root, args.output), indent=2))
