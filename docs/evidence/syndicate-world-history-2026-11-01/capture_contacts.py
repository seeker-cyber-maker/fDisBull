"""Bounded original-game research probe. Private inputs and outputs only.
Uses SYNDICATE_HISTORY_WORKSPACE for the caller-owned prepared workspace.
Not a game-independent API or ordinary-player reachability certificate.
"""
import os
from pathlib import Path
import json,time,base64,struct,sys
from z_provider import Controller,MAIN_SHA
from syndicate_scene import Mission,digest,identify_offset
R=Path(os.environ['SYNDICATE_HISTORY_WORKSPACE']).resolve();kind=int(sys.argv[1]);label=sys.argv[2];folder=R/'private'/label;folder.mkdir(exist_ok=False)
c=Controller(json.loads((R/'private/mission-binding.json').read_text()));from capture_hits import verify_source_windows; binding_windows=verify_source_windows(c);cp=json.loads((R/'private/engagement.json').read_text());c.rpc('state.load',{'path':cp['path']});assert digest(c.snapshot())==cp['game_sha256'];keys=[];events=[];writes=[]
if '--near' in sys.argv:
 before=c.snapshot();c.teleport(digest(before),'person-0',(18240,10432,256));writes.append({'preparation':'graph-preserving teleport to original guard vicinity','xyz':[18240,10432,256]})
wp=0x91748
for at,dat in [(wp+20,struct.pack('<h',200)),(wp+25,bytes([kind]))]:
 old=c.read(at,len(dat));c.rpc('memory.write',{'address':{'space':'linear','offset':f'0x{c.address(at):08X}'},'expected_sha256':digest(old),'data_base64':base64.b64encode(dat).decode()});assert c.read(at,len(dat))==dat
 writes.append({'preferred':hex(at),'old':old.hex(),'new':dat.hex()})
def ident(ptr):
 x=identify_offset(ptr-c.address(0x8810e));return f'{x[0]}-{x[1]}' if x else None
def mem(ptr,n):return base64.b64decode(c.rpc('memory.read',{'address':{'space':'linear','offset':f'0x{ptr:08X}'},'length':n})['data_base64'])
def ent(ptr):
 name=ident(ptr)
 if not name:return {'id':None}
 b=mem(ptr,92 if name.startswith('person-') else 36)
 return {'id':name,'kind':b[24],'subtype':b[25],'hp_word':int.from_bytes(b[20:22],'little',signed=True),'last_source_ref':int.from_bytes(b[22:24],'little'),'owner_field_raw':int.from_bytes(b[28:30],'little'),'flags_c':int.from_bytes(b[12:14],'little'),'xyz':list(struct.unpack_from('<HHH',b,4))}
sites=[0x127a0,0x127b7,0x12b7f,0x12b83,0x32fc0,0x32d1b,0x32d21,0x33003,0x33009,0x32ee0,0x32ee6,0x32fa0,0x32fa6,0x13be4,0x13be8]
for p in sites:keys.append(c.rpc('breakpoints.create',{'kind':'execution','address':{'space':'segmented','segment':'0x0158','offset':f'0x{c.address(p):08X}'},'once':False})['breakpoint_id'])
start=c.rpc('execution.timing')['guest_ticks'];tick=start;beg=time.monotonic();hits=0
try:
 while tick-start<30000 and time.monotonic()-beg<35 and hits<200:
  rr=c.call('run',{'guest_ms':min(1000,30000-(tick-start)),'timeout_ms':4000,'fast_forward':True});tick=rr['timing_after']['guest_ticks'];g=c.call('regs');pc=int(g['instruction_pointer'],16)-c.mapping[0]['runtime']+0x10000
  if pc not in sites:continue
  hits+=1;gg={k:int(v,16) for k,v in g['general'].items()};e={'pc':hex(pc),'tick':tick,'regs':g,'victim':ent(c.address(0x88110))}
  if pc in [0x127a0,0x127b7]:
   args=struct.unpack('<III',mem(gg['esp'],12));e['caller']=hex(args[0]-c.mapping[0]['runtime']+0x10000);e['source']=ent(args[1]);e['destination']=ent(args[2])
  elif pc in [0x12b7f,0x12b83]:e['source']=ent(gg['esi']);e['destination']=ent(gg['ebx']);e['applied_mask']=gg['eax']&65535
  elif pc==0x32fc0:e['destination']=ent(int.from_bytes(mem(gg['esp']+4,4),'little'))
  elif pc in [0x32ee0,0x32ee6,0x32fa0,0x32fa6,0x32d1b,0x32d21]:e['destination']=ent(gg['eax'])
  else:e['destination']=ent(gg['ebx']);e['source']=ent(gg['ebp'])
  events.append(e)
  if e['victim']['hp_word']<0:break
finally:
 for k in keys:c.rpc('breakpoints.delete',{'breakpoint_id':k})
 c.vehicle_interactions.advance_to_frame();b=c.snapshot();ss={e['id']:e for e in Mission(b).summary()['entities']};
 out={'type':kind,'label':label,'writes':writes,'events':events,'start':start,'end':tick,'bp_hits':hits,'final_hp':ss['person-0']['health_raw'],'final_ammo6':ss['weapon-6']['health_raw'],'final_selected':ss['person-11']['selected_weapon_ref'],'coverage':'selected contact and health sinks; not all damage writers','native_no_rewind_during_capture':True}
 (folder/'trace.json').write_text(json.dumps(out,indent=2)+'\n')
 print(json.dumps(out,indent=2))
