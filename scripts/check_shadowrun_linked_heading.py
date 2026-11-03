#!/usr/bin/env python3
"""Check linked-actor original heading and metric using controlled core entry."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine
from fdisbull.shadowrun_linked_heading import SOURCE,lift_linked_heading
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for k in ('rom','core','output'):p.add_argument('--'+k,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();core=Path(a.core).read_bytes();source=SOURCE.read_bytes()
 if sha(core)!=CORE:raise ValueError('wrong core')
 m=GameMachine(lift_linked_heading(rom),{0:rom});out=_private_directory(a.output);out.mkdir(mode=0o700)
 offsets=(-5000,-200,-1,0,1,200,5000)
 cases=[{'name':f'{dx},{dy}','registers':{'D2':10000+dy,'D3':10000+dx,'D4':10000,'D5':10000}} for dx in offsets for dy in offsets]
 cases += [{'name':'captured-0500','registers':{'D2':12938,'D3':21248,'D4':11210,'D5':15584}}]
 c={'name':'linked-target-heading','entry':0x15d3c,'code_ranges':[{'start':0x15d3c,'end':0x15dcc}],'stack_scratch_bytes':32,'max_instructions':250,'cases':cases}
 cp=out/'contract.json';cp.write_text(json.dumps(c));q=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',a.rom,'--core',a.core,'--contract',str(cp),'--output',str(out/'native')],capture_output=True,text=True,timeout=180)
 if q.returncode:raise RuntimeError(q.stderr[-4000:])
 r=json.loads((out/'native/receipt.json').read_text())
 if not r['complete'] or not r['inputs_unchanged'] or len(r['cases'])!=len(cases):raise AssertionError('incomplete original probe')
 for original,case in zip(cases,r['cases']):
  x=original['registers'];m.set_state({'shadowrun_linked_source_x':x['D5'],'shadowrun_linked_source_y':x['D4'],'shadowrun_linked_target_x':x['D3'],'shadowrun_linked_target_y':x['D2']});m.call('shadowrun_linked_measure');s=m.snapshot();got=(s['shadowrun_linked_heading'],s['shadowrun_linked_metric']);expected=(case['registers_after']['D2']&65535,case['registers_after']['D3']&65535)
  if not s['shadowrun_linked_supported'] or got!=expected:raise AssertionError((original['name'],got,expected))
 if SOURCE.read_bytes()!=source or Path(a.rom).read_bytes()!=rom or Path(a.core).read_bytes()!=core:raise ValueError('input changed')
 summary={'status':'passed','cases':len(cases),'rom_sha256':sha(rom),'core_sha256':sha(core),'authoring_sha256':sha(source),'trace_sha256':r['trace_sha256'],'scope':'controlled original linked-target heading and metric; target selection, projectile spawn and motion excluded'}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
