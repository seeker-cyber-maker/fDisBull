"""Behavior checks for a bounded debugger-operation feedback campaign."""
import json
import hashlib
import os
from pathlib import Path

import pytest

from windows_sequence_campaign import WIN16_CASES, fault_family, observe, retain_campaign, run_bounded, select_corpus
from test_win16_native import qualify_win16_snake

FULL, ENTRY, BOOTSTRAP = WIN16_CASES


def fault(*,pc='ne:2:0xa56d',raw='0xa4a97d',access='0x0',target='0xffffffffffffffff'):
    return {'stop': {'project_address':pc,'raw_address':raw},
            'registers': {'cs':'0x2f7','ss':'0x2ff'},
            'stack_descriptor': {'type':19,'default_big':False},
            'native_contexts': {'pending_event': {'exception': {
                'code':0xC0000005,'parameter_count':2,'parameters':[access,target]}}}}


def receipt(case,stages,*,status='failed'):
    return {'source_sha256':'a'*64,'status':status,'debug_probes':case.debug_probes,
            'trace_farcall':case.trace_farcall,'gpr_probe':case.gpr_probe,
            'gpr_probe_kind':'paired-integer-edit-restore' if case.gpr_probe else None,
            'adapter_sha256':'b'*64,'runtime_inputs':{'initramfs':{'sha256':'c'*64}},
            'checks':[{'stage':stage} for stage in stages],
            'first_unknown_av':{'file':'first-unknown-av.json'} if status=='failed' else None,
            'owned_process_reaped':True}


def passed_stages(case):
    stages=['actual-original-ne-entry',
            'actual-ne-checked-register-edit-restored-before-continuation']
    if case.trace_farcall:
        stages.append('actual-ne-memory-execution-breakpoint-step-trace')
    elif case.debug_probes:
        stages.append('controlled-entry-jmp-step-and-breakpoint-without-far-call-trace')
    stages.extend(('physical-ne-key-produced-observed-body-pixel',
                   'actual-ne-ordinary-r-reset',
                   'actual-ne-named-scene-replayed-physical-transition',
                   'actual-ne-dot-mode-retained-frame-http-no-host-input'))
    return stages


def test_fault_family_uses_access_kind_and_source_location_instead_of_code_and_pc_only():
    a=fault();b=fault(raw='0xb4a97d');c=fault(access='0x8',target='0x0');d=fault(pc=None,raw='0x0')
    assert fault_family(a)==fault_family(b)  # relocation does not split one source failure
    assert fault_family(a)!=fault_family(c)  # read vs execute AV is material
    assert fault_family(a)!=fault_family(d)  # source location vs unmapped null PC


def test_shortest_declared_failure_case_keeps_completed_prefix_and_new_stage_feedback():
    full=observe(FULL,receipt(FULL,['actual-original-ne-entry','step','fault']),fault())
    minimal=observe(BOOTSTRAP,receipt(BOOTSTRAP,['actual-original-ne-entry','fault']),fault(raw='0xb4a97d'))
    different=observe(BOOTSTRAP,receipt(BOOTSTRAP,['entry','fault']),fault(access='0x8',target='0x0'))
    result=select_corpus([full,minimal,different])
    assert [row['case'] for row in result['novel_cases']]==['full-debugger','bootstrap-only','bootstrap-only']
    assert len(result['shortest_declared_failure_cases'])==2
    selected=result['shortest_declared_failure_cases'][0]
    assert selected['case']=='bootstrap-only'
    assert selected['declared_operations']==list(BOOTSTRAP.operations)
    assert selected['completed_operations']==['bootstrap']
    assert len(selected['completed_operations'])<len(selected['declared_operations'])
    assert result['shortest_declared_failure_cases'][1]['fault_family']!=selected['fault_family']


