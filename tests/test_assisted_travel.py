"""Assisted travel checks: external observations and real guest execution."""
import base64
from copy import deepcopy
import hashlib
import os

import pytest

from fdisbull.assisted_travel import AssistedTravelSessionMixin, validate_travel
from fdisbull.runtime_observations import RuntimeObservationMixin
from fdisbull.project import Project
from test_dos_loader import mz_file


class Scene:
    revision = 'scene-revision'
    def __init__(self, session): self.session = session
    def check(self): return {'status':self.session.scene_status, 'complete':self.session.scene_complete}


class Session(AssistedTravelSessionMixin, RuntimeObservationMixin):
    run_id='run'; version={'id':1}; runtime_load=0x1000
    metadata={'source_sha256':'source','version_sha256':'version'}
    def __init__(self):
        self.data=bytearray(0x100000); self.data[0x1100:0x1105]=b'AB\x01\x01\x00'
        self.events=[]; self.writes=[]; self.scene_status='matched'; self.scene_complete=True
        self.fail_write_number=None
        self.bind_runtime_memory('actor',0x1100,length=5,expected_hex='4142',provenance='fixture')
    def scene(self,revision): return Scene(self)
    def keyboard_state(self): return {'keyboard':{'pending_events':0,'owned_keys':0}}
    def call(self,method,params=None):
        if method=='session.status': return {'state':'stopped'}
        if method=='state.get_registers': return {'cpu_mode':'real'}
        if method=='memory.read':
            addr=int(params['address']['offset'],16)
            return {'data_base64':base64.b64encode(self.data[addr:addr+params['length']]).decode()}
        if method=='memory.write':
            if self.fail_write_number==len(self.writes)+1: raise ValueError('write rejected')
            addr=int(params['address']['offset'],16); data=base64.b64decode(params['data_base64'])
            assert hashlib.sha256(self.data[addr:addr+len(data)]).hexdigest()==params['expected_sha256']
            self.data[addr:addr+len(data)]=data; self.writes.append((addr,data)); return {}
        raise ValueError(method)
    def _event(self,name,data): self.events.append((name,deepcopy(data)))
    def screenshot(self,*args,**kwargs): return {'artifact':'diagnostic'}
    def run(self,**kwargs): return {'outcome':'guest_time','guest_elapsed_ms':1,'hook_hits':[]}
    def keyboard_press(self,**kwargs): return {'queued':True}
    def keyboard_type(self,**kwargs): return {'queued':True}


def plan():
    return {'format':'fdisbull-assisted-travel-1','kind':'within-room','scene_revision':'scene-revision',
            'observations':{'x':{'runtime_memory':{'binding':'actor','offset':2,'type':'u8'}},
                            'room':{'runtime_memory':{'binding':'actor','offset':3,'type':'u8'}}},
            'context':{'field':'room','op':'eq','value':1}, 'writes':[{'binding':'actor','offset':2,'type':'u8','value':5}],
            'inputs':[], 'until':{'field':'x','op':'eq','value':5},
            'destination':{'label':'same','room_field':'room','room_value':1},
            'provenance':{'fixture':'explicit'},'guest_ms':10,'slice_ms':1}


def test_reject_incomplete_scene_invalid_witness_unknown_or_overlapping_fields_before_write():
    for mutation in ('incomplete','witness','unknown','overlap'):
        s=Session(); p=plan()
        if mutation=='incomplete': s.scene_complete=False
        if mutation=='witness': s.data[0x1100]=0
        if mutation=='unknown': p['writes'][0]['binding']='unknown'
        if mutation=='overlap': p['writes'].append(dict(p['writes'][0]))
        result=s.assisted_travel(p)
        assert not result['ok'] and not s.writes, (mutation,result)


def test_kind_requires_observed_room_and_jump_requires_input():
    s=Session(); p=plan(); p['destination']['room_value']=2
    assert not s.assisted_travel(p)['ok'] and not s.writes
    p['kind']='room-jump'
    with pytest.raises(ValueError,match='requires original guest transition input'): validate_travel(p)


def test_partial_failure_retains_first_write_without_rollback_claim():
    s=Session(); p=plan()
    p['writes'].append({'binding':'actor','offset':4,'type':'u8','value':2})
    s.fail_write_number=2
    result=s.assisted_travel(p)
    assert not result['ok'] and result['writes'][0]['after_hex']=='05'
    assert s.data[0x1102]==5 and 'rollback' not in result


