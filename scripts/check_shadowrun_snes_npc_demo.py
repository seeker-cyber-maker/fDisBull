#!/usr/bin/env python3
"""Compare the two-actor prepared NPC demo with withheld original frames."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from fdisbull.game_il import canonical
from fdisbull.shadowrun_snes_field import ROM_SHA256, SAVE_SHA256
from fdisbull.shadowrun_snes_npc import SOURCE,FIELDS,demo_from_capture
from fdisbull.udc_macos import build_macos
from check_shadowrun_macos import Native
from check_shadowrun_snes_npc import CORE,RECEIPT,CHECK,sha

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('rom','original','output'):p.add_argument('--'+k,required=True,type=Path)
    a=p.parse_args();out=a.output.resolve()
    if out.exists() or any((x/'.git').exists() for x in (out,*out.parents)):
        raise ValueError('output must be a new private directory outside Git')
    raw=(a.original/'receipt.json').read_bytes();r=json.loads(raw);rom=a.rom.read_bytes()
    save=(a.original/'save_ram.bin').read_bytes()
    if (sha(raw)!=RECEIPT or sha(rom)!=ROM_SHA256 or r['rom_sha256']!=ROM_SHA256 or
        r['core_sha256']!=CORE or r['system']!='snes' or r['patches'] or
        sha(save)!=SAVE_SHA256 or r['save_ram_sha256']!=SAVE_SHA256 or
        r['frame_images_phase']!='after retro_run; frame is zero-based'):
        raise ValueError('source identity, patch or frame phase mismatch')
    entries={x['frame']:x for x in r['frame_ram']}
    if len(entries)!=len(r['frame_ram']) or set(entries)!=(set(range(2000,2063))|{2999}):
        raise ValueError('source frame set incomplete')
    def source(frame):
        item=entries[frame];b=(a.original/item['file']).read_bytes()
        if len(b)!=131072 or sha(b)!=item['sha256']:raise ValueError('source frame identity mismatch')
        return b
    seed=source(2000); watched=[SOURCE,ROOT/'src/fdisbull/shadowrun_snes_npc.py']
    hashes={str(p):sha(p.read_bytes()) for p in watched}
    machine,_=demo_from_capture(rom,seed,save);state=machine.snapshot()
    if state['demo_actor_id']!=[0x44,0x46]:raise ValueError('unexpected demo actors')
    out.mkdir(mode=0o700,parents=True)
    build=build_macos(machine.program,state,out/'native',entry='shadowrun_snes_frame')
    native=Native(out/'native/libfdisbull_native.dylib',a.rom.resolve())
    report={'format':'shadowrun-snes-npc-demo-heldout-1','result':'running',
       'source_receipt_sha256':RECEIPT,'rom_sha256':sha(rom),'core_sha256':CORE,
       'seed_sha256':sha(seed),'save_sha256':sha(save),'source_hashes':hashes,
       'program_sha256':sha(canonical(machine.program)),'native_build':build,
       'frame_phase':'zero-based after retro_run','source_compared':0,'native_elements':0,
       'first_divergence':None,'rollback_verified':False,
       'scope':'two noncolliding NPC projections seeded at frame 2000; no future source inputs, script dispatch, animation or rendering flags'}
    try:
        report['native_elements']+=native.compare(state,'seed')
        for frame in range(2001,2063):
            before=machine.snapshot();machine.call('shadowrun_snes_frame',0);state=machine.snapshot()
            rc=native.step(0)
            if state['shadowrun_snes_frame_status']==2:
                if rc!=1:raise AssertionError(('native refusal',frame,rc))
                machine.set_state(before);report['native_elements']+=native.compare(before,('refused',frame))
                if native.step(0)!=1:raise AssertionError(('repeat refusal',frame))
                report['native_elements']+=native.compare(before,('repeat',frame))
                machine.call('shadowrun_snes_frame',0)
                if machine.snapshot()['shadowrun_snes_frame_status']!=2:raise AssertionError(('model repeat',frame))
                machine.set_state(before)
                report.update(result='unsupported',first_divergence={'frame':frame,'kind':'model refused'},rollback_verified=True)
                break
            if rc!=0:raise AssertionError(('native return',frame,rc))
            report['native_elements']+=native.compare(state,frame)
            b=source(frame);mismatch=None
            for i,slot in enumerate((0x44,0x46)):
                for name in CHECK:
                    expected=int.from_bytes(b[FIELDS[name]+slot:FIELDS[name]+slot+2],'little')
                    got=state['demo_'+name[4:]][i]
                    if got!=expected:
                        mismatch={'frame':frame,'slot':slot,'field':name,'model':got,'source':expected};break
                if mismatch:break
            if mismatch:report.update(result='diverged',first_divergence=mismatch);break
            report['source_compared']+=1
        else:report['result']='passed'
    finally:native.close()
    if any(sha(Path(k).read_bytes())!=v for k,v in hashes.items()):raise ValueError('model changed during check')
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('result','source_compared','native_elements','first_divergence','rollback_verified')},indent=2))
    if report['result']=='diverged':raise SystemExit(1)
if __name__=='__main__':main()
