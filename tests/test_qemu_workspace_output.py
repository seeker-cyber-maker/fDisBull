"""Host-only admission and failure contracts for attested workspace output."""
from copy import deepcopy
import pytest

from test_qemu_workspace import session
from test_qemu_workspace_edits import prepared_host


@pytest.mark.parametrize('destination',[None,1,b'/private/output.dat','relative.dat','/bad\0name'])
def test_invalid_output_destination_refuses_before_native_observation(session,tmp_path,monkeypatch,destination):
    from fdisbull import qemu_workspace_output as output
    debug,_=prepared_host(session,tmp_path)
    def unexpected(*args):
        raise AssertionError('Invalid destination reached native observation')
    monkeypatch.setattr(output,'_boundary',unexpected)
    with pytest.raises(ValueError,match='absolute new host destination'):
        debug.workspace_save_output('SAVE.DAT',destination,closed_and_flushed=True)


@pytest.mark.parametrize('attestation', [False, None, 1, 'true'])
def test_literal_attestation_refuses_before_checkpoint_or_export(session,tmp_path,monkeypatch,attestation):
    debug,root=prepared_host(session,tmp_path)
    calls=[]
    monkeypatch.setattr(debug,'workspace_seal',lambda **kwargs:calls.append('seal'))
    before=deepcopy(debug._dos_workspace)
    destination=tmp_path/'output.dat'
    with pytest.raises((ValueError,TypeError)):
        debug.workspace_save_output('SAVE.DAT',destination,closed_and_flushed=attestation)
    assert not calls and not destination.exists()
    assert debug._dos_workspace==before


def test_missing_attestation_refuses_before_seal(session,tmp_path,monkeypatch):
    debug,root=prepared_host(session,tmp_path)
    calls=[]
    monkeypatch.setattr(debug,'workspace_seal',lambda **kwargs:calls.append('seal'))
    with pytest.raises(ValueError,match='attestation'):
        debug.workspace_save_output('SAVE.DAT',tmp_path/'output.dat')
    assert not calls and not (tmp_path/'output.dat').exists()


def _qualified(debug):
    from fdisbull import qemu_workspace_output as output
    runtime=dict(format=output.RUNTIME_FORMAT,version=output.VERSION,files={
        'system.img':dict(sha256=output.QUALIFIED_IMAGE_SHA256),
        'source/kernel.zip':dict(sha256=output.LOCK['kernel']),
        'source/freecom.zip':dict(sha256=output.LOCK['freecom'])})
    debug._workspace_runtime_component=runtime
    state=debug._dos_workspace
    state['runtime_descriptor']=deepcopy(runtime)
    state['runtime_component_sha256']=output._sha(output._json(runtime))
    debug._process={'state':'active'};debug._ready=dict(list_of_lists_segment=0x100,
        list_of_lists_offset=0x20,child_psp=0x300)
    debug._nonce=bytes(range(16));debug._runtime_epoch='epoch-1'
    debug.layers=lambda:dict(active=[])
    debug.registers=lambda:dict(registers={'rip':'0x100'},instruction_pointer='0x100',
        linear_pc='0x1100',cpu_mode='real',address_state=dict(paging=False,
        register_context_match=True,machine_vcpus=1,code_bits=16,a20=True,control=dict(CR0='0x0')))
    return debug


def test_physical_reader_rejects_outside_low_ram_and_selects_physical(session):
    from fdisbull import qemu_workspace_output as output
    calls=[]
    class Remote:
        def memory(self,address,length,*,space,timeout_ms):
            calls.append((address,length,space,timeout_ms));return b'X'*length
    session.vm.debugger=lambda:Remote()
    session._history_remaining_ms=lambda:123
    assert output._read_physical(session,0x9ffff,1)==b'X'
    assert calls==[(0x9ffff,1,'physical',123)]
    for address,length in [(0x9ffff,2),(0xa0000,1),(-1,1),(0,0),(True,1),(0,True)]:
        with pytest.raises(ValueError): output._read_physical(session,address,length)
    assert len(calls)==1


def test_physical_reader_rejects_short_reply(session):
    from fdisbull import qemu_workspace_output as output
    class Remote:
        def memory(self,*a,**kw): return b''
    session.vm.debugger=lambda:Remote();session._history_remaining_ms=lambda:100
    with pytest.raises(ValueError,match='incomplete'):output._read_physical(session,0,1)


@pytest.mark.parametrize('change',['image','source_package','descriptor','source','version'])
def test_runtime_identity_mismatch_refused(session,tmp_path,change):
    from fdisbull import qemu_workspace_output as output
    debug,_=prepared_host(session,tmp_path);_qualified(debug)
    if change=='image': debug._workspace_runtime_component['files']['system.img']['sha256']='0'*64
    elif change=='source_package':debug._workspace_runtime_component['files']['source/kernel.zip']['sha256']='0'*64
    elif change=='descriptor':debug._dos_workspace['runtime_component_sha256']='0'*64
    elif change=='source':debug._dos_workspace['source_sha256']='0'*64
    else:debug._dos_workspace['version']=-1
    with pytest.raises(ValueError,match='runtime|workspace'):
        output._admit_runtime(debug)


