from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from test_agi_control import loaded, lift
from fdisbull.agi_effects import CONTRACT, object_state
from fdisbull.interaction_il import execute_il


def setup(tmp_path, code, state=None):
    program = loaded(tmp_path, {0: bytes(code)})
    projection = lift(program, state or {}, control_flow='compact', effect_profile='agi-2.917')
    context = {'contract': CONTRACT, 'horizon': 36, 'player_control': True,
               'objects': {'0': object_state(y=40,width=3,height=2,view=2,loop_count=1,cel_count=1)},
               'views': {'2':{'sha256':'b'*64,'loops':[[{'width':3,'height':2}]]}}, 'loaded_views': [2],
               'messages': {program.root.resource_sha256: {'1': 'Test'}}}
    return projection['uil'], context


def ack(req, result):
    return {'request_id': req['request_id'], 'status': 'completed', 'result': result}


def test_draw_suspension_resume_and_negative_controls(tmp_path):
    # draw ego; assign v1=42; return
    doc, ctx = setup(tmp_path, [35, 0, 3, 1, 42, 0], {'$agi_v1': 0})
    saved = deepcopy(ctx); state = {'$agi_v1': 0}; initial = deepcopy(state)
    pending = execute_il(doc, state, effect_context=ctx)
    assert pending['status'] == 'pending_host' and pending['native_execution'] is False
    assert pending['state'] == initial and pending['proposed_state'] == initial
    assert ctx == saved and state == initial and pending['effect_context'] == saved
    req, cp = pending['host_request'], pending['checkpoint']
    assert req['operation'] == 'draw'
    again = execute_il(doc, checkpoint=cp)
    assert again['host_request']['request_id'] == req['request_id'] and again['visited'] == pending['visited']
    for result in ({'request_id': 'bad', 'status': 'completed', 'result': {'x': 1, 'y': 40}},
                   {'request_id': req['request_id'], 'status': 'failed', 'result': {}},
                   ack(req, {'x': 999, 'y': 40})):
        rejected = execute_il(doc, checkpoint=cp, host_result=result)
        assert rejected['status'] == 'refused' and rejected['events'] == []
    tampered = deepcopy(cp); tampered['body_index'] = 0
    assert execute_il(doc, checkpoint=tampered)['status'] == 'refused'
    edited = deepcopy(doc); edited['entry'] += 'bad'
    assert execute_il(edited, checkpoint=cp)['status'] == 'refused'
    done = execute_il(doc, checkpoint=cp, host_result=ack(req, {'x': 1, 'y': 40}))
    assert done['complete'] and done['state']['$agi_v1'] == 42 and done['native_execution'] is False
    assert done['effect_context']['objects']['0']['x'] == 1
    assert len(done['host_completions']) == 1 and ctx == saved


def test_print_modes_and_query_alias(tmp_path):
    # get.posn ego,v1,v1; print message 1; assign v2=9
    for mode in (False, True):
        doc, ctx = setup(tmp_path, [39,0,1,1,101,1,3,2,9,0],
                         {'$agi_v1':0,'$agi_v2':0,'$agi_f15':mode,'$agi_v21':3})
        ctx['objects']['0'].update(x=7,y=11)
        p = execute_il(doc, effect_context=ctx)
        assert p['status'] == 'pending_host' and p['proposed_state']['$agi_v1'] == 11
        assert p['proposed_state']['$agi_v2'] == 0
        req = p['host_request']; assert req['operation'] == 'print'
        result = {'shown': True} if mode else {'dismissed': True}
        done = execute_il(doc, checkpoint=p['checkpoint'], host_result=ack(req, result))
        assert done['complete'] and done['state']['$agi_v2'] == 9
        assert done['state']['$agi_f15'] is False
        assert done['state']['$agi_v21'] == (3 if mode else 0)


def test_preflight_and_budget(tmp_path):
    doc, ctx = setup(tmp_path, [35,0,3,1,42,0], {'$agi_v1':0})
    missing = deepcopy(ctx); missing['objects'] = {}
    assert execute_il(doc, effect_context=missing)['status'] == 'refused'
    p = execute_il(doc, effect_context=ctx, max_steps=2)
    assert p['status']=='pending_host'
    out = execute_il(doc, checkpoint=p['checkpoint'], host_result=ack(p['host_request'], {'x':0,'y':40}), max_steps=2)
    assert out['status']=='refused' and out['state']=={'$agi_v1':0}
    assert out['recovery_required'] and len(out['host_completions'])==1
    assert out['external_effects']=='caller_completion_claims_preserved'
    assert out['last_modeled_effect_context']['objects']['0']['x']==0
    v1 = {'format':'fdisbull-il-1','role':'uil','variables':{},'resources':{},'body':[]}
    assert execute_il(v1, effect_context=ctx)['status'] == 'refused'


def test_bad_nested_ports(tmp_path):
    doc, ctx = setup(tmp_path, [35,0,0])
    malformed = deepcopy(doc)
    b = next(b for c in malformed['continuations'].values() for b in c['body'] if b['op'] == 'effect')
    b['args']['object'] = {'var': []}
    assert execute_il(malformed, effect_context=ctx)['status'] == 'refused'
    nested=deepcopy(doc);c=nested['continuations'][nested['entry']]
    c['body']=[{'id':'nested','op':'if','condition':{'op':'eq','left':1,'right':1},
                'then':c['body'],'else':[]}]
    out=execute_il(nested,effect_context=ctx)
    assert out['status']=='refused' and 'top-level' in out['error']

