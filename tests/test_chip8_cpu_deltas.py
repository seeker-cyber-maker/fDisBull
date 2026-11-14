"""Host contracts for CHIP-8 selected undo; no native guest execution."""
from copy import deepcopy
from types import SimpleNamespace
import pytest

from fdisbull.chip8_cpu_undo_runtime import validate_ranges, validate_registers, prepare
from fdisbull.chip8_cpu_deltas import Chip8CpuDeltaMixin
from test_chip8_history import project


def test_literal_and_reference_admission():
    assert validate_ranges([{'address':'0xfff','length':1}])[0]['address']=='0xfff'
    assert validate_ranges([{'address':'$address','length':1}],allow_references=True) is None
    assert validate_registers(['v0','pc'])==['v0','pc']
    assert validate_registers('$registers',allow_references=True) is None
    for ranges in ([{'address':4096,'length':1}], [{'address':0,'length':2},{'address':1,'length':1}],
                   [{'address':0,'length':4097}], [{'address':0,'length':1,'cs':0}]):
        with pytest.raises(ValueError):validate_ranges(ranges)
    for registers in (['sp'],['stack0'],['pc','pc']):
        with pytest.raises(ValueError):validate_registers(registers)


def test_inverse_plan_rebases_fetch_guard_on_restored_ram():
    mask=bytearray(4096);mask[0x300]=1
    fetch=bytearray(4096);fetch[0x300]=0x60
    old=bytearray(4096);old[0x300]=9
    observed=dict(all_ram=bytes(old),all_cpu={'v0':2},cpu={'v0':2},
        native_layer={'generation':4,'execute-mask-hex':mask.hex(),'execute-bytes-hex':fetch.hex()},
        environment={'state-generation':10})
    plan=prepare(None,[{'address':'0x300','length':1}],observed,{'v0':1},[b'\x07'])
    assert plan['arguments']['ram']==[{'address':0x300,'expected-hex':'09','data-hex':'07'}]
    assert plan['arguments']['execute']==[{'address':0x300,'expected-hex':'07','data-hex':'60'}]
    assert plan['edits']=={'v0':1}
    assert observed['all_ram'][0x300]==9


def test_frozen_guard_blocks_mutation_and_allows_recovery():
    class Harness(Chip8CpuDeltaMixin): pass
    h=Harness();h._qemu_cpu_delta_history={'valid':False,'frozen':True};h._qemu_history_live=None
    with pytest.raises(ValueError,match='frozen'):h._cpu_delta_before_operation('run')
    h._cpu_delta_before_operation('registers');h._cpu_delta_before_operation('timeline_rewind')
    h._cpu_delta_full_restore_complete()
    assert h._qemu_cpu_delta_history['frozen'] is False


