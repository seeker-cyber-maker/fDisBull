"""Contract-level observations, independent of any source language or target."""
from copy import deepcopy
import json

import pytest

from fdisbull.common_uil import (FORMAT, digest, validate_program,
    validate_presentation, fold_function, expand_fold, load_json)
from fdisbull.uil_runtime import execute_program, prepare_execution, finish_execution


def fixture(typ='u16', value='1'):
    fn = {'variables':[{'type':typ}], 'constants':[{'type':typ}],
          'inputs':[0], 'outputs':[0], 'max_steps':10,
          'body':[{'op':'set','dst':0,'value':{'op':'add','type':typ,
                   'args':[{'var':0},{'const':0}]}}]}
    program = {'format':FORMAT,'capabilities':['core.scalar@1'],
               'imports':[],'functions':[fn],'entry':0}
    presentation = {'format':'fdisbull-uil-presentation-1','program_sha256':digest(program),
                    'functions':[{'constants':[value],'initial':['0']}],'resources':[]}
    return program,presentation


def rebind(p, b):
    b['program_sha256'] = digest(p)


def test_slot_indices_types_constants_and_realization_identity():
    p,b = fixture()
    assert validate_program(p) and validate_presentation(p,b)
    a = execute_program(p,b,inputs=[65535])
    assert a['outputs'] == [0] and a['state'] == [0]
    changed = deepcopy(b); changed['functions'][0]['constants'][0]='2'
    c = execute_program(p,changed,inputs=[65535])
    assert c['outputs'] == [1]
    assert a['program_sha256'] == c['program_sha256']
    assert a['presentation_sha256'] != c['presentation_sha256']
    assert p['functions'][0]['variables'] == [{'type':'u16'}]


@pytest.mark.parametrize('port', ['inputs', 'outputs'])
def test_unused_import_array_signature_still_requires_array_capability(port):
    p, _ = fixture()
    p['capabilities'].append('core.calls@1')
    spec = {'semantic_id': 'semantic:' + '0' * 64,
            'inputs': [], 'outputs': [], 'effects': []}
    spec[port] = [{'type': 'u32-array', 'length': 1}]
    p['imports'] = [spec]
    with pytest.raises(ValueError, match='capabilit'):
        validate_program(p)
    p['capabilities'].append('core.array@1')
    assert validate_program(p)


@pytest.mark.parametrize('change', [
    lambda p:p['functions'][0]['body'][0].update(dst=-1),
    lambda p:p['functions'][0]['body'][0].update(dst=True),
    lambda p:p['functions'][0]['body'][0]['value']['args'][0].update(var=1),
    lambda p:p['functions'][0]['body'][0]['value']['args'][1].update(const=1),
    lambda p:p['functions'][0]['variables'][0].update(name='host_address'),
    lambda p:p['functions'][0]['constants'][0].update(value='1'),
    lambda p:p['capabilities'].append('unknown.execution@1'),
    lambda p:p['functions'][0]['body'].append({'op':'x86.exec','bytes':'90'}),
])
def test_bad_or_named_core_slots_and_unknowns_refuse(change):
    p,_ = fixture(); change(p)
    with pytest.raises(ValueError): validate_program(p)


@pytest.mark.parametrize('literal', [1, '01', '+1', '-0', '65536'])
def test_presentation_does_not_silently_narrow_or_change_numeric_spelling(literal):
    p,b=fixture(); b['functions'][0]['constants'][0]=literal
    with pytest.raises(ValueError): validate_presentation(p,b)


def test_wide_integer_decimal_roundtrip_and_no_float_substitution():
    p,b=fixture('u64','18446744073709551615')
    result=execute_program(p,json.loads(json.dumps(b)),inputs=[2])
    assert result['outputs']==[1]
    b['functions'][0]['constants'][0]=1.0
    with pytest.raises(ValueError):validate_presentation(p,b)


def test_recoverable_fold_is_exact_owned_and_budget_transparent():
    p,b=fixture(); before=deepcopy(p)
    folded=fold_function(p,0,'semantic:'+'a'*64)
    assert p==before
    assert expand_fold(folded['program'],folded['recovery'])==before
    fb=deepcopy(b);rebind(folded['program'],fb)
    assert execute_program(folded['program'],fb,inputs=[65535])['outputs']==[0]
    assert execute_program(folded['program'],fb,inputs=[65535])['steps']==execute_program(p,b,inputs=[65535])['steps']
    altered=deepcopy(folded['program']);altered['functions'][0]['body'][0]['body'].append({'op':'return'})
    with pytest.raises(ValueError,match='stale'):expand_fold(altered,folded['recovery'])
    bad=deepcopy(folded['recovery']);bad['original']['body']=[]
    with pytest.raises(ValueError,match='corrupt'):expand_fold(folded['program'],bad)


def test_arrays_aliases_eager_select_and_faults_leave_input_owned():
    p,b=fixture('u32')
    f=p['functions'][0]
    f['variables']=[{'type':'u32-array','length':2},{'type':'u32'}]
    f['inputs']=[0];f['outputs']=[0]
    f['body']=[{'op':'store','array':0,'index':{'const':0},'value':{'const':0}},
               {'op':'set','dst':1,'value':{'op':'div','type':'u32','args':[{'const':0},{'const':1}]}}]
    f['constants']=[{'type':'u32'},{'type':'u32'}]
    p['capabilities'].append('core.array@1')
    b['functions']=[{'constants':['1','0'],'initial':[[0,0],'0']}];rebind(p,b)
    source=[9,8];result=execute_program(p,b,inputs=[source])
    assert result['status']=='refused' and result['state'][0]==source==[9,8]
    assert result['events']==[]
    # Select is eager: an out-of-bounds unselected expression still refuses.
    f['constants'].append({'type':'bool'}); b['functions'][0]['constants'].append(True)
    f['body'][-1]['value']={'op':'select','type':'u32','args':[{'const':2},{'const':0},
                           {'op':'load','array':0,'index':{'op':'add','type':'u32','args':[{'const':0},{'const':0}]}}]}
    rebind(p,b)
    assert execute_program(p,b,inputs=[source])['status']=='refused'


