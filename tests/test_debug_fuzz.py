"""Packaged route fuzzer planning, feedback, and fail-closed boundaries."""
from dataclasses import FrozenInstanceError
from copy import deepcopy

import pytest

from fdisbull.debug_fuzz import plan_campaign, run_campaign


def campaign():
    return {
        'format': 'fdisbull-fuzz-1',
        'base_script': {'format': 'fdisbull-script-1', 'backend': 'wine-ne', 'steps': [
            {'op': 'keyboard.press', 'key': 'n'},
            {'op': 'click', 'x': 10, 'y': 20},
            {'op': 'run', 'timeout_ms': 100, 'expect': 'timeout'},
        ]},
        'mutation_sites': [
            {'index': 0, 'field': 'key', 'choices': ['n', 'r', 'enter', 'space']},
            {'index': 1, 'field': 'x', 'choices': [11, 12, 13]},
        ],
        'seed': 17, 'max_cases': 5, 'timeout_ms': 2500,
    }


def receipt(case, *, status='passed', family=None, reaped=True, adapter='c'):
    return {'status': status, 'script_sha256': case.script_sha256,
            'run_id': f'{case.index + 1:032x}', 'source_sha256': 'a'*64,
            'runtime_sha256': 'b'*64, 'adapter_sha256': adapter*64,
            'completed_steps': len(case.script['steps']) if status=='passed' else 1,
            'stage_ids': ['entry', 'input'], 'fault_family': family,
            'owned_process_reaped': reaped, 'raw_private_error': 'secret game bytes'}


def test_plan_is_deterministic_baseline_first_and_immutable():
    document=campaign()
    first=plan_campaign(document)
    second=plan_campaign(deepcopy(document))
    assert len(first)==5 and first==second
    assert first[0].mutation is None and first[0].script==document['base_script']
    assert len({case.script_sha256 for case in first})==len(first)
    assert all(case.timeout_ms==2500 for case in first)
    assert all(case.mutation is not None for case in first[1:])
    changed=first[0].script;changed['steps'][0]['key']='x'
    assert first[0].script['steps'][0]['key']=='n'
    with pytest.raises(FrozenInstanceError):
        first[0].index=9
    different=deepcopy(document);different['seed']=18
    assert [case.script_sha256 for case in plan_campaign(different)][1:] != [
        case.script_sha256 for case in first][1:]


def test_planner_validates_every_candidate_before_any_runner_call():
    document=campaign()
    document['mutation_sites'][1]['choices']=[11, 5000]
    called=[]
    with pytest.raises(ValueError):
        run_campaign(document,lambda case: called.append(case) or receipt(case))
    assert called==[]


def test_deep_campaign_values_are_refused_before_json_recursion():
    document=campaign()
    nested='x'
    for _ in range(33):
        nested=[nested]
    document['mutation_sites'][0]['choices']=[nested]
    with pytest.raises(ValueError,match='nesting'):
        plan_campaign(document)


@pytest.mark.parametrize('change', [
    lambda d: d['base_script']['steps'].__setitem__(0, {'op':'write-memory','address':'0x0','data_hex':'00'}),
    lambda d: d['base_script']['steps'].__setitem__(0, {'op':'repeat','count':2,'steps':[{'op':'status'}]}),
    lambda d: d['base_script']['steps'][0].__setitem__('key','$prior.key'),
    lambda d: d['mutation_sites'][0].__setitem__('field','op'),
    lambda d: d['mutation_sites'][0].__setitem__('choices',['$prior.key']),
    lambda d: d.__setitem__('seed',True),
    lambda d: d.__setitem__('max_cases',33),
    lambda d: d.__setitem__('mutation_sites',[{'index':0,'field':'key','choices':['n']}]),
    lambda d: d['base_script']['steps'].__setitem__(slice(None),[{'op':'status'}]*65),
])
def test_unsafe_or_unbounded_plan_is_refused(change):
    document=campaign();change(document)
    with pytest.raises(ValueError):
        plan_campaign(document)


