"""Opt-in, original-backed mission-1 vehicle interaction research profile.

The original input/order producer and actor updater do the boarding/exit. This
adapter supplies diagnostic input latches, native observer selection and a
vehicle hit-test reference. It does NOT write actor state, occupant links,
position, original instructions, or CPU registers. It is assisted execution,
not physical mouse-input qualification or a generic game-action API.
"""
from __future__ import annotations
import base64,hashlib,json,struct,time,uuid
from pathlib import Path
from syndicate_scene import Mission,digest,canonical

SOURCE_SHA='bfbed760ab2def1fbe9f73588dc5a24747826c9b7660d615b02a8847d92bf078'
# Half-open native code windows. Never includes the mutable render-pointer table.
WINDOWS=((0x2d610,0x2e480),(0x29360,0x29388),(0x32300,0x32560),(0x394a0,0x394e0))

class RejectedInteraction(ValueError):
    """No guest write or execution request has been made."""

class OriginalVehicleInteractions:
    def __init__(self,controller,source:Path,private_trials:Path):
        from fdisbull.le import load_le
        original=Path(source).read_bytes()
        if digest(original)!=SOURCE_SHA or controller.cfg.get('main_sha256')!=SOURCE_SHA:
            raise ValueError('Vehicle profile source identity mismatch')
        controller.validate()
        if controller.cfg.get('binding_evidence',{}).get('unexplained_code_object_differences')!=0:
            raise ValueError('A qualified whole-object binding is required')
        image=load_le(original);code=image.regions[0]
        bases={x['id']:x['runtime'] for x in controller.mapping}
        expected=bytearray(code.data)
        for f in image.metadata['le']['fixups']:
            if f['source_object']==1:
                expected[f['source_offset']:f['source_offset']+4]=(bases[f['target_object']]+f['target_offset']).to_bytes(4,'little')
        self.windows=[]
        for start,end in WINDOWS:
            wanted=bytes(expected[start-code.start:end-code.start])
            if controller.read(start,end-start)!=wanted:raise ValueError('Interaction code window mismatch')
            self.windows.append({'preferred':start,'length':end-start,'sha256':digest(wanted)})
        self.controller=controller;self.root=Path(private_trials)
        self.root.mkdir(parents=True,exist_ok=True)

    def advance_to_frame(self):
        """Explicit action-time advancement to a source-verified observation boundary.

        Never called from a passive observation. A paused timer can use other
        selectors, so verify session/load code independently, then require the
        original foreground entry. No register or mode is forced.
        """
        c=self.controller
        status=c.rpc('session.status');session=status.get('session',status)
        if session.get('session_id',status.get('session_id'))!=c.cfg['session_id']:
            raise RuntimeError('Foreign session before frame wait')
        if 'launch_receipt' in c.cfg and json.loads(Path(c.cfg['launch_receipt']).read_text())['run']!=c.cfg['run_id']:
            raise RuntimeError('Controller generation changed before frame wait')
        w=self.windows[0]
        if digest(c.read(w['preferred'],w['length']))!=w['sha256']:
            raise RuntimeError('Changed frame-entry source before wait')
        key=c.rpc('breakpoints.create',{'kind':'execution','address':{'space':'segmented',
                 'segment':c.cfg['cs'],'offset':f'0x{c.address(0x2d610):08X}'},'once':True})['breakpoint_id']
        try:
            result=c.call('run',{'guest_ms':2000,'timeout_ms':3000,'fast_forward':True})
            regs=c.call('regs')
            if (regs['cpu_mode']!='protected' or regs['segments']['cs']!=c.cfg['cs']
                    or regs['segments']['ds']!=c.cfg['ds']
                    or int(regs['instruction_pointer'],16)!=c.address(0x2d610)):
                raise RuntimeError('Qualified foreground frame boundary not reached')
            return result
        finally:
            try:c.rpc('breakpoints.delete',{'breakpoint_id':key})
            except Exception as exc:
                # A fired once-watch is deleted by the backend itself. Do not turn
                # this expected cleanup result into uncertain target completion.
                if 'BREAKPOINT_NOT_FOUND' not in str(exc):raise

    def _checked_state(self,expected):
        c=self.controller;c.validate()
        for w in self.windows:
            if digest(c.read(w['preferred'],w['length']))!=w['sha256']:
                raise RejectedInteraction('Source window changed; no request')
        data=c.snapshot()
        if digest(data)!=expected:raise RejectedInteraction('Stale GAME observation; no request')
        scene=Mission(data).summary()
        if not scene['vehicle_occupancy']['valid']:
            raise RejectedInteraction('Unqualified occupant graph; no request')
        return data,scene

    def perform(self,expected,actor_id,vehicle_id,verb):
        """One bounded request; uncertain results never automatically replay.

        Only the two observed team slots and selected subtype-13 car are exposed.
        The actor must already be near the car. No implicit teleport occurs.
        A caller must hold subsequent writes if this method raises after writes.
        """
        if verb not in ('board','exit'):raise RejectedInteraction('Unsupported vehicle verb')
        c=self.controller;data,scene=self._checked_state(expected)
        entities={e['id']:e for e in scene['entities']}
        actor=entities.get(actor_id);car=entities.get(vehicle_id)
        if actor_id not in ('person-0','person-1') or not actor or not actor.get('team_member'):
            raise RejectedInteraction('Only qualified team slots 0 and 1 are admitted')
        if vehicle_id!='vehicle-0' or not car or car['status_raw']!=13 or car['flags'][1]&1:
            raise RejectedInteraction('Only the admitted mission-1 subtype-13 car is qualified')
        membership=actor['vehicle_membership'];occupants=car['occupancy']['occupants']
        if verb=='board':
            if membership=={'state':'occupant','vehicle_id':vehicle_id}:
                return {'state':'already-boarded','writes':0,'complete':True,'effects':'none-confirmed'}
            if membership['state']!='no-vehicle-membership' or actor['status_raw']!=0:
                raise RejectedInteraction('Actor has another or unresolved order/membership')
            delta=[abs(a-b) for a,b in zip(actor['position_raw'],car['position_raw'])]
            if max(delta[:2])>256 or delta[2]!=0:
                raise RejectedInteraction('Move to a separately qualified nearby approach first')
        elif membership!={'state':'occupant','vehicle_id':vehicle_id}:
            raise RejectedInteraction('Actor is not a qualified occupant of this car')
        # Preflight every input field, expected actor and private destination before
        # a first target write. Do not repeat the earlier partial-preflight mistake.
        if c.read(0x60b3e,4)!=b'\0'*4:
            raise RejectedInteraction('Pending/held mouse input; no latch replacement')
        if c.read(0x60b16,2)!=b'\0\0' or c.read(0x5e551,1)!=b'\0':
            raise RejectedInteraction('Unqualified profile or team-base selection')
        old_selected=c.read(0x5e552,1)
        if old_selected[0]>3:raise RejectedInteraction('Invalid selected team slot')
        if c.read(0x5e120,2)!=b'\1\0':
            raise RejectedInteraction('Only the observed single-agent order mode is admitted')
        patches=[(0x5e552,bytes([actor['slot']])),(0x55390,struct.pack('<HH',300,200)),
                 (0x60b22,struct.pack('<HH',300,200)),(0x60b3f,b'\1')]
        edits=[(at,c.read(at,len(new)),new) for at,new in patches]
        trial_id='vehicle-'+uuid.uuid4().hex;folder=self.root/trial_id;folder.mkdir(exist_ok=False)
        journal={'id':trial_id,'source_sha256':SOURCE_SHA,'run':c.cfg['run_id'],
                 'verb':verb,'actor':actor_id,'vehicle':vehicle_id,'before_game_sha256':digest(data),
                 'assistance':'diagnostic native selection, mouse latches and vehicle hit-test',
                 'windows':self.windows,'events':[],'state':'prepared'}
        def event(item):
            journal['events'].append(item)
            # Append-only event stream; final summary is created once below.
            with (folder/'events.jsonl').open('a') as f:f.write(canonical(item)+'\n')
        with (folder/'preparation.json').open('x') as f:f.write(json.dumps(journal,indent=2)+'\n')
        bps=[];written=0;began=False
        def bp(at):
            key=c.rpc('breakpoints.create',{'kind':'execution','address':{'space':'segmented',
                  'segment':c.cfg['cs'],'offset':f'0x{c.address(at):08X}'},'once':True})['breakpoint_id']
            bps.append(key);return key
        def run():return c.call('run',{'guest_ms':2000,'timeout_ms':3000,'fast_forward':True})
        def write(at,old,new,why):
            nonlocal written,began
            if old==new:return
            began=True
            r=c.rpc('memory.write',{'address':{'space':'linear','offset':f'0x{c.address(at):08X}'},
                 'expected_sha256':digest(old),'data_base64':base64.b64encode(new).decode()})
            written+=1
            if c.read(at,len(new))!=new:raise RuntimeError('Guarded input readback failed')
            event({'kind':'diagnostic-write','preferred':at,'bytes':len(new),
                   'old_sha256':digest(old),'new_sha256':digest(new),'purpose':why,
                   'native_revision':r.get('state_revision')})
        try:
            # Final scene/token validation after preflight reads, still no guest advance.
            self._checked_state(expected)
            bp(0x2ddd1)
            for at,old,new in edits:write(at,old,new,'native selection/input latch')
            hit=run();regs=c.call('regs');event({'kind':'producer-entry','result':hit,'registers':regs})
            if int(regs['instruction_pointer'],16)!=c.address(0x2ddd1) or regs['segments']['cs']!=c.cfg['cs']:
                raise RuntimeError('Producer entry not observed; input effect unresolved')
            if int(regs['general']['esi'],16)!=c.address(0x80108+actor['source_offset']):
                raise RuntimeError('Original producer chose another actor; held before target selection')
            new=struct.pack('<H',car['offset_reference'])
            write(0x60b12,c.read(0x60b12,2),new,'diagnostic selected-vehicle hit-test')
            order_address=int(regs['general']['ebx'],16)
            bp(0x2de1e)
            emitted=run();regs=c.call('regs')
            if int(regs['instruction_pointer'],16)!=c.address(0x2de1e):
                raise RuntimeError('Original request completion boundary not observed')
            # This is private target memory; publish only decoded command fields.
            raw=c.rpc('memory.read',{'address':{'space':'linear','offset':f'0x{order_address:08X}'},'length':14})
            order=base64.b64decode(raw['data_base64']);wanted=9 if verb=='board' else 25
            event({'kind':'order-produced','command':order[13],'expected_command':wanted,
                   'target_reference':int.from_bytes(order[:2],'little'),'result':emitted})
            if order[13]!=wanted:raise RuntimeError('Original producer chose an unexpected order')
            samples=[];deadline=time.monotonic()+12
            for index in range(80):
                if time.monotonic()>deadline:break
                # Stop at the verified original frame/input boundary, not a random
                # timer callback whose selectors can differ. This resumes the same
                # committed order; it never repeats input or hit-test writes.
                advanced=self.advance_to_frame()
                now=c.snapshot();s=Mission(now).summary(actor_id);es={e['id']:e for e in s['entities']}
                aa=es[actor_id];cc=es[vehicle_id]
                attached=[e for e in s['entities'] if e.get('owner_id')==actor_id]
                settled=all(e['position_raw']==aa['position_raw'] for e in attached)
                occupancy=s['vehicle_occupancy'];member=aa['vehicle_membership']
                others=[p for p in occupants if p!=actor_id]
                other_members_ok=all(occupancy['people'].get(p)=={'state':'occupant','vehicle_id':vehicle_id} for p in others)
                complete=occupancy['valid'] and settled and other_members_ok
                if verb=='board':complete &= member=={'state':'occupant','vehicle_id':vehicle_id} and aa['position_raw']==cc['position_raw']
                else:complete &= member['state']=='no-vehicle-membership' and actor_id not in cc['occupancy']['occupants']
                sample={'kind':'observation','index':index,'game_sha256':digest(now),'position_raw':aa['position_raw'],
                        'state_raw':aa['status_raw'],'membership':member,'occupants':cc['occupancy']['occupants'],
                        'spatial_valid':s['spatial_index']['valid'],'occupancy_valid':occupancy['valid'],
                        'attachments_settled':settled,'other_occupants_preserved':other_members_ok,
                        'complete':bool(complete),'advance':advanced}
                event(sample);samples.append(sample)
                if complete:
                    journal.update(state='complete',writes=written,complete=True,effects='applied-confirmed',samples=len(samples))
                    return {'state':verb+'-complete','writes':written,'complete':True,'effects':'applied-confirmed',
                            'trial':trial_id,'samples':len(samples),'final':sample}
            raise RuntimeError('Original request issued but completion remains unresolved within its bound')
        except Exception as exc:
            journal.update(state='held-incomplete',complete=False,writes=written,error=str(exc),
                           effects='unknown' if began else 'none-confirmed')
            raise RuntimeError('Vehicle request held; do not replay writes. '+str(exc)) from exc
        finally:
            # Delete owned watches only. One-shot watches may already be absent.
            cleanup=[]
            for key in bps:
                try:cleanup.append({'id':key,'result':c.rpc('breakpoints.delete',{'breakpoint_id':key})})
                except Exception as exc:cleanup.append({'id':key,'error':str(exc)})
            journal['watch_cleanup']=cleanup
            with (folder/'result.json').open('x') as f:f.write(json.dumps(journal,indent=2)+'\n')
