import base64
from copy import deepcopy
from hashlib import sha256

import pytest

from fdisbull.agi import load_logic
import fdisbull.agi_print as module
from fdisbull.agi_print import AGIDOSPrintObserver


class FakeSession:
    session_id='test-session'
    def __init__(self, resource):
        self.cs=0x1000;self.ds=0x2000;self.ss=0x3000;self.mem=bytearray(0x50000);self.calls=[]
        self.reg={'segments':{'cs':hex(self.cs),'ds':hex(self.ds),'ss':hex(self.ss)},'instruction_pointer':hex(0x1c06),'general':{'esi':hex(0x501),'esp':hex(0x200)}}
        def w(offset,data):self.mem[self.ds*16+offset:self.ds*16+offset+len(data)]=data
        w(0x61d+101*4,(0x1c06).to_bytes(2,'little'));w(0x979,(0x400).to_bytes(2,'little'))
        w(0x400,bytes([0,0,0,1,0,5,0,0,0,6]));w(0x500,resource.code)
        w(0x602,(4).to_bytes(2,'little'));w(0x604,b'Hi\0')
        self.mem[self.ss*16+0x200:self.ss*16+0x202]=bytes([0xfa,0x02])
    def call(self,method,args=None):
        self.calls.append(method);args=args or {}
        if method=='session.status':return {'state':'stopped','state_revision':1,'frame_id':1,'mode_id':1}
        if method=='memory.read':
            pos=int(args['address']['offset'],16);return {'data_base64':base64.b64encode(self.mem[pos:pos+args['length']]).decode()}
        if method=='breakpoints.create':return {'breakpoint_id':'test'}
        if method=='breakpoints.delete':return {}
        raise AssertionError(method)
    def registers(self):return deepcopy(self.reg)
    def run(self,**kwargs):return {'outcome':'guest_time','guest_elapsed_ms':1}
    def keyboard_state(self):return {'keyboard':{'pending_events':0,'owned_keys':0,'queued_guest_ms':0}}
    def keyboard_press(self,*args,**kwargs):self.calls.append('keyboard_press');return {}


def resource(tmp_path):
    key=b'Avis Durgan';plain=b'Hi\0';encoded=bytes(b^key[i%len(key)] for i,b in enumerate(plain))
    payload=b'\x03\x00\x65\x01\x00'+b'\x01\x07\x00\x04\x00'+encoded
    (tmp_path/'LOGDIR').write_bytes(b'\0\0\0');(tmp_path/'VOL.0').write_bytes(b'\x12\x34\0'+len(payload).to_bytes(2,'little')+payload)
    return load_logic(tmp_path/'LOGDIR',tmp_path,0,profile='2.917')


def setup(tmp_path,monkeypatch):
    res=resource(tmp_path);s=FakeSession(res)
    monkeypatch.setattr(module,'_ENGINE_SHA256',sha256(s.mem[s.cs*16:s.cs*16+module._ENGINE_LENGTH]).hexdigest())
    return res,s


def test_admission_and_no_replay_after_interruption(tmp_path,monkeypatch):
    res,s=setup(tmp_path,monkeypatch);o=AGIDOSPrintObserver(s,{0:res},cs=s.cs,ds=s.ds)
    assert o.offset==0 and o.message_id==1 and o.mode=='blocking'
    result=o.finish();assert result['status']=='incomplete' and not result['input_attempted']
    count=len(s.calls);assert o.finish()==result and len(s.calls)==count
    assert 'keyboard_press' not in s.calls

@pytest.mark.parametrize('change',[
    lambda s:s.reg.update(instruction_pointer='0x1234'),
    lambda s:s.mem.__setitem__(s.ss*16+0x200,0),
    lambda s:s.mem.__setitem__(s.ds*16+0x500,0),
    lambda s:s.mem.__setitem__(s.ds*16+0x604,0),
])
def test_refuses_unbound_admission(tmp_path,monkeypatch,change):
    res,s=setup(tmp_path,monkeypatch);change(s)
    with pytest.raises(ValueError):AGIDOSPrintObserver(s,{0:res},cs=s.cs,ds=s.ds)

def test_input_failure_is_retained_without_retry(tmp_path,monkeypatch):
    res,s=setup(tmp_path,monkeypatch);o=AGIDOSPrintObserver(s,{0:res},cs=s.cs,ds=s.ds)
    count={'run':0,'frame':0,'input':0}
    def run(**kwargs):
        count['run']+=1
        if count['run']==2:return {'outcome':'guest_time','guest_elapsed_ms':50}
        return {'outcome':'breakpoint','guest_elapsed_ms':1,'session':{'stop_reason':{'kind':'breakpoint','breakpoint_id':'test'}}}
    def screenshot(*args,**kwargs):
        count['frame']+=1
        return {'artifact':'frame','metadata':{'frame_id':count['frame'],'mode_id':1}}
    def press(*args,**kwargs):
        count['input']+=1
        raise RuntimeError('transport lost after key attempt')
    s.run=run;s.screenshot=screenshot;s.keyboard_press=press
    s.mem[s.ds*16+0xd15:s.ds*16+0xd17]=b'\x01\x00'
    monkeypatch.setattr(o,'_modal',lambda: {'qualified':'synthetic'})
    result=o.finish();assert result['status']=='incomplete' and result['input_attempted'] and count['input']==1
    assert o.finish()==result and count['input']==1

