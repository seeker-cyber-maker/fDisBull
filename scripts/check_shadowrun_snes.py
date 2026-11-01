#!/usr/bin/env python3
"""Held-out unpatched SNES source vs UIL vs native comparison.

Private original snapshots are expected outputs only; initial capture supplies the
model's explicitly immutable collision region. Unsupported frames are DNFs and
must roll back the full native context. The script publishes hashes and semantic
field differences, never ROM, WRAM, or emulator-state bytes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from fdisbull.game_il import canonical
from fdisbull.shadowrun_snes_field import machine_from_capture, SOURCE
from fdisbull.udc_macos import build_macos
from check_shadowrun_macos import Native

FIXTURE_SHA='81f80aa7d3277f40ebc06e1abe9ee74c1f4612bc01a8363aaa5c2672c2a82130'
BASE_CORE_SHA='89fe8f7602428dbe532a19f098075182619c576383f177e641b19eb1f5fa19e8'
SOURCE_WORDS={'shadowrun_snes_player_x':0x0e86,'shadowrun_snes_player_y':0x0ede,
              'shadowrun_snes_player_z':0x0f36,'shadowrun_snes_velocity_x':0x0d7e,
              'shadowrun_snes_velocity_y':0x0dd6,'shadowrun_snes_flags':0x14b6}
PAD={'UP':1,'DOWN':2,'LEFT':4,'RIGHT':8}

def sha(data): return hashlib.sha256(data).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('rom','original','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();original=a.original.resolve();out=a.output.resolve()
    if out.exists() or any((q/'.git').exists() for q in (out,*out.parents)):
        raise ValueError('output must be a fresh private directory outside Git')
    receipt_bytes=(original/'receipt.json').read_bytes()
    if sha(receipt_bytes)!=FIXTURE_SHA:raise ValueError('unexpected held-out original receipt')
    receipt=json.loads(receipt_bytes);rom=a.rom.read_bytes()
    if sha(rom)!=receipt['rom_sha256'] or receipt['core_sha256']!=BASE_CORE_SHA:raise ValueError('source identity mismatch')
    captured={x['frame']:x for x in receipt['frame_ram']}
    if 2999 not in captured or not all(f in captured for f in range(3000,3051)):
        raise ValueError('held-out source snapshots incomplete')
    def source_frame(f):
        item=captured[f];data=(original/item['file']).read_bytes()
        if len(data)!=131072 or sha(data)!=item['sha256']:raise ValueError('original RAM hash mismatch')
        return data
    initial=source_frame(2999);save=(original/'save_ram.bin').read_bytes()
    if sha(save)!=receipt['save_ram_sha256']:raise ValueError('save identity mismatch')
    source_hash=sha(SOURCE.read_bytes());machine=machine_from_capture(rom,initial,save)
    program_hash=sha(canonical(machine.program));seed=machine.snapshot()
    out.mkdir(mode=0o700,parents=True)
    build=build_macos(machine.program,seed,out/'native',entry='shadowrun_snes_frame',immutable_regions={1:initial})
    lib=out/'native'/'libfdisbull_native.dylib';native=Native(lib,a.rom.resolve())
    summary={'format':'shadowrun-snes-heldout-comparison-1','source_receipt_sha256':FIXTURE_SHA,
       'rom_sha256':sha(rom),'baseline_core_sha256':BASE_CORE_SHA,'capture_sha256':sha(initial),
       'save_sha256':sha(save),'program_sha256':program_hash,'authoring_sha256':source_hash,
       'native_build':build,'logical_steps':0,'source_compared':0,'native_state_elements':0,
       'frame_phase':'source frames are zero-based and sampled after retro_run',
       'collision':'immutable captured WRAM; live changes are not asserted absent',
       'result':'running','first_divergence':None}
    try:
        summary['native_state_elements']+=native.compare(seed,'seed')
        for f in range(3000,3061):
            pad=0
            for entry in receipt['inputs']:
                if entry['start']<=f<entry['end']:
                    for button in entry['buttons']:
                        if button not in PAD:raise ValueError('held-out route contains unsupported input')
                        pad|=PAD[button]
            before=machine.snapshot();machine.call('shadowrun_snes_frame',pad);state=machine.snapshot()
            rc=native.step(pad)
            if state['shadowrun_snes_frame_status']==2:
                if rc!=1:raise AssertionError(('unsupported native result',f,rc))
                machine.set_state(before)
                summary['native_state_elements']+=native.compare(before,('refused',f))
                if native.step(pad)!=1:raise AssertionError(('refusal repeat',f))
                summary['native_state_elements']+=native.compare(before,('refused-repeat',f))
                summary.update(result='unsupported',first_divergence={'frame':f,'pad':pad,'kind':'source branch not modeled'},rollback_verified=True)
                break
            if rc!=0:raise AssertionError(('native failed accepted frame',f,rc))
            summary['native_state_elements']+=native.compare(state,('accepted',f));summary['logical_steps']+=1
            if f in captured:
                data=source_frame(f);differences={}
                for name,off in SOURCE_WORDS.items():
                    actual=int.from_bytes(data[off:off+2],'little')
                    if state[name]!=actual:differences[name]={'model':state[name],'original':actual}
                summary['source_compared']+=1
                if differences:
                    summary.update(result='diverged',first_divergence={'frame':f,'pad':pad,'fields':differences})
                    break
        else:summary['result']='completed'
        # Chords are explicitly outside the recovered model domain.  This is
        # a native rollback control, not an original-source behavior claim.
        before=machine.snapshot();machine.call('shadowrun_snes_frame',3)
        if machine.snapshot()['shadowrun_snes_frame_status']!=2:raise AssertionError('chord did not refuse')
        machine.set_state(before)
        if native.step(3)!=1:raise AssertionError('native chord did not refuse')
        summary['native_state_elements']+=native.compare(before,'chord-rollback')
        if native.step(3)!=1:raise AssertionError('native chord repeat did not refuse')
        summary['native_state_elements']+=native.compare(before,'chord-repeat-rollback')
        summary['unsupported_chord_rollback']=True
    finally:native.close()
    if sha(SOURCE.read_bytes())!=source_hash:raise ValueError('model source changed during check')
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:summary[k] for k in ('result','logical_steps','source_compared','first_divergence')},indent=2))
    if summary['result']=='diverged':raise SystemExit(1)

if __name__=='__main__':main()