def test_runner_retains_sanitized_feedback_and_fault_identity():
    document=campaign();document['max_cases']=3
    calls=[]
    def fresh(case):
        calls.append(case.index)
        if case.index==1:
            return receipt(case,status='failed',family='C0000005:execute:null')
        return receipt(case)
    result=run_campaign(document,fresh)
    assert calls==[0,1,2]
    assert result['format']=='fdisbull-fuzz-result-1'
    assert result['planned_cases']==result['executed_cases']==3
    assert result['stop_reason']=='completed'
    assert result['cases'][0]['failure_kind']=='none'
    assert result['cases'][1]['failure_kind']=='fault'
    assert result['cases'][1]['new_fault_family'] is True
    assert result['cases'][1]['fault_family']=='C0000005:execute:null'
    assert result['corpus_case_indices']==[0,1]
    text=str(result)
    assert 'secret game bytes' not in text and 'raw_private_error' not in text
    assert 'base_script' not in text and 'steps' not in result['cases'][0]
    assert 'mutation_sites' not in text and 'choices' not in text


def test_fault_and_stage_feedback_is_scoped_to_exact_identities():
    document=campaign();document['max_cases']=3
    def fresh(case):
        return receipt(case,status='failed',family='C0000005:execute:null',
                       adapter='c' if case.index!=2 else 'd')
    result=run_campaign(document,fresh)
    assert [case['new_fault_family'] for case in result['cases']]==[True,False,True]
    assert result['cases'][2]['new_stage_edges']==result['cases'][0]['new_stage_edges']


def test_unknown_or_unreaped_case_stops_without_replay():
    document=campaign();called=[]
    def uncertain(case):
        called.append(case.index)
        return receipt(case,status='unknown',reaped=False)
    result=run_campaign(document,uncertain)
    assert called==[0] and result['executed_cases']==1
    assert result['stop_reason']=='cleanup_unverified'
    assert result['cases'][0]['failure_kind']=='unknown'
    assert result['cases'][0]['retained'] is False and result['corpus_case_indices']==[]
    result=run_campaign(document,lambda case:receipt(case,status='unknown',reaped=True))
    assert result['stop_reason']=='outcome_unknown' and result['executed_cases']==1
    assert result['corpus_case_indices']==[]


def test_failed_without_fault_is_not_reported_as_crash_and_bad_receipt_stops():
    document=campaign();document['max_cases']=2
    result=run_campaign(document,lambda case:receipt(case,status='failed'))
    assert all(case['failure_kind']=='nonfault_failure' and not case['new_fault_family']
               for case in result['cases'])
    called=[]
    def malformed(case):
        called.append(case.index)
        value=receipt(case);value['adapter_sha256']='unknown';return value
    with pytest.raises(ValueError,match='SHA-256'):
        run_campaign(document,malformed)
    assert called==[0]


def test_nonfault_failure_after_same_stages_is_a_distinct_terminal_edge():
    document=campaign();document['max_cases']=2
    result=run_campaign(document,lambda case:receipt(
        case,status='passed' if case.index==0 else 'failed'))
    assert result['cases'][0]['stage_ids']==result['cases'][1]['stage_ids']
    assert result['cases'][1]['failure_kind']=='nonfault_failure'
    assert result['cases'][1]['new_fault_family'] is False
    assert result['cases'][1]['new_stage_edges']==1
    assert result['corpus_case_indices']==[0,1]


def test_runner_rejects_stale_or_swapped_script_receipt():
    document=campaign();document['max_cases']=2
    plan=plan_campaign(document)
    called=[]
    def stale(case):
        called.append(case.index)
        result=receipt(case)
        result['script_sha256']=plan[1-case.index].script_sha256
        return result
    with pytest.raises(ValueError,match='planned case'):
        run_campaign(document,stale)
    assert called==[0]


def test_runner_rejects_reused_run_id_across_fresh_cases():
    document=campaign();document['max_cases']=2
    called=[]
    def reused(case):
        called.append(case.index)
        result=receipt(case)
        result['run_id']='1'*32
        return result
    with pytest.raises(ValueError,match='reused a live run ID'):
        run_campaign(document,reused)
    assert called==[0,1]


@pytest.mark.parametrize('bad_run_id', ['short', 'A'*32, '0'*33])
def test_runner_requires_a_bounded_native_run_id(bad_run_id):
    document=campaign();document['max_cases']=1
    def malformed(case):
        result=receipt(case);result['run_id']=bad_run_id;return result
    with pytest.raises(ValueError,match='32-character run ID'):
        run_campaign(document,malformed)
