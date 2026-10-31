import base64
from copy import deepcopy

import pytest

from test_agi_control import loaded
import fdisbull.agi_dos as agi_dos
from fdisbull.agi_dos import AGIDOSMonitor, _CALL_SIGNATURE, _SIGNATURE, _TABLE_EXPECTED

class Session:
    session_id='synthetic-session'
    def __init__(self, code):
        self.memory=bytearray(0x50000); self.cs=0x1000;self.ds=0x2000;self.base=0x3000
        self.memory[self.cs*16+0x2c4:self.cs*16+0x2c4+len(_SIGNATURE)]=_SIGNATURE
        self.memory[self.cs*16+0x2f5:self.cs*16+0x2f5+len(_CALL_SIGNATURE)]=_CALL_SIGNATURE
        for op,handler in _TABLE_EXPECTED.items():
            a=self.ds*16+0x61d+op*4;self.memory[a:a+2]=handler.to_bytes(2,'little')
        self.memory[self.ds*16+self.base:self.ds*16+self.base+len(code)]=code
        self.memory[self.ds*16+0x963:self.ds*16+0x965]=(0x4000).to_bytes(2,'little')
        self.reg={'segments':{'cs':hex(self.cs),'ds':hex(self.ds)}, 'instruction_pointer':hex(0x2c4),
                  'general':{'esi':hex(self.base+1),'eax':hex(code[0])},'session_id':self.session_id}
        self.calls=[];self.outcome='breakpoint';self.breakpoint_ids=[];self.foreign_breakpoint=False;self.state_revision=1
    def registers(self):return deepcopy(self.reg)
    def call(self,method,args=None):
        self.calls.append(method)
        if method=='session.status':return {'state':'stopped','state_revision':self.state_revision,'frame_id':1,'mode_id':1}
        if method=='memory.read':
            pos=int(args['address']['offset'],16);return {'data_base64':base64.b64encode(self.memory[pos:pos+args['length']]).decode()}
        if method=='breakpoints.create':
            self.state_revision+=1
            ident=f'test-{len(self.breakpoint_ids)+1}';self.breakpoint_ids.append(ident)
            return {'breakpoint_id':ident}
        if method=='breakpoints.delete':self.state_revision+=1;return {}
        raise AssertionError(method)
    def run(self,**kwargs):
        self.reg['instruction_pointer']=hex(0x2fa);self.reg['general']['eax']=hex(self.base+2)
        ident='foreign-breakpoint' if self.foreign_breakpoint else self.breakpoint_ids[-1]
        return {'outcome':self.outcome,'session':{'stop_reason':{
            'kind':'breakpoint' if self.outcome=='breakpoint' else self.outcome,
            'breakpoint_id':ident}}}


def monitor(tmp_path,code,monkeypatch):
    resource=loaded(tmp_path,{0:bytes(code)}).root;s=Session(resource.code)
    from hashlib import sha256
    monkeypatch.setattr(agi_dos, '_ENGINE_SHA256', sha256(s.memory[s.cs*16:s.cs*16+agi_dos._ENGINE_LENGTH]).hexdigest())
    return AGIDOSMonitor(s,resource,cs=s.cs,ds=s.ds,code_offset=s.base),s

def test_action_returns_raw_observation(tmp_path, monkeypatch):
    m,s=monitor(tmp_path,[33,0,0],monkeypatch); r=m.step()
    assert r['status']=='completed' and r['offset']==0 and r['opcode']==33 and r['next_offset']==2
    assert r['native_execution'] is True and len(bytes.fromhex(r['raw_after']['object_13_hex']))==43
    assert s.calls.count('breakpoints.create')==1
    with pytest.raises(ValueError):m.step()

def test_control_byte_is_not_treated_as_return(tmp_path, monkeypatch):
    m,s=monitor(tmp_path,[255,0],monkeypatch); r=m.step()
    assert r['status']=='stopped' and 'control byte' in r['reason']
    assert 'breakpoints.create' not in s.calls

def test_binding_and_unexpected_stop(tmp_path, monkeypatch):
    m,s=monitor(tmp_path,[33,0,0],monkeypatch);s.memory[s.ds*16+s.base+1]=1
    with pytest.raises(ValueError):m.step()
    m,s=monitor(tmp_path,[33,0,0],monkeypatch);s.outcome='guest_time'
    assert m.step()['status']=='stopped'


def prefetch_monitor(tmp_path,monkeypatch,code=(33,0,0)):
    from hashlib import sha256
    resource=loaded(tmp_path,{0:bytes(code)}).root;s=Session(resource.code)
    s.reg['segments']['ss']='0x3000';s.reg['general']['esp']='0x9000'
    s.memory[s.ds*16+0x979:s.ds*16+0x97b]=(0x5000).to_bytes(2,'little')
    s.memory[s.ds*16+0x5000:s.ds*16+0x5008]=bytes([0,0,0,0])+s.base.to_bytes(2,'little')*2
    s.memory[0x30000+0x9008:0x30000+0x900c]=agi_dos.LOGIC_RETURN.to_bytes(2,'little')+(0x5000).to_bytes(2,'little')
    s.reg['instruction_pointer']=hex(agi_dos.FETCH);s.reg['general']['esi']=hex(s.base)
    monkeypatch.setattr(agi_dos,'_ENGINE_SHA256',sha256(s.memory[s.cs*16:s.cs*16+agi_dos._ENGINE_LENGTH]).hexdigest())
    return AGIDOSMonitor(s,resource,cs=s.cs,ds=s.ds,code_offset=s.base),s


