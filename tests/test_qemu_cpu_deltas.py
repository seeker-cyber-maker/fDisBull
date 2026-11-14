"""Selected CPU/RAM history with real project artifacts and a fake native seam."""
from copy import deepcopy
import sys
import types
import pytest
from fdisbull.qemu_cpu_deltas import QemuCpuDeltaMixin
from test_qemu_dos_history import project, session


@pytest.fixture
def delta(session,monkeypatch):
    session.__class__=type('DeltaHarness',(QemuCpuDeltaMixin,type(session)),{})
    session._runtime_epoch='run-1:process:1'
    session.selected_ram=bytearray(b'abcd')
    session._artifact=lambda *args:session.project._debug_artifact(session.run_id,*args)
    from fdisbull.qemu_dos_checkpoint import _archive, _json, FORMAT as CHECKPOINT_FORMAT
    def save(name,*,max_bytes=None):
        bundle=dict(format=CHECKPOINT_FORMAT,source_sha256=session.metadata['source_sha256'],
            version_sha256=session.metadata['version_sha256'],version=session.version['id'],
            runtime={'runtime':'authored'})
        data=_archive(b'authored-disk',bundle)
        metadata=dict(format=CHECKPOINT_FORMAT,source_sha256=bundle['source_sha256'],
            version_sha256=bundle['version_sha256'],host_files_restored=False,
            sidecar_sha256=__import__('hashlib').sha256(_json(bundle)).hexdigest())
        return session._artifact(name,'state',data,metadata)
    session.save_state=save
    native=types.ModuleType('fdisbull.qemu_cpu_undo_runtime')
    native.REGISTERS={'eax','rip'}
    def normalize(owner,ranges):
        return [dict(address=hex(int(r['address'],0)),linear=hex(int(r['address'],0)),
                     length=r['length'],spans=[dict(address=int(r['address'],0),length=r['length'])]) for r in ranges]
    def observe(owner,ranges,registers):
        values={'eax':owner.pc,'rip':owner.pc}
        return dict(cpu={k:values[k] for k in registers},ram=[bytes(owner.selected_ram[:r['length']]) for r in ranges],
                    binding={'process':'stable'},register_snapshot={'linear_pc':hex(owner.pc)})
    def prepare(owner,ranges,observed,cpu,ram):
        return dict(cpu=cpu,ram=ram)
    def apply(owner,plan):
        owner.pc=plan['cpu'].get('eax',plan['cpu'].get('rip',owner.pc))
        owner.selected_ram[:len(plan['ram'][0])]=plan['ram'][0]
        return {'observation':{'cpu':dict(plan['cpu']),'ram':list(plan['ram']),
                               'binding':{'process':'stable'}},'ram_transition':{'owned':True}}
    native.normalize_ranges=normalize;native.observe=observe;native.prepare=prepare;native.apply=apply
    monkeypatch.setitem(sys.modules,'fdisbull.qemu_cpu_undo_runtime',native)
    def step(*,timeout_ms):
        session.calls.append(('step',session.pc));session.pc+=1;session.selected_ram[0]+=1
        return dict(outcome='step',timed_out=False,session=dict(state='stopped',stop_reason=dict(kind='step',breakpoint_ids=[])))
    session.step=step
    def load(artifact,*,timeout_ms=60000):
        session.pc=0
        session.selected_ram[:]=b'abcd'
        return {'source_binding_restored':True}
    session.load_state=load
    return session


def begin(delta,**kwargs):
    return delta.cpu_delta_start([dict(address='0x100',length=4)],max_steps=4,max_bytes=1024*1024,**kwargs)


def test_record_rewind_freeze_and_full_anchor_recover(delta):
    initial=begin(delta)
    result=delta.cpu_delta_record(count=2)
    assert result['recorded_count']==2 and delta.pc==2 and bytes(delta.selected_ram)==b'cbcd'
    rewind=delta.cpu_delta_rewind(count=1)
    assert rewind['partial_restored'] and not rewind['execution_allowed'] and not rewind['resume_safe']
    assert delta.pc==1 and bytes(delta.selected_ram)==b'bbcd' and delta.cpu_delta_status()['frozen']
    delta._cpu_delta_before_operation('registers')
    with pytest.raises(ValueError,match='frozen'):
        delta._cpu_delta_before_operation('run')
    with pytest.raises(ValueError,match='frozen'):
        delta._cpu_delta_before_operation('save_state')
    with pytest.raises(ValueError): delta.cpu_delta_record()
    recovered=delta.cpu_delta_recover()
    assert recovered['full_native_anchor_loaded'] and delta.pc==0 and bytes(delta.selected_ram)==b'abcd'
    assert not recovered['history']['frozen'] and not recovered['history']['valid']
    assert initial['anchor']['artifact']==recovered['restore'].get('artifact',initial['anchor']['artifact'])


