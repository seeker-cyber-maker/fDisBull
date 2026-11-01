"""Ordinary KQ1 lake refusal, wandering and room-exit retirement.

This is not the invisible-goat departure branch. Original resources, states,
raw traces and databases must remain in a fresh private directory outside Git.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import time

from examples.agi.spatial_trial import native_game, read, require, manifest
from examples.agi.verify_goat import GoatRun
from examples.agi.verify_troll import bind_carrot
from fdisbull.agi import load_logic
from fdisbull.agi_dos import _ENGINE_LENGTH, _ENGINE_SHA256


class GoatBranchesRun(GoatRun):
    guest_budget_ms=420000
    wall_budget_ms=360000

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        for n in (8,101):self.resources[n]=load_logic(self.source/'LOGDIR',self.source,n,profile='2.917')
        self.inventory=bind_carrot(self.d,self.source,self.cs,self.ds)
        self.report['inventory_binding']=self.inventory
        self.report['implementation_sha256']['examples/agi/verify_goat_branches.py']=sha256(Path(__file__).read_bytes()).hexdigest()
        self.report['implementation_sha256']['examples/agi/verify_troll.py']=sha256(Path(__file__).with_name('verify_troll.py').read_bytes()).hexdigest()
        self.watch=None;self.expected_effect=None;self.effects=[]

    def state(self):
        state=super().state();flags=read(self.d,self.ds+0x109,32)
        flag=lambda n:bool(flags[n//8]&(0x80>>(n%8)))
        table=int.from_bytes(read(self.d,self.ds+0x963,2),'little')
        motion=read(self.d,self.ds+table+43*13+34,1)[0]
        v=read(self.d,self.ds+9,256)
        state.update(carrot_carried=read(self.d,self.inventory['location_linear'],1)==b'\xff',
            water_refused=flag(66),goat_wandering=motion==1,goat_motion=motion,
            goat_retired=flag(130),water_departure=flag(213),invisible=flag(79),
            in_water=flag(0),swimming=v[94],edge=v[2],goat_distance=v[40])
        return state

    def observe(self,name):
        result=super().observe(name);s=self.observations[name]['native_state']
        self.observations[name]['state'].update({k:s[k] for k in
            ('carrot_carried','water_refused','goat_wandering','goat_retired','water_departure')})
        print(json.dumps({'observation':name,'state':self.observations[name]['state'],'guest_ms':self.guest_elapsed}),flush=True)
        return result

    def move(self,*args,**kwargs):
        before=self.state()['room'];state=super().move(*args,**kwargs)
        if state['room']!=before:
            print(json.dumps({'entered_room':state['room'],'ego':state['ego'],'goat':state['goat'],
                              'refused':state['water_refused'],'guest_ms':self.guest_elapsed}),flush=True)
        return state

    def message_observed(self,message):
        if (message['logic'],message['source_offset'],message['message_id'])==(103,375,1):
            require(self.watch is None and not any(p['branch']=='water-refusal' for p in self.effects),'Duplicate refusal occurrence')
            table=int.from_bytes(read(self.d,self.ds+0x963,2),'little')
            self.arm_effect('water-refusal',103,381,84,13,self.ds+table+43*13+34,0x6dcb,0x6dcf)

    def arm_effect(self,branch,logic,offset,opcode,argument,address,writer,resume):
        require(self.watch is None,'Previous owned effect watch remains active')
        require(sha256(read(self.d,self.cs*16,_ENGINE_LENGTH)).hexdigest()==_ENGINE_SHA256,'Effect interpreter differs')
        require(self.resources[logic].code[offset:offset+2]==bytes([opcode,argument]),'Effect source bytes differ')
        self.expected_effect={'branch':branch,'logic':logic,'offset':offset,'opcode':opcode,'argument':argument,
            'address':address,'writer':writer,'resume':resume,'before':self.state()}
        self.watch=self.d.call('breakpoints.create',{'kind':'w','once':False,
            'address':{'space':'linear','offset':f'0x{address:08X}'}})['breakpoint_id']

    def handle_stop(self,out):
        expected=self.expected_effect;reason=(out.get('session') or {}).get('stop_reason',{})
        access=reason.get('data_access',{});cause=access.get('instruction',{})
        require(expected is not None and self.watch is not None and reason.get('breakpoint_id')==self.watch
                and access.get('access')=='w','Foreign effect stop preserved')
        require(cause.get('space')=='segmented' and int(cause.get('segment','-1'),16)==self.cs
                and int(cause.get('offset','-1'),16)==expected['writer'],'Unexpected effect writer preserved')
        regs=self.d.registers()
        require(int(regs['segments']['cs'],16)==self.cs and int(regs['segments']['ds'],16)*16==self.ds
                and int(regs['instruction_pointer'],16)==expected['resume'],'Effect resume binding differs')
        record=int.from_bytes(read(self.d,self.ds+0x979,2),'little');desc=read(self.d,self.ds+record,10)
        code=int.from_bytes(desc[4:6],'little');resource=self.resources[expected['logic']]
        require(desc[2]==resource.logic and code+len(resource.code)<=65536 and
                read(self.d,self.ds+code,len(resource.code))==resource.code,'Effect resource binding differs')
        require(int(regs['general']['esi'],16)&65535==code+expected['offset']+2,'Effect source cursor differs')
        state=self.state()
        if expected['branch']=='water-refusal':
            table=int.from_bytes(read(self.d,self.ds+0x963,2),'little')
            require(int(regs['general']['edi'],16)&65535==table+43*13,'Wander selected another actor')
            require(expected['before']['goat_motion'] in (0,2) and state['goat_motion']==1
                    and state['water_refused'] and state['following'],'Water wander effect differs')
        else:
            require(expected['before']['following'] and not state['following']
                    and int(regs['general']['ebx'],16)&65535==0x112
                    and int(regs['general']['eax'],16)&255==0xef,'Water departure flag write differs')
        proof={'format':'fdisbull-agi-goat-branch-effect-1','branch':expected['branch'],'status':'incomplete',
            'complete':False,'native_execution':True,'source_logic':resource.logic,
            'source_logic_sha256':resource.resource_sha256,'source_offset':expected['offset'],
            'opcode':expected['opcode'],'argument':expected['argument'],
            'writer':{'offset':expected['writer'],'resume_offset':expected['resume']},
            'before':expected['before'],'after_access':state,'stop':out,'registers':regs,
            'source_binding':{'code_offset':code,'code_sha256':sha256(resource.code).hexdigest()}}
        self.effects.append(proof);path=self.root/(expected['branch']+'-effect.private.json')
        path.write_text(json.dumps(proof,indent=2)+'\n')
        self.d.call('breakpoints.delete',{'breakpoint_id':self.watch});self.watch=None
        try:
            proof['trace']=self.trace_effect(expected['branch'])
        except Exception as exc:
            proof['error']=str(exc);raise
        finally:path.write_text(json.dumps(proof,indent=2)+'\n')
        confirmed={**proof,'status':'verified','complete':True}
        path.write_text(json.dumps(confirmed,indent=2)+'\n');proof.update(confirmed)
        print(json.dumps({'effect':expected['branch'],'status':'verified','source_offset':expected['offset']}),flush=True)

    def trace_effect(self,branch):
        trace={'format':'fdisbull-agi-branch-continuation-1','events':[],'run':None,'complete':False,
               'scope':'Native fetch observations; instruction completion unknown.'}
        path=self.root/(branch+'-trace.private.json');primary=None;errors=[]
        self.d.call('trace.start',{'detail':'normal','instruction_count':32})
        try:
            guest,wall=self.remaining_limits(100,10000)
            attempt={'kind':'effect-trace','attempted':True,'branch':branch,'result':None};self.journal.append(attempt)
            result=self.d.run(guest_ms=guest,timeout_ms=wall,fast_forward=True,stop_on_hook=True)
            attempt['result']=result;trace['run']=result
            elapsed=result.get('guest_elapsed_ms');require(type(elapsed) in (int,float) and elapsed>=0,'Missing trace progress')
            self.guest_elapsed+=elapsed
            page=self.d.call('trace.read',{'cursor':None,'limit':64});trace['events']=page['events']
            require(not page.get('next_cursor') and len(trace['events'])==32 and result['outcome']=='pause','Effect trace interrupted or incomplete')
            require(self.guest_elapsed<=self.guest_budget_ms and time.monotonic()<self.deadline,'Route budget exhausted after trace')
            trace['complete']=True
        except BaseException as exc:primary=exc;raise
        finally:
            try:self.d.call('trace.stop')
            except Exception as exc:
                trace.setdefault('cleanup_errors',[]).append(str(exc));errors.append(exc)
            try:path.write_text(json.dumps(trace,indent=2)+'\n')
            except Exception as exc:errors.append(exc)
            if errors and primary is None:raise errors[0]
        return {'path':path.name,'sha256':sha256(path.read_bytes()).hexdigest(),'count':32}

    def effect_reference(self,branch):
        matches=[p for p in self.effects if p['branch']==branch]
        require(len(matches)==1 and matches[0]['complete'],'Missing qualified branch effect')
        path=self.root/(branch+'-effect.private.json')
        return {'path':path.name,'sha256':sha256(path.read_bytes()).hexdigest()}

    def route(self):
        super().route();before=self.actions[-1]['after'];i,m=len(self.inputs),len(self.messages)
        # The goat stands just below the pen-exit position. Step aside before
        # turning south; input delivery alone does not make that route clear.
        self.move('left',axis='x',target=125)
        self.move('down',room=8)
        self.move('right',axis='x',target=151)
        self.press('down',150)
        self.wait(lambda s:s['water_refused'] and s['goat_wandering'],'Original goat water refusal',8000)
        self.neutral();after=self.observe('water-refused')
        proof=self.effect_reference('water-refusal')
        require(self.state()['score']==7 and self.state()['following'] and self.state()['carrot_carried'],'Water refusal changed an unexpected fact')
        self.actions.append({'id':'lead-to-water','label':'lead the goat to the lake','verb':'use',
            'before':before,'after':after,'complete':True,'messages_complete':True,'inputs':self.inputs[i:],
            'messages':self.messages[m:],'native_branch_effect':proof})
        i,m=len(self.inputs),len(self.messages)
        self.command('swim')
        self.wait(lambda s:s['swimming']==2,'Original swimming command')
        self.move('left',axis='x',target=75)
        self.move('up',axis='y',target=50)
        s=self.state();require(s['water_refused'] and s['following'] and s['swimming']==0,'Goat recovered before departure; not a retirement route')
        self.arm_effect('water-departure',8,478,13,75,self.ds+0x112,0x7432,0x7434)
        self.move('up',room=9)
        self.wait(lambda s:not s['following'] and s['goat_retired'] and s['water_departure'] and not s['goat']['drawn'],'Original water departure retirement')
        end=self.observe('water-departure')
        require(self.state()['score']==7 and self.state()['carrot_carried'],'Departure changed score or carried carrot')
        self.actions.append({'id':'leave-water','label':'leave the wandering goat at the lake','verb':'use',
            'before':after,'after':end,'complete':True,'messages_complete':True,'inputs':self.inputs[i:],
            'messages':self.messages[m:],'native_branch_effect':self.effect_reference('water-departure')})
        return self.capture()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','backend','output'):parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args();source=args.source.resolve();root=args.output.resolve();checkout=Path(__file__).resolve().parents[2]
    require(root!=checkout and checkout not in root.parents,'Keep runtime data outside Git')
    driver=None
    try:
        with native_game('kq1',source,root,args.backend.resolve(),fair_play=True) as (p,d,obs,restore,frame,report,game):
            driver=GoatBranchesRun(p,d,report,frame,source,root)
            try:
                capture=driver.route();(root/'capture.private.json').write_text(json.dumps(capture,indent=2)+'\n')
                report['normal_water_departure_complete']=True
                print(json.dumps({'complete':True,'state':driver.state(),'visibility':'pending stored-frame inspection'}),flush=True)
            except Exception as exc:
                report['normal_water_departure_complete']=False;report['error']=str(exc);report['last_state']=driver.state()
                frame('failure.png');raise
            finally:
                for bp in (driver.bp,driver.watch):
                    if bp:d.call('breakpoints.delete',{'breakpoint_id':bp})
    finally:
        if driver:
            (root/'journal.private.json').write_text(json.dumps(driver.journal,indent=2)+'\n')
            (root/'partial-capture.private.json').write_text(json.dumps(driver.capture(),indent=2)+'\n')
            (root/'partial-effects.private.json').write_text(json.dumps(driver.effects,indent=2)+'\n')
            report=json.loads((root/'result.json').read_text());original=report['source_manifest']
            report['post_teardown_source_unchanged']=manifest(source)==original
            report['post_teardown_copy_unchanged']=manifest(root/'game')==original
            (root/'result.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