def test_candidate_identity_scopes_stage_and_fault_novelty():
    case=BOOTSTRAP
    initial=receipt(case,['actual-original-ne-entry','fault'])
    changed=receipt(case,['actual-original-ne-entry','fault'])
    changed['adapter_sha256']='d'*64
    observations=[observe(case,initial,fault()),observe(case,changed,fault())]
    result=select_corpus(observations)
    assert [row['new_fault_family'] for row in result['novel_cases']]==[True,True]
    assert all(row['new_stage_edges']==3 for row in result['novel_cases'])
    assert len(result['shortest_declared_failure_cases'])==2
    assert {row['adapter_sha256'] for row in result['shortest_declared_failure_cases']}=={'b'*64,'d'*64}


def test_invalid_or_unidentified_native_receipt_never_becomes_feedback():
    case=BOOTSTRAP
    with pytest.raises(ValueError,match='identified'):
        observe(case,{'status':'failed','checks':[]},fault())
    invalid=receipt(case,['entry']);invalid['source_sha256']='unknown'
    with pytest.raises(ValueError,match='source, runtime and adapter identities'):
        observe(case,invalid,fault())
    wrong=receipt(case,['entry']);wrong['debug_probes']=True
    with pytest.raises(ValueError,match='flags differ'):
        observe(case,wrong,fault())
    with pytest.raises(ValueError,match='authoritative'):
        observe(case,receipt(case,['entry']),None)


def test_completed_operation_feedback_tracks_observed_stages_only():
    case=BOOTSTRAP
    stages=['actual-original-ne-entry','actual-ne-checked-register-edit-restored-before-continuation',
            'physical-ne-key-produced-observed-body-pixel']
    result=observe(case,receipt(case,stages,status='passed'))
    assert result['completed_operations']==['bootstrap','register-edit-restore','physical-n']
    assert result['operations']==list(case.operations)
    assert len(result['completed_operations'])<len(result['operations'])


def test_campaign_summary_uses_fresh_private_file_and_does_not_embed_fault_dump(tmp_path):
    case=BOOTSTRAP;observation=observe(case,receipt(case,['entry','fault']),fault())
    path=tmp_path/'campaign.json'
    identity=retain_campaign(path,[observation])
    text=path.read_text();result=json.loads(text)
    assert identity['cases']==1 and identity['fault_families']==1
    assert result['shortest_declared_failure_cases'][0]['case']==case.name
    assert result['shortest_declared_failure_cases'][0]['completed_operations']==[]
    assert 'native_contexts' not in text and 'stack_descriptor' not in text
    with pytest.raises(ValueError,match='fresh file'):
        retain_campaign(path,[observation])


def test_bounded_runner_never_replays_or_continues_after_uncertain_guest_cleanup():
    called=[]
    def fresh(case):
        called.append(case.name)
        result=receipt(case,['entry','fault'])
        if len(called)==2:result['owned_process_reaped']=False
        return result,fault()
    observations,feedback=run_bounded(WIN16_CASES,fresh,max_cases=3)
    assert called==['full-debugger','entry-step']
    assert len(observations)==2 and observations[-1]['original_reaped'] is False
    assert feedback['schema']=='fdisbull-windows-sequence-campaign-2'
    with pytest.raises(ValueError,match='one to three'):
        run_bounded(WIN16_CASES,fresh,max_cases=4)


def test_adaptive_campaign_starts_with_full_route_and_stops_after_its_pass():
    assert [case.name for case in WIN16_CASES]==['full-debugger','entry-step','bootstrap-only']
    called=[]
    def fresh(case):
        called.append(case.name)
        return receipt(case,passed_stages(case),status='passed'),None
    observations,feedback=run_bounded(WIN16_CASES,fresh,max_cases=3)
    assert called==['full-debugger']
    assert len(observations)==1 and observations[0]['status']=='passed'
    assert feedback['shortest_declared_failure_cases']==[]


