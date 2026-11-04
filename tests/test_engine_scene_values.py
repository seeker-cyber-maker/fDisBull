"""VM observations retain their own identity and a single stopped snapshot."""
import pytest

from fdisbull.scene_values import ObservationReads, before_refs, comparison, evaluate_comparison
from fdisbull.scenes import video_signature
from fdisbull.debug_script import validate_script, execute_script


class Engine:
    def __init__(self):
        self.calls=0
        self.state={'vars':[9,7],'flags':[True],'objects':[{'x':12}]}

    def engine_state(self):
        self.calls+=1
        return self.state


def test_engine_comparisons_share_one_snapshot_and_preserve_before():
    engine=Engine();reads=ObservationReads(engine)
    score={'engine_state':{'path':['vars',1]}}
    rule={'left':score,'op':'eq','right':7}
    comparison(rule)
    assert evaluate_comparison(rule,reads,None)==(True,7,7)
    assert reads.engine_scalar({'path':['flags',0]})==1
    assert reads.engine_scalar({'path':['objects',0,'x']})==12
    assert engine.calls==1
    outcome={'left':score,'op':'eq','right':{'before':score}}
    comparison(outcome,allow_before=True)
    frozen=reads.freeze(list(before_refs(outcome)),{'run':'one'})
    engine.state={'vars':[9,8]}
    after=ObservationReads(engine)
    assert evaluate_comparison(outcome,after,frozen)==(False,8,7)


@pytest.mark.parametrize('path', [[],['vars',True],['vars',-1],['__class__','bad.path'],['vars']*9])
def test_engine_paths_refuse_invalid_fields(path):
    with pytest.raises(ValueError):
        comparison({'left':{'engine_state':{'path':path}},'op':'eq','right':0})


def test_unavailable_or_nonscalar_engine_state_stays_unknown():
    reads=ObservationReads(Engine())
    with pytest.raises(ValueError,match='integer or boolean'):
        reads.engine_scalar({'path':['vars']})
    with pytest.raises(ValueError):reads.engine_scalar({'path':['missing']})
    assert all('error' in capture for capture in reads.captures.values())


def test_scene_video_identity_binds_replacement_engine_resources():
    native=dict(width=320,height=200,source_bpp=8,double_width=False,double_height=False)
    one=dict(native,backend='scummvm-agi',resource_manifest_sha256='a'*64,resource_layers_sha256='c'*64)
    two=dict(one,resource_manifest_sha256='b'*64)
    assert video_signature(one)!=video_signature(native)
    assert video_signature(one)!=video_signature(two)
    assert video_signature(one)!=video_signature(dict(one,resource_layers_sha256='d'*64))
    with pytest.raises(ValueError,match='manifest'):
        video_signature(dict(native,backend='scummvm-agi'))


def test_saved_engine_script_binds_its_run_contract_before_any_execution():
    script={'format':'fdisbull-script-1','backend':'scummvm-agi',
            'steps':[{'op':'run','max_instructions':20,'guest_ms':100}]}
    assert validate_script(script)==script['steps']
    script['steps'][0]['expect']='budget'
    assert validate_script(script)==script['steps']
    with pytest.raises(ValueError,match='backend differs'):
        validate_script(script,session=Engine())
    script['steps'][0].pop('expect')
    with pytest.raises(TypeError):
        validate_script({'format':'fdisbull-script-1','steps':script['steps']})


@pytest.mark.parametrize('operation',['step','engine-cycle'])
def test_incomplete_engine_control_stops_saved_script_before_next_mutation(operation):
    class Session:
        metadata={'backend':'scummvm-agi'};run_id='run'
        script_operations={'step','engine-cycle','engine-set'}
        def __init__(self):self.writes=0
        def _artifact(self,*args):return {'artifact':'receipt'}
        def step(self,*,timeout_ms=1000):return {'completed':False,'steps':[]}
        def run_until_cycle(self,*,timeout_ms=1000):return {'outcome':'timeout'}
        def write_engine_state(self,kind,index,value):self.writes+=1
    session=Session()
    result=execute_script(session,{'format':'fdisbull-script-1','backend':'scummvm-agi',
        'steps':[{'op':operation},{'op':'engine-set','kind':'var','index':3,'value':1}]},timeout_ms=1000)
    assert result['ok'] is False and result['completed_steps']==0
    assert result['error']['op']==operation and session.writes==0
