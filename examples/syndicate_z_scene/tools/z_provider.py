"""JSON-lines Z provider over a pinned Syndicate diagnostic controller.

Read observations do not advance guest time. Actions are an explicit, bounded
research subset. Snapshot mode is read-only and never pretends to execute DOS.
"""
from __future__ import annotations
import argparse,base64,hashlib,json,socket,struct,sys,time
from pathlib import Path
from syndicate_scene import Mission,Terrain,relocate,digest,canonical
from agent_map import CandidateTerrain,render_ascii,plan_approach,destination_decision

MAIN_SHA='bfbed760ab2def1fbe9f73588dc5a24747826c9b7660d615b02a8847d92bf078'
WAYPOINTS={
 'car approach':(60.5,36.5,2), 'mission target approach':(64.5,31.5,2),
 'guard approach':(75.5,32.5,2), 'door approach':(73.5,34.5,2),
 'roof probe':(64.5,30.5,6), 'start position':(91.703125,41.671875,2)}

class Controller:
    def __init__(self,config:dict):
        self.cfg=config
        if config['main_sha256']!=MAIN_SHA:raise ValueError('Unsupported original source identity')
        self.mapping=config['objects'];self.sock=config['socket'];self.counter=0
        self.log=Path(config['private_action_log']);self.log.parent.mkdir(parents=True,exist_ok=True)
    def call(self,op,args=None,**kw):
        q={'op':op,'args':args or {},**kw}
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
            s.settimeout(30);s.connect(self.sock);s.sendall((canonical(q)+'\n').encode())
            line=s.makefile('r').readline(8*1024*1024)
            reply=json.loads(line)
        if not reply.get('ok'):raise RuntimeError(reply.get('error','controller request failed'))
        return reply['result']
    def rpc(self,method,args=None):return self.call('rpc',args,method=method)
    def address(self,p):
        for o in self.mapping:
            if o['preferred']<=p<o['preferred']+o['size']:return o['runtime']+p-o['preferred']
        raise ValueError('Unmapped preferred address')
    def read(self,p,n):
        out=[]
        for offset in range(0,n,65536):
            r=self.rpc('memory.read',{'address':{'space':'linear','offset':f'0x{self.address(p+offset):08X}'},'length':min(65536,n-offset)})
            out.append(base64.b64decode(r['data_base64'],validate=True))
        data=b''.join(out)
        if len(data)!=n:raise ValueError('Incomplete native memory read')
        return data
    def validate(self):
        if 'launch_receipt' in self.cfg and json.loads(Path(self.cfg['launch_receipt']).read_text())['run']!=self.cfg['run_id']:
            raise ValueError('Controller generation changed')
        state=self.rpc('session.status')
        # Controller identity comes from its session status, not numerical addresses alone.
        session=state.get('session',state)
        if session.get('session_id',state.get('session_id')) != self.cfg['session_id']:raise ValueError('Foreign debugger session')
        regs=self.call('regs')
        if regs['cpu_mode']!='protected' or regs['segments']['cs']!=self.cfg['cs'] or regs['segments']['ds']!=self.cfg['ds']:
            raise ValueError('Current mode/selector binding differs from qualified mission context')
        window=self.cfg['move_helper']
        if digest(self.read(window['preferred'],window['length']))!=window['sha256']:raise ValueError('Stale module/load or changed move-helper bytes')
        return regs
    def snapshot(self):
        before=self.validate()
        data=self.read(0x80108,116010)
        after=self.call('regs')
        if before['state_revision']!=after['state_revision']:raise ValueError('Runtime advanced during observation')
        self.last_revision=after['state_revision']
        if struct.unpack_from('<H',data,0x1bd28)[0]!=1:raise ValueError('Provider currently qualifies mission/map 1 only')
        return data
    def record(self,event):
        with self.log.open('a') as f:f.write(canonical({'at':time.time(),**event})+'\n')
    def teleport(self,expected,entity_id,pos):
        self.validate();old=self.read(0x80108,116010)
        if digest(old)!=expected:raise ValueError('Stale scene snapshot; no writes')
        new,changes=relocate(old,entity_id,pos)
        # No execution requests occur during the grouped guarded writes.
        written=0
        try:
            for c in changes:
                previous=bytes.fromhex(c['old_hex']);value=bytes.fromhex(c['new_hex'])
                self.rpc('memory.write',{'address':{'space':'linear','offset':f'0x{self.address(0x80108+c["file_offset"]):08X}'},
                                      'expected_sha256':digest(previous),'data_base64':base64.b64encode(value).decode()})
                written+=1
            observed=self.read(0x80108,116010)
            if observed!=new:raise ValueError('Grouped relocation readback mismatch')
            graph=Mission(observed).graph()
            if not graph['valid']:raise ValueError('Post-relocation spatial index is incoherent')
            self.record({'operation':'assisted-teleport','entity':entity_id,'destination_raw':list(pos),
                         'snapshot_before':digest(old),'snapshot_after':digest(new),'changes':changes,
                         'source_helper_binding':self.cfg['move_helper'],'state':'committed','guest_time_advanced':False})
            samples=[];okay=False;deadline=time.monotonic()+10
            for attempt in range(10):
                if time.monotonic()>deadline:break
                run=self.call('run',{'guest_ms':200,'timeout_ms':1000,'fast_forward':True})
                settled=self.read(0x80108,116010);world=Mission(settled);view=world.summary(entity_id)
                chosen=next(e for e in view['entities'] if e['id']==entity_id)
                attachments=[e for e in view['entities'] if e.get('owner_ref')==chosen['offset_reference']]
                okay=(chosen['position_raw']==list(pos) and all(e['position_raw']==chosen['position_raw'] for e in attachments))
                sample={'operation':'teleport-settle','snapshot_sha256':digest(settled),'position':chosen['position_raw'],
                        'owned_items':len(attachments),'attachments_followed':okay,'graph':view['spatial_index'],'run':run}
                self.record(sample);samples.append(sample)
                if okay:break
                if chosen['position_raw']!=list(pos):break
            if not okay:raise RuntimeError('Relocation applied but bounded original updates did not settle the requested position/attachments')
            return {'changed_spans':written,'snapshot_sha256':digest(settled),'owned_items':len(attachments),
                    'settle_windows':len(samples),'guest_elapsed_ms':sum(x['run'].get('guest_elapsed_ms',0) for x in samples)}
        except BaseException as exc:
            self.record({'operation':'assisted-teleport','state':'unknown-partial','written_spans':written,'error':str(exc)})
            raise RuntimeError('Relocation uncertain; keep guest paused and explicitly restore a qualified checkpoint') from exc