def _guest_binary():
    # VGA mode, DS=CS. Poll BIOS keyboard; only x while x=5 changes room 1 to 2.
    code=bytearray.fromhex('b81300cd100e1f')
    loop=len(code); code += bytes.fromhex('b401cd16')
    def branch(op,target):
        code.extend([op,(target-(len(code)+2)) & 255])
    branch(0x74,loop)
    code += bytes.fromhex('b400cd163c78'); branch(0x75,loop)
    code += bytes.fromhex('803e020105'); branch(0x75,loop)
    code += bytes.fromhex('c606030102'); branch(0xeb,loop)
    return mz_file(bytes(code).ljust(0x100,b'\0') + b'AB\x01\x01' + bytes(1024),ss=0,sp=0x400),loop


def _scene(snapshot):
    return {'format':'fdisbull-scene-1','width':320,'height':200,'mode_id':snapshot['metadata']['mode_id'],
            'reference':snapshot['artifact'],'context':{'state':'fixture','triggers':['fixture boot']},
            'match':{'constant':True},'objects':[{'name':'fixture','context':{'state':'fixture','triggers':['boot']},
            'area':{'rect':[1,1,5,5]},'point':[2,2], 'visible':{'constant':True}, 'ready':{'constant':True},
            'enabled':{'constant':True},'action':{'kind':'press','key':'x'},'outcome':{'constant':False}}]}


def test_native_synthetic_original_room_input_and_breakpoint(tmp_path):
    backend=os.environ.get('FDISBULL_DOSBOX')
    if not backend: pytest.skip('FDISBULL_DOSBOX required')
    game=tmp_path/'game'; game.mkdir(); binary=game/'GAME.EXE'; data,loop=_guest_binary(); binary.write_bytes(data)
    path=tmp_path/'test.fdb'
    with Project.create(path,binary) as p: p.analyze(max_instructions=30)
    with Project(path) as p, p.debugger(backend,game) as d:
        d.run(guest_ms=50,timeout_ms=5000,fast_forward=True)
        scene=p.debug_save_scene('fixture',_scene(d.screenshot()))
        d.bind_runtime_memory('actor',d.runtime_base+0x100,length=4,expected_hex='4142',provenance={'test':'authored MZ'})
        spec=plan();spec['scene_revision']=scene['id']
        # A native timing poll can span more than this unit collaborator's
        # ten fake ticks. Keep a finite budget large enough for a real slice.
        spec.update(guest_ms=500,slice_ms=10)
        inside=d.assisted_travel(spec)
        assert inside['ok'] and inside['after']['values']=={'x':5,'room':1},inside
        jump=deepcopy(spec);jump.update(kind='room-jump',inputs=[{'key':'x'}])
        jump['destination']={'label':'room 2','room_field':'room','room_value':2}
        jump['until']={'field':'room','op':'eq','value':2}
        jumped=d.assisted_travel(jump)
        assert jumped['ok'] and jumped['after']['values']['room']==2 and jumped['inputs'],jumped
        bp=d.breakpoint('1000:%04x'%loop)
        again=deepcopy(spec);again['context']={'field':'room','op':'eq','value':2}
        again['destination']['room_value']=2
        stopped=d.assisted_travel(again)
        assert not stopped['ok'] and stopped['status']=='stopped' and stopped['stop']['outcome']=='breakpoint',stopped
        d.delete_breakpoint(bp['breakpoint_id'])


def test_room_identity_cannot_be_directly_written():
    s=Session(); p=plan()
    p['kind']='room-jump'; p['destination']['room_value']=2; p['inputs']=[{'key':'x'}]
    p['writes']=[{'binding':'actor','offset':3,'type':'u8','value':2}]
    result=s.assisted_travel(p)
    assert not result['ok'] and not s.writes and s.data[0x1103]==1


def test_write_readback_failure_records_attempt_without_rollback_claim():
    s=Session(); p=plan(); original=s.runtime_memory
    def fail_readback(*args,**kwargs):
        if s.writes: raise ValueError('readback unavailable')
        return original(*args,**kwargs)
    s.runtime_memory=fail_readback
    result=s.assisted_travel(p)
    assert not result['ok'] and s.data[0x1102]==5
    assert result['writes'] and result['writes'][0]['field']['offset']==2
    assert not result['writes'][0].get('verified',False)
    assert 'rollback' not in result


