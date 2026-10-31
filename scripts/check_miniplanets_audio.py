#!/usr/bin/env python3
"""Compare all recovered audio streams with the portable native C runtime.

This checks stream timing/commands, not original chip waveform equivalence or
6502 speed. Retained stream bytes, generated C and raw traces stay outside Git.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from fdisbull.miniplanets_audio import SonaEngine, encode_sona, recover_audio


def sha(data):
    return hashlib.sha256(data).hexdigest()


def host_bindings(audio):
    rows = []
    for track in audio['tracks']:
        values = ','.join(str(value) for value in encode_sona(track['event_program']))
        rows.append(f"static const unsigned char stream_{track['track']}[] = {{{values}}};")
    rows.append('static const unsigned char *streams[32] = {' + ','.join(f'stream_{i}' for i in range(32)) + '};')
    rows.append('static const unsigned int sizes[32] = {' + ','.join(str(t['source_length']) for t in audio['tracks']) + '};')
    rows.append('static const unsigned char metadata[28][17] = {' + ','.join('{' + ','.join(map(str, i['nes_meta'])) + '}' for i in audio['instruments']) + '};')
    for name in ('pulse_periods','triangle_periods','psg_pulse_periods','psg_triangle_periods'):
        rows.append(f'static const unsigned int {name}[1536] = {{' + ','.join(map(str, audio[name])) + '};')
    rows.append('static const unsigned int *periods[4] = {pulse_periods,triangle_periods,psg_pulse_periods,psg_triangle_periods};')
    rows.append('''unsigned long host_writes, host_pcm_starts, host_tone_volumes;
unsigned char audio_stream_byte(unsigned char t,unsigned int p){return streams[t][p];}
unsigned int audio_stream_size(unsigned char t){return sizes[t];}
unsigned char audio_instrument_byte(unsigned char i,unsigned char f){return metadata[i][f];}
unsigned int audio_period(unsigned int p,unsigned char o){return periods[o][p];}
void audio_hw_write(unsigned int a,unsigned char v){host_writes++;if(a==0x4015 && (v&16))host_pcm_starts++;if((a==0x4000 || a==0x4004 || a==0x400c) && (v&15))host_tone_volumes++;}
''')
    return '\n'.join(rows)


def verify(rom_path, output, cc='cc', interrupts=20000):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('choose a fresh output directory')
    if any((ancestor / '.git').exists() for ancestor in (output, *output.parents)):
        raise ValueError('private audio output must be outside Git')
    rom_path = Path(rom_path).resolve()
    original = rom_path.read_bytes()
    audio = recover_audio(original)
    runtime = Path(__file__).resolve().parents[1] / 'src/fdisbull/game_sources/miniplanets_audio_nes.c'
    runtime_hash = sha(runtime.read_bytes())
    output.mkdir(parents=True)
    (output / 'audio-uil.json').write_text(json.dumps(audio, separators=(',', ':')) + '\n')
    bindings = output / 'audio-bindings.c'
    bindings.write_text(host_bindings(audio))
    library = output / ('audio-runtime.dylib' if sys.platform == 'darwin' else 'audio-runtime.so')
    command = [cc, '-std=c89', '-Wall', '-Wextra', '-Werror', '-O2', '-shared', '-fPIC', '-DFDISBULL_AUDIO_HOST', str(runtime), str(bindings), '-o', str(library)]
    build = subprocess.run(command, capture_output=True, text=True)
    (output / 'build.txt').write_text(build.stdout + build.stderr)
    if build.returncode:
        raise RuntimeError(f'audio runtime build failed: {build.stderr[-3000:]}')
    native = ctypes.CDLL(str(library))
    native.audio_request.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte]
    native.audio_busy.restype = ctypes.c_ubyte
    fields = ('audio_tick_count','audio_command_count','audio_event_crc','audio_note_count')
    values = [ctypes.c_uint.in_dll(native, name) for name in fields]
    active = (ctypes.c_ubyte * 2).in_dll(native, 'audio_stream_active')
    error = ctypes.c_ubyte.in_dll(native, 'audio_error')
    metrics = [ctypes.c_ulong.in_dll(native, name) for name in ('host_writes','host_pcm_starts','host_tone_volumes')]
    losses = [ctypes.c_uint.in_dll(native, name) for name in ('audio_pcm_dropped','audio_pcm_preempted')]
    cases = [{'name': t['name'], 'kind': 1 if t['kind']=='bgm' else 2,
              'id': t['track'] + 1 if t['kind']=='bgm' else t['track'] - 12,
              'interrupts': interrupts if t['kind']=='bgm' else 512} for t in audio['tracks']]
    cases.append({'name':'priority-and-stop', 'kind':1, 'id':1, 'interrupts':1024,
                  'requests':{100:(2,1),101:(2,1),105:(2,19),106:(2,3),200:(1,5),250:(3,0),300:(2,18),305:(2,1)}})
    receipts = []
    for case in cases:
        engine = SonaEngine(audio)
        for metric in metrics:
            metric.value = 0
        native.audio_init()
        engine.request(case['kind'],case['id'])
        native.audio_request(case['kind'],case['id'])
        trace = []
        for interrupt in range(1,case['interrupts'] + 1):
            request = case.get('requests',{}).get(interrupt)
            if request:
                engine.request(*request)
                native.audio_request(*request)
            engine.nes_tick()
            native.audio_tick()
            expected = [engine.clock,engine.command_count,engine.event_crc,engine.note_count,
                        int(engine.streams[0] is not None),int(engine.streams[1] is not None),int(engine.busy),0]
            actual = [value.value & 65535 for value in values] + list(active) + [native.audio_busy(),error.value]
            if actual != expected:
                raise AssertionError(f"{case['name']} interrupt {interrupt}: C {actual} != event engine {expected}")
            trace.append(actual)
        raw = (json.dumps(trace,separators=(',', ':')) + '\n').encode()
        (output / (case['name'] + '-trace.json')).write_bytes(raw)
        coverage = {event['offset'] for event in engine.events if event['track'] == (case['id']-1 if case['kind']==1 else case['id']+12)}
        track_index = case['id'] - 1 if case['kind']==1 else case['id'] + 12
        complete_coverage = len(coverage) == len(audio['tracks'][track_index]['event_program']['events'])
        if case['name'] != 'priority-and-stop' and not complete_coverage:
            raise AssertionError(f"{case['name']}: did not execute every source command")
        if not metrics[1].value and not metrics[2].value:
            raise AssertionError(f"{case['name']}: runtime produced no active APU voices")
        receipts.append({'name':case['name'],'interrupts':case['interrupts'],'source_ticks':engine.clock,
                         'commands':engine.command_count,'notes':engine.note_count,
                         'complete_source_command_coverage':complete_coverage,
                         'trace_sha256':sha(raw),'apu_writes':metrics[0].value,
                         'pcm_starts':metrics[1].value,'tonal_volume_writes':metrics[2].value,
                         'pcm_notes_dropped':losses[0].value,'pcm_notes_preempted':losses[1].value})
    if sha(rom_path.read_bytes()) != sha(original) or sha(runtime.read_bytes()) != runtime_hash:
        raise RuntimeError('ROM or runtime changed while checking audio')
    receipt = {'format':'fdisbull-audio-check-1','source_sha256':sha(original),
               'runtime_sha256':runtime_hash,'tracks':32,'instruments':28,
               'decoded_commands':sum(len(t['event_program']['events']) for t in audio['tracks']),
               'dpcm_used_bytes':audio['dpcm_used_bytes'],'comparisons':sum(c['interrupts'] for c in cases),
               'cases':receipts,'passed':True,
               'claim':'portable C versus independent decoded-event engine; not a native 6502 or waveform parity result'}
    (output / 'receipt.json').write_text(json.dumps(receipt,indent=2) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--cc',default='cc')
    args = parser.parse_args()
    receipt = verify(args.rom,args.output,args.cc)
    print(json.dumps({key:value for key,value in receipt.items() if key != 'cases'},indent=2))


if __name__ == '__main__':
    main()
