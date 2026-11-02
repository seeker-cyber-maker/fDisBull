"""Execute emitted source without fDisBull to qualify the lowering boundary."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from fdisbull.common_uil import digest, required_capabilities
from fdisbull.uil_catalog import build_catalog
from fdisbull.uil_codegen import compile_program
from fdisbull.uil_runtime import TRACE_LIMITS, execute_program


TARGETS = ('python', 'javascript')


def typ(name):
    return {'type': name}


def var(index):
    return {'var': index}


def const(index):
    return {'const': index}


def op(name, typ_, *args):
    return {'op': name, 'type': typ_, 'args': list(args)}


def function(variables, inputs, outputs, body, constants=(), max_steps=1000):
    return {'variables': variables, 'constants': list(constants), 'inputs': inputs,
            'outputs': outputs, 'body': body, 'max_steps': max_steps}


def documents(functions, values, *, imports=(), resources=(), catalog=None, bindings=(), depth=32):
    program={'format':'fdisbull-common-uil-1','capabilities':[],
             'imports':list(imports),'functions':functions,'entry':0}
    program['capabilities']=sorted(required_capabilities(program))
    presentation={'format':'fdisbull-uil-presentation-1','program_sha256':digest(program),
                  'functions':values,'resources':list(resources)}
    plan={'format':'fdisbull-uil-orchestration-1','program_sha256':digest(program),
          'bindings':list(bindings),'ownership':'copy-in-copy-out','max_call_depth':depth}
    if catalog is None:
        catalog=build_catalog([])
    return program,presentation,catalog,plan


def emitted(tmp_path, docs, target):
    if target == 'javascript' and shutil.which('node') is None:
        pytest.skip('Node is not installed')
    directory=tmp_path/target
    manifest=compile_program(*docs,directory,target=target)
    filename='program.mjs' if target=='javascript' else 'program.py'
    command=[shutil.which('node'),str(directory/filename)] if target=='javascript' else [sys.executable,'-I',str(directory/filename)]
    def run(*requests):
        result=subprocess.run(command,input=''.join(json.dumps(r)+'\n' for r in requests),
                              text=True,capture_output=True,cwd=tmp_path,timeout=20)
        assert result.returncode==0,result.stderr
        assert result.stderr=='',result.stderr
        return [json.loads(line) for line in result.stdout.splitlines()]
    return manifest,run,directory/filename


@pytest.mark.parametrize('target',TARGETS)
def test_real_scalar_functions_and_exact_64bit_protocol(tmp_path,target):
    fn=function([typ('u64'),typ('u64'),typ('i16'),typ('i16'),typ('bool')],
                [0,1,2,3],[0,2,3,4],[
                    {'op':'set','dst':0,'value':op('add','u64',var(0),var(1))},
                    {'op':'set','dst':4,'value':op('parity_even','bool',var(0))},
                    {'op':'set','dst':3,'value':op('mod','i16',var(2),var(3))},
                    {'op':'set','dst':2,'value':op('div','i16',var(2),const(0))},
                    {'op':'return'}],constants=[typ('i16')])
    docs=documents([fn],[{'constants':['3'],'initial':['0','0','0','0',False]}])
    manifest,run,source=emitted(tmp_path,docs,target)
    rows=run({'inputs':['18446744073709551615',2,-7,3]},
             {'inputs':['9007199254740993',0,-32768,-1]})
    assert rows[0]['status']=='complete'
    assert rows[0]['outputs']==[1,-2,-1,False]
    large='9007199254740993' if target=='javascript' else 9007199254740993
    assert rows[1]['outputs']==[large,-10922,0,False]
    assert rows[0]['steps']==5
    assert rows[0]['closure_sha256']==manifest['closure_sha256']
    text=source.read_text()
    assert 'fdisbull-common-uil-1' not in text
    assert 'from fdisbull' not in text
    assert 'def fn0' in text if target=='python' else 'function fn0' in text
    assert manifest['runtime_ast_interpreter'] is False
    assert hashlib.sha256(source.read_bytes()).hexdigest()==manifest['artifacts'][source.name]


@pytest.mark.parametrize('target',TARGETS)
def test_arrays_local_calls_groups_and_copy_shims(tmp_path,target):
    array={'type':'u32-array','length':4}
    child=function([array,typ('u32')],[0],[0],[
        {'op':'while','condition':op('lt','bool',var(1),const(0)),'limit':4,'body':[
            {'op':'store','array':0,'index':var(1),'value':op('mul','u32',{'op':'load','array':0,'index':var(1)},const(1))},
            {'op':'set','dst':1,'value':op('add','u32',var(1),const(2))}]},
        {'op':'return'}],constants=[typ('u32')]*3)
    entry=function([array,array],[0],[0,1],[{'op':'group','semantic_id':'semantic:'+'a'*64,'body':[
        {'op':'call','function':1,'inputs':[var(0)],'outputs':[1]},
        {'op':'store','array':1,'index':const(0),'value':const(1)},
        {'op':'require','condition':op('eq','bool',{'op':'load','array':0,'index':const(0)},const(2))}]},
        {'op':'return'}],constants=[typ('u32')]*3)
    docs=documents([entry,child],[{'constants':['0','99','1'],'initial':[[0]*4,[0]*4]},
                                {'constants':['4','2','1'],'initial':[[0]*4,'0']}])
    _,run,source=emitted(tmp_path,docs,target)
    rows=run({'inputs':[[1,2,3,4]]},{'inputs':[[1,9,8,7]]})
    assert rows[0]['outputs']==[[1,2,3,4],[99,4,6,8]]
    assert rows[1]['outputs']==[[1,9,8,7],[99,18,16,14]]
    assert rows[0]['steps']==19
    text=source.read_text()
    assert 'while True:' in text if target=='python' else 'while (true)' in text


@pytest.mark.parametrize('target',TARGETS)
def test_selected_catalog_invocation_records_actual_language_and_copies(tmp_path,target):
    add=function([typ('u16')]*3,[0,1],[2],[
        {'op':'set','dst':2,'value':op('add','u16',var(0),var(1))}])
    catalog=build_catalog([{'language':'common','function':add,'constants':[],
                           'source':{'label':'authored arithmetic block'}}])
    group=catalog['groups'][0];impl=group['implementations'][0]
    entry=function([typ('u16')]*3,[0,1],[2],[
        {'op':'invoke','block':0,'inputs':[var(0),var(1)],'outputs':[2]}])
    docs=documents([entry],[{'constants':[],'initial':['0']*3}],catalog=catalog,
                   imports=[{'semantic_id':group['semantic_id'],'inputs':[typ('u16')]*2,
                             'outputs':[typ('u16')],'effects':[]}],
                   bindings=[{'import':0,'implementation':impl['id']}])
    manifest,run,_=emitted(tmp_path,docs,target)
    row=run({'inputs':[65535,2]})[0]
    assert row['outputs']==[1]
    assert row['calls']==[{'block':0,'semantic_id':group['semantic_id'],
                          'implementation':impl['id'],'language':impl['language'],
                          'inputs':[65535,2],'outputs':[1],'status':'complete'}]
    assert manifest['selected_implementations'][0]['source']==impl['source']
    assert manifest['shims'][0]['implementation']==impl['id']


@pytest.mark.parametrize('target',TARGETS)
def test_effect_plans_are_pending_and_later_refusal_drops_staged_effects(tmp_path,target):
    fn=function([typ('resource'),typ('u16'),typ('bool')],[2],[1],[
        {'op':'set','dst':1,'value':const(0)},
        {'op':'effect','service':'text.show','inputs':[var(0)]},
        {'op':'require','condition':var(2)}],constants=[typ('u16')])
    docs=documents([fn],[{'constants':['42'],'initial':[0,'7',False]}],
                   resources=[{'kind':'text','text':'Win or lose'}])
    _,run,_=emitted(tmp_path,docs,target)
    pending,refused=run({'inputs':[True]},{'inputs':[False]})
    assert pending['status']=='pending_host'
    assert pending['outputs']==[]
    assert pending['state']==[0,7,True]
    assert pending['proposed_state']==[0,42,True]
    assert pending['events']==[{'service':'text.show','inputs':[0],
                                'resource':{'kind':'text','text':'Win or lose'}}]
    assert refused['status']=='refused'
    assert refused['state']==[0,7,False]
    assert refused['events']==[]
    assert refused['outputs']==[]


@pytest.mark.parametrize('target',TARGETS)
@pytest.mark.parametrize('failure',('divide','shift','bounds','loop','budget','depth'))
def test_bounded_refusal_keeps_original_owned_state(tmp_path,target,failure):
    array={'type':'u16-array','length':2}
    variables=[typ('u16'),typ('u16'),array]
    body=[{'op':'set','dst':0,'value':const(0)}]
    if failure in ('divide','shift'):
        body.append({'op':'set','dst':0,'value':op('div' if failure=='divide' else 'shl','u16',var(0),var(1))})
    elif failure=='bounds':body.append({'op':'store','array':2,'index':var(1),'value':var(0)})
    elif failure in ('loop','budget'):
        body.append({'op':'while','condition':const(1),'limit':2,'body':[]})
    else:body.append({'op':'call','function':1,'inputs':[],'outputs':[]})
    fn=function(variables,[0,1,2],[0],body,constants=[typ('u16'),typ('bool')],max_steps=2 if failure=='budget' else 100)
    functions=[fn];values=[{'constants':['42',True],'initial':['7','0',[1,2]]}]
    if failure=='depth':
        functions.append(function([],[],[],[{'op':'return'}]));values.append({'constants':[],'initial':[]})
    docs=documents(functions,values,depth=1 if failure=='depth' else 32)
    _,run,_=emitted(tmp_path,docs,target)
    operand={'divide':0,'shift':16,'bounds':2}.get(failure,0)
    row=run({'inputs':[9,operand,[3,4]]})[0]
    assert row['status']=='refused'
    assert row['state']==[9,operand,[3,4]]
    assert row['outputs']==[] and row['events']==[]


def test_deterministic_closure_private_output_and_preflight(tmp_path):
    fn=function([typ('u8')],[0],[0],[{'op':'return'}])
    docs=documents([fn],[{'constants':[],'initial':['0']}])
    a=compile_program(*docs,tmp_path/'a')
    b=compile_program(*docs,tmp_path/'b')
    assert a==b
    assert (tmp_path/'a/program.py').read_bytes()==(tmp_path/'b/program.py').read_bytes()
    assert a['closure']['presentation']==docs[1]
    with pytest.raises(ValueError,match='new'):
        compile_program(*docs,tmp_path/'a')
    (tmp_path/'.git').mkdir()
    with pytest.raises(ValueError,match='outside Git'):
        compile_program(*docs,tmp_path/'forbidden')
    assert not (tmp_path/'forbidden').exists()


def test_unknown_binding_and_capability_refuse_before_output(tmp_path):
    fn=function([typ('u8')],[0],[0],[{'op':'return'}])
    docs=list(documents([fn],[{'constants':[],'initial':['0']}]))
    docs[0]=deepcopy(docs[0]);docs[0]['capabilities'].append('unknown.backend@1')
    with pytest.raises(ValueError):compile_program(*docs,tmp_path/'unknown')
    assert not (tmp_path/'unknown').exists()


@pytest.mark.parametrize('target',TARGETS)
@pytest.mark.parametrize('type_name,a,b',[
    ('u8',128,1),('u16',65535,15),('i16',-32768,1),
    ('u64',18446744073709551615,1),('i64',-9223372036854775808,1)])
def test_primitive_operator_family_matches_reference(tmp_path,target,type_name,a,b):
    arithmetic=('add','sub','mul','div','mod','and','or','xor','shl','shr')
    comparisons=('eq','ne','lt','le','gt','ge')
    variables=[typ(type_name)]*(2+len(arithmetic))+[typ('bool')]*(len(comparisons)+2)+[typ(type_name)]
    expressions=[op(name,type_name,var(0),var(1)) for name in arithmetic]
    expressions += [op(name,'bool',var(0),var(1)) for name in comparisons]
    expressions += [op('not','bool',op('eq','bool',var(0),var(1))),op('parity_even','bool',var(0)),
                    op('select',type_name,op('lt','bool',var(0),var(1)),var(0),var(1))]
    fn=function(variables,[0,1],list(range(2,len(variables))),[
        {'op':'set','dst':i+2,'value':expr} for i,expr in enumerate(expressions)])
    initial=['0']*(2+len(arithmetic))+[False]*(len(comparisons)+2)+['0']
    docs=documents([fn],[{'constants':[],'initial':initial}])
    reference=execute_program(docs[0],docs[1],docs[3],docs[2],inputs=[a,b])
    _,run,_=emitted(tmp_path,docs,target)
    transport=[str(x) if abs(x)>9007199254740991 else x for x in (a,b)]
    actual=run({'inputs':transport})[0]
    def exact(value):
        if type(value) is str and value.lstrip('-').isdigit(): return int(value)
        if type(value) is list:return [exact(v) for v in value]
        return value
    assert actual['status']==reference['status']=='complete'
    assert exact(actual['outputs'])==reference['outputs']
    assert actual['steps']==reference['steps']


@pytest.mark.parametrize('target',TARGETS)
def test_imported_large_array_is_copied_across_u16_boundary(tmp_path,target):
    array={'type':'u32-array','length':70000}
    child=function([array],[0],[0],[{'op':'store','array':0,'index':const(0),'value':const(1)}],
                   constants=[typ('u32')]*2)
    catalog=build_catalog([{'language':'common','function':child,'constants':['65536','17'],
                           'source':{'label':'authored paged-size transport fixture'}}])
    group=catalog['groups'][0];impl=group['implementations'][0]
    entry=function([array,array],[0],[0,1],[{'op':'invoke','block':0,'inputs':[var(0)],'outputs':[1]}])
    docs=documents([entry],[{'constants':[],'initial':[[0]*70000,[0]*70000]}],
                   imports=[{'semantic_id':group['semantic_id'],'inputs':[array],'outputs':[array],'effects':[]}],
                   catalog=catalog,bindings=[{'import':0,'implementation':impl['id']}])
    manifest,run,_=emitted(tmp_path,docs,target)
    values=[0]*70000;values[65536]=9;values[69999]=23
    row=run({'inputs':[values]})[0]
    assert row['status']=='complete'
    assert row['outputs'][0]==values
    expected=values.copy();expected[65536]=17
    assert row['outputs'][1]==expected
    def summary(words):
        raw=json.dumps(words,separators=(',',':')).encode('utf-8')
        return {'kind':'array-summary','length':len(words),'sha256':hashlib.sha256(raw).hexdigest()}
    assert row['calls'][0]['inputs']==[summary(values)]
    assert row['calls'][0]['outputs']==[summary(expected)]
    assert manifest['shims'][0]['inputs'][0]['ownership']=='copy'
    assert manifest['shims'][0]['inputs'][0]['type']==array
    assert manifest['diagnostic_limits']==manifest['closure']['diagnostic_limits']==TRACE_LIMITS


@pytest.mark.parametrize('target',TARGETS)
def test_all_media_capabilities_only_return_bound_plans(tmp_path,target):
    services=[('text.show',[const(0)]),('image.show',[const(1)]),
              ('sound.play',[const(2)]),('music.start',[const(3),const(4)]),
              ('music.stop',[const(3)])]
    fn=function([],[],[],[{'op':'effect','service':service,'inputs':args} for service,args in services],
                constants=[typ('resource')]*4+[typ('bool')])
    resources=[{'kind':'text','text':'Outcome'},
               {'kind':'graphic','uri':'file:///absent/image.bin'},
               {'kind':'sound','uri':'file:///absent/sound.bin'},
               {'kind':'music','uri':'file:///absent/music.bin'}]
    docs=documents([fn],[{'constants':[0,1,2,3,True],'initial':[]}],resources=resources)
    _,run,_=emitted(tmp_path,docs,target)
    row=run({'inputs':[]})[0]
    assert row['status']=='pending_host'
    assert row['outputs']==[] and row['state']==row['proposed_state']==[]
    assert [event['service'] for event in row['events']]==[name for name,_ in services]
    assert [event['resource'] for event in row['events']]==resources+[resources[3]]


@pytest.mark.parametrize('target',TARGETS)
def test_failing_selected_block_retains_entered_identity(tmp_path,target):
    child=function([typ('u16')],[0],[0],[{'op':'require','condition':const(0)}],constants=[typ('bool')])
    catalog=build_catalog([{'language':'common','function':child,'constants':[False]}])
    group=catalog['groups'][0];impl=group['implementations'][0]
    entry=function([typ('u16')],[0],[0],[{'op':'invoke','block':0,'inputs':[var(0)],'outputs':[0]}])
    docs=documents([entry],[{'constants':[],'initial':['0']}],catalog=catalog,
                   imports=[{'semantic_id':group['semantic_id'],'inputs':[typ('u16')],
                             'outputs':[typ('u16')],'effects':[]}],
                   bindings=[{'import':0,'implementation':impl['id']}])
    _,run,_=emitted(tmp_path,docs,target)
    row=run({'inputs':[42]})[0]
    assert row['status']=='refused' and row['state']==[42]
    assert row['calls'][0]['implementation']==impl['id']
    assert row['calls'][0]['status']=='refused'
    assert row['calls'][0]['inputs']==[42] and row['calls'][0]['outputs']==[]
    assert row['events']==[]


@pytest.mark.parametrize('target',TARGETS)
def test_emitted_branches_and_explicit_boolean_conversions(tmp_path,target):
    fn=function([typ('u8'),typ('bool'),typ('u8'),typ('bool'),typ('u8')],
                [0,1],[2,3,4],[
        {'op':'if','condition':var(1),
         'then':[{'op':'set','dst':2,'value':op('add','u8',var(0),const(0))}],
         'else':[{'op':'set','dst':2,'value':op('sub','u8',var(0),const(0))}]},
        {'op':'set','dst':3,'value':op('cast','bool',var(2))},
        {'op':'set','dst':4,'value':op('cast','u8',var(1))}],constants=[typ('u8')])
    docs=documents([fn],[{'constants':['1'],'initial':['0',False,'0',False,'0']}])
    _,run,_=emitted(tmp_path,docs,target)
    a,b=run({'inputs':[255,True]},{'inputs':[0,False]})
    assert a['outputs']==[0,False,1]
    assert b['outputs']==[255,True,0]


@pytest.mark.parametrize('target',TARGETS)
def test_select_evaluates_both_value_dependencies(tmp_path,target):
    fn=function([typ('u8')],[0],[0],[{'op':'set','dst':0,'value':op('select','u8',const(0),const(1),
        op('div','u8',const(1),var(0)))}],constants=[typ('bool'),typ('u8')])
    docs=documents([fn],[{'constants':[True,'7'],'initial':['0']}])
    _,run,_=emitted(tmp_path,docs,target)
    refused,complete=run({'inputs':[0]},{'inputs':[2]})
    assert refused['status']=='refused' and refused['state']==[0]
    assert complete['status']=='complete' and complete['outputs']==[7]


def imported_documents(child, constants, entry, initial, entry_constants):
    catalog=build_catalog([{'language':'common','function':child,'constants':constants}])
    group=catalog['groups'][0];impl=group['implementations'][0]
    return documents([entry],[{'constants':entry_constants,'initial':initial}],catalog=catalog,
        imports=[{'semantic_id':group['semantic_id'],
                  'inputs':[child['variables'][i] for i in child['inputs']],
                  'outputs':[child['variables'][i] for i in child['outputs']],'effects':[]}],
        bindings=[{'import':0,'implementation':impl['id']}])


@pytest.mark.parametrize('target',TARGETS)
def test_text_trace_uses_utf8_threshold_without_changing_actual_values(tmp_path,target):
    child=function([typ('text')],[0],[0],[{'op':'return'}])
    entry=function([typ('text')],[0],[0],[{'op':'invoke','block':0,'inputs':[var(0)],'outputs':[0]}])
    docs=imported_documents(child,[],entry,[''],[])
    _,run,_=emitted(tmp_path,docs,target)
    inline='é'*128;large='é'*129
    a,b=run({'inputs':[inline]},{'inputs':[large]})
    assert a['outputs']==[inline] and b['outputs']==[large]
    assert a['calls'][0]['inputs']==a['calls'][0]['outputs']==[inline]
    summary={'kind':'text-summary','bytes':258,'sha256':hashlib.sha256(large.encode('utf-8')).hexdigest()}
    assert b['calls'][0]['inputs']==b['calls'][0]['outputs']==[summary]


@pytest.mark.parametrize('target',TARGETS)
def test_invocation_count_budget_refuses_before_an_extra_block(tmp_path,target):
    child=function([typ('u16')],[0],[0],[{'op':'set','dst':0,'value':op('add','u16',var(0),const(0))}],constants=[typ('u16')])
    entry=function([typ('u16')]*3,[2],[0],[
        {'op':'while','condition':op('lt','bool',var(1),var(2)),'limit':1025,'body':[
            {'op':'invoke','block':0,'inputs':[var(0)],'outputs':[0]},
            {'op':'set','dst':1,'value':op('add','u16',var(1),const(0))}]}],
        constants=[typ('u16')],max_steps=20000)
    docs=imported_documents(child,['1'],entry,['7','0','0'],['1'])
    _,run,_=emitted(tmp_path,docs,target)
    complete,refused=run({'inputs':[1024]},{'inputs':[1025]})
    assert complete['status']=='complete' and complete['outputs']==[1031]
    assert len(complete['calls'])==1024
    assert refused['status']=='refused' and refused['state']==[7,0,1025]
    assert refused['events']==refused['outputs']==[]
    assert len(refused['calls'])==1024
    assert all(call['status']=='complete' for call in refused['calls'])
    assert 'trace budget' in refused['error']


@pytest.mark.parametrize('target',TARGETS)
def test_trace_cell_budget_includes_both_ports_and_refused_output(tmp_path,target):
    # 949 complete calls cost 949*(1+34+34)=65481 cells. Call950's
    # input fits (35 cells), but its 34-cell result does not fit.
    array={'type':'u16-array','length':34}
    child=function([array],[0],[0],[{'op':'store','array':0,'index':const(0),
        'value':op('add','u16',{'op':'load','array':0,'index':const(0)},const(1))}],
        constants=[typ('u16')]*2)
    entry=function([array,typ('u16')],[],[0],[
        {'op':'while','condition':op('lt','bool',var(1),const(0)),'limit':950,'body':[
            {'op':'invoke','block':0,'inputs':[var(0)],'outputs':[0]},
            {'op':'set','dst':1,'value':op('add','u16',var(1),const(1))}]}],
        constants=[typ('u16')]*2,max_steps=20000)
    docs=imported_documents(child,['0','1'],entry,[[0]*34,'0'],['950','1'])
    _,run,_=emitted(tmp_path,docs,target)
    row=run({'inputs':[]})[0]
    assert row['status']=='refused' and row['state']==[[0]*34,0]
    assert row['outputs']==row['events']==[]
    assert len(row['calls'])==950
    assert all(call['status']=='complete' for call in row['calls'][:-1])
    assert row['calls'][-1]['status']=='refused' and row['calls'][-1]['outputs']==[]
    assert row['calls'][-1]['inputs'][0][0]==949
    assert 'trace budget' in row['error']
    assert sum(1+sum(len(v) if type(v) is list else 1 for v in call['inputs']+call['outputs'])
               for call in row['calls'])==65516


def effect_loop_documents(text):
    fn=function([typ('resource'),typ('u16'),typ('u16')],[2],[1],[
        {'op':'while','condition':op('lt','bool',var(1),var(2)),'limit':257,'body':[
            {'op':'effect','service':'text.show','inputs':[var(0)]},
            {'op':'set','dst':1,'value':op('add','u16',var(1),const(0))}]}],
        constants=[typ('u16')],max_steps=10000)
    return documents([fn],[{'constants':['1'],'initial':[0,'0','0']}],
                     resources=[{'kind':'text','text':text}])


@pytest.mark.parametrize('target',TARGETS)
def test_event_count_budget_discards_pure_transaction_and_all_plans(tmp_path,target):
    docs=effect_loop_documents('Small event')
    _,run,_=emitted(tmp_path,docs,target)
    pending,refused=run({'inputs':[256]},{'inputs':[257]})
    assert pending['status']=='pending_host' and len(pending['events'])==256
    assert pending['proposed_state']==[0,256,256]
    assert refused['status']=='refused' and refused['state']==[0,0,257]
    assert refused['events']==refused['outputs']==[]
    assert 'event budget' in refused['error']


@pytest.mark.parametrize('target',TARGETS)
def test_event_bytes_budget_counts_compact_utf8_encoding(tmp_path,target):
    text='é'*131000
    event={'service':'text.show','inputs':[0],'resource':{'kind':'text','text':text}}
    size=len(json.dumps(event,ensure_ascii=False,separators=(',',':')).encode('utf-8'))
    assert 4*size<=1048576<5*size
    docs=effect_loop_documents(text)
    _,run,_=emitted(tmp_path,docs,target)
    pending,refused=run({'inputs':[4]},{'inputs':[5]})
    assert pending['status']=='pending_host' and len(pending['events'])==4
    assert refused['status']=='refused' and refused['state']==[0,0,5]
    assert refused['events']==refused['outputs']==[]
    assert 'event budget' in refused['error']
