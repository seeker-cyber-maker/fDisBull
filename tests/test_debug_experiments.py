"""Saved experiments restore their controls, not merely their guest RAM."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from fdisbull.project import Project
from fdisbull.debug_experiments import validate_observations, compare_trials
from test_dos_loader import mz_file
from native_fixture import prepare_native_fixture


def test_observations_are_bounded_and_explicit():
    assert validate_observations([{'address':'0x10020','length':2}]) == [{'address':'0x10020','length':2}]
    for value in ({}, [{'address':'0x10020','length':0}], [{'address':'0x10020','length':True}],
                  [{'address':'0x10020','length':2,'expression':'eval()'}]):
        with pytest.raises(ValueError):
            validate_observations(value)


def test_incomplete_trials_cannot_be_reported_as_equal():
    trial={'ok':False,'registers':{},'memory':[],'traces':[],'screenshots':[]}
    result=compare_trials(trial,trial)
    assert result['complete'] is False and result['observed_difference'] is None


@pytest.mark.parametrize('field,item',[
    ('memory',{'project_address':'0x10020','hex':'00'}),
    ('traces',{'step':1,'artifact':'trace-a','events':[],'semantics':'before-fetch'}),
    ('screenshots',{'step':1,'artifact':'frame-a','sha256':'abc'}),
    ('observations',{'step':1,'op':'registers','value':{}}),
])
@pytest.mark.parametrize('side',['baseline','layer'])
def test_mismatched_capture_counts_fail_closed(field,item,side):
    from copy import deepcopy
    trial={'ok':True,'registers':{},'memory':[],'traces':[],'screenshots':[],'observations':[]}
    pair={'baseline':deepcopy(trial),'layer':deepcopy(trial)}
    pair[side][field].append(item)
    with pytest.raises(ValueError,match='capture alignment'):
        compare_trials(pair['baseline'],pair['layer'])


@pytest.mark.parametrize('field,first,second',[
    ('memory',{'project_address':'0x10020','hex':'00'},{'project_address':'0x10021','hex':'00'}),
    ('memory',{'project_address':'0x10020','hex':'00'},{'project_address':'0x10020','hex':'0000'}),
    ('screenshots',{'step':1,'artifact':'a','sha256':'x'},{'step':2,'artifact':'b','sha256':'x'}),
    ('traces',{'step':1,'artifact':'a','events':[],'semantics':'fetch'},{'step':1,'artifact':'b','events':[],'semantics':'completed'}),
    ('observations',{'step':1,'op':'run','value':{}},{'step':1,'op':'registers','value':{}}),
])
def test_capture_identity_mismatch_is_not_equality(field,first,second):
    trial={'ok':True,'registers':{},'memory':[],'traces':[],'screenshots':[],'observations':[]}
    with pytest.raises(ValueError,match='capture alignment'):
        compare_trials({**trial,field:[first]},{**trial,field:[second]})


def test_experiment_listing_is_available_through_the_offline_cli(tmp_path):
    binary=tmp_path/'LIST.EXE';binary.write_bytes(mz_file(b'\xeb\xfe'+bytes(510)))
    path=tmp_path/'list.fdb'
    with Project.create(path,binary):
        pass
    result=subprocess.run([sys.executable,'-m','fdisbull','debug-experiments',str(path)],
                          text=True,capture_output=True,check=True)
    assert json.loads(result.stdout)['result']['experiments']==[]


def test_dos_trace_lookahead_is_not_mistaken_for_executed_bytes():
    from fdisbull.debug_experiments import _trace_event
    first={'address':{'offset':'0x0','segment':'0x1000'},'execution_bytes':'90b81111','ram_bytes':'90b81111'}
    second={**first,'execution_bytes':'90b82222'}
    assert _trace_event(first)==_trace_event(second)


def test_stop_comparison_ignores_rearmed_native_ids_but_keeps_writer_identity():
    from fdisbull.debug_experiments import _stop_value
    run={'outcome':'breakpoint','session':{'stop_reason':{'kind':'breakpoint','breakpoint_id':'bp-1',
         'data_access':{'project_instruction':'0x12345'}}}}
    second={'outcome':'breakpoint','session':{'stop_reason':{'kind':'breakpoint','breakpoint_id':'bp-99',
            'data_access':{'project_instruction':'0x12345'}}}}
    assert _stop_value(run)==_stop_value(second)
    second['session']['stop_reason']['data_access']['project_instruction']='0x12346'
    assert _stop_value(run)!=_stop_value(second)


@pytest.fixture
def experiment_backend():
    path=os.environ.get('FDISBULL_DOSBOX')
    if not path:
        pytest.skip('Set FDISBULL_DOSBOX to the layers backend')
    return str(Path(path).resolve(strict=True))


@pytest.mark.parametrize('ram_baseline',[False,True])
def test_real_experiment_restart_controls_layers_and_offline_exports(tmp_path,experiment_backend,ram_baseline):
    # DS=CS; AX=1111; store AX; increment and repeat the store.
    binary=tmp_path/'TRIAL.EXE'
    binary.write_bytes(mz_file(bytes.fromhex('0e1fb81111a3200040ebfa')+bytes(501),ss=0,sp=0x200))
    path=tmp_path/'trial.fdb'
    with Project.create(path,binary) as p:
        p.analyze(max_instructions=32)
        layer=p.debug_layer('alternate immediate',kind='execute',patches=[
            {'address':'1000:0003','expected_hex':'1111','data_hex':'2222'}])['layer']
        baseline=[]
        if ram_baseline:
            baseline=[p.debug_layer('RAM baseline',kind='ram',patches=[
                {'address':'1000:0003','expected_hex':'1111','data_hex':'3333'}])['layer']]
        with p.debugger(experiment_backend,binary.parent) as d:
            prepare_native_fixture(d)
            d.layers(baseline)
            bp=d.breakpoint('0x10008')
            watch=d.breakpoint('0x10020',access='w',length=2)
            cx=d.registers()['general']['ecx']
            hook=d.hook('0x10002',actions=[{'op':'registers','registers':{'ecx':{'expected':cx,'value':cx}}}])
            ids=[bp['breakpoint_id']]+[x['breakpoint_id'] for x in watch['breakpoints']]
            route={'format':'fdisbull-script-1','steps':[
                {'op':'run','timeout_ms':3000},
                {'op':'memory','address':'0x10020','length':2},
                *[{'op':'delete-breakpoint','breakpoint_id':f'$controls.breakpoints.{i}.breakpoint_id'} for i in ids],
                {'op':'trace','count':4,'timeout_ms':3000},
                {'op':'run','guest_ms':80,'fast_forward':True,'timeout_ms':3000},
                {'op':'screenshot','grid':True,'grid_step':8},
            ]}
            saved=d.save_experiment('store experiment',script=route,observations=[{'address':'0x10020','length':2}])
            assert d.run(timeout_ms=3000)['hook_hits'][0]['hook']==hook['hook']
            assert d.hooks()['hooks']==[]  # consumed once-hook
            d.delete_breakpoint(bp['breakpoint_id'])
    with Project(path) as p:
        assert p.debug_experiments()['experiments'][0]['id']==saved['artifact']
        info=p.debug_experiment_info(saved['artifact'])
        assert len(info['controls']['breakpoints'])==3 and info['controls']['hooks'][0]['hits']==0
        assert info['controls']['breakpoints'][0]['params']['cs']=='0x1000'
        assert info['controls']['hooks'][0]['params']['cs']=='0x1000'
        with p.debugger(experiment_backend,binary.parent) as d:
            result=d.compare_experiment(saved['artifact'],layers=baseline+[layer],timeout_ms=10000)
            assert result['ok'], result
            assert result['comparison']['observed_difference'] is True
            observed=[s for s in result['comparison']['steps'] if s['op']=='memory'][0]
            assert observed['baseline']['hex']==('3333' if ram_baseline else '1111')
            assert observed['layer']['hex']=='2222'
            assert result['comparison']['traces'][0]['first_observed_difference']['index']==0
            assert len(d.controls()['breakpoints'])==3
            assert len(d.hooks()['hooks'])==1 and d.hooks()['hooks'][0]['hits']==0
            assert d.layers()['active']==baseline
            assert d.memory('1000:0003',length=2)['hex']==('3333' if ram_baseline else '1111')
            assert p.disassembly('1000:0002',lines=1)['instructions'][0]['bytes']=='b81111'
            report=result['artifact']
            image=result['baseline']['screenshots'][0]['artifact']
    with Project(path) as p:
        p.debug_export(report,tmp_path/'comparison.json')
        p.debug_export(image,tmp_path/'frame.png')
        assert json.loads((tmp_path/'comparison.json').read_text())['ok']
        assert (tmp_path/'frame.png').read_bytes().startswith(b'\x89PNG')


def test_real_failed_trial_restores_nonzero_hook_count_and_deleted_breakpoint(tmp_path,experiment_backend):
    binary=tmp_path/'FAIL.EXE'
    binary.write_bytes(mz_file(bytes.fromhex('0e1fb81111a3200040ebfa')+bytes(501),ss=0,sp=0x200))
    with Project.create(tmp_path/'fail.fdb',binary) as p, p.debugger(experiment_backend,binary.parent) as d:
        p.analyze(max_instructions=32)
        bp=d.breakpoint('1000:0008')
        cx=d.registers()['general']['ecx']
        hook=d.hook('1000:0002',once=False,max_hits=3,
                    actions=[{'op':'registers','registers':{'ecx':{'expected':cx,'value':cx}}}])
        assert len(d.run(timeout_ms=3000)['hook_hits'])==1
        assert d.hooks()['hooks'][0]['hits']==1
        script={'format':'fdisbull-script-1','steps':[
            {'op':'delete-breakpoint','breakpoint_id':f"$controls.breakpoints.{bp['breakpoint_id']}.breakpoint_id"},
            {'op':'assert','value':1,'equals':2}]}
        saved=d.save_experiment('intentional failure',script=script)
        d.delete_hook(hook['hook'])
        result=d.compare_experiment(saved['artifact'],layers=[])
        assert result['ok'] is False and result['baseline_restored'] is True
        assert result['layer'] is None and result['comparison'] is None
        assert result['error']['type']=='ScriptFailure'
        assert len(d.controls()['breakpoints'])==1
        assert d.hooks()['hooks'][0]['hits']==1
        before=d.controls()
        with pytest.raises(ValueError,match='Unknown code layer'):
            d.compare_experiment(saved['artifact'],layers=['missing-layer'])
        assert d.controls()==before
        with p.transaction(True):
            p.db.execute('UPDATE debug_artifacts SET data=? WHERE id=?',(b'changed',saved['artifact']))
        with pytest.raises(ValueError,match='experiment hash mismatch'):
            d.restore_experiment(saved['artifact'])
        assert d.controls()==before and not d.closed


def test_real_capture_refuses_partial_hooks_and_untracked_native_breakpoints(tmp_path,experiment_backend):
    binary=tmp_path/'GUARD.EXE';binary.write_bytes(mz_file(b'\xeb\xfe'+bytes(510),ss=0,sp=0x200))
    with Project.create(tmp_path/'guard.fdb',binary) as p, p.debugger(experiment_backend,binary.parent) as d:
        script={'format':'fdisbull-script-1','steps':[{'op':'registers'}]}
        hook=d.hook('0x10020',access='w',length=2,actions=[{'op':'layers','layers':[]}])
        d.delete_breakpoint(hook['breakpoints'][0])
        with pytest.raises(ValueError,match='Partially deleted hook'):
            d.save_experiment('partial hook',script=script)
        d.delete_hook(hook['hook'])
        native=d.call('breakpoints.create',{'kind':'execution','once':False,
                     'address':{'space':'segmented','segment':f'0x{d.runtime_load:04X}','offset':'0x00000000'}})
        with pytest.raises(ValueError,match='Untracked'):
            d.save_experiment('untracked native control',script=script)
        assert p.debug_experiments()['experiments']==[]
        d.call('breakpoints.delete',{'breakpoint_id':native['breakpoint_id']})