def test_local_functions_have_explicit_frames_and_copy_shims():
    p,b=fixture();child=deepcopy(p['functions'][0]);p['functions'].append(child)
    p['functions'][0]['body']=[{'op':'call','function':1,'inputs':[{'var':0}],'outputs':[0]}]
    p['capabilities'].append('core.calls@1');b['functions'].append(deepcopy(b['functions'][0]));rebind(p,b)
    assert execute_program(p,b,inputs=[4])['outputs']==[5]
    p['functions'][1]['body']=[{'op':'call','function':0,'inputs':[{'var':0}],'outputs':[0]}]
    with pytest.raises(ValueError,match='recursive'):validate_program(p)


def test_media_requests_are_pending_and_bound_outside_uil():
    p,b=fixture();f=p['functions'][0]
    f['constants'] += [{'type':'resource'},{'type':'bool'}]
    f['body'] += [{'op':'effect','service':'music.start','inputs':[{'const':1},{'const':2}]}]
    p['capabilities'].append('host.effects@1');b['functions'][0]['constants'] += [0,True]
    b['resources']=[{'kind':'music','uri':'local:music/intro.mp3'}];rebind(p,b)
    r=execute_program(p,b,inputs=[4])
    assert r['status']=='pending_host' and r['outputs']==[]
    assert r['state']==[4] and r['proposed_state']==[5]
    assert r['events']==[{'service':'music.start','inputs':[0,True],
                         'resource':{'kind':'music','uri':'local:music/intro.mp3'}}]
    b['resources'][0]['kind']='sound'
    with pytest.raises(ValueError,match='resource kind'):
        execute_program(p,b,inputs=[4])


def test_guarded_ticket_is_single_use_and_context_change_cannot_commit():
    p,b=fixture();context={k:0 for k in ('session','generation','revision','selection_epoch','provider_epoch')}
    plan={'format':'fdisbull-uil-orchestration-1','program_sha256':digest(p),'bindings':[],
          'ownership':'copy-in-copy-out','max_call_depth':32,'context':context}
    catalog={'format':'fdisbull-uil-catalog-1','groups':[],'rejected':[]}
    t=prepare_execution(p,b,plan,catalog,inputs=[4])
    context['selection_epoch']=1
    assert finish_execution(t,context)['status']=='refused'
    with pytest.raises(ValueError,match='consumed'):finish_execution(t,context)
    plan['context']=context
    t=prepare_execution(p,b,plan,catalog,inputs=[4]);r=finish_execution(t,context)
    assert r['outputs']==[5]
    r['outputs'][0]=99
    with pytest.raises(ValueError):finish_execution(t,context)
    t=prepare_execution(p,b,plan,catalog,inputs=[4])
    invalid=deepcopy(context);invalid['revision']=False
    with pytest.raises(ValueError,match='epochs'):finish_execution(t,invalid)


def test_duplicate_json_keys_and_unselected_bad_calls_are_rejected(tmp_path):
    bad=tmp_path/'bad.json';bad.write_text('{"entry":0,"entry":1}')
    with pytest.raises(ValueError,match='duplicate'):load_json(bad)
    p,b=fixture();p['functions'][0]['body'].append({'op':'if','condition':{'op':'eq','type':'bool',
        'args':[{'var':0},{'const':0}]},'then':[],
        'else':[{'op':'call','function':99,'inputs':[],'outputs':[]}]})
    p['capabilities'].append('core.calls@1')
    with pytest.raises(ValueError):validate_program(p)


def test_selected_resource_constants_are_preflighted_in_an_untaken_call():
    from fdisbull.uil_catalog import build_catalog
    from fdisbull.common_uil import validate_realization
    fn={'variables':[],'constants':[{'type':'resource'}],'inputs':[],'outputs':[],
        'max_steps':10,'body':[{'op':'effect','service':'sound.play','inputs':[{'const':0}]}]}
    catalog=build_catalog([{'language':'common','function':fn,'constants':[1]}])
    group=catalog['groups'][0];impl=group['implementations'][0]
    p,b=fixture()
    p['imports']=[{'semantic_id':group['semantic_id'],'inputs':[],'outputs':[],'effects':['sound.play']}]
    p['capabilities'] += ['core.calls@1','host.effects@1']
    b['resources']=[{'kind':'sound','uri':'local:one.wav'}];rebind(p,b)
    plan={'format':'fdisbull-uil-orchestration-1','program_sha256':digest(p),
          'bindings':[{'import':0,'implementation':impl['id']}],
          'ownership':'copy-in-copy-out','max_call_depth':32}
    with pytest.raises(ValueError,match='resource'):
        validate_realization(p,b,catalog,plan)


def test_unimplemented_native_layout_is_not_silently_treated_as_metadata():
    p,b=fixture();b['layout']={'profile':'native-pointer-map','address':'0x1234'}
    with pytest.raises(ValueError):validate_presentation(p,b)
