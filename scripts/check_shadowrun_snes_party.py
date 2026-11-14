#!/usr/bin/env python3
"""Compare one source-fed $A173 party insertion with original writes/native.

The entry checkpoint supplies all preconditions. It is diagnostic evidence,
not a continuous title-to-player run.
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
from fdisbull.shadowrun_snes_scene_init import SOURCE,party_from_source_capture
from fdisbull.shadowrun_snes_script import SOURCE as SCRIPT_SOURCE
from fdisbull.udc_macos import build_macos
from check_shadowrun_macos import Native

CORE='6d679f9123cbffe635815dfc137af88c2effc54bd9355f3cd112fb3cd4e51283'
SEED='047f4e7482354a659b34bee8fac0285254111bb15a96df8da69e33637aede8ac'
TRACE='252b911e5c82ab078b250ddf44d0ba98667fc719e174f64b00b98b31439671c8'
FIELDS={'task_frame':0x26e,'task_callback':0x2ce,'task_next':0x32e,'task_link':0x38e,'task_wait':0xbbe}
def sha(b):return hashlib.sha256(b).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('rom','original','output'):p.add_argument('--'+k,required=True,type=Path)
    a=p.parse_args();out=a.output.resolve();original=a.original.resolve()
    if out.exists() or any((x/'.git').exists() for x in (out,*out.parents)):
        raise ValueError('output must be a fresh private directory outside Git')
    entry=original/'player-create-entry';watched=original/'player-select-writes'
    r=json.loads((entry/'receipt.json').read_bytes());t=json.loads((watched/'receipt.json').read_bytes())
    rom=a.rom.read_bytes();raw=(watched/'snes_trace.json').read_bytes()
    if (sha(rom)!=ROM_SHA256 or r['rom_sha256']!=ROM_SHA256 or t['rom_sha256']!=ROM_SHA256 or
        r['core_sha256']!=CORE or t['core_sha256']!=CORE or r['patches'] or t['patches'] or
        sha(raw)!=TRACE or t['snes_trace_sha256']!=TRACE or r['snes_checkpoints']['pc']!=0x80a173):
        raise ValueError('unexpected source, trace or checkpoint')
    before=(entry/'checkpoint-002680-00.bin').read_bytes()
    if len(before)!=131072 or sha(before)!=SEED:raise ValueError('wrong source entry checkpoint')
    sources=[Path(__file__).resolve(),SOURCE,SCRIPT_SOURCE,ROOT/'src/fdisbull/game_sources/shadowrun_snes_task_init.c',
             ROOT/'src/fdisbull/shadowrun_snes_scene_init.py']
    hashes={str(x):sha(x.read_bytes()) for x in sources}
    m=party_from_source_capture(rom,before);seed=m.snapshot();out.mkdir(mode=0o700,parents=True)
    build=build_macos(m.program,seed,out/'native',entry='shadowrun_snes_party_construct',
                      unsupported_status='scene_party_status')
    native=Native(out/'native'/'libfdisbull_native.dylib',a.rom.resolve())
    try:
        count=native.compare(seed,'seed');m.call('shadowrun_snes_party_construct',0);s=m.snapshot()
        if s['scene_party_status']!=1 or native.step(0)!=0:raise ValueError('party insertion refused')
        count+=native.compare(s,'party insertion')
    finally:native.close()
    f=next(x for x in json.loads(raw)['frames'] if x['frame']==2680)
    if f['dropped']:raise ValueError('trace dropped events')
    events=f['events'];lo=next(i for i,e in enumerate(events) if e['pc']==0x80a179)
    hi=max(i for i,e in enumerate(events) if e['pc']==0x80a21f)+1
    expected={}
    for e in events[lo:hi]:
        if e['kind']==2 and e['address']>>16 in (0x7e,0x80):expected[e['address']&65535]=e['value']
    def actual(a):
        for name,base in FIELDS.items():
            if base<=a<base+96:return (s[name][(a-base)//2]>>(8*((a-base)&1)))&255
        if 0x3ee<=a<0x3f2:return s['task_heap_first_header'][a-0x3ee]
        if 0x3f2<=a<0xbbe:return s['task_heap'][a-0x3f2]
        for name,base in (('task_list_head',0x268),('task_list_free',0x26a),('task_list_current',0x26c)):
            if base<=a<base+2:return (s[name]>>(8*(a-base)))&255
        return s['task_shared'][a]
    bad=[(hex(a),actual(a),v) for a,v in expected.items() if actual(a)!=v]
    if any(sha(Path(k).read_bytes())!=v for k,v in hashes.items()):raise ValueError('source changed during check')
    report={'result':'passed' if not bad else 'mismatch','entry_sha256':SEED,'original_trace_sha256':TRACE,
      'program_sha256':sha(canonical(m.program)),'source_hashes':hashes,'native_build':build,
      'source_write_bytes':len(expected),'native_elements':count,'actor':s['scene_actor'],
      'task_script':s['scene_task_id'],'first_mismatches':bad[:20],
      'scope':'source-fed single $A173 party insertion; does not qualify preceding title or script execution'}
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('native_build','source_hashes')},indent=2))
    if bad:raise SystemExit(1)

if __name__=='__main__':main()
