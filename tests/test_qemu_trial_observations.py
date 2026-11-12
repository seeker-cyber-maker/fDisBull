"""Source-bound native trial comparisons and real artifact verification."""
from copy import deepcopy
import hashlib
import io
import json
import pytest
from PIL import Image
from fdisbull.qemu_trial_observations import (FORMAT,capture_trial,compare_trials)
from test_qemu_dos_history import project,session


def cpu():
    return dict(registers={'rip':'0x10','rax':'0x1','eflags':'0x2'},linear_pc='0x1010',cpu_mode='real',
        address_state=dict(register_context_match=True,machine_vcpus=1,control={'CR0':'0x0'},
            segments={'cs':{'base':'0x1000'}},a20=True,paging=False,code_bits=16,stack_bits=16))


@pytest.fixture
def harness(session,monkeypatch):
    from fdisbull import qemu_cpu_undo_runtime, memory_search_runtime
    session.registers=cpu
    session._runtime_epoch='run:1'
    session.closed=False
    session._process['source_mapping']=dict(live=True,live_ranges=[dict(runtime_address=0x1010,project_address=0x100,length=2)])
    session._process['allocation']={'segment':0x100}
    monkeypatch.setattr('fdisbull.qemu_dos_checkpoint._origin',lambda owner:{})
    monkeypatch.setattr('fdisbull.qemu_dos_checkpoint._verify_process',lambda *args:None)
    def normalize(owner,items):
        return [dict(address='0x100',linear='0x1010',length=i['length'],spans=[dict(address=0x1010,length=i['length'])]) for i in items]
    def capture(owner,address,length,space,task_id,*,view):
        return b'a'*length,dict(mapping_id='a'*64,qemu_memory_view=dict(format='fdisbull-qemu-memory-view-1',
            scope='machine',view='ram',task_identity=None,backings=[{'address':4096,'backing':4096}],native_epoch=9)),dict(pages=[])
    monkeypatch.setattr(qemu_cpu_undo_runtime,'normalize_ranges',normalize)
    monkeypatch.setattr(memory_search_runtime,'_capture',capture)
    session._artifact=lambda *args:session.project._debug_artifact(session.run_id,*args)
    return session


def make_report(harness,steps,results,ok=True):
    records=[dict(index=i,op=s['op'],ok=True,result=r) for i,(s,r) in enumerate(zip(steps,results))]
    encoded=json.dumps(dict(format='fdisbull-script-1',steps=steps),sort_keys=True,separators=(',',':')).encode()
    source=harness._artifact('script.json','script',encoded,{})
    report=dict(ok=ok,error=None,requested_steps=len(steps),completed_steps=len(records),steps=records,
                script_artifact=source['artifact'],script_sha256=source['sha256'])
    artifact=harness._artifact('script-result.json','script-result',json.dumps(report).encode(),{})
    return dict(report,artifact=artifact['artifact'])


def document(harness,steps):
    return dict(version=harness.version['id'],source_sha256=harness.metadata['source_sha256'],
                script=dict(format='fdisbull-script-1',steps=steps),observations=[dict(address='0x100',length=2)])


def screenshot(harness):
    output=io.BytesIO();Image.new('RGB',(2,1),(0,0,0)).save(output,format='PNG')
    data=output.getvalue()
    return harness._artifact('frame.png','screenshot',data,dict(width=2,height=1,source='qemu_display_surface',
        run=harness.run_id,sha256=hashlib.sha256(data).hexdigest(),stopped=True,selected_cpu_unchanged=True))


def trace(harness,*,complete=True,qualified=True):
    event=dict(project_address='0x100',address='0x1010',segmented_address={'segment':'0x100','offset':'0x10'},
        execution_bytes='90',registers={'rip':'0x10'},cpu_mode='real',code_bits=16,task_id=0x100,address_context={'a20':True},
        source_qualification={'qualified':True,'context':'real:0100','source_instruction_sha256':'a'*64},
        observation={'instruction_completed':None})
    if not qualified:
        event['project_address']=None
        event['source_qualification']={'qualified':False,'context':None,'source_instruction_sha256':None}
    doc=dict(events=[event],requested_count=1,complete=complete,window={'closed':complete},
        run={'run':harness.run_id},version=harness.version['id'],capture_epoch=harness._runtime_epoch,
        native_process_capture={'capture_epoch':harness._runtime_epoch},
        mapping={'source_sha256':harness.metadata['source_sha256'],'version_sha256':harness.metadata['version_sha256']})
    return harness._artifact('trace.json','trace',json.dumps(doc).encode(),
        dict(complete=complete,context='dos-process',capture_kind='stopped-boundary-count'))


