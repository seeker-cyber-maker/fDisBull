"""Host protocol/restore contracts; synthetic packets are not guest evidence."""
from copy import deepcopy
import pytest
from fdisbull import qemu_dos_provenance as witness
from test_qemu_workspace import session
from test_qemu_workspace_edits import prepared_host
from test_qemu_workspace_output import _qualified


def packet():
    return {'api-version':1,'model':witness.MODEL,'epoch':1,'generation':1,
            'active':False,'valid':True,'phase':'idle','token':'owner-token',
            'child-psp':0x300,'created-handle':5,'dos-path':'D:\\SAVE.DAT',
            'int21-vector':0,
            'source-ranges':[{'start':0x1100,'size':0x100}],
            'create-seen':False,'write-count':0,'bytes-written':0,'commit-seen':False,
            'flush-seen':False,'close-seen':False,'event-count':0,'events':[],
            'pending':False,'payload-hex':''}


def ready(payload=b''):
    p=packet();p.update(active=True,phase='ready',**{'create-seen':True,'close-seen':True,'flush-seen':True})
    events=[]
    def add(fn,handle,ax=0,requested=0,accepted=0):
        events.append(dict(sequence=len(events)+1,function=fn,handle=handle,ax=ax,
            carry=False,requested=requested,accepted=accepted,**{'caller-pc':0x1100,'return-pc':0x1102}))
    add(0x5b,5,5)
    if payload:add(0x40,5,len(payload),len(payload),len(payload))
    add(0x3e,5);add(0x0d,0)
    p.update(events=events,**{'event-count':len(events),'bytes-written':len(payload),
                            'write-count':int(bool(payload)),'payload-hex':payload.hex()})
    return p


def document(payload=b''):
    return dict(format=witness.FORMAT,path='SAVE.DAT',observer_token='owner-token',
                size=len(payload),payload_sha256=witness._sha(payload),native=ready(payload))


@pytest.mark.parametrize('path',['C:\\SAVE.DAT','DIR\\SAVE.DAT','..\\SAVE.DAT','CON','CLOCK$','COM1','TOOLONGNAME.DAT'])
def test_guest_path_refuses_ambiguous_or_device_targets(path):
    with pytest.raises(ValueError):witness._path(path)


@pytest.mark.parametrize('payload',[b'',b'\0\xffsaved'])
def test_completed_native_proof_requires_byte_exact_ordered_returns(payload):
    assert witness.validate_proof_document(document(payload))['payload-hex']==payload.hex()


@pytest.mark.parametrize('change',['raw_taint','pending','foreign_pc','order','short','wrong_handle','flags','payload','sequence'])
def test_corrupt_native_proof_cannot_grant_keep(change):
    doc=document(b'data');p=doc['native']
    if change=='raw_taint':p['valid']=False
    elif change=='pending':p['pending']=True
    elif change=='foreign_pc':p['events'][1]['caller-pc']=0x2000
    elif change=='order':p['events'][1]['function']=0x56
    elif change=='short':p['events'][1]['accepted']=1
    elif change=='wrong_handle':p['events'][1]['handle']=9
    elif change=='flags':p['events'][0]['carry']=True
    elif change=='payload':p['payload-hex']='00000000'
    else:p['events'][0]['sequence']=0
    with pytest.raises(ValueError):witness.validate_proof_document(doc)


def configured(session,tmp_path):
    debug,_=prepared_host(session,tmp_path);_qualified(debug)
    debug._vectors_before=bytes(1024)
    debug._process_checkpoint_verify_entry=lambda:None
    debug._process['source_mapping']={'live_ranges':[{'runtime_address':0x1100,'length':0x100}]}
    debug.vm.qmp_commands|=witness.COMMANDS
    class Qmp:
        info=packet()
        def call(self,command,args=None):
            if command==witness.ARM:
                self.info.update(active=True,phase='armed',token=args['token'],
                    **{'child-psp':args['child-psp'],'source-ranges':args['source-ranges'],
                       'dos-path':args['dos-path'],'int21-vector':args['int21-vector']})
            elif command==witness.DISARM:self.info['active']=False
            return deepcopy(self.info)
    debug.vm.qmp=Qmp()
    return debug


def test_start_status_stop_bind_the_real_source_owner(session,tmp_path):
    debug=configured(session,tmp_path)
    armed=debug.workspace_provenance_start('D:\\SAVE.DAT')
    assert armed['native']['phase']=='armed' and armed['policy'] is None
    assert debug.workspace_provenance_status()['binding']['path']=='SAVE.DAT'
    saved=witness.capture_checkpoint(debug)
    assert saved['binding']['source_sha256']==debug.metadata['source_sha256']
    assert debug.workspace_provenance_stop()['native']['active'] is False