class SceneBackend:
    def __init__(self,controller=None,snapshot=None,terrain=None):
        self.controller=controller;self.static=snapshot;self.terrain=terrain;self.selected='person-0';self.epoch=0;self.held=False
        self.session_token=controller.cfg['run_id'] if controller else 'offline-observation'
    def state(self):
        if self.held:raise ValueError('Provider held after uncertain action; no further guest actions')
        if self.controller:
            s=Mission(self.controller.snapshot()).summary(self.selected)
            s['runtime_revision']=self.controller.last_revision
        else:s=json.loads(json.dumps(self.static))
        return s
    def token(self,s):return digest(canonical({'state':s['source_state_sha256'],'selected':self.selected,'epoch':self.epoch,'run':self.session_token,'runtime_revision':s.get('runtime_revision')}).encode())
    def observe(self):
        s=self.state();byid={e['id']:e for e in s['entities']};sel=byid[s['selected']]
        counts=s['counts'];nearest=s['nearest']
        inventory=[]
        objects=[]
        def add(ident,label,description,aliases=None,verbs=None):objects.append({'id':ident,'label':label,'description':description,'aliases':aliases or [],'verbs':verbs or []})
        descriptions=[]
        for e in s['team']:
            descriptions.append(f"{e['id']}: ({e['position'][0]:.3f}, {e['position'][1]:.3f}, z={e['position'][2]:g}); health raw {e['health_raw']}; status {e['status_raw']}; vehicle refs {e['vehicle_refs']}")
        add('team','team','\n'.join(descriptions)+ '\nHealth/life/drug semantics remain partially recovered.','squad'.split())
        for category in ['civilian','police','guard','agent','vehicle','door']:
            n=nearest.get(category);count=counts.get(category,0)
            text=f'{count} registered {category} entities in this entire mission snapshot, not a visible/alive count.'
            if n:text+=f" Nearest other: {n['id']} at ({n['position'][0]:.3f}, {n['position'][1]:.3f}, z={n['position'][2]:g}); XY straight-line distance {n['distance_xy']:.3f} tiles. Route not verified."
            else:text+=' No matching registered entity in this snapshot; future spawns are not excluded.'
            aliases={'vehicle':['cars','car','nearest car','nearest vehicle'],'door':['gates','gate','car gate','nearest gate','nearest door']}.get(category,[category,category+'s','nearest '+category])
            if category=='vehicle':text+=' Boarding point, lock/gate state and occupant interpretation are unqualified.'
            if category=='door':text+=' Door-class records are candidate portals. Open/closed and vehicle-gate relationships are not yet recovered.'
            add('summary-'+category,category+' summary',text,aliases)
        for e in s['entities']:
            if e['family'] in ('effect','weapon') or e['category']=='tree':continue
            critical=e['mission_critical'];label=f"{e['category']} {e['slot']}"+(' [MISSION TARGET]' if critical else '')
            aliases=[e['id']]
            if critical:aliases+=['mission target','special target','objective target']
            if e.get('team_member'):aliases+=['team agent '+str(e['slot']+1)]
            desc=f"{e['id']}: {e['category']}; position {e['position']}; health raw {e['health_raw']}; status/class byte {e['status_raw']}. "
            if critical:desc+='Explicit objective reference points here; identity survives other civilian classifications. '
            if e['family']=='vehicle':desc+='Occupancy and boarding semantics unqualified. '
            if e['family']=='object':desc+='Portal behavior/blocked state not inferred from drawing or subtype alone. '
            if e['family']=='person':desc+=f"Vehicle references {e['vehicle_refs']}; life state unknown. "
            add(e['id'],label,desc,aliases,['focus'] if e.get('team_member') and self.controller else [])
        for e in s['entities']:
            if e.get('owner_id')==sel['id']:
                inventory.append({'id':'inventory-'+e['id'],'label':e['id']+' (weapon class '+str(e['status_raw'])+')',
                                  'aliases':[e['id']],'description':f"Source-linked owned weapon; raw ammo/health field {e['health_raw']}. Equipped-weapon semantics remain unqualified.",'verbs':[]})
        obj=s['objectives']
        add('objectives','objectives', '\n'.join(f"{o['id']}: type {o['type_raw']}, state {o['state_raw']}, target {o['target_id'] or 'none'}" for o in obj)+ '\nEight source-consumer slots; type-zero satisfied slots are not eight distinct missions.', ['mission','targets'])
        map_text=self.local_map(s) if self.terrain else 'No terrain loaded. '
        add('map','map',map_text+'\nMission map: 128 x 96 tiles, 12 height layers. Coordinates are world tiles, not screen pixels. Conditional flat-surface graph does not qualify doors, slopes, dynamic collisions, line-of-sight or a walked route. Consult mission-map.html.',['room','accessibility'])
        if self.terrain:
            for category,label in [('vehicle','car'),('civilian','mission target')]:
                candidates=[e for e in s['entities'] if e['category']==category and
                            (label!='mission target' or e.get('mission_critical'))]
                if candidates:
                    # Reuse exact coordinates for selection, not formatted text.
                    chosen=min(candidates,key=lambda e:(sum((e['position_raw'][i]-sel['position_raw'][i])**2 for i in (0,1)),e['id']))
                    route=plan_approach(s,self.terrain,chosen['id'])
                    add('route-'+label.replace(' ','-'),'route to '+label,
                        canonical(route),['path to '+label,'route '+label])
        for name,pos in WAYPOINTS.items():
            add('waypoint-'+name.replace(' ','-'),name,f'Diagnostic placement waypoint {list(pos)}. Prior placement persisted through 200 guest ms; this does not prove walking access, visibility, stairs, boarding or permission to enter a vehicle.',[],['teleport'] if self.controller else [])
        add('world','world','Request 200 emulated milliseconds of original mission execution; actual elapsed time may overshoot. AI and time-dependent effects can change the world.',[],['advance'] if self.controller else [])
        description=(f"Diagnostic global view. Focus {s['selected']} at ({sel['position'][0]:.3f}, {sel['position'][1]:.3f}, z={sel['position'][2]:g}). "
                     f"Team {len(s['team'])}; civilians {counts.get('civilian',0)}; police {counts.get('police',0)}; guards {counts.get('guard',0)}; cars {counts.get('vehicle',0)}; doors {counts.get('door',0)}. "
                     "Special objective targets are listed independently of character class. Nearest means XY geometric distance, not travel cost. "
                     "Reads are passive; teleport is diagnostic, not walking. This is not a fair-play visibility projection.")
        return {'complete':True,'session_token':self.session_token,
                'context':{'id':'syndicate-mission-1','token':self.token(s),'title':'Syndicate | Mission 1 spatial scene','description':description},
                'coverage':{'partial':True},'objects':objects,'inventory':inventory}
    def local_map(self,s):
        # ASCII is a projection. Full game-unit coordinates stay authoritative.
        return render_ascii(s,self.terrain)['text']
    def act(self,a):
        def reject(msg):return {'status':'rejected','complete':True,'effects':'none-confirmed','message':msg}
        if not self.controller:return reject('Offline snapshot is read-only; no original execution occurred.')
        s=self.state()
        if a.get('context_token')!=self.token(s):return reject('Stale context; no action sent.')
        if a.get('item') is not None:return reject('Item actions are not qualified.')
        verb,target=a.get('verb'),a.get('target')
        if verb=='focus' and target in [e['id'] for e in s['team']]:
            self.selected=target;self.epoch+=1
            return {'status':'success','complete':True,'effects':'applied-confirmed','message':'Observer focus changed; native UI selection was not changed.'}
        if verb=='advance' and target=='world':
            self.controller.call('run',{'guest_ms':200,'timeout_ms':10000,'fast_forward':True});self.epoch+=1
            return {'status':'success','complete':True,'effects':'applied-confirmed','message':'Original world advanced for the bounded interval; refreshed state requires a new observation.'}
        points={'waypoint-'+k.replace(' ','-'):v for k,v in WAYPOINTS.items()}
        if verb!='teleport' or target not in points:return reject('Unsupported action; no diagnostic writes.')
        pos=points[target];raw=(round(pos[0]*256),round(pos[1]*256),round(pos[2]*128))
        chosen=next(e for e in s['entities'] if e['id']==self.selected)
        attachments=[e for e in s['entities'] if e.get('owner_id')==self.selected]
        settled=all(e['position_raw']==chosen['position_raw'] for e in attachments)
        decision=destination_decision(chosen['position_raw'],raw,attachments_settled=settled)
        if decision=='already_at_exact_destination':
            return {'status':'success','complete':True,'effects':'none-confirmed',
                    'message':'Already at the exact raw destination with attachments settled; no writes or guest-time advance.'}
        if decision=='observe_unsettled_attachments':
            return reject('Position already reached but attachments are unsettled. Observe the committed action; do not replay relocation writes.')
        if self.terrain and not self.terrain.classify(int(pos[0]),int(pos[1]),int(pos[2]))['candidate']:
            return reject('Waypoint does not satisfy the admitted flat-support/clearance model.')
        try:
            result=self.controller.teleport(s['source_state_sha256'],self.selected,raw);self.epoch+=1
        except Exception as exc:
            self.held=True
            return {'status':'incomplete','complete':False,'effects':'unknown','recovery_required':True,'message':str(exc)}
        return {'status':'success','complete':True,'effects':'applied-confirmed','assistance':{'kind':'spatial','mode':'assisted'},
                'message':f"Diagnostic relocation of {self.selected} to {list(pos)} committed with coherent spatial links; original updates settled the agent and attached items in {result['settle_windows']} bounded window(s), observed {result['guest_elapsed_ms']} guest ms. Walking access is not certified."}
    def save(self,slot='live'):return {'complete':False,'status':'unsupported','message':'Automatic live-turn checkpoint certificates not implemented; use explicit owned native checkpoint workflow.'}
    def load(self,checkpoint='live'):return {'complete':False,'status':'unsupported','message':'No automatic checkpoint replay.'}