def test_record_inverse_freezes_and_verified_anchor_recovers(project,monkeypatch):
    from test_chip8_history import Harness
    from fdisbull.chip8_history import KEY_SUBSET,KEY_STATE_FORMAT
    import fdisbull.chip8_cpu_undo_runtime as runtime
    import json, uuid

    class Subject(Chip8CpuDeltaMixin,Harness):
        def __init__(self, project, run):
            super().__init__(project,run);self.identity['cpu_subset']=KEY_SUBSET
            self.values={'v0':1,'pc':0x200};self.data=bytearray(4096);self.data[0x300]=2
        def _artifact(self,name,kind,data,metadata):return self.project._debug_artifact(self.run_id,name,kind,data,metadata)
        def _event(self,*args):pass
        def save_state(self,name,*,max_bytes=None,timeout_ms=60000):
            payload=json.dumps({'values':self.values,'data':self.data.hex()}).encode()
            return self._artifact(name,'state',payload,{'format':KEY_STATE_FORMAT,'identity':self.identity,'host_files_restored':False})
        def load_state(self,artifact,*,timeout_ms=60000):
            row=self.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',(artifact,)).fetchone()
            saved=json.loads(bytes(row['data']));self.values=saved['values'];self.data=bytearray.fromhex(saved['data'])
            self.vm.history_epoch=uuid.uuid4().hex
            return {'host_files_restored':False}
        def step(self,*,timeout_ms=10000):
            self.values['v0']=7;self.values['pc']=0x202;self.data[0x300]=9
            return {'outcome':'step','timed_out':False,'session':{'state':'stopped','stop_reason':{'kind':'step','breakpoint_ids':[]}}}
    def observe(s,ranges,registers):
        return {'cpu':{k:s.values[k] for k in registers},
                'ram':[bytes(s.data[int(r['address'],0):int(r['address'],0)+r['length']]) for r in ranges],
                'binding':{'owner':s.vm.history_epoch},'register_snapshot':{'linear_pc':hex(s.values['pc'])}}
    def prepare(s,ranges,old,cpu,ram):return {'ranges':ranges,'cpu':cpu,'ram':ram}
    def apply(s,plan):
        s.values.update(plan['cpu'])
        for r,data in zip(plan['ranges'],plan['ram']):
            start=int(r['address'],0);s.data[start:start+len(data)]=data
        return {'observation':observe(s,plan['ranges'],list(plan['cpu'])),'ram_transition':{'generation':1}}
    monkeypatch.setattr(runtime,'observe',observe);monkeypatch.setattr(runtime,'prepare',prepare);monkeypatch.setattr(runtime,'apply',apply)
    s=Subject(project,'undo');s._chip8_hooks={}
    root=s.cpu_delta_start([{'address':'0x300','length':1}],registers=['v0','pc'],max_bytes=1000000)
    assert root['valid'];recorded=s.cpu_delta_record();assert recorded['recorded_count']==1
    entry=recorded['records'][0]['artifact']
    metadata=project.db.execute('SELECT metadata FROM debug_artifacts WHERE id=?',(entry,)).fetchone()['metadata']
    with project.transaction(True):project.db.execute('UPDATE debug_artifacts SET metadata=? WHERE id=?',('{}',entry))
    with pytest.raises(ValueError,match='metadata'):s.cpu_delta_rewind()
    assert s.values['v0']==7 and not s.closed
    with project.transaction(True):project.db.execute('UPDATE debug_artifacts SET metadata=? WHERE id=?',(metadata,entry))
    result=s.cpu_delta_rewind();assert result['partial_restored'] and not result['execution_allowed']
    assert s.values=={'v0':1,'pc':0x200} and s.data[0x300]==2
    with pytest.raises(ValueError,match='frozen'):s._cpu_delta_before_operation('run')
    result=s.cpu_delta_recover();assert result['full_native_anchor_loaded'] and not result['history']['frozen']

    other=Subject(project,'second');other._chip8_hooks={}
    with project.transaction(True):
        with pytest.raises(ValueError,match='transaction'):
            other.cpu_delta_start([{'address':0x300,'length':1}],registers=['v0'])
    other.cpu_delta_start([{'address':0x300,'length':1}],registers=['v0'],max_bytes=1000000)
    calls=[]
    def event(name,value):
        if name=='qemu-cpu-delta-intent':
            calls.append(name)
            if len(calls)==2:raise RuntimeError('journal unavailable')
    other._event=event
    with pytest.raises(RuntimeError,match='journal') as error:other.cpu_delta_record(count=2)
    assert error.value.result['recorded_count']==1 and len(error.value.result['records'])==1
    assert error.value.result['do_not_replay'] and error.value.result['owner_closed'] and other.closed

    stale=Subject(project,'stale');stale._chip8_hooks={}
    stale.cpu_delta_start([{'address':0x300,'length':1}],registers=['v0'],max_bytes=1000000)
    stale.values['v0']=99
    with pytest.raises(ValueError,match='recorded state'):stale.cpu_delta_record()
    assert not stale.closed and stale.data[0x300]==2
    changed=Subject(project,'changed');changed._chip8_hooks={}
    changed.cpu_delta_start([{'address':0x300,'length':1}],registers=['v0'],max_bytes=1000000)
    changed.vm.history_epoch='different'
    status=changed.cpu_delta_status()
    assert not status['valid'] and 'identity changed' in status['invalid_reason']
    with pytest.raises(ValueError,match='epoch'):changed.cpu_delta_record()
    assert changed.values['v0']==1 and not changed.closed
    changed.close();status=changed.cpu_delta_status()
    assert not status['valid'] and not status['active'] and 'closed' in status['invalid_reason']

    exited=Subject(project,'exited');exited._chip8_hooks={}
    exited.cpu_delta_start([{'address':0x300,'length':1}],registers=['v0'],max_bytes=1000000)
    exited.vm.process=SimpleNamespace(poll=lambda:7)
    status=exited.cpu_delta_status()
    assert not status['valid'] and not status['active'] and not status['execution_allowed']
    assert 'exited' in status['invalid_reason'] and not exited.closed

    budget=Subject(project,'budget');budget._chip8_hooks={};events=[]
    budget.cpu_delta_start([{'address':0x300,'length':1}],registers=['v0'],max_steps=1,max_bytes=1000000)
    budget._event=lambda name,value:events.append(name)
    with pytest.raises(ValueError,match='budget'):budget.cpu_delta_record(count=2)
    assert events==[] and budget.values['v0']==1 and not budget.closed
    class BusyLock:
        def acquire(self,timeout):return False
    budget.vm.lock=BusyLock()
    with pytest.raises(TimeoutError,match='lock|acquire'):budget.cpu_delta_record()
    assert events==[] and budget.values['v0']==1

    uncertain=Subject(project,'uncertain');uncertain._chip8_hooks={}
    uncertain.cpu_delta_start([{'address':0x300,'length':1}],registers=['v0'],max_bytes=1000000)
    uncertain.cpu_delta_record()
    def broken_apply(session,plan):
        session.data[0x300]=42
        error=RuntimeError('uncertain inverse');error.result={'native_receipt':'unknown'}
        raise error
    monkeypatch.setattr(runtime,'apply',broken_apply)
    with pytest.raises(RuntimeError,match='uncertain inverse') as error:uncertain.cpu_delta_rewind()
    assert error.value.result['phase']=='inverse-dispatch'
    assert error.value.result['cause_result']=={'native_receipt':'unknown'}
    assert error.value.result['do_not_replay'] and uncertain.closed


