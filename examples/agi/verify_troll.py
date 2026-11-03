"""Continue the fresh, physical KQ1 goat route through the troll bridge.

Supply the exact licensed AGI 2.917 edition. All outputs, including the native
trace and unchanged game copy, belong in a fresh private directory outside Git.
No state is restored and no guest data, code, coordinates or registers are set.
The original game itself positions the goat for its scripted bridge encounter.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import time

from examples.agi.spatial_trial import native_game, read, require, manifest
from examples.agi.verify_goat import GoatRun
from fdisbull.agi import load_logic
from fdisbull.agi_dos import _ENGINE_LENGTH, _ENGINE_SHA256

OBJECT_SHA256='2d1b7a75bb443b4a340cb8d9a2842ff5c834d7d597ea2a1365b6a7a2dfb57985'
SCORE_WRITER=bytes.fromhex('32ffac8ad8ac008709008bc6c3')


def bind_carrot(session,source,cs,ds):
    """Qualify the carried-item read separately from the story's f77 flag."""
    require(sha256((source/'OBJECT').read_bytes()).hexdigest()==OBJECT_SHA256,'Unqualified inventory source')
    require(sha256(read(session,cs*16,_ENGINE_LENGTH)).hexdigest()==_ENGINE_SHA256,'Unqualified inventory interpreter')
    require(read(session,cs*16+0x7601,2)==b'\x03\x00','Inventory stride differs')
    base=int.from_bytes(read(session,ds+0x969,2),'little')
    end=int.from_bytes(read(session,ds+0x96b,2),'little')
    require(0<base<end<=65536 and end-base==81,'Inventory record bounds differ')
    require(base+0x67<=65536,'Inventory name outside data segment')
    require(read(session,ds+base+9,2)==b'\x60\x00' and read(session,ds+base+0x60,7)==b'carrot\0','Carrot source name binding differs')
    return {'source_sha256':OBJECT_SHA256,'base':base,'end':end,'stride':3,'item':3,
            'name_offset':0x60,'location_linear':ds+base+11,'carried_value':255}