def test_new_epochs_control_ids_and_artifacts_do_not_change_semantic_equality(harness):
    steps=[dict(op='run'),dict(op='trace'),dict(op='capture-surface')]
    def arm(identifier):
        stop=dict(outcome='breakpoint',timed_out=False,session={'stop_reason':{'kind':'breakpoint','address':'0x1010',
                  'breakpoint_ids':[identifier],'native_reply':'T05'}})
        report=make_report(harness,steps,[stop,trace(harness),screenshot(harness)])
        return capture_trial(harness,document(harness,steps),report,{'breakpoints':{'logical':identifier},'hooks':{}})
    a=arm('bp-a');harness._runtime_epoch='run:2';b=arm('bp-b')
    result=compare_trials(a,b)
    assert result['complete'] and result['observed_difference'] is False
    assert a['provenance']['capture_epoch'] != b['provenance']['capture_epoch']


def test_incomplete_trace_cannot_establish_equality(harness):
    steps=[dict(op='trace')]
    report=make_report(harness,steps,[trace(harness,complete=False)])
    a=capture_trial(harness,document(harness,steps),report,{'breakpoints':{},'hooks':{}})
    assert not a['complete'] and compare_trials(a,deepcopy(a))['observed_difference'] is None


def test_corrupt_screenshot_is_rejected_before_comparison(harness):
    steps=[dict(op='capture-surface')]; shot=screenshot(harness)
    with harness.project.transaction(True):
        harness.project.db.execute('UPDATE debug_artifacts SET data=? WHERE id=?',(b'bad',shot['artifact']))
    with pytest.raises(ValueError,match='artifact bytes'):
        capture_trial(harness,document(harness,steps),make_report(harness,steps,[shot]),{'breakpoints':{},'hooks':{}})


def test_changed_memory_and_semantically_different_view_do_not_collapse(harness):
    steps=[];report=make_report(harness,steps,[])
    a=capture_trial(harness,document(harness,steps),report,{'breakpoints':{},'hooks':{}})
    b=deepcopy(a);b['memory'][0]['hex']='6262';b['memory'][0]['sha256']=hashlib.sha256(b'bb').hexdigest()
    assert compare_trials(a,b)['observed_difference'] is True
    b['memory'][0]['context']['scope']='task-private'
    with pytest.raises(ValueError,match='identity'):
        compare_trials(a,b)


def test_incomplete_or_misaligned_captures_never_compare_equal(harness):
    steps=[];report=make_report(harness,steps,[])
    a=capture_trial(harness,document(harness,steps),report,{'breakpoints':{},'hooks':{}})
    b=deepcopy(a);b['memory']=[]
    with pytest.raises(ValueError,match='count'):compare_trials(a,b)
    b=deepcopy(a);del b['registers']['registers']
    with pytest.raises(ValueError,match='CPU'):compare_trials(a,b)


def test_hook_breakpoint_rebind_and_unknown_hook_are_strict(harness):
    steps=[dict(op='run')]
    def trial(hook,bp):
        # The hook may have been removed by a later script action; only the
        # restored pre-script registry is authoritative for its prior hit.
        harness._qemu_hooks={}
        stop=dict(outcome='hook',timed_out=False,session={'stop_reason':{'kind':'breakpoint',
            'address':'0x1010','breakpoint_ids':[bp],'native_reply':'T05'}},
            hook_hits=[dict(hook=hook,breakpoint_id=bp,hit=1,actions=[])])
        report=make_report(harness,steps,[stop])
        return capture_trial(harness,document(harness,steps),report,{'breakpoints':{},'hooks':{'original':hook},
            'hook_registry':[{'hook':hook,'breakpoint_id':bp}]})
    left=trial('hook-a','bp-a');right=trial('hook-b','bp-b')
    assert compare_trials(left,right)['observed_difference'] is False
    harness._qemu_hooks={}
    stop=dict(outcome='breakpoint',timed_out=False,session={'stop_reason':{'kind':'breakpoint',
        'address':'0x1010','breakpoint_ids':['unknown'],'native_reply':'T05'}})
    with pytest.raises(ValueError,match='untracked breakpoint'):
        capture_trial(harness,document(harness,steps),make_report(harness,steps,[stop]),{'breakpoints':{},'hooks':{}})


