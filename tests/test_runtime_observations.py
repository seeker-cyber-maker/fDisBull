import base64
import pytest
from fdisbull.runtime_observations import RuntimeObservationMixin, capture_observations, validate_observations
from fdisbull.scene_values import ObservationReads, evaluate_comparison


class Session(RuntimeObservationMixin):
    run_id='run';version={'id':1};runtime_load=0x1000
    metadata={'source_sha256':'source','version_sha256':'version'}
    def __init__(self):self.data=bytearray(1024*1024);self.events=[];self.frames=0;self.stopped=True
    def call(self,method,params=None):
        if method=='session.status':return {'state':'stopped' if self.stopped else 'running'}
        if method=='state.get_registers':return {'cpu_mode':'real'}
        if method=='memory.read':
            start=int(params['address']['offset'],16)
            return {'data_base64':base64.b64encode(self.data[start:start+params['length']]).decode()}
        raise ValueError(method)
    def _event(self,name,data):self.events.append((name,data))
    def frame_probe(self,points):self.frames+=1;return {'frame_id':7}
    def registers(self):return {'instruction_pointer':'10'}
    def status(self):return {'state':'stopped'}


def bound():
    s=Session();s.data[0x16c17:0x16c1b]=b'AB\x12\x34'
    b=s.bind_runtime_memory('ego',0x16c17,length=4,expected_hex='4142',provenance={'source':'fixture'})
    return s,b


def test_runtime_binding_scope_identity_epoch_and_events():
    s,b=bound();assert s.runtime_memory('ego',offset=2,length=2)['hex']=='1234'
    assert s.runtime_memory(b['id'],offset=0,length=2)['witness_hex']=='4142'
    with pytest.raises(ValueError):s.runtime_memory('ego',offset=3,length=2)
    with pytest.raises(ValueError):s.bind_runtime_memory('ego',0,length=2,expected_hex='0000',provenance='x')
    s.data[0x16c17]=0
    with pytest.raises(ValueError,match='witness mismatch'):s.runtime_memory('ego',length=1)
    s.data[0x16c17]=65;s.metadata=dict(s.metadata,source_sha256='different')
    with pytest.raises(ValueError,match='context changed'):s.runtime_memory('ego',length=1)
    s._invalidate_runtime_bindings()
    with pytest.raises(ValueError,match='invalidated'):s.runtime_memory(b['id'],length=1)
    assert [e[0] for e in s.events]==['runtime-memory-bind','runtime-memory-read','runtime-memory-read']


def test_bind_requires_paused_valid_nonzero_identity_and_range():
    s=Session()
    for args in [dict(address=0xfffff,length=2,expected_hex='00'),dict(address=0,length=1,expected_hex='00',mask_hex='00')]:
        with pytest.raises(ValueError):s.bind_runtime_memory('x',provenance='test',**args)
    s.stopped=False
    with pytest.raises(ValueError,match='paused'):s.bind_runtime_memory('x',0,length=1,expected_hex='00',provenance='test')


def test_capture_deduplicates_and_preserves_missing_without_frame():
    s,_=bound();ref={'binding':'ego','offset':2,'type':'u16'}
    specs={'x':{'runtime_memory':ref},'same':{'runtime_memory':ref},'ip':{'register':'instruction_pointer'}}
    validate_observations(specs);result=capture_observations(s,specs)
    assert result['complete'] and result['values']['x']==0x3412 and len(result['captures'])==1 and s.frames==0
    result=capture_observations(s,{'missing':{'runtime_memory':dict(ref,binding='missing')}})
    assert not result['complete'] and 'missing' in result['errors']
    assert capture_observations(s,{'frame':{'frame':'frame_id'}})['values']['frame']==7
    reads=ObservationReads(s)
    assert evaluate_comparison({'left':{'runtime_memory':ref},'op':'eq','right':0x3412},reads,None)[0]


def test_provenance_bound_and_context_change_marks_incomplete():
    s=Session()
    with pytest.raises(ValueError,match='64 KiB'):
        s.bind_runtime_memory('x',0,length=1,expected_hex='00',provenance='x'*65537)
    s,b=bound()
    original=s.call;count=[0]
    def changing(method,params=None):
        result=original(method,params)
        if method=='session.status':
            count[0]+=1;result['state_revision']=count[0]
        return result
    s.call=changing
    result=capture_observations(s,{'x':{'runtime_memory':{'binding':'ego','offset':2,'type':'u16'}}})
    assert not result['complete'] and 'state_revision' in result['errors']['context']
