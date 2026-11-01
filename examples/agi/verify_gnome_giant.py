"""Private physical KQ1 gnome/key and sleeping-giant investigation.

Use the owner's exact originals and a fresh private output directory. Source
paths and predicates are proposals until the original guest completes them.
"""
from copy import deepcopy
import argparse
from hashlib import sha256
import json
from pathlib import Path

from examples.agi.spatial_trial import read, require
from examples.agi.verify_leprechaun import CaveRun
from examples.agi.inventory_probe import PickupProbe
from examples.agi.motion_probe import MotionProbe
from examples.agi.distance_probe import DistanceProbe
from examples.agi.verify_bridge_clip import retain_private_evidence
from examples.agi.spatial_trial import native_game
from fdisbull.agi import load_logic


class QuestRun(CaveRun):
    guest_budget_ms = 1800000
    wall_budget_ms = 3600000

    def __init__(self, *args):
        super().__init__(*args)
        directory = (self.source/'LOGDIR').read_bytes()
        # Print observations must bind the actual caller, including auxiliary
        # logics reached by an ordinary input. Loading host metadata runs no guest.
        for n in range(len(directory)//3):
            if directory[n*3:n*3+3] != b'\xff\xff\xff' and n not in self.resources:
                self.resources[n] = load_logic(self.source/'LOGDIR',self.source,n,profile='2.917')
        self.report['implementation_sha256']['examples/agi/verify_gnome_giant.py'] = sha256(Path(__file__).read_bytes()).hexdigest()
        self.quest_started = False
        self.preceding_cave = None
        self.quest_probe = None
        self.motion_probe = None
        self.distance_probe = None
        self.capture_checkpoints = False
        self.guess_observations = []
        self.report['implementation_sha256']['examples/agi/inventory_probe.py'] = sha256(Path(__file__).with_name('inventory_probe.py').read_bytes()).hexdigest()
        self.report['implementation_sha256']['examples/agi/motion_probe.py'] = sha256(Path(__file__).with_name('motion_probe.py').read_bytes()).hexdigest()
        self.report['implementation_sha256']['examples/agi/distance_probe.py'] = sha256(Path(__file__).with_name('distance_probe.py').read_bytes()).hexdigest()

    def state(self):
        s = super().state()
        v = read(self.d,self.ds+9,256); f = read(self.d,self.ds+0x109,32)
        flag = lambda n: bool(f[n//8] & (0x80 >> (n % 8)))
        s['quest_variables'] = {str(n):v[n] for n in (1,30,31,62,63,64,66,70,71,80,83,84,85,86)}
        s['quest_flags'] = {str(n):flag(n) for n in (20,21,22,23,24,25,26,73,79,84,85,102,104,148,154,156,169,205)}
        s['player_control'] = int.from_bytes(read(self.d,self.ds+0x139,2),'little')
        table=int.from_bytes(read(self.d,self.ds+0x963,2),'little')
        s['quest_actors']={}
        for n in (1,2,3,4):
            b=read(self.d,self.ds+table+43*n,43)
            s['quest_actors'][str(n)]={'x':int.from_bytes(b[3:5],'little',signed=True),
                'y':int.from_bytes(b[5:7],'little',signed=True),'view':b[7],'loop':b[10],'cel':b[14],
                'width':int.from_bytes(b[26:28],'little'),'height':int.from_bytes(b[28:30],'little'),
                'direction':b[33],'motion':b[34],
                'drawn':bool(b[37]&1),'motion_bit':bool(b[37]&128)}
        if hasattr(self,'inventory'):
            for name,item in (('key',5),('chest',2)):
                location=read(self.d,self.ds+self.inventory['base']+3*item+2,1)[0]
                s['inventory_locations'][str(item)]=location
                s[name+'_carried']=location==255
        return s

    def handle_stop(self,out):
        distance=getattr(self,'distance_probe',None)
        if distance is not None and distance.active:
            distance.handle_stop(out)
            if not distance.active:
                require(distance.proof['complete'] is True,'Original distance proof incomplete')
                self.quest_probe.start()
            return
        motion=getattr(self,'motion_probe',None)
        if motion is not None and motion.active:
            return motion.handle_stop(out)
        probe=getattr(self,'quest_probe',None)
        if probe is not None and probe.active:
            return probe.handle_stop(out)
        return super().handle_stop(out)

    def message_observed(self,message):
        super().message_observed(message)
        message['guest_ms']=self.guest_elapsed

    def observe_clip(self,name):
        result=super().observe_clip(name)
        self.clip_observations[name]['guest_ms']=self.guest_elapsed
        return result

    def quest_safe(self,room=None,score=None):
        s=self.safe_state()
        require(s['shield_carried'] and s['quest_flags']['102'],'Original shield protection was lost')
        require(room is None or s['room']==room,'Quest room differs')
        require(score is None or s['score']==score,'Quest score differs')
        return s

    def safe_state(self):
        s=super().safe_state()
        if getattr(self,'quest_started',False):
            require(s['shield_carried'] and s['quest_flags']['102'],'Original shield protection was lost')
            if s['room'] in (66,67,68,69):
                require(not s['on_trigger'],'Original stair fall trigger observed; preserve the stop')
        return s

    def _precise(self,*,x=None,y=None):
        s=self.state()
        if not getattr(self,'quest_started',False) or s['room'] not in (66,67,68,69):
            return super()._precise(x=x,y=y)
        self.quest_safe(s['room'],19)
        require((x is None)!=(y is None),'Watched stair motion requires one axis')
        axis,target=('x',x) if x is not None else ('y',y)
        require(type(target) is int and 0<=target<=(154 if axis=='x' else 167),'Invalid stair waypoint')
        self.ready();s=self.quest_safe(s['room'],19)
        if s['ego'][axis]==target:return s
        key=('right' if target>s['ego']['x'] else 'left') if axis=='x' else ('down' if target>s['ego']['y'] else 'up')
        probe=MotionProbe(self,axis=axis,target=target,key=key);self.motion_probe=probe
        try:
            probe.start();end=self.guest_elapsed+25000
            while not probe.poll():
                require(self.guest_elapsed<end,'Watched stair waypoint budget exhausted')
                self.advance(min(10,end-self.guest_elapsed))
            final=self.quest_safe(s['room'],19)
            require(final['ego'][axis]==target and final['ego']['direction']==0 and self._idle(),
                    'Watched stair waypoint did not remain settled')
            return final
        except BaseException as error:
            if probe.active and not probe.failed:probe._fail(error,'controller')
            raise

    def quest_action(self,name,before,after,start):
        self.ready();self.quest_safe()
        require(self.state()['player_control']==1 and self._idle(),'Quest controls not ready')
        self.observe_clip(after)
        require(self.clip_observations[after]['state']['player_control']==1 and self._idle(),
                'Quest controls changed during capture')
        self.action(name,before,after,*start)
        if after in ('tree-unlocked','giant-awake','giant-asleep'):
            self.checkpoint(after)

    def checkpoint(self,name):
        if not getattr(self,'capture_checkpoints',False):return
        try:
            require(self._idle() and self.watch is None and not self.trace_active,
                    'Private checkpoint requires idle execution without a data watch or trace')
            artifact=self.d.save_state(name+'.sav')
            path=self.root/(name+'.sav')
            self.p.debug_export(artifact['artifact'],path)
            require(sha256(path.read_bytes()).hexdigest()==artifact['sha256'],'Private checkpoint export differs')
            self.report.setdefault('private_checkpoints',[]).append({'path':path.name,
                'sha256':artifact['sha256'],'guest_ms':self.guest_elapsed,'loaded':False})
        except BaseException as error:
            self.execution_blocked=True
            self.report['checkpoint_failure']={'name':name,'error':str(error)}
            raise

    def guess_frame(self,stage):
        require(type(stage) is int and 1<=stage<=3 and len(getattr(self,'guess_observations',[]))==stage-1,
                'Guess snapshots duplicated or out of order')
        self.ready();s=self.quest_safe(40,14)
        def qualify(s):
            require(s['quest_variables']['84']==stage and not s['key_carried'] and
                    s['quest_flags']['22']==(stage<3) and s['quest_flags']['21']==(stage==3),
                    'Original gnome guess outcome differs')
        qualify(s)
        name=f'gnome-guess-{stage}'
        prior=self.d.screenshot(name+'-initial.png',hooks=False)['metadata'];self.advance(50)
        s=self.quest_safe(40,14);qualify(s);item=self.frame(name+'.png')
        require(all(type(m[k]) is int and m[k]>=0 for m in (prior,item['metadata']) for k in ('frame_id','mode_id')) and
                item['metadata']['frame_id']>prior['frame_id'] and item['metadata']['mode_id']==prior['mode_id'],
                'Guess frame not fresh')
        if not hasattr(self,'guess_observations'):self.guess_observations=[]
        self.guess_observations.append({'stage':stage,'state':s,'guest_ms':self.guest_elapsed,
            'frame':{'path':name+'.png','sha256':item['sha256'],'metadata':item['metadata']}})

    def gnome(self):
        self.ready();s=self.quest_safe(40,14)
        require(s['quest_variables']['84']==0 and not s['key_carried'] and
                not s['quest_flags']['21'] and not s['quest_flags']['22'],'Gnome start differs')
        start=len(self.inputs),len(self.messages)
        self.command('hi')
        self.wait_for(lambda s:s['quest_flags']['22'],'original gnome riddle')
        self.command('get key');self.wait_for(lambda s:s['quest_variables']['84']==1,'first wrong guess')
        self.guess_frame(1)
        for stage in (2,3):
            self.press('f3',100,hold_ms=1,gap_ms=1)
            self.press('enter',300,hold_ms=1,gap_ms=1)
            self.wait_for(lambda s:s['quest_variables']['84']==stage,'repeated wrong guess')
            self.guess_frame(stage)
        self.quest_action('wrong-names','gnome-ready','key-on-ground',start)

    def pickup(self,name):
        specs={'key':(40,5,0x2d6,0x2db,3,14,('item','return','score'),'key-on-ground','key-taken'),
               'chest':(58,2,0x25d,0x25a,8,26,('score','item','return'),'giant-asleep','chest-taken')}
        logic,item,offset,score_offset,delta,before,order,anchor,after=specs[name]
        self.quest_safe(logic,before);start=len(self.inputs),len(self.messages)
        self.quest_probe=PickupProbe(self,name=name,logic=logic,item=item,item_offset=offset,
            score_offset=score_offset,score_delta=delta,before_score=before,order=order)
        if name=='chest':
            self.distance_probe=DistanceProbe(self)
            self.distance_probe.start()
        else:self.quest_probe.start()
        self.command('get '+name)
        self.wait_for(lambda s:not self.quest_probe.active and s[name+'_carried'] and s['score']==before+delta,
                      'original '+name+' pickup')
        require(self.quest_probe.proof['complete'] is True and self.quest_probe.proof['status']=='verified' and
                self.quest_probe.proof['native_execution'] is True,'Original pickup proof incomplete')
        self.quest_action('take-'+name,anchor,after,start)
        path=self.root/(name+'-pickup.private.json')
        self.clip_actions[-1]['native_pickup']={'path':path.name,'sha256':sha256(path.read_bytes()).hexdigest()}
        if name=='chest':
            require(self.distance_probe.proof['complete'] is True,'Native distance observation incomplete')
            path=self.root/'giant-distance.private.json'
            self.clip_actions[-1]['native_distance']={'path':path.name,'sha256':sha256(path.read_bytes()).hexdigest()}

    def get_key(self):self.pickup('key')
    def get_chest(self):self.pickup('chest')

    def reach_gnome(self):
        self.quest_safe(36,14);start=len(self.inputs),len(self.messages)
        self.surface_exit('up',45,41);self.surface_exit('right',46,164)
        self.surface_exit('right',47,164);self.surface_exit('right',48,150)
        # The source keeps the crossing's x coordinate. A generic fallback
        # exit on the left would reach the other bank, despite the right room.
        self.static_path(110,165);self.move('down',room=33)
        require(self.state()['ego']['x']>103,'Wrong riverbank at room33 entry')
        self.surface_exit('right',40,100);self.static_path(50,120)
        self.quest_safe(40,14)
        self.wait_for(lambda s:s['quest_variables']['62']<35 and s['quest_actors']['1']['drawn'] and
            s['player_control']==1,'original gnome talking distance',20000)
        self.quest_action('reach-gnome','quest-start','gnome-ready',start)

    def reach_tree(self):
        s=self.quest_safe(40,17);require(s['key_carried'],'Original key missing')
        start=len(self.inputs),len(self.messages)
        for key,room,preferred in (('up',41,70),('up',8,70),('up',9,20),
                ('left',16,100),('left',15,100),('up',18,70),('left',19,50)):
            self.surface_exit(key,room,preferred)
            self.quest_safe(room,17)
        self.static_path(110,105)
        self.quest_action('reach-tree','key-taken','tree-ready',start)

    def unlock_tree(self):
        s=self.quest_safe(19,17)
        require(s['key_carried'] and s['quest_flags']['84'] and s['quest_variables']['66']==0,
                'Original locked-tree state differs')
        start=len(self.inputs),len(self.messages)
        # The original accepts this form after f84. Keep the command within
        # the guest parser's observed rapid-input capacity; queue acceptance
        # alone did not prove consumption of the exploratory long form.
        self.command('unlock door')
        self.wait_for(lambda s:s['quest_variables']['66']==1 and s['quest_flags']['85'] and s['score']==19,
                      'original tree unlock')
        self.quest_action('unlock-tree','tree-ready','tree-unlocked',start)

    def door_frame(self):
        self.ready();s=self.quest_safe(19,19)
        def qualify(s):
            a=s['quest_actors']['1']
            require(s['quest_variables']['66']==2 and a['view']==20 and a['cel']==3 and a['drawn'] and
                    s['ignore_blocks'] and s['player_control']==1 and self._idle(),
                    'Original door animation not complete')
        qualify(s);prior=self.d.screenshot('door-open-initial.png',hooks=False)['metadata']
        self.advance(50);s=self.quest_safe(19,19);qualify(s);item=self.frame('door-open.png')
        require(all(type(m[k]) is int and m[k]>=0 for m in (prior,item['metadata']) for k in ('frame_id','mode_id')) and
                item['metadata']['frame_id']>prior['frame_id'] and item['metadata']['mode_id']==prior['mode_id'],
                'Door frame not fresh')
        self.door_observation={'state':s,'guest_ms':self.guest_elapsed,
            'frame':{'path':'door-open.png','sha256':item['sha256'],'metadata':item['metadata']}}

    def stair_ready(self,room,point):
        self.wait_for(lambda s:s['room']==room and not s['initializing'] and s['quest_flags']['148'] and
            s['player_control']==1 and s['ego']['drawn'] and s['ego']['direction']==0 and not s['window'] and
            (s['ego']['x'],s['ego']['y'])==point and self._idle(), 'original stair entry',15000)
        self.quest_safe(room,19)

    def admit_room68(self):
        """Select a source-qualified visit using ordinary retreats and reentry.

        Hidden actor pixels alone do not establish an empty visit. In this
        exact source, f23 marks the dwarf initialization branch. Its random
        selector is sampled once on entry; no initialization is admitted only
        after the original entry motion has completed. Each rejected visit
        has a known outcome before another ordinary room transition is sent.
        """
        expected='779fcbf87c2c07318e24289fdf5d5619e5615e09e972543fa456d7a62bba4469'
        visits=self.report.setdefault('room68_visits',[])
        require(not visits and self.resources[68].resource_sha256==expected,
                'Room 68 visit source or controller differs')
        for attempt in range(1,17):
            s=self.quest_safe(68,19);v=s['quest_variables'];f=s['quest_flags']
            require(self._idle() and not s['initializing'] and not s['window'] and
                    s['player_control']==1 and s['ego']=={'x':95,'y':159,'direction':0,'drawn':True}
                    and f['148'] is True and v['1']==67 and s['key_carried'] and not s['chest_carried']
                    and type(v['62']) is int and 0<=v['62']<=250
                    and type(v['70']) is int and 0<=v['70']<=45 and type(f['23']) is bool,
                    'Room 68 entry is not reconciled')
            empty=f['23'] is False and v['62']>=150 and v['70']==0 and s['quest_actors']['1']['drawn'] is False
            selected=f['23'] is True and v['62']<150
            require(empty or selected,'Room 68 source decision contradicts its observed state')
            record={'attempt':attempt,'source_logic_sha256':expected,'state':deepcopy(s),
                    'guest_ms':self.guest_elapsed,'admitted':empty,
                    'scope':'Source-linked host admission; not a native conditional-handler trace.'}
            visits.append(record)
            if empty:return
            require(attempt<16,'Room 68 no-initialization visit budget exhausted')
            # These dry baseline origins lead to the source's y=166 room exit.
            # The guest still decides actual movement and transition success.
            self.precise(x=94);self.precise(y=165)
            self.press('down',20,hold_ms=1,gap_ms=1)
            self.stair_ready(67,(119,42))
            record['retreat_state']=deepcopy(self.quest_safe(67,19))
            self.press('up',20,hold_ms=1,gap_ms=1)
            self.stair_ready(68,(95,159))

    def climb(self):
        self.quest_safe(19,19);start=len(self.inputs),len(self.messages)
        self.command('open door')
        self.wait_for(lambda s:s['quest_variables']['66']==2 and s['quest_actors']['1']['cel']==3 and
                      s['ignore_blocks'] and s['player_control']==1,'original door animation')
        self.door_frame()
        self.precise(y=95);self.press('up',20,hold_ms=1,gap_ms=1)
        self.wait_for(lambda s:s['room']==66 and not s['initializing'] and s['ego']['drawn'] and
            s['player_control']==1,'original tree entry')
        self.ready();self.quest_safe(66,19)
        for room,goal,next_room,entry in ((66,(129,46),67,(10,151)),
                (67,(111,41),68,(95,159)),(68,(49,41),69,(143,154))):
            self.quest_safe(room,19);self.static_path(*goal)
            self.press('up',20,hold_ms=1,gap_ms=1)
            self.stair_ready(next_room,entry)
            if next_room==68:self.admit_room68()
        self.static_path(2,94);self.move('left',room=59)
        self.quest_safe(59,19);self.static_path(2,110);self.move('left',room=58)
        self.quest_safe(58,19)
        self.quest_action('climb-to-clouds','tree-unlocked','giant-awake',start)

    def wait_giant(self):
        s=self.quest_safe(58,19)
        require(s['quest_variables']['86']==0 and not s['chest_carried'],'Original giant start differs')
        start=len(self.inputs),len(self.messages);end=self.guest_elapsed+180000
        while True:
            s=self.quest_safe(58)
            require(s['score'] in (19,26) and s['quest_variables']['86'] in (0,1),
                    'Original giant took another branch')
            if s['score']==26 and s['quest_variables']['86']==1 and s['quest_flags']['205'] and any(
                    m.get('logic')==58 and m.get('source_offset')==0x450 and m.get('status')=='completed'
                    for m in self.messages[start[1]:]):break
            require(self.guest_elapsed<end,'Original giant sleep budget exhausted')
            self.advance(min(100,end-self.guest_elapsed))
        self.ready()
        self.approach_sleeping_giant()
        self.quest_action('wait-for-sleep','giant-awake','giant-asleep',start)

    def approach_sleeping_giant(self):
        def qualify(s):
            a=s['quest_actors']['1']
            require(s['quest_variables']['86']==1 and s['quest_flags']['205'] and not s['quest_flags']['104'] and
                    a['drawn'] and a['view']==52 and type(a['motion']) is int and a['motion']==0 and
                    type(a['direction']) is int and a['direction']==0 and not s['chest_carried'],
                    'Original sleeping giant differs')
            return a
        s=self.quest_safe(58,26);a=qualify(s)
        fields=('x','y','width','height','view','drawn','motion','direction')
        original=tuple(a[k] for k in fields)
        # Check that the observed sleeping pose stays put. The game computes
        # v70 later, inside GET CHEST; elapsed time cannot refresh that value.
        self.advance(100);s=self.quest_safe(58,26);a=qualify(s)
        require(tuple(a[k] for k in fields)==original,'Sleeping giant changed during observation')
        center=a['x']+a['width']//2
        initial_distance=abs(s['ego']['x']+s['ego_width']//2-center)+abs(s['ego']['y']-a['y'])
        if initial_distance<=30:
            self.report['pre_chest_geometry']={'kind':'host-derived','distance':initial_distance,
                'native_distance_observed':False,'ego':s['ego'],'giant':a}
            return
        offsets=((0,24),(0,-24),(24,0),(-24,0),(18,6),(18,-6),(-18,6),(-18,-6),
                 (12,12),(12,-12),(-12,12),(-12,-12))
        candidates=sorted(((center-s['ego_width']//2+dx,a['y']+dy) for dx,dy in offsets),
            key=lambda p:abs(p[0]-s['ego']['x'])+abs(p[1]-s['ego']['y']))
        target=None
        # A conservative visible-body exclusion makes these static proposals
        # avoid walking through the stopped actor. Original collision decides.
        box=(max(0,a['x']-s['ego_width']+1),max(0,a['y']-a['height']+1),
             min(154,a['x']+a['width']-1),a['y'])
        for point in candidates:
            if not (0<=point[0]<=154 and 43<=point[1]<=166):continue
            plan,_=self.path_model(58,(s['ego']['x'],s['ego']['y']),point,allow_priority_one=s['ignore_blocks'])
            path=plan.get('path')
            valid=isinstance(path,list) and bool(path) and all(isinstance(p,(list,tuple)) and len(p)==2 and
                all(type(v) is int for v in p) and 0<=p[0]<=154 and 0<=p[1]<=167 for p in path)
            if (plan['status']=='found' and valid and tuple(path[0])==(s['ego']['x'],s['ego']['y']) and
                    tuple(path[-1])==point and not any(box[0]<=x<=box[2] and box[1]<=y<=box[3] for x,y in path)):
                target=point;break
        require(target is not None,'No conservative sleeping-giant approach proposal')
        self.journal.append({'kind':'sleeping-giant-approach-proposal','actor':a,'target':target,
            'excluded_origin_rectangle':box,'scope':'Derived proposal; actual original distance and collision must agree.'})
        self.static_path(*target);self.advance(100);s=self.quest_safe(58,26)
        a=qualify(s)
        distance=abs(s['ego']['x']+s['ego_width']//2-a['x']-a['width']//2)+abs(s['ego']['y']-a['y'])
        require(tuple(a[k] for k in fields)==original and distance<=30,
                'Sleeping-chest approach geometry changed')
        self.report['pre_chest_geometry']={'kind':'host-derived','distance':distance,
            'native_distance_observed':False,'ego':s['ego'],'giant':a}

    def resume_quest(self):
        self.reach_gnome();self.gnome();self.get_key();self.reach_tree();self.unlock_tree()
        self.climb();self.wait_giant();self.get_chest()
        s=self.quest_safe(58,34)
        require(s['chest_carried'] and s['key_carried'] and s['quest_flags']['104'] and
                s['quest_flags']['169'] and s['quest_variables']['86']==3,'Original chest completion differs')
        self.report['normal_gnome_giant_complete']=True
        return self.capture()

    def route(self):
        self.prepare_prefix()
        return self.resume_quest()

    def prepare_prefix(self):
        require(not self.quest_started,'Quest prefix already prepared')
        self.preceding_cave=deepcopy(CaveRun.route(self))
        (self.root/'preceding-cave.private.json').write_text(json.dumps(self.preceding_cave,indent=2)+'\n')
        s=self.safe_state()
        require(s['room']==36 and s['score']==14 and s['shield_carried'] and
                s['quest_flags']['102'] and not s['key_carried'] and not s['chest_carried'],
                'Prepared quest state differs')
        self.clip_observations={};self.clip_actions=[];self.quest_started=True
        self.observe_clip('quest-start')
        self.checkpoint('quest-start')
        return self.capture()

    def capture(self):
        result=super().capture()
        if getattr(self,'quest_started',False):
            result['format']='fdisbull-agi-gnome-giant-capture-1'
            result['guess_observations']=getattr(self,'guess_observations',[])
            if hasattr(self,'door_observation'):result['door_observation']=self.door_observation
        return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','backend','output'):parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--checkpoints',action='store_true',help='Save private native checkpoints; never load them during this route')
    args=parser.parse_args();source=args.source.resolve();root=args.output.resolve()
    checkout=Path(__file__).resolve().parents[2]
    require(not args.output.is_symlink() and root!=checkout and checkout not in root.parents and
            root!=source and source not in root.parents,'Keep runtime inputs and captures private')
    driver=None;report=None;primary=None
    def secondary(label,fn):
        nonlocal primary
        try:fn()
        except BaseException as exc:
            if primary is None:primary=exc
            if report is not None:report.setdefault('persistence_errors',[]).append({'operation':label,'error':str(exc)})
    try:
        with native_game('kq1',source,root,args.backend.resolve(),fair_play=True) as (p,d,obs,restore,frame,report,game):
            driver=QuestRun(p,d,report,frame,source,root)
            driver.capture_checkpoints=args.checkpoints
            try:
                capture=driver.route()
                (root/'capture.private.json').write_text(json.dumps(capture,indent=2)+'\n')
                report.update(normal_gnome_giant_complete=True,final_state=driver.state())
            except BaseException as exc:
                primary=exc;report.update(normal_gnome_giant_complete=False,error=str(exc))
                secondary('failure state',lambda:report.update(last_state=driver.state()))
                secondary('failure frame',lambda:frame('failure.png'))
            finally:
                if driver.trace_active:secondary('partial trace readback',driver.retain_trace_readback)
                if driver.trace_active:secondary('trace cleanup',driver.stop_trace)
                probe=driver.quest_probe
                distance=driver.distance_probe
                if distance is not None and distance.proof is not None:
                    report['retained_distance_proof']=deepcopy(distance.proof)
                    secondary('independent distance proof snapshot',lambda:(root/'retained-distance-proof.private.json').write_text(
                        json.dumps(distance.proof,indent=2)+'\n'))
                # A complete in-memory prefix trace may have failed its first
                # file write. Retain it even after tracing has stopped.
                if (driver.trace_receipt is not None and
                        (probe is None or driver.trace_receipt.get('name')!=probe.name)):
                    secondary('partial prefix trace persistence',lambda:(root/'partial-prefix-trace.private.json').write_text(
                        json.dumps(driver.trace_receipt,indent=2)+'\n'))
                if probe is not None and probe.proof is not None and not probe.proof.get('complete'):
                    if driver.trace_receipt is not None and driver.trace_receipt.get('name')==probe.name:
                        secondary('partial pickup trace persistence',probe.persist_partial_trace)
                    secondary('partial pickup proof persistence',probe.persist)
                if probe is not None and probe.proof is not None:
                    # The canonical pickup file can be the failing destination.
                    # Keep the current known effects in independent artifacts.
                    report['retained_pickup_proof']=deepcopy(probe.proof)
                    secondary('independent pickup proof snapshot',lambda:(root/'retained-pickup-proof.private.json').write_text(
                        json.dumps(probe.proof,indent=2)+'\n'))
                    if driver.trace_receipt is not None and driver.trace_receipt.get('name')==probe.name:
                        report['retained_pickup_trace']=deepcopy(driver.trace_receipt)
                if driver.watch:secondary('owned watch cleanup',driver.remove_watch)
                if driver.bp:secondary('print breakpoint cleanup',lambda:d.call('breakpoints.delete',{'breakpoint_id':driver.bp}))
    except BaseException as exc:
        if primary is None:primary=exc
        elif report is not None:report.setdefault('persistence_errors',[]).append({'operation':'native cleanup','error':str(exc)})
    finally:
        if report is not None:
            errors=retain_private_evidence(driver,source,root,report)
            if primary is None and errors:primary=errors[0]
    if primary is not None:raise primary
    print(json.dumps({'complete':True,'state':report['final_state']}),flush=True)


if __name__=='__main__':main()
