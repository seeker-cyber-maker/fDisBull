"""CHIP-8 history contracts over real FDB artifacts and a stub checkpoint peer."""
from copy import deepcopy
import json
import threading
from types import SimpleNamespace
import uuid
import pytest

from fdisbull.project import Project
from fdisbull.chip8_history import Chip8HistoryMixin, bind_history_mutations, FORMAT, STATE_FORMAT, SUBSET


class Harness(Chip8HistoryMixin):
    def __init__(self,project,run):
        self.project=project;self.version=project.version();self.run_id=run;self.closed=False
        self.identity={'cpu_subset':SUBSET,'source_sha256':project.meta['source_sha256'],'qemu_sha256':'1'*64}
        self.metadata={'backend':'qemu-chip8','source_sha256':project.meta['source_sha256'],'version_sha256':self.version['sha256']}
        with project.transaction(True):project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',(run,self.version['id'],'authored',None,'stopped',json.dumps(self.metadata)))
        disk=project.path.parent/(run+'.qcow2');disk.write_bytes(b'authored')
        self.vm=SimpleNamespace(lock=threading.RLock(),operation_deadline=None,qmp=None,gdb=None,checkpoint_disk=disk,
            history_epoch=uuid.uuid4().hex,process=SimpleNamespace(poll=lambda:None))
        self._checkpoint_tool='authored';self.pc=0;self.calls=[];self.failure=None;self._chip8_hook_pending=None
    def _stopped(self):return None
    def _checkpoint_admit(self):
        self._history_supported()
    def close(self):self.closed=True
    def registers(self):return {'registers':{'pc':hex(self.pc)},'linear_pc':hex(self.pc)}
    def save_state(self,name,*,max_bytes=None,timeout_ms=60000):
        self.calls.append('save')
        if self.failure=='save':raise TimeoutError('lost save')
        data=json.dumps({'pc':self.pc}).encode()
        if len(data)>max_bytes:raise ValueError('limit')
        return self.project._debug_artifact(self.run_id,name,'state',data,
                    {'format':STATE_FORMAT,'identity':self.identity,'host_files_restored':False})
    def load_state(self,artifact,*,timeout_ms=60000):
        self.calls.append('load')
        if self.failure=='load':raise TimeoutError('lost load')
        row=self.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',(artifact,)).fetchone()
        self.pc=json.loads(bytes(row['data']))['pc'];self.vm.history_epoch=uuid.uuid4().hex
        return {'host_files_restored':False}
    def step(self,*,timeout_ms=10000):
        self.calls.append('step')
        if self.failure=='step':raise TimeoutError('lost step')
        self.pc+=1
        if self.failure=='known-stop':return {'outcome':'key_wait','timed_out':False,'session':{'state':'stopped','stop_reason':{'kind':'key_wait','breakpoint_ids':[]}}}
        return {'outcome':'step','timed_out':False,'session':{'state':'stopped','stop_reason':{'kind':'step','breakpoint_ids':[]}}}
    def layers(self,active=None,*,conflict='stop'):return {'active':active}


def _mutator(self,*args,**kwargs):self.calls.append('mutate')
for _name in ('run','write_memory','write_registers','breakpoint','delete_breakpoint','chip8_keypad','chip8_tick',
              'chip8_seed_rng','layer_enable','layer_patch','hook','delete_hook'):
    setattr(Harness,_name,_mutator)
bind_history_mutations(Harness)


@pytest.fixture
def project(tmp_path,monkeypatch):
    monkeypatch.setenv('FDISBULL_TARGET_STORE',str(tmp_path/'private'))
    source=tmp_path/'game.ch8';source.write_bytes(bytes.fromhex('6001 1200'))
    with Project.create(tmp_path/'game.fdb',source,arch='chip8',bits=16) as p:yield p


def test_persistent_branch_and_cold_attach(project):
    a=Harness(project,'a');root=a.rewind_start(max_steps=5,max_bytes=65536);first=a.rewind_record(count=2)
    assert root['format']==FORMAT and first['recorded_count']==2
    original=first['cursor'];a.rewind(node=root['cursor']);branch=a.rewind_record()
    assert original in branch['node_ids'] and branch['nodes'][-1]['parent']==root['cursor']
    b=Harness(project,'b');assert not b.rewind_start(history=branch['history'])['valid']
    restored=b.rewind(history=branch['history'],node=root['cursor'])
    assert restored['cursor']==root['cursor'] and b.pc==0


def test_mutation_invalidates_before_effect_and_capture_recovers(project):
    s=Harness(project,'a');root=s.rewind_start(max_steps=4,max_bytes=65536)
    s.layers();assert s.rewind_status()['valid']
    s.write_memory(0,'aa');assert not s.rewind_status()['valid']
    with pytest.raises(ValueError,match='cursor'):s.rewind_record()
    captured=s.rewind_record(advance='capture')
    assert captured['nodes'][-1]['parent']==root['cursor'] and captured['nodes'][-1]['edge']['kind']=='capture'