def test_guarded_inverse_preserves_active_guest_changed_ram_and_fetch():
    from test_chip8_layers import machine
    from fdisbull.chip8_keys import KEY_SUBSET,KEY_ENV
    from fdisbull.chip8_cpu_undo_runtime import observe,prepare,apply
    s,add,native,env=machine()
    s.identity['cpu_subset']=KEY_SUBSET;s.vm.fault['cpu-subset']=KEY_SUBSET
    env.update({'cpu-subset':KEY_SUBSET,'env-model':KEY_ENV})
    s.vm.history_epoch='owner';s._chip8_frame_idle=lambda:None
    s._chip8_keys_query=lambda:dict(epoch=1,active=True,generation=2,**{'accepted-edges':1,'held-mask':1,'key-mask':1,'state-generation':env['state-generation']})
    add('ram','ram',0x300,'00','01');add('fetch','execute',0x200,'00','60')
    s.layers(['ram','fetch']);s.vm.gdb.bytes[0x300]=9
    before=observe(s,[{'address':'0x300','length':1}],['v0'])
    plan=prepare(s,[{'address':'0x300','length':1}],before,{'v0':before['cpu']['v0']},[b'\x01'])
    result=apply(s,plan)
    assert result['observation']['ram']==[b'\x01']
    assert s._layer_active==['ram','fetch'] and s._layer_ram_applied[0x300]==1
    assert s.code(0x200,length=1,view='execute')['hex']=='60'
    assert result['ram_transition']['generation']==2


