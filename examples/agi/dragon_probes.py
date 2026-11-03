"""Owned write/return probes for KQ1's water and magic mirror actions.

The caller supplies input and advances the guest. Trace stops before any
blocking print; returned evidence is supplied observation, not authentication.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from examples.agi.inventory_probe import PickupProbe
from examples.agi.spatial_trial import read, require
from examples.agi.verify_troll import SCORE_WRITER
from fdisbull.agi_layout import logic_layout

# Digests bind original DROP 74a9..74c4 and SUBN 72f4..7300 without copying bytes.
DROP_SHA='09cede37b9273231680365b3ec250cea473feead59c8128558d6574c8956f6fc'
SUB_SHA='f2f6ff28f441ceb5c641e9329ad61d1ec35db9e779c0c078b84dd4fcef3bc18f'


def setup_probe(probe, owner, name, item, item_offset, score_offset, score_delta, before_score, order):
    probe.owner=owner;probe.name=name;probe.logic=51;probe.item=item;probe.item_offset=item_offset
    probe.score_offset=score_offset;probe.score_delta=score_delta;probe.before_score=before_score
    probe.order=order;probe.index=0;probe.active=False;probe.failed=False;probe.item_frame=None
    probe.proof=None;probe.location=None


class MirrorProbe(PickupProbe):
    """Observe GET19, original return, modal success, and ADDN8 in order."""
    def __init__(self, owner):
        setup_probe(self,owner,'mirror',19,0x37f,0x385,8,20,('item','return','score'))
        self.pre_print_trace=None

    def start(self):
        o=self.owner
        require(isinstance(o.d.session_id,str) and bool(o.d.session_id),'Mirror session identity missing')
        proof=super().start()
        try:
            proof['identity']={'session_id':o.d.session_id,'cs':o.cs,'ds':o.ds//16}
            proof['instruction_completed']=None
            proof['writer_stop_stage']='after data access; instruction completion unknown'
            self.persist()
        except BaseException as error:self._fail(error,'setup');raise
        return proof

    def _handle_stop(self,out):
        require(self.owner.d.session_id==self.proof['identity']['session_id'],'Mirror session changed')
        stage=self.order[self.index]
        super()._handle_stop(out)
        if stage=='return':
            # Source's next opcode is a blocking print. Never trace its wait.
            self.pre_print_trace=super()._finish_trace()
            self.proof['pre_print_trace']=deepcopy(self.pre_print_trace)
            self.persist()

    def _finish_trace(self):
        require(self.pre_print_trace is not None and not self.owner.trace_active,
                'Mirror return trace did not complete before the print')
        return deepcopy(self.pre_print_trace)


class DragonWaterProbe(PickupProbe):
    """Observe DROP26/return, SUBN2 and ADDN7 after the original print."""
    def __init__(self,owner):
        setup_probe(self,owner,'dragon-water',26,0x460,0x465,7,15,('drop','return','subtract','add'))
        self.pre_score_trace=None

    def _source(self,regs):
        o=self.owner
        require(int(regs['segments']['cs'],16)==o.cs and int(regs['segments']['ds'],16)*16==o.ds,
                'Dragon water segment changed')
        record=int.from_bytes(read(o.d,o.ds+0x979,2),'little');desc=read(o.d,o.ds+record,10)
        code=int.from_bytes(desc[4:6],'little');r=o.resources[51]
        starts=set(logic_layout(r.payload)['instructions'])
        require(sha256(r.payload).hexdigest()==r.resource_sha256==self.proof['source_logic_sha256'] and
                r.payload[2:2+len(r.code)]==r.code and desc[2]==51 and code+len(r.code)<=65536 and
                read(o.d,o.ds+code,len(r.code))==r.code and {0x460+2,0x462+2,0x465+2}.issubset(starts) and
                r.code[0x45e:0x468]==bytes((101,34,94,26,7,3,2,5,3,7)),
                'Dragon water source operations differ')
        return code

    def _arm_stage(self,stage):
        o=self.owner;o.watch_kind='quest-dragon-water-'+stage
        if stage=='return':o.arm('execution',0x2fa,'segmented')
        else:o.arm('w',self.location if stage=='drop' else o.ds+12)

    def start(self):
        o=self.owner
        require(not self.active and not self.failed and not getattr(o,'execution_blocked',False) and
                o.watch is None and not o.trace_active and isinstance(o.d.session_id,str) and
                bool(o.d.session_id),'Dragon water owner busy or session identity missing')
        require(sha256(read(o.d,o.cs*16+0x74a9,28)).hexdigest()==DROP_SHA and
                sha256(read(o.d,o.cs*16+0x72f4,13)).hexdigest()==SUB_SHA and
                read(o.d,o.cs*16+0x72d4,len(SCORE_WRITER))==SCORE_WRITER and
                read(o.d,o.ds+0x61d+94*4,2)==(0x74a9).to_bytes(2,'little'),
                'Dragon water handlers differ')
        binding=self._binding();require(read(o.d,o.ds+12,1)==b'\x0f' and
                                       read(o.d,self.location,1)==b'\xff','Dragon water initial state differs')
        self.proof={'format':'fdisbull-agi-dragon-water-1','status':'incomplete','complete':False,
            'native_execution':False,'source_logic':51,'source_logic_sha256':o.resources[51].resource_sha256,
            'print_source_offset':0x45e,'item_source_offset':0x460,'subtract_source_offset':0x462,
            'add_source_offset':0x465,'item':26,'order':list(self.order),
            'identity':{'session_id':o.d.session_id,'cs':o.cs,'ds':o.ds//16},
            'instruction_completed':None,'writer_stop_stage':'after data access; instruction completion unknown',
            'before':{'score':15,'item_location':255},'known_effects':{'score':15,'item_location':255},
            'inventory_binding':binding}
        self.active=True
        try:self.persist();self._arm_stage('drop')
        except BaseException as error:self._fail(error,'setup');raise
        return self.proof

    def _handle_stop(self,out):
        o=self.owner;reason=(out.get('session') or {}).get('stop_reason',{});stage=self.order[self.index]
        require(out.get('outcome')=='breakpoint' and o.watch is not None and reason.get('breakpoint_id')==o.watch and
                o.watch_kind=='quest-dragon-water-'+stage and o.d.session_id==self.proof['identity']['session_id'],
                'Foreign dragon water stop preserved')
        observed=self.proof.setdefault('last_observation',{'stage':stage})
        observed.clear();observed['stage']=stage
        observed['score']=read(o.d,o.ds+12,1)[0]
        observed['item_location']=read(o.d,self.location,1)[0]
        regs=o.d.registers();code=self._source(regs)
        require(self._binding()==self.proof['inventory_binding'],'Dragon water inventory binding changed')
        ip=int(regs['instruction_pointer'],16);score=observed['score'];item=observed['item_location']
        effects=self.proof['known_effects'];cursor=0x462
        if stage=='return':
            ss,bp,prior_code=self.item_frame
            require(not reason.get('data_access') and ip==0x2fa and code==prior_code and
                int(regs['segments']['ss'],16)==ss and int(regs['general']['esp'],16)&65535==bp+8 and
                int(regs['general']['eax'],16)&65535==code+cursor and
                read(o.d,ss*16+bp+8,2)==(code+cursor).to_bytes(2,'little') and
                score==effects['score'] and item==effects['item_location'],'Dragon DROP return differs')
            self.proof['handler_return']={'offset':0x2fa,'observed':True,'source_cursor_offset':cursor,'stack_verified':True}
        else:
            access=reason.get('data_access',{});cause=access.get('instruction',{})
            off,resume={'drop':(0x74ba,0x74be),'subtract':(0x72fa,0x72fe),'add':(0x72da,0x72de)}[stage]
            require(access.get('access')=='w' and cause.get('space')=='segmented' and
                    int(cause.get('segment','-1'),16)==o.cs and int(cause.get('offset','-1'),16)==off and
                    ip==resume,'Dragon water writer differs')
            if stage=='drop':
                di=int(regs['general']['edi'],16)&65535;bp=int(regs['general']['ebp'],16)&65535
                sp=int(regs['general']['esp'],16)&65535;ss=int(regs['segments']['ss'],16)
                require(di==o.inventory['base']+78 and sp==bp<=65525 and
                    read(o.d,ss*16+bp+6,4)==(0x2fa).to_bytes(2,'little')+(code+cursor).to_bytes(2,'little') and
                    score==15 and item==0,'Dragon water DROP frame or value differs')
                self.item_frame=(ss,bp,code);effects['item_location']=0
                self.proof['drop_writer']={'cause_offset':off,'resume_offset':resume,'di_offset':di}
            else:
                delta=2 if stage=='subtract' else 7;offset=0x462 if stage=='subtract' else 0x465
                expected=13 if stage=='subtract' else 20
                require(int(regs['general']['ebx'],16)&65535==3 and int(regs['general']['eax'],16)&255==delta and
                    int(regs['general']['esi'],16)&65535==code+offset+3 and score==expected and item==0,
                    'Dragon water score writer operands differ')
                effects['score']=score
                self.proof[stage+'_writer']={'cause_offset':off,'resume_offset':resume,'bx':3,'al':delta}
        self.proof['native_execution']=True;self.persist()
        o.remove_watch();self.index+=1
        if stage=='return':
            self.pre_score_trace=super()._finish_trace();self.proof['drop_trace']=deepcopy(self.pre_score_trace);self.persist()
        if self.index<len(self.order):
            self._arm_stage(self.order[self.index])
            if stage=='drop':self._begin_trace()
            return
        require(self.pre_score_trace is not None and not o.trace_active,'Dragon DROP trace incomplete')
        self.proof.update(status='verified',complete=True,after=deepcopy(effects),trace=deepcopy(self.pre_score_trace))
        self.persist();self.active=False
