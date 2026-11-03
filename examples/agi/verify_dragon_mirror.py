"""Fresh physical KQ1 well, dragon and magic-mirror segment.

Supply the exact licensed originals and a private output. No state is loaded,
no guest memory or code is edited, and no parser action is retried after an
unknown outcome. Runtime evidence is scoped to this one bounded route.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from examples.agi.spatial_trial import native_game, read, require
from examples.agi.verify_leprechaun import CaveRun
from examples.agi.verify_bridge_clip import retain_private_evidence
from examples.agi.dragon_probes import DragonWaterProbe, MirrorProbe
from fdisbull.agi import load_logic
from fdisbull.agi_picture import extract_v2_resource

DEPENDENCIES=(
    'examples/agi/verify_dragon_mirror.py','examples/agi/dragon_probes.py',
    'examples/agi/inventory_probe.py','examples/agi/verify_leprechaun.py',
    'examples/agi/verify_mushroom.py','examples/agi/verify_bridge_clip.py',
    'examples/agi/verify_goat.py','examples/agi/verify_troll.py','examples/agi/verify_host.py',
    'examples/agi/spatial_trial.py','examples/agi/scan_collision_candidates.py',
    'src/fdisbull/agi.py','src/fdisbull/agi_layout.py','src/fdisbull/agi_picture.py',
    'src/fdisbull/agi_lift.py','src/fdisbull/agi_resources.py','src/fdisbull/agi_host.py',
    'src/fdisbull/agi_dos.py','src/fdisbull/agi_print.py','src/fdisbull/project.py',
    'src/fdisbull/debugger.py',
)


def dragon_approach_safe(s):
    """Conservative host stop guard; original follow timing remains unproven."""
    if s['room']!=51 or s['quest_variables']['75']!=0:return True
    if s['quest_flags']['20']:return False
    actor=s['dragon_actor']
    if not actor['drawn']:return True
    ego=s['ego']
    dx=abs(ego['x']+s['ego_width']//2-actor['x']-actor['width']//2)
    dy=abs(ego['y']-actor['y'])
    # A host-side conservative margin, not a claim about original update timing.
    return max(dx,dy)>30


class DragonRun(CaveRun):
    guest_budget_ms=1200000
    wall_budget_ms=2400000

    def __init__(self,*args):
        super().__init__(*args)
        directory=(self.source/'LOGDIR').read_bytes()
        for n in range(len(directory)//3):
            if directory[n*3:n*3+3]!=b'\xff\xff\xff' and n not in self.resources:
                self.resources[n]=load_logic(self.source/'LOGDIR',self.source,n,profile='2.917')
        self.pictures={str(n):extract_v2_resource(self.source/'PICDIR',self.source,n)['sha256']
                       for n in (1,2,3,4,5,12,22,49,50,51,52)}
        self.in_well=False;self.water_probe=None;self.mirror_probe=None;self.mirror_before=None;self.water_before=None
        self.repeat_controls=[];self.capture_checkpoints=False
        for name in ('verify_dragon_mirror.py','dragon_probes.py'):
            self.report['implementation_sha256']['examples/agi/'+name]=sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()

    def state(self):
        s=super().state();v=read(self.d,self.ds+9,256);f=read(self.d,self.ds+0x109,32)
        flag=lambda n:bool(f[n//8]&(0x80>>(n%8)))
        s['quest_variables']={str(n):v[n] for n in (68,69,74,75,94)}
        s['quest_flags']={str(n):flag(n) for n in (20,21,22,23,67,81,88,91,100,162,164,165,167,176,177,178,179,180)}
        s['player_control']=int.from_bytes(read(self.d,self.ds+0x139,2),'little')
        table=int.from_bytes(read(self.d,self.ds+0x963,2),'little')
        def actor(n):
            b=read(self.d,self.ds+table+43*n,43)
            return {'x':int.from_bytes(b[3:5],'little',signed=True),'y':int.from_bytes(b[5:7],'little',signed=True),
                'view':b[7],'width':int.from_bytes(b[26:28],'little'),'height':int.from_bytes(b[28:30],'little'),
                'direction':b[33],'motion':b[34],'drawn':bool(b[37]&1)}
        s['ego_height']=actor(0)['height'];s['dragon_actor']=actor(3)
        if hasattr(self,'inventory'):
            s['inventory_locations']={str(n):read(self.d,self.ds+self.inventory['base']+3*n+2,1)[0]
                                      for n in (1,11,19,26)}
            for name,item in (('dagger',1),('bucket',11),('mirror',19),('water',26)):
                s[name+'_carried']=s['inventory_locations'][str(item)]==255
        return s

    def safe_state(self):
        s=self.state();self.samples.append({'guest_ms':self.guest_elapsed,'state':s})
        require(not s['dead'],'Original guest death')
        require(dragon_approach_safe(s),'Dragon approach reached conservative contact stop')
        if self.in_well and s['room'] in (49,52):
            require(s['ego_view'] in (0,70,73,74,93,143) and s['ego_width']>0,
                    'Unqualified original well/swimming footprint')
        else:
            require(not s['in_water'] and not s['swimming'] and s['ego_width']==6 and
                    s['ego_view']==0 and s['step_size']==1,'Unexpected dry walking state')
        return s

    def handle_stop(self,out):
        for probe in (self.water_probe,self.mirror_probe):
            if probe is not None and probe.active:return probe.handle_stop(out)
        return super().handle_stop(out)

    def observe_clip(self,name):
        result=super().observe_clip(name)
        self.clip_observations[name]['guest_ms']=self.guest_elapsed
        return result

    def message_observed(self,message):
        super().message_observed(message)
        message['guest_ms']=self.guest_elapsed

    def action(self,name,before,after,i,m):
        super().action(name,before,after,i,m)

    def checkpoint(self,name):
        """Optionally save one private diagnostic state; never load it here."""
        if not self.capture_checkpoints:return
        try:
            require(self._idle() and self.watch is None and not self.trace_active,
                    'Private checkpoint requires settled input and no watch or trace')
            artifact=self.d.save_state(name+'.sav');path=self.root/(name+'.sav')
            self.p.debug_export(artifact['artifact'],path)
            require(sha256(path.read_bytes()).hexdigest()==artifact['sha256'],'Checkpoint export differs')
            self.report.setdefault('private_checkpoints',[]).append({'path':path.name,
                'sha256':artifact['sha256'],'guest_ms':self.guest_elapsed,'loaded':False})
        except BaseException as error:
            self.execution_blocked=True
            self.report['checkpoint_failure']={'name':name,'error':str(error)}
            raise

    def capture(self):
        value={'format':'fdisbull-agi-dragon-mirror-capture-1',
            'source':{'agi_sha256':sha256((self.source/'AGI').read_bytes()).hexdigest(),
                'object_sha256':sha256((self.source/'OBJECT').read_bytes()).hexdigest(),
                'resources':{str(n):r.resource_sha256 for n,r in self.resources.items()}},
            'runtime':{'policy':'physical','fresh_game':True,'interventions':[],
                'session_id':self.d.session_id,'guest_elapsed_ms':self.guest_elapsed},
            'observations':self.clip_observations,'actions':self.clip_actions,'pictures':self.pictures,
            'repeat_controls':self.repeat_controls}
        if self.mirror_before is not None:value['mirror_before']=self.mirror_before
        if self.water_before is not None:value['water_before']=self.water_before
        return value

    def fresh(self):
        s=self.safe_state()
        require(s['room']==1 and s['score']==0 and not any(s[x+'_carried'] for x in ('dagger','bucket','mirror','water')),
                'Fresh initial dragon route differs')
        return self.observe_clip('fresh')

    def obtain_dagger(self,before):
        i,m=len(self.inputs),len(self.messages)
        self.surface_exit('left',2);self.surface_exit('left',3)
        # The live rock actor is absent from the static PIC priority plane.
        # Approach its source-qualified push rectangle from above, keeping the
        # intermediate path away from the actor's original baseline at y=133.
        self.static_path(150,110);self.static_path(120,110);self.precise(y=114)
        s=self.safe_state()
        require(s['room']==3 and (s['ego']['x'],s['ego']['y'])==(120,114),
                'Original rock approach did not settle in the upper push guard')
        self.command('push rock')
        self.wait_for(lambda s:s['quest_flags']['67'] or
            (s['score']==2 and bool(read(self.d,self.ds+0x109+62//8,1)[0]&(0x80>>(62%8)))),
            'rock movement',15000)
        s=self.safe_state()
        require(s['room']==3 and 112<=s['ego']['x']<=134 and 108<=s['ego']['y']<=133,
                'Original dagger pickup guard changed after moving the rock')
        self.command('get dagger')
        self.wait_for(lambda s:s['dagger_carried'] and s['quest_flags']['67'] and s['score']==7,'dagger pickup')
        after=self.observe_clip('dagger-carried');self.action('obtain-dagger',before,after,i,m);return after

    def detach_bucket(self,before):
        i,m=len(self.inputs),len(self.messages)
        self.surface_exit('left',4);self.surface_exit('left',5)
        # L5 sets horizon 55; the generic north proposal uses y=48 and is
        # necessarily outside its own collision model. Stay on its first
        # walkable row and let the original north input select room 12.
        self.static_path(40,56);self.move('up',room=12)
        self.static_path(65,120);self.command('cut rope')
        self.wait_for(lambda s:s['bucket_carried'] and s['quest_flags']['81'] and s['quest_flags']['176'] and
                      s['score']==9,'bucket detachment')
        after=self.observe_clip('bucket-carried');self.action('detach-bucket',before,after,i,m)
        self.checkpoint('bucket-carried');return after

    def descend_well(self,before):
        i,m=len(self.inputs),len(self.messages)
        self.static_path(65,120);self.command('lower rope')
        self.wait_for(lambda s:s['quest_flags']['179'],'rope lowering')
        self.in_well=True;self.command('climb rope')
        # CLIMB mounts the rope and moves to (39,132); the original game
        # requires an ordinary DOWN input before its y>145 room transition.
        self.wait_for(lambda s:s['room']==12 and s['ego_view']==143 and s['quest_flags']['180'] and
                      (s['ego']['x'],s['ego']['y'],s['ego']['direction'])==(39,132,0) and
                      s['player_control']==1 and not s['window'], 'top rope readiness',15000)
        self.report['top_rope_state']=self.state()
        self.press('down',20,hold_ms=1,gap_ms=1)
        self.wait_for(lambda s:s['room']==49 and not s['initializing'] and s['ego']['drawn'] and s['score']==10,
                      'original well entry',30000)
        self.ready();after=self.observe_clip('well-ready');self.action('descend-well',before,after,i,m);return after

    def dive_to_cave(self,before):
        i,m=len(self.inputs),len(self.messages)
        self.press('down',20,hold_ms=1,gap_ms=1)
        self.wait_for(lambda s:s['room']==49 and s['quest_variables']['94'] in (1,2),'well water entry',25000)
        self.command('dive')
        self.wait_for(lambda s:s['room']==52 and not s['initializing'] and s['water_carried'] and
            s['quest_flags']['88'] and s['score']==14,'underwater cave and water collection',30000)
        self.ready();after=self.observe_clip('water-ready');self.action('dive-to-cave',before,after,i,m);return after

    def enter_dragon(self,before):
        i,m=len(self.inputs),len(self.messages)
        self.move('down',axis='y',target=120);self.move('left',room=51)
        self.in_well=False
        self.wait_for(lambda s:s['room']==51 and not s['initializing'] and s['ego_view']==0 and s['score']==15,
                      'dragon cave entry',15000)
        after=self.observe_clip('dragon-before');self.action('enter-dragon',before,after,i,m)
        self.checkpoint('dragon-before');return after

    def douse_dragon(self,before):
        i,m=len(self.inputs),len(self.messages)
        s=self.safe_state()
        require(s['room']==51 and 131<=s['ego']['x']<=133 and s['ego']['y']==136 and
                s['ego']['direction']==0 and s['player_control']==1 and s['ignore_blocks'] and
                s['score']==15 and s['water_carried'] and s['quest_flags']['88'] and
                s['quest_variables']['75']==0 and not s['quest_flags']['20'],
                'Original dragon entry differs')
        # Type once, before movement, then approach away from the pursuing
        # dragon. Original PIC priority-zero barriers rule out a straight
        # eastward walk at y=136. Each leg remains ordinary physical input.
        self.type_text('throw water')
        self.report['dragon_approach']=[]
        for axis,target in (('x',135),('y',131),('x',146)):
            self.precise(**{axis:target});pose=self.safe_state()
            self.report['dragon_approach'].append({'axis':axis,'target':target,
                'guest_ms':self.guest_elapsed,'input_count':len(self.inputs),'state':pose})
        self.observe_clip('water-before')
        self.water_before=self.clip_observations.pop('water-before');s=self.water_before['state']
        require(s['room']==51 and s['score']==15 and s['water_carried'] and s['quest_flags']['88'] and
                s['quest_variables']['75']==0 and not (105<=s['ego']['x']<=145 and 96<=s['ego']['y']<=166),
                'Dragon water launch position differs')
        self.water_probe=DragonWaterProbe(self);self.water_probe.start()
        try:
            self.press('enter',300,hold_ms=1,gap_ms=1)
            end=self.guest_elapsed+1000
            while self.water_probe.active:
                self.safe_state()
                require(self.guest_elapsed<end,'Pretyped water outcome not observed; preserve without replay')
                self.advance(min(20,end-self.guest_elapsed))
            require(self.water_probe.proof.get('complete') is True,'Pretyped water proof incomplete')
        except BaseException as error:
            if self.water_probe.active and not self.water_probe.failed:self.water_probe._fail(error,'controller')
            raise
        self.wait_for(lambda s:not self.water_probe.active and s['score']==20 and not s['water_carried'] and
                      s['quest_variables']['75']==2 and not s['dragon_actor']['drawn'] and
                      not any(s['quest_flags'][str(n)] for n in (21,22,23)),'dragon retreat',20000)
        require(self.water_probe.proof['complete'] is True and self.water_probe.proof['status']=='verified' and
                any(z.get('logic')==51 and z.get('source_offset')==0x45e and z.get('status')=='completed'
                    for z in self.messages[m:]),'Original dragon water response incomplete')
        after=self.observe_clip('dragon-retreated');self.action('douse-dragon',before,after,i,m)
        path=self.root/'dragon-water-pickup.private.json'
        self.clip_actions[-1]['native_water']={'path':path.name,'sha256':sha256(path.read_bytes()).hexdigest()}
        return after

    def take_mirror(self,before):
        i,m=len(self.inputs),len(self.messages)
        self.static_path(45,115);self.observe_clip('mirror-before')
        self.mirror_before=self.clip_observations.pop('mirror-before');s=self.mirror_before['state']
        require(s['room']==51 and s['score']==20 and 26<=s['ego']['x']<=59 and 104<=s['ego']['y']<=127 and
                s['quest_variables']['75']==2 and not s['mirror_carried'],'Mirror source guard differs')
        self.mirror_probe=MirrorProbe(self);self.mirror_probe.start();self.command('get mirror')
        self.wait_for(lambda s:not self.mirror_probe.active and s['mirror_carried'] and s['score']==28,'mirror pickup')
        require(self.mirror_probe.proof['complete'] is True and self.mirror_probe.proof['status']=='verified' and
                any(z.get('logic')==51 and z.get('source_offset')==0x381 and z.get('status')=='completed'
                    for z in self.messages[m:]),'Original mirror response incomplete')
        after=self.observe_clip('mirror-taken');self.action('take-mirror',before,after,i,m)
        path=self.root/'mirror-pickup.private.json'
        self.clip_actions[-1]['native_pickup']={'path':path.name,'sha256':sha256(path.read_bytes()).hexdigest()}
        return after

    def repeat_controls_once(self):
        for index,text in enumerate(('get mirror','throw water')):
            name=f'repeat-{index}-before';self.observe_clip(name);before=self.clip_observations.pop(name)
            start=(len(self.inputs),len(self.messages));self.command(text)
            name=f'repeat-{index}-after';self.observe_clip(name);after=self.clip_observations.pop(name)
            state=after['state']
            require(state['room']==51 and state['score']==28 and state['mirror_carried'] and not state['water_carried'] and
                    state['quest_variables']['75']==2,'Repeat control changed qualified outcome')
            self.repeat_controls.append({'command':text,'before_observation':before,'after_observation':after,
                'inputs':self.inputs[start[0]:],'messages':self.messages[start[1]:],
                'scope':'One ordinary post-outcome command; no general parser claim.'})

    def leave_cave(self,before):
        i,m=len(self.inputs),len(self.messages)
        s=self.safe_state()
        require(s['room']==51 and (s['ego']['x'],s['ego']['y'])==(45,115) and
                s['quest_variables']['75']==2 and not s['dragon_actor']['drawn'] and
                s['mirror_carried'] and s['ignore_blocks'], 'Original cave exit starting state differs')
        # The PIC-only shortest path crosses the drawn boulder's baseline at
        # y=127. Approach the left passage from below the original actor's
        # source position, then let the ordinary left input change rooms.
        self.move('left',axis='x',target=38)
        s=self.safe_state()
        require(s['room']==51 and 35<=s['ego']['x']<=40 and s['ego']['y']==115 and
                s['ego']['direction']==0 and s['ignore_blocks'],
                'Original boulder approach did not settle right of the actor')
        self.move('down',axis='y',target=134)
        s=self.safe_state()
        require(s['room']==51 and 35<=s['ego']['x']<=40 and 133<=s['ego']['y']<=139 and
                s['ego']['direction']==0 and s['ignore_blocks'],
                'Original boulder exit did not settle in the qualified corridor')
        self.move('left',room=50)
        self.surface_exit('left',22)
        s=self.safe_state();require(s['score']==28 and s['mirror_carried'] and not s['water_carried'],
                                    'Original surface return state differs')
        after=self.observe_clip('surface-return');self.action('leave-cave',before,after,i,m);return after

    def route(self):
        b=self.fresh();b=self.obtain_dagger(b);b=self.detach_bucket(b);b=self.descend_well(b)
        b=self.dive_to_cave(b);b=self.enter_dragon(b);b=self.douse_dragon(b);b=self.take_mirror(b)
        self.repeat_controls_once();self.leave_cave(b)
        self.report['normal_dragon_mirror_complete']=True
        return self.capture()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','backend','output'):parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--checkpoints',action='store_true',help='Save private diagnostic states; never load them in this route')
    args=parser.parse_args(argv);source=args.source.resolve();root=args.output.resolve();checkout=Path(__file__).resolve().parents[2]
    require(not args.output.is_symlink() and root!=checkout and checkout not in root.parents and
            root!=source and source not in root.parents,'Keep runtime inputs and captures private')
    dependencies={name:sha256((checkout/name).read_bytes()).hexdigest() for name in DEPENDENCIES}
    backend_sha=sha256(args.backend.resolve().read_bytes()).hexdigest()
    driver=None;report=None;primary=None
    def secondary(label,fn):
        nonlocal primary
        try:fn()
        except BaseException as error:
            if primary is None:primary=error
            if report is not None:report.setdefault('persistence_errors',[]).append({'operation':label,'error':str(error)})
    try:
        with native_game('kq1',source,root,args.backend.resolve(),fair_play=True) as (p,d,obs,restore,frame,report,game):
            report['dependency_sha256']=dependencies
            driver=DragonRun(p,d,report,frame,source,root)
            driver.capture_checkpoints=args.checkpoints
            try:
                capture=driver.route();(root/'capture.private.json').write_text(json.dumps(capture,indent=2)+'\n')
                report['final_state']=driver.state()
            except BaseException as error:
                primary=error;report.update(normal_dragon_mirror_complete=False,error=str(error))
                secondary('last state',lambda:report.update(last_state=driver.state()))
                secondary('failure frame',lambda:frame('failure.png'))
            finally:
                if driver.trace_active:secondary('partial trace readback',driver.retain_trace_readback)
                if driver.trace_active:secondary('trace cleanup',driver.stop_trace)
                for probe in (driver.water_probe,driver.mirror_probe):
                    if probe is not None and probe.proof is not None:
                        report.setdefault('retained_proofs',{})[probe.name]=probe.proof
                        secondary('independent '+probe.name+' proof',lambda probe=probe:(root/('retained-'+probe.name+'.private.json')).write_text(json.dumps(probe.proof,indent=2)+'\n'))
                if driver.trace_receipt is not None:report['retained_trace']=driver.trace_receipt
                if driver.watch:secondary('watch cleanup',driver.remove_watch)
                if driver.bp:secondary('print breakpoint cleanup',lambda:d.call('breakpoints.delete',{'breakpoint_id':driver.bp}))
    except BaseException as error:
        if report is not None:report['normal_dragon_mirror_complete']=False
        if primary is None:primary=error
        elif report is not None:report.setdefault('persistence_errors',[]).append({'operation':'native cleanup','error':str(error)})
    finally:
        if report is not None:
            def verify_dependencies():
                report['dependency_hashes_unchanged']=all(
                    sha256((checkout/name).read_bytes()).hexdigest()==value for name,value in dependencies.items())
                report['backend_unchanged']=sha256(args.backend.resolve().read_bytes()).hexdigest()==backend_sha
                require(report['dependency_hashes_unchanged'] and report['backend_unchanged'],
                        'Native dependencies or backend changed')
            secondary('dependency integrity',verify_dependencies)
            errors=retain_private_evidence(driver,source,root,report)
            if primary is None and errors:primary=errors[0]
            if primary is not None:
                report['normal_dragon_mirror_complete']=False
                secondary('failed final receipt',lambda:(root/'result.json').write_text(json.dumps(report,indent=2,default=str)+'\n'))
    if primary is not None:raise primary

if __name__=='__main__':main()
