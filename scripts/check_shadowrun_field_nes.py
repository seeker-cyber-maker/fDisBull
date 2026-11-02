#!/usr/bin/env python3
"""Compile and compare an assisted prepared-hit diagnostic on real NES emulation.

Original shot and hit receipts are separate controlled entries. No projectile
motion, ordinary input, actor lifecycle, or combat reachability is claimed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'scripts'))
from fdisbull.game_il import canonical
from fdisbull.shadowrun_field_combat import SOURCE,lift_field_combat
from fdisbull.shadowrun_systems import _probe_source
from check_shadowrun_system_nes import compare

def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for n in ('rom','core','cc65-root','original','output'):p.add_argument('--'+n,required=True,type=Path)
 a=p.parse_args();rom=a.rom.read_bytes();program=lift_field_combat(rom);core=a.core.read_bytes()
 if sha(core)!='5d1db7d31c0dc810ad44888d7a00ea1b77897f9d0d883ec81954694cbfb6fc60':raise ValueError('wrong NES core')
 summary_raw=(a.original/'summary.json').read_bytes();summary=json.loads(summary_raw)
 if summary.get('status')!='passed' or summary.get('cases')!=40 or summary.get('rom_sha256')!=sha(rom) or summary.get('authoring_sha256')!=sha(SOURCE.read_bytes()):raise ValueError('original qualification mismatch')
 shot=json.loads((a.original/'shot/receipt.json').read_text());hit=json.loads((a.original/'hit/receipt.json').read_text())
 if (not shot['complete'] or not hit['complete'] or not shot['inputs_unchanged'] or not hit['inputs_unchanged'] or
     shot['trace_sha256']!=summary['shot_trace_sha256'] or hit['trace_sha256']!=summary['hit_trace_sha256'] or
     len(shot['cases'])!=40 or len(hit['cases'])!=40):raise ValueError('incomplete original qualification')
 states=[]
 for seed in range(1,41):
  states.append({'shadowrun_field_captured_profile':1,'shadowrun_field_actor_index':0,'shadowrun_field_item':2,'shadowrun_field_equipped_slot':0,'shadowrun_field_source_flags':15,'shadowrun_field_ammo':12,'shadowrun_field_slots_busy':0,'shadowrun_field_projectile_x':512,'shadowrun_field_projectile_y':512,'shadowrun_field_target_x':512,'shadowrun_field_target_y':512,'shadowrun_field_target_flags':1,'shadowrun_field_target_flags_b0':0,'shadowrun_field_target_flags_9e':0,'shadowrun_field_target_hp':50,'shadowrun_field_target_a':5,'shadowrun_field_target_b':5,'shadowrun_field_target_c':5,'shadowrun_field_target_posture':0,'shadowrun_field_rng':seed})
 watch=['shadowrun_field_supported','shadowrun_field_target_hp','shadowrun_field_rng','shadowrun_field_source_effect','shadowrun_field_ammo']
 source,expected=_probe_source(program,'shadowrun_field_captured_fire',states,watch,regions={0:rom})
 for i,(want,shotcase,hitcase) in enumerate(zip(expected,shot['cases'],hit['cases']),1):
  hp=bytes.fromhex(hitcase['ram_after']['target'])[0x4c];rng=int.from_bytes(bytes.fromhex(hitcase['ram_after']['globals'])[0x9f8:0x9fa],'big');effect=bytes.fromhex(shotcase['ram_after']['projectile'])[0x9f]
  if [want[k] for k in watch]!=[1,hp,rng,effect,11]:raise AssertionError(f'original mismatch seed {i}')
 out=a.output.resolve()
 if out.exists() or any((x/'.git').exists() for x in (out,*out.parents)):raise ValueError('output must be new and private')
 out.mkdir(mode=0o700,parents=True);(out/'check.c').write_text(source)
 root=a.cc65_root.resolve();env={k:v for k,v in os.environ.items() if not k.startswith(('CC65_','LD_','DYLD_'))};env['LC_ALL']='C'
 cmd=[str(root/'bin/cl65'),'-t','nes','-Oirs','-C',str(root/'cfg/nes.cfg'),'--lib-path',str(root/'lib'),'-I',str(root/'include'),'-o','check.nes','check.c']
 run=subprocess.run(cmd,cwd=out,env=env,text=True,capture_output=True,timeout=120);(out/'build.log').write_text(run.stdout+run.stderr)
 if run.returncode:raise RuntimeError(run.stderr[-3000:])
 image=(out/'check.nes').read_bytes();(out/'watch.json').write_text(json.dumps([{'name':'publication','offset':1792,'length':4+4*len(watch)}]))
 cmd=[sys.executable,str(ROOT/'scripts/check_console_udc.py'),'--core',str(a.core),'--rom',str(out/'check.nes'),'--system','nes','--frames','500','--watch',str(out/'watch.json'),'--output',str(out/'native')]
 run=subprocess.run(cmd,capture_output=True,text=True,timeout=180);(out/'run.log').write_text(run.stdout+run.stderr)
 if run.returncode:raise RuntimeError(run.stderr[-3000:])
 receipt=json.loads((out/'native/receipt.json').read_text());trace_raw=(out/'native/ram_trace.json').read_bytes()
 if receipt['rom_sha256']!=sha(image) or receipt['core_sha256']!=sha(core) or receipt['ram_trace_sha256']!=sha(trace_raw) or receipt['patches']:raise ValueError('NES receipt mismatch')
 result=compare(json.loads(trace_raw),{'watch':watch,'reference_results':expected})
 result.update({'format':'fdisbull-shadowrun-field-nes-diagnostic-1','program_sha256':sha(canonical(program)),'nes_sha256':sha(image),'nes_trace_sha256':sha(trace_raw),'original_summary_sha256':sha(summary_raw),'scope':'40 assisted prepared collision positions; original shot and hit are separately entered; no normal firing or projectile motion'})
 (out/'comparison.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