def test_missing_event_fields_and_wide_register_values_are_not_silently_equal(harness):
    steps=[dict(op='trace')]
    report=make_report(harness,steps,[trace(harness)])
    trial=capture_trial(harness,document(harness,steps),report,{'breakpoints':{},'hooks':{}})
    malformed=deepcopy(trial);malformed['traces'][0]['events']=[{}]
    with pytest.raises(ValueError,match='boundary'):
        compare_trials(malformed,deepcopy(malformed))
    wide=cpu();wide['registers']['xmm0']=hex((1<<127)+3);wide['registers']['st0']=None
    harness.registers=lambda:deepcopy(wide)
    result=capture_trial(harness,document(harness,[]),make_report(harness,[],[]),{'breakpoints':{},'hooks':{}})
    assert result['registers']['registers']['xmm0']==(1<<127)+3
    assert result['registers']['unavailable_registers']==['st0']


def test_unqualified_source_boundary_is_explicitly_incomplete(harness):
    steps=[dict(op='trace')]
    report=make_report(harness,steps,[trace(harness,complete=False,qualified=False)])
    trial=capture_trial(harness,document(harness,steps),report,{'breakpoints':{},'hooks':{}})
    assert not trial['complete'] and 'trace_incomplete' in trial['incomplete_reasons']
    assert compare_trials(trial,deepcopy(trial))['observed_difference'] is None


def test_unqualified_cpu_and_tampered_report_refused(harness):
    bad=cpu();bad['address_state']['a20']=None;harness.registers=lambda:deepcopy(bad)
    with pytest.raises(ValueError,match='context'):
        capture_trial(harness,document(harness,[]),make_report(harness,[],[]),{'breakpoints':{},'hooks':{}})
    harness.registers=cpu
    report=make_report(harness,[],[]);report['ok']=False
    with pytest.raises(ValueError,match='differs from its artifact'):
        capture_trial(harness,document(harness,[]),report,{'breakpoints':{},'hooks':{}})


def test_unrecognized_observation_operation_cannot_be_silently_ignored(harness):
    steps=[dict(op='clock-observe')]
    with pytest.raises(ValueError,match='unsupported observation'):
        capture_trial(harness,document(harness,steps),make_report(harness,steps,[{}]),{'breakpoints':{},'hooks':{}})


def test_trace_epoch_and_source_are_verified_before_normalization(harness):
    steps=[dict(op='trace')]
    old=trace(harness);harness._runtime_epoch='new-epoch'
    with pytest.raises(ValueError,match='trace completeness'):
        capture_trial(harness,document(harness,steps),make_report(harness,steps,[old]),{'breakpoints':{},'hooks':{}})


def test_equal_pixels_with_different_png_encoding_are_still_byte_different(harness):
    steps=[dict(op='capture-surface')]
    def shot(level):
        output=io.BytesIO();Image.new('RGB',(16,16),(0,0,0)).save(output,format='PNG',compress_level=level)
        data=output.getvalue()
        return harness._artifact('frame.png','screenshot',data,dict(width=16,height=16,
            source='qemu_display_surface',run=harness.run_id,sha256=hashlib.sha256(data).hexdigest(),
            stopped=True,selected_cpu_unchanged=True))
    a=capture_trial(harness,document(harness,steps),make_report(harness,steps,[shot(0)]),{'breakpoints':{},'hooks':{}})
    b=capture_trial(harness,document(harness,steps),make_report(harness,steps,[shot(9)]),{'breakpoints':{},'hooks':{}})
    assert a['screenshots'][0]['pixel_sha256']==b['screenshots'][0]['pixel_sha256']
    assert compare_trials(a,b)['observed_difference'] is True


def test_trace_difference_reports_first_boundary_without_full_event_bodies(harness):
    steps=[dict(op='trace')]
    original=capture_trial(harness,document(harness,steps),make_report(harness,steps,[trace(harness)]),
                           {'breakpoints':{},'hooks':{}})
    a=deepcopy(original);b=deepcopy(original)
    for trial in (a,b):
        event=trial['traces'][0]['events'][0]
        trial['traces'][0]['events']=[deepcopy(event) for _ in range(3)]
        trial['traces'][0]['requested_count']=3
    b['traces'][0]['events'][1]['execution_bytes']='91'
    result=compare_trials(a,b)
    assert result['observed_difference'] and len(result['traces'])==1
    difference=result['traces'][0]
    assert difference['first_observed_difference']['index']==1
    assert difference['first_observed_difference']['fields']==['execution_bytes']
    assert difference['baseline_count']==difference['layer_count']==3 and not difference['count_differs']
    assert 'events' not in difference and 'baseline' not in difference and 'layer' not in difference
