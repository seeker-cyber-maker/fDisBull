#!/usr/bin/env python3
"""Compare title-seeded source scene construction with private SNES writes.

The sole seed is ordinary frame-839 title WRAM. Later trace events and the
first main-loop checkpoint are read only for comparison, never as inputs.
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
from fdisbull.shadowrun_snes_scene_init import (SOURCE,COLLISION_SOURCE,constructed_from_title_capture)
from fdisbull.shadowrun_snes_script import SOURCE as SCRIPT_SOURCE
from fdisbull.udc_macos import build_macos
from check_shadowrun_macos import Native

CORE='6d679f9123cbffe635815dfc137af88c2effc54bd9355f3cd112fb3cd4e51283'
TRACE='da5564e5bb42602a38bb217a150698ec7becb4bff9554740daca6646b1a68d5b'
TITLE='15caaf78faed99408c783119ac5e1703da066b904e5570dd895b7bcb49db9d93'
TASK_FIELDS={'task_frame':0x26e,'task_callback':0x2ce,'task_next':0x32e,
             'task_link':0x38e,'task_wait':0xbbe}
def sha(b):return hashlib.sha256(b).hexdigest()
def word(b,a):return b[a]|(b[a+1]<<8)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('rom','original','output'):p.add_argument('--'+k,required=True,type=Path)
    a=p.parse_args();original=a.original.resolve();out=a.output.resolve()
    if out.exists() or any((x/'.git').exists() for x in (out,*out.parents)):
        raise ValueError('output must be a fresh private directory outside Git')
    base=original/'reference-continuous';watched=original/'init-writes-900'
    r=json.loads((base/'receipt.json').read_bytes());tr=json.loads((watched/'receipt.json').read_bytes())
    trace=(watched/'snes_trace.json').read_bytes();rom=a.rom.read_bytes()
    if (sha(rom)!=ROM_SHA256 or r['rom_sha256']!=ROM_SHA256 or tr['rom_sha256']!=ROM_SHA256 or
        r['core_sha256']!=CORE or tr['core_sha256']!=CORE or r['patches'] or tr['patches'] or
        sha(trace)!=TRACE or tr['snes_trace_sha256']!=TRACE):raise ValueError('source or trace identity mismatch')
    title=(base/'ram-000839.bin').read_bytes()
    if len(title)!=131072 or sha(title)!=TITLE:raise ValueError('wrong title seed')
    cps=[c for f in r['snes_checkpoints']['frames'] for c in f['captures'] if c['serial']==1]
    if len(cps)!=1 or r['snes_checkpoints']['pc']!=0x80962e:raise ValueError('missing first main-loop checkpoint')
    cp=(base/cps[0]['file']).read_bytes()
    if len(cp)!=131072 or sha(cp)!=cps[0]['sha256']:raise ValueError('checkpoint mismatch')
    sources=[Path(__file__).resolve(),SOURCE,COLLISION_SOURCE,SCRIPT_SOURCE,
             ROOT/'src/fdisbull/game_sources/shadowrun_snes_task_init.c',
             ROOT/'src/fdisbull/shadowrun_snes_scene_init.py']
    hashes={str(x):sha(x.read_bytes()) for x in sources}
    machine=constructed_from_title_capture(rom,title);seed=machine.snapshot()
    out.mkdir(mode=0o700,parents=True)
    build=build_macos(machine.program,seed,out/'native',entry='shadowrun_snes_scene_construct',
                      unsupported_status='scene_construct_status')
    native=Native(out/'native'/'libfdisbull_native.dylib',a.rom.resolve())
    try:
        native_elements=native.compare(seed,'seed')
        machine.call('shadowrun_snes_scene_construct',0);s=machine.snapshot()
        if s['scene_construct_status']!=1 or native.step(0)!=0:raise ValueError('construction refused')
        native_elements+=native.compare(s,'constructed')
    finally:native.close()
    events=json.loads(trace)['frames'];world={};room={};created={}
    for frame in events:
        if frame['dropped']:raise ValueError('original write trace has dropped events')
        for e in frame['events']:
            if e['kind']!=2:continue
            address=e['address'];pc=e['pc'];lo=address&65535;bank=address>>16
            if 0x7e2e00<=address<0x7e3bbb and pc in (0x809e59,0x809e6a,0x809eb7):world[lo]=e['value']
            if 0x7fda14<=address<0x7fdb1b and pc in (0x809f41,0x809f52,0x809f9f):room[lo]=e['value']
            if frame['frame']==1015 and bank in (0x7e,0x80) and (
              0x80a7c2<=pc<=0x80a881 or 0x80a343<=pc<=0x80a3cb or 0x80c212<=pc<=0x80c335):
                created[lo]=e['value']
    if len(world)!=3515 or len(room)!=263:raise ValueError('source write coverage incomplete')
    def created_byte(addr):
        for name,base_addr in TASK_FIELDS.items():
            if base_addr<=addr<base_addr+96:
                return (s[name][(addr-base_addr)//2]>>(8*((addr-base_addr)&1)))&255
        if 0x3ee<=addr<0x3f2:return s['task_heap_first_header'][addr-0x3ee]
        if 0x3f2<=addr<0xbbe:return s['task_heap'][addr-0x3f2]
        if 0x268<=addr<0x26a:return (s['task_list_head']>>(8*(addr-0x268)))&255
        if 0x26a<=addr<0x26c:return (s['task_list_free']>>(8*(addr-0x26a)))&255
        return s['task_shared'][addr]
    mismatch=[]
    for label,mapping,reader in (('world',world,lambda i:s['task_shared'][i]),
                                ('room',room,lambda i:s['scene_7f'][i]),
                                ('actor_task_writes',created,created_byte)):
        mismatch.extend((label,hex(i),reader(i),v) for i,v in mapping.items() if reader(i)!=v)
    collision=[]
    for name,start,n,model,offset in (
      ('static_heads',0xde88,512,s['task_shared'],0),
      ('rectangles',0xe288,s['scene_static_record'],s['task_shared'],0),
      ('node_records',0xef18,s['scene_static_node'],s['task_shared'],0),
      ('node_next',0xf778,s['scene_static_node'],s['task_shared'],0),
      ('owners',0xe214,(s['scene_static_record']//4)+2,s['scene_7f'],65536)):
        for i in range(n):
            x=model[start+i];y=cp[offset+start+i];collision.append(1)
            if x!=y:mismatch.append((name,hex(start+i),x,y))
    for name,address in (('static_record_end',0xde84),('static_node_end',0xde86),
                         ('camera_x',0x0ce0),('camera_y',0x0ce2),('camera_bounds',0x0cf6),
                         ('room_list',0x009a),('second_list',0x009d),('waypoint_list',0x00f3)):
        x=word(s['task_shared'],address);y=word(cp,address);collision.append(1)
        if x!=y:mismatch.append((name,hex(address),x,y))
    for name,address in (('room_bank',0x009c),('second_list_bank',0x009f),('waypoint_bank',0x00f5)):
        x=s['task_shared'][address];y=cp[address];collision.append(1)
        if x!=y:mismatch.append((name,hex(address),x,y))
    if any(sha(Path(k).read_bytes())!=v for k,v in hashes.items()):raise ValueError('source changed during check')
    report={'result':'passed' if not mismatch else 'mismatch','title_sha256':sha(title),
      'checkpoint_sha256':sha(cp),'original_write_trace_sha256':TRACE,'program_sha256':sha(canonical(machine.program)),
      'source_hashes':hashes,'native_build':build,'native_elements':native_elements,
      'world_bytes':len(world),'room_bytes':len(room),'actor_task_write_bytes':len(created),
      'collision_elements':len(collision),'actor_entries':s['scene_entry'],
      'static_records':s['scene_static_record']//12,'static_nodes':s['scene_static_node']//2,
      'first_mismatches':mismatch[:20],
      'scope':'single source-seeded initialization slice; direct-page scratch, later task execution, dynamic collision and rendering excluded'}
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('native_build','source_hashes')},indent=2))
    if mismatch:raise SystemExit(1)

if __name__=='__main__':main()