def test_adaptive_campaign_refuses_a_partial_first_case_pass():
    called=[]
    def fresh(case):
        called.append(case.name)
        return receipt(case,['actual-original-ne-entry'],status='passed'),None
    with pytest.raises(ValueError,match='Passed case lacks observed operation milestones'):
        run_bounded(WIN16_CASES,fresh,max_cases=3)
    assert called==['full-debugger']


def test_adaptive_campaign_isolates_terminal_full_failure_with_two_fresh_cases():
    called=[]
    def fresh(case):
        called.append(case.name)
        if case is FULL:
            return receipt(case,['actual-original-ne-entry']),fault()
        return receipt(case,passed_stages(case),status='passed'),None
    observations,feedback=run_bounded(WIN16_CASES,fresh,max_cases=3)
    assert called==['full-debugger','entry-step','bootstrap-only']
    assert [item['status'] for item in observations]==['failed','passed','passed']
    assert [item['case'] for item in feedback['shortest_declared_failure_cases']]==['full-debugger']


def test_adaptive_campaign_refuses_a_partial_narrow_case_pass():
    called=[]
    def fresh(case):
        called.append(case.name)
        if case is FULL:
            return receipt(case,['actual-original-ne-entry']),fault()
        return receipt(case,['actual-original-ne-entry'],status='passed'),None
    with pytest.raises(ValueError,match='Passed case lacks observed operation milestones'):
        run_bounded(WIN16_CASES,fresh,max_cases=3)
    assert called==['full-debugger','entry-step']


def test_real_win16_bounded_operation_campaign():
    """Opt-in fresh native cases through the ordinary NE GUI qualification."""
    names=('FDISBULL_NE_QEMU','FDISBULL_NE_KERNEL','FDISBULL_NE_INITRAMFS',
           'FDISBULL_NE_SNAKE_EXE','FDISBULL_NE_SNAKE_INITIAL','FDISBULL_NE_CAMPAIGN_OUTPUT')
    missing=[name for name in names if not os.environ.get(name)]
    if missing:
        if os.environ.get('FDISBULL_REQUIRE_NE_CAMPAIGN')=='1':
            pytest.fail('Missing real Win16 operation campaign inputs: '+', '.join(missing))
        pytest.skip('Requires explicit native inputs and an external campaign output directory')
    output=Path(os.environ['FDISBULL_NE_CAMPAIGN_OUTPUT']).resolve(strict=True)
    if not output.is_dir() or any(output.iterdir()):
        raise ValueError('Native campaign requires a fresh empty external output directory')
    count=int(os.environ.get('FDISBULL_NE_CAMPAIGN_CASES','3'))
    def fresh(case):
        case_output=output/case.name
        try:
            receipt=qualify_win16_snake(case_output,qemu=os.environ['FDISBULL_NE_QEMU'],
                kernel=os.environ['FDISBULL_NE_KERNEL'],runtime=os.environ['FDISBULL_NE_INITRAMFS'],
                fixture=os.environ['FDISBULL_NE_SNAKE_EXE'],initial=os.environ['FDISBULL_NE_SNAKE_INITIAL'],
                debug_probes=case.debug_probes,trace_farcall=case.trace_farcall,gpr_probe=case.gpr_probe)
        except Exception:
            path=case_output/'qualification.json'
            if not path.is_file():raise
            receipt=json.loads(path.read_text())
        ref=receipt.get('first_unknown_av')
        fault=None
        if ref:
            path=case_output/ref['file']
            data=path.read_bytes()
            if hashlib.sha256(data).hexdigest()!=ref['sha256']:
                raise ValueError('Native first-fault receipt changed during campaign')
            fault=json.loads(data)
        return receipt,fault
    observations,feedback=run_bounded(WIN16_CASES,fresh,max_cases=count)
    retained=retain_campaign(output/'summary.json',observations)
    assert retained['cases']==len(observations)
    assert feedback['schema']=='fdisbull-windows-sequence-campaign-2'
    assert all(item['original_reaped'] for item in observations),'Campaign stopped after uncertain guest cleanup'