def main():
    ap=argparse.ArgumentParser();src=ap.add_mutually_exclusive_group(required=True)
    src.add_argument('--live-config',type=Path);src.add_argument('--snapshot',type=Path)
    maps=ap.add_mutually_exclusive_group()
    maps.add_argument('--decoded-data',type=Path)
    maps.add_argument('--map-model',type=Path,help='Read-only semantic terrain for the recorded snapshot')
    args=ap.parse_args()
    terrain=None
    if args.decoded_data:terrain=Terrain((args.decoded_data/'MAP01.DAT').read_bytes(),(args.decoded_data/'COL01.DAT').read_bytes())
    snapshot=json.loads(args.snapshot.read_text()) if args.snapshot else None
    if args.map_model:
        if args.live_config:raise ValueError('Semantic map-model input is qualified for recorded snapshot mode only')
        model=json.loads(args.map_model.read_text())
        if model['map_number']!=snapshot['map_number'] or model['scene']['source_state_sha256']!=snapshot['source_state_sha256']:
            raise ValueError('Semantic terrain/snapshot binding differs')
        terrain=CandidateTerrain(model)
    backend=SceneBackend(Controller(json.loads(args.live_config.read_text())) if args.live_config else None,
                         snapshot,terrain)
    for line in sys.stdin:
        if len(line)>65536:raise ValueError('Request limit exceeded')
        try:
            q=json.loads(line);op=q.get('op')
            if op=='observe':r=backend.observe()
            elif op=='act':r=backend.act(q['action'])
            elif op=='save':r=backend.save(q.get('slot','live'))
            elif op=='load':r=backend.load(q.get('checkpoint','live'))
            else:r={'complete':False,'error':'Unknown operation'}
        except Exception as exc:r={'complete':False,'error':str(exc)}
        print(canonical(r),flush=True)
if __name__=='__main__':main()
