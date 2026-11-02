"""Test the KQ1 bottom-row bridge hypothesis with fresh ordinary gameplay.

Game copies, native states, databases and complete captures stay private.
"""
import argparse, json
from pathlib import Path
from hashlib import sha256
from examples.agi.spatial_trial import native_game, read, require
from examples.agi.verify_bridge_clip import ClipRun, retain_private_evidence

PIC_SHA='3fe43fc43ad170ea502e034f0d7a6be1727f5e8ec83e2db0b343119de2b5f303'
LOGIC_SHA='49ebf4046de0446b7c307108e4d2e264560447aa778e898df292ad3e523758f6'


def classify(state, *, target_y, crossing_seen):
    """Choose one evidence-bounded next action; no guest execution here."""
    s=state; e=s['ego']
    if s['dead']:return 'unsafe'
    if s['in_water'] or s['swimming']:
        if target_y==166 and s['room']==39 and e['y']==166 and 5<=e['x']<=86:
            return 'control-water'
        return 'unsafe'
    if s['room']==26:return 'bottom-transition'
    if s['room']==40:
        if (s['score']!=0 or s['troll_paid'] or s['troll_removed'] or
                s['ego_width']!=6 or s['ego_view']!=0):return 'unexpected-state'
        if target_y==167 and crossing_seen and s.get('initializing') is True:
            return 'arrival-pending'
        if not e['drawn']:return 'unexpected-state'
        return 'west-exit' if target_y==167 and crossing_seen else 'unexpected-room'
    if (s['room']!=39 or s['score']!=0 or s['bridge_active'] or s['troll_paid'] or
        s['troll_removed'] or s['ego_width']!=6 or s['ego_view']!=0 or s['step_size']!=1):
        return 'unexpected-state'
    if s['edge']!=0:
        if (s['edge']==4 and target_y==167 and crossing_seen and e['x']==0 and e['y']==167
                and e.get('direction')==7 and s.get('control_direction')==7
                and not s.get('initializing') and s.get('window')==0):
            return 'west-border'
        return 'border-pending'
    if e['y']!=target_y:return 'displaced-row'
    if not s['ignore_blocks']:return 'blocks-enabled'
    if e['x']<=80:return 'crossed-over-water'
    return 'continue'


