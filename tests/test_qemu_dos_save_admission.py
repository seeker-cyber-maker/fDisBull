"""Host admission and immutable predecessor checks; packets are synthetic."""
from copy import deepcopy
import pytest
from fdisbull import qemu_dos_provenance as witness
from fdisbull.dos_file_layers import WorkspaceStore
from test_qemu_workspace import session
from test_qemu_dos_provenance import configured,document
from test_dos_save_operations import create


def configured_save(session,tmp_path):
    debug=configured(session,tmp_path);old=debug.vm.qmp
    vectors=bytearray(debug._vectors_before);vectors[0x84:0x88]=(0x12345678).to_bytes(4,'little')
    debug._vectors_before=bytes(vectors)
    debug.vm.qmp_commands|={witness.ARM_SAVE}
    class Qmp:
        info=old.info
        arms=[]
        def call(self,command,args=None):
            if command==witness.ARM_SAVE:
                self.arms.append(deepcopy(args));self.info=create()
                initial=bytes.fromhex(args['initial-payload-hex']);exists=args['initial-exists']
                self.info.update(phase='armed',events=[],token=args['token'],**{
                    'child-psp':args['child-psp'],'int21-vector':args['int21-vector'],
                    'source-ranges':args['source-ranges'],'dos-path':args['dos-path'],
                    'temporary-path':args['temporary-path'],'initial-exists':exists,
                    'initial-payload-hex':initial.hex(),'event-count':0,'write-count':0,
                    'bytes-written':0,'payload-hex':'','current-path':args['dos-path'] if exists else '',
                    'file-exists':exists,'final-exists':exists,'temporary-exists':False,
                    'file-offset':0,'final-size':len(initial),'file-open':False,
                    'create-seen':False,'close-seen':False,'flush-seen':False})
            elif command==witness.DISARM:self.info['active']=False
            return deepcopy(self.info)
    debug.vm.qmp=Qmp()
    return debug


def stage(debug,path='SAVE.DAT',data=b'data',authored=True):
    store=WorkspaceStore(debug);generation=debug._dos_workspace['generation']['artifact']
    if authored:ref=store.create_file(generation,path,data)
    else:
        entries=store.load(generation)['entries']+[dict(path=path,dos_path=path,type='file',data=data,
                    attributes=0x20,dos_date=0x21,dos_time=0)]
        ref=store.seal(entries,parent=generation)
    debug._dos_workspace['generation']=ref
    return ref


def prior_proof(debug,generation,data=b'data'):
    doc=document(data);doc.update(version=debug.version['id'],source_sha256=debug.metadata['source_sha256'],
        base_generation=debug._dos_workspace['base_generation']['artifact'],generation=generation)
    ref=debug._artifact('synthetic-prior.json',witness.KIND,witness._json(doc),{})
    return dict(artifact=ref['artifact'],sha256=ref['sha256'])


def test_save_mode_arms_distinct_native_command_and_binds_preimage(session,tmp_path):
    debug=configured_save(session,tmp_path);created=stage(debug)
    result=debug.workspace_provenance_start('SAVE.DAT',mode='save',temporary_path='TEMP.DAT')
    binding=result['binding'];assert binding['initial_exists'] and binding['initial_payload_hex']==b'data'.hex()
    assert binding['arm_generation']==created['artifact'] and binding['temporary_path']=='TEMP.DAT'
    assert debug.vm.qmp.arms[0]['temporary-path']=='D:\\TEMP.DAT'
    saved=witness.capture_checkpoint(debug);witness.validate_checkpoint(debug,saved)
    saved['binding']['initial_payload_hex']='00'
    with pytest.raises(ValueError):witness.validate_checkpoint(debug,saved)


def test_save_mode_requires_extension_without_native_effect(session,tmp_path):
    debug=configured_save(session,tmp_path);debug.vm.qmp_commands.remove(witness.ARM_SAVE)
    with pytest.raises(ValueError,match='N23'):debug.workspace_provenance_start('SAVE.DAT',mode='save')
    assert not debug.vm.qmp.arms and not debug.closed


def test_unproven_existing_save_requires_exact_stored_predecessor(session,tmp_path):
    debug=configured_save(session,tmp_path);ref=stage(debug,authored=False)
    with pytest.raises(ValueError,match='predecessor'):
        debug.workspace_provenance_start('SAVE.DAT',mode='save')
    proof=prior_proof(debug,ref['artifact'])
    result=debug.workspace_provenance_start('SAVE.DAT',mode='save',predecessor=proof)
    assert result['binding']['predecessor']==proof
    witness._verify_arm_preimage(debug,result['binding'])


@pytest.mark.parametrize('bad',['hash','bytes'])
def test_predecessor_mismatch_cannot_admit_existing_save(session,tmp_path,bad):
    debug=configured_save(session,tmp_path);ref=stage(debug,authored=False)
    proof=prior_proof(debug,ref['artifact'],data=b'wrong' if bad=='bytes' else b'data')
    if bad=='hash':proof['sha256']='0'*64
    with pytest.raises(ValueError):debug.workspace_provenance_start('SAVE.DAT',mode='save',predecessor=proof)
    assert not debug.vm.qmp.arms


@pytest.mark.parametrize('options',[{'path':'DATA.TXT'},
    {'path':'SAVE.DAT','temporary_path':'DATA.TXT'},
    {'path':'SAVE.DAT','temporary_path':'SAVE.DAT'},
    {'path':'SAVE.DAT','temporary_path':'TEMP.DAT'}])
def test_protected_or_existing_temporary_paths_refuse_before_arm(session,tmp_path,options):
    debug=configured_save(session,tmp_path);stage(debug,path='TEMP.DAT')
    with pytest.raises(ValueError):debug.workspace_provenance_start(mode='save',**options)
    assert not debug.vm.qmp.arms


def test_save_predecessor_cannot_admit_missing_file(session,tmp_path):
    debug=configured_save(session,tmp_path)
    with pytest.raises(ValueError,match='no current file'):
        debug.workspace_provenance_start('SAVE.DAT',mode='save',predecessor={'artifact':'none','sha256':'0'*64})
    assert not debug.vm.qmp.arms
