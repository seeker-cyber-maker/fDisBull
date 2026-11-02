#!/usr/bin/env python3
"""Controlled original hostile pursuit continuation in prepared arena."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine,canonical
from fdisbull.shadowrun_hostile_follow import SOURCE,lift_hostile_follow
from fdisbull.udl_shadowrun import ROM_SHA256
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def w(b,n):return int.from_bytes(b[n:n+2],'big')
def l(b,n):return int.from_bytes(b[n:n+4],'big')
def main():
 p=argparse.ArgumentParser()
 for k in ('rom','core','baseline','output'):p.add_argument('--'+k,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();core=Path(a.core).read_bytes();root=Path(a.baseline);rcraw=(root/'receipt.json').read_bytes();rc=json.loads(rcraw);b0=(root/'ram-after.bin').read_bytes();author=SOURCE.read_bytes()
 if sha(rom)!=ROM_SHA256 or sha(core)!=CORE or not rc['complete'] or not rc['inputs_unchanged'] or rc['source_sha256']!=ROM_SHA256 or rc['core_sha256']!=CORE or len(b0)!=65536 or sha(b0)!=rc['cases'][0]['ram_after_sha256']:raise ValueError('identity or prepared receipt mismatch')
 prog=lift_hostile_follow(rom);m=GameMachine(prog,{0:rom});cases=[];inputs=[];refused=0
 for shift in (-32,-16,0,16,32):
  for yshift in (-16,0,16,32):
   b=bytearray(b0);actor=bytearray(b[0x400:0x500]);player=bytearray(b[0x100:0x200]);x=w(actor,0)+shift;y=w(actor,4)+yshift
   actor[0:2]=x.to_bytes(2,'big');actor[4:6]=y.to_bytes(2,'big');b[0x100:0x200]=player;b[0x400:0x500]=actor
   m.set_state({'shadowrun_terrain_map':list(b[0x1700:0x2200]),'shadowrun_hostile_pursuit_x':w(actor,0),'shadowrun_hostile_pursuit_y':w(actor,4),'shadowrun_hostile_pursuit_player_x':w(player,0),'shadowrun_hostile_pursuit_player_y':w(player,4),'shadowrun_hostile_pursuit_kind':w(actor,14),'shadowrun_hostile_pursuit_animation':w(actor,0x16),'shadowrun_hostile_pursuit_collision':w(actor,0xb8),'shadowrun_hostile_pursuit_path_index':w(actor,0xba),'shadowrun_hostile_pursuit_goal_x':w(actor,0x96),'shadowrun_hostile_pursuit_goal_y':w(actor,0x98),'shadowrun_hostile_pursuit_heading':w(actor,0x34),'shadowrun_hostile_pursuit_distance':w(actor,0xc8),'shadowrun_hostile_pursuit_path0':w(actor,0xbc),'shadowrun_hostile_pursuit_path1':w(actor,0xbe),'shadowrun_hostile_pursuit_path2':w(actor,0xc0),'shadowrun_hostile_pursuit_global_de':w(b,0xdfde),'shadowrun_hostile_pursuit_global_e0':w(b,0xdfe0),'shadowrun_hostile_pursuit_callback':l(actor,0x3a),'shadowrun_hostile_pursuit_target':l(actor,0xa2),'shadowrun_hostile_pursuit_flags':actor[0x10],'shadowrun_hostile_pursuit_item':actor[0x57],'shadowrun_hostile_pursuit_slot':actor[0x56],'shadowrun_hostile_pursuit_ammo':actor[0x4e],'shadowrun_hostile_pursuit_alert':b[0xe186],'shadowrun_hostile_pursuit_event':actor[0xb0],'shadowrun_hostile_pursuit_direction':actor[0xb1],'shadowrun_hostile_pursuit_counter':actor[0xb5]})
   m.call('shadowrun_hostile_follow_tick');state=m.snapshot()
   if not state['shadowrun_hostile_follow_supported']:refused+=1;continue
   ranges=[(0x100,0x1100),(0x1100,0x2100),(0x2100,0x2200),(0xdd00,0xe200)]
   cases.append({'name':f'{shift}-{yshift}','registers':{'A0':0xff0400},'ram':[{'address':0xff0000+lo,'data':b[lo:hi].hex()} for lo,hi in ranges]});inputs.append((shift,yshift,dict(state)))
 if not cases:raise ValueError('no supported inputs')
 spans=[(0x13d0c,0x13e40),(0x144e8,0x14640),(0x14682,0x14914),(0x149c0,0x14a38),(0x14b4e,0x14c2e),(0x14d6a,0x14d8e),(0x15ca4,0x15cc0),(0x15d3c,0x15df6)]
 contract={'name':'prepared-hostile-pursuit','entry':0x13d0c,'code_ranges':[{'start':x,'end':y} for x,y in spans],'stop_pcs':[0x1460c,0x13e40,0x1470c,0x14756,0x14a38,0x149d2], 'stack_scratch_bytes':256,'max_instructions':5000,'watch':[{'name':'actor','address':0xff0400,'length':256},{'name':'globals','address':0xffdd00,'length':1280}],'cases':cases}
 # $149D2 is a modeled continuation, not a terminal.
 contract['stop_pcs'].remove(0x149d2)
 out=_private_directory(a.output);out.mkdir(mode=0o700);cp=out/'contract.json';cp.write_text(json.dumps(contract));q=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',a.rom,'--core',a.core,'--contract',str(cp),'--output',str(out/'native')],capture_output=True,text=True,timeout=180)
 if q.returncode:raise RuntimeError(q.stderr[-4000:])
 r=json.loads((out/'native/receipt.json').read_text());assert r['complete'] and r['inputs_unchanged'] and len(r['cases'])==len(cases)
 for (shift,distance,s),n in zip(inputs,r['cases']):
  pc=n['registers_after']['PC'];a1=bytes.fromhex(n['ram_after']['actor']);g=bytes.fromhex(n['ram_after']['globals'])
  if pc!=0x1460c:raise AssertionError((shift,distance,hex(pc)))
  keys=('shadowrun_hostile_pursuit_goal_x','shadowrun_hostile_pursuit_goal_y','shadowrun_hostile_pursuit_event','shadowrun_hostile_pursuit_direction','shadowrun_hostile_pursuit_counter','shadowrun_hostile_pursuit_path0','shadowrun_hostile_pursuit_path1','shadowrun_hostile_pursuit_path2','shadowrun_hostile_pursuit_heading','shadowrun_hostile_pursuit_distance','shadowrun_hostile_pursuit_callback','shadowrun_hostile_pursuit_centre_x','shadowrun_hostile_pursuit_centre_y')
  got=tuple(s[k] for k in keys);expected=(w(a1,0x96),w(a1,0x98),a1[0xb0],a1[0xb1],a1[0xb5],w(a1,0xbc),w(a1,0xbe),w(a1,0xc0),w(a1,0x34),w(a1,0xc8),l(a1,0x3a),w(g,0x2a),w(g,0x2c))
  if got!=expected:raise AssertionError((shift,distance,got,expected))
 if SOURCE.read_bytes()!=author:raise ValueError('source changed')
 summary={'status':'passed','matched':len(cases),'refused_before_native':refused,'rom_sha256':sha(rom),'core_sha256':sha(core),'prepared_receipt_sha256':sha(rcraw),'authoring_sha256':sha(author),'program_sha256':sha(canonical(prog)),'trace_sha256':r['trace_sha256'],'scope':'controlled prepared kind8/item10 following existing westward path; controlled positions; no natural reachability or other pathfinding'}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