def test_cold_restore_requires_rotated_epoch_and_identical_native_ledger(session,tmp_path):
    debug=configured(session,tmp_path);debug.workspace_provenance_start('SAVE.DAT')
    saved=witness.capture_checkpoint(debug)
    with pytest.raises(ValueError,match='differs'):witness.verify_loaded(debug.vm,saved)
    debug.vm.qmp.info['epoch']=2;debug.vm.qmp.info['generation']=7
    actual=witness.verify_loaded(debug.vm,saved)
    witness.adopt(debug,saved,actual)
    debug.vm.qmp.info['pending']=True
    with pytest.raises(ValueError,match='differs'):witness.verify_loaded(debug.vm,saved)


def test_foreign_native_observer_and_unsupported_backend_refuse(session,tmp_path):
    debug=configured(session,tmp_path);debug.vm.qmp.info['active']=True
    with pytest.raises(ValueError):witness.capture_checkpoint(debug)
    debug.vm.qmp_commands-=witness.COMMANDS
    assert witness.query(debug.vm) is None
    with pytest.raises(ValueError):debug.workspace_provenance_start('SAVE.DAT')


def test_arming_requires_original_entry_before_native_or_policy_effects(session,tmp_path):
    debug=configured(session,tmp_path)
    def changed_entry():raise ValueError('not original entry')
    debug._process_checkpoint_verify_entry=changed_entry
    with pytest.raises(ValueError,match='original entry'):
        debug.workspace_provenance_start('SAVE.DAT')
    assert debug.vm.qmp.info['active'] is False
    assert getattr(debug,'_dos_save_witness',None) is None


def test_arm_event_failure_closes_owner_and_reports_binding(session,tmp_path,monkeypatch):
    debug=configured(session,tmp_path)
    def fail_event(kind,value):raise OSError('receipt failed')
    monkeypatch.setattr(debug,'_event',fail_event)
    with pytest.raises(OSError,match='receipt failed') as error:
        witness.start(debug,'SAVE.DAT')
    assert debug.closed
    assert error.value.result['binding']['observer_token']==debug.vm.qmp.info['token']
    assert 'do not replay' in error.value.result['disposition']


def test_capture_failure_retains_created_checkpoint_effects(session,tmp_path,monkeypatch):
    debug=configured(session,tmp_path);witness.start(debug,'SAVE.DAT')
    token=debug.vm.qmp.info['token'];debug.vm.qmp.info.update(ready(b'data'),token=token)
    monkeypatch.setattr(witness,'_boundary',lambda s:{'stable':True})
    sealed={'checkpoint':123,'workspace':{'generation':{'artifact':456}}}
    monkeypatch.setattr(witness,'_seal_workspace',lambda s:sealed)
    def missing_file(*args):raise ValueError('missing sealed file')
    monkeypatch.setattr(witness,'_select_output',missing_file)
    with pytest.raises(ValueError,match='missing sealed file') as error:
        witness.provenance(debug)
    assert error.value.result['checkpoint']==123
    assert error.value.result['generation']=={'artifact':456}
    assert error.value.result['export_published'] is False


def test_host_mutation_taints_only_live_witness_and_full_restore_can_rebind(session,tmp_path):
    debug=configured(session,tmp_path);witness.start(debug,'SAVE.DAT')
    witness.before_host_operation(debug,'registers')
    assert not debug._dos_save_witness.get('host_fault')
    debug._qemu_cpu_delta_full_load_depth=1
    witness.before_host_operation(debug,'write_memory')
    assert not debug._dos_save_witness.get('host_fault')
    debug._qemu_cpu_delta_full_load_depth=0
    witness.before_host_operation(debug,'write_memory')
    assert debug._dos_save_witness['host_fault']=='Unobserved host mutation: write_memory'


@pytest.mark.parametrize('surface',['query','boundary'])
def test_post_seal_observation_failure_closes_owner_with_checkpoint(session,tmp_path,monkeypatch,surface):
    debug=configured(session,tmp_path);witness.start(debug,'SAVE.DAT')
    token=debug.vm.qmp.info['token'];debug.vm.qmp.info.update(ready(b'data'),token=token)
    sealed={'checkpoint':123,'workspace':{'generation':{'artifact':456}}}
    after_seal=False
    def seal(s):
        nonlocal after_seal
        after_seal=True
        return sealed
    original=witness.query
    def query(vm):
        if after_seal and surface=='query':raise OSError('observation failed')
        return original(vm)
    def boundary(s):
        if after_seal and surface=='boundary':raise OSError('observation failed')
        return {'stable':True}
    monkeypatch.setattr(witness,'query',query)
    monkeypatch.setattr(witness,'_boundary',boundary)
    monkeypatch.setattr(witness,'_seal_workspace',seal)
    with pytest.raises(OSError,match='observation failed') as error:
        witness.provenance(debug)
    assert debug.closed
    assert error.value.result['checkpoint']==123
