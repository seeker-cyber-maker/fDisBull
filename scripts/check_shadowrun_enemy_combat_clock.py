#!/usr/bin/env python3
"""Compare combat clock start, tick and expiry with original CPU."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine,canonical
from fdisbull.shadowrun_enemy_combat_clock import SOURCE,lift_enemy_combat_clock
from fdisbull.udl_shadowrun import ROM_SHA256
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def w(b,n):return int.from_bytes(b[n:n+2],'big')
def l(b,n):return int.from_bytes(b[n:n+4],'big')
def main():
 p=argparse.ArgumentParser()
 for k in ('rom','core','run','output'):p.add_argument('--'+k,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();core=Path(a.core).read_bytes();root=Path(a.run);capraw=(root/'capture.json').read_bytes();cap=json.loads(capraw);rc=json.loads((root/'native/receipt.json').read_text());author=SOURCE.read_bytes()
 if sha(rom)!=ROM_SHA256 or sha(core)!=CORE or rc['patches'] or rc['memory_injection_mode']!='no memory patches':raise ValueError('identity or capture patches')
 groups=[]
 for frame in cap['captures']:
  rel=f'native/scene-{frame:06d}/ram.bin';raw=(root/rel).read_bytes()
  if len(raw)!=65536 or cap['files'][rel]['sha256']!=sha(raw):raise ValueError('RAM mismatch')
  base=bytes(raw[i^1] for i in range(65536))
  for mode,timer,pause,longmode,scene in [('start',0,0,0,2),('start',0,0,1,2),('start',0,0,0,54),('tick',0,0,0,2),('tick',1,0,0,2),('tick',120,0,0,2),('tick',10,1,0,2),('tick',10,0,0,20)]:
   b=bytearray(base);b[0xddc4:0xddc6]=scene.to_bytes(2,'big');b[0xdf84:0xdf86]=(0 if mode=='start' else 65535).to_bytes(2,'big');b[0xdf86:0xdf88]=timer.to_bytes(2,'big');b[0xe162:0xe166]=longmode.to_bytes(4,'big');b[0xe186]=pause;b[0xe16f]=0;b[0xe177]=0
   groups.append((frame,mode,bytes(b)))
 out=_private_directory(a.output);out.mkdir(mode=0o700);results=[]
 for mode in ('start','tick'):
  these=[z for z in groups if z[1]==mode]
  cases=[{'name':f'{frame}-{i}','ram':[{'address':0xff0100,'data':b[0x100:0xb00].hex()},{'address':0xffdd00,'data':b[0xdd00:0xe200].hex()}]} for i,(frame,_,b) in enumerate(these)]
  contract={'name':'combat-clock-'+mode,'entry':0x1dbaa if mode=='start' else 0x1de00,'code_ranges':[{'start':0x1dbaa,'end':0x1dc22},{'start':0x1de00,'end':0x1de40}], 'stop_pcs':[0x1dbc0,0x1dbee] if mode=='start' else [0x1de3e,0x1de7c], 'stack_scratch_bytes':128,'max_instructions':1000,'watch':[{'name':'actors','address':0xff0100,'length':2560},{'name':'globals','address':0xffdd00,'length':1280}],'cases':cases}
  cp=out/(mode+'.json');cp.write_text(json.dumps(contract));q=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',a.rom,'--core',a.core,'--contract',str(cp),'--output',str(out/('native-'+mode))],capture_output=True,text=True,timeout=180)
  if q.returncode:raise RuntimeError(q.stderr[-4000:])
  r=json.loads((out/('native-'+mode)/'receipt.json').read_text());assert r['complete'] and r['inputs_unchanged'] and len(r['cases'])==len(cases)
  prog=lift_enemy_combat_clock(rom);m=GameMachine(prog,{});branches={}
  for (frame,_,b),native in zip(these,r['cases']):
   actors=b[0x100:0xb00]
   m.set_state({'shadowrun_ai_clock_combat':w(b,0xdf84),'shadowrun_ai_clock_timer':w(b,0xdf86),'shadowrun_ai_clock_scene':w(b,0xddc4),'shadowrun_ai_clock_long_mode':l(b,0xe162),'shadowrun_ai_clock_scene_override':b[0xe177], 'shadowrun_ai_clock_pause1':b[0xe186],'shadowrun_ai_clock_pause2':b[0xe16f], 'shadowrun_ai_clock_target':[l(actors,i*256+0xa2) for i in range(10)], 'shadowrun_ai_clock_attacker':[l(actors,i*256+0xac) for i in range(10)], 'shadowrun_ai_clock_selected_value':[actors[i*256+0x43] for i in range(10)], 'shadowrun_ai_clock_event_flags':[actors[i*256+0xb0] for i in range(10)], 'shadowrun_ai_clock_flags_low':[actors[i*256+0x11] for i in range(10)]})
   m.call('shadowrun_ai_clock_'+mode);s=m.snapshot();pc=native['registers_after']['PC'];af=bytes.fromhex(native['ram_after']['actors']);g=bytes.fromhex(native['ram_after']['globals'])
   if not s['shadowrun_ai_clock_supported'] or pc not in ((0x1dbc0,0x1dbee) if mode=='start' else (0x1de3e,0x1de7c)):raise AssertionError((frame,mode,hex(pc)))
   got=(s['shadowrun_ai_clock_combat'],s['shadowrun_ai_clock_timer'],s['shadowrun_ai_clock_target'],s['shadowrun_ai_clock_attacker'],s['shadowrun_ai_clock_selected_value'],s['shadowrun_ai_clock_event_flags'],s['shadowrun_ai_clock_flags_low'])
   expected=(w(g,0x284),w(g,0x286),[l(af,i*256+0xa2) for i in range(10)],[l(af,i*256+0xac) for i in range(10)],[af[i*256+0x43] for i in range(10)],[af[i*256+0xb0] for i in range(10)],[af[i*256+0x11] for i in range(10)])
   if got!=expected:raise AssertionError((frame,mode,hex(pc),got,expected))
   key=hex(pc);branches[key]=branches.get(key,0)+1
  results.append({'mode':mode,'matched':len(these),'matched_terminal_pcs':branches,'trace_sha256':r['trace_sha256']})
 if SOURCE.read_bytes()!=author:raise ValueError('source changed')
 summary={'status':'passed','results':results,'rom_sha256':sha(rom),'core_sha256':sha(core),'source_capture_sha256':sha(capraw),'authoring_sha256':sha(author),'program_sha256':sha(canonical(prog)),'scope':'controlled source capture clock start/tick/expiry and actor reset; target-processing tail excluded'}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
