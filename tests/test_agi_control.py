"""Authored AGI graphs, independent mathematical states and call boundaries."""
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from fdisbull.agi_lift import lift_logic
from fdisbull.agi_source import bind_program, load_program
from fdisbull.cli import main, respond
from fdisbull.decoder_modules import analyze_input, builtin_registry, lift_input
from fdisbull.interaction_il import execute_il


def resources(tmp_path, programs):
    directory = bytearray(b'\xff\xff\xff' * (max(programs)+1))
    volume = bytearray()
    for logic,code in sorted(programs.items()):
        directory[3*logic:3*logic+3] = len(volume).to_bytes(3,'big')
        payload = len(code).to_bytes(2,'little') + code + b'\x00\x00\x00'
        volume += b'\x12\x34\x00' + len(payload).to_bytes(2,'little') + payload
    (tmp_path/'LOGDIR').write_bytes(directory)
    (tmp_path/'VOL.0').write_bytes(volume)
    return tmp_path/'LOGDIR'


def loaded(tmp_path, programs, *, root=0, **options):
    log = resources(tmp_path,programs)
    return load_program(log,tmp_path,root,profile='2.917',**options)


def lift(program, state, **options):
    return lift_logic(program.root,callees=program.callees,callee_entries=dict(program.callee_entries),
                      entry_offset=program.entry_offset,stop_offsets=program.stop_offsets,
                      stop_points=program.stop_points,initial_state=state,**options)


def conditional(conditions):
    # True sets v2=10, jumps to return. False sets v2=20, then returns.
    return b'\xff'+conditions+b'\xff\x06\x00'+bytes.fromhex('03020afe030003021400')


def source_trace(projection, execution):
    return [(projection['block_sources'][node]['logic'],projection['block_sources'][node]['offset'])
            for node in execution['visited'] if projection['block_sources'][node]['source_entry']]


def test_branches_and_join_preserve_both_paths_for_all_byte_inputs(tmp_path):
    program=loaded(tmp_path,{0:conditional(bytes([1,1,5]))})
    projection=lift(program,{'$agi_v1':5,'$agi_v2':0})
    assert projection['format']=='fdisbull-agi-state-projection-2'
    for value in range(256):
        result=execute_il(projection['uil'],{'$agi_v1':value,'$agi_v2':0})
        assert result['complete']
        assert result['state']['$agi_v2']==(10 if value==5 else 20)
        assert source_trace(projection,result)==([(0,0),(0,7),(0,10),(0,16)] if value==5
                                                else [(0,0),(0,13),(0,16)])
    assert projection['read_set']==['$agi_v1'] and projection['write_set']==['$agi_v2']


@pytest.mark.parametrize('opcode',[1,2,3,4,5,6])
def test_scalar_comparisons_are_unsigned_and_not_concretized(tmp_path,opcode):
    # Variable forms read v3; constant forms compare against byte 128.
    program=loaded(tmp_path,{0:conditional(bytes([opcode,1,3 if opcode%2==0 else 128]))})
    before={'$agi_v1':0,'$agi_v2':0}
    if opcode%2==0: before['$agi_v3']=128
    projection=lift(program,before)
    for a in (0,1,127,128,129,254,255):
        for b in ((0,128,255) if opcode%2==0 else (128,)):
            state=dict(before,**{'$agi_v1':a})
            if opcode%2==0: state['$agi_v3']=b
            expected=a==b if opcode<3 else a<b if opcode<5 else a>b
            out=execute_il(projection['uil'],state)
            assert out['complete'] and out['state']['$agi_v2']==(10 if expected else 20)


