"""Authored strategy observations test projection/plans, never original gameplay."""
import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from fdisbull.strategy_z import (WitnessBackend, project_observation, plan_action,
                                screen_catalog, validate_witness)


def witness():
    return dict(format='fdisbull-strategy-witness-1',session='authored-example-session',
        revision=7,complete=True,partial=True,
        views=[dict(scene='map',parameters={'phase':'human'},instance='map:0'),
               dict(scene='city',parameters={'city':'city:7@0','tab':'resources'},instance='city:1')],
        title='City — Example City',description='An authored interface fixture.',
        facts=[dict(label='Food stock',value='10'),dict(label='Production',value='12')],
        controls=[dict(id='next-city',label='next city',aliases=['next'],
            description='Select the next known city in this city view.',
            visible=True,enabled=True,verb='select',intent='city.select',arguments={'direction':'next'}),
            dict(id='production',label='production',aliases=['build'],
            description='Choose production for the selected city.',
            visible=True,enabled=True,verb='change',intent='production.open',arguments={'city':'city:7@0'})])


def request(w, target='next-city', verb='select'):
    return dict(context_token=project_observation(w)['context']['token'],verb=verb,target=target,item=None)


def test_every_family_uses_same_public_contract():
    catalog=screen_catalog()
    assert len(catalog['families'])>=35 and not catalog['native_provider_qualified']
    for family in catalog['families']:
        w=witness()
        w['views']=[dict(scene=family['id'],parameters={k:'authored-value' for k in family['required_parameters']},instance='authored-view')]
        w['controls']=[]
        observation=project_observation(w)
        assert observation['context']['id']==family['id'] and observation['complete']
        assert observation['coverage']['partial'] and not family['runtime_qualified']


def test_city_identity_is_parameter_not_scene_and_old_token_refuses():
    w=witness(); first=project_observation(w)
    for city in range(128):
        new=copy.deepcopy(w); new['views'][-1]['parameters']['city']=f'city:{city}@0'
        observation=project_observation(new)
        assert observation['context']['id']=='city'
        if city!=7:
            assert observation['context']['token']!=first['context']['token']
            with pytest.raises(ValueError,match='stale'):
                plan_action(new,request(w))
    assert plan_action(w,request(w))['arguments']=={'direction':'next'}
    del w['views'][-1]['parameters']['city']
    with pytest.raises(ValueError,match='identity parameters'):
        project_observation(w)


@pytest.mark.parametrize('change', ['session','revision','tab','instance','parent','label','arguments','facts','enabled','generation'])
def test_freshness_binds_full_view_and_visible_controls(change):
    w=witness(); altered=copy.deepcopy(w)
    if change=='session': altered['session']='another-process'
    elif change=='revision': altered['revision']+=1
    elif change=='tab': altered['views'][-1]['parameters']['tab']='happiness'
    elif change=='instance': altered['views'][-1]['instance']='reopened-city'
    elif change=='parent': altered['views'][0]['parameters']['phase']='next-turn'
    elif change=='label': altered['controls'][0]['label']='previous city'
    elif change=='arguments': altered['controls'][0]['arguments']['direction']='previous'
    elif change=='facts': altered['facts'][0]['value']='11'
    elif change=='enabled': altered['controls'][0]['enabled']=False
    elif change=='generation': altered['views'][-1]['parameters']['city']='city:7@1'
    with pytest.raises(ValueError,match='stale'):
        plan_action(altered,request(w))


@pytest.mark.parametrize('visible,enabled', [(False,True),(None,True),(True,False),(True,None)])
def test_unknown_or_disabled_readiness_never_becomes_action(visible,enabled):
    w=witness(); w['controls'][0].update(visible=visible,enabled=enabled)
    obj=[o for o in project_observation(w)['objects'] if o['id']=='next-city']
    assert not obj or not obj[0]['verbs']
    with pytest.raises(ValueError,match='hidden'):
        plan_action(w,request(w))


def test_modal_stack_masks_parent_actions_and_incomplete_reads_refuse():
    w=witness(); w['views'].append(dict(scene='confirmation',parameters={'kind':'rush'},instance='dialog:3'))
    with pytest.raises(ValueError,match='active scene'):
        validate_witness(w)
    w['controls']=[]
    assert project_observation(w)['context']['id']=='confirmation'
    w['complete']=False
    with pytest.raises(ValueError,match='incomplete'):
        plan_action(w,request(w))


def test_no_hidden_objects_or_source_fields_leak():
    w=witness()
    hidden=copy.deepcopy(w['controls'][0]);hidden.update(id='hidden-city',label='Hidden City',visible=False)
    w['controls'].append(hidden)
    raw=json.dumps(project_observation(w))
    assert 'Hidden City' not in raw and 'city.select' not in raw and 'parameters' not in raw
    bad=copy.deepcopy(w);bad['native_memory']='secret'
    with pytest.raises(ValueError,match='unknown'):
        project_observation(bad)


def test_player_can_use_existing_protocol_but_no_native_effect_is_claimed():
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'player'))
    from fdisbull_player.player import Player
    backend=WitnessBackend(witness()); player=Player(backend)
    assert 'City — Example City' in player.execute('look')
    assert '10' in player.execute('look')
    assert 'next known city' in player.execute('examine next city')
    result=player.execute_result('select next city')
    assert result['status']=='incomplete' and result['effects']=='none-confirmed'
    assert len(backend.plans)==1 and backend.plans[0]['native_dispatched'] is False
    assert backend.observe()['context']['id']=='city'


def test_bounded_line_service_uses_same_player_observation(tmp_path):
    path=tmp_path/'witness.json';path.write_text(json.dumps(witness()))
    lines=[{'op':'observe'},{'op':'act','action':request(witness())},[],{'op':'save'}]
    p=subprocess.run([sys.executable,'-m','fdisbull.strategy_z','--witness',str(path)],
        input=''.join(json.dumps(x)+'\n' for x in lines),text=True,capture_output=True,check=True)
    replies=[json.loads(x) for x in p.stdout.splitlines()]
    assert replies[0]['context']['id']=='city'
    assert replies[1]['plan']['native_dispatched'] is False
    assert replies[1]['complete'] is False
    assert replies[2]['status']==replies[3]['status']=='rejected'
