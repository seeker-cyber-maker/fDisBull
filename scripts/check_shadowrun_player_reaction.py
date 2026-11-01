#!/usr/bin/env python3
"""Controlled original party wound start, callback, sprite and outer gate."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine,canonical
from fdisbull.shadowrun_player_reaction import SOURCE,lift_player_reaction
from fdisbull.udl_shadowrun import ROM_SHA256
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def w(b,n):return int.from_bytes(b[n:n+2],'big')
def l(b,n):return int.from_bytes(b[n:n+4],'big')
def main():
 p=argparse.ArgumentParser()
 for k in ('rom','core','run','output'):p.add_argument('--'+k,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();core=Path(a.core).read_bytes();root=Path(a.run);cr=(root/'capture.json').read_bytes();cap=json.loads(cr);rec=json.loads((root/'native/receipt.json').read_text());author=SOURCE.read_bytes()
 if sha(rom)!=ROM_SHA256 or sha(core)!=CORE or rec['patches'] or rec['memory_injection_mode']!='no memory patches':raise ValueError('source or capture mismatch')
 rel='native/scene-005999/ram.bin';raw=(root/rel).read_bytes()
 if len(raw)!=65536 or cap['files'][rel]['sha256']!=sha(raw):raise ValueError('capture mismatch')
 b=bytes(raw[i^1] for i in range(65536));source=b[0x100:0x200]
 if (w(source,14),source[0x10],source[0x4c],source[0x9c])!=(3,15,10,10):raise ValueError('player profile mismatch')
 program=lift_player_reaction(rom);m=GameMachine(program,{0:rom});out=_private_directory(a.output);out.mkdir(mode=0o700);results=[]
 for mode in ('start','callback','advance','select','gate'):
  variants=[]
  for heading in range(0,65536,8192):
   anim=w(rom,0xc072+((heading>>13)&7)*2)
   for variant in (0,1):
    actor=bytearray(source);actor[0x2e:0x30]=heading.to_bytes(2,'big')
    if mode!='start':
     actor[0x3a:0x3e]=(0xb07e).to_bytes(4,'big');actor[0x16:0x18]=(anim | (0x8000 if mode=='gate' and variant else 0)).to_bytes(2,'big')
     actor[0x18:0x1a]=(768 if variant else 480).to_bytes(2,'big');actor[0x1a:0x1c]=(4000 if variant else 0).to_bytes(2,'big');actor[0x1c:0x1e]=(4096).to_bytes(2,'big');actor[0x1e:0x20]=(2 if mode=='select' and variant else 1 if mode=='advance' and variant else 0).to_bytes(2,'big');actor[0xce]=1 if variant else 8
    actor[0xdc:0xde]=(0 if variant else 37).to_bytes(2,'big')
    variants.append((heading,variant,bytes(actor)))
  cases=[]
  for heading,variant,actor in variants:
   segments=[{'address':0xff0100,'data':actor.hex()}]
   if mode=='callback':segments += [{'address':0xff1700,'data':b[0x1700:0x2200].hex()},{'address':0xffdd00,'data':b[0xdd00:0xe200].hex()},{'address':0xffef10,'data':b[0xef10:0xef14].hex()},{'address':0xfffc0a,'data':'0000'}]
   cases.append({'name':f'{heading}-{variant}','registers':{'A0':0xff0100},'ram':segments})
  mode_config={
   'start':(0xaff2,[(0xaf6c,0xaf7c),(0xaff2,0xb03e)],[0xb03c]),
   'callback':(0xb07e,[(0xb07e,0xb0ac),(0xb48c,0xb49c),(0xe7c8,0xeb4e),(0xedfa,0xee10),(0x530de,0x530ea)],[0xb0aa]),
   'advance':(0x5fdc,[(0x5fdc,0x600e)],[0x600c]),
   'select':(0x600e,[(0x600e,0x6060)],[0x6044,0x605c,0x6060]),
   'gate':(0xa8fc,[(0xa8fc,0xaa76)],[0xaa74,0xacae,0xaa4c,0xab02,0xa9a6])}
  entry,spans,stops=mode_config[mode]
  if mode=='gate':stops.remove(0xa9a6)
  watch=[{'name':'actor','address':0xff0100,'length':256},{'name':'globals','address':0xffdd00,'length':1280},{'name':'corners','address':0xffef10,'length':4}]
  contract={'name':'player-reaction-'+mode,'entry':entry,'code_ranges':[{'start':x,'end':y} for x,y in spans],'stop_pcs':stops,'stack_scratch_bytes':128,'max_instructions':1000,'watch':watch,'cases':cases}
  cp=out/(mode+'.json');cp.write_text(json.dumps(contract));q=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',a.rom,'--core',a.core,'--contract',str(cp),'--output',str(out/('native-'+mode))],capture_output=True,text=True,timeout=180)
  if q.returncode:raise RuntimeError(q.stderr[-4000:])
  rr=json.loads((out/('native-'+mode)/'receipt.json').read_text());assert rr['complete'] and rr['inputs_unchanged'] and len(rr['cases'])==len(variants);branches={}
  for (heading,variant,actor),n in zip(variants,rr['cases']):
   m.set_state({'shadowrun_reaction_kind':w(actor,14),'shadowrun_reaction_x':w(actor,0),'shadowrun_reaction_y':w(actor,4),'shadowrun_reaction_heading':w(actor,0x2e),'shadowrun_reaction_animation':w(actor,0x16),'shadowrun_reaction_increment':w(actor,0x18),'shadowrun_reaction_accumulator':w(actor,0x1a),'shadowrun_reaction_threshold':w(actor,0x1c),'shadowrun_reaction_index':w(actor,0x1e),'shadowrun_reaction_move_state':w(actor,0x38),'shadowrun_reaction_action_timer':w(actor,0xdc),'shadowrun_reaction_callback':l(actor,0x3a),'shadowrun_reaction_flags':actor[0x10],'shadowrun_reaction_flags_low':actor[0x11],'shadowrun_reaction_hp':actor[0x4c],'shadowrun_reaction_max_hp':actor[0x9c],'shadowrun_reaction_counter':actor[0xce],'shadowrun_reaction_corners':list(actor[0xd0:0xd4]),'shadowrun_terrain_map':list(b[0x1700:0x2200]),'shadowrun_x_max':w(b,0xddd2),'shadowrun_y_max':w(b,0xddd4),'shadowrun_x_min':w(b,0xddd6),'shadowrun_y_min':w(b,0xddd8),'shadowrun_rect_base':l(b,0xddec),'shadowrun_probe_corners':list(b[0xef10:0xef14])})
   m.call({'start':'shadowrun_reaction_start','callback':'shadowrun_reaction_callback_tick','advance':'shadowrun_reaction_advance','select':'shadowrun_reaction_select','gate':'shadowrun_reaction_outer_gate'}[mode]);s=m.snapshot();pc=n['registers_after']['PC'];af=bytes.fromhex(n['ram_after']['actor'])
   if not s['shadowrun_reaction_supported'] or pc not in stops:raise AssertionError((mode,heading,variant,hex(pc)))
   if mode=='start':got=(s['shadowrun_reaction_callback'],s['shadowrun_reaction_animation'],s['shadowrun_reaction_accumulator'],s['shadowrun_reaction_index'],s['shadowrun_reaction_flags_low'],s['shadowrun_reaction_counter']);expected=(l(af,0x3a),w(af,0x16),w(af,0x1a),w(af,0x1e),af[0x11],af[0xce])
   elif mode=='callback':got=(s['shadowrun_reaction_counter'],s['shadowrun_reaction_move_state'],s['shadowrun_reaction_corners']);expected=(af[0xce],w(af,0x38),list(af[0xd0:0xd4]))
   elif mode in ('advance','select'):got=(s['shadowrun_reaction_animation'],s['shadowrun_reaction_increment'],s['shadowrun_reaction_accumulator'],s['shadowrun_reaction_index'],s['shadowrun_reaction_flags_low']);expected=(w(af,0x16),w(af,0x18),w(af,0x1a),w(af,0x1e),af[0x11])
   else:got=(s['shadowrun_reaction_admitted'],s['shadowrun_reaction_action_timer']);expected=(int(pc==0xacae),w(af,0xdc))
   if got!=expected:raise AssertionError((mode,heading,variant,got,expected))
   branches[hex(pc)]=branches.get(hex(pc),0)+1
  results.append({'mode':mode,'matched':len(variants),'matched_terminal_pcs':branches,'trace_sha256':rr['trace_sha256']})
 if SOURCE.read_bytes()!=author:raise ValueError('source changed')
 summary={'status':'passed','results':results,'rom_sha256':sha(rom),'core_sha256':sha(core),'source_capture_sha256':sha(cr),'authoring_sha256':sha(author),'program_sha256':sha(canonical(program)),'scope':'controlled positive-HP captured party actor: reaction start, callback, animation counter/selector and outer input admission; sound/sprite effects excluded'}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
