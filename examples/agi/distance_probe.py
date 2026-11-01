"""Observe the original KQ1 sleeping-giant chest distance handler once.

The owner sends ordinary input and advances the guest. A completed proof binds
observed stops and supplied source; it does not authenticate captured evidence.
"""
from copy import deepcopy
from hashlib import sha256
import json

from examples.agi.spatial_trial import read, require
from fdisbull.agi_layout import logic_layout

AGI_SHA256 = '5ab189ebd9822739962767afe0113853e23797ef16dd4784d2dc93423934fb74'
LOGIC_SHA256 = '38a7afd5c3fdd3e03c7c8e0ed670516b75d1521a4f0034bd0faac14954a3570e'
HANDLER_SHA256 = '1948a0f4a7f843c374a0a80216cc781e9fbf73cf97de2cf42d0d4ada2d422bc9'
HANDLER_START, HANDLER_END = 0x47ef, 0x48b3  # includes the two constants
SOURCE_OFFSET, SOURCE_CURSOR = 0x234, 0x238


class DistanceProbe:
    def __init__(self, owner):
        self.owner = owner
        self.active, self.failed, self.proof = False, False, None
        self.stage, self.frame, self.pose = None, None, None

    def persist(self):
        path = self.owner.root/'giant-distance.private.json'
        path.write_text(json.dumps(self.proof, indent=2)+'\n')
        return path

    def _fail(self, error, phase):
        self.failed = True
        self.owner.execution_blocked = True
        failure = self.owner.report.setdefault('quest_distance_failure',
            {'phase':phase, 'type':type(error).__name__, 'message':str(error)})
        if self.proof is not None:
            self.proof.update(status='incomplete', complete=False)
            self.proof.setdefault('failure', failure)
            try:
                self.persist()
            except BaseException as save_error:
                failure.setdefault('persistence_error', {'type':type(save_error).__name__, 'message':str(save_error)})

    def _handler(self):
        o = self.owner
        require(sha256(read(o.d, o.cs*16+HANDLER_START, HANDLER_END-HANDLER_START)).hexdigest()==HANDLER_SHA256 and
                read(o.d, o.ds+0x61d+69*4, 2)==HANDLER_START.to_bytes(2,'little'),
                'Distance handler binding differs')

    def _source(self, regs):
        o = self.owner
        require(int(regs['segments']['cs'],16)==o.cs and int(regs['segments']['ds'],16)*16==o.ds,
                'Distance segments changed')
        record=int.from_bytes(read(o.d,o.ds+0x979,2),'little')
        desc=read(o.d,o.ds+record,10); code=int.from_bytes(desc[4:6],'little')
        resource=o.resources[58]
        require(sha256(resource.payload).hexdigest()==resource.resource_sha256 and
                resource.payload[2:2+len(resource.code)]==resource.code and desc[2]==58 and
                code+len(resource.code)<=65536 and read(o.d,o.ds+code,len(resource.code))==resource.code and
                resource.resource_sha256==self.proof['source_logic_sha256'] and
                {SOURCE_OFFSET+2,SOURCE_CURSOR+2}.issubset(set(logic_layout(resource.payload)['instructions'])) and
                resource.code[SOURCE_OFFSET:SOURCE_CURSOR]==bytes((69,0,1,70)),
                'Distance source binding differs')
        self._handler()
        return code

    def _resource(self):
        resource=self.owner.resources[58]
        require(resource.resource_sha256==LOGIC_SHA256 and
                sha256(resource.payload).hexdigest()==LOGIC_SHA256 and
                resource.payload[2:2+len(resource.code)]==resource.code and
                {SOURCE_OFFSET+2,SOURCE_CURSOR+2}.issubset(set(logic_layout(resource.payload)['instructions'])) and
                resource.code[SOURCE_OFFSET:SOURCE_CURSOR]==bytes((69,0,1,70)),
                'Distance source resource differs')
        return resource

    def _state(self):
        o=self.owner
        data=read(o.d,o.ds+9,0x132);flags=data[0x100:0x120]
        flag=lambda n:bool(flags[n//8] & (0x80>>(n%8)))
        table=int.from_bytes(read(o.d,o.ds+0x963,2),'little')
        require(0<table and table+86<=65536,'Distance actor bounds differ')
        a=read(o.d,o.ds+table,43);b=read(o.d,o.ds+table+43,43)
        obj=lambda row:{'x':int.from_bytes(row[3:5],'little',signed=True),
                        'y':int.from_bytes(row[5:7],'little',signed=True),
                        'width':int.from_bytes(row[26:28],'little'),'view':row[7],
                        'direction':row[33],'drawn':bool(row[37]&1)}
        ego=obj(a);giant=obj(b)
        giant.update(height=int.from_bytes(b[28:30],'little'),motion=b[34])
        base=o.inventory['base'];end=o.inventory['end']
        require(type(base) is int and type(end) is int and 0<base<end<=65536 and end-base==81 and
                int.from_bytes(read(o.d,o.ds+0x969,2),'little')==base and
                int.from_bytes(read(o.d,o.ds+0x96b,2),'little')==end,'Distance inventory binding differs')
        loc=lambda n:read(o.d,o.ds+base+3*n+2,1)[0]
        state={'room':data[0],'score':data[3], 'ego':ego,'giant':giant,
               'sleep_state':data[86], 'sleep_scored':flag(205), 'chest_taken_flag':flag(104),
               'shield_flag':flag(102),'key_location':loc(5),'shield_location':loc(21),'chest_location':loc(2),
               'v70':data[70]}
        require(state['room']==58 and state['score']==26 and state['sleep_state']==1 and
                state['sleep_scored'] and not state['chest_taken_flag'] and state['shield_flag'] and
                state['key_location']==255 and state['shield_location']==255 and state['chest_location']==0 and
                ego['drawn'] and ego['view']==0 and ego['width']==6 and ego['direction']==0 and
                giant['drawn'] and giant['view']==52 and giant['width']==30 and giant['height']==15 and
                giant['direction']==0 and giant['motion']==0 and
                not flag(0) and not flag(3) and not flag(5) and not flag(63) and data[94]==0 and
                int.from_bytes(data[0x130:0x132],'little')==1 and
                int.from_bytes(read(o.d,o.ds+0xd15,2),'little')==0,
                'Distance pose or quest state differs')
        return table,state

    @staticmethod
    def _expected(state):
        ego,giant=state['ego'],state['giant']
        return min(254,abs(ego['x']+ego['width']//2-giant['x']-giant['width']//2)+abs(ego['y']-giant['y']))

    def _unchanged(self, state):
        return all(state[k]==v for k,v in self.pose.items() if k not in ('v70','expected_distance'))

    def start(self):
        o=self.owner
        require(not self.active and not self.failed and not getattr(o,'execution_blocked',False) and
                o.watch is None and not o.trace_active and
                not getattr(getattr(o,'quest_probe',None),'active',False) and
                not getattr(getattr(o,'motion_probe',None),'active',False) and o._idle(),
                'Distance owner or keyboard not idle')
        agi=sha256((o.source/'AGI').read_bytes()).hexdigest()
        require(agi==AGI_SHA256 and type(o.d.session_id) is str and bool(o.d.session_id), 'Distance session or source differs')
        resource=self._resource();self._handler();table,state=self._state();expected=self._expected(state)
        require(expected<=30,'Sleeping giant is too far away')
        self.pose=deepcopy(state);self.pose['expected_distance']=expected
        self.proof={'format':'fdisbull-agi-chest-distance-1','status':'incomplete','complete':False,
                    'native_execution':False,'identity':{'session_id':o.d.session_id,'cs':o.cs,'ds':o.ds//16,
                    'agi_sha256':agi,'handler_sha256':HANDLER_SHA256},'source_logic':58,
                    'source_logic_sha256':resource.resource_sha256,'source_offset':SOURCE_OFFSET,
                    'source_cursor_offset':SOURCE_CURSOR,'arguments':[0,1,70],
                    'actor_table':table,'before':deepcopy(self.pose)}
        o.report['quest_distance']=self.proof
        self.active=True;self.stage='write'
        try:
            self.persist();o.watch_kind='quest-distance-write';o.arm('w',o.ds+9+70)
        except BaseException as error:
            self._fail(error,'setup');raise
        return self.proof

    def handle_stop(self,out):
        try:
            require(self.active and not self.failed and self.stage in ('write','return'),'Distance probe inactive or failed')
            self._handle_stop(out)
        except BaseException as error:
            if self.active:self._fail(error,'stop')
            raise

    def _handle_stop(self,out):
        o=self.owner;reason=(out.get('session') or {}).get('stop_reason',{})
        require(out.get('outcome')=='breakpoint' and o.watch is not None and reason.get('breakpoint_id')==o.watch and
                o.watch_kind=='quest-distance-'+self.stage and o.d.session_id==self.proof['identity']['session_id'],
                'Foreign distance stop preserved')
        # Retain the raw observed byte even if later qualification or storage
        # fails. It becomes a known result only after every writer check passes.
        if self.stage=='write':
            self.proof['last_observed_v70']=read(o.d,o.ds+9+70,1)[0]
        regs=o.d.registers();code=self._source(regs);table,state=self._state()
        require(table==self.proof['actor_table'] and self._unchanged(state),'Distance pose changed')
        ip=int(regs['instruction_pointer'],16); expected=self.pose['expected_distance']
        if self.stage=='write':
            access=reason.get('data_access',{});cause=access.get('instruction',{})
            bx=int(regs['general']['ebx'],16)&65535;ax=int(regs['general']['eax'],16)&65535
            si=int(regs['general']['esi'],16)&65535;di=int(regs['general']['edi'],16)&65535
            bp=int(regs['general']['ebp'],16)&65535;sp=int(regs['general']['esp'],16)&65535
            ss=int(regs['segments']['ss'],16)
            require(access.get('access')=='w' and cause.get('space')=='segmented' and
                    int(cause.get('segment','-1'),16)==o.cs and int(cause.get('offset','-1'),16)==0x48a2 and
                    ip==0x48a6 and bx==70 and ax==expected and si==table and di==table+43 and
                    4<=bp<=65525 and sp==bp-4 and
                    read(o.d,ss*16+bp+4,6)==(code+SOURCE_OFFSET+1).to_bytes(2,'little')+
                    (0x2fa).to_bytes(2,'little')+(code+SOURCE_CURSOR).to_bytes(2,'little') and
                    state['v70']==expected,'Distance writer, value or call frame differs')
            self.frame=(ss,bp,code)
            self.proof['native_execution']=True;self.proof['known_result']=state['v70']
            self.proof['distance_writer']={'cause_offset':0x48a2,'resume_offset':0x48a6,'bx':bx,'ax':ax,
                                           'si':si,'di':di,'bp':bp,'sp':sp,'ss':ss}
            self.persist()  # Preserve the native result before changing watches.
            o.remove_watch();self.stage='return';o.watch_kind='quest-distance-return';o.arm('execution',0x2fa,'segmented')
            return
        ss,bp,old_code=self.frame
        require(not reason.get('data_access') and ip==0x2fa and code==old_code and
                int(regs['segments']['ss'],16)==ss and int(regs['general']['esp'],16)&65535==bp+8 and
                int(regs['general']['eax'],16)&65535==code+SOURCE_CURSOR and
                int(regs['general']['esi'],16)&65535==code+SOURCE_OFFSET+1 and
                read(o.d,ss*16+bp+8,2)==(code+SOURCE_CURSOR).to_bytes(2,'little') and state['v70']==expected,
                'Distance handler return differs')
        self.proof['handler_return']={'offset':0x2fa,'observed':True,'source_cursor_offset':SOURCE_CURSOR,
                                      'stack_verified':True,'ss':ss,'writer_bp':bp,'sp':bp+8,
                                      'ax':code+SOURCE_CURSOR,'si':code+SOURCE_OFFSET+1}
        self.proof['after']=state
        self.persist();o.remove_watch()
        self.proof.update(status='verified',complete=True)
        self.persist();self.active=False