def test_budget_pending_and_corruption_fail_before_guest(project):
    s=Harness(project,'a');root=s.rewind_start(max_steps=2,max_bytes=65536)
    s._chip8_hook_pending='hook'
    with pytest.raises(ValueError,match='pending hook'):s.rewind_record()
    assert 'step' not in s.calls
    s._chip8_hook_pending=None;s.rewind_record()
    with pytest.raises(ValueError,match='budget'):s.rewind_record()
    checkpoint=root['nodes'][0]['checkpoint']['artifact']
    with project.transaction(True):project.db.execute('UPDATE debug_artifacts SET data=? WHERE id=?',(b'bad',checkpoint))
    with pytest.raises(ValueError,match='corrupt|inconsistent'):s.rewind(history=root['history'],node=root['cursor'])
    assert 'load' not in s.calls


def test_uncertain_step_leaves_pending_and_does_not_replay(project):
    s=Harness(project,'a');s.rewind_start(max_steps=3,max_bytes=65536);s.failure='step'
    with pytest.raises(TimeoutError):s.rewind_record()
    assert s.closed and s.calls.count('step')==1
    rows=project.db.execute("SELECT data FROM debug_artifacts WHERE kind='rewind-history' ORDER BY rowid").fetchall()
    assert json.loads(bytes(rows[-1]['data']))['pending']['kind']=='step'


@pytest.mark.parametrize('method', ['run','write_memory','write_registers','breakpoint','delete_breakpoint',
    'chip8_keypad','chip8_tick','chip8_seed_rng','layer_enable','layer_patch','hook','delete_hook'])
def test_each_unrecorded_mutation_invalidates(method,project):
    s=Harness(project,'a');s.rewind_start(max_steps=3,max_bytes=65536)
    getattr(s,method)()
    assert not s.rewind_status()['valid'] and s.rewind_status()['cursor'] is None


def test_known_stop_records_one_stopped_node_without_retirement_claim(project):
    s=Harness(project,'a');s.rewind_start(max_steps=4,max_bytes=65536);s.failure='known-stop'
    result=s.rewind_record(count=2)
    assert result['recorded_count']==1 and result['records'][0]['edge']['outcome']=='key_wait'
    assert result['records'][0]['edge']['completed_instruction'] is None


def test_older_profiles_cannot_start_history(project):
    s=Harness(project,'a');s.identity['cpu_subset']='fdisbull-chip8-classic-complete-3'
    with pytest.raises(ValueError,match='v4'):s.rewind_start()
    assert not s.calls


def test_saved_history_script_uses_real_project_and_shared_budget(project):
    from fdisbull.qemu_chip8 import Chip8DebugSession
    s=Harness(project,'a');s.capabilities={'rewind':True};s._budget=Chip8DebugSession._budget.__get__(s)
    s.script_operations=Chip8DebugSession.script_operations.fget(s)
    s.script=Chip8DebugSession.script.__get__(s);s._artifact=Chip8DebugSession._artifact.__get__(s)
    script={'format':'fdisbull-script-1','backend':'qemu-chip8',
            'steps':[{'op':'rewind-start','max_steps':4,'max_bytes':65536},
                     {'op':'rewind-record','count':1}]}
    saved=project.debug_save_script('route',script)
    report=s.script(script_id=saved['script_id'],timeout_ms=10000)
    assert report['ok'] and s.pc==1 and s.rewind_status()['valid']
    with project.transaction(True):project.db.execute('UPDATE debug_scripts SET sha256=? WHERE id=?',('0'*64,saved['script_id']))
    with pytest.raises(ValueError,match='hash mismatch'):s.script(script_id=saved['script_id'])


def test_tampered_checkpoint_control_metadata_refuses_before_restore_intent(project):
    s=Harness(project,'a');root=s.rewind_start(max_steps=3,max_bytes=65536)
    checkpoint=root['nodes'][0]['checkpoint']['artifact']
    row=project.db.execute('SELECT metadata FROM debug_artifacts WHERE id=?',(checkpoint,)).fetchone()
    document=json.loads(row['metadata']);document['hook_state']={'hooks':[{'actions':['tampered']}],'pending':None}
    before=project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='rewind-history'").fetchone()[0]
    with project.transaction(True):project.db.execute('UPDATE debug_artifacts SET metadata=? WHERE id=?',(json.dumps(document),checkpoint))
    with pytest.raises(ValueError,match='metadata hash'):s.rewind(history=root['history'],node=root['cursor'])
    after=project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='rewind-history'").fetchone()[0]
    assert before==after and 'load' not in s.calls and not s.closed


@pytest.mark.parametrize('capabilities,later', [
    ({'code_layers':False,'hooks':False,'save_states':False,'rewind':False,'frame':False},
     {'op':'layer-stack','active':[]}),
    ({'code_layers':True,'hooks':True,'save_states':False,'rewind':False,'frame':True},
     {'op':'save-state'}),
])
def test_script_rejects_unavailable_later_operation_before_prior_write(capabilities,later):
    from test_qemu_chip8 import session
    s=session();s.capabilities=capabilities;s.metadata={'backend':'qemu-chip8'}
    script={'format':'fdisbull-script-1','backend':'qemu-chip8','steps':[
        {'op':'write-memory','address':0x200,'data_hex':'aa','expected_hex':'00'},later]}
    before=bytes(s.vm.gdb.bytes)
    with pytest.raises(ValueError,match='Unsupported|unsupported'):
        s.script(script,timeout_ms=10000)
    assert bytes(s.vm.gdb.bytes)==before and not s.vm.gdb.requests