def test_source_fetch_and_stack_matched_logic_return(tmp_path,monkeypatch):
    m,s=prefetch_monitor(tmp_path,monkeypatch)
    def action(**kwargs):
        s.calls.append('run');s.reg['instruction_pointer']=hex(agi_dos.FAST_FETCH)
        s.reg['general']['esi']=hex(s.base+2)
        return {'outcome':'breakpoint','guest_elapsed_ms':1,'session':{'stop_reason':{
            'kind':'breakpoint','breakpoint_id':s.breakpoint_ids[-1]}}}
    s.run=action
    r=m.step();assert r['status']=='completed' and r['next_offset']==2
    def returned(**kwargs):
        s.calls.append('run');s.reg['instruction_pointer']=hex(agi_dos.LOGIC_RETURN)
        s.reg['general']['esp']='0x900a'
        return {'outcome':'breakpoint','guest_elapsed_ms':1,'session':{'stop_reason':{
            'kind':'breakpoint','breakpoint_id':s.breakpoint_ids[-1]}}}
    s.run=returned
    assert m.step()['status']=='returned'
    with pytest.raises(ValueError,match='reconciliation'):m.step()
    assert s.calls.count('run')==2


@pytest.mark.parametrize('outcome',['timeout','hook','guest_exit','guest_tsr'])
def test_unexpected_stop_cannot_replay_source_operation(tmp_path,monkeypatch,outcome):
    m,s=prefetch_monitor(tmp_path,monkeypatch)
    def interrupted(**kwargs):s.calls.append('run');return {'outcome':outcome}
    s.run=interrupted
    r=m.step();assert r['status']=='stopped' and r['stop']['outcome']==outcome
    with pytest.raises(ValueError,match='reconciliation'):m.step()
    assert s.calls.count('run')==1


def test_binding_epoch_and_engine_changes_refuse_before_execution(tmp_path,monkeypatch):
    m,s=prefetch_monitor(tmp_path,monkeypatch)
    s._runtime_epoch='restored-state'
    with pytest.raises(ValueError,match='identity changed'):m.step()
    s._runtime_epoch=None;s.memory[s.cs*16+0x50]^=1
    with pytest.raises(ValueError,match='interpreter code changed'):m.step()
    assert 'breakpoints.create' not in s.calls


def test_wrong_return_stack_is_not_a_logic_return(tmp_path,monkeypatch):
    m,s=prefetch_monitor(tmp_path,monkeypatch,code=(0,))
    def wrong_stack(**kwargs):
        s.reg['instruction_pointer']=hex(agi_dos.LOGIC_RETURN)
        s.reg['general']['esp']='0x800a'
        return {'outcome':'breakpoint','session':{'stop_reason':{
            'kind':'breakpoint','breakpoint_id':s.breakpoint_ids[-1]}}}
    s.run=wrong_stack
    r=m.step();assert r['status']=='stopped' and 'stack witness' in r['reason']


def test_total_budget_and_initial_frame_fail_closed(tmp_path,monkeypatch):
    m,s=prefetch_monitor(tmp_path,monkeypatch)
    m.guest_remaining=0
    result=m.step()
    assert result['status']=='stopped' and 'total native run budget' in result['reason']
    with pytest.raises(ValueError,match='reconciliation'):m.step()
    assert not m.history
    s.memory[0x30000+0x9008:0x30000+0x900a]=bytes(2)
    with pytest.raises(ValueError,match='initial evaluator call frame'):
        AGIDOSMonitor(s,m.resource,cs=s.cs,ds=s.ds,code_offset=s.base)


def test_foreign_breakpoint_at_owned_source_pc_is_not_accepted(tmp_path,monkeypatch):
    m,s=prefetch_monitor(tmp_path,monkeypatch)
    def foreign(**kwargs):
        s.calls.append('run')
        s.reg['instruction_pointer']=hex(agi_dos.FAST_FETCH)
        s.reg['general']['esi']=hex(s.base+2)
        return {'outcome':'breakpoint','guest_elapsed_ms':1,'session':{'stop_reason':{
            'kind':'breakpoint','breakpoint_id':'foreign-breakpoint'}}}
    s.run=foreign
    result=m.step()
    assert result['status']=='stopped' and 'stop' in result
    assert result['stop']['session']['stop_reason']['breakpoint_id']=='foreign-breakpoint'
    with pytest.raises(ValueError,match='reconciliation'):
        m.step()
    assert s.calls.count('run')==1


def test_data_access_breakpoint_at_owned_source_pc_is_not_accepted(tmp_path,monkeypatch):
    m,s=prefetch_monitor(tmp_path,monkeypatch)
    def data_access(**kwargs):
        s.calls.append('run')
        s.reg['instruction_pointer']=hex(agi_dos.FAST_FETCH)
        s.reg['general']['esi']=hex(s.base+2)
        return {'outcome':'breakpoint','guest_elapsed_ms':1,'session':{'stop_reason':{
            'kind':'breakpoint','breakpoint_id':s.breakpoint_ids[-1],
            'data_access':{'access':'w'}}}}
    s.run=data_access
    result=m.step()
    assert result['status']=='stopped' and result['stop']['session']['stop_reason']['data_access']
    with pytest.raises(ValueError,match='reconciliation'):
        m.step()
    assert s.calls.count('run')==1
