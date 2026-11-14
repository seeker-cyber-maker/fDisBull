#!/usr/bin/env python3
"""Check composed frame model on withheld patch-free source frames and native lowering."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from fdisbull.game_il import canonical
from fdisbull.shadowrun_snes_field import ROM_SHA256, SNAPSHOT_SHA256, SAVE_SHA256, SOURCE as FIELD_SOURCE
from fdisbull.shadowrun_snes_live import ACTOR_ARRAYS, machine_from_live_capture, SOURCE
from fdisbull.udc_macos import build_macos
from check_shadowrun_macos import Native
from check_shadowrun_snes_live_heldout import CORE_SHA, RECEIPT_SHA, OUTPUTS, words, sha

FIELDS = {'shadowrun_snes_player_x':0xe86, 'shadowrun_snes_player_y':0xede,
          'shadowrun_snes_player_z':0xf36, 'shadowrun_snes_velocity_x':0xd7e,
          'shadowrun_snes_velocity_y':0xdd6, 'shadowrun_snes_flags':0x14b6}
PAD = {'UP':1, 'DOWN':2, 'LEFT':4, 'RIGHT':8}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('rom','original','output'): p.add_argument('--'+k,required=True,type=Path)
    p.add_argument('--long', action='store_true', help='Use sparse extended held-out sequence')
    a=p.parse_args(); out=a.output.resolve()
    if out.exists() or any((x/'.git').exists() for x in (out,*out.parents)):
        raise ValueError('output must be a fresh private directory outside Git')
    receipt_raw=(a.original/'receipt.json').read_bytes()
    receipt_sha = ('a9256b85f2658b6d17cc01de27b4760bb7bc4c3b0028990a1ae4388812e58cb4'
                   if a.long else RECEIPT_SHA)
    if sha(receipt_raw)!=receipt_sha: raise ValueError('unexpected held-out receipt')
    r=json.loads(receipt_raw); rom=a.rom.read_bytes(); save=(a.original/'save_ram.bin').read_bytes()
    if (r['core_sha256']!=CORE_SHA or r['rom_sha256']!=ROM_SHA256 or sha(rom)!=ROM_SHA256 or
        r['system']!='snes' or r['patches'] or sha(save)!=SAVE_SHA256 or
        r['save_ram_sha256']!=SAVE_SHA256 or r['frame_images_phase']!='after retro_run; frame is zero-based'):
        raise ValueError('source identity, patch, or frame phase mismatch')
    entries={x['frame']:x for x in r['frame_ram']}
    frames = ({2999,3190} | set(range(3000,3184,3))) if a.long else set(range(2999,3061))
    if len(entries)!=len(r['frame_ram']) or set(entries)!=frames:
        raise ValueError('held-out frame set incomplete')
    def source(frame):
        item=entries[frame]; b=(a.original/item['file']).read_bytes()
        if len(b)!=131072 or sha(b)!=item['sha256']: raise ValueError('source frame identity mismatch')
        return b
    initial=source(2999)
    if sha(initial)!=SNAPSHOT_SHA256: raise ValueError('capture mismatch')
    watched=[SOURCE,FIELD_SOURCE,ROOT/'src/fdisbull/shadowrun_snes_live.py',
             ROOT/'src/fdisbull/game_sources/shadowrun_snes_flags.c']
    hashes={str(x):sha(x.read_bytes()) for x in watched}
    machine,regions=machine_from_live_capture(rom,initial,save); seed=machine.snapshot()
    out.mkdir(mode=0o700,parents=True)
    build=build_macos(machine.program,seed,out/'native',entry='shadowrun_snes_frame',immutable_regions={1:regions[1]})
    native=Native(out/'native/libfdisbull_native.dylib',a.rom.resolve())
    report={'format':'shadowrun-snes-frame-heldout-1','result':'running',
            'source_receipt_sha256':receipt_sha,'rom_sha256':sha(rom),'core_sha256':CORE_SHA,
            'seed_sha256':sha(initial),'save_sha256':sha(save),'source_hashes':hashes,
            'program_sha256':sha(canonical(machine.program)),'native_build':build,
            'frame_phase':'post retro_run, zero-based','source_compared':0,'logical_steps':0,'native_elements':0,
            'scope':'prepared scene; player and collision arrays, not autonomous NPC or scripts',
            'first_divergence':None}
    try:
        report['native_elements']+=native.compare(seed,'seed')
        for frame in range(3000,3191 if a.long else 3061):
            pad=0
            for item in r['inputs']:
                if item['start']<=frame<item['end']:
                    for button in item['buttons']:
                        if button not in PAD: raise ValueError('unsupported held-out button')
                        pad |= PAD[button]
            before=machine.snapshot();machine.call('shadowrun_snes_frame',pad);s=machine.snapshot()
            rc=native.step(pad)
            if s['shadowrun_snes_frame_status']==2:
                if rc!=1: raise AssertionError(('native refusal',frame,rc))
                machine.set_state(before)
                report['native_elements']+=native.compare(before,('refused',frame))
                report.update(result='unsupported',first_divergence={'frame':frame,'kind':'model refused'})
                break
            if rc!=0: raise AssertionError(('native return',frame,rc))
            report['native_elements']+=native.compare(s,frame)
            report['logical_steps']+=1
            if frame not in entries:
                continue
            b=source(frame); mismatch=None
            for name,offset in FIELDS.items():
                expected=words(b,offset,1)[0]
                if s[name]!=expected:
                    mismatch={'frame':frame,'field':name,'model':s[name],'source':expected};break
            if mismatch is None:
                for name, offset in ACTOR_ARRAYS.items():
                    for i, (got, want) in enumerate(zip(s[name], words(b,offset,44), strict=True)):
                        if got!=want:
                            mismatch={'frame':frame,'field':name,'index':i,'model':got,'source':want};break
                    if mismatch: break
            if mismatch is None:
                count_word=words(b,0x14cc,1)[0]
                if count_word & 1 or count_word//2+1>44:
                    raise ValueError('unsupported source actor order')
                count=count_word//2+1
                if s['live_order_count']!=count or s['live_order'][:count]!=words(b,0x14ce,count):
                    mismatch={'frame':frame,'field':'live_order','kind':'actor order differs'}
            if mismatch is None:
                for name,(offset,count) in OUTPUTS.items():
                    expected=list(b[offset:offset+count]) if name=='live_owners' else words(b,offset,count)
                    for i,(got,want) in enumerate(zip(s[name],expected,strict=True)):
                        if got!=want:
                            mismatch={'frame':frame,'field':name,'index':i,'model':got,'source':want};break
                    if mismatch:break
            if mismatch:
                report.update(result='diverged',first_divergence=mismatch);break
            report['source_compared']+=1
        else: report['result']='passed'
    finally: native.close()
    if any(sha(Path(path).read_bytes())!=digest for path,digest in hashes.items()):
        raise ValueError('model changed during comparison')
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('result','logical_steps','source_compared','native_elements','first_divergence')},indent=2))
    if report['result']!='passed':raise SystemExit(1)
if __name__=='__main__':main()
