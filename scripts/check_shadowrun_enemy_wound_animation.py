#!/usr/bin/env python3
"""Original CPU comparisons for wounded animation counter and selector."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine,canonical
from fdisbull.shadowrun_enemy_wound_animation import SOURCE,lift_enemy_wound_animation
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
 actors=[]
 for frame in cap['captures']:
  rel=f'native/scene-{frame:06d}/ram.bin';raw=(root/rel).read_bytes()
  if len(raw)!=65536 or cap['files'][rel]['sha256']!=sha(raw):raise ValueError('RAM mismatch')
  b=bytes(raw[i^1] for i in range(65536));actor=b[0x400:0x500]
  if w(actor,0xe)==11 and l(actor,0x3a)==0xb07e and w(actor,0x16) in (0x7c,0x807c):actors.append((frame,actor))
 out=_private_directory(a.output);out.mkdir(mode=0o700);prog=lift_enemy_wound_animation(rom);m=GameMachine(prog,{0:rom});results=[]
 for mode in ('advance','select'):
  variants=[]
  for frame,actor in actors:
   for forced in (False,True):
    v=bytearray(actor)
    if forced:
     if mode=='advance':v[0x1a:0x1c]=(4000).to_bytes(2,'big')
     else:v[0x1e:0x20]=(2).to_bytes(2,'big')
    variants.append((frame,forced,bytes(v)))
  cases=[{'name':f'{frame}-{int(force)}','registers':{'A0':0xff0400},'ram':[{'address':0xff0400,'data':actor.hex()}]} for frame,force,actor in variants]
  contract={'name':'wound-animation-'+mode,'entry':0x5fdc if mode=='advance' else 0x600e,'code_ranges':[{'start':0x5fdc,'end':0x6060}], 'stop_pcs':[0x600c] if mode=='advance' else [0x6044,0x605c,0x6060], 'stack_scratch_bytes':128,'max_instructions':1000,'watch':[{'name':'actor','address':0xff0400,'length':256},{'name':'globals','address':0xffdd3c,'length':4}],'cases':cases}
  cp=out/(mode+'.json');cp.write_text(json.dumps(contract));q=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',a.rom,'--core',a.core,'--contract',str(cp),'--output',str(out/('native-'+mode))],capture_output=True,text=True,timeout=180)
  if q.returncode:raise RuntimeError(q.stderr[-4000:])
  r=json.loads((out/('native-'+mode)/'receipt.json').read_text());assert r['complete'] and r['inputs_unchanged'] and len(r['cases'])==len(cases);branches={}
  for (frame,forced,actor),native in zip(variants,r['cases']):
   m.set_state({'shadowrun_ai_kind':w(actor,14),'shadowrun_ai_callback':l(actor,0x3a),'shadowrun_ai_animation':w(actor,0x16),'shadowrun_ai_flags_low':actor[0x11], 'shadowrun_ai_wound_accumulator':w(actor,0x1a),'shadowrun_ai_wound_increment':w(actor,0x18),'shadowrun_ai_wound_threshold':w(actor,0x1c),'shadowrun_ai_wound_index':w(actor,0x1e)})
   m.call('shadowrun_ai_wound_'+mode);s=m.snapshot();pc=native['registers_after']['PC'];af=bytes.fromhex(native['ram_after']['actor'])
   if not s['shadowrun_ai_wound_anim_supported'] or pc not in ((0x600c,) if mode=='advance' else (0x6044,0x605c)):raise AssertionError((frame,forced,mode,hex(pc)))
   got=(s['shadowrun_ai_animation'],s['shadowrun_ai_wound_increment'],s['shadowrun_ai_wound_accumulator'],s['shadowrun_ai_wound_index'],s['shadowrun_ai_flags_low'])
   expected=(w(af,0x16),w(af,0x18),w(af,0x1a),w(af,0x1e),af[0x11])
   if got!=expected:raise AssertionError((frame,forced,mode,got,expected))
   branches[hex(pc)]=branches.get(hex(pc),0)+1
  results.append({'mode':mode,'matched':len(variants),'matched_terminal_pcs':branches,'trace_sha256':r['trace_sha256']})
 if SOURCE.read_bytes()!=author:raise ValueError('source changed')
 summary={'status':'passed','results':results,'rom_sha256':sha(rom),'core_sha256':sha(core),'source_capture_sha256':sha(capraw),'authoring_sha256':sha(author),'program_sha256':sha(canonical(prog)),'scope':'captured wound counter and negative selector; forced accumulator/index interventions; sprite upload excluded'}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
