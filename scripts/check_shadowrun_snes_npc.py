#!/usr/bin/env python3
"""Check source-seeded NPC kinematics on independent original frames and native output.

Only the frame-2000 state seeds the projection. Rendering flags, script dispatch,
collision and animation are outside this comparison.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from fdisbull.game_il import canonical
from fdisbull.shadowrun_snes_field import ROM_SHA256
from fdisbull.shadowrun_snes_npc import SOURCE,FIELDS,control_from_capture
from fdisbull.udc_macos import build_macos
from check_shadowrun_macos import Native

CORE='89fe8f7602428dbe532a19f098075182619c576383f177e641b19eb1f5fa19e8'
RECEIPT='b703e8f6c9e4a94641eafa73d5dc183f52f70f763c43d60f78a52162aa704628'
CHECK=('npc_timer','npc_control','npc_velocity_x','npc_velocity_y','npc_x','npc_y','npc_z','npc_depth')
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('rom','original','output'):p.add_argument('--'+k,required=True,type=Path)
    a=p.parse_args();out=a.output.resolve()
    if out.exists() or any((x/'.git').exists() for x in (out,*out.parents)):
        raise ValueError('output must be a fresh private directory outside Git')
    raw=(a.original/'receipt.json').read_bytes()
    if sha(raw)!=RECEIPT:raise ValueError('unexpected original receipt')
    r=json.loads(raw);rom=a.rom.read_bytes()
    if (sha(rom)!=ROM_SHA256 or r['rom_sha256']!=ROM_SHA256 or r['core_sha256']!=CORE or
        r['system']!='snes' or r['patches'] or r['frame_images_phase']!='after retro_run; frame is zero-based'):
        raise ValueError('source identity, patches, or frame phase mismatch')
    entries={x['frame']:x for x in r['frame_ram']}
    if len(entries)!=len(r['frame_ram']) or set(entries)!=set(range(2000,2063))|{2999}:
        raise ValueError('source frame set incomplete')
    def source(frame):
        item=entries[frame];b=(a.original/item['file']).read_bytes()
        if len(b)!=131072 or sha(b)!=item['sha256']:raise ValueError('source frame identity mismatch')
        return b
    seed=source(2000); watched=[SOURCE,ROOT/'src/fdisbull/shadowrun_snes_npc.py']
    hashes={str(p):sha(p.read_bytes()) for p in watched}
    out.mkdir(mode=0o700,parents=True)
    report={'format':'shadowrun-snes-npc-heldout-1','result':'running',
      'source_receipt_sha256':RECEIPT,'rom_sha256':sha(rom),'core_sha256':CORE,
      'seed_sha256':sha(seed),'source_hashes':hashes,'frame_phase':'zero-based after retro_run',
      'scope':'frame-2000 source seed; independent noncolliding NPC kinematics only; no later source state input, rendering flags, scripts or animation',
      'slots':{}}
    for slot in (0x44,0x46):
        machine=control_from_capture(rom,seed,slot); before=machine.snapshot()
        build=build_macos(machine.program,before,out/f'native-{slot:02x}',entry='shadowrun_snes_npc_frame')
        native=Native(out/f'native-{slot:02x}'/'libfdisbull_native.dylib',a.rom.resolve())
        row={'program_sha256':sha(canonical(machine.program)),'native_build':build,
             'source_compared':0,'native_elements':0,'result':'running','first_divergence':None,
             'rollback_verified':False}
        try:
            row['native_elements']+=native.compare(before,'seed')
            for frame in range(2001,2063):
                before=machine.snapshot();machine.call('shadowrun_snes_npc_frame',0);state=machine.snapshot()
                rc=native.step(0)
                if state['shadowrun_snes_npc_frame_status']==2:
                    if rc!=1:raise AssertionError(('native refusal',slot,frame,rc))
                    machine.set_state(before)
                    row['native_elements']+=native.compare(before,('refused',frame))
                    if native.step(0)!=1:raise AssertionError(('native refusal repeat',slot,frame))
                    row['native_elements']+=native.compare(before,('refused-repeat',frame))
                    machine.call('shadowrun_snes_npc_frame',0)
                    if machine.snapshot()['shadowrun_snes_npc_frame_status']!=2:
                        raise AssertionError(('model refusal repeat',slot,frame))
                    machine.set_state(before)
                    row.update(result='unsupported',first_divergence={'frame':frame,'kind':'model refused'},rollback_verified=True)
                    break
                if rc!=0:raise AssertionError(('native return',slot,frame,rc))
                row['native_elements']+=native.compare(state,frame)
                b=source(frame)
                for name in CHECK:
                    expected=int.from_bytes(b[FIELDS[name]+slot:FIELDS[name]+slot+2],'little')
                    if state[name]!=expected:
                        row.update(result='diverged',first_divergence={'frame':frame,'field':name,'model':state[name],'source':expected})
                        break
                if row['first_divergence']:break
                row['source_compared']+=1
            else:row['result']='passed'
        finally:native.close()
        report['slots'][f'{slot:02x}']=row
    if any(sha(Path(k).read_bytes())!=v for k,v in hashes.items()):raise ValueError('model changed during comparison')
    report['result']='diverged' if any(x['result']=='diverged' for x in report['slots'].values()) else 'bounded'
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:{q:v[q] for q in ('result','source_compared','native_elements','first_divergence','rollback_verified')} for k,v in report['slots'].items()},indent=2))
    if report['result']=='diverged':raise SystemExit(1)
if __name__=='__main__':main()