def test_and_or_not_flag_predicates_and_empty_and(tmp_path):
    # (v1==5 OR NOT f7) AND v3>2
    terms=bytes([0xfc,1,1,5,0xfd,7,7,0xfc,5,3,2])
    projection=lift(loaded(tmp_path,{0:conditional(terms)}),
                    {'$agi_v1':0,'$agi_v2':0,'$agi_v3':0,'$agi_f7':False})
    for a in (0,5,255):
        for flag in (False,True):
            for c in (0,2,3,255):
                state={'$agi_v1':a,'$agi_v2':0,'$agi_v3':c,'$agi_f7':flag}
                result=execute_il(projection['uil'],state)
                assert result['state']['$agi_v2']==(10 if ((a==5 or not flag) and c>2) else 20)
    empty=lift(loaded(tmp_path,{0:conditional(b'')}),{'$agi_v2':0})
    assert execute_il(empty['uil'])['state']['$agi_v2']==10


def test_if_false_displacement_is_unsigned_but_goto_is_signed(tmp_path):
    # IF's unsigned 0x8000 skip reaches an authored far return, not a negative PC.
    code=bytes.fromhex('ff010100ff0080')+b'\x00'*32769
    projection=lift(loaded(tmp_path,{0:code}),{'$agi_v1':1})
    result=execute_il(projection['uil'])
    assert result['complete'] and source_trace(projection,result)==[(0,0),(0,32775)]
    # A backward goto is supported when it does not form a cycle.
    projection=lift(loaded(tmp_path,{0:bytes.fromhex('fe0300000000fefaff')}),{})
    result=execute_il(projection['uil'])
    assert result['complete'] and source_trace(projection,result)==[(0,0),(0,6),(0,3)]


def test_direct_call_uses_explicit_scan_entry_and_resumes_caller(tmp_path):
    program=loaded(tmp_path,{0:bytes.fromhex('160103010900'),
                             1:bytes.fromhex('03036303020700')},callee_entries={1:3})
    projection=lift(program,{'$agi_v1':0,'$agi_v2':0})
    result=execute_il(projection['uil'])
    assert result['complete'] and result['state']=={'$agi_v1':9,'$agi_v2':7}
    assert source_trace(projection,result)==[(0,0),(1,3),(1,6),(0,2),(0,5)]
    assert projection['calls']==[{'logic':0,'offset':0,'target_logic':1,'entry_offset':3,'resume_offset':2}]
    assert '$agi_v3' not in projection['uil']['variables']


def test_both_callee_returns_reach_shared_caller_continuation(tmp_path):
    caller=bytes.fromhex('160104030200')  # call1; assignv v3,v2; return
    callee=bytes.fromhex('ff0701ff040003020a0003021400')
    projection=lift(loaded(tmp_path,{0:caller,1:callee},callee_entries={1:0}),
                    {'$agi_f1':False,'$agi_v2':0,'$agi_v3':0})
    for flag in (False,True):
        result=execute_il(projection['uil'],{'$agi_f1':flag,'$agi_v2':0,'$agi_v3':0})
        assert result['complete'] and result['state']['$agi_v3']==(10 if flag else 20)
        assert source_trace(projection,result)[-2:]==[(0,2),(0,5)]


def test_stop_inside_callee_preserves_effects_without_fabricating_return(tmp_path):
    program=loaded(tmp_path,{0:bytes.fromhex('160103016300'),
                             1:bytes.fromhex('030207650100')},
                   callee_entries={1:0},stop_points=[(1,3)])
    projection=lift(program,{'$agi_v2':0})
    result=execute_il(projection['uil'])
    assert result['complete'] and result['state']=={'$agi_v2':7}
    assert '$agi_v1' not in projection['uil']['variables']
    assert source_trace(projection,result)==[(0,0),(1,0),(1,3)]
    assert projection['exits']==[{'logic':1,'offset':3,'kind':'declared-component-stop',
                                 'call_stack':[{'logic':0,'resume_offset':2}],
                                 'caller_continuation':'not_executed'}]
    with pytest.raises(ValueError,match='unsupported'):
        lift(bind_program(program.root,callees=program.callees,callee_entries={1:0}),{'$agi_v2':0})