def test_pending_parser_release_settles_before_dismissal(tmp_path,monkeypatch):
    res,s=setup(tmp_path,monkeypatch);o=AGIDOSPrintObserver(s,{0:res},cs=s.cs,ds=s.ds)
    calls={'run':0,'keyboard':0,'frame':0,'input':0}
    def run(**kwargs):
        calls['run']+=1
        if calls['run']==2:return {'outcome':'guest_time','guest_elapsed_ms':50}
        return {'outcome':'breakpoint','guest_elapsed_ms':1,'session':{'stop_reason':{'kind':'breakpoint','breakpoint_id':'test'}}}
    def keyboard():
        calls['keyboard']+=1
        return {'keyboard':{'pending_events':1 if calls['keyboard']==1 else 0,'owned_keys':0,'queued_guest_ms':0}}
    def screenshot(*args,**kwargs):
        calls['frame']+=1
        return {'artifact':'frame','metadata':{'frame_id':calls['frame'],'mode_id':1}}
    def press(*args,**kwargs):
        assert calls['run']==3 and calls['keyboard']>=2
        calls['input']+=1
        raise RuntimeError('stop after qualified input attempt')
    s.run=run;s.keyboard_state=keyboard;s.screenshot=screenshot;s.keyboard_press=press
    s.mem[s.ds*16+0xd15:s.ds*16+0xd17]=b'\x01\x00'
    monkeypatch.setattr(o,'_modal',lambda: {'qualified':'synthetic'})
    result=o.finish()
    assert result['keyboard_before']['keyboard']['pending_events']==1
    assert result['input_attempted'] and calls['input']==1
    assert o.finish()==result and calls['input']==1

@pytest.mark.parametrize('change',[
    lambda s:s.reg['general'].update(esi='0x502'),
    lambda s:s.mem.__setitem__(s.ds*16+0x10a,1),
    lambda s:s.mem.__setitem__(s.ds*16+9+21,1),
])
def test_stale_operand_or_mode_refuses_before_resume(tmp_path,monkeypatch,change):
    res,s=setup(tmp_path,monkeypatch);o=AGIDOSPrintObserver(s,{0:res},cs=s.cs,ds=s.ds)
    change(s);result=o.finish()
    assert result['status']=='incomplete' and not result['native_execution_attempted']
    assert result['native_execution'] is False and not result['input_attempted']
    assert 'changed after admission' in result['error']

def test_lost_run_response_preserves_unknown_execution(tmp_path,monkeypatch):
    res,s=setup(tmp_path,monkeypatch);o=AGIDOSPrintObserver(s,{0:res},cs=s.cs,ds=s.ds)
    def lost(**kwargs):raise TimeoutError('response lost')
    s.run=lost;result=o.finish()
    assert result['status']=='incomplete' and result['native_execution_attempted']
    assert result['native_execution'] is None and not result['input_attempted']
    assert o.finish()==result

def test_lost_later_run_retains_earlier_native_evidence(tmp_path,monkeypatch):
    res,s=setup(tmp_path,monkeypatch);o=AGIDOSPrintObserver(s,{0:res},cs=s.cs,ds=s.ds)
    calls={'run':0}
    def run(**kwargs):
        calls['run']+=1
        if calls['run']>1:raise TimeoutError('later response lost')
        return {'outcome':'breakpoint','guest_elapsed_ms':1,'session':{'stop_reason':{'kind':'breakpoint','breakpoint_id':'test'}}}
    s.run=run;s.screenshot=lambda *a,**k:{'artifact':'frame','metadata':{'frame_id':1,'mode_id':1}}
    monkeypatch.setattr(o,'_modal',lambda:{'qualified':'synthetic'})
    result=o.finish()
    assert result['status']=='incomplete' and result['native_execution_attempted']
    assert result['native_execution'] is True and not result['input_attempted']

def test_rejected_key_never_resumes_or_retries(tmp_path,monkeypatch):
    res,s=setup(tmp_path,monkeypatch);o=AGIDOSPrintObserver(s,{0:res},cs=s.cs,ds=s.ds)
    calls={'run':0,'frame':0,'input':0}
    def run(**kwargs):
        calls['run']+=1
        if calls['run']==2:return {'outcome':'guest_time','guest_elapsed_ms':50}
        return {'outcome':'breakpoint','guest_elapsed_ms':1,'session':{'stop_reason':{'kind':'breakpoint','breakpoint_id':'test'}}}
    def screenshot(*args,**kwargs):
        calls['frame']+=1;return {'artifact':'frame','metadata':{'frame_id':calls['frame'],'mode_id':1}}
    def press(*args,**kwargs):
        calls['input']+=1;return {'accepted':False}
    s.run=run;s.screenshot=screenshot;s.keyboard_press=press
    s.mem[s.ds*16+0xd15:s.ds*16+0xd17]=b'\x01\x00'
    monkeypatch.setattr(o,'_modal',lambda:{'qualified':'synthetic'})
    result=o.finish()
    assert result['status']=='incomplete' and result['input_attempted'] and result['input']=={'accepted':False}
    assert calls['run']==3 and calls['input']==1
    assert o.finish()==result and calls['run']==3 and calls['input']==1
