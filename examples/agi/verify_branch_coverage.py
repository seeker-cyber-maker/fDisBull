"""Run bounded original-backed synthetic AGI branch probes privately.

Requires the user-owned exact KQ1 edition and qualified DOS backend.
"""
import base64, hashlib, json
from pathlib import Path
from examples.agi.spatial_trial import native_game,read,require
from examples.agi.verify_host import NAMES
from fdisbull.agi import load_logic
from fdisbull.agi_dos import AGIDOSMonitor,FETCH
from fdisbull.agi_host import AGIDOSHostAdapter,capture_state
from fdisbull.agi_lift import lift_logic

# Synthetic diagnostic inputs only; these are not original game states.
CASES = [{'flags': [207, 75],
  'objects': {0: [19, 100, 0, 0, 1], 13: [55, 100, 0, 0, 1]},
  'variables': {0: 17, 1: 32, 40: 20, 41: 2, 94: 1}},
 {'flags': [5, 40, 43, 66, 75, 63, 76, 68, 79, 42],
  'objects': {0: [0, 40, 0, 0, 1], 13: [20, 40, 0, 0, 1]},
  'variables': {0: 7, 1: 8, 5: 1, 107: 1}},
 {'flags': [5, 40, 43, 66, 75, 63, 76, 68, 79, 42],
  'objects': {0: [0, 40, 0, 0, 1], 13: [100, 65, 0, 0, 1]},
  'variables': {0: 7, 1: 10, 40: 255, 94: 255, 107: 255}},
 {'flags': [5],
  'objects': {0: [120, 40, 0, 0, 1], 13: [100, 65, 0, 0, 0]},
  'variables': {0: 17, 1: 18, 40: 35, 41: 2, 94: 255}},
 {'flags': [5, 40, 43, 66, 75, 76, 68, 79, 42],
  'objects': {0: [19, 65, 0, 0, 1], 13: [100, 150, 0, 0, 0]},
  'variables': {0: 17, 1: 32, 40: 25, 41: 2, 107: 255}},
 {'flags': [5, 40, 43, 66, 75, 63, 76, 68, 79, 42],
  'objects': {0: [149, 101, 0, 0, 1], 13: [20, 150, 0, 0, 1]},
  'variables': {0: 17, 1: 32, 5: 1, 40: 24, 41: 1, 94: 255, 107: 255}},
 {'flags': [75],
  'objects': {0: [19, 100, 0, 0, 1], 13: [149, 150, 0, 0, 1]},
  'variables': {0: 17, 1: 32, 40: 20, 41: 2}},
 {'flags': [75, 76, 68, 79],
  'objects': {0: [50, 40, 0, 0, 1], 13: [70, 150, 0, 0, 1]},
  'variables': {0: 7, 1: 8, 40: 24, 94: 255}},
 {'flags': [75],
  'objects': {0: [19, 100, 0, 0, 1], 13: [15, 100, 0, 0, 1]},
  'variables': {0: 17, 1: 32, 40: 20, 41: 2}},
 {'flags': [75, 68, 79],
  'objects': {0: [79, 100, 0, 0, 1], 13: [149, 150, 0, 0, 0]},
  'variables': {40: 20, 94: 1, 107: 1}}]