class BottomRun(ClipRun):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        require(self.picture['sha256']==PIC_SHA and self.resources[39].resource_sha256==LOGIC_SHA,
                'Bridge source identity differs')
        self.bottom_samples=[];self.bottom_observations=[]
        self.report['implementation_sha256']['examples/agi/verify_bridge_bottom.py']=sha256(Path(__file__).read_bytes()).hexdigest()

    def state(self):
        s=super().state();table=int.from_bytes(read(self.d,self.ds+0x963,2),'little')
        actor=read(self.d,self.ds+table,43)
        s['ignore_blocks']=bool(int.from_bytes(actor[37:39],'little') & 2)
        return s

    def observe(self,name):
        # Only settled visual boundaries request another completed frame.
        # Moving/water stops remain readonly: never resume them for an image.
        fresh=name in ('row-start','west-exit')
        previous=self.fast_forward
        if fresh:self.fast_forward=False
        controller=self._transport()
        def capture_frame():
            item=self.frame(name+'.png')
            return {'path':name+'.png','sha256':item['sha256'],'metadata':item['metadata']}
        try:
            captured=controller.capture_frame_state(capture_frame,
                require_fresh=fresh,
                guest_ms=1000,slice_ms=20,max_polls=64)
        finally:
            self.guest_elapsed=controller.guest_elapsed;self.fast_forward=previous
        value={'id':name,'guest_ms':self.guest_elapsed,'state':captured.get('state_after'),
               'input_count':len(self.inputs),'message_count':len(self.messages),
               'frame':captured.get('frame'),'frame_state':captured,
               'frame_scope':'paused state bracket; freshness '+captured['freshness']+
                    '; atomic frame/CPU equivalence is not asserted'}
        self.bottom_observations.append(value)
        require(captured['complete'],'Frame/state observation incomplete: '+str(captured['issues']))
        return value

    def prefix(self):
        initial=self.state();require(initial['room']==1 and initial['score']==0,'Fresh opening required')
        self.move('right',room=8);self.move('right',axis='x',target=70)
        self.move('down',room=41);self.move('right',room=42);self.precise(y=51)
        for x,y in ((99,51),(99,65),(106,65),(106,89),(108,89),(108,90),
                    (111,90),(111,91),(112,91),(112,92),(113,92),(113,160)):
            current=self.state()['ego'];self.precise(**({'x':x} if x!=current['x'] else {'y':y}))
        self.move('down',room=39)
        s=self.safe_state();require(s['room']==39 and s['ego']['direction']==0,'Bridge entry did not settle')
        self.observe('bridge-entry')
        # PIC-derived dry approach; ordinary arrows, hazards not changed.
        # Declare a two-column approach range, retaining the actual result and
        # the original dry-state guards. The row discriminator remains exact.
        for axis,target in (('x',[129,130]),('y',60),('x',126),('y',61),('x',122),('y',62),('x',110),('y',166)):
            self.precise(**{axis:target})
        s=self.safe_state();require(s['room']==39 and s['ego']['x']==110 and s['ego']['y']==166 and
                not s['ego']['direction'] and s['ignore_blocks'] and self._idle(), 'Approach did not settle safely')
        self.observe('east-bank')

    def run_case(self,target_y):
        self.prefix()
        if target_y==167:self.precise(y=167)
        s=self.safe_state();require(s['room']==39 and s['ego']['x']==110 and s['ego']['y']==target_y and
            s['ego']['direction']==0 and s['edge']==0 and s['ignore_blocks'] and self._idle(),'Exact requested starting row not settled')
        self.observe('row-start')
        s=self.state();require(s['room']==39 and s['ego']['x']==110 and s['ego']['y']==target_y and
            s['ego']['direction']==0 and s['edge']==0 and s['ignore_blocks'] and self._idle(),'Start changed during observation')
        self.press('left',20,hold_ms=1,gap_ms=1)
        end=self.guest_elapsed+20000;crossing_seen=False
        while self.guest_elapsed<end:
            s=self.state();self.bottom_samples.append({'guest_ms':self.guest_elapsed,'state':s})
            status=classify(s,target_y=target_y,crossing_seen=crossing_seen)
            if status=='control-water':
                return {'complete':True,'result':'adjacent-row-water-observed','trigger':self.observe('control-water')}
            require(status not in ('unsafe','bottom-transition','unexpected-room','unexpected-state','displaced-row','blocks-enabled','border-pending'),
                    'Boundary stop: '+status)
            if status=='crossed-over-water' and not crossing_seen:
                crossing_seen=True;self.observe('over-water')
            if status=='west-exit':
                # Stop the observed physical motion by the ordinary arrow; no replay.
                self.neutral();s=self.state()
                require(s['room']==40 and s['score']==0 and s['ego']['drawn'] and not s['ego']['direction'] and
                        s['ego_width']==6 and s['ego_view']==0 and not s['in_water'] and not s['swimming'] and
                        not s['dead'] and not s['troll_paid'] and not s['troll_removed'] and self._idle(),
                        'West exit did not settle')
                return {'complete':True,'result':'bottom-row-west-exit','final':self.observe('west-exit')}
            self.advance(10)
        raise RuntimeError('Boundary movement budget exhausted')

    def capture(self):
        v=super().capture();v.update(format='fdisbull-agi-bridge-bottom-capture-1',
            inputs=self.inputs,messages=self.messages,
            bottom_samples=self.bottom_samples,bottom_observations=self.bottom_observations)
        return v


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for k in ('source','backend','output'):ap.add_argument('--'+k,type=Path,required=True)
    ap.add_argument('--target-y',type=int,choices=(166,167),required=True);a=ap.parse_args()
    source=a.source.resolve();root=a.output.resolve()
    require(not a.output.exists() and not a.output.is_symlink() and source not in root.parents and root!=source,
            'Output must be new and separate from source')
    repo=Path(__import__('examples.agi.verify_bridge_clip',fromlist=['__file__']).__file__).resolve().parents[2]
    require(root!=repo and repo not in root.parents,'Keep runtime data outside checkout')
    driver=None;report=None;primary=None
    def secondary(label,fn):
        nonlocal primary
        try:fn()
        except BaseException as exc:
            if primary is None:primary=exc
            report.setdefault('persistence_errors',[]).append({'operation':label,'error':str(exc)})
    try:
        with native_game('kq1',source,root,a.backend.resolve(),fair_play=True) as (p,d,obs,restore,frame,report,game):
            driver=BottomRun(p,d,report,frame,source,root)
            try:
                outcome=driver.run_case(a.target_y)
                report['boundary_result']=outcome;report['boundary_case_complete']=True
                (root/'capture.private.json').write_text(json.dumps(driver.capture(),indent=2)+'\n')
            except BaseException as exc:
                primary=exc;report['boundary_case_complete']=False;report['error']=str(exc)
                def retain_failure_state():
                    state=driver.state();report['last_state']=state
                    if a.target_y==167 and state['room']==26:
                        report['observed_contrary']='original bottom-edge transition to room 26; crossing not established'
                secondary('failure state',retain_failure_state)
                # A stored frame read does not resume the guest.
                secondary('failure frame',lambda:frame('failure.png'))
            finally:
                if driver.bp:secondary('print breakpoint cleanup',lambda:d.call('breakpoints.delete',{'breakpoint_id':driver.bp}))
    except BaseException as exc:
        if primary is None:primary=exc
        elif report is not None:report.setdefault('persistence_errors',[]).append({'operation':'native context cleanup','error':str(exc)})
        if report is not None:report['boundary_case_complete']=False
    finally:
        if report is not None:
            errors=retain_private_evidence(driver,source,root,report)
            if errors and primary is None:primary=errors[0]
            if primary is not None:
                report['boundary_case_complete']=False
                try:(root/'result.json').write_text(json.dumps(report,indent=2,default=str)+'\n')
                except BaseException:pass
    if primary is not None:raise primary
    print(json.dumps({'complete':True,'target_y':a.target_y,'result':report['boundary_result']['result']}),flush=True)

if __name__=='__main__':main()