def test_stale_field_is_rejected_before_any_write():
    s=Session(); p=plan(); read=s.runtime_memory; seen=[]
    def change_between_preflight_and_write(*args,**kwargs):
        if kwargs.get('offset')==2:
            seen.append(1)
            if len(seen)==3: s.data[0x1102]=7
        return read(*args,**kwargs)
    s.runtime_memory=change_between_preflight_and_write
    result=s.assisted_travel(p)
    assert not result['ok'] and 'stale' in result['error'] and not s.writes


def test_hook_stop_is_preserved_and_never_reported_success():
    s=Session(); s.run=lambda **kw: {'outcome':'guest_time','guest_elapsed_ms':1,'hook_hits':[{'id':'hook'}]}
    result=s.assisted_travel(plan())
    assert result['status']=='stopped' and not result['ok']
    assert result['stop']['hook_hits']==[{'id':'hook'}]


def test_late_true_outcome_remains_incomplete():
    s=Session();s.run=lambda **kw:{'outcome':'guest_time','guest_elapsed_ms':11,'hook_hits':[]}
    result=s.assisted_travel(plan())
    assert result['after']['values']['x']==5 and not result['ok'] and not result['complete']
    assert 'outside its budget' in result['error']


def test_input_failure_retains_attempt_after_partial_delivery():
    s=Session(); p=plan();p['inputs']=[{'key':'x'}]
    def fail(**kwargs):raise ValueError('Response lost after delivery')
    s.keyboard_press=fail
    result=s.assisted_travel(p)
    assert result['writes'][0]['verified'] and result['inputs'][0]['outcome']=='unknown'
    assert not result['complete']


def test_destination_scene_must_match_after_memory_goal():
    s=Session();p=plan();p['destination_scene']='destination';polls=[]
    class Destination:
        revision='destination'
        def check(self):
            polls.append(1)
            return {'status':'matched' if len(polls)>1 else 'mismatch','complete':True}
    source=s.scene;s.scene=lambda revision:Destination() if revision=='destination' else source(revision)
    result=s.assisted_travel(p)
    assert result['ok'] and len(result['runs'])==2 and len(polls)==2


def test_missing_destination_capture_never_completes_memory_goal():
    s=Session();p=plan();p['destination_scene']='destination'
    class Destination:
        revision='destination'
        def check(self):return {'status':'unavailable','complete':False}
    source=s.scene;s.scene=lambda revision:Destination() if revision=='destination' else source(revision)
    result=s.assisted_travel(p)
    assert not result['complete'] and result['writes'][0]['verified']
    assert result['after']['values']['x']==5 and len(result['runs'])==1


def test_observed_cleanup_runs_once_and_requires_another_capture():
    s=Session();p=plan();p['cleanup']={'when':{'field':'x','op':'eq','value':5},'inputs':[{'key':'right'}]}
    result=s.assisted_travel(p)
    assert result['ok'] and len(result['runs'])==2
    assert len(result['inputs'])==1 and result['inputs'][0]['phase']=='cleanup'


def test_cleanup_validation_precedes_all_writes():
    s=Session();p=plan();p['cleanup']={'when':{'field':'missing','op':'eq','value':0},'inputs':[{'key':'right'}]}
    with pytest.raises(ValueError):s.assisted_travel(p)
    assert not s.writes


def test_guarded_set_bits_preserves_other_field_bits():
    s=Session();p=plan();s.data[0x1102]=2
    p['writes']=[{'binding':'actor','offset':2,'type':'u8','set_bits':4}]
    p['until']={'field':'x','op':'eq','value':6}
    result=s.assisted_travel(p)
    assert result['ok'] and s.data[0x1102]==6
    assert result['writes'][0]['before_hex']=='02' and result['writes'][0]['after_hex']=='06'


def test_ambiguous_write_operator_is_rejected_before_effects():
    s=Session();p=plan();p['writes'][0]['set_bits']=4
    with pytest.raises(ValueError):s.assisted_travel(p)
    assert not s.writes

@pytest.mark.parametrize('kind', ['within-room', 'room-jump'])
def test_fair_play_refuses_before_plan_reads_or_guest_access(kind):
    s=Session(); s._allow_assisted_travel=False
    p=plan(); p['kind']=kind
    # An invalid plan still cannot reach validation or guest interaction.
    p['writes'] = None
    before=bytes(s.data)
    s.scene=lambda *args: pytest.fail('scene read during refusal')
    result=s.assisted_travel(p)
    assert result['status']=='refused' and result['policy']=={'assisted_travel':False}
    assert bytes(s.data)==before and not s.writes and s.events[-1][1]==result