@pytest.mark.parametrize('change',['protected','paging','cpus','context','layer','task','sync','pending','held'])
def test_context_refuses_unsafe_execution_and_input(session,tmp_path,change):
    from fdisbull import qemu_workspace_output as output
    debug,_=prepared_host(session,tmp_path);_qualified(debug)
    initial=debug.registers()
    if change=='protected':initial['address_state']['control']['CR0']='0x1'
    elif change=='paging':initial['address_state']['paging']=True
    elif change=='cpus':initial['address_state']['machine_vcpus']=2
    elif change=='context':initial['address_state']['register_context_match']=False
    elif change=='layer':debug.layers=lambda:dict(active=['layer'])
    elif change=='task':debug._dos_task_views={'other':{}}
    elif change=='sync':debug.vm._clock_sync={}
    elif change=='pending':debug.vm._physical_input=dict(pending=['edge'],leases={},valid=True)
    elif change=='held':debug.vm._physical_input=dict(pending=[],leases={'a':1},valid=True)
    debug.registers=lambda:deepcopy(initial)
    with pytest.raises(ValueError):output._context(debug)


@pytest.mark.parametrize('epoch',[None,'',42])
def test_context_requires_runtime_epoch(session,tmp_path,epoch):
    from fdisbull import qemu_workspace_output as output
    debug,_=prepared_host(session,tmp_path);_qualified(debug)
    debug._runtime_epoch=epoch
    with pytest.raises(ValueError,match='epoch'):output._context(debug)


@pytest.mark.parametrize('open_count,dirty_count',[(1,0),(0,1),(1,1)])
def test_boundary_refuses_any_global_open_or_dirty(session,monkeypatch,open_count,dirty_count):
    from fdisbull import qemu_workspace_output as output
    monkeypatch.setattr(output,'_context',lambda owner:dict(process=dict(
        list_of_lists_segment=1,list_of_lists_offset=2,child_psp=3)))
    monkeypatch.setattr(output,'observe_guest_files',lambda *a:dict(
        ordinary_open_count=open_count,dirty_buffer_count=dirty_count))
    with pytest.raises(ValueError,match='open|dirty'):output._boundary(session)


def test_boundary_rejects_cpu_change_during_double_observation(session,monkeypatch):
    from fdisbull import qemu_workspace_output as output
    values=iter([dict(process=dict(list_of_lists_segment=1,list_of_lists_offset=2,child_psp=3),pc=1),
                 dict(process=dict(list_of_lists_segment=1,list_of_lists_offset=2,child_psp=3),pc=2)])
    monkeypatch.setattr(output,'_context',lambda owner:next(values))
    monkeypatch.setattr(output,'observe_guest_files',lambda *a:dict(ordinary_open_count=0,dirty_buffer_count=0))
    with pytest.raises(ValueError,match='changed'):output._boundary(session)


def _orchestration(session,tmp_path,monkeypatch):
    from fdisbull import qemu_workspace_output as output
    from fdisbull.dos_file_layers import WorkspaceStore
    debug,root=prepared_host(session,tmp_path);_qualified(debug)
    store=WorkspaceStore(debug);base=debug._dos_workspace['generation']['artifact']
    entry=store.create_file(base,'SAVE.DAT',b'guest-content')
    generation=entry['artifact']
    saved=debug._artifact('snapshot.qcow2','state',b'checkpoint',{})
    monkeypatch.setattr(output,'_seal_workspace',lambda owner:dict(checkpoint=saved['artifact'],
        workspace=dict(generation=dict(artifact=generation))))
    boundary=dict(context=dict(pc='same',epoch='epoch-1'),files=dict(ordinary_open_count=0,dirty_buffer_count=0))
    monkeypatch.setattr(output,'_boundary',lambda owner:deepcopy(boundary))
    return debug,root,output,boundary,saved,generation


def test_success_returns_attestation_and_exact_export(session,tmp_path,monkeypatch):
    debug,root,output,boundary,saved,generation=_orchestration(session,tmp_path,monkeypatch)
    target=tmp_path/'out.bin'
    result=output.save_output(debug,'D:\\SAVE.DAT',target,closed_and_flushed=True)
    assert target.read_bytes()==b'guest-content'
    assert result['provenance']=='caller-attested' and result['guest_create_provenance'] is False
    assert result['file_state_before']==result['file_state_after']==boundary['files']
    assert result['checkpoint']['artifact']==saved['artifact'] and result['generation']['artifact']==generation
    assert result['export']['durable'] and result['artifact']