def run(index, source, backend, root, dialogue_key=None):
 spec=CASES[index];output=root/f'case-{index:02d}'; inputs={name:False if name.startswith('$agi_f') else 0 for name in NAMES}
 for n,value in spec['variables'].items():inputs[f'$agi_v{n}']=value
 for n in spec['flags']:inputs[f'$agi_f{n}']=True
 context={'objects':{str(n):dict(zip(('x','y','prev_x','prev_y','drawn'),values)) for n,values in spec['objects'].items()}}
 resource=load_logic(source/'LOGDIR',source,103,profile='2.917')

 with native_game('kq1',source,output,backend) as (p,d,obs,restore,frame,report,game):
  cs=int(report['resolution']['registers']['segments']['cs'],16);ds=int(report['resolution']['registers']['segments']['ds'],16);base=ds*16; interventions=[]
  def write(addr,data,label):
   old=read(d,addr,len(data));d.call('memory.write',{'address':{'space':'linear','offset':f'0x{addr:08X}'},'expected_sha256':hashlib.sha256(old).hexdigest(),'data_base64':base64.b64encode(data).decode()});require(read(d,addr,len(data))==data,'write mismatch');interventions.append({'field':label,'old':old.hex(),'new':data.hex()});return old
  def bp(off):return d.call('breakpoints.create',{'kind':'execution','once':False,'address':{'space':'segmented','segment':f'0x{cs:04X}','offset':f'0x{off:08X}'}})['breakpoint_id']
  def stop(off):
   o=d.run(guest_ms=5000,timeout_ms=10000,fast_forward=True,stop_on_hook=True);r=d.registers();require(o['outcome']=='breakpoint' and int(r['segments']['cs'],16)==cs and int(r['instruction_pointer'],16)==off,'unexpected preparation stop');return r
  def trial(first):
   if first:
    ident=bp(0x125a);r=stop(0x125a);addr=base+(int(r['general']['esi'],16)&65535);require(read(d,addr-1,2)==bytes([22,101]),'unexpected caller');old=write(addr,b'\x67','caller operand');d.call('breakpoints.delete',{'breakpoint_id':ident})
    ident=bp(0x1303);stop(0x1303);d.call('breakpoints.delete',{'breakpoint_id':ident});write(addr,old,'caller operand restore')
    f=read(d,base+0x109,1)[0];write(base+0x109,bytes([f|4]),'f5 initialize')
   else:
    r=d.registers();require(int(r['segments']['cs'],16)==cs and int(r['instruction_pointer'],16)==0x1306,'not returned')
    sp=int(r['segments']['ss'],16)*16+(int(r['general']['esp'],16)&65535);require(read(d,sp,2)==read(d,base+0x979,2),'return stack mismatch')
    d.call('state.set_register',{'register':'EIP','value':0x1303});require(int(d.registers()['instruction_pointer'],16)==0x1303,'IP write mismatch');interventions.append({'field':'instruction pointer','old':'1306','new':'1303','purpose':'new diagnostic invocation after completion'})
    state=dict(inputs);state['$agi_f15']=dialogue_key is None
    for name,val in state.items():
     n=int(name[6:])
     if name.startswith('$agi_v'):write(base+9+n,bytes([val]),name)
     else:
      a=base+0x109+n//8;mask=0x80>>(n%8);f=read(d,a,1)[0];write(a,bytes([(f|mask) if val else f&~mask]),name)
    table=int.from_bytes(read(d,base+0x963,2),'little')
    for n in (0,13):
     obj=context['objects'][str(n)];a=base+table+n*43
     for key,offset in (('x',3),('y',5),('prev_x',22),('prev_y',24)):
      write(a+offset,int(obj[key]).to_bytes(2,'little',signed=True),f'object{n}.{key}')
     # Explicit diagnostic frame intervention, never represented as gameplay.
     flags=int.from_bytes(read(d,a+37,2),'little'); flags=(flags|1) if obj['drawn'] else (flags&~1)
     write(a+37,flags.to_bytes(2,'little'),f'object{n}.drawn')
   record=int.from_bytes(read(d,base+0x979,2),'little');desc=read(d,base+record,8);codeoff=int.from_bytes(desc[4:6],'little');require(desc[2]==103 and int.from_bytes(desc[6:8],'little')==codeoff and read(d,base+codeoff,len(resource.code))==resource.code,'logic mismatch')
   ident=bp(FETCH);stop(FETCH);d.call('breakpoints.delete',{'breakpoint_id':ident})
   monitor=AGIDOSMonitor(d,resource,cs=cs,ds=ds,code_offset=codeoff);state=capture_state(monitor,NAMES);projection=lift_logic(resource,initial_state=state,control_flow='compact',effect_profile='agi-2.917');adapter=AGIDOSHostAdapter(monitor,projection,viewdir=source/'VIEWDIR',volume_dir=source,dialogue_key=None if first else dialogue_key);result=adapter.run();require(adapter.readback()==result,'readback mismatch');return result
  init=trial(True);(output/'initial.private.json').write_text(json.dumps(init));require(init['status']=='verified','initial trial not verified')
  result=trial(False);(output/'trial.private.json').write_text(json.dumps(result));(output/'interventions.private.json').write_text(json.dumps(interventions));report['host_trial']=result
  for completion in result['host_completions']:
   waiting=completion.get('dialogue',{}).get('waiting_frame')
   if waiting:p.debug_export(waiting['artifact'],output/f'dialogue-{completion["source_offset"]}-waiting.png')
  print(json.dumps({'case':index,'status':result['status'],'error':result.get('error'),'count':len(result['source_offsets']),'differences':len(result['differences']),'operations':[x['operation'] for x in result['host_completions']]}),flush=True)
def main():
 import argparse
 from types import SimpleNamespace
 from examples.agi.verify_host import verify
 from fdisbull.agi_coverage import aggregate_native_coverage
 parser=argparse.ArgumentParser(description='Original-backed diagnostic KQ1 branch coverage; writes private outputs only')
 parser.add_argument('--source',type=Path,required=True);parser.add_argument('--backend',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
 parser.add_argument('--dialogue-key',choices=('enter','escape'),default=None,help='send a qualified key to blocking original dialogue')
 args=parser.parse_args();source=args.source.resolve();backend=args.backend.resolve();root=args.output.resolve()
 checkout=Path(__file__).resolve().parents[2]
 if root.exists() or root in source.parents or source in root.parents or root==checkout or checkout in root.parents:
  raise ValueError('output must be a fresh private directory outside source and checkout')
 root.mkdir(parents=True)
 for index in range(len(CASES)):run(index,source,backend,root,args.dialogue_key)
 # Two independently authored probes add the print/erase paths not guaranteed
 # by the ten frame variants. Each uses a fresh private native game copy.
 extra={'print':('dialogue-'+args.dialogue_key if args.dialogue_key else 'print'),
        'erase':('dialogue-erase' if args.dialogue_key=='enter' else 'erase')}
 for name,case in extra.items():
  verify(SimpleNamespace(source=source,backend=backend,output=root/name,case=case))
 receipts=[]
 for directory in sorted(root.glob('case-*')):
  for name in ('initial.private.json','trial.private.json'):
   receipts.append(json.loads((directory/name).read_text()))
 for name in ('print','erase'):
  folder=root/name;receipts.append(json.loads((folder/'trial.private.json').read_text()))
  report=json.loads((folder/'result.json').read_text())
  if name=='erase':receipts.append(report['setup_trial'])
 resource=load_logic(source/'LOGDIR',source,103,profile='2.917')
 first=receipts[0];projection=lift_logic(resource,initial_state=first['model']['state'],control_flow='compact',effect_profile='agi-2.917')
 summary=aggregate_native_coverage(projection,receipts)
 summary['dialogue_key']=args.dialogue_key
 summary['standalone_cases']=extra
 (root/'coverage.json').write_text(json.dumps(summary,indent=2)+'\n')
 print(json.dumps(summary))
 if not summary['complete']:raise SystemExit(2)

if __name__=='__main__':main()
