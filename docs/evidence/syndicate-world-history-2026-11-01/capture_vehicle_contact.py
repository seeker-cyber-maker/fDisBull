"""Bounded original-game research probe. Private inputs and outputs only.
Uses SYNDICATE_HISTORY_WORKSPACE for the caller-owned prepared workspace.
Not a game-independent API or ordinary-player reachability certificate.
"""
import os
"""One disposable diagnostic car-contact attempt; not a generic driving adapter."""
from pathlib import Path
import json,time,base64,struct
from z_provider import Controller
from syndicate_scene import Mission,digest,identify_offset
R=Path(os.environ['SYNDICATE_HISTORY_WORKSPACE']).resolve();folder=R/'private'/os.environ.get('SYNDICATE_HISTORY_TRIAL','car-contact-new');folder.mkdir(exist_ok=False)
c=Controller(json.loads((R/'private/mission-binding.json').read_text()));from capture_hits import verify_source_windows; binding_windows=verify_source_windows(c);cp=json.loads((R/'private/ready.json').read_text());c.rpc('state.load',{'path':cp['path']});b=c.snapshot();assert digest(b)==cp['game_sha256'];writes=[];keys=[];events=[]
def edit(p,value,why):
 old=c.read(p,len(value));c.rpc('memory.write',{'address':{'space':'linear','offset':f'0x{c.address(p):08X}'},'expected_sha256':digest(old),'data_base64':base64.b64encode(value).decode()});assert c.read(p,len(value))==value;writes.append({'preferred':hex(p),'old':old.hex(),'new':value.hex(),'why':why})
def bp(p,once=True):
 k=c.rpc('breakpoints.create',{'kind':'execution','address':{'space':'segmented','segment':'0x0158','offset':f'0x{c.address(p):08X}'},'once':once})['breakpoint_id'];keys.append(k);return k
def remove(k):
 try:c.rpc('breakpoints.delete',{'breakpoint_id':k})
 except Exception as e:
  if 'BREAKPOINT_NOT_FOUND' not in str(e):raise

def mem(ptr,n):return base64.b64decode(c.rpc('memory.read',{'address':{'space':'linear','offset':f'0x{ptr:08X}'},'length':n})['data_base64'])
def ident(ptr):
 q=identify_offset(ptr-c.address(0x8810e));return f'{q[0]}-{q[1]}' if q else None

def entity(ptr):
 name=ident(ptr)
 if name is None:return {'id':None}
 b=mem(ptr,36)
 return {'id':name,'kind':b[24],'subtype':b[25],'hp':int.from_bytes(b[20:22],'little',signed=True),'last_source':int.from_bytes(b[22:24],'little'),'owner_head':int.from_bytes(b[28:30],'little'),'flags_c':int.from_bytes(b[12:14],'little'),'xyz':list(struct.unpack_from('<HHH',b,4))}
