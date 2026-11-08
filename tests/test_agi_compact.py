"""Authored source graphs; no original game code or state is embedded."""
from copy import deepcopy
import json

import pytest

from fdisbull.agi_compact import lift_compact
from fdisbull.cli import respond, main
from fdisbull.decoder_modules import builtin_registry, lift_input
from fdisbull.interaction_il import execute_il
from test_agi_control import loaded, lift, conditional, source_trace


def compact(program,state,**options):
    return lift(program,state,control_flow='compact',**options)


def test_many_diamonds_share_each_source_join_and_match_independent_contract(tmp_path):
    # Twelve authored independent choices. Each false path skips one assignment.
    code=b''.join(bytes([255,1,0,n,255,3,0,3,1,n]) for n in range(12))+b'\x00'
    program=loaded(tmp_path,{0:code})
    with pytest.raises(ValueError,match='budget'):
        lift(program,{'$agi_v0':0,'$agi_v1':99})
    projection=compact(program,{'$agi_v0':0,'$agi_v1':99})
    assert projection['static_metrics']=={'source_instructions':25,'continuations':25,'shared_joins':12}
    assert len(json.dumps(projection['uil']).encode())<18000
    for v in range(256):
        result=execute_il(projection['uil'],{'$agi_v0':v,'$agi_v1':99})
        assert result['complete'] and result['state']['$agi_v1']==(v if v<12 else 99)
        assert len(source_trace(projection,result))==13+(v<12)
        assert result['control']['call_stack']==[]


def test_shared_callee_multiple_calls_and_return_arms_match_tree(tmp_path):
    caller=bytes.fromhex('1601040302160104040200')
    callee=bytes.fromhex('ff0701ff040003020a0003021400')
    program=loaded(tmp_path,{0:caller,1:callee},callee_entries={1:0})
    state={'$agi_f1':False,'$agi_v2':0,'$agi_v3':0,'$agi_v4':0}
    projection=compact(program,state)
    tree=lift(program,state)
    for flag in (False,True):
        before=dict(state,**{'$agi_f1':flag})
        actual=execute_il(projection['uil'],before)
        expected=execute_il(tree['uil'],before)
        assert actual['complete'] and actual['state']==expected['state']
        assert source_trace(projection,actual)==source_trace(tree,expected)
        targets=[c['transfer']['target'] for c in projection['uil']['continuations'].values()
                 if c['transfer']['op']=='call']
        assert len(targets)==2 and len(set(targets))==1
        assert actual['control_trace'][1]['call_stack']==['agi_0002']


def test_global_callee_stop_does_not_admit_unknown_caller_continuation(tmp_path):
    program=loaded(tmp_path,{0:bytes.fromhex('1601f000'),1:bytes.fromhex('030207650100')},
                   callee_entries={1:0},stop_points=[(1,3)])
    projection=compact(program,{'$agi_v2':0})
    assert projection['uil']['continuations'][projection['uil']['entry']]['transfer']['resume'] is None
    result=execute_il(projection['uil'])
    assert result['complete'] and result['state']=={'$agi_v2':7}
    assert result['control']['stop']=='stop' and result['control']['call_stack']==[None]
    assert source_trace(projection,result)==[(0,0),(1,0),(1,3)]


def test_one_callee_branch_stops_other_returns_to_caller(tmp_path):
    program=loaded(tmp_path,{0:bytes.fromhex('160103030900'),1:bytes.fromhex('ff0701ff0500030207650100')},
                   callee_entries={1:0},stop_points=[(1,9)])
    state={'$agi_f1':False,'$agi_v2':0,'$agi_v3':42}
    projection=compact(program,state)
    for flag in (False,True):
        before=dict(state,**{'$agi_f1':flag})
        out=execute_il(projection['uil'],before)
        old=execute_il(lift(program,state)['uil'],before)
        assert out['complete'] and out['state']==old['state']
        assert source_trace(projection,out)==source_trace(lift(program,state),old)
        assert out['control']['stop']==('stop' if flag else 'return')


def test_opaque_engine_actions_are_explicit_and_never_evaluated(tmp_path):
    # An inactive load.view is still a declared whole-graph execution blocker.
    code=bytes.fromhex('ff0701ff02001e0500')
    program=loaded(tmp_path,{0:code})
    with pytest.raises(ValueError,match='unsupported'):
        compact(program,{'$agi_f1':False})
    projection=compact(program,{'$agi_f1':False},allow_opaque=True)
    assert projection['qualification']=='control_flow_only'
    assert projection['opaque_operations'][0]['instruction']=='load.view'
    out=execute_il(projection['uil'])
    assert not out['complete'] and out['status']=='refused' and 'opaque' in out['error']
    assert out['state']=={'$agi_f1':False} and out['visited']==[] and out['events']==[]
    with pytest.raises(ValueError,match='compact'):
        lift(program,{'$agi_f1':False},allow_opaque=True)


