"""Bounded mission-1 walking through original order production.

This is diagnostic input assistance, not mouse-picking qualification. It never
writes actor positions, actor state, path buffers, registers or instructions.
A candidate route is an experiment plan; only its observed segments are witnessed.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import base64, json, struct, time, uuid
from syndicate_scene import Mission, canonical, digest, TABLES
from agent_map import raw_position, ProgressWatch, checksum, plan_approach
from original_interactions import RejectedInteraction


@dataclass(frozen=True)
class NavigationLimits:
    max_segments: int = 64
    max_observations_per_segment: int = 96
    max_total_observations: int = 1200
    stagnant_observations: int = 12
    wall_seconds: float = 90.0

    def __post_init__(self):
        for key, maximum in (('max_segments',64),('max_observations_per_segment',128),
                             ('max_total_observations',2048),('stagnant_observations',32)):
            n=getattr(self,key)
            if type(n) is not int or not 1<=n<=maximum:raise ValueError('Invalid '+key)
        if type(self.wall_seconds) not in (float,int) or not 0<self.wall_seconds<=120:
            raise ValueError('Invalid wall_seconds')


class NavigationHeld(RuntimeError):
    def __init__(self, message, receipt):
        super().__init__(message);self.receipt=receipt


def validate_route(plan,scene,terrain,limits):
    """Pure preflight. Does not promote a candidate route into known walkability."""
    if plan.get('format')!='syndicate-candidate-route-1' or plan.get('status')!='candidate_requires_validation':
        raise RejectedInteraction('A complete conditional candidate plan is required')
    if plan.get('plan_id')!=checksum({k:v for k,v in plan.items() if k!='plan_id'}):
        raise RejectedInteraction('Route content identity changed')
    if plan.get('source_state_sha256')!=scene['source_state_sha256'] or plan.get('map_number')!=scene['map_number']:
        raise RejectedInteraction('Stale route observation')
    # Recompute the candidate geometry from the current entities and terrain.
    # A self-consistent hash alone is not authority to remove a gate or invent a shortcut.
    rebuilt=plan_approach(scene,terrain,plan.get('target_id'),
                          blocked_cells=tuple(tuple(x) for x in plan.get('blocked_cells',[])),
                          blocked_edges=tuple((tuple(a),tuple(b)) for a,b in plan.get('blocked_edges',[])))
    for key in ('status','actor_id','start_raw','target_raw','path_cells','waypoints_raw',
                'approach_raw','grid_steps','conditional_gates','map_identity'):
        if plan.get(key)!=rebuilt.get(key):raise RejectedInteraction('Route differs from the current candidate model: '+key)
    if plan.get('conditional_gates'):
        raise RejectedInteraction('Route crosses an unqualified gate; no movement request sent')
    if scene['map_number']!=1 or not scene['spatial_index']['valid'] or not scene['vehicle_occupancy']['valid']:
        raise RejectedInteraction('Invalid or unsupported world/graph')
    byid={e['id']:e for e in scene['entities']}
    actor=byid.get(plan.get('actor_id'));target=byid.get(plan.get('target_id'))
    if not actor or actor['id'] not in ('person-0','person-1') or not actor.get('team_member'):
        raise RejectedInteraction('Only the two investigated team slots are admitted')
    if not target or target['id']==actor['id']:raise RejectedInteraction('Missing/distinct target required')
    if actor['status_raw']!=0 or actor['vehicle_membership']['state']!='no-vehicle-membership':
        raise RejectedInteraction('Actor must be stopped and on foot')
    if tuple(actor['position_raw'])!=raw_position(plan['start_raw']) or tuple(target['position_raw'])!=raw_position(plan['target_raw']):
        raise RejectedInteraction('Actor/target position changed')
    points=[raw_position(p) for p in plan.get('waypoints_raw',[])]
    if not points or points[0]!=tuple(actor['position_raw']) or points[-1]!=raw_position(plan['approach_raw']):
        raise RejectedInteraction('Missing/mismatched route endpoints')
    if not 0<=len(points)-1<=limits.max_segments:raise RejectedInteraction('Route exceeds segment budget')
    for i,p in enumerate(points):
        if p[2]!=points[0][2] or p[2]%128 or not 0<p[0]<terrain.nx*256-256 or not 0<p[1]<terrain.ny*256-256:
            raise RejectedInteraction('Unqualified elevation/boundary')
        if not terrain.classify(p[0]//256,p[1]//256,p[2]//128)['candidate']:
            raise RejectedInteraction('Route enters excluded/unresolved terrain')
        if i:
            prev=points[i-1]
            if max(abs(p[0]-prev[0]),abs(p[1]-prev[1]))>512:
                raise RejectedInteraction('Unqualified long movement segment')
            # The planner is four-neighbor; an initial within-cell offset remains exact.
            cells=(abs(p[0]//256-prev[0]//256)+abs(p[1]//256-prev[1]//256))
            if cells>1:raise RejectedInteraction('Route is not locally connected')
    attached=[e for e in scene['entities'] if e.get('owner_id')==actor['id']]
    if any(e['position_raw']!=actor['position_raw'] for e in attached):
        raise RejectedInteraction('Observe pending attachment settlement before a new order')
    return actor,target,points


def read_actor_sample(controller,actor,target,attachment_records):
    """Small coherent read, no time advance. Graph-wide validation is at each stop."""
    before=controller.call('regs')
    def record(entity):
        size=TABLES[entity['family']][1]
        return controller.read(0x80108+entity['source_offset'],size)
    a=record(actor);t=record(target)
    items=[record(e) for e in attachment_records]
    after=controller.call('regs')
    if before['state_revision']!=after['state_revision']:raise RuntimeError('Noncoherent progress sample')
    if a[24]!=1 or t[24]!=TABLES[target['family']][3] or not a[10]&4 or not t[10]&4:
        raise RuntimeError('Actor/target record no longer matches')
    p=list(struct.unpack_from('<HHH',a,4));tp=list(struct.unpack_from('<HHH',t,4))
    attached=all(list(struct.unpack_from('<HHH',b,4))==p and int.from_bytes(b[32:34],'little')==actor['offset_reference'] for b in items)
    return {'position_raw':p,'target_raw':tp,'state_raw':a[25],
            'health_raw':struct.unpack_from('<h',a,20)[0],
            'target_position_raw':list(struct.unpack_from('<HHH',a,46)),
            'target_state_raw':t[25],'target_health_raw':struct.unpack_from('<h',t,20)[0],
            'attachments_settled':attached,'revision':after['state_revision']}


class OriginalNavigation:
    def __init__(self,controller,terrain,private_trials:Path,limits=None):
        if controller.vehicle_interactions is None:
            raise ValueError('A qualified source-bound original interaction profile is required')
        self.c=controller;self.profile=controller.vehicle_interactions;self.terrain=terrain
        self.root=Path(private_trials);self.root.mkdir(parents=True,exist_ok=True)
        self.limits=limits or NavigationLimits();self.held=False

    def follow(self,plan):
        if self.held:raise RejectedInteraction('Previous movement is held; explicit verified recovery is required')
        c=self.c;data,scene=self.profile._checked_state(plan.get('source_state_sha256'))
        if plan.get('observed_run')!=c.cfg['run_id'] or plan.get('runtime_revision')!=c.last_revision:
            raise RejectedInteraction('Route belongs to another run or runtime revision')
        scene=Mission(data).summary(plan.get('actor_id','person-0'))
        actor,target,points=validate_route(plan,scene,self.terrain,self.limits)
        # A plan is valid only under this exact admitted terrain identity.
        identity=getattr(self.terrain,'identity',checksum({'map':getattr(self.terrain,'map_sha256',None),'classes':getattr(self.terrain,'classes_sha256',None),'dimensions':[self.terrain.nx,self.terrain.ny,self.terrain.nz]}))
        if plan['map_identity']!=identity:raise RejectedInteraction('Terrain identity changed')
        if all(p==points[0] for p in points):
            return {'complete':True,'effects':'none-confirmed','state':'already-at-approach','writes':0,'orders':0}
        name='walk-'+uuid.uuid4().hex;folder=self.root/name;folder.mkdir()
        summary={'id':name,'format':'syndicate-original-navigation-1','plan_id':plan['plan_id'],
                 'run':c.cfg['run_id'],'session':c.cfg['session_id'],'source_sha256':c.cfg['main_sha256'],
                 'actor':actor['id'],'target':target['id'],'start_raw':list(points[0]),'approach_raw':list(points[-1]),
                 'target_raw':list(target['position_raw']),'assistance':'diagnostic native selection/mouse/world hit-test; original order and actor motion',
                 'writes':0,'orders':0,'observations':0,'segments':[],'complete':False,'effects':'none-confirmed',
                 'state':'prepared','source_windows':self.profile.windows,'limits':self.limits.__dict__}
        (folder/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
        deadline=time.monotonic()+self.limits.wall_seconds;watch=ProgressWatch(points[-1],tuple(target['position_raw']),stall_limit=self.limits.stagnant_observations)
        def event(x):
            with (folder/'events.jsonl').open('a') as f:f.write(canonical(x)+'\n')
        def write(at,old,new,why):
            if old==new:return
            # Mark uncertainty BEFORE the write call; a lost response must not permit replay.
            summary['effects']='unknown';summary['state']='request-started'
            c.rpc('memory.write',{'address':{'space':'linear','offset':f'0x{c.address(at):08X}'},
                  'expected_sha256':digest(old),'data_base64':base64.b64encode(new).decode()})
            summary['writes']+=1
            if c.read(at,len(new))!=new:raise RuntimeError('Guarded input readback mismatch')
            event({'kind':'diagnostic-input-write','preferred':at,'bytes':len(new),'old_sha256':digest(old),'new_sha256':digest(new),'purpose':why})
        def run_to(preferred,edits=()):
            key=c.rpc('breakpoints.create',{'kind':'execution','address':{'space':'segmented','segment':c.cfg['cs'],'offset':f'0x{c.address(preferred):08X}'},'once':True})['breakpoint_id']
            try:
                for at,old,new,why in edits:write(at,old,new,why)
                result=c.call('run',{'guest_ms':2000,'timeout_ms':3000,'fast_forward':True})
                regs=c.call('regs')
                if regs['segments']['cs']!=c.cfg['cs'] or int(regs['instruction_pointer'],16)!=c.address(preferred):
                    raise RuntimeError('Expected original order boundary was not reached')
                return result,regs
            finally:
                try:c.rpc('breakpoints.delete',{'breakpoint_id':key})
                except Exception as exc:
                    if 'BREAKPOINT_NOT_FOUND' not in str(exc):raise
        try:
            for index,dest in enumerate(points[1:],1):
                if time.monotonic()>deadline:raise RuntimeError('Route wall budget exhausted')
                now=c.snapshot();world=Mission(now).summary(actor['id']);byid={e['id']:e for e in world['entities']}
                current=byid.get(actor['id']);newtarget=byid.get(target['id'])
                if not current or not newtarget or newtarget['position_raw']!=target['position_raw']:
                    raise RuntimeError('Target changed; hold for a fresh plan')
                if current['status_raw']!=0 or current['vehicle_membership']['state']!='no-vehicle-membership':
                    raise RuntimeError('Actor is not stopped/on foot between segments')
                if not world['spatial_index']['valid'] or not world['vehicle_occupancy']['valid']:
                    raise RuntimeError('Invalid graph between segments')
                if current['health_raw']!=actor['health_raw']:raise RuntimeError('Actor health changed; hold')
                attached=[e for e in world['entities'] if e.get('owner_id')==actor['id']]
                if any(e['position_raw']!=current['position_raw'] for e in attached):raise RuntimeError('Attachments not settled')
                if tuple(current['position_raw'])==dest:continue
                if c.read(0x60b3e,4)!=bytes(4) or c.read(0x60b16,2)!=bytes(2) or c.read(0x5e551,1)!=b'\0' or c.read(0x5e120,2)!=b'\1\0':
                    raise RejectedInteraction('Pending input or unsupported selection profile')
                patches=[(0x5e552,bytes([current['slot']])),(0x55390,struct.pack('<HH',300,200)),(0x60b22,struct.pack('<HH',300,200)),(0x60b3f,b'\1')]
                edits=[(at,c.read(at,len(v)),v,'native selection/mouse latch') for at,v in patches]
                self.profile._checked_state(digest(now))
                _,regs=run_to(0x2ddd1,edits)
                if int(regs['general']['esi'],16)!=c.address(0x80108+current['source_offset']):raise RuntimeError('Original producer selected another actor')
                order_addr=int(regs['general']['ebx'],16)
                patches=[(at,bytes(2)) for at in (0x60b12,0x60b14,0x60b1a)]+[(0x60b1c,struct.pack('<HHH',dest[2],dest[1],dest[0]))]
                edits=[(at,c.read(at,len(v)),v,'diagnostic world hit-test') for at,v in patches]
                run_to(0x2dedd,edits)
                response=c.rpc('memory.read',{'address':{'space':'linear','offset':f'0x{order_addr:08X}'},'length':14})
                order=base64.b64decode(response['data_base64'],validate=True)
                if len(order)!=14 or order[13]!=3 or struct.unpack_from('<HHH',order)!=dest:
                    raise RuntimeError('Original movement order mismatched')
                summary['orders']+=1;summary['effects']='applied-confirmed'
                event({'kind':'order-produced','segment':index,'command':3,'destination_raw':list(dest)})
                segment={'index':index,'start_raw':current['position_raw'],'destination_raw':list(dest),'complete':False,'samples':0}
                summary['segments'].append(segment)
                for _ in range(self.limits.max_observations_per_segment):
                    if time.monotonic()>deadline or summary['observations']>=self.limits.max_total_observations:
                        raise RuntimeError('Route observation/wall budget exhausted')
                    run=self.profile.advance_to_frame();sample=read_actor_sample(c,current,newtarget,attached)
                    summary['observations']+=1;segment['samples']+=1
                    decision=watch.observe(sample['position_raw'],revision=sample['revision'],target_raw=sample['target_raw'],
                             waypoint_raw=dest,waypoint_index=index,attachments_settled=sample['attachments_settled'],gate_ready=True)
                    sample.update(kind='progress',segment=index,decision=decision,guest_elapsed_ms=run.get('guest_elapsed_ms'))
                    event(sample)
                    if sample['health_raw']!=actor['health_raw'] or sample['position_raw'][2]!=dest[2]:raise RuntimeError('Actor context/health changed')
                    if sample['target_health_raw']!=target['health_raw'] or (target['family']=='vehicle' and sample['target_state_raw']!=target['status_raw']):raise RuntimeError('Target state/health changed; fresh plan required')
                    if decision in ('target_moved_replan','oscillation_replan','route_regressed_replan','stalled_replan','moving_without_progress_hold','gate_unqualified_hold','held_requires_new_plan'):
                        raise RuntimeError(decision)
                    if sample['state_raw']==0:
                        if tuple(sample['position_raw'])!=dest:raise RuntimeError('Original order stopped short; do not resend')
                        if not sample['attachments_settled']:continue
                        full=Mission(c.snapshot()).summary(actor['id'])
                        if not full['spatial_index']['valid'] or not full['vehicle_occupancy']['valid']:raise RuntimeError('Graph invalid at arrival')
                        segment.update(complete=True,end_raw=sample['position_raw'],stopped=True,spatial_valid=True,attachments_settled=True)
                        break
                if not segment['complete']:raise RuntimeError('Per-segment observation budget exhausted')
            summary.update(state='arrived-at-approach',complete=True,final_game_sha256=digest(c.snapshot()))
            return dict(summary)
        except Exception as exc:
            summary.update(state='held-incomplete',error=str(exc),complete=False)
            if summary['effects']=='none-confirmed':
                raise RejectedInteraction(str(exc)) from exc
            self.held=True
            raise NavigationHeld('Movement held; inspect or restore, never replay its input: '+str(exc),dict(summary)) from exc
        finally:
            (folder/'result.json').write_text(json.dumps(summary,indent=2)+'\n')
