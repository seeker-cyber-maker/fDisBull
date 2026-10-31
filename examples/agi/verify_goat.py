"""Reach KQ1's goat through ordinary inputs; keep all captures private.

Exact supplied AGI 2.917 edition only. No guest state/code/register edits,
teleports, native-state restore or redirected calls are used. Source-bound
print observation pauses original execution, then uses one physical Enter.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import time

from examples.agi.spatial_trial import native_game, read, require, manifest
from fdisbull.agi import load_logic
from fdisbull.agi_print import AGIDOSPrintObserver
from fdisbull.agi_dos import AGIDOSMonitor, FETCH
from fdisbull.agi_host import AGIDOSHostAdapter, capture_state
from fdisbull.agi_lift import lift_logic
from examples.agi.verify_host import NAMES

DIRECTIONS = {1:'up',2:'pageup',3:'right',4:'pagedown',5:'down',6:'end',7:'left',8:'home'}


class GoatRun:
    def __init__(self,p,d,report,frame,source,root):
        self.p,self.d,self.report,self.frame,self.source,self.root=p,d,report,frame,source,root
        self.cs=int(report['resolution']['registers']['segments']['cs'],16)
        self.ds=int(report['resolution']['ds_linear'],16)
        self.resources={n:load_logic(source/'LOGDIR',source,n,profile='2.917') for n in (0,1,9,10,11,16,103)}
        self.journal=[];self.messages=[];self.inputs=[];self.observations={};self.actions=[]
        checkout=Path(__file__).resolve().parents[2]
        report['implementation_sha256']={name:sha256((checkout/name).read_bytes()).hexdigest() for name in
            ('examples/agi/verify_goat.py','src/fdisbull/agi_print.py','src/fdisbull/agi_host.py','src/fdisbull/agi_dos.py','src/fdisbull/agi_resources.py')}
        self.deadline=time.monotonic()+180;self.guest_elapsed=0;self.bp=None
        self._arm()

    def _arm(self):
        self.bp=self.d.call('breakpoints.create',{'kind':'execution','once':False,
            'address':{'space':'segmented','segment':f'0x{self.cs:04X}','offset':'0x00001C06'}})['breakpoint_id']

    def state(self):
        v=read(self.d,self.ds+9,256);f=read(self.d,self.ds+0x109,32)
        table=int.from_bytes(read(self.d,self.ds+0x963,2),'little')
        def obj(n):
            b=read(self.d,self.ds+table+43*n,43)
            return {'x':int.from_bytes(b[3:5],'little',signed=True),'y':int.from_bytes(b[5:7],'little',signed=True),'direction':b[33],'drawn':bool(b[37]&1)}
        flag=lambda n:bool(f[n//8]&(0x80>>(n%8)))
        return {'room':v[0],'score':v[3],'carrot':flag(77),'following':flag(75),'gate_open':flag(78),
                'ego':obj(0),'goat':obj(13),'gate_actor':obj(1),'inside_pen':flag(74),'control_direction':v[6],
                'distance':v[70],'initializing':flag(5),'window':int.from_bytes(read(self.d,self.ds+0xd15,2),'little')}

    def advance(self,ms=100):
        end=self.guest_elapsed+ms
        while self.guest_elapsed<end:
            require(time.monotonic()<self.deadline and self.guest_elapsed<240000,'Route budget exhausted')
            attempt={'kind':'run','attempted':True,'result':None};self.journal.append(attempt)
            out=self.d.run(guest_ms=min(100,end-self.guest_elapsed),timeout_ms=10000,fast_forward=True,stop_on_hook=True)
            attempt['result']=out;elapsed=out.get('guest_elapsed_ms')
            require(type(elapsed) in (int,float) and elapsed>=0,'Missing guest progress')
            self.guest_elapsed+=elapsed
            if out['outcome']=='breakpoint':
                stop=(out.get('session') or {}).get('stop_reason',{})
                require(stop.get('breakpoint_id')==self.bp and not stop.get('data_access'),'Foreign stop preserved')
                observer=AGIDOSPrintObserver(self.d,self.resources,cs=self.cs,ds=self.ds//16)
                self.d.call('breakpoints.delete',{'breakpoint_id':self.bp});self.bp=None
                msg=observer.finish(frame_name=f'goat-message-{len(self.messages)}')
                self.messages.append(msg);self.journal.append({'kind':'message','observation':msg})
                require(observer.readback()==msg and observer.finish()==msg,'Message readback replayed')
                if msg.get('frame'):
                    item=msg['frame'];name=f'message-{len(self.messages)-1}.png';self.p.debug_export(item['artifact'],self.root/name)
                    msg['frame']={'path':name,'sha256':item['sha256'],'metadata':item['metadata']}
                self.guest_elapsed+=sum(s.get('guest_elapsed_ms',0) for s in msg['stops'])
                require(msg['status']=='completed','Original message did not complete: '+str(msg.get('error')))
                self._arm()
            else:require(out['outcome']=='guest_time','Unexpected native stop preserved')
        return self.state()

    def _idle(self):
        k=self.d.keyboard_state().get('keyboard',{})
        return all(type(k.get(n)) is int and k[n]==0 for n in ('pending_events','owned_keys','queued_guest_ms'))

    def press(self,key,ms=150,*,hold_ms=60,gap_ms=50):
        require(self._idle(),'Existing keyboard input is not settled')
        item={'kind':'keyboard','key':'press:'+key,'delivered':None,'complete':False}
        self.inputs.append(item);self.journal.append({'kind':'input','record':item})
        receipt=self.d.keyboard_press(key,hold_ms=hold_ms,gap_ms=gap_ms);item['delivery']=receipt
        item['delivered']=receipt.get('accepted') if type(receipt.get('accepted')) is bool else None
        self.advance(max(ms,hold_ms+gap_ms));item['complete']=self._idle();require(item['delivered'] and item['complete'],'Key outcome unknown')

    def command(self,text):
        require(self._idle(),'Existing keyboard input is not settled')
        item={'kind':'keyboard','key':'type:'+text,'delivered':None,'complete':False}
        self.inputs.append(item);self.journal.append({'kind':'input','record':item})
        receipt=self.d.keyboard_type(text,hold_ms=30,gap_ms=30);item['delivery']=receipt
        item['delivered']=receipt.get('accepted') if type(receipt.get('accepted')) is bool else None
        self.advance(len(text)*60+150);item['complete']=self._idle();require(item['delivered'] and item['complete'],'Text outcome unknown')
        self.press('enter',300,hold_ms=30,gap_ms=30)

    def neutral(self):
        state=self.state()
        if state['ego']['direction']:self.press(DIRECTIONS[state['ego']['direction']])
        require(self.state()['ego']['direction']==0,'Original movement did not settle')

    def ready(self):
        for _ in range(30):
            s=self.state()
            if not s['initializing'] and s['ego']['drawn'] and not s['window']:
                self.neutral();return self.state()
            self.advance(100)
        raise RuntimeError('Room readiness budget exhausted')

    def wait(self,predicate,label,budget=3000):
        end=self.guest_elapsed+budget
        while True:
            state=self.state()
            if predicate(state):return state
            require(self.guest_elapsed<end,label+' did not complete within budget')
            self.advance(50)

    def move(self,key,*,axis=None,target=None,room=None,budget=25000):
        self.ready();start=self.state()
        if axis:
            if abs(start['ego'][axis]-target)<=1:return start
            key=('right' if target>start['ego'][axis] else 'left') if axis=='x' else ('down' if target>start['ego'][axis] else 'up')
        self.press(key,50);deadline=self.guest_elapsed+budget;stationary=0;last=None
        sign=1 if key in ('right','down') else -1
        while self.guest_elapsed<deadline:
            s=self.state();pos=(s['ego']['x'],s['ego']['y'],s['room'])
            if s['room']!=start['room'] or (axis and (s['ego'][axis]-target)*sign>=0):break
            stationary=stationary+1 if pos==last else 0;last=pos
            require(stationary<15,'Route blocked before destination')
            self.advance(100)
        else:raise RuntimeError('Movement budget exhausted')
        self.ready();s=self.state()
        if room is not None:require(s['room']==room,'Unexpected room transition')
        if axis and s['room']==start['room']:require(abs(s['ego'][axis]-target)<=4,'Waypoint overshoot')
        return s

    def observe(self,name):
        previous=self.d.screenshot(name+'-initial.png',hooks=False)['metadata'];self.advance(50)
        s=self.state();item=self.frame(name+'.png')
        require(item['metadata']['frame_id']>previous['frame_id'] and item['metadata']['mode_id']==previous['mode_id'],'Observation frame is not fresh')
        self.observations[name]={'state':{k:s[k] for k in ('room','score','carrot','following','gate_open')},
            'goat_visible':None,'frame':{'path':name+'.png','sha256':item['sha256'],'metadata':item['metadata']},
            'native_state':s,'visibility_qualification':'pending operator inspection; drawn flag alone is insufficient'}
        return name

    def qualify_follow(self):
        """Observe a naturally entered leaf; never redirect a source call."""
        self.d.call('breakpoints.delete',{'breakpoint_id':self.bp});self.bp=None
        entry=self.d.call('breakpoints.create',{'kind':'execution','once':False,
            'address':{'space':'segmented','segment':f'0x{self.cs:04X}','offset':f'0x{FETCH:08X}'}})['breakpoint_id']
        found=None;start=time.monotonic()
        try:
            for _ in range(2048):
                require(time.monotonic()-start<30,'Natural logic entry wall budget exhausted')
                require(time.monotonic()<self.deadline and self.guest_elapsed<240000,'Route budget exhausted at natural entry')
                stop=self.d.run(guest_ms=100,timeout_ms=5000,fast_forward=True,stop_on_hook=True)
                self.journal.append({'kind':'entry-search','result':stop});self.guest_elapsed+=stop.get('guest_elapsed_ms',0)
                reason=(stop.get('session') or {}).get('stop_reason',{})
                require(stop['outcome']=='breakpoint' and reason.get('breakpoint_id')==entry,'Natural entry interrupted')
                record=int.from_bytes(read(self.d,self.ds+0x979,2),'little');desc=read(self.d,self.ds+record,8)
                r=self.d.registers();code=int.from_bytes(desc[4:6],'little')
                if desc[2]==103 and int(r['general']['esi'],16)&65535==code:
                    found=code;break
            require(found is not None,'Natural logic103 entry not observed')
        finally:self.d.call('breakpoints.delete',{'breakpoint_id':entry})
        guest_left=min(10000,int(240000-self.guest_elapsed))
        wall_left=min(60000,int((self.deadline-time.monotonic())*1000))
        require(guest_left>0 and wall_left>0,'Route budget exhausted before natural comparison')
        monitor=AGIDOSMonitor(self.d,self.resources[103],cs=self.cs,ds=self.ds//16,code_offset=found,
            guest_ms=min(1000,guest_left),timeout_ms=min(10000,wall_left),
            total_guest_ms=guest_left,total_timeout_ms=wall_left)
        projection=lift_logic(self.resources[103],initial_state=capture_state(monitor,NAMES),control_flow='compact',effect_profile='agi-2.917')
        adapter=AGIDOSHostAdapter(monitor,projection,viewdir=self.source/'VIEWDIR',volume_dir=self.source,dialogue_key='enter')
        trial=adapter.run();self.guest_elapsed+=guest_left-monitor.guest_remaining
        self.journal.append({'kind':'natural-follow-invocation','trial':trial})
        variants=self.root/'native-view-versions';variants.mkdir(exist_ok=False)
        for digest,payload in adapter.native_view_captures.items():
            (variants/(digest+'.bin')).write_bytes(payload)
        path=self.root/'natural-follow.private.json';path.write_text(json.dumps(trial,indent=2)+'\n')
        require(adapter.readback()==trial and trial['status']=='verified' and trial['complete'] and trial['differences']==[],'Natural follow model comparison incomplete')
        self._arm()
        return {'path':path.name,'sha256':sha256(path.read_bytes()).hexdigest()}

    def route(self):
        require(self.state()['room']==1 and self.state()['score']==0,'Fresh opening required')
        self.move('up',axis='y',target=40,room=16)
        self.move('up',axis='y',target=140);self.command('get carrot')
        self.wait(lambda s:s['carrot'] and s['score']==2,'Carrot commitment')
        self.observe('carrot-acquired')
        self.move('down',axis='y',target=160)
        for room in (9,10,11):self.move('right',room=room)
        self.move('right',axis='x',target=26);self.command('open gate')
        self.wait(lambda s:s['gate_open'],'Gate motion',5000)
        self.move('up',axis='y',target=110)
        # Goat roaming chooses either pen half. Approach it using real arrows.
        for _ in range(80):
            s=self.state()
            if s['goat']['drawn'] and s['distance']<25:break
            if not s['goat']['drawn']:
                self.move('left' if s['room']==11 else 'right',room=10 if s['room']==11 else 11)
            else:
                dx=s['goat']['x']-s['ego']['x'];dy=s['goat']['y']-s['ego']['y']
                key=('right' if dx>0 else 'left') if abs(dx)>=abs(dy) else ('down' if dy>0 else 'up')
                self.press(key,250);self.neutral()
        else:raise RuntimeError('Goat approach budget exhausted')
        before=self.observe('before-carrot');i,m=len(self.inputs),len(self.messages)
        self.command('show carrot')
        self.wait(lambda s:s['following'] and s['score']==7,'Goat following commitment')
        after=self.observe('following')
        self.actions.append({'id':'show-carrot','label':'show the carrot to the goat','verb':'use',
            'before':before,'after':after,'complete':True,'messages_complete':True,
            'inputs':self.inputs[i:],'messages':self.messages[m:]})
        i,m=len(self.inputs),len(self.messages)
        if self.state()['room']==10:
            # The south fence slopes across the western half. Move east inside
            # it before approaching the clear crossing to the other pen half.
            self.move('right',axis='x',target=120)
            self.move('down',axis='y',target=120);self.move('right',room=11)
        if self.state()['ego']['x']<20:self.move('right',axis='x',target=20)
        elif self.state()['ego']['x']>20:self.move('left',axis='x',target=20)
        self.move('down',axis='y',target=160)
        self.move('left',room=10);self.move('left',room=9)
        invocation=self.qualify_follow()
        end=self.observe('outside-pen')
        require(self.state()['following'] and self.state()['score']==7,'Goat did not continue following')
        self.actions.append({'id':'leave-pen','label':'lead the goat out of the pen','verb':'use',
            'before':after,'after':end,'complete':True,'messages_complete':True,
            'inputs':self.inputs[i:],'messages':self.messages[m:],'native_invocation':invocation})
        return self.capture()

    def capture(self):
        return {'format':'fdisbull-agi-natural-encounter-1',
            'source':{'agi_sha256':sha256((self.source/'AGI').read_bytes()).hexdigest(),'resources':{str(n):r.resource_sha256 for n,r in self.resources.items()}},
            'runtime':{'policy':'physical','fresh_game':True,'interventions':[],'session_id':self.d.session_id,'guest_elapsed_ms':self.guest_elapsed},
            'observations':self.observations,'actions':self.actions}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,type=Path);parser.add_argument('--backend',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();source=args.source.resolve();root=args.output.resolve();checkout=Path(__file__).resolve().parents[2]
    require(root!=checkout and checkout not in root.parents,'Keep runtime inputs and captures outside Git')
    driver=None
    try:
        with native_game('kq1',source,root,args.backend.resolve(),fair_play=True) as (p,d,obs,restore,frame,report,game):
            driver=GoatRun(p,d,report,frame,source,root)
            try:
                capture=driver.route();(root/'capture.private.json').write_text(json.dumps(capture,indent=2)+'\n')
                report['natural_goat_complete']=True;print(json.dumps({'complete':True,'state':driver.state(),'messages':len(driver.messages),'visibility':'pending operator inspection'}),flush=True)
            except Exception as exc:
                report['natural_goat_complete']=False;report['error']=str(exc);report['last_state']=driver.state()
                driver.frame('failure.png')
                raise
            finally:
                if driver.bp:d.call('breakpoints.delete',{'breakpoint_id':driver.bp})
    finally:
        if driver:
            (root/'journal.private.json').write_text(json.dumps(driver.journal,indent=2)+'\n')
            (root/'partial-capture.private.json').write_text(json.dumps(driver.capture(),indent=2)+'\n')
            receipt=json.loads((root/'result.json').read_text());original=receipt['source_manifest']
            receipt['post_teardown_source_unchanged']=manifest(source)==original
            receipt['post_teardown_copy_unchanged']=manifest(root/'game')==original
            (root/'result.json').write_text(json.dumps(receipt,indent=2)+'\n')


if __name__=='__main__':main()
