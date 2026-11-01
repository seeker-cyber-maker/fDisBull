"""Qualify the KQ1 eastern bridge's southeast corner with ordinary inputs.

Numeric waypoints are source/PIC-derived hypotheses until the original guest
completes them. Outputs, input copies, states and databases must stay private.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from examples.agi.spatial_trial import native_game,read,require,manifest
from examples.agi.verify_goat import GoatRun
from fdisbull.agi import load_logic
from fdisbull.agi_dos import _ENGINE_LENGTH,_ENGINE_SHA256
from fdisbull.agi_layout import logic_layout
from fdisbull.agi_picture import extract_v2_resource,decode_picture
from fdisbull.scene_receipts import retain_evidence


class ClipRun(GoatRun):
    guest_budget_ms=300000
    wall_budget_ms=360000

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        for n in (8,39,40,41,42,101):self.resources[n]=load_logic(self.source/'LOGDIR',self.source,n,profile='2.917')
        require(sha256(read(self.d,self.cs*16,_ENGINE_LENGTH)).hexdigest()==_ENGINE_SHA256,'Unqualified original interpreter')
        self.samples=[];self.clip_observations={};self.clip_actions=[]
        self.predicate_proof=None
        self.picture=extract_v2_resource(self.source/'PICDIR',self.source,39)
        self.priority=decode_picture(self.picture['payload'])['priority']
        self.report['implementation_sha256']['examples/agi/verify_bridge_clip.py']=sha256(Path(__file__).read_bytes()).hexdigest()

    def state(self):
        state=super().state();flags=read(self.d,self.ds+0x109,32);v=read(self.d,self.ds+9,256)
        flag=lambda n:bool(flags[n//8]&(0x80>>(n%8)))
        table=int.from_bytes(read(self.d,self.ds+0x963,2),'little');actor=read(self.d,self.ds+table,43)
        state.update(in_water=flag(0),on_trigger=flag(3),swimming=v[94],dead=flag(63),
            bridge_active=flag(21),troll_removed=flag(150),troll_paid=flag(151),
            ego_width=int.from_bytes(actor[26:28],'little'),ego_view=actor[7],step_size=actor[30],edge=v[2])
        return state

    def safe_state(self):
        s=self.state();self.samples.append({'guest_ms':self.guest_elapsed,'state':s})
        require(not s['in_water'] and not s['swimming'] and not s['dead'],'Clip route entered water or death')
        require(not s['bridge_active'] and not s['troll_removed'] and not s['troll_paid']
                and s['score']==0,'Clip route activated or resolved the troll encounter')
        require(s['ego_width']==6 and s['ego_view']==0 and s['step_size']==1,'Unqualified walking footprint or step size')
        return s

    def precise(self,*,x=None,y=None):
        """One axis or a unit diagonal, sampled without changing guest state."""
        previous=self.fast_forward;self.fast_forward=False
        try:return self._precise(x=x,y=y)
        finally:self.fast_forward=previous

    def _precise(self,*,x=None,y=None):
        self.ready();start=self.safe_state();a=start['ego'];targets={k:v for k,v in (('x',x),('y',y)) if v is not None}
        require(bool(targets),'Missing waypoint')
        dx=0 if x is None else x-a['x'];dy=0 if y is None else y-a['y']
        if dx==dy==0:return start
        require(not (dx and dy) or abs(dx)==abs(dy),'Only straight or equal-axis diagonal waypoints')
        sx=(dx>0)-(dx<0);sy=(dy>0)-(dy<0)
        key={(0,-1):'up',(1,-1):'pageup',(1,0):'right',(1,1):'pagedown',
             (0,1):'down',(-1,1):'end',(-1,0):'left',(-1,-1):'home'}[(sx,sy)]
        self.press(key,20,hold_ms=1,gap_ms=1);end=self.guest_elapsed+20000;last=None;still=0
        while self.guest_elapsed<end:
            s=self.safe_state();p=s['ego'];require(s['room']==start['room'],'Waypoint changed room unexpectedly')
            if all(p[k]==v for k,v in targets.items()):
                self.neutral();final=self.safe_state()
                require(all(final['ego'][k]==v for k,v in targets.items()),'Waypoint did not settle precisely')
                return final
            require((not sx or (p['x']-x)*sx<=0) and (not sy or (p['y']-y)*sy<=0),'Waypoint overshoot')
            point=(p['x'],p['y']);still=still+1 if point==last else 0;last=point
            require(still<150,'Precise route blocked')
            self.advance(10)
        raise RuntimeError('Precise waypoint budget exhausted')

    def observe_clip(self,name):
        previous=self.d.screenshot(name+'-initial.png',hooks=False)['metadata'];self.advance(50)
        s=self.safe_state();frame=self.frame(name+'.png')
        require(frame['metadata']['frame_id']>previous['frame_id'] and frame['metadata']['mode_id']==previous['mode_id'],'Clip frame not fresh')
        record={'state':s,'frame':{'path':name+'.png','sha256':frame['sha256'],'metadata':frame['metadata']}}
        self.clip_observations[name]=record
        print(json.dumps({'observation':name,'room':s['room'],'ego':s['ego'],'score':s['score'],'guest_ms':self.guest_elapsed}),flush=True)
        return name

    def action(self,name,before,after,i,m):
        self.clip_actions.append({'id':name,'before':before,'after':after,'complete':True,
            'messages_complete':True,'inputs':self.inputs[i:],'messages':self.messages[m:]})

    def observe_corner_predicate(self,*,control_input=None):
        """Observe the original posn handler, its return and source successor."""
        control=control_input is not None;position=(72,87) if control else (72,88)
        s=self.safe_state()
        require(s['room']==39 and (s['ego']['x'],s['ego']['y'])==((73,88) if control else position)
            and (control or self._idle()),'Unqualified predicate position/input')
        require(read(self.d,self.ds+0x921,4)==bytes.fromhex('c6080500'),'Original posn table differs')
        resource=self.resources[39]
        require(resource.code[0x410:0x416]==bytes.fromhex('0b0048544857'),'Target posn source differs')
        proof={'format':'fdisbull-agi-posn-observation-1','status':'incomplete','complete':False,
            'native_execution':False,'source_logic':39,'source_logic_sha256':resource.resource_sha256,
            'condition_offset':0x410,'arguments':[0,72,84,72,87],
            'input_position':{'x':position[0],'y':position[1],'width':6},'handler_entry_offset':0x8c6,
            'return_offset':0x7fb,'call_frame_verified':False,'handler_return_observed':False,
            'false_continuation_observed':False,'result':None,'search':[]}
        self.predicate_proof=proof;path=self.root/'corner-predicate.private.json'
        path.write_text(json.dumps(proof,indent=2)+'\n');owned=[];tracing=False;trace=None;primary=None
        def bp(offset):
            item=self.d.call('breakpoints.create',{'kind':'execution','once':False,
                'address':{'space':'segmented','segment':f'0x{self.cs:04X}','offset':f'0x{offset:08X}'}})['breakpoint_id']
            owned.append(item);return item
        def remove(item):
            self.d.call('breakpoints.delete',{'breakpoint_id':item});owned.remove(item)
        def run(kind):
            guest,wall=self.remaining_limits(100,5000)
            attempt={'kind':kind,'attempted':True,'result':None};self.journal.append(attempt)
            out=self.d.run(guest_ms=guest,timeout_ms=wall,fast_forward=True,stop_on_hook=True)
            attempt['result']=out;elapsed=out.get('guest_elapsed_ms')
            require(type(elapsed) in (int,float) and elapsed>=0,'Missing predicate guest progress')
            self.guest_elapsed+=elapsed;self.remaining_limits()
            return out
        def site():
            regs=self.d.registers()
            require(int(regs['segments']['cs'],16)==self.cs and int(regs['segments']['ds'],16)*16==self.ds,'Predicate segments changed')
            rec=int.from_bytes(read(self.d,self.ds+0x979,2),'little');desc=read(self.d,self.ds+rec,10)
            number=desc[2];code=int.from_bytes(desc[4:6],'little')
            require(number in self.resources,'Uncaptured predicate source logic')
            source=self.resources[number]
            require(code+len(source.code)<=65536 and read(self.d,self.ds+code,len(source.code))==source.code,'Predicate loaded source changed')
            return regs,source,code
        def owned_stop(out,ids):
            reason=(out.get('session') or {}).get('stop_reason',{})
            return out['outcome']=='breakpoint' and reason.get('breakpoint_id') in ids and not reason.get('data_access')
        try:
            entry=bp(0x8c6);selected=None
            for _ in range(128):
                out=run('predicate-entry-search');proof['search'].append(out)
                if out['outcome']=='guest_time':continue
                require(owned_stop(out,[entry]),'Foreign predicate search stop preserved')
                regs,source,code=site();off=(int(regs['general']['esi'],16)&65535)-code-1
                layout=logic_layout(source.payload)
                require(off+2 in layout['conditions'] and layout['conditions'][off+2]['opcode']==11,'Posn entry not at a source condition')
                ss=int(regs['segments']['ss'],16)*16;sp=int(regs['general']['esp'],16)&65535
                require(sp<=65529 and read(self.d,ss+sp,2)==bytes.fromhex('fb07'),'Posn dispatch return differs')
                if source.logic==39 and off==0x410:
                    observed=self.safe_state()
                    if (observed['ego']['x'],observed['ego']['y'])!=position:continue
                    require(read(self.d,ss+sp,6)==bytes.fromhex('fb0793290001'),'Selected OR call frame differs')
                    require(observed['ego']['drawn'] and self._idle(),'Predicate actor/input not settled')
                    if not control:require(observed['ego']==s['ego'],'Predicate position changed during search')
                    if control:control_input['complete']=True
                    selected=(regs,code,ss,sp);break
            require(selected is not None,'Target predicate occurrence not observed')
            regs,code,ss,sp=selected
            proof.update(call_frame_verified=True,native_execution=True,entry_registers=regs,code_offset=code)
            path.write_text(json.dumps(proof,indent=2)+'\n')
            remove(entry);returned=bp(0x7fb)
            self.d.call('trace.start',{'detail':'normal','instruction_count':128});tracing=True
            trace={'format':'fdisbull-agi-posn-trace-1','maximum_count':128,'runs':[],'events':[],'complete':False,
                'scope':'Original native fetch observations; handler/continuation evidence is separate from instruction completion.'}
            out=run('predicate-handler-return');trace['runs'].append(out)
            require(owned_stop(out,[returned]),'Original predicate return interrupted')
            after,source,current_code=site()
            require(source.logic==39 and current_code==code and int(after['instruction_pointer'],16)==0x7fb
                and int(after['general']['esp'],16)&65535==sp+2 and int(after['general']['esi'],16)&65535==code+0x416,
                'Original predicate return binding differs')
            proof.update(handler_return_observed=True,result=bool(int(after['general']['eax'],16)&255),return_registers=after)
            require(proof['result'] is control,'Original trap predicate returned an unexpected value')
            remove(returned);fetches=[bp(0x294a),bp(0x303)]
            out=run('predicate-source-continuation');trace['runs'].append(out)
            require(owned_stop(out,fetches),'Original predicate continuation interrupted')
            after,source,current_code=site();off=(int(after['general']['esi'],16)&65535)-code
            require(source.logic==39 and current_code==code and off==(0x41a if control else 0x41e),'Original predicate took an unexpected source successor')
            proof.update(false_continuation_observed=not control,branch_continuation_observed=True,continuation_source_offset=off)
            page=self.d.call('trace.read',{'cursor':None,'limit':256});trace['events']=page['events']
            require(not page.get('next_cursor') and 0<len(trace['events'])<128,'Predicate trace incomplete or exhausted')
            trace['complete']=True
        except BaseException as exc:primary=exc;proof['error']=str(exc);raise
        finally:
            errors=[]
            if tracing:
                try:self.d.call('trace.stop')
                except Exception as exc:errors.append(exc)
            for item in list(owned):
                try:remove(item)
                except Exception as exc:errors.append(exc)
            if trace is not None:
                tpath=self.root/'corner-predicate-trace.private.json'
                try:
                    tpath.write_text(json.dumps(trace,indent=2)+'\n')
                    proof['trace']={'path':tpath.name,'sha256':sha256(tpath.read_bytes()).hexdigest(),
                        'event_count':len(trace['events']),'maximum_count':128}
                except Exception as exc:errors.append(exc)
            if errors:proof['cleanup_errors']=[str(e) for e in errors]
            try:path.write_text(json.dumps(proof,indent=2)+'\n')
            except Exception as exc:
                errors.append(exc)
                self.report.setdefault('persistence_errors',[]).append({'operation':'predicate receipt','error':str(exc)})
            if errors and primary is None:raise errors[0]
        confirmed={**proof,'status':'verified','complete':True}
        path.write_text(json.dumps(confirmed,indent=2)+'\n');self.predicate_proof=confirmed
        return {'path':path.name,'sha256':sha256(path.read_bytes()).hexdigest()}

    def route(self,*,adjacent_control=False):
        require(self.state()['room']==1 and self.state()['score']==0,'Fresh opening required')
        self.move('right',room=8);self.move('right',axis='x',target=70)
        self.move('down',room=41);self.move('right',room=42)
        self.precise(y=51)
        # Ordinary stone-bridge route to the southeast approach. The close
        # staircase follows the source control plane; no zip or state edit.
        for x,y in ((99,51),(99,65),(106,65),(106,89),(108,89),(108,90),
                    (111,90),(111,91),(112,91),(112,92),(113,92),(113,160)):
            current=self.state()['ego']
            self.precise(**({'x':x} if x!=current['x'] else {'y':y}))
        self.move('down',room=39);self.precise(x=130);self.precise(y=100);self.precise(x=85)
        before=self.observe_clip('clip-before');i,m=len(self.inputs),len(self.messages)
        if adjacent_control:
            self.precise(x=73);self.precise(y=88)
            require(self._idle(),'Control keyboard not idle')
            item={'kind':'keyboard','key':'press:home','delivered':None,'complete':False}
            self.inputs.append(item);self.journal.append({'kind':'input','record':item})
            item['delivery']=self.d.keyboard_press('home',hold_ms=1,gap_ms=1)
            item['delivered']=item['delivery'].get('accepted');require(item['delivered'] is True,'Control input not accepted')
            proof=self.observe_corner_predicate(control_input=item)
            for _ in range(30):
                self.advance(10);state=self.state()
                if state['in_water']:
                    require(state['room']==39 and (state['ego']['x'],state['ego']['y'])==(72,87),'Control water at unexpected position')
                    frame=self.frame('adjacent-control.png')
                    result={'complete':True,'result':'adjacent-origin-script-water','state':state,
                        'native_predicate':proof,'frame':{'path':'adjacent-control.png','sha256':frame['sha256'],'metadata':frame['metadata']}}
                    self.report['adjacent_control']=result
                    return self.capture()
            raise RuntimeError('Original adjacent guard did not commit the water flag')
        self.precise(x=73);self.precise(y=89);self.precise(x=72,y=88)
        corner=self.observe_clip('clip-corner');self.action('approach-corner',before,corner,i,m)
        i,m=len(self.inputs),len(self.messages)
        predicate=self.observe_corner_predicate()
        self.precise(x=71,y=87);self.precise(x=10)
        bank=self.observe_clip('clip-bank');self.action('cross-gap',corner,bank,i,m)
        self.clip_actions[-1]['native_predicate']=predicate
        i,m=len(self.inputs),len(self.messages);self.move('left',room=40)
        final=self.observe_clip('clip-complete');self.action('leave-bridge',bank,final,i,m)
        require(self.state()['room']==40,'Did not reach gnome room')
        return self.capture()

    def capture(self):
        base=super().capture()
        if hasattr(self,'clip_observations'):
            base.update(format='fdisbull-agi-bridge-clip-capture-1',observations=self.clip_observations,
                actions=self.clip_actions,samples=self.samples,picture={'room':39,'sha256':self.picture['sha256']})
        return base


def retain_private_evidence(driver,source,root,report):
    """Try every independent receipt/hash operation without replacing a primary."""
    operations=[]
    def write(name,value):
        (root/name).write_text(json.dumps(value,indent=2)+'\n')
    if driver is not None:
        operations.append(('journal',lambda:write('journal.private.json',driver.journal)))
        operations.append(('partial capture',lambda:write('partial-capture.private.json',driver.capture())))
        if driver.predicate_proof:
            operations.append(('partial predicate',lambda:write('partial-predicate.private.json',driver.predicate_proof)))
    def integrity(path,field):
        report[field]=manifest(path)==report['source_manifest']
        require(report[field],'Post-teardown files changed: '+field)
    operations.extend([('source integrity',lambda:integrity(source,'post_teardown_source_unchanged')),
                       ('copy integrity',lambda:integrity(root/'game','post_teardown_copy_unchanged')),
                       ('final receipt',lambda:write('result.json',report))])
    return retain_evidence(operations,report)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','backend','output'):parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--adjacent-control',action='store_true')
    args=parser.parse_args();source=args.source.resolve();root=args.output.resolve();checkout=Path(__file__).resolve().parents[2]
    require(root!=checkout and checkout not in root.parents,'Keep runtime data outside Git')
    require(root!=source and source not in root.parents,'Keep runtime data outside original source')
    driver=None;report=None;primary=None
    def secondary(operation,fn):
        nonlocal primary
        try:fn()
        except Exception as exc:
            if primary is None:primary=exc
            report.setdefault('persistence_errors',[]).append({'operation':operation,'error':str(exc)})
    try:
        with native_game('kq1',source,root,args.backend.resolve(),fair_play=True) as (p,d,obs,restore,frame,report,game):
            driver=ClipRun(p,d,report,frame,source,root)
            try:
                capture=driver.route(adjacent_control=args.adjacent_control);(root/'capture.private.json').write_text(json.dumps(capture,indent=2)+'\n')
                report['normal_clip_complete']=not args.adjacent_control;report['final_state']=driver.state()
            except BaseException as exc:
                primary=exc;report['normal_clip_complete']=False;report['error']=str(exc)
                secondary('failure state',lambda:report.update(last_state=driver.state()))
                secondary('failure frame',lambda:frame('failure.png'))
            finally:
                if driver.bp:secondary('print breakpoint cleanup',lambda:d.call('breakpoints.delete',{'breakpoint_id':driver.bp}))
    except BaseException as exc:
        if primary is None:primary=exc
        elif report is not None:report.setdefault('persistence_errors',[]).append({'operation':'native context cleanup','error':str(exc)})
    finally:
        if report is not None:
            errors=retain_private_evidence(driver,source,root,report)
            if errors and primary is None:primary=errors[0]
    if primary is not None:raise primary
    print(json.dumps({'complete':True,'control':args.adjacent_control,'state':report['final_state']}),flush=True)


if __name__=='__main__':main()
