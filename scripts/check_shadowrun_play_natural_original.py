#!/usr/bin/env python3
"""Compare an ordinary source encounter with the frozen-NPC NES adaptation.

Only selected actor identity, player position at selection, and sampled ammo/HP
outcomes are compared. NPC paths, timings and complete combat state may differ.
"""
import argparse,hashlib,json
from pathlib import Path
from check_shadowrun_opening_route import SOURCE_ROM_SHA,NES_CORE_SHA,GENESIS_CORE_SHA,captured_file,checked_receipt,indexed_frames,scheduled_mask
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--control',type=Path)
 for n in ('rom','capture','nes','run','output'):p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();out=a.output.resolve()
 if out.exists() or any((x/'.git').exists() for x in (out,*out.parents)):raise ValueError('output must be new and private')
 rom=a.rom.read_bytes();nes=a.nes.read_bytes()
 if sha(rom)!=SOURCE_ROM_SHA:raise ValueError('wrong source')
 cr=(a.capture/'capture.json').read_bytes();c=json.loads(cr)
 if c.get('assistance')!='ordinary controller schedule; no memory patches' or c.get('inputs',{}).get('rom',{}).get('sha256')!=sha(rom) or c.get('inputs',{}).get('core',{}).get('sha256')!=GENESIS_CORE_SHA:raise ValueError('wrong source capture')
 sr=captured_file(a.capture,c,'native/receipt.json');source=json.loads(sr);checked_receipt(source,system='genesis',core_sha=GENESIS_CORE_SHA,rom_sha=sha(rom))
 for f,mask in ((6000,64),(6080,16),(6120,1),(6140,2)):
  if scheduled_mask(source,f)!=mask:raise ValueError('unexpected source input route')
 rr=(a.run/'receipt.json').read_bytes();r=json.loads(rr);checked_receipt(r,system='nes',core_sha=NES_CORE_SHA,rom_sha=sha(nes))
 exp=[{'start':100,'end':160,'buttons':['LEFT']},{'start':180,'end':201,'buttons':['UP']},{'start':220,'end':224,'buttons':['B']},{'start':240,'end':620,'buttons':['A']}]
 if r.get('inputs')!=exp or r.get('watches')!=[{'name':'state','offset':1792,'length':84}]:raise ValueError('wrong target input route')
 raw=(a.run/'ram_trace.json').read_bytes();frames=indexed_frames(raw,r);rows=[];bad=[]
 for sf,nf in ((6120,220),(6140,240),(6175,290),(6250,349)):
  data=captured_file(a.capture,c,f'native/scene-{sf:06d}/ram.bin');m=bytes(data[i^1] for i in range(len(data)));b=bytes.fromhex(frames[nf]['raw']['state'])
  if b[:2]!=b'SW' or b[22]&1:raise ValueError('unstable target publication')
  want={'player_x':int.from_bytes(m[0x100:0x102],'big'),'player_y':int.from_bytes(m[0x104:0x106],'big'),
        'target_slot':(int.from_bytes(m[0x1a2:0x1a6],'big')-0xff0400)//256,
        'ammo':m[0x14e],'target_hp':m[0x44c]}
  got={'player_x':int.from_bytes(b[4:6],'little'),'player_y':int.from_bytes(b[6:8],'little'),'target_slot':b[55],'ammo':b[34],'target_hp':b[64]}
  rows.append({'source_frame':sf,'target_frame':nf,'source':want,'target':got,'source_npc_position':[int.from_bytes(m[0x400:0x402],'big'),int.from_bytes(m[0x404:0x406],'big')]})
  if want!=got:bad.append({'source_frame':sf,'target_frame':nf})
 neutral=None
 if a.control:
  ur=(a.control/'capture.json').read_bytes();u=json.loads(ur);us_raw=captured_file(a.control,u,'native/receipt.json');us=json.loads(us_raw)
  checked_receipt(us,system='genesis',core_sha=GENESIS_CORE_SHA,rom_sha=sha(rom))
  if (u.get('assistance')!='ordinary controller schedule; no memory patches' or us.get('inputs')!=source.get('inputs') or u.get('captures')!=c.get('captures') or u.get('ram_write_observer',{}).get('start') is not None or c.get('ram_write_observer',{}).get('start') is None):raise ValueError('unexpected observer control')
  matching=[]
  for f in c['captures']:
   rel=f'native/scene-{f:06d}/ram.bin';x=captured_file(a.capture,c,rel);y=captured_file(a.control,u,rel)
   if x!=y:raise ValueError('observer changed sampled RAM')
   matching.append({'frame':f,'ram_sha256':sha(x)})
  neutral={'matched_full_ram_frames':matching,'control_capture_sha256':sha(ur),'control_receipt_sha256':sha(us_raw)}
 result={'format':'fdisbull-shadowrun-natural-encounter-1','rows':rows,'mismatches':bad,'observer_control':neutral,'source_capture_sha256':sha(cr),'source_receipt_sha256':sha(sr),'nes_sha256':sha(nes),'nes_receipt_sha256':sha(rr),'nes_trace_sha256':sha(raw),'scope':'ordinary controller route on both systems; sampled player/selection/ammo/HP effects only; source NPC moves, NES NPC is frozen; observer neutrality applies only to checked RAM snapshots; timing parity unestablished'}
 out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
 if bad:raise SystemExit(1)
if __name__=='__main__':main()