@pytest.mark.parametrize('changed',['pc','epoch','files'])
def test_postseal_change_prevents_publication(session,tmp_path,monkeypatch,changed):
    debug,root,output,boundary,saved,generation=_orchestration(session,tmp_path,monkeypatch)
    altered=deepcopy(boundary)
    if changed=='files':altered['files']['dirty_buffer_count']=1
    else:altered['context'][changed]='different'
    sequence=iter([boundary,altered]);monkeypatch.setattr(output,'_boundary',lambda owner:next(sequence))
    target=tmp_path/'out.bin'
    with pytest.raises(ValueError,match='changed') as error:
        output.save_output(debug,'SAVE.DAT',target,closed_and_flushed=True)
    assert not target.exists() and debug.closed
    assert error.value.result['checkpoint']==saved['artifact']
    assert error.value.result['export_published'] is False


def test_output_receipt_failure_exposes_durable_effect_without_replay(session,tmp_path,monkeypatch):
    debug,root,output,boundary,saved,generation=_orchestration(session,tmp_path,monkeypatch)
    original=debug._artifact
    def failing(name,kind,*args,**kwargs):
        if kind==output.KIND:raise OSError('receipt persistence failed')
        return original(name,kind,*args,**kwargs)
    debug._artifact=failing
    target=tmp_path/'out.bin'
    with pytest.raises(OSError) as error:output.save_output(debug,'SAVE.DAT',target,closed_and_flushed=True)
    assert target.read_bytes()==b'guest-content' and debug.closed
    assert error.value.result['export']['durable'] and error.value.result['receipt_persisted'] is False
    assert error.value.result['publication']=='do not replay'


@pytest.mark.parametrize('path', ['MISSING.DAT','GAME.COM'])
def test_postseal_path_refusal_identifies_checkpoint_without_export(session,tmp_path,monkeypatch,path):
    debug,root,output,boundary,saved,generation=_orchestration(session,tmp_path,monkeypatch)
    # GAME.COM is protected already at admission; exercise a path that becomes
    # protected in the sealed generation by adding it after the current check.
    if path=='GAME.COM':
        monkeypatch.setattr(output,'_select_output',lambda *a: (_ for _ in ()).throw(ValueError('protected')))
        path='LATER.DAT'
    target=tmp_path/'out.bin'
    with pytest.raises(ValueError) as error:
        output.save_output(debug,path,target,closed_and_flushed=True)
    assert not target.exists()
    assert error.value.result['checkpoint']==saved['artifact']
    assert error.value.result['export_published'] is False
    assert error.value.result['receipt_persisted'] is False


def test_postseal_observer_error_reports_checkpoint_without_export(session,tmp_path,monkeypatch):
    debug,root,output,boundary,saved,generation=_orchestration(session,tmp_path,monkeypatch)
    calls=[]
    def observe(owner):
        calls.append(None)
        if len(calls)==2: raise ValueError('observer failed')
        return boundary
    monkeypatch.setattr(output,'_boundary',observe)
    target=tmp_path/'out.bin'
    with pytest.raises(ValueError) as error:
        output.save_output(debug,'SAVE.DAT',target,closed_and_flushed=True)
    assert not target.exists() and debug.closed
    assert error.value.result['checkpoint']==saved['artifact']
    assert error.value.result['export_published'] is False
    assert error.value.result['receipt_persisted'] is False


def test_generation_receipt_failure_reports_checkpoint_without_export(session,tmp_path,monkeypatch):
    debug,root,output,boundary,saved,generation=_orchestration(session,tmp_path,monkeypatch)
    def fail_receipt(*args):
        raise OSError('generation receipt unavailable')
    monkeypatch.setattr(output,'_generation_receipt',fail_receipt)
    target=tmp_path/'out.bin'
    with pytest.raises(OSError,match='generation receipt unavailable') as error:
        output.save_output(debug,'SAVE.DAT',target,closed_and_flushed=True)
    assert not target.exists()
    assert error.value.result['checkpoint']==saved['artifact']
    assert error.value.result['generation']['artifact']==generation
    assert error.value.result['export_published'] is False
    assert error.value.result['receipt_persisted'] is False


@pytest.mark.parametrize('kind',['scheduled','clock_budget','frame_key'])
def test_context_rejects_additional_active_input_and_clock_owners(session,tmp_path,kind):
    from fdisbull import qemu_workspace_output as output
    debug,_=prepared_host(session,tmp_path);_qualified(debug)
    if kind=='scheduled':
        debug.vm._physical_input=dict(pending=[],leases={},valid=True,schedule=dict(bound=True))
    elif kind=='clock_budget':debug.vm._active_clock_budget={'token':'active'}
    else:debug.vm._frame_key_owner={'held':['a']}
    with pytest.raises(ValueError):output._context(debug)
