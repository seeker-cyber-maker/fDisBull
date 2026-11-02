"""Verify a candidate live MAIN code base and derive all LE object bases.

Does not search for a process or change guest state. The caller nominates a
code base; every code-side relocation and code byte is then checked. Output is
private and generation-bound. This is not a generic protected-mode loader.
"""
import argparse,base64,collections,hashlib,json,socket
from pathlib import Path
from fdisbull.le import load_le
from syndicate_scene import Mission,digest
from z_provider import MAIN_SHA

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--controller-root',type=Path,required=True);ap.add_argument('--main',type=Path,required=True);ap.add_argument('--code-base',type=lambda s:int(s,0),required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--enable-original-vehicle-actions',action='store_true',help='Opt in to diagnostic input preparations for the bounded original vehicle profile');ap.add_argument('--enable-original-navigation',action='store_true',help='Opt in to bounded diagnostic original walking, using conditional terrain plans');a=ap.parse_args()
 if a.output.exists():raise ValueError('Refuse to overwrite binding')
 root=a.controller_root.resolve();launch=json.loads((root/'launch.json').read_text());original=a.main.read_bytes()
 if digest(original)!=MAIN_SHA:raise ValueError('Foreign source')
 def q(op,args=None,**kw):
  with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
   s.settimeout(30);s.connect(str(root/'control.sock'));s.sendall((json.dumps({'op':op,'args':args or {},**kw})+'\n').encode());r=json.loads(s.makefile('r').readline(8*1024*1024))
  if not r.get('ok'):raise ValueError(r.get('error'))
  return r['result']
 def read(at,n):
  values=[]
  for i in range(0,n,65536):
   r=q('rpc',{'address':{'space':'linear','offset':f'0x{at+i:08X}'},'length':min(65536,n-i)},method='memory.read');values.append(base64.b64decode(r['data_base64'],validate=True))
  return b''.join(values)
 regs=q('regs')
 if regs['cpu_mode']!='protected':raise ValueError('Wait for protected-mode MAIN scene')
 image=load_le(original);code=image.regions[0];live=read(a.code_base,len(code.data));bases={1:a.code_base};seen=collections.defaultdict(set);fixups=image.metadata['le']['fixups']
 for f in fixups:
  if f['source_object']!=1:continue
  value=int.from_bytes(live[f['source_offset']:f['source_offset']+4],'little')
  seen[f['target_object']].add(value-f['target_offset'])
 for obj,values in seen.items():
  if len(values)!=1:raise ValueError(f'Inconsistent code-side base observations for object {obj}')
  value=next(iter(values))
  if obj in bases and value!=bases[obj]:raise ValueError('Nominated code base disagrees with fixups')
  bases[obj]=value
 if set(bases)!={1,2,3,4}:raise ValueError('Missing object base evidence')
 expected=bytearray(code.data)
 for f in fixups:
  if f['source_object']==1:expected[f['source_offset']:f['source_offset']+4]=(bases[f['target_object']]+f['target_offset']).to_bytes(4,'little')
 # This source's startup writes DS here. Do not silently mask other differences.
 ds=int(regs['segments']['ds'],16);offset=0x3d8d0-code.start
 expected[offset:offset+2]=ds.to_bytes(2,'little')
 # Source instructions write an indexed rendering-pointer list at 0x48AD0;
 # the eight observed slots are data in an executable object, not changed code.
 # Keep this bounded: changes in the rest of the zero area remain rejected.
 mutable_offset=0x48ad0-code.start
 changed_data=sum(a!=b for a,b in zip(expected[mutable_offset:mutable_offset+32],live[mutable_offset:mutable_offset+32]))
 expected[mutable_offset:mutable_offset+32]=live[mutable_offset:mutable_offset+32]
 if bytes(expected)!=live:raise ValueError('Runtime executable object differs outside qualified DS/render-pointer data fields')
 objects=[{'id':i,'preferred':r.start,'size':len(r.data),'runtime':bases[i]} for i,r in enumerate(image.regions,1)]
 game=read(bases[4]+0x108,116010);scene=Mission(game).summary()
 if scene['map_number']!=1 or len(scene['team'])!=4:raise ValueError('Expected populated map 1 team')
 if q('regs')['state_revision']!=regs['state_revision']:raise ValueError('Guest advanced during binding')
 helper=live[0x29530-code.start:0x29654-code.start]
 cfg={'main_sha256':MAIN_SHA,'run_id':launch['run'],'session_id':regs['session_id'],'socket':str(root/'control.sock'),
      'launch_receipt':str(root/'launch.json'),'objects':objects,'cs':regs['segments']['cs'],'ds':regs['segments']['ds'],
      'move_helper':{'preferred':0x29530,'length':len(helper),'sha256':digest(helper)},
      'private_action_log':str(root/'scene-actions.jsonl'),
      'binding_evidence':{'code_bytes_checked':len(live),'code_side_fixup_records':sum(f['source_object']==1 for f in fixups),'saved_ds_qualified':True,'observed_render_pointer_data_bytes':32,'differing_render_data_bytes':changed_data,'unexplained_code_object_differences':0,'registered_entities':scene['spatial_index']['entity_count']}}
 if a.enable_original_vehicle_actions or a.enable_original_navigation:
  cfg.update(original_vehicle_source=str(a.main.resolve()),private_vehicle_trials=str(root/'vehicle-trials'))
 if a.enable_original_navigation:cfg.update(enable_original_navigation=True,private_navigation_trials=str(root/'navigation-trials'))
 a.output.write_text(json.dumps(cfg,indent=2));print(json.dumps(cfg['binding_evidence']))
if __name__=='__main__':main()
