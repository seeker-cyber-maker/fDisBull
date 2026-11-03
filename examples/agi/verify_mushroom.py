"""Fresh physical KQ1 mushroom crossing and source-bound inventory pickup.

All inputs, native states, databases and raw captures belong outside Git.
Static paths are proposals executed through ordinary keyboard input. The
original interpreter owns room-entry placement, collisions and inventory.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from examples.agi.spatial_trial import native_game,read,require
from examples.agi.verify_goat import GoatRun
from examples.agi.verify_bridge_clip import ClipRun,retain_private_evidence
from examples.agi.verify_troll import OBJECT_SHA256,SCORE_WRITER
from examples.agi.scan_collision_candidates import bounded_path,extract_water_guards
from fdisbull.agi import load_logic
from fdisbull.agi_picture import decode_picture,extract_v2_resource

GET_HANDLER=bytes.fromhex('5657558bec8d460850e8c90083c4028bf8c64502ff8b46085d5f5ec3')


def bind_mushroom(d,source,cs,ds):
    require(sha256((source/'OBJECT').read_bytes()).hexdigest()==OBJECT_SHA256,'Inventory source differs')
    require(read(d,cs*16+0x7601,2)==b'\x03\x00' and read(d,cs*16+0x7471,len(GET_HANDLER))==GET_HANDLER,'Inventory handler differs')
    require(read(d,ds+0x78d,2)==bytes.fromhex('7174'),'Original get table entry differs')
    base=int.from_bytes(read(d,ds+0x969,2),'little');end=int.from_bytes(read(d,ds+0x96b,2),'little')
    require(0<base<end<=65536 and end-base==81 and base+0x13c<=65536,'Inventory bounds differ')
    require(read(d,ds+base+72,2)==bytes.fromhex('3301') and read(d,ds+base+0x133,9)==b'mushroom\0','Mushroom source name differs')
    return {'source_sha256':OBJECT_SHA256,'base':base,'end':end,'stride':3,'item':24,
        'name_offset':0x133,'location_linear':ds+base+74,'carried_value':255}


class MushroomRun(ClipRun):
    guest_budget_ms=420000
    wall_budget_ms=600000

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        for n in(33,34,47,48):self.resources[n]=load_logic(self.source/'LOGDIR',self.source,n,profile='2.917')
        self.inventory=bind_mushroom(self.d,self.source,self.cs,self.ds)
        self.pictures={str(n):extract_v2_resource(self.source/'PICDIR',self.source,n)['sha256'] for n in(33,47,48)}
        self.watch=None;self.watch_kind=None;self.trace_active=False;self.trace_receipt=None;self.pickup_active=False
        self.report['inventory_binding']=self.inventory
        self.report['implementation_sha256']['examples/agi/verify_mushroom.py']=sha256(Path(__file__).read_bytes()).hexdigest()
        self.report['implementation_sha256']['examples/agi/scan_collision_candidates.py']=sha256(Path(__file__).with_name('scan_collision_candidates.py').read_bytes()).hexdigest()

    def state(self):
        s=super().state();f=read(self.d,self.ds+0x109,32)
        flag=lambda n:bool(f[n//8]&(0x80>>(n%8)))
        if hasattr(self,'inventory'):
            s.update(mushroom_carried=read(self.d,self.inventory['location_linear'],1)==b'\xff',
                mushroom_taken=flag(121),mushroom_scored=flag(123))
        return s

    def safe_state(self):
        s=self.state();self._safe_observation(s)
        return s

    def _safe_observation(self,s):
        self.samples.append({'guest_ms':self.guest_elapsed,'state':s})
        require(not s['in_water'] and not s['swimming'] and not s['dead'],'Mushroom route entered water/death')
        require(not any(s[k] for k in('bridge_active','troll_removed','troll_paid')) and
            s['score'] in ((0,1) if self.pickup_active else (0,)),'Unexpected score or troll outcome')
        require(s['ego_width']==6 and s['ego_view']==0 and s['step_size']==1,'Walking footprint changed')
        return True

    def static_path(self,x,y):
        s=self.safe_state();room=s['room'];resource=self.resources[room]
        item=extract_v2_resource(self.source/'PICDIR',self.source,room);plane=bytearray(decode_picture(item['payload'])['priority'])
        # Conservative model boundary, not an edit to any guest memory/PIC.
        plane[:44*160]=bytes(44*160)
        guards=extract_water_guards(resource.payload,logic_number=room)
        result=bounded_path(bytes(plane),(s['ego']['x'],s['ego']['y']),(x,y),width=6,
            allow_priority_one=True,hazards=[r for g in guards for r in g['rectangles']],max_nodes=26880,max_steps=1024)
        require(result['status']=='found','Static path incomplete/absent: '+result['status'])
        points=result['path'];turns=[]
        for i,p in enumerate(points[1:],1):
            if i==len(points)-1 or (p[0]-points[i-1][0],p[1]-points[i-1][1])!=(points[i+1][0]-p[0],points[i+1][1]-p[1]):turns.append(p)
        self.journal.append({'kind':'static-path-proposal','room':room,'picture_sha256':item['sha256'],
            'logic_sha256':resource.resource_sha256,'waypoints':turns,'scope':'Destination-only land baseline; ignores dynamic objects. Guest input decides success.'})
        for a,b in turns:
            current=self.state()['ego'];self.precise(**({'x':a} if a!=current['x'] else {'y':b}))

    def source_binding(self,regs):
        require(int(regs['segments']['cs'],16)==self.cs and int(regs['segments']['ds'],16)*16==self.ds,'Pickup segment binding changed')
        rec=int.from_bytes(read(self.d,self.ds+0x979,2),'little');desc=read(self.d,self.ds+rec,10)
        code=int.from_bytes(desc[4:6],'little');resource=self.resources[47]
        require(desc[2]==47 and code+len(resource.code)<=65536 and read(self.d,self.ds+code,len(resource.code))==resource.code,'Pickup source changed')
        require(resource.code[0x195:0x19a]==bytes.fromhex('0503015c18'),'Pickup source instructions differ')
        return code

    def arm(self,kind,address,space='linear'):
        require(self.watch is None,'Existing owned pickup breakpoint')
        a={'space':space,'offset':f'0x{address:08X}'}
        if space=='segmented':a['segment']=f'0x{self.cs:04X}'
        self.watch=self.d.call('breakpoints.create',{'kind':kind,'once':False,'address':a})['breakpoint_id']

    def remove_watch(self):
        self.d.call('breakpoints.delete',{'breakpoint_id':self.watch});self.watch=None

    def persist_pickup(self):
        (self.root/'mushroom-pickup.private.json').write_text(json.dumps(self.predicate_proof,indent=2)+'\n')

    def retain_trace_readback(self):
        page=self.d.call('trace.read',{'cursor':None,'limit':256});events=page['events']
        known=self.trace_receipt['events']
        require(isinstance(events,list) and len(events)>=len(known) and events[:len(known)]==known,
            'Partial trace readback would lose or contradict known events')
        self.trace_receipt['events']=events
        self.trace_receipt['runs']=[x['result'] for x in self.journal[self.trace_start_index:] if isinstance(x.get('result'),dict)]

    def stop_trace(self):
        self.d.call('trace.stop');self.trace_active=False

    def persist_partial_trace(self):
        path=self.root/'partial-mushroom-trace.private.json'
        path.write_text(json.dumps(self.trace_receipt,indent=2)+'\n')
        self.predicate_proof['partial_trace']={'path':path.name,'sha256':sha256(path.read_bytes()).hexdigest(),
            'event_count':len(self.trace_receipt['events']),'complete':self.trace_receipt['complete']}

    def handle_stop(self,out):
        reason=(out.get('session') or {}).get('stop_reason',{})
        require(self.watch is not None and reason.get('breakpoint_id')==self.watch,'Foreign stop preserved')
        regs=self.d.registers();code=self.source_binding(regs);ip=int(regs['instruction_pointer'],16)
        proof=self.predicate_proof
        if self.watch_kind in('score','item'):
            access=reason.get('data_access',{});cause=access.get('instruction',{})
            offset,resume=(0x72da,0x72de) if self.watch_kind=='score' else (0x7482,0x7486)
            require(access.get('access')=='w' and cause.get('space')=='segmented' and
                int(cause.get('segment','-1'),16)==self.cs and int(cause.get('offset','-1'),16)==offset and ip==resume,'Unqualified pickup writer')
            if self.watch_kind=='score':
                bx=int(regs['general']['ebx'],16)&65535;al=int(regs['general']['eax'],16)&255
                require(bx==3 and al==1 and int(regs['general']['esi'],16)&65535==code+0x198 and
                    self.state()['score']==1 and read(self.d,self.inventory['location_linear'],1)==b'\x00','Score write operands differ')
                proof.update(native_execution=True,score_writer={'cause_offset':offset,'resume_offset':resume,'bx':bx,'al':al})
                self.persist_pickup();self.remove_watch();self.watch_kind='item';self.arm('w',self.inventory['location_linear'])
                self.trace_receipt={'format':'fdisbull-agi-mushroom-trace-1','maximum_count':128,'complete':False,'events':[],'runs':[],
                    'scope':'Native fetch observations; original writes/handler return are observed separately.'}
                self.trace_start_index=len(self.journal);self.trace_active=True
                self.d.call('trace.start',{'detail':'normal','instruction_count':128})
                return
            di=int(regs['general']['edi'],16)&65535;bp=int(regs['general']['ebp'],16)&65535
            sp=int(regs['general']['esp'],16)&65535;ss=int(regs['segments']['ss'],16)
            require(di==self.inventory['base']+72 and sp==bp<=65525 and
                read(self.d,ss*16+bp+6,4)==(0x2fa).to_bytes(2,'little')+(code+0x19a).to_bytes(2,'little') and
                read(self.d,self.inventory['location_linear'],1)==b'\xff','Item write or original get call frame differs')
            self.item_frame=(ss,bp,code)
            proof['item_writer']={'cause_offset':offset,'resume_offset':resume,'di_offset':di}
            proof['after']={'score':self.state()['score'],'item_location':255}
            self.persist_pickup();self.remove_watch();self.watch_kind='return';self.arm('execution',0x2fa,'segmented');return
        require(self.watch_kind=='return' and not reason.get('data_access') and ip==0x2fa,'Foreign pickup return stop preserved')
        ss,bp,original_code=self.item_frame
        require(code==original_code and int(regs['segments']['ss'],16)==ss and
            int(regs['general']['esp'],16)&65535==bp+8 and int(regs['general']['eax'],16)&65535==code+0x19a and
            read(self.d,ss*16+bp+8,2)==(code+0x19a).to_bytes(2,'little'),'Original get handler did not return with its source cursor')
        proof['handler_return']={'offset':0x2fa,'observed':True,'source_cursor_offset':0x19a,'stack_verified':True}
        self.persist_pickup();self.remove_watch()
        page=self.d.call('trace.read',{'cursor':None,'limit':256});self.trace_receipt['events']=page['events']
        require(not page.get('next_cursor') and 0<len(page['events'])<128,'Pickup trace exhausted/incomplete')
        self.trace_receipt['runs']=[x['result'] for x in self.journal[self.trace_start_index:] if isinstance(x.get('result'),dict)]
        self.stop_trace()
        self.trace_receipt['complete']=True;path=self.root/'mushroom-trace.private.json'
        path.write_text(json.dumps(self.trace_receipt,indent=2)+'\n')
        proof['trace']={'path':path.name,'sha256':sha256(path.read_bytes()).hexdigest(),'event_count':len(page['events']),'maximum_count':128}
        confirmed={**proof,'status':'verified','complete':True}
        (self.root/'mushroom-pickup.private.json').write_text(json.dumps(confirmed,indent=2)+'\n');self.predicate_proof=confirmed

    def route(self,*,adjacent_control=False):
        require(self.state()['room']==1 and self.state()['score']==0,'Fresh game required')
        self.move('right',room=8);self.move('right',axis='x',target=70);self.move('down',room=41)
        self.precise(x=154);self.move('down',room=40);self.precise(y=100);self.static_path(1,100)
        self.move('left',room=33);self.precise(x=154);self.precise(y=87)
        if adjacent_control:
            self.precise(x=153);self.observe_clip('control-before');self.press('up',20,hold_ms=1,gap_ms=1)
            stable=0;last=None;start=self.guest_elapsed;records=[]
            while self.guest_elapsed-start<6000:
                s=self.safe_state();records.append({'guest_ms':self.guest_elapsed,'state':s})
                require(s['room']==33 and s['ego']['x']==153 and s['ego']['direction']==1 and s['control_direction']==1 and self._idle(),'Control movement/context unknown')
                point=(s['ego']['x'],s['ego']['y']);stable=stable+1 if point==last else 0;last=point
                if stable>=20:
                    require(point==(153,85),'Unexpected neighboring stop position')
                    self.report['adjacent_control']={'complete':True,'result':'bounded-north-request-without-advancement','samples':records,'stable_samples':stable}
                    self.neutral();self.observe_clip('control-stopped');return self.capture()
                self.advance(100)
            raise RuntimeError('Adjacent control observation budget exhausted')
        before=self.observe_clip('mushroom-before');i,m=len(self.inputs),len(self.messages)
        self.precise(y=55);self.observe_clip('mushroom-midwater');self.move('up',room=48)
        self.report['room48_entry']=self.state();self.static_path(129,140)
        landed=self.observe_clip('mushroom-landed');self.action('cross-to-island',before,landed,i,m)
        i,m=len(self.inputs),len(self.messages)
        self.static_path(1,150);self.move('left',room=47);self.static_path(94,90)
        near=self.observe_clip('mushroom-near');self.action('reach-mushroom',landed,near,i,m)
        s=self.safe_state();require(not any(s[k] for k in('mushroom_carried','mushroom_taken','mushroom_scored')) and
            read(self.d,self.inventory['location_linear'],1)==b'\x00' and self._idle(),'Pickup already committed/input not idle')
        require(read(self.d,self.cs*16+0x72d4,len(SCORE_WRITER))==SCORE_WRITER,'Score writer differs')
        self.predicate_proof={'format':'fdisbull-agi-mushroom-pickup-1','status':'incomplete','complete':False,'native_execution':False,
            'source_logic':47,'source_logic_sha256':self.resources[47].resource_sha256,'score_source_offset':0x195,'item_source_offset':0x198,
            'before':{'score':0,'item_location':0},'inventory_binding':self.inventory}
        self.persist_pickup();self.pickup_active=True;self.watch_kind='score';self.arm('w',self.ds+12)
        i,m=len(self.inputs),len(self.messages);self.command('get mushroom')
        require(self.predicate_proof['complete'] and self.predicate_proof['status']=='verified','Pickup native effects incomplete')
        final=self.observe_clip('mushroom-taken');self.action('take-mushroom',near,final,i,m)
        self.clip_actions[-1]['native_pickup']={'path':'mushroom-pickup.private.json','sha256':sha256((self.root/'mushroom-pickup.private.json').read_bytes()).hexdigest()}
        self.report['normal_mushroom_complete']=True
        return self.capture()

    def capture(self):
        base=GoatRun.capture(self)
        if hasattr(self,'pictures'):
            base.update(format='fdisbull-agi-mushroom-capture-1',pictures=self.pictures,observations=self.clip_observations,
                actions=self.clip_actions,samples=self.samples,crossing_observation='mushroom-midwater')
        return base


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in('source','backend','output'):parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--adjacent-control',action='store_true');args=parser.parse_args()
    source=args.source.resolve();root=args.output.resolve();checkout=Path(__file__).resolve().parents[2]
    require(not root.is_relative_to(checkout) and not root.is_relative_to(source),'Keep runtime data outside checkout/source')
    driver=None;report=None;primary=None
    def secondary(label,fn):
        nonlocal primary
        try:fn()
        except Exception as exc:
            if primary is None:primary=exc
            report.setdefault('persistence_errors',[]).append({'operation':label,'error':str(exc)})
    try:
        with native_game('kq1',source,root,args.backend.resolve(),fair_play=True) as(p,d,obs,restore,frame,report,game):
            driver=MushroomRun(p,d,report,frame,source,root)
            try:
                capture=driver.route(adjacent_control=args.adjacent_control)
                (root/'capture.private.json').write_text(json.dumps(capture,indent=2)+'\n');report['final_state']=driver.state()
            except BaseException as exc:
                primary=exc;report['error']=str(exc);report['normal_mushroom_complete']=False
                if driver.predicate_proof is not None:driver.predicate_proof['error']=str(exc)
                secondary('failure state',lambda:report.update(last_state=driver.state()));secondary('failure frame',lambda:frame('failure.png'))
            finally:
                if driver.trace_active:secondary('partial trace readback',driver.retain_trace_readback)
                if driver.trace_active:secondary('trace cleanup',driver.stop_trace)
                if driver.trace_receipt is not None:secondary('partial trace persistence',driver.persist_partial_trace)
                if driver.watch:secondary('owned pickup breakpoint cleanup',driver.remove_watch)
                if driver.bp:secondary('print breakpoint cleanup',lambda:d.call('breakpoints.delete',{'breakpoint_id':driver.bp}))
    except BaseException as exc:
        if primary is None:primary=exc
        elif report is not None:report.setdefault('persistence_errors',[]).append({'operation':'context cleanup','error':str(exc)})
    finally:
        if report is not None:
            errors=retain_private_evidence(driver,source,root,report)
            if errors and primary is None:primary=errors[0]
    if primary is not None:raise primary
    print(json.dumps({'complete':True,'control':args.adjacent_control,'state':report['final_state']}),flush=True)


if __name__=='__main__':main()