@pytest.mark.parametrize('code,message',[('fefdff','cyclic'),('f000','unsupported'),
                                      ('170100','indirect'),('1e','truncated')])
def test_bad_or_unknown_source_never_becomes_an_opaque_noop(tmp_path,code,message):
    with pytest.raises(ValueError,match=message):
        compact(loaded(tmp_path,{0:bytes.fromhex(code)}),{},allow_opaque=True)


def test_compact_options_reach_json_and_real_cli(tmp_path,capsys):
    program=loaded(tmp_path,{0:conditional(bytes([1,1,5]))})
    state={'$agi_v1':5,'$agi_v2':0}
    params=dict(module='fdisbull.agi.2.917.subset',path=str(tmp_path/'LOGDIR'),
                volume_dir=str(tmp_path),logic=0,profile='2.917',initial_state=state,
                control_flow='compact')
    response=respond({'id':1,'method':'module-lift','params':params})
    assert response['ok'] and response['result']['uil']['format']=='fdisbull-il-2'
    path=tmp_path/'state.json';path.write_text(json.dumps(state))
    assert main(['module-lift',params['module'],params['path'],'--volume-dir',str(tmp_path),
                 '--logic','0','--profile','2.917','--state-file',str(path),
                 '--control-flow','compact'])==0
    result=json.loads(capsys.readouterr().out)['result']
    assert result['control_flow']=='shared_continuations'
    uil_path=tmp_path/'uil.json';uil_path.write_text(json.dumps(result['uil']))
    assert main(['il-run',str(uil_path)])==0
    executed=json.loads(capsys.readouterr().out)
    assert executed['complete'] and executed['state']=={'$agi_v1':5,'$agi_v2':10}
    opened=builtin_registry().open(params['module'],params['path'],volume_dir=str(tmp_path),logic=0,profile='2.917')
    assert lift_input(opened,initial_state=state,control_flow='compact')['snapshot']==result['snapshot']


def test_compact_revision_storage_survives_restart_with_source_checks(tmp_path):
    import hashlib
    from fdisbull.il_recovery import save_il,load_il
    from fdisbull.project import Project
    document=compact(loaded(tmp_path,{0:b'\x03\x01\x07\x00'}),{'$agi_v1':0})['udl']
    binary=tmp_path/'T.COM';binary.write_bytes(bytes.fromhex('b8004ccd21'))
    db=tmp_path/'private.fdb'
    volume=(tmp_path/'VOL.0').read_bytes()
    document['evidence']['captured-file']={'file':'resource-volume',
        'sha256':hashlib.sha256(volume).hexdigest(),'range':[0,len(volume)],'bytes':volume.hex()}
    with Project.create(db,binary,image='com') as p:
        p.attach_file(tmp_path/'VOL.0',name='resource-volume')
        receipt=save_il(p,'compact',document)
    with Project(db) as p:
        recovered=load_il(p,receipt['id'])['document']
        wrong=deepcopy(document);wrong['evidence']['captured-file']['bytes']='00'*len(volume)
        with pytest.raises(ValueError,match='evidence'):
            save_il(p,'wrong',wrong)
    assert recovered==document and execute_il(recovered)['state']=={'$agi_v1':7}


def test_shared_callee_depth_is_checked_again_in_a_deeper_call_chain(tmp_path):
    program=loaded(tmp_path,{0:bytes.fromhex('1602160100'),1:bytes.fromhex('160200'),
                              2:bytes.fromhex('160300'),3:b'\x00'},
                   callee_entries={1:0,2:0,3:0})
    with pytest.raises(ValueError,match='depth budget'):
        compact(program,{},max_call_depth=2)
    out=execute_il(compact(program,{},max_call_depth=3)['uil'],max_call_depth=3)
    assert out['complete'] and max(len(t['call_stack']) for t in out['control_trace'])==3
    recursive=loaded(tmp_path,{0:bytes.fromhex('160100'),1:bytes.fromhex('160100')},callee_entries={1:0})
    with pytest.raises(ValueError,match='recursive'):
        compact(recursive,{})


def test_v1_only_proof_and_scene_consumers_refuse_graphs(tmp_path):
    from fdisbull.udl_blocks import lift_asm_block,verify_block
    from fdisbull.il_scenes import ILSceneBackend
    from test_il_scenes import definition
    document=compact(loaded(tmp_path,{0:bytes.fromhex('03010000')}),{'$agi_v1':0})['uil']
    native=lift_asm_block(bytes.fromhex('b80000'),{'ax':'$agi_v1'},inputs=[],outputs=['ax'])
    with pytest.raises(ValueError,match='tree IL v1'):
        verify_block(native,document)
    scene=definition();scene['programs'][next(iter(scene['programs']))]=document
    with pytest.raises(ValueError,match='tree IL v1'):
        ILSceneBackend(scene)
