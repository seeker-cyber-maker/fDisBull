"""Source-bound probe for the inside water branch."""
from copy import deepcopy
from hashlib import sha256
from examples.agi.dragon_probes import setup_probe, DROP_SHA, SUB_SHA
from examples.agi.inventory_probe import PickupProbe
from examples.agi.spatial_trial import read, require
from examples.agi.verify_troll import SCORE_WRITER
from fdisbull.agi_layout import logic_layout

class InsideWaterProbe(PickupProbe):
    """Observe DROP26/return and SUBN2 after the inside-branch print."""
    def __init__(self,owner):
        setup_probe(self,owner,'dragon-inside',26,0x42b,0x42d,-2,15,('drop','return','subtract'))
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
                read(o.d,o.ds+code,len(r.code))==r.code and {0x42b+2,0x42d+2}.issubset(starts) and
                r.code[0x429:0x430]==bytes((101,33,94,26,7,3,2)),
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
        self.proof={'format':'fdisbull-agi-dragon-inside-water-1','status':'incomplete','complete':False,
            'native_execution':False,'source_logic':51,'source_logic_sha256':o.resources[51].resource_sha256,
            'print_source_offset':0x429,'item_source_offset':0x42b,'subtract_source_offset':0x42d,
            'item':26,'order':list(self.order),
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
        effects=self.proof['known_effects'];cursor=0x42d
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
                delta=2 if stage=='subtract' else 7;offset=0x42d if stage=='subtract' else 0x465
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