def test_nonordinary_stop_retains_prefix_without_extra_execution(delta):
    begin(delta); calls=[]
    def stopped(*,timeout_ms):
        calls.append(1)
        return dict(outcome='breakpoint',timed_out=False,session={'state':'stopped','stop_reason':{'kind':'breakpoint','breakpoint_ids':['b']}})
    delta.step=stopped
    result=delta.cpu_delta_record(count=2)
    assert result['outcome']=='interrupted' and result['recorded_count']==0 and len(calls)==1
    assert result['stop']['outcome']=='breakpoint' and not delta.cpu_delta_status()['valid'] and not delta.closed


def test_observed_context_change_stops_without_another_step(delta,monkeypatch):
    begin(delta)
    provider=sys.modules['fdisbull.qemu_cpu_undo_runtime'];old=provider.observe
    def observe(owner,ranges,registers):
        result=old(owner,ranges,registers)
        if owner.pc: result['binding']={'process':'other'}
        return result
    monkeypatch.setattr(provider,'observe',observe)
    result=delta.cpu_delta_record(count=2)
    assert result['outcome']=='context_changed' and result['recorded_count']==0
    assert result['stop']['outcome']=='step' and len([x for x in delta.calls if x[0]=='step'])==1
    assert not delta.closed and not result['history']['valid']


def test_binding_mismatch_invalidates_even_if_context_returns(delta,monkeypatch):
    begin(delta)
    provider=sys.modules['fdisbull.qemu_cpu_undo_runtime'];old=provider.observe
    def changed(owner,ranges,registers):
        result=old(owner,ranges,registers);result['binding']={'process':'other'}
        return result
    monkeypatch.setattr(provider,'observe',changed)
    before=(len(delta.events),len(delta.calls))
    with pytest.raises(ValueError,match='context or ownership'):
        delta.cpu_delta_record()
    assert (len(delta.events),len(delta.calls)) == before and not delta.closed
    assert not delta.cpu_delta_status()['valid']
    monkeypatch.setattr(provider,'observe',old)
    with pytest.raises(ValueError,match='No valid'):
        delta.cpu_delta_record()


def test_later_hook_preflight_refusal_retains_committed_prefix(delta):
    begin(delta);old=delta.step
    def first_step(*,timeout_ms):
        result=old(timeout_ms=timeout_ms)
        delta._qemu_hooks={'next-hook':{'access':'x','runtime_address':delta.pc}}
        return result
    delta.step=first_step
    with pytest.raises(ValueError,match='active hook') as caught:
        delta.cpu_delta_record(count=2)
    receipt=caught.value.result
    assert receipt['outcome']=='preflight_refused' and receipt['requested_count']==2
    assert receipt['recorded_count']==1 and len(receipt['records'])==1
    assert receipt['history']['cursor']==1 and len([x for x in delta.calls if x[0]=='step'])==1
    assert not delta.closed


def test_selected_preimage_and_allow_resume_refuse_before_write(delta):
    begin(delta);delta.cpu_delta_record()
    before=(delta.pc,bytes(delta.selected_ram))
    with pytest.raises(ValueError,match='partial resume'):
        delta.cpu_delta_rewind(policy={'allow_partial_resume':True})
    delta.selected_ram[0]=ord('Z')
    with pytest.raises(ValueError,match='preimage'):
        delta.cpu_delta_rewind()
    assert delta.pc==before[0] and delta.selected_ram[0]==ord('Z') and not delta.closed
    assert not delta.cpu_delta_status()['valid']


def test_preserved_memory_remains_frozen_and_records_provenance(delta):
    begin(delta);delta.cpu_delta_record()
    result=delta.cpu_delta_rewind(policy={'name':'keep-byte','preserve_memory':[dict(address='0x100',length=1)]})
    assert bytes(delta.selected_ram)==b'bbcd' and delta.pc==0
    assert result['history']['frozen'] and not result['execution_allowed']
    row=delta.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',(result['provenance']['artifact'],)).fetchone()
    import json
    proof=json.loads(bytes(row['data']))
    assert proof['preserved']['memory'][0]['range']['address']=='0x100'
    assert proof['native_ram_transition']=={'owned':True} and not proof['devices_restored']