def test_callee_conditional_stop_does_not_stop_the_returning_arm(tmp_path):
    # True reaches a declared stop before print; false returns to caller.
    caller=bytes.fromhex('160103030900')
    callee=bytes.fromhex('ff0701ff0500030207650100')
    projection=lift(loaded(tmp_path,{0:caller,1:callee},callee_entries={1:0},stop_points=[(1,9)]),
                    {'$agi_f1':False,'$agi_v2':0,'$agi_v3':42})
    yes=execute_il(projection['uil'],{'$agi_f1':True,'$agi_v2':0,'$agi_v3':42})
    no=execute_il(projection['uil'],{'$agi_f1':False,'$agi_v2':0,'$agi_v3':42})
    assert yes['complete'] and no['complete']
    assert yes['state']=={'$agi_f1':True,'$agi_v2':7,'$agi_v3':42}
    assert no['state']=={'$agi_f1':False,'$agi_v2':0,'$agi_v3':9}


@pytest.mark.parametrize('code,message',[
    ('fefdff','cyclic'), ('170100','indirect call.v'),
    ('160100','captured callee'), ('ff0dff000000','unsupported condition'),
    ('feff7f','unresolved branch'), ('ff010101ff0000','unresolved conditional')])
def test_unsupported_or_unbounded_paths_refuse(tmp_path,code,message):
    with pytest.raises(ValueError,match=message):
        lift(loaded(tmp_path,{0:bytes.fromhex(code)}),{})


def test_inactive_unsupported_branch_is_not_pruned_from_initial_state(tmp_path):
    code=bytes.fromhex('ff010101ff010000aa')
    with pytest.raises(ValueError,match='unsupported'):
        lift(loaded(tmp_path,{0:code}),{'$agi_v1':1})


def test_cycle_call_depth_and_source_budgets(tmp_path):
    recursive=loaded(tmp_path,{0:bytes.fromhex('160100'),1:bytes.fromhex('160000')},callee_entries={1:0})
    with pytest.raises(ValueError,match='recursive'):lift(recursive,{})
    chain=loaded(tmp_path,{0:bytes.fromhex('160100'),1:bytes.fromhex('160200'),2:b'\x00'},callee_entries={1:0,2:0})
    with pytest.raises(ValueError,match='call depth'):lift(chain,{},max_call_depth=1)
    with pytest.raises(ValueError,match='instruction budget'):lift(chain,{},max_instructions=2)
    for bad in (0,9,True):
        with pytest.raises(ValueError,match='max_call_depth'):lift(chain,{},max_call_depth=bad)
    # Reused callees can expand greatly even with a small source graph.
    expanded=loaded(tmp_path,{0:b'\x16\x01'*20+b'\x00',1:b'\x16\x02'*20+b'\x00',2:b'\x00'},
                    callee_entries={1:0,2:0})
    with pytest.raises(ValueError,match='path depth budget'):
        lift(expanded,{})


def test_scalar_copy_wrapping_and_saturating_updates(tmp_path):
    code=bytes.fromhex('010102020401030501010603010701020803010e0700')
    projection=lift(loaded(tmp_path,{0:code}),{'$agi_v1':255,'$agi_v2':0,'$agi_v3':99,'$agi_f7':False})
    result=execute_il(projection['uil'])
    assert result['complete']
    # inc255 saturates255; dec0 saturates0; v1 copy99 then +1=100;
    # v3 += v1 ->199; v1 -=2 ->98; v3 -=v1 ->101; togglef7.
    assert result['state']=={'$agi_v1':98,'$agi_v2':0,'$agi_v3':101,'$agi_f7':True}