class TrollRun(GoatRun):
    guest_budget_ms=420000
    wall_budget_ms=360000

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        for n in (24,25):self.resources[n]=load_logic(self.source/'LOGDIR',self.source,n,profile='2.917')
        self.inventory=bind_carrot(self.d,self.source,self.cs,self.ds)
        self.report['inventory_binding']=self.inventory
        self.report['implementation_sha256']['examples/agi/verify_troll.py']=sha256(Path(__file__).read_bytes()).hexdigest()
        self.watch=None;self.score_write=None

    def state(self):
        state=super().state();flags=read(self.d,self.ds+0x109,32)
        flag=lambda n:bool(flags[n//8]&(0x80>>(n%8)))
        state.update(carrot_carried=read(self.d,self.inventory['location_linear'],1)==b'\xff',
                     troll_removed=flag(150),troll_paid=flag(151),goat_retired=flag(130),
                     bridge_active=flag(21),goat_scripted=flag(76),on_water=flag(0),
                     edge=read(self.d,self.ds+11,1)[0])
        return state

    def observe(self,name):
        result=super().observe(name);s=self.observations[name]['native_state']
        self.observations[name]['state'].update({k:s[k] for k in ('carrot_carried','troll_removed','troll_paid')})
        self.observations[name]['troll_visible']=None
        print(json.dumps({'observation':name,'state':self.observations[name]['state'],'guest_ms':self.guest_elapsed}),flush=True)
        return result

    def move(self,*args,**kwargs):
        before=self.state()['room'];state=super().move(*args,**kwargs)
        if state['room']!=before:
            print(json.dumps({'entered_room':state['room'],'ego':state['ego'],'goat':state['goat'],
                              'following':state['following'],'guest_ms':self.guest_elapsed}),flush=True)
        return state

    def arm_score_watch(self):
        require(self.state()['score']==7 and self.score_write is None and self.watch is None,'Unexpected pre-bridge score')
        require(read(self.d,self.cs*16+0x72d4,len(SCORE_WRITER))==SCORE_WRITER,'Score handler bytes differ')
        self.watch=self.d.call('breakpoints.create',{'kind':'w','once':False,
            'address':{'space':'linear','offset':f'0x{self.ds+12:08X}'}})['breakpoint_id']

    def handle_stop(self,out):
        """Accept only our exact source-bound +4 write; preserve everything else."""
        reason=(out.get('session') or {}).get('stop_reason',{})
        access=reason.get('data_access',{});cause=access.get('instruction',{})
        require(self.watch is not None and reason.get('breakpoint_id')==self.watch and access.get('access')=='w','Foreign stop preserved')
        require(cause.get('space')=='segmented' and int(cause.get('segment','-1'),16)==self.cs
                and int(cause.get('offset','-1'),16)==0x72da,'Unexpected score writer preserved')
        regs=self.d.registers()
        require(int(regs['segments']['cs'],16)==self.cs and int(regs['segments']['ds'],16)*16==self.ds
                and int(regs['instruction_pointer'],16)==0x72de,'Unexpected score resume binding')
        record=int.from_bytes(read(self.d,self.ds+0x979,2),'little');desc=read(self.d,self.ds+record,10)
        code=int.from_bytes(desc[4:6],'little');resource=self.resources[25]
        require(desc[2]==25 and code+len(resource.code)<=65536,'Score source is not logic 25')
        require(read(self.d,self.ds+code,len(resource.code))==resource.code and resource.code[0x1b8:0x1bb]==bytes.fromhex('050304'),'Score source bytes differ')
        bx=int(regs['general']['ebx'],16)&65535;al=int(regs['general']['eax'],16)&255
        require(bx==3 and al==4 and int(regs['general']['esi'],16)&65535==code+0x1bb,'Score operands differ')
        require(read(self.d,self.ds+12,1)==b'\x0b','Original score write did not commit 11')
        self.score_write={'format':'fdisbull-agi-troll-score-write-1','status':'incomplete','complete':False,
            'native_execution':True,'source_logic_sha256':resource.resource_sha256,'source_offset':0x1b8,
            'before_score':7,'after_score':11,'writer':{'source_offset':0x72da,'resume_offset':0x72de,'bx':bx,'al':al},
            'code_binding':{'offset':code,'length':len(resource.code),'sha256':sha256(resource.code).hexdigest()},
            'stop':out,'registers':regs,'inventory':self.inventory}
        proof_path=self.root/'troll-score-write.private.json'
        proof_path.write_text(json.dumps(self.score_write,indent=2)+'\n')
        self.d.call('breakpoints.delete',{'breakpoint_id':self.watch});self.watch=None
        # A fetch trace has a separate bounded run, with measured guest progress.
        # The game-owned write is established above; the trace is continuation
        # evidence, not a claim that every fetched instruction completed.
        self.d.call('trace.start',{'detail':'normal','instruction_count':32})
        trace={'format':'fdisbull-agi-troll-continuation-1','events':[],'run':None,'complete':False,
               'instruction_semantics':'fetch observed; completion unknown'}
        path=self.root/'troll-score-trace.private.json'
        primary=None
        try:
            guest,wall=self.remaining_limits(100,10000)
            attempt={'kind':'score-trace','attempted':True,'result':None};self.journal.append(attempt)
            result=self.d.run(guest_ms=guest,timeout_ms=wall,fast_forward=True,stop_on_hook=True)
            attempt['result']=result;trace['run']=result
            elapsed=result.get('guest_elapsed_ms');require(type(elapsed) in (int,float) and elapsed>=0,'Missing trace guest progress')
            self.guest_elapsed+=elapsed
            page=self.d.call('trace.read',{'cursor':None,'limit':64});trace['events']=page['events']
            require(not page.get('next_cursor') and len(trace['events'])==32 and result['outcome']=='pause','Trace stop incomplete or interrupted')
            require(self.guest_elapsed<=self.guest_budget_ms and time.monotonic()<self.deadline,'Route budget exhausted after trace')
            trace['complete']=True
        except BaseException as exc:
            primary=exc
            raise
        finally:
            errors=[]
            try:self.d.call('trace.stop')
            except Exception as exc:
                self.score_write.setdefault('cleanup_errors',[]).append({'operation':'trace.stop','error':str(exc)})
                errors.append(exc)
            try:
                path.write_text(json.dumps(trace,indent=2)+'\n')
                self.score_write['trace']={'path':path.name,'sha256':sha256(path.read_bytes()).hexdigest(),'count':len(trace['events'])}
            except Exception as exc:
                self.score_write.setdefault('persistence_errors',[]).append({'artifact':path.name,'error':str(exc)})
                errors.append(exc)
            try:proof_path.write_text(json.dumps(self.score_write,indent=2)+'\n')
            except Exception as exc:
                self.score_write.setdefault('persistence_errors',[]).append({'artifact':proof_path.name,'error':str(exc)})
                errors.append(exc)
            if errors and primary is None:raise errors[0]
        confirmed={**self.score_write,'status':'verified','complete':True}
        proof_path.write_text(json.dumps(confirmed,indent=2)+'\n')
        self.score_write=confirmed
        print(json.dumps({'score_write':'verified','score':11,'source':'logic25:01b8','guest_ms':self.guest_elapsed}),flush=True)

    def route(self):
        super().route()
        before=self.actions[-1]['after'];i,m=len(self.inputs),len(self.messages)
        self.arm_score_watch()
        self.move('left',axis='x',target=75)
        self.move('up',room=24)
        self.move('up',room=25)
        self.move('up',axis='y',target=130)
        self.move('left',axis='x',target=41)
        self.move('up',axis='y',target=95)
        self.observe('bridge-encounter')
        self.move('right',axis='x',target=60)
        self.wait(lambda s:s['troll_removed'] and not s['following'] and s['score']==11
                  and not s['gate_actor']['drawn'] and not s['goat']['drawn'],'Goat resolves the troll bridge',20000)
        self.observe('bridge-cleared');s=self.state()
        require(self.score_write and self.score_write['complete'] and s['carrot'] and s['carrot_carried']
                and not s['troll_paid'] and s['goat_retired'],'Bridge outcome or retained carrot incomplete')
        # The six-pixel ego baseline fits x35 across the original bridge.
        # x41 clips the northern rail. No collision policy is changed here:
        # the original room logic owns ignore.blocks after the encounter.
        self.move('left',axis='x',target=35)
        self.move('up',axis='y',target=44)
        after=self.observe('bridge-crossed');s=self.state()
        require(s['room']==25 and s['edge']==0 and 40<=s['ego']['y']<=47
                and abs(s['ego']['x']-35)<=1 and not s['on_water'] and not s['bridge_active']
                and s['score']==11 and s['troll_removed'],'Original bridge crossing incomplete')
        proof=self.root/'troll-score-write.private.json'
        self.actions.append({'id':'troll-bridge','label':'lead the goat through the troll bridge encounter','verb':'use',
            'before':before,'after':after,'complete':True,'messages_complete':True,
            'inputs':self.inputs[i:],'messages':self.messages[m:],
            'native_score_write':{'path':proof.name,'sha256':sha256(proof.read_bytes()).hexdigest()}})
        return self.capture()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,type=Path);parser.add_argument('--backend',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    source=args.source.resolve();root=args.output.resolve();checkout=Path(__file__).resolve().parents[2]
    require(root!=checkout and checkout not in root.parents,'Keep runtime inputs and captures outside Git')
    driver=None
    try:
        with native_game('kq1',source,root,args.backend.resolve(),fair_play=True) as (p,d,obs,restore,frame,report,game):
            driver=TrollRun(p,d,report,frame,source,root)
            try:
                capture=driver.route();(root/'capture.private.json').write_text(json.dumps(capture,indent=2)+'\n')
                report['natural_troll_complete']=True
                print(json.dumps({'complete':True,'state':driver.state(),'messages':len(driver.messages),'visibility':'pending operator inspection'}),flush=True)
            except Exception as exc:
                report['natural_troll_complete']=False;report['error']=str(exc);report['last_state']=driver.state()
                frame('failure.png');raise
            finally:
                for bp in (driver.bp,driver.watch):
                    if bp:d.call('breakpoints.delete',{'breakpoint_id':bp})
    finally:
        if driver:
            (root/'journal.private.json').write_text(json.dumps(driver.journal,indent=2)+'\n')
            (root/'partial-capture.private.json').write_text(json.dumps(driver.capture(),indent=2)+'\n')
            if driver.score_write:
                (root/'partial-score-write.private.json').write_text(json.dumps(driver.score_write,indent=2)+'\n')
            receipt=json.loads((root/'result.json').read_text());original=receipt['source_manifest']
            receipt['post_teardown_source_unchanged']=manifest(source)==original
            receipt['post_teardown_copy_unchanged']=manifest(root/'game')==original
            (root/'result.json').write_text(json.dumps(receipt,indent=2)+'\n')


if __name__=='__main__':main()