def test_policy_outside_selected_projection_is_refused_before_write(delta):
    begin(delta,registers=['eax']);delta.cpu_delta_record()
    before=(delta.pc,bytes(delta.selected_ram),len(delta.events))
    with pytest.raises(ValueError,match='register'):
        delta.cpu_delta_rewind(policy={'preserve_registers':['rip']})
    with pytest.raises(ValueError,match='fit'):
        delta.cpu_delta_rewind(policy={'preserve_memory':[dict(address='0x104',length=1)]})
    assert (delta.pc,bytes(delta.selected_ram),len(delta.events)) == before
    assert not delta.closed and not delta.cpu_delta_status()['frozen']


def test_unknown_undo_write_closes_with_frozen_state(delta,monkeypatch):
    begin(delta);delta.cpu_delta_record()
    provider=sys.modules['fdisbull.qemu_cpu_undo_runtime']
    def fail(owner,plan):
        owner.selected_ram[0]=ord('z')
        raise TimeoutError('uncertain write')
    monkeypatch.setattr(provider,'apply',fail)
    with pytest.raises(TimeoutError): delta.cpu_delta_rewind()
    assert delta.closed and delta._qemu_cpu_delta_history['frozen']


def test_unknown_step_or_failed_undo_closes_without_replay(delta,monkeypatch):
    begin(delta)
    def timeout(*,timeout_ms): raise TimeoutError('lost stop')
    delta.step=timeout
    with pytest.raises(TimeoutError): delta.cpu_delta_record()
    assert delta.closed and not delta.cpu_delta_status()['valid']


def test_hook_site_preflight_has_no_step_or_intent(delta):
    begin(delta)
    delta._qemu_hooks={'hook':{'access':'x','runtime_address':0}}
    before=len(delta.events)
    with pytest.raises(ValueError,match='active hook'): delta.cpu_delta_record()
    assert len(delta.events)==before and not delta.closed and not any(c[0]=='step' for c in delta.calls)


def test_stale_hook_task_hint_does_not_block_but_real_pending_hook_does(delta):
    begin(delta)
    delta._qemu_hook_pending=None
    delta._qemu_hook_pending_task='old-task-hint'
    assert delta.cpu_delta_record()['recorded_count']==1
    delta._qemu_hook_pending='live-hook'
    before=(len(delta.events),len(delta.calls))
    with pytest.raises(ValueError,match='pending hook'):
        delta.cpu_delta_record()
    assert (len(delta.events),len(delta.calls))==before and not delta.closed


def test_artifact_corruption_refused_before_write(delta):
    begin(delta);rec=delta.cpu_delta_record(); artifact=rec['records'][0]['artifact']
    with delta.project.transaction(True):
        delta.project.db.execute('UPDATE debug_artifacts SET data=? WHERE id=?',(b'bad',artifact))
    before=(delta.pc,bytes(delta.selected_ram))
    with pytest.raises(ValueError,match='corrupt'): delta.cpu_delta_rewind()
    assert (delta.pc,bytes(delta.selected_ram))==before and not delta.closed


def test_budget_refusal_precedes_step_and_intent(delta):
    begin(delta)
    history=delta._qemu_cpu_delta_history
    history['max_bytes']=history['anchor']['size']+history['per_step_reserve']-1
    before=(len(delta.calls),len(delta.events),delta.pc)
    with pytest.raises(ValueError,match='budget'):
        delta.cpu_delta_record()
    assert (len(delta.calls),len(delta.events),delta.pc)==before and not delta.closed


def test_corrupt_anchor_blocks_recovery_without_dispatch(delta):
    begin(delta);delta.cpu_delta_record();delta.cpu_delta_rewind()
    artifact=delta._qemu_cpu_delta_history['anchor']['artifact']
    with delta.project.transaction(True):
        delta.project.db.execute('UPDATE debug_artifacts SET data=? WHERE id=?',(b'bad',artifact))
    before=(delta.pc,bytes(delta.selected_ram))
    with pytest.raises(ValueError,match='corrupt'):
        delta.cpu_delta_recover()
    assert (delta.pc,bytes(delta.selected_ram))==before and delta.cpu_delta_status()['frozen']
