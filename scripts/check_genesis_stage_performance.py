#!/usr/bin/env python3
"""Compare assisted original-stage Genesis performance on two cartridges.

Select stages in the typed UIL interpreter, skip their intro, and initialize all
79 native state fields through each build's manifest. All ROM data and outputs
stay private. This is not natural play or an independent game-rule oracle.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from fdisbull.game_il import GameMachine,canonical
from fdisbull.udl_miniplanets_full import checked_rom

def sha(b):return hashlib.sha256(b).hexdigest()

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ('core','source-rom','program','baseline','candidate','output'):p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--frames',type=int,default=600);p.add_argument('--pause-frame',type=int,default=220);p.add_argument('--seed-frame',type=int,default=240);p.add_argument('--release-frame',type=int,default=260);p.add_argument('--measure-start',type=int,default=280)
 a=p.parse_args();out=a.output.resolve();root=Path(__file__).resolve().parents[1]
 if out.exists() or any((q/'.git').exists() for q in (out,*out.parents)):raise ValueError('choose fresh output outside Git')
 if not 160<=a.pause_frame<a.seed_frame<a.release_frame<a.measure_start<a.frames<=10000 or a.frames<=320:raise ValueError('invalid bounded timing')
 rom=checked_rom(a.source_rom.read_bytes());program=json.loads(a.program.read_text());program_hash=sha(canonical(program))
 builds={'baseline':a.baseline.resolve(),'candidate':a.candidate.resolve()};manifests={k:json.loads((v/'manifest.json').read_text()) for k,v in builds.items()}
 for m in manifests.values():
  if m['source_rom_sha256']!=sha(rom) or m['program_sha256']!=program_hash or len(m['state_layout'])!=79:raise ValueError('incompatible ROM, program or 79-field profile')
 out.mkdir(parents=True);all_results=[];checker=root/'scripts/check_genesis_performance.py'
 for stage in (40,43,44):
  machine=GameMachine(program,{0:rom},environment={'hv16':[0],'sound_busy':[0]});machine.call('game_boot');machine.set_state({'stage':stage});machine.call('start_game');machine.call('begin_stage',0)
  snapshot=machine.snapshot();actor_count=sum(snapshot['objects'][i]!=0 for i in range(0,192,4))
  if snapshot['mode']!=1 or snapshot['stage']!=stage:raise ValueError('stage setup failed')
  (out/f'stage-{stage}-seed.json').write_text(json.dumps(snapshot))
  for label,build in builds.items():
   layout=manifests[label]['state_layout'];debug_mode=manifests[label]['debug']['mode']
   patches=[{'frame':a.pause_frame,'memory_id':2,'offset':debug_mode^1,'data_hex':'01'},
            {'frame':a.seed_frame,'memory_id':2,'offset':0,'data_hex':('00'*(4*704))},
            {'frame':a.seed_frame,'memory_id':2,'offset':manifests[label]['debug']['logic_epoch'],'data_hex':'0000'},
            {'frame':a.release_frame,'memory_id':2,'offset':debug_mode^1,'data_hex':'00'}]
   if set(snapshot)!=set(layout):raise ValueError('state schema differs from manifest')
   for name,meta in layout.items():
    value=snapshot[name];values=value if isinstance(value,list) else [value]
    if len(values)!=meta['array_length']:raise ValueError('state array length mismatch')
    width=meta['element_bits']//8
    raw=b''.join((int(v)&((1<<(8*width))-1)).to_bytes(width,'big') for v in values)
    if len(raw)!=meta['length']:raise ValueError('state byte length mismatch')
    for index,byte in enumerate(raw):patches.append({'frame':a.seed_frame,'memory_id':2,'offset':(meta['offset']+index)^1,'data_hex':f'{byte:02x}'})
   patchfile=out/f'stage-{stage}-{label}-patches.json';patchfile.write_text(json.dumps(patches))
   for scenario in ('neutral','moving'):
    inp=[{'start':150,'end':160,'buttons':['START']}]
    if scenario=='moving':inp.append({'start':320,'end':min(520,a.frames),'buttons':['RIGHT']})
    inputfile=out/f'{scenario}-inputs.json';inputfile.write_text(json.dumps(inp))
    runout=out/f'stage-{stage}-{label}-{scenario}'
    cmd=[sys.executable,str(checker),'--core',str(a.core),'--cartridge',str(build/'program.md'),'--manifest',str(build/'manifest.json'),'--labels',str(build/'build/labels.txt'),'--renderer',str(build/'build/genesis_game_renderer.c'),'--inputs',str(inputfile),'--patches',str(patchfile),'--watch-state','--frames',str(a.frames),'--measure-start',str(a.measure_start),'--output',str(runout)]
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=150)
    if r.returncode:raise RuntimeError(f'{runout.name}: {r.stderr[-2000:]}')
    from check_genesis_game import debug_bytes,sampled_state,watches_for
    trace=json.loads((runout/'observed/ram_trace.json').read_text());_,state_base,state_length=watches_for(manifests[label])
    for row in trace['frames'][a.pause_frame+5:a.release_frame]:
     if debug_bytes(row)[4]!=1 or debug_bytes(row)[5]!=0:raise AssertionError('diagnostic pause did not settle')
    if sampled_state(trace['frames'][a.release_frame-1],manifests[label],state_base,state_length)!=snapshot:raise AssertionError('assisted 79-field seed differs before release')
    result=json.loads((runout/'receipt.json').read_text());all_results.append({'stage':stage,'stage_name_bcd':snapshot['stage_name'],'original_actor_count':actor_count,'build':label,'scenario':scenario,'seed_fields_read_back':79,'receipt':str(runout/'receipt.json'),'complete_batches':result['complete_batches'],'presentation_rate':result['complete_batches_per_second'],'logic_rate':result['logic_updates_per_second'],'fault_frames':result['fault_frames'],'vram_mismatches':result['complete_batch_mismatches'],'write_counts':result['batch_size_distribution'],'final_scanlines':result['last_line_distribution'],'minimum_staged_sprite_y':result['minimum_staged_sprite_y']})
 summary={'format':'fdisbull-genesis-stage-performance-1','source_sha256':sha(rom),'program_sha256':program_hash,'script_sha256':sha(Path(__file__).read_bytes()),'checker_sha256':sha(checker.read_bytes()),'pause_frame':a.pause_frame,'seed_frame':a.seed_frame,'release_frame':a.release_frame,'measure_start':a.measure_start,'frames':a.frames,'protocol':'UIL game_boot, set stage, start_game and begin_stage(0); pause normal loop, apply all 79 fields, clear publication ring and epoch, read back while paused, then release; intro skipped; same controller schedule','results':all_results,'limitations':['assisted selection and state initialization, not input-only completion','states evolve at each build\'s own native update cadence','stage-specific audio hardware state is not seeded','VDP writes observed on a pinned emulator, not physical hardware or original pixel parity']}
 (out/'receipt.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
