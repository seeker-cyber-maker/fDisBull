from pathlib import Path
import sys,json,struct,time,traceback
root=Path(__file__).parent;delivery=root/'delivery/fdisbull-native-debugger-cd13636'
sys.path.insert(0,str(delivery/'packages/fdisbull-0.9.0-py3-none-any.whl'))
from fdisbull.project import Project
import fdisbull.debugger
assert '.whl/' in fdisbull.debugger.__file__
project=root/'parking.fdb'
if not project.exists():
 with Project.create(project,root/'game/DINOPARK.EXE') as p:
  for address in ('1000:75bc','38ff:211f','38ff:22ee'):
   p.analyze(start=address,max_instructions=32)
with Project(project) as p, p.debugger(delivery/'backend/native-macos-arm64/dosbox-x',root/'game') as d, (root/'actions.jsonl').open('a',buffering=1) as log:
 print(json.dumps({'ready':True,'run':d.run_id,'module':fdisbull.debugger.__file__}),flush=True)
 for line in sys.stdin:
  req=json.loads(line);op=req['op'];params=req.get('params',{});at=time.time();result=None
  try:
   if op=='close':break
   if op=='peek':
    data=d.memory('0x471a6',length=8);regs=d.registers();result={'hex':data['hex'],'words':struct.unpack('<4H',bytes.fromhex(data['hex'])),'timing':d._timing(),'cs':regs['cs'],'ip':regs['ip'],'project_address':regs['project_address']}
   elif op=='analyze':result=p.analyze(**params)
   elif op=='disasm':result=p.disassembly(**params)
   else:result=getattr(d,op)(**params)
   if op in ('screenshot','trace'):
    p.debug_export(result['artifact'],root/result['name'])
   log.write(json.dumps({'request':req,'result':result,'host_time':at})+'\n')
   if op=='status':shown={k:result[k] for k in ('run','state','mapping') if k in result}
   elif op=='save_state':shown={k:result[k] for k in ('artifact','name','sha256','size')}
   elif op=='script':shown={k:result[k] for k in ('ok','error','completed_steps','artifact','steps')}
   else:shown=result
   print(json.dumps({'ok':True,'result':shown}),flush=True)
  except Exception as e:
   log.write(json.dumps({'request':req,'error':str(e),'host_time':at})+'\n');print(json.dumps({'ok':False,'error':str(e)}),flush=True)