@pytest.mark.parametrize('instruction', [
    [30,2], [33,0], [35,0], [36,0], [37,0,1,2], [38,0,1,2],
    [39,0,1,2], [41,0,2], [61,0], [65,0], [69,0,1,2],
    [70,0], [71,0], [77,0], [78,0], [79,0,1], [83,0,2,3],
    [84,0], [85,0], [88,0], [89,0], [101,1],
])
def test_all_source_effects_lower_without_opaque(tmp_path, instruction):
    states = {38: {'$agi_v1': 0, '$agi_v2': 0}, 39: {'$agi_v1': 0, '$agi_v2': 0},
              69: {'$agi_v2': 0}, 77: {'$agi_v6': 0}, 78: {'$agi_v6': 0},
              79: {'$agi_v1': 0}, 83: {'$agi_f3': False},
              101: {'$agi_f15': False, '$agi_v21': 0}}
    doc, _ = setup(tmp_path, instruction + [0], states.get(instruction[0], {}))
    ops = [b['op'] for c in doc['continuations'].values() for b in c['body']]
    assert 'effect' in ops and 'opaque' not in ops


def test_model_host_checkpoint_resumes_in_a_fresh_cli_process(tmp_path):
    doc,ctx=setup(tmp_path,[35,0,3,1,9,0],{'$agi_v1':0})
    graph=tmp_path/'graph.json';context=tmp_path/'context.json'
    graph.write_text(json.dumps(doc));context.write_text(json.dumps(ctx))
    root=Path(__file__).resolve().parents[1]
    env=dict(os.environ,PYTHONPATH=str(root/'src'),PYTHONDONTWRITEBYTECODE='1')
    command=[sys.executable,'-B','-S','-m','fdisbull','il-run',str(graph)]
    first=subprocess.run(command+['--effect-context',str(context)],env=env,
                         capture_output=True,text=True,timeout=20)
    assert first.returncode==1,first.stderr
    suspended=json.loads(first.stdout)
    assert suspended['status']=='pending_host' and suspended['state']=={'$agi_v1':0}
    checkpoint=tmp_path/'checkpoint.json';checkpoint.write_text(json.dumps(suspended['checkpoint']))
    completion=tmp_path/'result.json'
    completion.write_text(json.dumps(ack(suspended['host_request'],{'x':1,'y':40})))
    second=subprocess.run(command+['--checkpoint',str(checkpoint),'--host-result',str(completion)],
                          env=env,capture_output=True,text=True,timeout=20)
    assert second.returncode==0,second.stderr
    done=json.loads(second.stdout)
    assert done['complete'] and done['state']=={'$agi_v1':9}
    assert len(done['host_completions'])==1 and done['native_execution'] is False
    assert json.loads(context.read_text())==ctx


@pytest.mark.parametrize('stop',[False,True])
def test_effect_suspension_preserves_callee_stack_and_component_stop(tmp_path,stop):
    _,ctx=setup(tmp_path,[0])
    program=loaded(tmp_path,{0:bytes([22,1,3,1,9,0]),1:bytes([35,0,0])},
                   callee_entries={1:0},stop_points=[(1,2)] if stop else [])
    projection=lift(program,{} if stop else {'$agi_v1':0},control_flow='compact',
                    effect_profile='agi-2.917')
    doc=projection['uil'];pending=execute_il(doc,effect_context=ctx)
    assert pending['status']=='pending_host'
    assert pending['checkpoint']['stack']==([None] if stop else ['agi_0002'])
    done=execute_il(doc,checkpoint=pending['checkpoint'],
                    host_result=ack(pending['host_request'],{'x':1,'y':40}))
    assert done['complete'] and done['state']==({} if stop else {'$agi_v1':9})
    assert done['control']['stop']==('stop' if stop else 'return')
    assert done['control']['call_stack']==([None] if stop else [])


def test_print_zero_is_outside_bound_message_profile(tmp_path):
    with pytest.raises(ValueError,match='one-based'):
        setup(tmp_path,[101,0,0],{'$agi_f15':False,'$agi_v21':0})


def test_inactive_object_binding_is_still_required(tmp_path):
    doc,ctx=setup(tmp_path,bytes.fromhex('ff0701ff0200230100'),{'$agi_f1':False})
    out=execute_il(doc,effect_context=ctx)
    assert out['status']=='refused' and out['visited']==[] and out['events']==[]
    assert 'missing object snapshot' in out['error']


def test_source_variable_coordinates_step_and_controller_outputs(tmp_path):
    code=[38,0,1,2,39,0,3,4,79,0,1,83,0,2,5,0]
    state={'$agi_v1':17,'$agi_v2':83,'$agi_v3':0,'$agi_v4':0,'$agi_f5':True}
    doc,ctx=setup(tmp_path,code,state)
    out=execute_il(doc,effect_context=ctx)
    assert out['complete'] and out['state']['$agi_v3']==17 and out['state']['$agi_v4']==83
    assert out['state']['$agi_f5'] is False
    obj=out['effect_context']['objects']['0']
    assert (obj['x'],obj['y'],obj['prev_x'],obj['prev_y'])==(17,83,17,83)
    assert (obj['step_size'],obj['follow_step'],obj['motion'])==(17,17,'follow')
    assert obj['follow_flag']=='$agi_f5' and obj['follow_count']==255
