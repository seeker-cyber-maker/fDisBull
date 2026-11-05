"""Bounded original-game research probe. Private inputs and outputs only.
Uses SYNDICATE_HISTORY_WORKSPACE for the caller-owned prepared workspace.
Not a game-independent API or ordinary-player reachability certificate.
"""
import os
from pathlib import Path
import json,time,base64,struct
from z_provider import Controller,MAIN_SHA
from syndicate_scene import Mission,digest,identify_offset
R=Path(os.environ['SYNDICATE_HISTORY_WORKSPACE']).resolve()
import sys
kind=int(sys.argv[1]);label=sys.argv[2];folder=R/'private'/label;folder.mkdir(exist_ok=False)
c=Controller(json.loads((R/'private/mission-binding.json').read_text()));from capture_hits import verify_source_windows; binding_windows=verify_source_windows(c);cp=json.loads((R/'private/engagement.json').read_text());c.rpc('state.load',{'path':cp['path']});b=c.snapshot();assert digest(b)==cp['game_sha256'];keys=[];events=[]
if '--near' in sys.argv:
 before=c.snapshot();c.teleport(digest(before),'person-0',(18240,10432,256))
wp=0x91748 # weapon-6 preferred start, checked from source record
es={e['id']:e for e in Mission(b).summary()['entities']};assert wp==0x80108+es['weapon-6']['source_offset']
for at,dat in [(wp+20,struct.pack('<h',200)),(wp+25,bytes([kind]))]:
 old=c.read(at,len(dat));c.rpc('memory.write',{'address':{'space':'linear','offset':f'0x{c.address(at):08X}'},'expected_sha256':digest(old),'data_base64':base64.b64encode(dat).decode()});assert c.read(at,len(dat))==dat
for i in range(2):keys.append(c.rpc('breakpoints.create',{'kind':'memory_change','address':{'space':'linear','offset':f'0x{c.address(0x88110+20+i):08X}'},'once':False})['breakpoint_id'])
start=c.rpc('execution.timing')['guest_ticks'];tick=start;hp=16;beg=time.monotonic()
def entity(ptr):
 x=identify_offset(ptr-c.address(0x8810e));return f'{x[0]}-{x[1]}' if x else None
try:
 while tick-start<30000 and time.monotonic()-beg<40 and len(events)<40:
  rr=c.call('run',{'guest_ms':min(1000,30000-(tick-start)),'timeout_ms':4000,'fast_forward':True});tick=rr['timing_after']['guest_ticks'];regs=c.call('regs');new=int.from_bytes(c.read(0x88124,2),'little',signed=True)
  if new==hp:continue
  ev={'guest_tick':tick,'hp_before':hp,'hp_after':new,'preferred_pc':hex(int(regs['instruction_pointer'],16)-c.mapping[0]['runtime']+0x10000),'regs':regs,'stop':rr,'entities':{}}
  for name in ['eax','ebx','ecx','edx','esi','edi','ebp']:
   ptr=int(regs['general'][name],16);ident=entity(ptr)
   if ident:
    raw=base64.b64decode(c.rpc('memory.read',{'address':{'space':'linear','offset':f'0x{ptr:08X}'},'length':36})['data_base64'])
    ev['entities'][name]={'id':ident,'raw_hex':raw.hex(),'kind':raw[24],'subtype':raw[25],'owner_candidate':int.from_bytes(raw[28:30],'little')}
  events.append(ev);hp=new
  if hp<=0:break
finally:
 for k in keys:c.rpc('breakpoints.delete',{'breakpoint_id':k})
 c.vehicle_interactions.advance_to_frame()
 s=Mission(c.snapshot()).summary();ss={e['id']:e for e in s['entities']}
 out={'type':kind,'label':label,'events':events,'initial_tick':start,'end_tick':tick,'final_hp':ss['person-0']['health_raw'],'ammo':ss['weapon-6']['health_raw'],'attacker_state':ss['person-11'],'writes':'ammo=200 plus requested type, no health writes','no_rewind_within_capture':True,'per_shot_watchpoints':0}
 (folder/'watch.json').write_text(json.dumps(out,indent=2))
 print(json.dumps(out,indent=2))