@pytest.mark.parametrize('source_id', ['full-artifact', 'reconstructed-frame'])
@pytest.mark.parametrize('stage_failure', [False, True])
def test_frozen_restore_scopes_hook_reinstall_and_preserves_failed_owner(source_id,stage_failure,monkeypatch):
    import hashlib
    import fdisbull.qemu_chip8 as module
    import fdisbull.qemu_checkpoint as checkpoint
    from test_chip8_layers import machine
    from test_qemu_chip8 import VM
    from fdisbull.chip8_keys import KEY_SUBSET,KEY_ENV

    s,add,native,env=machine();s.identity.update(cpu_subset=KEY_SUBSET,qemu_sha256='hash',checkpoint_tool_sha256='hash')
    s.vm.fault['cpu-subset']=KEY_SUBSET;env.update({'cpu-subset':KEY_SUBSET,'env-model':KEY_ENV})
    s._qemu_cpu_delta_history={'valid':False,'frozen':True,'invalid_reason':'partial'}
    s._executable='binary';s._checkpoint_tool='tool';s._rom=b'authored';s.rpc=s.vm
    s._checkpoint_admit=lambda:None;s._chip8_frame_idle=lambda:None;s._chip8_key_adopt=lambda saved:{}
    s._chip8_layer_query=lambda:deepcopy(native)
    monkeypatch.setattr(module,'_file_sha',lambda value:'hash')
    monkeypatch.setattr(module,'_validate_environment',lambda value:deepcopy(value))
    monkeypatch.setattr(module,'validate_key_snapshot',lambda *args:None)
    monkeypatch.setattr(module,'_environment_receipt',lambda qmp:deepcopy(env))
    monkeypatch.setattr(module,'_fault_receipt',lambda qmp,subset:deepcopy(s.vm.fault))
    monkeypatch.setattr(checkpoint,'validate_qcow_header',lambda *args:None)
    monkeypatch.setattr(checkpoint,'snapshot_job',lambda *args,**kwargs:None)
    created=[]
    def owner(*args,**kwargs):
        new=VM();new.fault['cpu-subset']=KEY_SUBSET;new.history_epoch='new';created.append(new);return new
    monkeypatch.setattr(module,'_Owner',owner)
    old=s.vm;regs=s.registers();data=b'authored checkpoint';hook='a'*32
    metadata={'format':'fdisbull-qemu-chip8-state-6','identity':deepcopy(s.identity),
              'environment':deepcopy(env),'key_state':{},'tag':'tag','registers':regs,
              'ram_sha256':hashlib.sha256(bytes(old.gdb.bytes)).hexdigest(),
              'fault':deepcopy(old.fault),'layer_native':deepcopy(native),'layer_state':s._chip8_layer_state(),
              'hook_state':{'pending':None,'hooks':[{'hook':hook,'address':0x200,'once':False,
                 'max_hits':5,'hits':1,'actions':[{'op':'registers','registers':{'v0':{'expected':0,'value':1}}}]}]}}
    s.capabilities['hooks']=True
    install=s._restore_chip8_hooks
    def restore(state):
        mapping=install(state)
        if stage_failure:raise ValueError('staged hook failure')
        return mapping
    s._restore_chip8_hooks=restore
    if stage_failure:
        with pytest.raises(ValueError,match='staged hook failure'):
            s._load_state_data(data,metadata,source_id=source_id)
        assert s.vm is old and not old.closed and created[0].closed
        assert s._qemu_cpu_delta_history['frozen'] and s._qemu_cpu_delta_full_load_depth==0
        with pytest.raises(ValueError,match='frozen'):s._cpu_delta_before_operation('run')
    else:
        result=s._load_state_data(data,metadata,source_id=source_id)
        assert result['hooks'][hook] in s.breakpoints and old.closed
        assert not s._qemu_cpu_delta_history['frozen'] and s._qemu_cpu_delta_full_load_depth==0


def test_frozen_restore_invalid_metadata_never_replaces_owner(monkeypatch):
    from test_qemu_chip8 import session
    s=session();s._qemu_cpu_delta_history={'valid':False,'frozen':True,'invalid_reason':'partial'}
    s._checkpoint_admit=lambda:None;old=s.vm
    with pytest.raises(ValueError,match='identity'):
        s._load_state_data(b'bad',{'format':'wrong','identity':{}},source_id='corrupt')
    assert s.vm is old and not old.closed and s._qemu_cpu_delta_history['frozen']
    assert getattr(s,'_qemu_cpu_delta_full_load_depth',0)==0


def test_screenshot_rechecks_freeze_after_acquiring_owner_budget():
    from contextlib import contextmanager
    from test_qemu_chip8_devices import device
    s,_,_,artifacts=device();captured=[]
    s._qemu_cpu_delta_history={'frozen':False}
    @contextmanager
    def acquired(owner,deadline):
        s._qemu_cpu_delta_history['frozen']=True
        yield
    s._budget=acquired
    s.frame_rgba=lambda **kwargs:captured.append('frame')
    with pytest.raises(ValueError,match='frozen'):s.screenshot()
    assert captured==[] and artifacts==[] and not s.closed