def test_source_bundle_witness_and_boundary_integrity(tmp_path):
    program=loaded(tmp_path,{0:bytes.fromhex('160100'),1:b'\x00'},callee_entries={1:0})
    with pytest.raises(ValueError,match='entry witness'):
        bind_program(program.root,callees=program.callees)
    with pytest.raises(ValueError,match='snapshot'):
        bind_program(program.root,callees=(replace(program.callees[0],_directory=b''),),callee_entries={1:0})
    with (tmp_path/'VOL.0').open('ab') as stream:
        stream.write(b'unrelated authored trailing bytes')
    other=load_program(tmp_path/'LOGDIR',tmp_path,1,profile='2.917')
    with pytest.raises(ValueError,match='inconsistent volume'):
        bind_program(program.root,callees=(other.root,),callee_entries={1:0})
    with pytest.raises(ValueError,match='duplicate'):
        load_program(tmp_path/'LOGDIR',tmp_path,0,profile='2.917',callee_entries=['1:0','1:0'])
    with pytest.raises(ValueError,match='instruction boundary'):
        lift(loaded(tmp_path,{0:bytes.fromhex('03010100')},stop_offsets=[1]),{'$agi_v1':0})


def test_operand_offsets_cannot_be_claimed_as_root_or_callee_entries(tmp_path):
    resources(tmp_path,{0:bytes.fromhex('160100'),1:bytes.fromhex('03010000')})
    # Operand offset 1 would decode as incrementv0; it is not a candidate
    # boundary from the source entry and cannot become a scan-entry witness.
    with pytest.raises(ValueError,match='instruction boundary'):
        load_program(tmp_path/'LOGDIR',tmp_path,0,profile='2.917',callee_entries={1:1})
    with pytest.raises(ValueError,match='instruction boundary'):
        load_program(tmp_path/'LOGDIR',tmp_path,1,profile='2.917',entry_offset=1)
    program=load_program(tmp_path/'LOGDIR',tmp_path,0,profile='2.917',callee_entries={1:3})
    check=[row for row in program.provenance()['boundary_checks'] if row['logic']==1][0]
    assert check['offset']==3 and not check['runtime_observed']
    assert check['basis']=='candidate-start-from-known-static-edges'


def test_module_cli_and_captured_callee_are_source_bound(tmp_path,capsys):
    loaded(tmp_path,{0:bytes.fromhex('160100'),2:b'\x00',10:b'\x00',1:b'\x00'})
    params={'module':'fdisbull.agi.2.917.subset','path':str(tmp_path/'LOGDIR'),
            'volume_dir':str(tmp_path),'logic':0,'profile':'2.917','callee_entries':{'1':0,'2':0,'10':0}}
    opened=builtin_registry().open(params['module'],params['path'],
                                   **{k:v for k,v in params.items() if k not in ('module','path')})
    before=lift_input(opened,initial_state={})
    assert before['module']['version']=='2'
    assert not analyze_input(opened)['complete']  # generic analysis retains external call uncertainty
    (tmp_path/'VOL.0').unlink()
    assert lift_input(opened,initial_state={})==before
    resources(tmp_path,{0:bytes.fromhex('160100'),1:b'\x00'})
    state=tmp_path/'private-state.json';state.write_text('{}')
    assert main(['module-lift',params['module'],params['path'],'--volume-dir',str(tmp_path),
                 '--logic','0','--profile','2.917','--callee-entry','1:0','--state-file',str(state)])==0
    assert json.loads(capsys.readouterr().out)['result']['calls'][0]['target_logic']==1
    result=respond({'method':'module-lift','params':dict(params,callee_entries={'1':0},initial_state={})})
    assert result['ok'] and result['result']['coverage']=='selected_acyclic_source_component'
    request={'method':'module-lift','params':dict(params,callee_entries={'1':0},initial_state={})}
    completed=subprocess.run([sys.executable,'-B','-S','-m','fdisbull','request',json.dumps(request)],
        env=dict(os.environ,PYTHONPATH=str(Path(__file__).parents[1]/'src'),PYTHONDONTWRITEBYTECODE='1'),
        capture_output=True,text=True,timeout=20)
    assert completed.returncode==0,completed.stderr
    assert json.loads(completed.stdout)['result']['calls'][0]['target_logic']==1