setup={}
try:
 setup['driver_teleport']=c.teleport(digest(c.snapshot()),'person-1',(15488,9344,256))
 setup['board']=c.vehicle_interactions.perform(digest(c.snapshot()),'person-1','vehicle-0','board')
 setup['pedestrian_preparation']='performed after the original order, before simulation resumes'
 data=c.snapshot();es={e['id']:e for e in Mission(data).summary()['entities']};setup['before']={k:es[k] for k in ['person-0','person-1','vehicle-0']}
 assert c.read(0x60b3e,4)==bytes(4)
 for p,val in [(0x5e552,b'\1'),(0x55390,struct.pack('<HH',300,200)),(0x60b22,struct.pack('<HH',300,200)),(0x60b3f,b'\1')]:edit(p,val,'diagnostic driving order selection/latch')
 k=bp(0x2ddd1);rr=c.call('run',{'guest_ms':2000,'timeout_ms':3000,'fast_forward':True});g=c.call('regs');remove(k)
 assert int(g['instruction_pointer'],16)==c.address(0x2ddd1)
 setup['selected_ptr']=g['general']['esi'];orderptr=int(g['general']['ebx'],16)
 dest=(15496,10680,256)
 for p,val in [(0x60b12,bytes(2)),(0x60b14,bytes(2)),(0x60b1a,bytes(2)),(0x60b1c,struct.pack('<HHH',dest[2],dest[1],dest[0]))]:edit(p,val,'diagnostic vehicle world target')
 k=bp(0x2dedd);rr=c.call('run',{'guest_ms':2000,'timeout_ms':3000,'fast_forward':True});g=c.call('regs');remove(k)
 assert int(g['instruction_pointer'],16)==c.address(0x2dedd);o=mem(orderptr,14);setup['order']={'command':o[13],'xyz':list(struct.unpack_from('<HHH',o))}

 from syndicate_scene import relocate
 old=c.read(0x80108,116010);ss={e['id']:e for e in Mission(old).summary()['entities']};overlap=tuple(ss['vehicle-0']['position_raw']);new,changes=relocate(old,'person-0',overlap)
 for change in changes:
  off=change['file_offset'];val=bytes.fromhex(change['new_hex']);edit(0x80108+off,val,'explicit diagnostic graph-preserving pedestrian placement overlapping vehicle; no advance')
 assert c.read(0x80108,116010)==new
 setup['overlap_preparation']={'position_raw':overlap,'changed_spans':len(changes),'graph_valid':Mission(new).graph()['valid']}

 for p in [0x127a0,0x127b7,0x12b83,0x32fa0,0x32fa6]:bp(p,False)
 for i in range(2):keys.append(c.rpc('breakpoints.create',{'kind':'memory_change','address':{'space':'linear','offset':f'0x{c.address(0x88124+i):08X}'},'once':False})['breakpoint_id'])
 start=c.rpc('execution.timing')['guest_ticks'];tick=start;beg=time.monotonic()
 while tick-start<15000 and time.monotonic()-beg<35 and len(events)<100:
  rr=c.call('run',{'guest_ms':1000,'timeout_ms':4000,'fast_forward':True});tick=rr['timing_after']['guest_ticks'];g=c.call('regs');pc=int(g['instruction_pointer'],16)-c.mapping[0]['runtime']+0x10000;gg={k:int(v,16) for k,v in g['general'].items()}
  if rr['outcome']=='breakpoint':
   e={'tick':tick,'pc':hex(pc),'victim':entity(c.address(0x88110)),'car':entity(c.address(0x8810e+23554)),'regs':g}
   if pc in [0x127a0,0x127b7]:
    args=struct.unpack('<III',mem(gg['esp'],12));e['source']=entity(args[1]);e['destination']=entity(args[2]);e['caller']=hex(args[0]-c.mapping[0]['runtime']+0x10000)
   elif pc==0x12b83:e['source']=entity(gg['esi']);e['destination']=entity(gg['ebx']);e['mask']=gg['eax']&65535
   elif pc in [0x32fa0,0x32fa6]:e['destination']=entity(gg['eax'])
   events.append(e)
   if e['victim']['hp']<0:break
 setup['guest_start']=start;setup['guest_end']=tick
finally:
 for k in keys:remove(k)
 c.vehicle_interactions.advance_to_frame();s=Mission(c.snapshot()).summary();ss={e['id']:e for e in s['entities']};setup['after']={k:ss[k] for k in ['person-0','person-1','vehicle-0']}
 (folder/'result.json').write_text(json.dumps({'setup':setup,'input_writes':writes,'events':events,'scope':'diagnostic setup and original driving order; one bounded vehicle contact experiment'},indent=2))
 print('contacts',len(events),'beforecar',setup.get('before',{}).get('vehicle-0',{}).get('position_raw'),'aftercar',ss['vehicle-0']['position_raw'],'hp',ss['person-0']['health_raw'],'order',setup.get('order'))
